"""PRD asset registration / DATA_ASSET_SPEC / OBSERVABILITY.

Synthetic files, in-memory MinIO and mocked SQL transactions only. No real
DB/MinIO/API/Blender/FFmpeg/Docker or server. No actual media decoding claim.
"""
from contextlib import nullcontext, redirect_stdout
import copy
from dataclasses import replace
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

from minio.error import S3Error

from backend.adapters.minio import room_objects as objects
from backend.adapters.postgres import room_asset_repository as database
from backend.cli import register_room_assets as cli
from backend.services import room_registration as service
from render_engine.jobs import operation_logging as log
from render_engine.jobs.room_animation_job import digest, fingerprint

ROOT = Path(__file__).resolve().parents[2]
DEVICES = (0, 2, 4, 6, 8, 10, 12, 14, 16, 18, 20, 22, 40)


def error(code: str) -> S3Error:
    return S3Error(code, 'synthetic', None, None, None, None)


class MemoryMinio:
    def __init__(self):
        self.buckets = set()
        self.objects = {}
        self.uploads = 0
        self.policy = None
        self.responses = []

    def bucket_exists(self, bucket): return bucket in self.buckets
    def make_bucket(self, bucket): self.buckets.add(bucket)
    def get_bucket_policy(self, bucket):
        if self.policy: return self.policy
        raise error('NoSuchBucketPolicy')
    def stat_object(self, bucket, key):
        if (bucket, key) not in self.objects: raise error('NoSuchKey')
        body, media = self.objects[bucket, key]
        return SimpleNamespace(size=len(body), content_type=media, version_id=None)
    def fput_object(self, bucket, key, filename, *, content_type, metadata):
        self.uploads += 1
        self.objects[bucket, key] = (Path(filename).read_bytes(), content_type)
    def get_object(self, bucket, key, **kwargs):
        response = io.BytesIO(self.objects[bucket, key][0])
        response.release_conn = MagicMock()
        self.responses.append(response)
        return response


class Fixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.scene = self.root/'synthetic-scene'
        self.asset = self.scene/'rooms/Room8/version-1/asset'
        self.job = self.scene/'rooms/Room8/render_jobs/job-1'
        self.asset.mkdir(parents=True); self.job.mkdir(parents=True)
        self.logs = self.root/'logs'
        environment = patch.dict(os.environ, {'OPERATION_LOG_ROOT': str(self.logs)})
        environment.start(); self.addCleanup(environment.stop)
        for name in ('mesh.obj', 'points.json', 'timeline.json'):
            (self.scene/name).write_bytes(b'synthetic-source')
        (self.asset.parent/'candidate.json').write_text('{}', encoding='utf-8')
        for name in ('room.blend', 'room.glb', 'top.png', 'oblique.png', 'interior.png'):
            (self.asset/name).write_bytes(('synthetic '+name).encode())
        self.write(self.asset/'validation.json', {'status': 'passed', 'checks': {'synthetic': True},
                                                'ready_for_fire_effects': False})
        self.review = {'xy_verified': True, 'alignment_report_sha256': 'a'*64}
        self.manifest = {'scene_code': self.scene.name, 'room_id': 'Room8',
            'candidate_sha256': digest(self.asset.parent/'candidate.json'),
            'interior_devices': list(DEVICES), 'boundary_devices': [32],
            'provenance': {'alignment_sha256': 'a'*64, 'review_sha256': 'b'*64},
            'source_fingerprints': {name: digest(self.scene/name) for name in ('mesh.obj', 'points.json', 'timeline.json')},
            'artifacts': {p.name: digest(p) for p in self.asset.iterdir()}}
        self.write(self.asset/'manifest.json', self.manifest)
        self.timeline = {'start_point': 22, 'spread_events': [{'point': d, 'time': 0 if d == 22 else 1.5} for d in DEVICES]}
        self.spec = {'schema_version': 1, 'inputs': {
            'asset': '/app/data/synthetic-scene/rooms/Room8/version-1/asset',
            'style': json.loads((ROOT/'configs/render/room_fire_round3.json').read_text(encoding='utf-8')),
            'guards': {'/app/data/synthetic-scene/'+p.relative_to(self.scene).as_posix(): digest(p)
                       for p in (self.asset/'manifest.json', self.asset/'room.blend', self.asset/'room.glb', self.asset.parent/'candidate.json')},
            'timeline': self.timeline},
            'animation': {'stage': 'final', 'preset': 'final', 'camera_mode': 'overview',
                          'duration_seconds': 24, 'fps': 24, 'resolution': [1280, 720], 'frame_count': 576}}
        self.sign_spec()
        (self.job/'fire_final.mp4').write_bytes(b'synthetic-video')
        self.video = {'file': 'fire_final.mp4', 'sha256': digest(self.job/'fire_final.mp4'),
                      'bytes': (self.job/'fire_final.mp4').stat().st_size,
                      'duration_seconds': 24, 'frames': 576, 'resolution': [1280, 720],
                      'fps': '24/1', 'codec': 'h264', 'pixel_format': 'yuv420p', 'full_decode_passed': True}
        self.render = {'signature': self.spec['signature'], 'technical_complete': True,
                       'worker_complete': True, 'guarded_files_unchanged': True, 'camera_mode': 'overview',
                       'timeline': self.timeline, 'frames': [{}]*576, 'video': self.video}
        self.write(self.job/'render_manifest.json', self.render)
        self.write(self.job/'video_receipt.json', self.video)
        self.write(self.job/'status.json', {'state': 'awaiting_visual_review'})

    @staticmethod
    def write(path, value): path.write_text(json.dumps(value), encoding='utf-8')
    def sign_spec(self):
        self.spec.pop('signature', None)
        self.spec['signature'] = fingerprint(self.spec)
        self.write(self.job/'config_snapshot.json', self.spec)
    def plan(self): return service.build_plan(self.root, self.scene.name, self.asset, self.job, 1)
    def events(self):
        return [json.loads(line) for p in self.logs.glob('*.jsonl') for line in p.read_text().splitlines()]
    def argv(self, *extra):
        return ['register', '--data-root', str(self.root), '--scene', self.scene.name,
                '--asset', str(self.asset), '--job', str(self.job), '--layout-version-id', '1', *extra]


class LocalPlan(Fixture):
    def test_preview_is_file_only_and_keeps_historical_review_state(self):
        before = {p: p.read_bytes() for p in self.scene.rglob('*') if p.is_file()}
        with patch.object(database, 'connect', side_effect=AssertionError('DB forbidden')), \
             patch('backend.adapters.minio.s3_io.get_minio_client', side_effect=AssertionError('network forbidden')):
            plan = self.plan()
        self.assertEqual(len(plan.files), 6)
        self.assertEqual(plan.summary()['human_acceptance'], 'not_recorded')
        self.assertEqual({p: p.read_bytes() for p in before}, before)
        self.assertNotIn('config_snapshot.json', [f.path.name for f in plan.files])

    def test_explicit_scene_asset_and_job_versions_are_required(self):
        for scene, asset, job, version in [('../escape', self.asset, self.job, 1),
                 (self.scene.name, self.job, self.asset, 1), (self.scene.name, self.asset, self.job, 0)]:
            with self.assertRaises((ValueError, FileNotFoundError)):
                service.build_plan(self.root, scene, asset, job, version)

    def test_changed_geometry_and_video_bytes_are_rejected(self):
        for path in (self.asset/'room.blend', self.job/'fire_final.mp4'):
            original = path.read_bytes(); path.write_bytes(b'tampered')
            with self.assertRaises(ValueError): self.plan()
            path.write_bytes(original)

    def test_nonterminal_or_unverified_video_is_rejected(self):
        self.write(self.job/'status.json', {'state': 'rendering'})
        with self.assertRaises(ValueError): self.plan()
        self.write(self.job/'status.json', {'state': 'awaiting_visual_review'})
        self.video['full_decode_passed'] = False
        self.write(self.job/'video_receipt.json', self.video)
        with self.assertRaises(ValueError): self.plan()

    def test_different_asset_snapshot_or_style_is_rejected(self):
        self.spec['inputs']['asset'] = '/other/rooms/Room8/version-2/asset'
        self.sign_spec()
        with self.assertRaises(ValueError): self.plan()
        self.spec['inputs']['asset'] = '/app/data/synthetic-scene/rooms/Room8/version-1/asset'
        self.spec['inputs']['style']['art']['exposure'] = 10
        self.sign_spec()
        with self.assertRaises(ValueError): self.plan()

    def test_boundary_points_cannot_enter_propagation(self):
        self.render['timeline'] = copy.deepcopy(self.timeline)
        self.render['timeline']['spread_events'][0]['point'] = 32
        self.write(self.job/'render_manifest.json', self.render)
        with self.assertRaises(ValueError): self.plan()

    def test_absolute_artifact_path_and_symlink_escape_rejected(self):
        self.manifest['artifacts']['../outside'] = 'a'*64
        self.write(self.asset/'manifest.json', self.manifest)
        with self.assertRaises(ValueError): self.plan()
        outside = self.root/'outside'; outside.write_text('synthetic')
        with self.assertRaises(ValueError): service.inside(self.scene, outside)

    def test_guard_detects_change_after_preview(self):
        plan = self.plan()
        (self.job/'status.json').write_text('{}')
        with self.assertRaises(ValueError): service.verify_unchanged(plan)


