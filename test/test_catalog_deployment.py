"""PRD 2.1 / architecture 2.3,3.1: catalog download isolation and app-role check.

Offline synthetic tests; temporary directories and mocked connections only.
Run locally: python -m unittest test.test_catalog_deployment -v
"""
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from app import check_catalog, s3_io


class CatalogIsolation(unittest.TestCase):
    def test_old_share_does_not_connect_to_failed_database(self) -> None:
        from app import main
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / 'output.mp4'
            output.write_bytes(b'synthetic video')
            with patch('app.database.connect', side_effect=RuntimeError('database offline')) as database, \
                 patch.object(main, 'read_render_status', return_value=None), \
                 patch.object(main, 'verify_output', return_value=output), \
                 patch.object(main, 'ensure_share_output', return_value='test/output.mp4'), \
                 patch.object(main, 'get_share_url', return_value='http://synthetic.test/video'), \
                 patch.object(main, 'write_event'):
                self.assertEqual(main.read_root()['status'], 'Backend is running!')
                self.assertEqual(main.get_render_share('test')['expires_in_seconds'], 604800)
            database.assert_not_called()

    def test_catalog_versions_never_replace_missing_active_assets(self) -> None:
        client = MagicMock()
        client.list_objects.return_value = [SimpleNamespace(object_name=name) for name in (
            'test/catalog/old/points.json', 'test/catalog/new/timeline.json',
            'test/history/22.jpg', 'test/points.json', 'test/22.jpg')]
        with tempfile.TemporaryDirectory() as folder, patch.object(s3_io, 'get_minio_client', return_value=client):
            result = s3_io.download_scene_assets('test', Path(folder))
        self.assertEqual(result['pulled'], 2)
        self.assertEqual([c.args[1] for c in client.fget_object.call_args_list], ['test/points.json', 'test/22.jpg'])

    def test_existing_active_file_is_not_overwritten(self) -> None:
        client = MagicMock()
        client.list_objects.return_value = [SimpleNamespace(object_name='test/points.json')]
        with tempfile.TemporaryDirectory() as folder, patch.object(s3_io, 'get_minio_client', return_value=client):
            path = Path(folder) / 'points.json'
            path.write_text('original', encoding='utf-8')
            s3_io.download_scene_assets('test', Path(folder))
            self.assertEqual(path.read_text(encoding='utf-8'), 'original')
        client.fget_object.assert_not_called()


class ApplicationRoleCheck(unittest.TestCase):
    def connection(self, superuser: bool = False) -> MagicMock:
        conn = MagicMock()
        conn.execute.return_value.fetchone.side_effect = [
            {'name': 'app_test', 'rolsuper': superuser, 'rolcreatedb': False, 'rolcreaterole': False},
            *[{'allowed': True}] * 8,
        ]
        return conn

    def test_uses_application_connection_without_writes(self) -> None:
        conn = self.connection()
        with patch.object(check_catalog, 'connect', return_value=nullcontext(conn)) as connect:
            self.assertEqual(check_catalog.check_catalog()['tables_checked'], 8)
        connect.assert_called_once_with()
        self.assertTrue(all(c.args[0].startswith('SELECT') for c in conn.execute.call_args_list))

    def test_superuser_is_rejected(self) -> None:
        with patch.object(check_catalog, 'connect', return_value=nullcontext(self.connection(True))):
            with self.assertRaises(ValueError):
                check_catalog.check_catalog()

    def test_missing_permission_is_rejected(self) -> None:
        conn = self.connection()
        conn.execute.return_value.fetchone.side_effect = [
            {'name': 'app_test', 'rolsuper': False, 'rolcreatedb': False, 'rolcreaterole': False}, {'allowed': False}]
        with patch.object(check_catalog, 'connect', return_value=nullcontext(conn)), self.assertRaises(ValueError):
            check_catalog.check_catalog()
