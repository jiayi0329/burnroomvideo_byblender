"""渲染可观测性工具: 生命周期日志 + GPU 指标采样 + 失败追踪。

为未来 UI 可视化大屏准备的结构化数据 (全部落在 data/{scene_code}/ 下):
  logs/render.log           全生命周期文本日志 (带时间戳)
  logs/lifecycle.jsonl      结构化生命周期事件流 (每行一条 JSON)
  logs/failure.log          失败摘要 + Blender 原始日志尾部
  metrics/gpu_metrics.jsonl GPU 采样 (利用率/显存/温度, 渲染期间每 5 秒一条)
  render_status.json        当前任务状态快照
"""
import json
import subprocess
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

GPU_SAMPLE_INTERVAL_SECONDS = 5.0
GPU_TEMP_WARN_C = 85.0  # GPU 温度告警阈值 (℃)
GPU_TEMP_KILL_C = 90.0  # GPU 温度终止阈值 (℃), 超过则自动终止渲染
# nvidia-smi 查询语句 (CSV 无表头输出, 便于解析)
NVIDIA_SMI_QUERY = [
    "nvidia-smi",
    "--query-gpu=index,utilization.gpu,memory.used,memory.total,temperature.gpu",
    "--format=csv,noheader,nounits",
]
RENDER_STATUS_FILENAME = "render_status.json"


def now_iso() -> str:
    """当前 UTC 时间 ISO 字符串 (任务状态时间戳)。"""
    return datetime.now(timezone.utc).isoformat()


def _append_line(path: Path, text: str) -> None:
    """向文件追加一行, 自动创建父目录。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(text + "\n")


def append_log(scene_dir: Path, message: str) -> None:
    """向 data/{scene}/logs/render.log 追加一行带时间戳的日志。"""
    _append_line(scene_dir / "logs" / "render.log", f"[{now_iso()}] {message}")


def write_event(
    scene_dir: Path, phase: str, event: str, status: str = "ok", detail: str = ""
) -> None:
    """记录一条结构化生命周期事件 (lifecycle.jsonl + 文本日志双写)。"""
    record = {
        "ts": now_iso(),
        "phase": phase,
        "event": event,
        "status": status,
        "detail": detail,
    }
    _append_line(
        scene_dir / "logs" / "lifecycle.jsonl",
        json.dumps(record, ensure_ascii=False),
    )
    append_log(scene_dir, f"[{phase}/{status}] {event} {detail}".rstrip())


def write_render_status(scene_dir: Path, **fields: object) -> None:
    """把渲染任务状态快照写入 render_status.json。"""
    (scene_dir / RENDER_STATUS_FILENAME).write_text(
        json.dumps(fields, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def read_render_status(scene_dir: Path) -> dict | None:
    """读取渲染任务状态, 无记录时返回 None。"""
    status_path = scene_dir / RENDER_STATUS_FILENAME
    if not status_path.is_file():
        return None
    return json.loads(status_path.read_text(encoding="utf-8"))


def read_log_tail(scene_dir: Path, n_lines: int = 50) -> str:
    """读取 Blender 原始日志 (render.log) 的最后 n 行, 用于失败诊断。"""
    log_path = scene_dir / "render.log"
    if not log_path.is_file():
        return "(render.log 不存在)"
    lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    return "\n".join(lines[-n_lines:])


def write_failure(scene_dir: Path, summary: str) -> None:
    """失败时写 failure.log: 摘要 + render.log 尾部, 并记录结构化事件。"""
    content = (
        f"=== 失败时间: {now_iso()} ===\n"
        f"{summary}\n\n--- render.log 尾部 ---\n{read_log_tail(scene_dir)}\n"
    )
    (scene_dir / "logs" / "failure.log").write_text(content, encoding="utf-8")
    write_event(scene_dir, "verify", "render_failed", status="failed", detail=summary)


def verify_output(scene_dir: Path) -> Path | None:
    """检查 output.mp4 是否存在且非空, 返回其路径或 None。"""
    output_path = scene_dir / "output.mp4"
    if output_path.is_file() and output_path.stat().st_size > 0:
        return output_path
    return None


def sample_gpu_metrics(scene_dir: Path) -> float | None:
    """调用 nvidia-smi 采集一次 GPU 指标, 写入 metrics/gpu_metrics.jsonl。

    返回本次采样中所有 GPU 的最高温度 (℃); None 表示 GPU 不可用 (无 nvidia-smi
    或无 GPU), 调用方应停止采样。
    """
    try:
        result = subprocess.run(
            NVIDIA_SMI_QUERY, capture_output=True, text=True, timeout=10
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        append_log(scene_dir, "[gpu] nvidia-smi 不可用, 跳过 GPU 指标采样")
        return None
    if result.returncode != 0 or not result.stdout.strip():
        append_log(
            scene_dir,
            f"[gpu] nvidia-smi 返回异常: {result.stderr.strip() or '无输出'}",
        )
        return None

    max_temp = 0.0
    for line in result.stdout.strip().splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 5:
            continue
        temp_c = int(parts[4])
        max_temp = max(max_temp, float(temp_c))
        record = {
            "ts": now_iso(),
            "gpu": int(parts[0]),
            "util_pct": int(parts[1]),
            "mem_used_mb": int(parts[2]),
            "mem_total_mb": int(parts[3]),
            "temp_c": temp_c,
        }
        _append_line(
            scene_dir / "metrics" / "gpu_metrics.jsonl",
            json.dumps(record, ensure_ascii=False),
        )
    return max_temp


def start_gpu_sampler(
    scene_dir: Path,
    is_running: Callable[[], bool],
    on_overheat: Callable[[float], None] | None = None,
) -> threading.Thread:
    """启动后台采样线程: 渲染期间周期采样 GPU 指标并守护温度。

    温度达到 GPU_TEMP_WARN_C 时记录告警; 达到 GPU_TEMP_KILL_C 时记录事件
    并调用 on_overheat 回调 (通常用于终止渲染进程)。
    """
    def _loop() -> None:
        gpu_available = True
        while is_running() and gpu_available:
            max_temp = sample_gpu_metrics(scene_dir)
            if max_temp is None:
                gpu_available = False
                continue
            if max_temp >= GPU_TEMP_WARN_C:
                append_log(
                    scene_dir,
                    f"[gpu/告警] 最高温度 {max_temp:.0f}°C 超过告警阈值 {GPU_TEMP_WARN_C:.0f}°C",
                )
                if max_temp >= GPU_TEMP_KILL_C:
                    write_event(
                        scene_dir, "process", "gpu_overheat_abort",
                        status="failed",
                        detail=f"最高温度 {max_temp:.0f}°C >= {GPU_TEMP_KILL_C:.0f}°C, 自动终止渲染",
                    )
                    if on_overheat is not None:
                        on_overheat(max_temp)
                    return
            threading.Event().wait(GPU_SAMPLE_INTERVAL_SECONDS)

    thread = threading.Thread(
        target=_loop, name=f"gpu-sampler-{scene_dir.name}", daemon=True
    )
    thread.start()
    return thread
