from fastapi import FastAPI, HTTPException
import os
import requests
import urllib.request
import json  # 新增了 json 库用来保存文件
import subprocess
import threading
import traceback
from pathlib import Path

from app.F6_detect import find_ignition_point
from app.F7_spread import SpreadTimeline, bfs_spread, load_adjacency
from app.observability import (
    append_log,
    now_iso,
    read_render_status,
    start_gpu_sampler,
    verify_output,
    write_event,
    write_failure,
    write_render_status,
)
from app.s3_io import (
    SHARE_EXPIRES_SECONDS,
    download_scene_assets,
    ensure_share_output,
    get_share_url,
    upload_output,
)

app = FastAPI(title="火灾蔓延视频生成系统 API")

BASE_URL = "https://api.4dkankan.com"
APP_KEY = os.getenv("DK_APPKEY")

DATA_ROOT = Path("/app/data")  # 场景资产根目录 (与下载接口保存路径一致)

RENDER_SCRIPT_PATH = Path(__file__).resolve().parent / "F8_blender_render.py"
BLENDER_BIN = "blender"

HEADERS = {
    "Content-Type": "application/json",
    "Authorization": APP_KEY
}

@app.get("/")
def read_root():
    return {"status": "Backend is running!", "appkey_loaded": bool(APP_KEY)}

@app.get("/api/scenes")
def get_all_scenes():
    url = f"{BASE_URL}/scene/getSceneList"
    payload = {"pageNum": 1, "pageSize": 50}
    response = requests.post(url, headers=HEADERS, json=payload).json()
    if response.get("code") == 0:
        scenes = [{"场景名称": item.get("sceneName"), "sceneCode": item.get("sceneCode")} for item in response.get("data", {}).get("list", [])]
        return {"status": "success", "总数量": response["data"]["total"], "场景列表": scenes}
    raise HTTPException(status_code=400, detail="获取失败")

def scene_assets_cached(scene_dir: Path) -> bool:
    """核心资产和点位对应的全景图均非空时，才允许跳过下载。"""
    mesh = scene_dir / "mesh.obj"
    points = scene_dir / "points.json"
    try:
        if not mesh.is_file() or mesh.stat().st_size == 0 or not points.is_file():
            return False
        raw_points = json.loads(points.read_text(encoding="utf-8"))
        if not isinstance(raw_points, list) or not raw_points:
            return False
        for point in raw_points:
            pano = scene_dir / f"{int(point['device'])}.jpg"
            if not pano.is_file() or pano.stat().st_size == 0:
                return False
    except (OSError, ValueError, KeyError, TypeError):
        return False
    return True


@app.get("/api/download_scene/{scene_code}")
def download_scene_files(scene_code: str):
    '''终极版：下载场景全景图、模型，并额外保存点位信息 points.json'''
    
    save_dir = f"/app/data/{scene_code}"
    os.makedirs(save_dir, exist_ok=True)
    downloaded_files = []

    # F6 依赖全景图，不能只凭 mesh.obj + points.json 判断缓存完整。
    if scene_assets_cached(Path(save_dir)):
        return {
            "status": "已缓存, 跳过下载 (核心资产齐全)",
            "sceneCode": scene_code,
            "详细信息": ["mesh.obj + points.json + 点位全景图完整, 未重复下载"],
        }

    try:
        # 1. 下载全景图
        pano_url = f"{BASE_URL}/scene/getScenePanorama"
        pano_res = requests.post(pano_url, headers=HEADERS, json={"sceneCode": scene_code}).json()
        if pano_res.get("code") == 0 and pano_res.get("data"):
            for link in pano_res["data"]:
                filename = link.split("/")[-1]
                filepath = os.path.join(save_dir, filename)
                if not os.path.isfile(filepath) or os.path.getsize(filepath) == 0:
                    urllib.request.urlretrieve(link, filepath)
                downloaded_files.append(f"全景图已存: {filename}")

        # 2. 下载模型文件
        obj_url = f"{BASE_URL}/scene/getSceneObj"
        obj_res = requests.post(obj_url, headers=HEADERS, json={"sceneCode": scene_code}).json()
        if obj_res.get("code") == 0 and obj_res.get("data"):
            for link in obj_res["data"]:
                filename = link.split("/")[-1]
                filepath = os.path.join(save_dir, filename)
                if not os.path.isfile(filepath) or os.path.getsize(filepath) == 0:
                    urllib.request.urlretrieve(link, filepath)
                downloaded_files.append(f"模型已存: {filename}")

        # 3. 获取并保存点位信息 (新增环节！)
        point_url = f"{BASE_URL}/scene/getScenePointInfo"
        point_res = requests.post(point_url, headers=HEADERS, json={"sceneCode": scene_code}).json()
        if point_res.get("code") == 0 and point_res.get("data"):
            points_path = os.path.join(save_dir, "points.json")
            # 把返回的数据存成 json 文件
            with open(points_path, "w", encoding="utf-8") as f:
                json.dump(point_res["data"], f, ensure_ascii=False, indent=2)
            downloaded_files.append("🎯 点位信息已存: points.json")

        return {
            "status": "所有资产获取成功！", 
            "sceneCode": scene_code, 
            "详细信息": downloaded_files
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"下载过程中发生错误: {str(e)}")


