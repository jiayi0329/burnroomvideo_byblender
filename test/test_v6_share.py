"""V6 回归：离线签名、旧成片复用、缓存与流水线；不启动 Blender。"""
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlsplit

from fastapi.testclient import TestClient
from minio.error import S3Error

from app import main, observability, s3_io


def s3_error(code: str) -> S3Error:
    return S3Error(code, "test error", "resource", "request", "host", None)


class TestPresignedShare(unittest.TestCase):
    def test_real_sdk_signs_public_host_offline(self) -> None:
        env = {
            "MINIO_PUBLIC_ENDPOINT": "https://video.example.test:9443/",
            "MINIO_ROOT_USER": "test-user",
            "MINIO_ROOT_PASSWORD": "test-only-secret",
        }
        with patch.dict("os.environ", env, clear=True), patch.object(
            s3_io.Minio, "_url_open", side_effect=AssertionError("network forbidden")
        ):
            url = s3_io.get_share_url("KK-test")
        parsed = urlsplit(url)
        query = parse_qs(parsed.query)
        self.assertEqual(parsed.netloc, "video.example.test:9443")
        self.assertEqual(parsed.scheme, "https")
        self.assertEqual(parsed.path, "/burnroom-outputs/KK-test/output.mp4")
        self.assertEqual(query["X-Amz-Expires"], ["604800"])
        self.assertEqual(query["X-Amz-SignedHeaders"], ["host"])
        self.assertEqual(query["response-content-type"], ["video/mp4"])
        self.assertIn("inline", query["response-content-disposition"][0])
        self.assertIn("X-Amz-Signature", query)
        self.assertNotIn("test-only-secret", url)

    def test_invalid_endpoints_rejected(self) -> None:
        for endpoint in ("host:9000", "http://host/path", "http://user:pass@host", "http://host?x=1"):
            with self.subTest(endpoint=endpoint), patch.dict(
                "os.environ", {"MINIO_PUBLIC_ENDPOINT": endpoint}
            ), self.assertRaises(ValueError):
                s3_io.get_share_url("KK-test")

    def test_missing_credentials_rejected(self) -> None:
        with patch.dict("os.environ", {}, clear=True), self.assertRaises(ValueError):
            s3_io.get_share_url("KK-test")


