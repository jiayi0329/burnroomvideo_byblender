"""F7 单元测试：拓扑解析、BFS 时序与边界用例。

运行 (容器内):
    docker exec burnroomvideo_byblender-app-server-1 python3 -m unittest test.test_f7 -v
"""
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.F7_spread import bfs_spread, load_adjacency

POINTS_PATH = PROJECT_ROOT / "data" / "KK-EEz16cmU14" / "points.json"

# 手工拓扑 (不依赖数据文件): 1-2 相连, 3 孤立
TOY = {1: [2], 2: [1], 3: []}


class TestLoadAdjacency(unittest.TestCase):
    @unittest.skipUnless(POINTS_PATH.is_file(), "缺少 points.json")
    def test_real_scene_spot_checks(self) -> None:
        adjacency = load_adjacency(POINTS_PATH)
        self.assertEqual(adjacency[38], [34, 36])          # 侧室A 边缘点位
        self.assertEqual(adjacency[40], [0, 4, 32, 42])    # 侧室B 门边点位


class TestBfsSpread(unittest.TestCase):
    def test_depth2_spread_order(self) -> None:
        timeline = bfs_spread(TOY, 1, max_depth=2)
        events = [(e.time, e.point) for e in timeline.spread_events]
        self.assertEqual(events, [(0, 1), (5, 2)])

    def test_isolated_node_single_event(self) -> None:
        timeline = bfs_spread(TOY, 3, max_depth=2)
        self.assertEqual([(e.time, e.point) for e in timeline.spread_events], [(0, 3)])

    def test_depth_zero_only_start(self) -> None:
        timeline = bfs_spread(TOY, 1, max_depth=0)
        self.assertEqual(len(timeline.spread_events), 1)

    def test_unknown_start_raises(self) -> None:
        with self.assertRaises(ValueError):
            bfs_spread(TOY, 99)

    @unittest.skipUnless(POINTS_PATH.is_file(), "缺少 points.json")
    def test_real_room_a_timeline(self) -> None:
        adjacency = load_adjacency(POINTS_PATH)
        timeline = bfs_spread(adjacency, 38)
        self.assertEqual(
            [(e.time, e.point) for e in timeline.spread_events],
            [(0, 38), (5, 34), (5, 36), (10, 32)],
        )


if __name__ == "__main__":
    unittest.main()