@app.post("/api/generate_timeline/{scene_code}")
def generate_timeline(scene_code: str) -> SpreadTimeline:
    """串联 F6 + F7：识别全局起火点，生成蔓延时序并落盘 timeline.json。"""

    # 1. 校验场景目录与 points.json 是否存在
    scene_dir = DATA_ROOT / scene_code
    if not scene_dir.is_dir():
        raise HTTPException(status_code=404, detail=f"场景目录不存在: {scene_code}")
    points_path = scene_dir / "points.json"
    if not points_path.is_file():
        raise HTTPException(status_code=404, detail=f"points.json 不存在: {scene_code}")

    # 2. 解析拓扑，筛选有对应全景图 (device.jpg) 的合法点位
    adjacency = load_adjacency(points_path)
    valid_points = sorted(
        point_id
        for point_id in adjacency
        if (scene_dir / f"{point_id}.jpg").is_file()
    )
    if not valid_points:
        raise HTTPException(
            status_code=404, detail=f"场景 {scene_code} 内没有可用的点位图片"
        )

    # 3. F6: 全局起火点识别
    f6_result = find_ignition_point(scene_dir, valid_points)

    # 4. F7: 以起火点为根生成蔓延时序
    timeline = bfs_spread(adjacency, f6_result.ignition_point)

    # 5. 落盘 timeline.json
    (scene_dir / "timeline.json").write_text(
        timeline.model_dump_json(indent=2), encoding="utf-8"
    )

    # 6. 返回完整时序数据模型
    return timeline


