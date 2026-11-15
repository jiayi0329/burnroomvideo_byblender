"""PRD controlled job API / OBSERVABILITY: no real services or rendering.

Real ASGI routing, files, signatures and streaming; mocked SQL, process, GPU
lock and safe launcher. Synthetic video bytes are not a media-decoding test.
"""
from contextlib import contextmanager
from copy import deepcopy
import io
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from backend.api import main, room_jobs
from backend.adapters.postgres import room_job_repository as database
from backend.cli import run_room_job as cli
from backend.services import room_job_service as service, room_video
from render_engine.jobs import operation_logging as log
from render_engine.jobs import room_animation_job as contract
from tests.backend.test_room_registration import Fixture, DEVICES


class JobsFixture(Fixture):
    def setUp(self):
        super().setUp()
        root_patch = patch.object(service, 'DATA_ROOT', self.root)
        root_patch.start(); self.addCleanup(root_patch.stop)
        self.env = patch.dict(os.environ, {'ROOM_JOB_RENDER_ENABLED': '1', 'ROOM_JOB_DIRECT_FINAL_ENABLED': '0'})
        self.env.start(); self.addCleanup(self.env.stop)
        self.client = TestClient(main.app)
        self.payload = {'scene_code': self.scene.name, 'room_id': 'Room8', 'asset_version': 'version-1',
            'layout_version_id': 1, 'style_preset': 'r3', 'preset': 'test', 'camera_mode': 'overview',
            'confirm_render': True, 'approval_job_id': None}
        self.inputs = deepcopy(self.spec['inputs'])
        self.inputs['timeline']['spread_events'][-1]['time'] = 3
        self.reference = self.asset.parent/'style_round3/reference/sample_manifest.json'
        self.reference.parent.mkdir(parents=True)
        self.write(self.reference, {})
        self.inputs.update(asset=str(self.asset), points=str(self.scene/'points.json'),
            config='/synthetic/room_fire_round3.json', camera_reference={'manifest': str(self.reference)})
        self.source = database.RoomSource(self.scene, 'Room8', 'version-1', 1,
            self.manifest['provenance'], DEVICES, {'scene_id': 1, 'room_id': 6, 'ignition_point_id': 22}, self.reference)
        self.write(self.job/'render_manifest.json', {**self.render, 'frames': [
            {'kind': 'video', 'camera': 'overview', 'frame': f} for f in range(1, 577)]})
        self.write(self.job/'timing_report.json', {'total_seconds_this_attempt': 360.542})

    def post(self, payload=None, key='synthetic-key-1', **headers):
        return self.client.post('/api/room-jobs', json=payload or self.payload,
            headers={'Idempotency-Key': key, **headers})

    @contextmanager
    def launch_stubs(self):
        self.locked = False

        @contextmanager
        def lock(root):
            self.assertEqual(root, self.root)
            self.locked = True
            try:
                yield 99
            finally:
                self.locked = False

        process = MagicMock(pid=12345)
        process.stdin.write.side_effect = lambda data: self.assertFalse(self.locked)
        with patch.object(service.launcher, 'gpu_lock', side_effect=lock), \
             patch.object(service.launcher, 'busy_processes'), \
             patch.object(service.shutil, 'which', return_value='/synthetic/tool'), \
             patch.object(database, 'resolve', return_value=self.source) as resolve, \
             patch.object(database, 'create_summary', return_value=2) as summary, \
             patch.object(database, 'sync') as sync, \
             patch.object(contract, 'preflight', return_value=self.inputs) as preflight, \
             patch.object(service.subprocess, 'Popen', return_value=process) as popen, \
             patch.object(service, 'start_reaper'):
            yield SimpleNamespace(process=process, popen=popen, resolve=resolve,
                                  summary=summary, sync=sync, preflight=preflight)