class ObjectStorage(Fixture):
    def test_readback_failure_closes_and_releases_response(self):
        file = self.plan().files[0]; client = MagicMock()
        client.stat_object.return_value = SimpleNamespace(size=file.size, content_type=file.content_type, version_id=None)
        response = client.get_object.return_value
        response.read.side_effect = OSError('synthetic disconnect')
        with self.assertRaises(OSError): objects.verify_object(client, file)
        response.close.assert_called_once()
        response.release_conn.assert_called_once()

    def test_upload_readback_and_retry_reuses_object(self):
        client = MemoryMinio(); file = self.plan().files[0]
        objects.private_bucket(client, file.bucket)
        self.assertFalse(objects.ensure_object(client, file)['reused_object'])
        self.assertTrue(objects.ensure_object(client, file)['reused_object'])
        self.assertEqual(client.uploads, 1)
        self.assertTrue(all(r.closed and r.release_conn.called for r in client.responses))

    def test_same_size_wrong_bytes_and_wrong_media_are_never_overwritten(self):
        file = self.plan().files[0]
        for body, media in ((b'x'*file.size, file.content_type), (file.path.read_bytes(), 'wrong/type')):
            client = MemoryMinio(); client.objects[file.bucket, file.key] = (body, media)
            with self.assertRaises(ValueError): objects.ensure_object(client, file)
            self.assertEqual(client.uploads, 0)
            self.assertEqual(client.objects[file.bucket, file.key], (body, media))

    def test_policy_rejection_never_changes_legacy_buckets(self):
        client = MemoryMinio(); client.policy = '{"Statement":[{"Effect":"Allow"}]}'
        with self.assertRaises(ValueError): objects.private_bucket(client, 'burnroom-room-assets')
        with self.assertRaises(ValueError): objects.private_bucket(client, 'burnroom-outputs')
        self.assertNotIn('burnroom-outputs', client.buckets)

    def test_permission_error_does_not_become_missing_object(self):
        client = MemoryMinio(); client.stat_object = MagicMock(side_effect=error('AccessDenied'))
        with self.assertRaises(S3Error): objects.ensure_object(client, self.plan().files[0])
        self.assertEqual(client.uploads, 0)


