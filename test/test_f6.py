"""F6 单元测试：纯函数逻辑 + 真实场景回归 + 边界用例。

运行 (容器内):
    docker exec burnroomvideo_byblender-app-server-1 python3 -m unittest test.test_f6 -v
"""
import sys
import unittest
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.F6_detect import calc_burn_ratio, find_ignition_point, load_pano

DATA_DIR = PROJECT_ROOT / "data" / "KK-EEz16cmU14"


class TestBurnRatio(unittest.TestCase):
    """合成图像：固定输入 → 固定期望输出。"""

    def test_all_black_is_burn(self) -> None:
        image = np.zeros((16, 16, 3), dtype=np.uint8)  # 纯黑 → 全部炭化
        self.assertEqual(calc_burn_ratio(image), 1.0)

    def test_all_white_is_clean(self) -> None:
        image = np.full((16, 16, 3), 255, dtype=np.uint8)  # 纯白 → 无烧痕
        self.assertEqual(calc_burn_ratio(image), 0.0)

    def test_mid_gray_is_clean(self) -> None:
        image = np.full((16, 16, 3), 128, dtype=np.uint8)  # 中性灰: 亮度与饱和度均不达标
        self.assertEqual(calc_burn_ratio(image), 0.0)


@unittest.skipUnless(DATA_DIR.is_dir(), "缺少场景数据 data/KK-EEz16cmU14")
class TestFindIgnition(unittest.TestCase):
    """真实场景回归：侧室 A/B 的固定预期起火点。"""

    def test_side_a_ignition_is_38(self) -> None:
        result = find_ignition_point(DATA_DIR, [32, 34, 36, 38])
        self.assertEqual(result.ignition_point, 38)

    def test_side_b_ignition_is_40(self) -> None:
        result = find_ignition_point(DATA_DIR, [40, 42])
        self.assertEqual(result.ignition_point, 40)


class TestEdgeCases(unittest.TestCase):
    """边界用例。"""

    def test_empty_point_list_raises(self) -> None:
        with self.assertRaises(ValueError):
            find_ignition_point(DATA_DIR, [])

    def test_missing_image_raises(self) -> None:
        with self.assertRaises(FileNotFoundError):
            load_pano(DATA_DIR, 99999)


if __name__ == "__main__":
    unittest.main()
