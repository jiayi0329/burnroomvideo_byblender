"""F7 本地验证脚本：以侧室 A (38) / 侧室 B (40) 为起火点，打印蔓延时间轴。

用法:
    容器 (推荐):
        docker compose exec app-server python3 test/test_f7.py
    本机:
        python test/test_f7.py
"""
import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
# 将项目根目录加入 sys.path，保证直接运行脚本时能 import app
sys.path.insert(0, str(PROJECT_ROOT))

from app.F7_spread import SpreadTimeline, bfs_spread, load_adjacency

DEFAULT_POINTS_PATH = PROJECT_ROOT / "data" / "KK-EEz16cmU14" / "points.json"

# 最小 Scope: 侧室 A / 侧室 B 的 F6 起火点 (图片编号)
START_POINTS: dict[str, int] = {
    "侧室A": 38,
    "侧室B": 40,
}


def print_timeline(room_name: str, timeline: SpreadTimeline) -> None:
    """打印单条蔓延时间轴。"""
    print(f"\n=== {room_name} (起火点 {timeline.start_point}) ===")
    for event in timeline.spread_events:
        print(f"  t={event.time:>3}s  引燃点位 {event.point}")


def main() -> None:
    parser = argparse.ArgumentParser(description="F7 蔓延时序生成本地验证")
    parser.add_argument(
        "--points", type=Path, default=DEFAULT_POINTS_PATH, help="points.json 路径"
    )
    args = parser.parse_args()

    if not args.points.is_file():
        raise SystemExit(f"points.json 不存在: {args.points}")

    adjacency = load_adjacency(args.points)
    for room_name, start_id in START_POINTS.items():
        timeline = bfs_spread(adjacency, start_id)
        print_timeline(room_name, timeline)


if __name__ == "__main__":
    main()
