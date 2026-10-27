"""MinIO 数据流转: 渲染前拉取依赖资产, 渲染后上传产物 (S3 SDK 交互层)。

桶约定:
  burnroom-assets   场景资产 (对象键: {scene_code}/{filename})
  burnroom-outputs  渲染产物 (对象键: {scene_code}/output.mp4)
连接配置从容器环境变量注入 (MINIO_ENDPOINT / MINIO_ROOT_USER / MINIO_ROOT_PASSWORD)。
"""
import json
import os
from datetime import timedelta
from pathlib import Path
from urllib.parse import urlsplit

from minio import Minio
from minio.error import S3Error

ASSETS_BUCKET = "burnroom-assets"
OUTPUTS_BUCKET = "burnroom-outputs"
SHARE_EXPIRES_SECONDS = 7 * 24 * 60 * 60


def get_minio_client() -> Minio:
    """按环境变量构造 MinIO 客户端。"""
    endpoint = os.getenv("MINIO_ENDPOINT", "minio-oss:9000")
    access_key = os.getenv("MINIO_ROOT_USER", "admin_blender")
    secret_key = os.getenv("MINIO_ROOT_PASSWORD", "")
    return Minio(endpoint, access_key=access_key, secret_key=secret_key, secure=False)


def ensure_buckets(client: Minio) -> None:
    """确保资产桶与产物桶存在 (不存在则创建)。"""
    for bucket in (ASSETS_BUCKET, OUTPUTS_BUCKET):
        if not client.bucket_exists(bucket):
            client.make_bucket(bucket)


def download_scene_assets(scene_code: str, scene_dir: Path) -> dict:
    """从 MinIO 下载场景依赖资产 (timeline.json 等) 到本地场景目录。

    只补齐本地缺失的文件; 返回统计信息。
    """
    client = get_minio_client()
    ensure_buckets(client)
    summary: dict = {"pulled": 0, "skipped": 0, "failed": 0, "files": []}
    for obj in client.list_objects(
        ASSETS_BUCKET, prefix=f"{scene_code}/", recursive=True
    ):
        filename = Path(obj.object_name).name
        local_path = scene_dir / filename
        if local_path.is_file():
            summary["skipped"] += 1
            continue
        try:
            client.fget_object(ASSETS_BUCKET, obj.object_name, str(local_path))
            summary["pulled"] += 1
            summary["files"].append(filename)
        except S3Error as exc:
            summary["failed"] += 1
            summary["files"].append(f"{filename}(失败: {exc.code})")
    return summary


def upload_output(scene_code: str, local_mp4: Path) -> str:
    """上传渲染产物 output.mp4 到产物桶, 返回对象键。"""
    client = get_minio_client()
    ensure_buckets(client)
    object_name = f"{scene_code}/output.mp4"
    client.fput_object(
        OUTPUTS_BUCKET, object_name, str(local_mp4), content_type="video/mp4"
    )
    return object_name


def ensure_share_output(scene_code: str, local_mp4: Path) -> str:
    """复用已有视频；对象缺失、大小或媒体类型不一致时补传，不触发渲染。"""
    client = get_minio_client()
    object_name = f"{scene_code}/output.mp4"
    try:
        obj = client.stat_object(OUTPUTS_BUCKET, object_name)
    except S3Error as exc:
        if exc.code not in ("NoSuchKey", "NoSuchObject", "NoSuchBucket"):
            raise
    else:
        if obj.size == local_mp4.stat().st_size and obj.content_type == "video/mp4":
            return object_name
    return upload_output(scene_code, local_mp4)


def set_bucket_public_read(bucket: str = OUTPUTS_BUCKET) -> None:
    """把产物桶设为公开只读 (Public/Read-only), 使对象可免认证访问。"""
    client = get_minio_client()
    ensure_buckets(client)
    policy = json.dumps(
        {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {"AWS": ["*"]},
                    "Action": ["s3:GetObject"],
                    "Resource": [f"arn:aws:s3:::{bucket}/*"],
                }
            ],
        }
    )
    client.set_bucket_policy(bucket, policy)


def get_share_url(scene_code: str, bucket: str = OUTPUTS_BUCKET) -> str:
    """按浏览器可达主机签名，生成七天有效的直接播放链接。"""
    endpoint = os.getenv("MINIO_PUBLIC_ENDPOINT", "http://172.25.76.201:9000").strip()
    parsed = urlsplit(endpoint)
    if (
        parsed.scheme not in ("http", "https")
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in ("", "/")
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("MINIO_PUBLIC_ENDPOINT 必须是 http(s)://主机[:端口]，不含路径或凭证")
    # 显式指定区域使签名在本地完成，避免从容器访问对外入口查询区域。
    client = Minio(
        parsed.netloc,
        access_key=os.getenv("MINIO_ROOT_USER", "admin_blender"),
        secret_key=os.getenv("MINIO_ROOT_PASSWORD", ""),
        secure=parsed.scheme == "https",
        region=os.getenv("MINIO_REGION", "us-east-1"),
    )
    if not os.getenv("MINIO_ROOT_PASSWORD"):
        raise ValueError("未配置 MinIO 签名凭证")
    return client.presigned_get_object(
        bucket, f"{scene_code}/output.mp4",
        expires=timedelta(seconds=SHARE_EXPIRES_SECONDS),
        response_headers={
            "response-content-type": "video/mp4",
            "response-content-disposition": 'inline; filename="output.mp4"',
        },
    )