class HTTPContracts(JobsFixture):
    def test_options_read_only_and_default_submission_disabled(self):
        schema = self.client.get('/openapi.json').json()
        operations = [value['operationId'] for path, methods in schema['paths'].items()
            if path.startswith('/api/room-jobs') for value in methods.values() if 'operationId' in value]
        self.assertEqual(len(operations), len(set(operations)))
        self.assertEqual(len(operations), 7)
        with patch.dict(os.environ, {'ROOM_JOB_RENDER_ENABLED': '0'}), \
             patch.object(database, 'resolve') as resolve, patch.object(service.subprocess, 'Popen') as process:
            options = self.client.get('/api/room-jobs/options').json()
            response = self.post()
        self.assertFalse(options['render_enabled'])
        self.assertEqual(options['presets']['test']['duration_seconds'], 4)
        self.assertEqual(response.status_code, 503)
        resolve.assert_not_called(); process.assert_not_called()

    def test_rejects_custom_paths_styles_points_rooms_and_client_direct_final(self):
        invalid = ({'asset': '/tmp/evil.blend'}, {'config': '/tmp/style.json'}, {'ignition_point': 32},
                   {'points': [42]}, {'style_preset': 'r1'}, {'room_id': 'Room9'}, {'direct_final': True},
                   {'layout_version_id': 0}, {'layout_version_id': True}, {'scene_code': '../escape'},
                   {'asset_version': '../escape'}, {'confirm_render': 1}, {'confirm_render': False},
                   {'preset': 'final', 'camera_mode': 'closeup'})
        with patch.object(service, 'submit') as submit:
            for changes in invalid:
                with self.subTest(changes=changes):
                    self.assertEqual(self.post({**self.payload, **changes}).status_code, 422)
        submit.assert_not_called()

    def test_requires_key_and_explicit_confirmation(self):
        self.assertEqual(self.client.post('/api/room-jobs', json=self.payload).status_code, 422)
        self.assertEqual(self.post(key='short').status_code, 422)
        body = dict(self.payload); del body['confirm_render']
        self.assertEqual(self.post(body).status_code, 422)

    def test_sources_redacts_missing_database_configuration(self):
        with patch.object(database, 'connect', side_effect=ValueError('secret-database-password')):
            response = self.client.get('/api/room-jobs/sources')
        self.assertEqual(response.status_code, 503)
        self.assertNotIn('secret', response.text)

    def test_missing_job_404_and_other_room_rejected(self):
        self.assertEqual(self.client.get('/api/room-jobs/missing?scene_code=synthetic-scene').status_code, 404)
        self.assertEqual(self.client.get('/api/room-jobs/job-1?scene_code=synthetic-scene&room_id=Room9').status_code, 422)

    def test_completed_history_and_video_work_without_database(self):
        with patch.object(database, 'connect', side_effect=AssertionError('DB forbidden')):
            response = self.client.get('/api/room-jobs/job-1?scene_code=synthetic-scene')
            listing = self.client.get('/api/room-jobs?scene_code=synthetic-scene').json()
            video = self.client.get('/api/room-jobs/job-1/video?scene_code=synthetic-scene', headers={'Range': 'bytes=0-0'})
        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertEqual((result['completed_frames'], result['progress_percent'], result['total_seconds']), (576, 100, 360.542))
        self.assertTrue(result['technical_complete']); self.assertTrue(result['video_available'])
        self.assertEqual(result['human_acceptance'], 'not_recorded')
        self.assertNotIn('/app/data', response.text)
        self.assertEqual(len(listing['jobs']), 1)
        self.assertEqual((video.status_code, video.content), (206, b's'))


