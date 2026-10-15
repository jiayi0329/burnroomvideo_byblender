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
from app.s3_io import download_scene_assets, upload_output

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

@app.get("/api/download_scene/{scene_code}")
def download_scene_files(scene_code: str):
    '''终极版：下载场景全景图、模型，并额外保存点位信息 points.json'''
    
    save_dir = f"/app/data/{scene_code}"
    os.makedirs(save_dir, exist_ok=True)
    downloaded_files = []

    try:
        # 1. 下载全景图
        pano_url = f"{BASE_URL}/scene/getScenePanorama"
        pano_res = requests.post(pano_url, headers=HEADERS, json={"sceneCode": scene_code}).json()
        if pano_res.get("code") == 0 and pano_res.get("data"):
            for link in pano_res["data"]:
                filename = link.split("/")[-1]
                filepath = os.path.join(save_dir, filename)
                if not os.path.exists(filepath): # 如果已经下载过就不重复下载了，节省时间
                    urllib.request.urlretrieve(link, filepath)
                downloaded_files.append(f"全景图已存: {filename}")

        # 2. 下载模型文件
        obj_url = f"{BASE_URL}/scene/getSceneObj"
        obj_res = requests.post(obj_url, headers=HEADERS, json={"sceneCode": scene_code}).json()
        if obj_res.get("code") == 0 and obj_res.get("data"):
            for link in obj_res["data"]:
                filename = link.split("/")[-1]
                filepath = os.path.join(save_dir, filename)
                if not os.path.exists(filepath):
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
def start_render(scene_code: str) -> dict:
    """F8 渲染接口: 拉取资产 -> 启动 Blender 子进程 -> 后台守护线程完成验证与上传。

    铁律: 绝不 import bpy, Blender 通过 subprocess 完全独立运行。
    """
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

    # ---- 实时进程: 启动 Blender 子进程 (不等待) ----
    cmd = [
        BLENDER_BIN, "--background",
        "--python", str(RENDER_SCRIPT_PATH),
        "--", "--scene", scene_code,
    ]
    log_file = (scene_dir / "render.log").open("w", encoding="utf-8")
    proc = subprocess.Popen(
        cmd,
        cwd=str(RENDER_SCRIPT_PATH.parent.parent),
        stdout=log_file,
        stderr=subprocess.STDOUT,
        env={**os.environ, "LIBGL_ALWAYS_SOFTWARE": "1"},  # 无 GPU 环境下强制软件渲染
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
    start_gpu_sampler(scene_dir, is_running=lambda: proc.poll() is None)
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