"""Synthetic file/ASGI tests only; no remote data, database, renderer or deploy."""
from copy import deepcopy
import json
import math
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.api import main
from backend.services import room_job_service as jobs
from backend.services import room_spatial_context as spatial
from render_engine.jobs.room_animation_job import digest
from tests.backend.test_room_registration import Fixture, DEVICES


class SpatialFixture(Fixture):
    def setUp(self):
        super().setUp()
        root = patch.object(jobs, 'DATA_ROOT', self.root)
        root.start(); self.addCleanup(root.stop)
        self.client = TestClient(main.app)
        self.raw_points = [{'device': d, 'x': (i % 4)+.5, 'y': (i // 4)+.5, 'z': 1.5}
                           for i, d in enumerate(DEVICES)]
        self.raw_points += [{'device': 32, 'x': 4, 'y': 1, 'z': 1.5},
                            {'device': 42, 'x': 10, 'y': 10, 'z': 1.5}]
        self.write(self.scene/'points.json', self.raw_points)
        polygon = [[0, 0], [4, 0], [4, 4], [0, 4]]
        self.manifest.update(raw_to_asset_matrix=deepcopy(spatial.IDENTITY),
            clipping_parameters={'polygon_raw_xy': polygon},
            engineering_policy={'floor_z': -1.35, 'physical_semantics_verified': False},
            glb_coordinate_mapping=spatial.GLB_MAPPING, points=self.raw_points[:-1])
        self.manifest['source_fingerprints']['points.json'] = digest(self.scene/'points.json')
        self.candidate = {'schema_version': 1, 'scene_code': self.scene.name, 'room_id': 'Room8',
            'polygon_raw_xy': polygon, 'floor_z': -1.35, 'physical_semantics_verified': False,
            'raw_to_asset_matrix': deepcopy(spatial.IDENTITY), 'interior_devices': list(DEVICES),
            'boundary_devices': [32], 'ignition_device': 22, 'points': deepcopy(self.raw_points[:-1]),
            'provenance': deepcopy(self.manifest['provenance']),
            'source_fingerprints': deepcopy(self.manifest['source_fingerprints'])}
        self.original = self.spec['inputs']['asset']
        self.spec['inputs']['points'] = '/app/data/'+self.scene.name+'/points.json'
        self.spec['inputs']['timeline']['allowed_devices'] = list(DEVICES)
        self.spec['private_note'] = 'secret-password Authorization https://private/?signature=secret'
        self.bind()

    def bind(self, write_candidate=True):
        if write_candidate:
            self.write(self.asset.parent/'candidate.json', self.candidate)
        self.manifest['candidate_sha256'] = digest(self.asset.parent/'candidate.json')
        self.manifest['artifacts'] = {p.name: digest(p) for p in self.asset.iterdir() if p.name != 'manifest.json'}
        self.write(self.asset/'manifest.json', self.manifest)
        guards = {self.original+'/'+name: digest(self.asset/name)
                  for name in ('manifest.json', 'room.blend', 'room.glb', 'validation.json')}
        guards[self.original.rsplit('/', 1)[0]+'/candidate.json'] = digest(self.asset.parent/'candidate.json')
        guards[self.spec['inputs']['points']] = digest(self.scene/'points.json')
        self.spec['inputs']['guards'] = guards
        self.sign_spec()

    def get(self, job='job-1', **kwargs):
        return self.client.get(f'/api/room-jobs/{job}/spatial-context?scene_code={self.scene.name}', **kwargs)

    def invalid(self):
        response = self.get()
        self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(response.json()['detail']['code'], 'spatial_evidence_invalid')
        self.assertNotIn('secret', response.text)
        return response


class ReadOnlyContext(SpatialFixture):
    def test_verified_response_is_minimal_file_bound_and_database_independent(self):
        before = {p: p.read_bytes() for p in self.scene.rglob('*') if p.is_file()}
        with patch.object(jobs.repository, 'connect', side_effect=AssertionError('DB forbidden')), \
             patch('subprocess.Popen', side_effect=AssertionError('Render forbidden')):
            response = self.get()
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()
        self.assertTrue(result['verified'])
        self.assertEqual(result['verification_scope'], 'file_consistency_only')
        self.assertEqual(result['file_job_id'], 'job-1')
        self.assertEqual(result['ignition']['device'], 22)
        point = next(p for p in self.raw_points if p['device'] == 22)
        self.assertEqual(result['ignition']['position_raw_xyz'], [point[k] for k in ('x', 'y', 'z')])
        self.assertEqual(result['boundary']['polygon_raw_xy'], [[0, 0], [4, 0], [4, 4], [0, 4]])
        self.assertFalse(result['boundary']['physical_semantics_verified'])
        self.assertIsNone(result['layout_version_id'])
        self.assertEqual(result['layout_binding'], 'file_fingerprints_only')
        self.assertEqual(result['source']['candidate_sha256'], self.manifest['candidate_sha256'])
        for text in ('/app/data', str(self.root), 'guards', 'private_note', 'secret', 'signature=', 'Authorization'):
            self.assertNotIn(text, response.text)
        self.assertEqual({p: p.read_bytes() for p in before}, before)

    def test_missing_job_and_missing_file_have_distinct_errors(self):
        self.assertEqual(self.get('missing').status_code, 404)
        (self.asset.parent/'candidate.json').unlink()
        response = self.get()
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()['detail']['code'], 'spatial_evidence_missing')

    def test_historical_source_guards_are_not_replaced_or_opened_with_current_code(self):
        self.spec['inputs']['codes'] = {'historical/app/F8_room_animation.py': 'a'*64}
        self.spec['inputs']['guards']['/historical/app/F8_room_animation.py'] = 'a'*64
        self.sign_spec()
        original = (self.job/'config_snapshot.json').read_bytes()
        self.assertEqual(self.get().status_code, 200)
        self.assertEqual((self.job/'config_snapshot.json').read_bytes(), original)

    def test_snapshot_signature_must_match(self):
        self.spec['inputs']['timeline']['start_point'] = 32
        self.write(self.job/'config_snapshot.json', self.spec)
        self.invalid()

    def test_changed_candidate_or_glb_bytes_are_rejected(self):
        for path in (self.asset.parent/'candidate.json', self.asset/'room.glb'):
            with self.subTest(path=path.name):
                original = path.read_bytes(); path.write_bytes(b'private tampering')
                self.invalid(); path.write_bytes(original)

    def test_wrong_scene_room_and_source_path_are_rejected(self):
        for name, value in (('scene_code', 'other'), ('room_id', 'Room9')):
            original = self.candidate[name]
            self.candidate[name] = value; self.bind(); self.invalid()
            self.candidate[name] = original
        self.bind()
        self.spec['inputs']['points'] = '/private/points.json'
        self.sign_spec(); self.invalid()

    def test_wrong_asset_version_cannot_read_another_folder(self):
        self.spec['inputs']['asset'] = self.original.replace('version-1', 'version-2')
        self.sign_spec(); self.invalid()

    def test_unsupported_coordinate_mapping_and_matrix_are_rejected(self):
        self.manifest['glb_coordinate_mapping'] = 'unknown mapping'
        self.bind(); self.invalid()
        self.manifest['glb_coordinate_mapping'] = spatial.GLB_MAPPING
        self.candidate['raw_to_asset_matrix'][0][3] = 5
        self.bind(); self.invalid()

    def test_review_and_point_source_bindings_cannot_drift(self):
        self.candidate['provenance']['review_sha256'] = 'c'*64
        self.bind(); self.invalid()
        self.candidate['provenance'] = deepcopy(self.manifest['provenance'])
        self.candidate['source_fingerprints']['points.json'] = 'd'*64
        self.bind(); self.invalid()

    def test_nonfinite_duplicate_degenerate_or_crossing_polygon_is_rejected(self):
        rings = ([[0, 0], [4, 0], [float('nan'), 4]],
                 [[0, 0], [0, 0], [4, 4]], [[0, 0], [1, 1], [2, 2]],
                 [[0, 0], [4, 4], [0, 4], [3, 0]],
                 [[False, 0], [4, 0], [4, 4]],
                 [[math.cos(i*2*math.pi/129), math.sin(i*2*math.pi/129)] for i in range(129)])
        for ring in rings:
            with self.subTest(ring=ring):
                self.candidate['polygon_raw_xy'] = ring
                self.manifest['clipping_parameters']['polygon_raw_xy'] = ring
                self.bind(); self.invalid()

    def test_candidate_and_manifest_boundaries_and_floor_must_agree(self):
        self.candidate['polygon_raw_xy'] = [[0, 0], [3, 0], [3, 3], [0, 3]]
        self.bind(); self.invalid()
        self.candidate['polygon_raw_xy'] = deepcopy(self.manifest['clipping_parameters']['polygon_raw_xy'])
        self.candidate['floor_z'] = -3
        self.bind(); self.invalid()

    def test_boundary_point_cannot_be_ignition(self):
        self.candidate['ignition_device'] = 32
        self.spec['inputs']['timeline']['start_point'] = 32
        self.bind(); self.invalid()

    def test_missing_duplicate_and_wrong_members_are_rejected(self):
        original = deepcopy(self.spec['inputs']['timeline'])
        for changes in ({'allowed_devices': list(DEVICES)+[32]},
                        {'allowed_devices': list(DEVICES)+[22]}, {'spread_events': []},
                        {'start_point': True}):
            self.spec['inputs']['timeline'] = {**deepcopy(original), **changes}
            self.sign_spec(); self.invalid()

    def test_anchor_coordinates_must_match_original_points(self):
        self.candidate['points'][0]['x'] = 100
        self.bind(); self.invalid()

    def test_original_pose_translation_format_is_verified_without_changing_files(self):
        nested = [{'device': p['device'], 'pose': {'translation': {k: p[k] for k in ('x', 'y', 'z')}}}
                  for p in self.raw_points]
        self.write(self.scene/'points.json', nested)
        self.manifest['points'] = deepcopy(nested[:-1])
        self.candidate['points'] = deepcopy(nested[:-1])
        value = digest(self.scene/'points.json')
        self.manifest['source_fingerprints']['points.json'] = value
        self.candidate['source_fingerprints']['points.json'] = value
        self.bind()
        response = self.get()
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['ignition']['device'], 22)

    def test_conflicting_flat_and_nested_coordinates_are_rejected(self):
        self.candidate['points'][0]['pose'] = {'translation': {'x': 100, 'y': 100, 'z': 100}}
        self.bind(); self.invalid()

    def test_duplicate_json_keys_are_rejected_even_with_updated_hash(self):
        path = self.asset.parent/'candidate.json'
        path.write_text('{"floor_z":123,'+path.read_text(encoding='utf-8')[1:], encoding='utf-8')
        self.bind(write_candidate=False); self.invalid()

    def test_overflowing_json_exponent_is_rejected_even_in_unused_fields(self):
        path = self.asset.parent/'candidate.json'
        path.write_text('{"unused":1e400,'+path.read_text(encoding='utf-8')[1:], encoding='utf-8')
        self.bind(write_candidate=False); self.invalid()

    def test_evidence_modified_mid_read_is_rejected(self):
        original = spatial.positions
        calls = []

        def change(value):
            result = original(value)
            if not calls:
                (self.asset/'room.glb').write_bytes(b'mutated after initial digest')
            calls.append(True)
            return result

        with patch.object(spatial, 'positions', side_effect=change):
            self.invalid()

    def test_guard_aliases_and_traversal_are_rejected(self):
        key = self.original+'/manifest.json'
        self.spec['inputs']['guards'][key.replace('/', '\\')] = self.spec['inputs']['guards'][key]
        self.sign_spec(); self.invalid()
        self.spec['inputs']['guards'].pop(key.replace('/', '\\'))
        self.spec['inputs']['asset'] = self.original.replace('/rooms/', '/../rooms/')
        self.sign_spec(); self.invalid()

    def test_http_rejects_other_rooms_and_write_methods(self):
        url = f'/api/room-jobs/job-1/spatial-context?scene_code={self.scene.name}'
        self.assertEqual(self.client.get(url+'&room_id=Room9').status_code, 422)
        self.assertEqual(self.client.post(url).status_code, 405)
        self.assertEqual(self.client.get('/api/room-jobs/job-1/spatial-context?scene_code=../escape').status_code, 422)

    def test_success_and_failure_logs_retain_trace_job_stage_and_duration_without_sensitive_data(self):
        response = self.get(headers={'X-Trace-ID': 'spatial-read-test'})
        self.assertEqual(response.status_code, 200, response.text)
        successful = self.events()
        stages = {event.get('stage') for event in successful if event.get('operation') == 'room.spatial'}
        self.assertTrue({'verify_snapshot', 'verify_asset', 'verify_membership', 'recheck_fingerprints'} <= stages)
        events = [event for event in successful if event.get('operation') == 'room.spatial' and event.get('event') == 'success']
        self.assertTrue(events)
        for event in events:
            self.assertEqual((event['trace_id'], event['job_id']), ('spatial-read-test', 'job-1'))
            self.assertGreaterEqual(event['duration_ms'], 0)
            self.assertTrue(event['ts'])
        (self.asset/'room.glb').write_bytes(b'secret-password')
        failed = self.get(headers={'X-Trace-ID': 'spatial-read-failed'})
        self.assertEqual(failed.status_code, 409)
        self.assertTrue(any(e.get('event') == 'failure' and e.get('trace_id') == 'spatial-read-failed' for e in self.events()))
        serialized = json.dumps(self.events())
        for text in ('secret-password', 'Authorization', 'https://private/', 'signature=', str(self.root)):
            self.assertNotIn(text, serialized)


if __name__ == '__main__':
    unittest.main()