class SafeSubmission(JobsFixture):
    def test_new_job_reserves_identity_handoff_after_unlock_and_trace_to_child(self):
        before = {p: p.read_bytes() for p in self.scene.rglob('*') if p.is_file()}
        with self.launch_stubs() as stub:
            response = self.post(**{'X-Trace-ID': 'job-api-test'})
        self.assertEqual(response.status_code, 202, response.text)
        result = response.json(); self.assertFalse(result['reused'])
        self.assertEqual((result['total_frames'], result['runtime_state']), (48, 'created'))
        self.assertEqual(result['submission_trace_id'], 'job-api-test')
        job = service.job_directory(self.scene.name, result['job_id'])
        self.assertNotEqual(job, self.job)
        self.assertTrue((job/'config_snapshot.json').is_file())
        self.assertEqual(self.payload['camera_mode'], 'overview')
        command = stub.popen.call_args.args[0]
        self.assertEqual(command[:5], [sys.executable, '-u', '-m', 'backend.cli.run_room_job', '--job'])
        self.assertNotIn('blender', command)
        self.assertTrue(stub.popen.call_args.kwargs['start_new_session'])
        context = json.loads(stub.popen.call_args.kwargs['env']['BURNROOM_OPERATION_CONTEXT'])
        self.assertEqual((context['trace_id'], context['job_id']), ('job-api-test', job.name))
        stub.process.stdin.write.assert_called_once_with(b'go\n')
        self.assertEqual(stub.preflight.call_args.kwargs['reference_manifest'], self.reference)
        self.assertEqual({p: p.read_bytes() for p in before}, before)
        events = self.events()
        accepted = [e for e in events if e['event'] == 'accepted']
        self.assertEqual(accepted[0]['job_id'], job.name)
        self.assertTrue(any(e.get('stage') == 'reserve_and_launch' and e['event'] == 'success' for e in events))

    def test_idempotent_running_retry_ignores_disabled_switch_and_never_relaunches(self):
        with self.launch_stubs() as stub:
            first = self.post().json()
            with patch.dict(os.environ, {'ROOM_JOB_RENDER_ENABLED': '0'}):
                second = self.post().json()
        self.assertEqual(first['job_id'], second['job_id']); self.assertTrue(second['reused'])
        stub.popen.assert_called_once(); stub.summary.assert_called_once()

    def test_same_key_different_payload_conflicts_without_launching(self):
        with self.launch_stubs() as stub:
            self.assertEqual(self.post().status_code, 202)
            result = self.post({**self.payload, 'camera_mode': 'closeup'})
        self.assertEqual(result.status_code, 409); stub.popen.assert_called_once()

    def test_completed_retry_returns_original_video_without_launching_again(self):
        payload_hash = contract.fingerprint(self.payload)
        index = service.index_path('synthetic-key-1'); index.parent.mkdir()
        self.write(index, {'request_fingerprint': payload_hash, 'job_id': self.job.name,
                           'trace_id': 'original-trace', 'database_job_id': 1})
        with self.launch_stubs() as stub:
            response = self.post()
        self.assertEqual(response.status_code, 202)
        self.assertTrue(response.json()['video_available']); self.assertTrue(response.json()['reused'])
        self.assertEqual(response.json()['submission_trace_id'], 'original-trace')
        stub.popen.assert_not_called(); stub.resolve.assert_not_called()

    def test_different_key_cannot_overlap_active_reservation(self):
        with self.launch_stubs() as stub:
            self.assertEqual(self.post().status_code, 202)
            result = self.post(key='another-key-2')
        self.assertEqual(result.status_code, 409); stub.popen.assert_called_once()

    def test_legacy_active_gpu_busy_and_lock_conflict_do_not_reserve(self):
        with self.launch_stubs() as stub:
            self.write(self.scene/'render_status.json', {'status': 'running'})
            self.assertEqual(self.post().status_code, 409)
            (self.scene/'render_status.json').unlink()
            service.launcher.busy_processes.side_effect = RuntimeError('GPU busy with secret-details')
            response = self.post()
            self.assertEqual(response.status_code, 409); self.assertNotIn('secret', response.text)
            service.launcher.gpu_lock.side_effect = RuntimeError('locked')
            self.assertEqual(self.post().status_code, 409)
        stub.popen.assert_not_called(); stub.summary.assert_not_called()

    def test_missing_tools_or_catalog_outage_do_not_reserve(self):
        with self.launch_stubs() as stub:
            service.shutil.which.return_value = None
            self.assertEqual(self.post().status_code, 503)
            service.shutil.which.return_value = '/synthetic/tool'
            stub.resolve.side_effect = database.CatalogUnavailable('private error')
            self.assertEqual(self.post().status_code, 503)
        stub.popen.assert_not_called(); stub.summary.assert_not_called()

    def test_preflight_failure_never_reserves_or_launches(self):
        with self.launch_stubs() as stub:
            stub.preflight.side_effect = ValueError('R3 input changed')
            self.assertEqual(self.post().status_code, 409)
        stub.popen.assert_not_called(); stub.summary.assert_not_called()
        self.assertEqual(list(self.job.parent.iterdir()), [self.job])

    def test_unknown_source_and_changed_local_asset_rejected(self):
        with self.launch_stubs() as stub:
            stub.resolve.side_effect = LookupError('missing')
            self.assertEqual(self.post().status_code, 404)
            stub.resolve.side_effect = ValueError('hash differs')
            self.assertEqual(self.post().status_code, 409)
        stub.popen.assert_not_called()

    def test_popen_failure_retains_failed_reservation_and_does_not_retry_render(self):
        with self.launch_stubs() as stub:
            stub.popen.side_effect = OSError('synthetic-private-password')
            response = self.post()
            self.assertEqual(response.status_code, 409)
            self.assertNotIn('synthetic-private-password', response.text)
            retry = self.post()
        self.assertEqual(retry.status_code, 202)
        self.assertEqual(retry.json()['runtime_state'], 'failed')
        self.assertTrue(retry.json()['reused']); stub.popen.assert_called_once()
        stub.sync.assert_called_once()
        self.assertNotIn('synthetic-private-password', json.dumps(self.events()))

    def test_summary_failure_preserves_original_video_and_new_failed_job(self):
        with self.launch_stubs() as stub:
            stub.summary.side_effect = RuntimeError('private-db-error')
            self.assertEqual(self.post().status_code, 409)
        failed = [p for p in self.job.parent.iterdir() if p != self.job]
        self.assertEqual(len(failed), 1)
        self.assertEqual(service.read_document(failed[0], 'status.json')['state'], 'failed')
        self.assertEqual((self.job/'fire_final.mp4').read_bytes(), b'synthetic-video')
        stub.popen.assert_not_called()

    def test_broken_handoff_preserves_failed_job_and_reaps_child(self):
        with self.launch_stubs() as stub:
            stub.process.stdin.write.side_effect = BrokenPipeError('child exited')
            response = self.post()
            self.assertEqual(response.status_code, 409)
            retry = self.post().json()
        self.assertEqual(retry['runtime_state'], 'failed')
        stub.process.stdin.close.assert_called()

    def test_final_requires_review_or_operator_policy_and_remains_overview_576(self):
        body = {**self.payload, 'preset': 'final'}
        with self.launch_stubs() as stub:
            self.assertEqual(self.post(body).status_code, 409)
            stub.popen.assert_not_called()
            with patch.dict(os.environ, {'ROOM_JOB_DIRECT_FINAL_ENABLED': '1'}):
                response = self.post(body)
                self.assertEqual(response.status_code, 202, response.text)
                result = response.json()
        self.assertEqual((result['total_frames'], result['resolution'], result['duration_seconds']), (576, [1280, 720], 24))
        spec = service.snapshot(service.job_directory(self.scene.name, result['job_id']), self.scene.name)
        self.assertEqual(spec['animation']['authorization']['mode'], 'explicit_direct_final')

    def test_review_path_server_resolved_and_engine_verifier_used(self):
        approval = self.job/'approval.json'; self.write(approval, {})
        with self.launch_stubs(), patch.object(contract, 'verify_approval') as verify:
            response = self.post({**self.payload, 'preset': 'final', 'approval_job_id': self.job.name})
        self.assertEqual(response.status_code, 202)
        self.assertEqual(verify.call_args.args[:2], (approval, self.job.parent))

    def test_test_preset_rejects_approval(self):
        with self.launch_stubs() as stub:
            self.assertEqual(self.post({**self.payload, 'approval_job_id': 'job-1'}).status_code, 422)
        stub.popen.assert_not_called()

    def test_failed_launcher_is_reaped_and_logged_without_raw_output(self):
        process = MagicMock(); process.wait.return_value = 1
        service.reap_process(process)
        process.wait.assert_called_once()
        self.assertTrue(any(e['event'] == 'failure' and e.get('stage') == 'launcher_exit' for e in self.events()))