class PublicationCLI(Fixture):
    def test_default_preview_and_help_do_not_call_services(self):
        with patch.object(cli, 'apply', side_effect=AssertionError('unexpected apply')), \
             patch.object(sys, 'argv', self.argv()), redirect_stdout(io.StringIO()) as output:
            self.assertEqual(cli.main(), 0)
        self.assertEqual(json.loads(output.getvalue())['mode'], 'preview')
        self.assertFalse((self.scene/'rooms/Room8/registrations').exists())
        with patch.object(sys, 'argv', ['register', '--help']), redirect_stdout(io.StringIO()):
            with self.assertRaises(SystemExit) as raised: cli.main()
        self.assertEqual(raised.exception.code, 0)

    def test_lock_rejects_concurrent_run_and_does_not_clear_other_lock(self):
        root = self.root/'locks'
        with cli.registration_lock(root):
            original = (root/'registration.lock').read_bytes()
            with self.assertRaises(FileExistsError):
                with cli.registration_lock(root): pass
            self.assertEqual((root/'registration.lock').read_bytes(), original)
        self.assertFalse((root/'registration.lock').exists())

    def test_database_failure_preserves_uploaded_objects_and_retry_needs_no_upload(self):
        plan = self.plan(); client = MemoryMinio()
        with patch.object(database, 'preflight'), patch('backend.adapters.minio.s3_io.get_minio_client', return_value=client), \
             patch.object(database, 'register', side_effect=RuntimeError('PRIVATE-SIGNATURE-DO-NOT-LOG')):
            with self.assertRaises(RuntimeError): cli.apply(plan)
        receipt_path = next((self.scene/'rooms/Room8/registrations').glob('*/registration_receipt.json'))
        receipt = json.loads(receipt_path.read_text())
        self.assertEqual(receipt['upload_status'], 'verified')
        self.assertEqual(receipt['registration_status'], 'not_registered')
        self.assertNotIn('PRIVATE-SIGNATURE', receipt_path.read_text())
        self.assertEqual(client.uploads, 6)
        result = {'database_job_id': 5, 'database_room_id': 6, 'reused_job': False, 'registration_status': 'registered'}
        with patch.object(database, 'preflight'), patch('backend.adapters.minio.s3_io.get_minio_client', return_value=client), \
             patch.object(database, 'register', return_value=result):
            self.assertEqual(cli.apply(plan)['registration_status'], 'registered')
        self.assertEqual(client.uploads, 6)
        self.assertEqual(len(list(receipt_path.parent.parent.glob('*/registration_receipt.json'))), 2)

    def test_database_preflight_prevents_upload_when_layout_is_wrong(self):
        with patch.object(database, 'preflight', side_effect=ValueError('mismatch')), \
             patch('backend.adapters.minio.s3_io.get_minio_client') as client:
            with self.assertRaises(ValueError): cli.apply(self.plan())
        client.assert_not_called()

    def test_interruption_keeps_receipt_and_releases_own_lock(self):
        with patch.object(database, 'preflight', side_effect=KeyboardInterrupt()):
            with self.assertRaises(KeyboardInterrupt): cli.apply(self.plan())
        root = self.scene/'rooms/Room8/registrations'
        receipt = json.loads(next(root.glob('*/registration_receipt.json')).read_text())
        self.assertEqual(receipt['error_type'], 'KeyboardInterrupt')
        self.assertEqual(receipt['registration_status'], 'not_registered')
        self.assertFalse((root/'registration.lock').exists())

    def test_cli_failure_logs_correlated_stages_and_redacts_raw_errors(self):
        secret = 'SENSITIVE?X-Amz-Signature=private'
        with patch.object(sys, 'argv', self.argv('--apply')), \
             patch.object(database, 'preflight', side_effect=RuntimeError(secret)), \
             redirect_stdout(io.StringIO()) as output:
            self.assertEqual(cli.main(), 1)
        events = self.events()
        self.assertEqual(len({r['trace_id'] for r in events}), 1)
        self.assertTrue(any(r['event'] == 'failure' and 'duration_ms' in r for r in events))
        self.assertTrue(any(r.get('job_id') == 'job-1' for r in events))
        self.assertNotIn(secret, output.getvalue()+json.dumps(events))