@app.post("/api/render/{scene_code}")
def start_render(scene_code: str, quality: str = "preview") -> dict:
    """F8 渲染接口: 拉取资产 -> 启动 Blender 子进程 -> 后台守护线程完成验证与上传。

    铁律: 绝不 import bpy, Blender 通过 subprocess 完全独立运行。
    quality: preview=720p 快速验证 / final=1080p 正式出片 (V6.0 参数化)。
    """
    if quality not in ("preview", "final"):
        raise HTTPException(
            status_code=400, detail=f"quality 仅支持 preview/final: {quality}"
        )
    scene_dir = DATA_ROOT / scene_code
    if not scene_dir.is_dir():
        raise HTTPException(status_code=404, detail=f"场景目录不存在: {scene_code}")

    # 幂等保护: 已有渲染在进行时直接返回当前状态
    existing = read_render_status(scene_dir)
    if existing and existing.get("status") == "running":
        return {"scene_code": scene_code, **existing}

    # ---- 前期准备: 从 MinIO 补齐依赖资产 (timeline.json 等) ----
    write_event(scene_dir, "prepare", "asset_download_start")
    try:
        summary = download_scene_assets(scene_code, scene_dir)
        write_event(
            scene_dir, "prepare", "asset_download_done",
            detail=f"拉取 {summary['pulled']} 个, 跳过 {summary['skipped']} 个, 失败 {summary['failed']} 个",
        )
    except Exception as exc:  # MinIO 不可用时仅警告, 本地资产齐全仍可渲染
        append_log(scene_dir, f"[prepare/警告] MinIO 资产下载失败: {exc}")
    if not (scene_dir / "timeline.json").is_file():
        raise HTTPException(
            status_code=404,
            detail=f"timeline.json 不存在，请先调用 POST /api/generate_timeline/{scene_code}",
        )

    # 覆盖机制: 启动渲染前清除旧产物, 防止新渲染失败时误判为旧视频成功
    old_output = scene_dir / "output.mp4"
    if old_output.exists():
        old_output.unlink()
        write_event(scene_dir, "prepare", "old_output_removed", detail="已清除上一轮的 output.mp4")

    # ---- 实时进程: 启动 Blender 子进程 (不等待) ----
    cmd = [
        BLENDER_BIN, "--background",
        "--python", str(RENDER_SCRIPT_PATH),
        "--", "--scene", scene_code, "--quality", quality,
    ]
    log_file = (scene_dir / "render.log").open("w", encoding="utf-8")
    proc = subprocess.Popen(
        cmd,
        cwd=str(RENDER_SCRIPT_PATH.parent.parent),
        stdout=log_file,
        stderr=subprocess.STDOUT,
    )
    log_file.close()  # 子进程持有 fd 副本, 关闭本进程引用不影响写日志
    write_event(scene_dir, "process", "blender_started", detail=f"pid={proc.pid}")

    write_render_status(
        scene_dir,
        scene_code=scene_code,
        status="running",
        pid=proc.pid,
        output="output.mp4",
        started_at=now_iso(),
    )

    # ---- 后台守护: GPU 指标采样线程 + 结果验证与上传线程 ----
    start_gpu_sampler(
        scene_dir,
        is_running=lambda: proc.poll() is None,
        on_overheat=lambda _temp: proc.terminate(),  # GPU 超温自动终止渲染
    )
    threading.Thread(
        target=_watch_render,
        args=(proc, scene_dir, scene_code),
        name=f"render-watcher-{scene_code}",
        daemon=True,
    ).start()

    return {
        "scene_code": scene_code,
        "status": "running",
        "pid": proc.pid,
        "status_endpoint": f"/api/render/{scene_code}/status",
    }


def _watch_render(proc: subprocess.Popen[bytes], scene_dir: Path, scene_code: str) -> None:
    """守护线程: 等待 Blender 退出 -> 验证产物 -> 上传 MinIO -> 收敛任务状态。"""
    try:
        return_code = proc.wait()
        output_path = verify_output(scene_dir)
        if return_code == 0 and output_path is not None:
            size_mb = output_path.stat().st_size / (1024 * 1024)
            write_event(
                scene_dir, "verify", "output_ok",
                detail=f"output.mp4 大小 {size_mb:.2f} MB",
            )
            output_object: str | None = None
            try:
                output_object = upload_output(scene_code, output_path)
                write_event(
                    scene_dir, "upload", "output_uploaded",
                    detail=f"MinIO 对象: {output_object}",
                )
            except Exception as exc:
                append_log(scene_dir, f"[upload/警告] 产物上传 MinIO 失败: {exc}")
            write_render_status(
                scene_dir,
                scene_code=scene_code,
                status="done",
                pid=proc.pid,
                output="output.mp4",
                output_size_bytes=output_path.stat().st_size,
                output_object=output_object,
                finished_at=now_iso(),
            )
        else:
            summary = f"Blender 退出码 {return_code}, output.mp4 {'存在' if output_path else '不存在'}"
            write_failure(scene_dir, summary)
            write_render_status(
                scene_dir,
                scene_code=scene_code,
                status="failed",
                pid=proc.pid,
                failure=summary,
                finished_at=now_iso(),
            )
    except Exception:
        write_failure(scene_dir, f"守护线程异常: {traceback.format_exc()}")
        write_render_status(
            scene_dir, scene_code=scene_code, status="failed", finished_at=now_iso()
        )