class ReadsAndVideo(JobsFixture):
    def endpoint(self): return f'/api/room-jobs/job-1/video?scene_code={self.scene.name}'

    def test_range_head_full_suffix_if_range_and_invalid_ranges(self):
        full = b'synthetic-video'
        response = self.client.get(self.endpoint())
        self.assertEqual((response.status_code, response.content), (200, full))
        self.assertEqual(response.headers['content-type'], 'video/mp4')
        for header, expected in [('bytes=0-0', b's'), ('bytes=10-', full[10:]), ('bytes=-5', full[-5:]), ('bytes=0-999', full)]:
            with self.subTest(header=header):
                response = self.client.get(self.endpoint(), headers={'Range': header})
                self.assertEqual((response.status_code, response.content), (206, expected))
                self.assertEqual(int(response.headers['content-length']), len(expected))
        head = self.client.head(self.endpoint(), headers={'Range': 'bytes=0-0'})
        self.assertEqual((head.status_code, head.content, head.headers['content-length']), (206, b'', '1'))
        response = self.client.get(self.endpoint(), headers={'Range': 'bytes=0-0', 'If-Range': '"different"'})
        self.assertEqual((response.status_code, response.content), (200, full))
        for header in ('bytes=99-', 'bytes=4-1', 'bytes=-0', 'bytes=0-1,3-4', 'bad', 'bytes=-'):
            response = self.client.get(self.endpoint(), headers={'Range': header})
            self.assertEqual(response.status_code, 416)
            self.assertEqual(response.headers['content-range'], f'bytes */{len(full)}')

    def test_modified_video_bytes_or_receipt_refuse_playback(self):
        (self.job/'fire_final.mp4').write_bytes(b'changed-video!!')
        self.assertEqual(self.client.get(self.endpoint()).status_code, 409)
        (self.job/'fire_final.mp4').write_bytes(b'synthetic-video')
        self.write(self.job/'video_receipt.json', {**self.video, 'full_decode_passed': False})
        self.assertEqual(self.client.get(self.endpoint()).status_code, 409)

    def test_stream_refuses_file_replaced_after_receipt_verification(self):
        actual = (self.job/'fire_final.mp4').stat()
        changed = SimpleNamespace(**{key: getattr(actual, key) for key in (
            'st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns')})
        changed.st_ino += 1
        with patch.object(room_video.os, 'fstat', return_value=changed):
            with self.assertRaises(OSError): self.client.get(self.endpoint())

    @unittest.skipUnless(os.name == 'nt', 'Windows path/handle ctime semantics')
    def test_windows_stream_accepts_ctime_only_stat_handle_discrepancy(self):
        actual = (self.job/'fire_final.mp4').stat()
        changed = SimpleNamespace(**{key: getattr(actual, key) for key in (
            'st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns')})
        changed.st_ctime_ns += 1
        with patch.object(room_video.os, 'fstat', return_value=changed):
            self.assertEqual(self.client.get(self.endpoint()).status_code, 200)

    def test_partial_failed_task_has_progress_and_no_raw_error(self):
        self.write(self.job/'status.json', {'state': 'failed', 'error': 'private-password /private/path'})
        self.write(self.job/'render_manifest.json', {**self.render, 'frames': [
            {'kind': 'video', 'camera': 'overview', 'frame': 1},
            {'kind': 'video', 'camera': 'overview', 'frame': 1},
            {'kind': 'keyframe', 'camera': 'overview', 'frame': 20}]})
        result = service.get_job(self.scene.name, self.job.name)
        self.assertEqual(result['completed_frames'], 1)
        self.assertFalse(result['video_available']); self.assertEqual(result['error_code'], 'render_failed')
        self.assertNotIn('private', json.dumps(result))

    def test_snapshot_tamper_rejected_and_history_retains_unknown_record(self):
        self.spec['animation']['camera_mode'] = 'closeup'
        self.write(self.job/'config_snapshot.json', self.spec)
        response = self.client.get('/api/room-jobs/job-1?scene_code=synthetic-scene')
        self.assertEqual(response.status_code, 409)
        result = service.history(self.scene.name, 20, 0)
        self.assertEqual(result['jobs'][0]['runtime_state'], 'unknown')

    def test_camera_check_uses_3_5s_frame_not_one_as_frame_number(self):
        self.spec['animation'].update(stage='camera_check', frame_count=1, fps=12)
        self.sign_spec()
        self.write(self.job/'render_manifest.json', {**self.render, 'signature': self.spec['signature'], 'frames': [
            {'kind': 'camera_check', 'camera': 'overview', 'frame': 43}]})
        result = service.get_job(self.scene.name, self.job.name)
        self.assertEqual(result['progress_percent'], 100)
        self.assertFalse(result['video_available'])

    def test_history_paginated_and_explicit_scene_only(self):
        (self.job.parent/'job-2').mkdir()
        first = service.history(self.scene.name, 1, 0)
        self.assertTrue(first['has_more']); self.assertEqual(first['jobs'][0]['job_id'], 'job-2')
        second = service.history(self.scene.name, 1, 1)
        self.assertFalse(second['has_more']); self.assertEqual(second['jobs'][0]['job_id'], 'job-1')
        self.assertEqual(service.history('another-scene', 20, 0)['jobs'], [])

    def test_video_evidence_resolution_and_signature_must_match(self):
        for changes in ({'resolution': [1, 1]}, {'frames': 575}, {'sha256': '0'*64}):
            self.write(self.job/'video_receipt.json', {**self.video, **changes})
            self.assertEqual(self.client.get(self.endpoint()).status_code, 409)

    def test_read_and_stream_logs_keep_http_trace_and_business_identity(self):
        response = self.client.get(self.endpoint(), headers={'Range': 'bytes=0-0', 'X-Trace-ID': 'video-trace'})
        self.assertEqual(response.status_code, 206)
        events = [e for e in self.events() if e['trace_id'] == 'video-trace']
        action = [e for e in events if e.get('stage') == 'request_operation' and e['event'] == 'success']
        self.assertEqual((action[0]['job_id'], action[0]['scene_code']), ('job-1', self.scene.name))
        self.assertIn('request_id', action[0]); self.assertIn('duration_ms', action[0])
        self.assertTrue(any(e.get('status_code') == 206 for e in events))


