"""坐标与房间归属回归；使用合成数据，不包含真实户型或 API 数据。"""
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from app import analyze_floorplan as align


def room(room_id: str, polygon: list[align.Point], valid: bool = True) -> dict:
    return {"room_id": room_id, "label": room_id, "polygon": polygon, "area_m2": align.area(polygon),
            "valid_candidate": valid, "problems": [], "warnings": []}


SQUARE = [(0, 0), (3, 0), (3, 3), (0, 3)]


class TestRoomGeometry(unittest.TestCase):
    def test_concave_polygon_not_bounding_box(self) -> None:
        polygon = [(0, 0), (3, 0), (3, 1), (1, 1), (1, 3), (0, 3)]
        self.assertTrue(align.contains((0.5, 2), polygon))
        self.assertFalse(align.contains((2, 2), polygon))
        self.assertAlmostEqual(align.area(polygon), 5)

    def test_intersection_including_non_adjacent_touch(self) -> None:
        self.assertFalse(align.self_intersects(SQUARE))
        self.assertTrue(align.self_intersects([(0, 0), (3, 3), (0, 3), (3, 0)]))
        self.assertTrue(align.self_intersects([(0, 0), (2, 0), (2, 2), (1, 0), (0, 2)]))

    def test_interior_boundary_outside_and_overlap(self) -> None:
        rooms = [room("A", SQUARE)]
        self.assertEqual(align.classify((1, 1), rooms)["room_id"], "A")
        for point in ((0, 1), (-0.05, 1), (0.05, 1)):
            result = align.classify(point, rooms)
            self.assertEqual(result["status"], "boundary")
            self.assertIsNone(result["room_id"])
        self.assertEqual(align.classify((-1, 1), rooms)["status"], "outside")
        rooms.append(room("B", [(1, 0), (4, 0), (4, 3), (1, 3)]))
        self.assertEqual(align.classify((2, 2), rooms)["status"], "overlap")

    def test_invalid_room_not_assigned(self) -> None:
        result = align.classify((1, 1), [room("bad", SQUARE, False)])
        self.assertIsNone(result["room_id"])
        self.assertIn("bad", result["invalid_room_hits"])

    def test_overlap_excludes_shared_boundary(self) -> None:
        a = room("A", SQUARE)
        b = room("B", [(3, 0), (5, 0), (5, 3), (3, 3)])
        self.assertEqual(align.room_overlap_candidates([a, b]), [])
        self.assertEqual(align.room_overlap_candidates([a, room("copy", SQUARE)]), [["A", "copy"]])
        self.assertEqual(align.room_overlap_candidates([a, room("B", [(1, 0), (4, 0), (4, 3), (1, 3)])]), [["A", "B"]])

    def test_missing_tiny_and_self_crossing_rooms_flagged(self) -> None:
        floor = {
            "points": {str(i): {"x": x, "y": y} for i, (x, y) in enumerate(SQUARE + [(0, 0.01), (0.01, 0)])},
            "rooms": [
                {"roomId": "good", "wallPointIDs": ["0", "1", "2", "3"], "area": 9},
                {"roomId": "missing", "wallPointIDs": ["0", "absent", "2"]},
                {"roomId": "tiny", "wallPointIDs": ["0", "4", "5"]},
                {"roomId": "cross", "wallPointIDs": ["0", "2", "3", "1"]},
            ],
        }
        rooms = {r["room_id"]: r for r in align.parse_rooms(floor)}
        self.assertTrue(rooms["good"]["valid_candidate"])
        self.assertIn("missing_boundary_point", rooms["missing"]["problems"])
        self.assertIn("tiny_area", rooms["tiny"]["problems"])
        self.assertIn("self_intersection", rooms["cross"]["problems"])

    def test_finite_and_duplicate_room_validation(self) -> None:
        with self.assertRaises(ValueError):
            align.finite(float("nan"))
        with self.assertRaises(ValueError):
            align.parse_rooms({"points": {}, "rooms": [{"roomId": "A"}, {"roomId": "A"}]})

    def test_axis_transform(self) -> None:
        matrix = next(c["matrix"] for c in align.axis_candidates() if c["id"] == "x_neg_y")
        self.assertEqual(align.apply_transform((2, 3), matrix), (2, -3))
        self.assertEqual(len(align.axis_candidates()), 8)