@app.get("/api/render/{scene_code}/status")
def get_render_status(scene_code: str) -> dict:
    """查询渲染进度快照 (守护线程自动收敛终态, 此处兜底进程意外消失的情况)。"""
    scene_dir = DATA_ROOT / scene_code
    status = read_render_status(scene_dir)
    if status is None:
        raise HTTPException(status_code=404, detail=f"场景 {scene_code} 尚未发起渲染")
    if status.get("status") == "running":
        pid = status.get("pid")
        if pid is None or not Path(f"/proc/{pid}").is_dir():
            output_path = verify_output(scene_dir)
            final_status = "done" if output_path is not None else "failed"
            status = {**status, "status": final_status, "finished_at": now_iso()}
            write_render_status(scene_dir, **status)
    return status


@app.get("/api/render/{scene_code}/share")
def get_render_share(scene_code: str) -> dict:
    """V6.0: 复用已有成片，补齐 MinIO 对象并生成七天预签名播放链接。"""
    if not scene_code.isascii() or not all(c.isalnum() or c in "-_" for c in scene_code):
        raise HTTPException(status_code=400, detail="无效的场景编号")
    scene_dir = DATA_ROOT / scene_code
    status = read_render_status(scene_dir)
    if status and status.get("status") == "running":
        raise HTTPException(status_code=409, detail="渲染仍在进行，请完成后再分享")
    output_path = verify_output(scene_dir)
    if output_path is None:
        raise HTTPException(status_code=404, detail=f"场景 {scene_code} 尚无渲染产物")
    try:
        object_name = ensure_share_output(scene_code, output_path)
        url = get_share_url(scene_code)
    except Exception as exc:
        # 不把带凭证的请求 URL 或底层异常文本写入公开响应/日志。
        write_event(
            scene_dir, "share", "share_url_failed",
            status="failed", detail=type(exc).__name__,
        )
        raise HTTPException(
            status_code=502,
            detail="生成分享链接失败，请检查 MinIO 连接、凭证及对外端点配置",
        ) from None
    write_event(
        scene_dir, "share", "share_url_created",
        detail=f"object={object_name} expires_in_seconds={SHARE_EXPIRES_SECONDS}",
    )
    return {
        "scene_code": scene_code, "url": url,
        "expires_in_seconds": SHARE_EXPIRES_SECONDS,
    }


@app.post("/api/pipeline/{scene_code}")
def run_pipeline(scene_code: str, quality: str = "preview") -> dict:
    """V6.0 流水线编排: 一键执行 下载(缓存去重) -> 起火点与时序 -> 渲染。"""
    if quality not in ("preview", "final"):
        raise HTTPException(status_code=400, detail="quality 仅支持 preview/final")
    scene_dir = DATA_ROOT / scene_code
    steps: dict = {}

    # 1. 资产就位 (download 接口内部自带缓存去重)
    try:
        assets = download_scene_files(scene_code)
        steps["assets"] = assets.get("status", "ok")
    except HTTPException as exc:
        return {
            "scene_code": scene_code, "status": "failed",
            "step": "download", "detail": exc.detail,
        }

    # 2. 蔓延时序就位 (已存在则复用)
    if not (scene_dir / "timeline.json").is_file():
        try:
            generate_timeline(scene_code)
        except HTTPException as exc:
            return {
                "scene_code": scene_code, "status": "failed",
                "step": "timeline", "detail": exc.detail,
            }
    steps["timeline"] = "ready"

    # 3. 异步拉起渲染
    render_result = start_render(scene_code, quality)
    steps["render"] = render_result.get("status")

    return {
        "scene_code": scene_code,
        "status": render_result.get("status", "running"),
        "steps": steps,
        "status_endpoint": f"/api/render/{scene_code}/status",
    }
