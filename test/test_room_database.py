"""Synthetic import validation and opt-in PostgreSQL integration (remote only)."""
import contextlib
import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from app import analyze_floorplan as align
from app import import_rooms


class ImportValidation(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.scene = Path(self.temp.name) / 'scene-test'
        self.probe = self.scene / 'diagnostics' / 'floorplan'
        self.probe.mkdir(parents=True)
        floor = {'unit': 'm', 'floors': [{'id': 0, 'points': {
            'a': {'x': 0, 'y': 0}, 'b': {'x': 3, 'y': 0}, 'c': {'x': 3, 'y': 3}, 'd': {'x': 0, 'y': 3}},
            'rooms': [{'roomId': 'R', 'tagName': 'room', 'wallPointIDs': ['a','b','c','d'], 'area': 9}]}]}
        (self.probe / 'floor.json').write_text(json.dumps(floor), encoding='utf-8')
        points = [{'device': d, 'pose': {'translation': {'x': x, 'y': 1, 'z': 1.5}}} for d,x in ((22,1),(32,0.02),(42,4))]
        (self.scene / 'points.json').write_text(json.dumps(points), encoding='utf-8')
        mesh = self.scene / 'mesh.obj'
        mesh.write_text('v 0 0 0\nv 3 0 0\nv 3 3 2\nv 0 3 2\nf 1 2 3\n', encoding='utf-8')
        (self.scene / 'timeline.json').write_text(json.dumps({'start_point': 22, 'spread_events': [{'point': 22}]}), encoding='utf-8')
        (self.probe / 'report.json').write_text(json.dumps({'scene_code': self.scene.name, 'status': 'inspected',
            'local_baseline': {'points': {'count': 3}, 'mesh': {'bytes': mesh.stat().st_size}},
            'api': {'assets': [{'json_documents': [{'name': 'floorplan.json', 'status': 'inspected', 'saved_as': 'floor.json'}]}]}}), encoding='utf-8')
        report, chart = align.analyze(self.scene, self.probe, transform_id='xy')
        self.output = self.scene / 'diagnostics' / 'alignment'
        align.write_outputs(self.output, report, chart)
        self.review_path = self.output / 'review.json'
        self.review = {'scene_code': self.scene.name, 'alignment_report_sha256': align.sha256(self.output / 'alignment_report.json'),
            'reviewed_by': 'test reviewer', 'reviewed_at': '2026-10-30T00:00:00+00:00', 'notes': 'synthetic verification', 'xy_verified': True,
            'points': {'22': {'kind': 'interior', 'room_id': 'R'}, '32': {'kind': 'doorway', 'room_id': 'R'}, '42': {'kind': 'outside', 'room_id': None}}}
        self.write_review()

    def write_review(self) -> None:
        self.review_path.write_text(json.dumps(self.review), encoding='utf-8')

    def plan(self) -> dict:
        return import_rooms.build_plan(self.scene, self.probe, self.output, self.review_path)

    def test_preview_has_no_db_or_upload_and_stable_identity(self) -> None:
        with patch('app.database.connect', side_effect=AssertionError('no database')):
            first = self.plan()
            self.assertEqual(first['fingerprint'], self.plan()['fingerprint'])
            self.assertTrue(first['review']['xy_verified'])
            self.assertEqual(first['report']['memberships_provisional'][1]['status'], 'boundary')

    def test_changed_source_rejected(self) -> None:
        (self.scene / 'mesh.obj').write_text('v 1 2 3\n', encoding='utf-8')
        with self.assertRaises(ValueError):
            self.plan()

    def test_tampered_report_rejected(self) -> None:
        path = self.output / 'alignment_report.json'
        report = json.loads(path.read_text(encoding='utf-8'))
        report['memberships_provisional'][0]['room_id'] = 'unknown'
        path.write_text(json.dumps(report), encoding='utf-8')
        with self.assertRaises(ValueError):
            self.plan()

    def test_review_rejects_wrong_binding_and_invalid_room(self) -> None:
        original = copy.deepcopy(self.review)
        for change in ({'scene_code': 'other'}, {'alignment_report_sha256': 'wrong'},
                       {'points': {'22': {'kind': 'interior', 'room_id': 'missing'}}},
                       {'points': {'42': {'kind': 'outside', 'room_id': 'R'}}}):
            self.review = {**original, **change}
            self.write_review()
            with self.assertRaises(ValueError):
                self.plan()

    def test_new_review_creates_new_version_identity(self) -> None:
        original = self.plan()['fingerprint']
        self.review['notes'] = 'additional checked evidence'
        self.write_review()
        self.assertNotEqual(original, self.plan()['fingerprint'])


@unittest.skipUnless(os.getenv('ROOM_DB_INTEGRATION') == '1', 'Remote PostgreSQL integration opt-in')
class PostgreSQLIntegration(unittest.TestCase):
    setUp = ImportValidation.setUp
    write_review = ImportValidation.write_review
    plan = ImportValidation.plan

    def test_transaction_import_idempotence_and_constraints(self) -> None:
        from app.database import connect
        from psycopg import sql, errors
        import uuid
        schema = 'test_rooms_' + uuid.uuid4().hex
        with connect(admin=True) as conn:
            with conn.transaction(force_rollback=True):
                conn.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
                conn.execute(sql.SQL('SET LOCAL search_path TO {}').format(sql.Identifier(schema)))
                conn.execute((Path(__file__).resolve().parents[1] / 'app/db/001_rooms.sql').read_text(encoding='utf-8'))
                with patch('app.database.connect', side_effect=lambda: contextlib.nullcontext(conn)):
                    first = import_rooms.import_plan(self.plan())
                    conn.execute("UPDATE rooms SET name='reviewed name'")
                    second = import_rooms.import_plan(self.plan())
                    self.assertFalse(first['reused'])
                    self.assertTrue(second['reused'])
                    self.assertEqual(first['layout_version_id'], second['layout_version_id'])
                    self.assertEqual(conn.execute('SELECT name FROM rooms LIMIT 1').fetchone()['name'], 'reviewed name')
                self.assertEqual(conn.execute('SELECT count(*) AS n FROM point_room_memberships').fetchone()['n'], 3)
                from app import room_api
                with patch.object(room_api, 'connect', side_effect=lambda: contextlib.nullcontext(conn)):
                    rooms = room_api.list_rooms(self.scene.name, None, False)['rooms']
                    self.assertEqual(rooms[0]['interior_points'], 1)
                    self.assertEqual(rooms[0]['doorway_points'], 1)
                    self.assertEqual(rooms[0]['associated_points'], 2)
                    self.assertEqual(len(room_api.list_points(rooms[0]['id'])['points']), 2)
                other = conn.execute("INSERT INTO scenes(scene_code,name) VALUES ('other','other') RETURNING id").fetchone()['id']
                point = conn.execute('SELECT id FROM points LIMIT 1').fetchone()['id']
                with self.assertRaises(errors.ForeignKeyViolation), conn.transaction():
                    conn.execute("INSERT INTO assets(scene_id,point_id,kind,sha256,size_bytes,local_relative_path) VALUES (%s,%s,'test','abc',1,'x')", (other, point))
                # The outer transaction rolls back all test schema/data changes.


if __name__ == '__main__':
    unittest.main()