class TestAnalysisWorkflow(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.scene = self.root / "data" / "KK-test"
        self.scene.mkdir(parents=True)
        self.probe_dir = self.root / "server_probe"
        self.probe_dir.mkdir()
        document = {"unit": "m", "floors": [{
            "id": 0, "panos": [], "points": {str(i): {"x": x, "y": y} for i, (x, y) in enumerate(SQUARE)},
            "rooms": [{"roomId": "A", "wallPointIDs": ["0", "1", "2", "3"], "tagName": "test", "area": 9}],
        }]}
        (self.probe_dir / "floor.json").write_text(json.dumps(document), encoding="utf-8")
        cameras = [{"device": d, "pose": {"translation": {"x": x, "y": y, "z": 1.5}}} for d, x, y in ((22, 1, 1), (24, 0.05, 1), (26, 4, 1))]
        (self.scene / "points.json").write_text(json.dumps(cameras), encoding="utf-8")
        (self.scene / "mesh.obj").write_text("v 0 0 0\nv 3 0 0\nv 3 3 2\nv 0 3 2\nf 1 2 3\n", encoding="utf-8")
        (self.scene / "timeline.json").write_text(json.dumps({"start_point": 22, "spread_events": [{"point": 22, "time": 0}, {"point": 24, "time": 5}, {"point": 26, "time": 10}]}), encoding="utf-8")
        (self.scene / "output.mp4").write_bytes(b"keep old movie")
        (self.scene / "render_status.json").write_text('{"status":"done"}', encoding="utf-8")
        self.probe_report = {
            "scene_code": "KK-test", "status": "inspected", "local_baseline": {
                "points": {"count": 3}, "mesh": {"bytes": (self.scene / "mesh.obj").stat().st_size}},
            "api": {"assets": [{"json_documents": [{"name": "floorplan.json", "status": "inspected", "saved_as": "floor.json"}]}]},
        }
        self.save_probe()

    def save_probe(self) -> None:
        (self.probe_dir / "report.json").write_text(json.dumps(self.probe_report), encoding="utf-8")

    def test_provisional_membership_and_outputs_preserve_inputs(self) -> None:
        original = {p: p.read_bytes() for p in self.scene.iterdir()}
        report, chart = align.analyze(self.scene, self.probe_dir, transform_id="xy")
        self.assertFalse(report["alignment_verified"])
        self.assertFalse(report["floorplan_ready_for_crop"])
        self.assertEqual(report["ignition_candidate"]["room_id"], "A")
        self.assertEqual(report["target_room_event_devices_provisional"], [22])
        self.assertEqual([r["status"] for r in report["memberships_provisional"]], ["interior", "boundary", "outside"])
        out = self.scene / "diagnostics" / "alignment" / "test"
        align.write_outputs(out, report, chart)
        self.assertIn("candidate", (out / "overlay.html").read_text(encoding="utf-8"))
        self.assertEqual(len((out / "point_rooms.csv").read_text(encoding="utf-8-sig").splitlines()), 4)
        for path, content in original.items():
            self.assertEqual(path.read_bytes(), content)
        with self.assertRaises(FileExistsError):
            align.write_outputs(out, report, chart)

    def test_offline_wrong_scene_and_traversal_reports_rejected(self) -> None:
        for field, value in (("status", "offline"), ("scene_code", "other")):
            with self.subTest(field=field):
                original = self.probe_report[field]
                self.probe_report[field] = value
                self.save_probe()
                with self.assertRaises(ValueError):
                    align.resolve_source(self.probe_dir, "KK-test")
                self.probe_report[field] = original
        self.probe_report["api"]["assets"][0]["json_documents"][0]["saved_as"] = "../outside.json"
        self.save_probe()
        with self.assertRaises(ValueError):
            align.resolve_source(self.probe_dir, "KK-test")

    def test_mismatched_assets_and_unknown_axis_rejected(self) -> None:
        with self.assertRaises(ValueError):
            align.analyze(self.scene, self.probe_dir, transform_id="unknown")
        self.probe_report["local_baseline"]["mesh"]["bytes"] = 0
        self.save_probe()
        with self.assertRaises(ValueError):
            align.analyze(self.scene, self.probe_dir)

    def test_unknown_units_multiple_floors_and_missing_ignition_rejected(self) -> None:
        path = self.probe_dir / "floor.json"
        original = json.loads(path.read_text())
        for unit in ("cm", "unknown"):
            document = {**original, "unit": unit}
            path.write_text(json.dumps(document))
            with self.assertRaises(ValueError):
                align.analyze(self.scene, self.probe_dir)
        path.write_text(json.dumps({**original, "floors": original["floors"] * 2}))
        with self.assertRaises(ValueError):
            align.analyze(self.scene, self.probe_dir)
        path.write_text(json.dumps(original))
        (self.scene / "timeline.json").write_text('{"start_point":99,"spread_events":[]}')
        with self.assertRaises(ValueError):
            align.analyze(self.scene, self.probe_dir)

    def test_html_escapes_embedded_script_data(self) -> None:
        report, chart = align.analyze(self.scene, self.probe_dir, transform_id="xy")
        chart["rooms"][0]["label"] = "</script><script>untrusted()</script>"
        path = self.root / "plot.html"
        align.write_overlay(path, **chart)
        html = path.read_text(encoding="utf-8")
        self.assertNotIn("</script><script>untrusted()", html)
        self.assertIn("\\u003c/script>", html)

    def test_cli_uses_explicit_server_probe_path(self) -> None:
        argv = ["align", "--scene", "KK-test", "--data-root", str(self.root / "data"), "--probe-dir", str(self.probe_dir), "--transform", "xy"]
        output = io.StringIO()
        with patch("sys.argv", argv), contextlib.redirect_stdout(output):
            self.assertEqual(align.main(), 0)
        summary = json.loads(output.getvalue())
        self.assertFalse(summary["floorplan_ready_for_crop"])
        self.assertEqual(summary["ignition_candidate"]["room_id"], "A")
        self.assertTrue(Path(summary["output_dir"]).is_dir())


if __name__ == "__main__":
    unittest.main()
