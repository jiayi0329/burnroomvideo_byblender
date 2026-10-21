"""MinIO 数据流转: 渲染前拉取依赖资产, 渲染后上传产物 (S3 SDK 交互层)。

桶约定:
  burnroom-assets   场景资产 (对象键: {scene_code}/{filename})
  burnroom-outputs  渲染产物 (对象键: {scene_code}/output.mp4)
连接配置从容器环境变量注入 (MINIO_ENDPOINT / MINIO_ROOT_USER / MINIO_ROOT_PASSWORD)。
"""
import json
import os
from pathlib import Path

from minio import Minio
from minio.error import S3Error

ASSETS_BUCKET = "burnroom-assets"
OUTPUTS_BUCKET = "burnroom-outputs"


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
    client.fput_object(OUTPUTS_BUCKET, object_name, str(local_mp4))
    return object_name


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
    """生成产物公开访问链接 (对外端点由环境变量 MINIO_PUBLIC_ENDPOINT 配置)。"""
    endpoint = os.getenv("MINIO_PUBLIC_ENDPOINT", "http://172.25.76.201:9000")
    return f"{endpoint.rstrip('/')}/{bucket}/{scene_code}/output.mp4"
