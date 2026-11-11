"""F7 蔓延时序生成：读取 points.json 拓扑，从起火点出发做 BFS，输出时间轴。

纯函数模块，不依赖 FastAPI / Blender，可独立在容器或本机运行。

拓扑键约定：points.json 中每个点位有 id (内部编号) 与 device (全景图文件名编号)。
F6 输出的起火点是图片编号 (device)，因此本模块的邻接表统一以 device 为键，
保证 F6 → F7 可直接衔接。
"""
import json
from pathlib import Path

from pydantic import BaseModel

# 蔓延层间时间间隔 (秒): 火势扩散到下一层相邻点位所需时间
LAYER_SECONDS = 5
# 默认最大蔓延层数 (BFS 深度)
DEFAULT_MAX_DEPTH = 2


class SpreadEvent(BaseModel):
    """单条蔓延事件: 某时刻某点位被引燃。"""

    time: int
    point: int


class SpreadTimeline(BaseModel):
    """F7 输出: 起火点 + 完整蔓延时间轴。"""

    start_point: int
    spread_events: list[SpreadEvent]


def load_adjacency(points_path: Path) -> dict[int, list[int]]:
    """解析 points.json，返回以图片编号 (device) 为键的邻接表 {点: [相邻点]}。"""
    raw_points: list[dict] = json.loads(points_path.read_text(encoding="utf-8"))

    id_to_device: dict[int, int] = {p["id"]: p["device"] for p in raw_points}

    adjacency: dict[int, list[int]] = {}
    for point in raw_points:
        device: int = point["device"]
        adjacency[device] = [
            id_to_device[visible_id]
            for visible_id in point.get("visibles", [])
            if visible_id in id_to_device
        ]
    return adjacency


def bfs_spread(
    adjacency: dict[int, list[int]],
    start_point_id: int,
    max_depth: int = DEFAULT_MAX_DEPTH,
    layer_seconds: int = LAYER_SECONDS,
) -> SpreadTimeline:
    """从起火点做 max_depth 层 BFS，生成蔓延时间轴。

    第 0 层 (起点) time=0；每向下一层，时间 +layer_seconds。
    """
    if start_point_id not in adjacency:
        raise ValueError(f"起火点 {start_point_id} 不在 points.json 拓扑中")

    events: list[SpreadEvent] = [SpreadEvent(time=0, point=start_point_id)]
    visited: set[int] = {start_point_id}
    frontier: list[int] = [start_point_id]
    time: int = 0

    for _ in range(max_depth):
        next_frontier: list[int] = []
        for current in frontier:
            for neighbor in adjacency.get(current, []):
                if neighbor not in visited:
                    visited.add(neighbor)
                    next_frontier.append(neighbor)
                    events.append(
                        SpreadEvent(time=time + layer_seconds, point=neighbor)
                    )
        if not next_frontier:
            break
        frontier = next_frontier
        time += layer_seconds

    return SpreadTimeline(start_point=start_point_id, spread_events=events)