class InternalLauncher(JobsFixture):
    def reserve(self):
        inputs = deepcopy(self.inputs)
        spec = contract.build_spec(inputs, 'short')
        self.write(self.job/'config_snapshot.json', spec)
        self.write(self.job/'status.json', {'state': 'created'})
        self.write(self.job/'api_request.json', {'source': 'room_job_api', 'job_id': self.job.name,
            'snapshot_signature': spec['signature'], 'approval_job_id': None})
        self.write(self.job/'api_launch.json', {'pid': os.getpid()})
        return spec

    def test_handoff_reuses_safe_launcher_with_reserved_id_and_syncs(self):
        spec = self.reserve()
        with patch.object(service.sys, 'stdin', io.StringIO('go\n')), \
             patch.object(service.launcher, 'execute', return_value=self.job) as execute, patch.object(database, 'sync') as sync:
            service.run_reserved(self.job)
        args = execute.call_args.args[0]
        self.assertEqual((args.resume, args.stage, args.camera_mode), (self.job, 'short', 'overview'))
        self.assertEqual(args.reference_samples, self.reference)
        self.assertFalse(args.direct_final)
        sync.assert_called_once_with(self.scene.name, self.job.name, spec['signature'], 'created')

    def test_child_waits_for_parent_before_reading_launch_pid(self):
        self.reserve(); (self.job/'api_launch.json').unlink()
        def handoff():
            self.write(self.job/'api_launch.json', {'pid': os.getpid()})
            return 'go\n'
        stdin = MagicMock(); stdin.readline.side_effect = handoff
        with patch.object(service.sys, 'stdin', stdin), \
             patch.object(service.launcher, 'execute', return_value=self.job) as execute, patch.object(database, 'sync'):
            service.run_reserved(self.job)
        execute.assert_called_once()

    def test_missing_handoff_fails_closed_keeps_frames_and_no_render(self):
        self.reserve()
        with patch.object(service.sys, 'stdin', io.StringIO('')), \
             patch.object(service.launcher, 'execute') as execute, patch.object(database, 'sync'):
            with self.assertRaises(ValueError): service.run_reserved(self.job)
        self.assertEqual(service.read_document(self.job, 'status.json')['state'], 'failed')
        self.assertTrue((self.job/'fire_final.mp4').exists()); execute.assert_not_called()

    def test_wrong_pid_or_reservation_cannot_bypass_launcher(self):
        self.reserve()
        self.write(self.job/'api_launch.json', {'pid': os.getpid()+1})
        with patch.object(service.sys, 'stdin', io.StringIO('go\n')), \
             patch.object(service.launcher, 'execute') as execute, patch.object(database, 'sync'):
            with self.assertRaises(ValueError): service.run_reserved(self.job)
        execute.assert_not_called()

    def test_db_sync_failure_does_not_discard_completed_render(self):
        self.reserve()
        def complete(args):
            self.write(self.job/'status.json', {'state': 'awaiting_visual_review'})
            return self.job
        with patch.object(service.sys, 'stdin', io.StringIO('go\n')), \
             patch.object(service.launcher, 'execute', side_effect=complete), \
             patch.object(database, 'sync', side_effect=ValueError('secret-database-password')):
            service.run_reserved(self.job)
        self.assertEqual(service.read_document(self.job, 'status.json')['state'], 'awaiting_visual_review')
        self.assertTrue(any(e.get('error_code') == 'catalog_sync_failed' for e in self.events()))
        self.assertNotIn('secret-database-password', json.dumps(self.events()))

    def test_cli_inherits_context_and_redacts_failure(self):
        with patch.object(sys, 'argv', ['run', '--job', str(self.job)]), \
             patch.dict(os.environ, {'BURNROOM_OPERATION_CONTEXT': json.dumps({'trace_id': 'parent-trace', 'job_id': 'job-1'})}), \
             patch.object(cli, 'run_reserved', side_effect=RuntimeError('synthetic-private-password')), \
             patch('builtins.print') as output:
            self.assertEqual(cli.main(), 1)
        self.assertNotIn('synthetic-private-password', output.call_args.args[0])
        self.assertTrue(output.call_args.kwargs['flush'])
        self.assertTrue(any(e['trace_id'] == 'parent-trace' and e['event'] == 'failure' for e in self.events()))