class TestExistingOutput(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.output = Path(self.temp.name) / "output.mp4"
        self.output.write_bytes(b"existing-video")

    def test_existing_video_is_not_uploaded_again(self) -> None:
        client = Mock()
        client.stat_object.return_value = SimpleNamespace(size=14, content_type="video/mp4")
        with patch.object(s3_io, "get_minio_client", return_value=client), patch.object(s3_io, "upload_output") as upload:
            self.assertEqual(s3_io.ensure_share_output("KK-test", self.output), "KK-test/output.mp4")
        upload.assert_not_called()

    def test_missing_or_outdated_object_is_uploaded(self) -> None:
        for result in (s3_error("NoSuchKey"), s3_error("NoSuchBucket"), SimpleNamespace(size=1, content_type="video/mp4"), SimpleNamespace(size=14, content_type="application/octet-stream")):
            client = Mock()
            if isinstance(result, Exception):
                client.stat_object.side_effect = result
            else:
                client.stat_object.return_value = result
            with self.subTest(result=result), patch.object(s3_io, "get_minio_client", return_value=client), patch.object(s3_io, "upload_output", return_value="KK-test/output.mp4") as upload:
                s3_io.ensure_share_output("KK-test", self.output)
                upload.assert_called_once_with("KK-test", self.output)

    def test_access_denied_is_not_treated_as_missing(self) -> None:
        client = Mock()
        client.stat_object.side_effect = s3_error("AccessDenied")
        with patch.object(s3_io, "get_minio_client", return_value=client), patch.object(s3_io, "upload_output") as upload, self.assertRaises(S3Error):
            s3_io.ensure_share_output("KK-test", self.output)
        upload.assert_not_called()

    def test_upload_has_video_content_type(self) -> None:
        client = Mock()
        with patch.object(s3_io, "get_minio_client", return_value=client), patch.object(s3_io, "ensure_buckets"):
            s3_io.upload_output("KK-test", self.output)
        client.fput_object.assert_called_once_with("burnroom-outputs", "KK-test/output.mp4", str(self.output), content_type="video/mp4")


class TestShareAPI(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.scene = self.root / "KK-test"
        self.scene.mkdir()
        self.output = self.scene / "output.mp4"
        self.output.write_bytes(b"existing-video")
        patcher = patch.object(main, "DATA_ROOT", self.root)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.client = TestClient(main.app)

    def test_share_reuses_video_and_redacts_log(self) -> None:
        signed = "http://host/video?X-Amz-Signature=private-token"
        with patch.object(main, "ensure_share_output", return_value="KK-test/output.mp4") as ensure, patch.object(main, "get_share_url", return_value=signed), patch.object(main.subprocess, "Popen") as process:
            response = self.client.get("/api/render/KK-test/share")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["url"], signed)
        self.assertEqual(response.json()["expires_in_seconds"], 604800)
        ensure.assert_called_once_with("KK-test", self.output)
        process.assert_not_called()
        self.assertEqual(self.output.read_bytes(), b"existing-video")
        log = (self.scene / "logs" / "lifecycle.jsonl").read_text(encoding="utf-8")
        self.assertIn("share_url_created", log)
        self.assertNotIn("private-token", log)

    def test_missing_video_returns_404(self) -> None:
        self.output.unlink()
        with patch.object(main, "ensure_share_output") as ensure:
            self.assertEqual(self.client.get("/api/render/KK-test/share").status_code, 404)
        ensure.assert_not_called()

    def test_running_render_returns_409(self) -> None:
        (self.scene / "render_status.json").write_text('{"status":"running"}', encoding="utf-8")
        with patch.object(main, "ensure_share_output") as ensure:
            self.assertEqual(self.client.get("/api/render/KK-test/share").status_code, 409)
        ensure.assert_not_called()

    def test_storage_failure_is_redacted(self) -> None:
        with patch.object(main, "ensure_share_output", side_effect=RuntimeError("secret-token")):
            response = self.client.get("/api/render/KK-test/share")
        self.assertEqual(response.status_code, 502)
        self.assertNotIn("secret-token", response.text)
        self.assertNotIn("secret-token", (self.scene / "logs" / "lifecycle.jsonl").read_text(encoding="utf-8"))


class TestV6CacheAndPipeline(unittest.TestCase):
    def test_quality_forwarded_and_existing_timeline_reused(self) -> None:
        for quality in ("preview", "final"):
            with self.subTest(quality=quality), tempfile.TemporaryDirectory() as temp:
                scene = Path(temp) / "KK-test"
                scene.mkdir()
                timeline = scene / "timeline.json"
                timeline.write_text("{}", encoding="utf-8")
                with patch.object(main, "DATA_ROOT", Path(temp)), patch.object(
                    main, "download_scene_files", return_value={"status": "cached"}
                ), patch.object(main, "generate_timeline") as generate, patch.object(
                    main, "start_render", return_value={"status": "running"}
                ) as render:
                    result = main.run_pipeline("KK-test", quality)
                render.assert_called_once_with("KK-test", quality)
                generate.assert_not_called()
                self.assertEqual(result["status"], "running")
                self.assertEqual(timeline.read_text(encoding="utf-8"), "{}")

    def test_cache_requires_nonempty_panoramas(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            scene = Path(temp)
            (scene / "mesh.obj").write_bytes(b"mesh")
            (scene / "points.json").write_text(json.dumps([{"device": 22}]), encoding="utf-8")
            self.assertFalse(main.scene_assets_cached(scene))
            (scene / "22.jpg").write_bytes(b"")
            self.assertFalse(main.scene_assets_cached(scene))
            (scene / "22.jpg").write_bytes(b"pano")
            self.assertTrue(main.scene_assets_cached(scene))
            (scene / "points.json").write_text("invalid", encoding="utf-8")
            self.assertFalse(main.scene_assets_cached(scene))

    def test_invalid_quality_has_no_download_or_render_side_effect(self) -> None:
        with patch.object(main, "download_scene_files") as download, patch.object(main, "start_render") as render:
            response = TestClient(main.app).post("/api/pipeline/KK-test?quality=invalid")
        self.assertEqual(response.status_code, 400)
        download.assert_not_called()
        render.assert_not_called()


class TestV6GPUProtection(unittest.TestCase):
    def test_warning_and_shutdown_thresholds_without_gpu(self) -> None:
        for temperature, terminated in ((84.0, False), (85.0, False), (90.0, True)):
            with self.subTest(temperature=temperature), tempfile.TemporaryDirectory() as temp:
                scene = Path(temp)
                running = Mock(side_effect=[True, False])
                abort = Mock()
                with patch.object(observability, "sample_gpu_metrics", return_value=temperature), patch.object(
                    observability.threading, "Event"
                ), patch.object(observability.threading, "Thread") as thread:
                    observability.start_gpu_sampler(scene, running, abort)
                    # 同步执行线程目标，避免真实等待、GPU 调用或后台线程。
                    thread.call_args.kwargs["target"]()
                self.assertEqual(abort.called, terminated)
                if temperature >= 85:
                    self.assertIn("[gpu/告警]", (scene / "logs" / "render.log").read_text(encoding="utf-8"))
                if terminated:
                    abort.assert_called_once_with(90.0)
                    self.assertIn("gpu_overheat_abort", (scene / "logs" / "lifecycle.jsonl").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
