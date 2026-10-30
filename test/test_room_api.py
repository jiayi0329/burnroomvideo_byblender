"""HTTP behavior without connecting a database or starting a service."""
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import room_api


class RoomAPI(unittest.TestCase):
    def setUp(self) -> None:
        app = FastAPI()
        app.include_router(room_api.router)
        self.client = TestClient(app)

    def test_database_failure_has_no_credentials(self) -> None:
        with patch.object(room_api, 'connect', side_effect=RuntimeError('secret password')):
            response = self.client.get('/api/catalog/scenes/test/rooms')
        self.assertEqual(response.status_code, 503)
        self.assertNotIn('secret', response.text)

    def test_missing_layout_404(self) -> None:
        with patch.object(room_api, 'query', return_value=[]):
            response = self.client.get('/api/catalog/scenes/test/rooms')
        self.assertEqual(response.status_code, 404)

    def test_version_and_counts_returned(self) -> None:
        with patch.object(room_api, 'query', side_effect=[
            [{'id': 8, 'xy_verified': True}], [{'id': 12, 'interior_points': 13, 'doorway_points': 1, 'associated_points': 14}]
        ]) as query:
            response = self.client.get('/api/catalog/scenes/test/rooms?layout_version_id=8')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['rooms'][0]['associated_points'], 14)
        self.assertEqual(query.call_args_list[0].args[1], ('test', 8, 8))

    def test_pagination_and_version_validated(self) -> None:
        for path in ('/rooms/1/assets?limit=501', '/rooms/1/assets?offset=-1', '/scenes/test/rooms?layout_version_id=0'):
            self.assertEqual(self.client.get('/api/catalog' + path).status_code, 422)

    def test_local_asset_not_given_fake_url(self) -> None:
        with patch.object(room_api, 'query', return_value=[{'bucket': None, 'object_key': None}]):
            response = self.client.get('/api/catalog/assets/1/share')
        self.assertEqual(response.status_code, 409)

    def test_uploaded_asset_signs_offline(self) -> None:
        from urllib.parse import urlsplit, parse_qs
        with patch.object(room_api, 'query', return_value=[{'bucket': 'test-bucket', 'object_key': 'test/image.jpg'}]), patch.dict('os.environ', {
            'MINIO_PUBLIC_ENDPOINT': 'http://127.0.0.1:19000', 'MINIO_ROOT_USER': 'test', 'MINIO_ROOT_PASSWORD': 'synthetic-password'
        }):
            response = self.client.get('/api/catalog/assets/1/share')
        self.assertEqual(response.status_code, 200)
        parsed = urlsplit(response.json()['url'])
        self.assertEqual(parsed.netloc, '127.0.0.1:19000')
        self.assertEqual(parse_qs(parsed.query)['X-Amz-Expires'], ['604800'])


if __name__ == '__main__':
    unittest.main()