class Repository(JobsFixture):
    def connection(self):
        connection = MagicMock()
        manager = MagicMock(); manager.__enter__.return_value = connection
        return connection, patch.object(database, 'connect', return_value=manager)

    def test_sources_return_identifiers_not_server_paths(self):
        conn, connection = self.connection()
        conn.execute.return_value.fetchall.return_value = [{'scene_code': self.scene.name, 'room_id': 'Room8',
            'database_room_id': 6, 'layout_version_id': 1, 'blend_asset_id': 60,
            'local_relative_path': 'rooms/Room8/version-1/asset/room.blend'}]
        with connection:
            result = database.sources()
        self.assertEqual(result['sources'][0]['asset_version'], 'version-1')
        self.assertNotIn('local_relative_path', result['sources'][0])

    def test_resolve_checks_published_fingerprint_binding_and_pins_reference(self):
        historical = deepcopy(self.spec)
        historical['inputs']['camera_reference'] = {'manifest': str(self.reference)}
        self.write(self.job/'config_snapshot.json', historical)
        conn, connection = self.connection()
        first, second = MagicMock(), MagicMock()
        first.fetchall.return_value = [{'sha256': contract.digest(self.asset/'room.blend'),
            'size_bytes': (self.asset/'room.blend').stat().st_size, 'bucket': 'burnroom-room-assets',
            'object_key': f'scenes/{self.scene.name}/rooms/Room8/assets/version-1/room.blend'}]
        second.fetchone.return_value = {'config': {'file_job_id': 'job-1'}}
        conn.execute.side_effect = [first, second]
        with connection, patch.object(database, 'binding', return_value=self.source.identity) as binding:
            source = database.resolve(self.root, self.scene.name, 'version-1', 1)
        self.assertEqual(source.reference, self.reference)
        self.assertEqual(source.interior_devices, DEVICES)
        self.assertEqual(conn.execute.call_args_list[0].args[1],
            (self.scene.name, 1, 'rooms/Room8/version-1/asset/room.blend'))
        binding.assert_called_once()

    def test_create_and_sync_use_same_scene_lock_and_parameterized_summary(self):
        conn, connection = self.connection()
        conn.execute.side_effect = [MagicMock(), MagicMock(**{'fetchone.return_value': None}),
                                   MagicMock(**{'fetchone.return_value': {'id': 2}})]
        with connection, patch.object(database, 'binding', return_value=self.source.identity):
            self.assertEqual(database.create_summary(self.source, self.job, self.spec), 2)
        self.assertIn('pg_advisory_xact_lock', conn.execute.call_args_list[0].args[0])
        metadata = conn.execute.call_args_list[-1].args[1][-1].obj
        self.assertEqual(metadata['file_job_id'], 'job-1')
        self.assertEqual(metadata['human_acceptance'], 'not_recorded')
        conn, connection = self.connection()
        with connection: database.sync(self.scene.name, 'job-1', self.spec['signature'], 'awaiting_visual_review')
        self.assertEqual(conn.execute.call_args.args[1][0], 'done')
        self.assertEqual(conn.execute.call_args.args[1][-2:], ('job-1', self.spec['signature']))


if __name__ == '__main__':
    unittest.main()
