"""F6 本地验证脚本：对侧室 A/B 的测试全景图跑起火点识别。

用法:
    本机 (需已安装 opencv-python-headless):
        python test/test_f6.py
    容器 (推荐, 与生产环境一致):
        docker compose exec app-server python3 test/test_f6.py
"""
import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
# 将项目根目录加入 sys.path，保证 `python test/test_f6.py` 直接运行时能 import app
sys.path.insert(0, str(PROJECT_ROOT))

try:
    from app.F6_detect import find_ignition_point
except ModuleNotFoundError as exc:
    # 仅当缺失的是 cv2 本身时才提示；其他导入错误原样抛出
    if exc.name == "cv2":
        raise SystemExit(
            "缺少依赖 (cv2)。请先安装 opencv-python-headless，"
            "或直接在容器内运行:\n"
            "    docker compose exec app-server python3 test/test_f6.py"
        ) from exc
    raise

DEFAULT_DATA_DIR = PROJECT_ROOT / "data" / "KK-EEz16cmU14"

# 最小 Scope: 侧室 A 与 侧室 B 的点位 (全景图文件名即点位 ID)
SIDE_ROOMS: dict[str, list[int]] = {
    "侧室A": [32, 34, 36, 38],
    "侧室B": [40, 42],
}


def run_room(data_dir: Path, room_name: str, point_ids: list[int]) -> None:
    """对单个房间跑 F6，打印每个点位占比与最终起火点。"""
    result = find_ignition_point(data_dir, point_ids)
    print(f"\n=== {room_name} ===")
    for stat in result.stats:
        bar = "#" * round(stat.burn_ratio * 100)
        print(f"  点位 {stat.point_id}: 烧痕占比 {stat.burn_ratio * 100:.2f}%  {bar}")
    print(f"  🔥 起火点: {result.ignition_point} (占比 {result.max_ratio * 100:.2f}%)")


def main() -> None:
    parser = argparse.ArgumentParser(description="F6 起火点识别本地验证")
    parser.add_argument(
        "--data-dir", type=Path, default=DEFAULT_DATA_DIR, help="场景数据目录"
    )
    args = parser.parse_args()

    if not args.data_dir.is_dir():
        raise SystemExit(f"数据目录不存在: {args.data_dir}")

    for room_name, point_ids in SIDE_ROOMS.items():
        run_room(args.data_dir, room_name, point_ids)


if __name__ == "__main__":
    main()
