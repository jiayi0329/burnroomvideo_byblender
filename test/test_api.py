"""API 集成测试：POST /api/generate_timeline/{scene_code} 正常链路与 404 边界。

运行 (容器内):
    docker exec burnroomvideo_byblender-app-server-1 python3 -m unittest test.test_api -v
"""
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from fastapi.testclient import TestClient

from app.main import app

SCENE_CODE = "KK-EEz16cmU14"
TIMELINE_PATH = PROJECT_ROOT / "data" / SCENE_CODE / "timeline.json"


class TestGenerateTimeline(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not (PROJECT_ROOT / "data" / SCENE_CODE).is_dir():
            raise unittest.SkipTest(f"缺少场景数据 {SCENE_CODE}")
        cls.client = TestClient(app)

    def test_normal_flow(self) -> None:
        response = self.client.post(f"/api/generate_timeline/{SCENE_CODE}")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIsInstance(payload["start_point"], int)
        self.assertTrue(payload["spread_events"])
        self.assertEqual(
            payload["spread_events"][0],
            {"time": 0, "point": payload["start_point"]},
        )
        self.assertTrue(TIMELINE_PATH.is_file())  # timeline.json 已落盘

    def test_missing_scene_returns_404(self) -> None:
        response = self.client.post("/api/generate_timeline/SCENE_NOT_EXIST")
        self.assertEqual(response.status_code, 404)
        self.assertIn("不存在", response.json()["detail"])


if __name__ == "__main__":
    unittest.main()
