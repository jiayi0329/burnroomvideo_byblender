"""户型探测回归：仅标准库、无网络、无 Blender。"""
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import zipfile

from app import probe_floorplan as probe


def response(payload: bytes, status: int = 200) -> Mock:
    result = Mock(status_code=status)
    result.__enter__ = Mock(return_value=result)
    result.__exit__ = Mock(return_value=False)
    result.iter_content.return_value = [payload]
    return result


class TestProbeParsing(unittest.TestCase):
    def test_redacts_nested_and_embedded_urls_and_credentials(self) -> None:
        value = {
            "token": "secret", "rooms": [{"id": 1, "polygon": [[0, 0], [1, 0], [1, 1]]}],
            "note": "key=private-key url=https://files.example.test/a?signature=private",
        }
        clean = probe.redact(value, "private-key")
        text = json.dumps(clean)
        self.assertNotIn("private-key", text)
        self.assertNotIn("signature=private", text)
        self.assertNotIn('"secret"', text)
        self.assertEqual(clean["rooms"], value["rooms"])

    def test_candidate_fields_are_evidence_not_validated_geometry(self) -> None:
        hints = probe.field_hints({"rooms": [{"polygon": [[0, 0]], "units": "m"}]})
        paths = {hint["path"] for hint in hints}
        self.assertIn("$.rooms", paths)
        self.assertIn("$.rooms[0].polygon", paths)
        self.assertIn("$.rooms[0].units", paths)

    def test_private_or_authenticated_download_addresses_rejected(self) -> None:
        for url in ("file:///etc/passwd", "http://127.0.0.1/a", "http://169.254.169.254/a", "http://localhost/a", "https://user:pass@example.test/a"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                probe.validate_download_url(url)
        probe.validate_download_url("https://files.example.test/a?signature=value")

    def test_body_limit(self) -> None:
        with self.assertRaises(ValueError):
            probe.bounded_body(response(b"12345"), 4)


class TestProbeArchives(unittest.TestCase):
    def test_zip_members_never_extracted_using_untrusted_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            archive = root / "asset.bin"
            with zipfile.ZipFile(archive, "w") as stream:
                stream.writestr("../../outside.json", json.dumps({"rooms": [], "token": "private"}))
                stream.writestr("floorplan.json", json.dumps({"polygon": [[1, 2], [3, 4]]}))
            result = probe.inspect_archive(archive, root)
            self.assertEqual(result["member_count"], 2)
            self.assertEqual(result["json_documents"][0]["status"], "inspected")
            self.assertFalse((root / "outside.json").exists())
            self.assertNotIn("private", (root / "asset_member_0000_redacted.json").read_text())
            self.assertEqual(len(list(root.glob("*_redacted.json"))), 2)

    def test_large_json_member_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            archive = root / "asset.bin"
            with zipfile.ZipFile(archive, "w") as stream:
                stream.writestr("huge.json", "x" * 100)
            with patch.object(probe, "MAX_JSON_BYTES", 20):
                result = probe.inspect_archive(archive, root)
            self.assertEqual(result["json_documents"][0]["status"], "skipped_size_limit")

    def test_non_zip_json_and_unknown_format(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path = root / "asset.bin"
            path.write_text('{"rooms": []}', encoding="utf-8")
            self.assertEqual(probe.inspect_archive(path, root)["format"], "json")
            path.write_bytes(b"not json")
            self.assertEqual(probe.inspect_archive(path, root)["format"], "non_zip")


class TestProbeAPI(unittest.TestCase):
    def test_queries_expected_api_and_download_does_not_receive_appkey(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            api = response(json.dumps({"code": 0, "data": {"url": "https://files.example.test/a?signature=hidden"}}).encode())
            asset = response(b'{"rooms": [{"id": 1}]}')
            requests = SimpleNamespace(post=Mock(return_value=api), get=Mock(return_value=asset))
            with patch.dict(sys.modules, {"requests": requests}):
                result = probe.probe_api("KK-test", root, "private-appkey")
            self.assertEqual(result["status"], "inspected")
            self.assertEqual(result["assets"][0]["format"], "json")
            self.assertEqual(requests.post.call_args.args[0], probe.API_URL)
            self.assertEqual(requests.post.call_args.kwargs["json"], {"sceneCode": "KK-test"})
            self.assertEqual(requests.post.call_args.kwargs["headers"]["Authorization"], "private-appkey")
            self.assertNotIn("headers", requests.get.call_args.kwargs)
            self.assertFalse(requests.get.call_args.kwargs["allow_redirects"])
            self.assertNotIn("signature=hidden", (root / "api_response_redacted.json").read_text())

    def test_api_error_and_no_data_do_not_download(self) -> None:
        for payload, expected in (({"code": 403, "data": "https://files.example.test/a"}, "api_rejected"), ({"code": 0, "data": None}, "no_data")):
            with self.subTest(payload=payload), tempfile.TemporaryDirectory() as temp:
                requests = SimpleNamespace(post=Mock(return_value=response(json.dumps(payload).encode())), get=Mock())
                with patch.dict(sys.modules, {"requests": requests}):
                    result = probe.probe_api("KK-test", Path(temp), "key")
                self.assertEqual(result["status"], expected)
                requests.get.assert_not_called()

    def test_redirect_is_reported_without_following(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            payload = {"code": 0, "data": ["https://files.example.test/a"]}
            requests = SimpleNamespace(post=Mock(return_value=response(json.dumps(payload).encode())), get=Mock(return_value=response(b"", 302)))
            with patch.dict(sys.modules, {"requests": requests}):
                result = probe.probe_api("KK-test", Path(temp), "key")
            self.assertEqual(result["assets"][0]["http_status"], 302)
            self.assertEqual(result["assets"][0]["status"], "download_rejected")


class TestOfflineBaseline(unittest.TestCase):
    def test_offline_run_preserves_assets_and_never_marks_crop_ready(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            scene = root / "KK-test"
            scene.mkdir()
            assets = {
                "points.json": json.dumps([{"device": 1, "room": 0, "group": 1}, {"device": 2, "room": 0, "group": 1}]).encode(),
                "timeline.json": json.dumps({"start_point": 1, "spread_events": [{"time": 0, "point": 1}, {"time": 10, "point": 2}]}).encode(),
                "mesh.obj": b"o room\nv -1 0 2\nv 3 4 5\nf 1 2 1\n",
                "output.mp4": b"old video", "render_status.json": b'{"status":"done"}',
            }
            for filename, content in assets.items():
                (scene / filename).write_bytes(content)
            argv = ["probe", "--scene", "KK-test", "--data-root", str(root), "--offline"]
            with patch.object(sys, "argv", argv), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(probe.main(), 0)
            for filename, content in assets.items():
                self.assertEqual((scene / filename).read_bytes(), content)
            reports = list(scene.glob("diagnostics/floorplan/*/report.json"))
            self.assertEqual(len(reports), 1)
            report = json.loads(reports[0].read_text(encoding="utf-8"))
            self.assertFalse(report["floorplan_ready_for_crop"])
            self.assertEqual(report["local_baseline"]["points"]["room_counts"], {"0": 2})
            self.assertEqual(report["local_baseline"]["timeline"]["legacy_frame_count_at_24fps"], 313)
            self.assertEqual(report["local_baseline"]["mesh"]["raw_xyz_bounds"]["max"], [3, 4, 5])

    def test_missing_appkey_produces_report_without_network(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "KK-test").mkdir()
            with patch.object(sys, "argv", ["probe", "--scene", "KK-test", "--data-root", str(root)]), patch.dict("os.environ", {}, clear=True), patch.object(probe, "probe_api") as api, contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(probe.main(), 1)
            api.assert_not_called()


if __name__ == "__main__":
    unittest.main()