class DatabaseRegistration(Fixture):
    def test_checkout_keeps_original_migration_bytes_and_lf_policy(self):
        from backend.paths import BASELINE_MIGRATION_SHA256, migration_files
        self.assertEqual(digest(migration_files()[0]), BASELINE_MIGRATION_SHA256)
        self.assertIn('*.sql text eol=lf', (ROOT/'.gitattributes').read_text(encoding='utf-8'))

    def test_checkout_keeps_exact_approved_preset_bytes(self):
        expected = ('f1f6a552746c999c416bc7da5b36a4ff0f515f596140d6c0d6588f774b41a815',
                    '6e99a2327305a668458bea516d9de87285164ec4c7ba67b0c21f41d5b59ce375',
                    'af9854a21f47e840c837b9299584d4d7d9fd74dfa4fac19251e91873369d4202')
        attributes = (ROOT/'.gitattributes').read_text(encoding='utf-8')
        for revision, sha in enumerate(expected, 1):
            name = f'configs/render/room_fire_round{revision}.json'
            self.assertEqual(hashlib.sha256((ROOT/name).read_bytes()).hexdigest(), sha)
            self.assertIn(f'{name} text eol='+('lf' if revision == 1 else 'crlf'), attributes)

    def binding_fixture(self):
        evidence = self.scene/'diagnostics'
        evidence.mkdir()
        alignment = evidence/'alignment.json'
        self.write(alignment, {'synthetic': True})
        review = {'xy_verified': True, 'alignment_report_sha256': digest(alignment)}
        review_path = evidence/'review.json'
        self.write(review_path, review)
        plan = replace(self.plan(), provenance={'alignment_sha256': digest(alignment), 'review_sha256': digest(review_path)})
        layout = {'scene_id': 1, 'room_id': 6, 'xy_verified': True, 'review': review}
        memberships = [{'device': d, 'kind': 'interior', 'source_room_id': 'Room8'} for d in DEVICES]
        memberships += [{'device': 32, 'kind': 'doorway', 'source_room_id': 'Room8'},
                        {'device': 42, 'kind': 'outside', 'source_room_id': None}]
        conn = MagicMock()

        def execute(sql, params):
            result = MagicMock()
            if sql.startswith('SELECT s.id'):
                result.fetchone.return_value = layout
            elif sql.startswith('SELECT local_relative_path'):
                path = alignment if params[1] == 'alignment_report' else review_path
                result.fetchall.return_value = [{'local_relative_path': path.relative_to(self.scene).as_posix()}]
            elif sql.startswith('SELECT p.device'):
                result.fetchall.return_value = memberships
            elif sql.startswith('SELECT id FROM points'):
                result.fetchone.return_value = {'id': 22}
            else:
                raise AssertionError(sql)
            return result

        conn.execute.side_effect = execute
        return plan, conn, layout, memberships, review_path

    def test_binding_uses_explicit_verified_layout_and_source_review(self):
        plan, conn, layout, _, _ = self.binding_fixture()
        self.assertEqual(database.binding(conn, plan), {'scene_id': 1, 'room_id': 6, 'ignition_point_id': 22})
        self.assertEqual(conn.execute.call_args_list[0].args[1], ('synthetic-scene', 1, 'Room8'))
        self.assertTrue(all(c.args[0].startswith('SELECT') for c in conn.execute.call_args_list))

    def test_unverified_layout_and_mismatched_review_are_rejected(self):
        plan, conn, layout, _, _ = self.binding_fixture()
        layout['xy_verified'] = False
        with self.assertRaises(ValueError): database.binding(conn, plan)
        layout['xy_verified'] = True
        layout['review']['alignment_report_sha256'] = 'wrong'
        with self.assertRaises(ValueError): database.binding(conn, plan)

    def test_changed_imported_evidence_is_rejected(self):
        plan, conn, _, _, review_path = self.binding_fixture()
        review_path.write_text('{}')
        with self.assertRaises(ValueError): database.binding(conn, plan)

    def test_database_membership_cannot_turn_doorway_into_interior(self):
        plan, conn, _, memberships, _ = self.binding_fixture()
        memberships[-2]['kind'] = 'interior'
        with self.assertRaises(ValueError): database.binding(conn, plan)

    def test_database_outside_point_cannot_be_assigned_to_room(self):
        plan, conn, _, memberships, _ = self.binding_fixture()
        memberships[-1]['source_room_id'] = 'Room8'
        with self.assertRaises(ValueError): database.binding(conn, plan)

    def test_existing_job_identity_rejects_cross_room_or_duplicate_rows(self):
        conn = MagicMock(); plan = self.plan()
        identity = {'scene_id': 1, 'room_id': 6, 'ignition_point_id': 22}
        row = {'id': 4, 'room_id': 6, 'layout_version_id': 1, 'ignition_point_id': 22,
               'config': {'snapshot_signature': plan.signature, 'asset_version': plan.asset_version}}
        conn.execute.return_value.fetchall.return_value = [row]
        self.assertEqual(database.existing_job(conn, plan, identity)['id'], 4)
        row['room_id'] = 99
        with self.assertRaises(ValueError): database.existing_job(conn, plan, identity)
        conn.execute.return_value.fetchall.return_value = [row, row]
        with self.assertRaises(ValueError): database.existing_job(conn, plan, identity)

    def test_asset_conflict_does_not_reassign_or_overwrite(self):
        conn = MagicMock(); plan = self.plan()
        conn.execute.return_value.fetchall.return_value = [{'sha256': 'changed', 'room_id': 99,
            'kind': plan.files[0].kind, 'bucket': None, 'object_key': None}]
        with self.assertRaises(ValueError): database.no_asset_conflicts(conn, plan, {'scene_id': 1, 'room_id': 6})
        self.assertTrue(all(call.args[0].startswith('SELECT') for call in conn.execute.call_args_list))

    def test_registration_transaction_links_input_output_and_reuses_job(self):
        plan = self.plan(); identity = {'scene_id': 1, 'room_id': 6, 'ignition_point_id': 22}
        conn = MagicMock(); context = MagicMock()
        context.__enter__.return_value = conn
        conn.execute.return_value.fetchone.return_value = {'id': 7}
        with patch.object(database, 'connect', return_value=context), patch.object(database, 'binding', return_value=identity), \
             patch.object(database, 'existing_job', return_value=None), patch.object(database, 'no_asset_conflicts'):
            first = database.register(plan)
        self.assertFalse(first['reused_job'])
        links = [call.args[1] for call in conn.execute.call_args_list if call.args[0].startswith('INSERT INTO render_job_assets')]
        # GLB/previews belong to the room, not inputs consumed by Blender.
        self.assertEqual([x[-1] for x in links], ['input', 'output'])
        context.__exit__.assert_called_once_with(None, None, None)
        conn.reset_mock()
        with patch.object(database, 'connect', return_value=nullcontext(conn)), patch.object(database, 'binding', return_value=identity), \
             patch.object(database, 'existing_job', return_value={'id': 7}), patch.object(database, 'no_asset_conflicts'):
            self.assertTrue(database.register(plan)['reused_job'])
        self.assertFalse(any(call.args[0].startswith('INSERT INTO render_jobs') for call in conn.execute.call_args_list))

    def test_sql_failure_escapes_transaction_and_is_not_reported_as_success(self):
        plan = self.plan(); context = MagicMock(); conn = context.__enter__.return_value
        conn.execute.side_effect = RuntimeError('synthetic SQL failure')
        with patch.object(database, 'connect', return_value=context):
            with self.assertRaises(RuntimeError): database.register(plan)
        self.assertIs(context.__exit__.call_args.args[0], RuntimeError)


if __name__ == '__main__':
    unittest.main()
