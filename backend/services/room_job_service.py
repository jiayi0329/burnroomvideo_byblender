"""File-authoritative Room8 jobs, safe-launcher handoff and read-only history."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
from contextvars import copy_context

from backend.adapters.postgres import room_job_repository as repository
from backend.paths import project_root
from backend.services.room_registration import inside, token
from render_engine.jobs import room_animation_job as contract
from render_engine.jobs import run_room_animation as launcher
from render_engine.jobs.operation_logging import bind_context, child_environment, current_context, emit, stage, traced, mark_failure

DATA_ROOT = Path('/app/data')
ACTIVE = {'created', 'preparing', 'rendering', 'encoding'}
TERMINAL = {'awaiting_visual_review', 'failed', 'interrupted'}


class JobError(Exception):
    def __init__(self, status: int, code: str):
        self.status, self.code = status, code
        super().__init__(code)


def options() -> dict:
    return {'render_enabled': os.getenv('ROOM_JOB_RENDER_ENABLED') == '1',
            'direct_final_enabled': os.getenv('ROOM_JOB_DIRECT_FINAL_ENABLED') == '1',
            'room_ids': ['Room8'], 'style_presets': ['r3'], 'camera_modes': ['overview', 'closeup'],
            'presets': {'test': {'stage': 'short', 'duration_seconds': 4, 'fps': 12, 'resolution': [960, 540]},
                        'final': {'stage': 'final', 'duration_seconds': 24, 'fps': 24, 'resolution': [1280, 720]}},
            'requires_confirmation': True, 'requires_idempotency_key': True}


def room_root(scene_code: str) -> Path:
    base = DATA_ROOT.resolve()
    path = base/token(scene_code)/'rooms/Room8'
    resolved = path.resolve()
    if not resolved.is_relative_to(base) or resolved != path:
        raise JobError(409, 'unsafe_room_path')
    return resolved


def job_directory(scene_code: str, job_id: str) -> Path:
    root = room_root(scene_code)/'render_jobs'
    if root.resolve() != root:
        raise JobError(409, 'unsafe_job_path')
    job = root/token(job_id)
    if not job.is_dir():
        raise JobError(404, 'job_not_found')
    resolved = job.resolve()
    if resolved.parent != root.resolve() or not resolved.is_relative_to(DATA_ROOT.resolve()):
        raise JobError(409, 'unsafe_job_path')
    return resolved


def read_document(job: Path, name: str) -> dict:
    value = contract.read_json(inside(job, job/name))
    if not isinstance(value, dict):
        raise ValueError('Invalid job document')
    return value


def snapshot(job: Path, scene_code: str) -> dict:
    spec = read_document(job, 'config_snapshot.json')
    if contract.fingerprint({k: v for k, v in spec.items() if k != 'signature'}) != spec['signature']:
        raise ValueError('Snapshot fingerprint mismatch')
    version = token(Path(spec['inputs']['asset'].replace('\\', '/')).parent.name)
    expected = f'/{scene_code}/rooms/Room8/{version}/asset'
    if not spec['inputs']['asset'].replace('\\', '/').endswith(expected):
        raise ValueError('Snapshot belongs to another room')
    if spec['animation']['camera_mode'] not in ('overview', 'closeup'):
        raise ValueError('Unknown camera mode')
    return spec


@traced('room.api', 'read_job')
def get_job(scene_code: str, job_id: str) -> dict:
    job = job_directory(scene_code, job_id)
    try:
        spec = snapshot(job, scene_code)
        state = read_document(job, 'status.json')['state']
        if state not in ACTIVE | TERMINAL:
            raise ValueError('Unknown runtime state')
        animation = spec['animation']
        records, technical = [], False
        if (job/'render_manifest.json').exists():
            manifest = read_document(job, 'render_manifest.json')
            if manifest.get('signature') != spec['signature']:
                raise ValueError('Manifest signature mismatch')
            records = manifest.get('frames', [])
            technical = (state == 'awaiting_visual_review' and manifest.get('technical_complete') is True
                         and manifest.get('worker_complete') is True and manifest.get('guarded_files_unchanged') is True)
        kind = 'camera_check' if animation['stage'] == 'camera_check' else 'video'
        completed = len({r['frame'] for r in records if r.get('kind') == kind
                         and r.get('camera') == animation['camera_mode'] and isinstance(r.get('frame'), int)
                         and (r['frame'] == round(3.5*animation['fps'])+1 if kind == 'camera_check'
                              else 1 <= r['frame'] <= animation['frame_count'])})
        timing = read_document(job, 'timing_report.json') if (job/'timing_report.json').exists() else {}
        seconds = timing.get('total_seconds_this_attempt', timing.get('elapsed_seconds_this_attempt'))
        if not isinstance(seconds, (float, int)) or not 0 <= seconds < 1e12:
            seconds = None
        video_available = False
        if technical and animation['stage'] != 'camera_check':
            video_available = verified_video(job, spec) is not None
        return {'scene_code': scene_code, 'room_id': 'Room8', 'job_id': job_id,
                'asset_version': Path(spec['inputs']['asset'].replace('\\', '/')).parent.name,
                'runtime_state': state, 'technical_complete': technical,
                'human_acceptance': 'not_recorded', 'preset': animation['preset'],
                'camera_mode': animation['camera_mode'], 'style_preset': 'r3',
                'fps': animation['fps'], 'resolution': animation['resolution'],
                'duration_seconds': animation['duration_seconds'], 'total_frames': animation['frame_count'],
                'completed_frames': completed, 'progress_percent': round(100*completed/max(1, animation['frame_count']), 2),
                'total_seconds': seconds, 'video_available': video_available,
                'video_url': f'/api/room-jobs/{job_id}/video?scene_code={scene_code}&room_id=Room8' if video_available else None,
                'error_code': 'render_failed' if state in ('failed', 'interrupted') else None}
    except JobError:
        raise
    except (OSError, ValueError, KeyError, TypeError):
        raise JobError(409, 'job_evidence_invalid') from None


def verified_video(job: Path, spec: dict) -> Path:
    """Validate historical receipt, then verify bytes without rerunning FFmpeg."""
    receipt = read_document(job, 'video_receipt.json')
    manifest = read_document(job, 'render_manifest.json')
    animation = spec['animation']
    filename = 'fire_final.mp4' if animation['stage'] == 'final' else 'fire_short.mp4'
    if (read_document(job, 'status.json').get('state') != 'awaiting_visual_review'
            or manifest.get('technical_complete') is not True or manifest.get('worker_complete') is not True
            or manifest.get('guarded_files_unchanged') is not True or manifest.get('signature') != spec['signature']
            or receipt.get('full_decode_passed') is not True or receipt.get('file') != filename):
        raise JobError(409, 'video_not_ready')
    from fractions import Fraction
    for key, expected in {'frames': animation['frame_count'], 'resolution': animation['resolution'],
                          'duration_seconds': animation['duration_seconds'], 'codec': 'h264', 'pixel_format': 'yuv420p'}.items():
        if receipt.get(key) != expected or manifest.get('video', {}).get(key) != expected:
            raise JobError(409, 'video_evidence_invalid')
    if Fraction(receipt['fps']) != animation['fps']:
        raise JobError(409, 'video_evidence_invalid')
    path = inside(job, job/filename)
    for key in ('sha256', 'bytes', 'file', 'fps', 'full_decode_passed'):
        if manifest['video'].get(key) != receipt.get(key):
            raise JobError(409, 'video_evidence_invalid')
    from backend.services.room_video import verify_bytes
    verify_bytes(path, receipt['sha256'], receipt['bytes'])
    return path


@traced('room.api', 'history')
def history(scene_code: str, limit: int, offset: int) -> dict:
    root = room_root(scene_code)/'render_jobs'
    if root.resolve() != root:
        raise JobError(409, 'unsafe_job_path')
    if not root.is_dir():
        return {'jobs': [], 'limit': limit, 'offset': offset, 'has_more': False}
    # One explicit room only; no cross-scene scans or mtime-based selection.
    ids = []
    for path in root.iterdir():
        if not path.is_dir() or path.is_symlink():
            continue
        try:
            token(path.name)
        except ValueError:
            continue
        ids.append(path.name)
    ids.sort(reverse=True)
    items = []
    for name in ids[offset:offset+limit]:
        try:
            token(name)
            items.append(get_job(scene_code, name))
        except (JobError, ValueError):
            items.append({'scene_code': scene_code, 'room_id': 'Room8', 'job_id': name,
                          'runtime_state': 'unknown', 'error_code': 'job_evidence_invalid'})
    return {'jobs': items, 'limit': limit, 'offset': offset, 'has_more': len(ids) > offset+limit}


def index_path(key: str) -> Path:
    root = DATA_ROOT.resolve()
    path = root/'.room_job_requests'/(hashlib.sha256(key.encode()).hexdigest()+'.json')
    if path.resolve() != path:
        raise JobError(409, 'unsafe_request_index')
    return path


def existing_submission(path: Path, payload: dict, expected: str) -> dict | None:
    if not path.exists():
        return None
    record = contract.read_json(inside(DATA_ROOT.resolve(), path))
    if record['request_fingerprint'] != expected:
        raise JobError(409, 'idempotency_key_reused_with_different_request')
    result = get_job(payload['scene_code'], record['job_id'])
    return {**result, 'reused': True, 'submission_trace_id': record['trace_id'],
            'database_job_id': record.get('database_job_id')}


def check_idle() -> None:
    for path in DATA_ROOT.glob('*/render_status.json'):
        if contract.read_json(path).get('status') == 'running':
            raise JobError(409, 'legacy_render_active')
    for path in DATA_ROOT.glob('*/rooms/*/render_jobs/*/status.json'):
        if contract.read_json(path).get('state') in ACTIVE:
            raise JobError(409, 'room_render_active')
    launcher.busy_processes()


def mark_submission_failed(job: Path, error_type: str) -> None:
    if read_document(job, 'status.json').get('state') == 'created':
        contract.write_json(job/'status.json', {'state': 'failed', 'error_code': 'api_launcher_failed', 'frames_retained': True})
        contract.write_json(job/'api_failure.json', {'error_type': error_type, 'at': datetime.now(timezone.utc).isoformat()})


def reap_process(process) -> None:
    """Reap the detached Python launcher; child owns actual render outcomes."""
    with stage('room.api', 'launcher_exit'):
        if process.wait() != 0:
            mark_failure('launcher_failed')


def start_reaper(process) -> None:
    context = copy_context()
    threading.Thread(target=lambda: context.run(reap_process, process), daemon=True).start()


@traced('room.api', 'submit')
def submit(payload: dict, key: str) -> dict:
    request_hash = contract.fingerprint(payload)
    index = index_path(key)
    old = existing_submission(index, payload, request_hash)
    if old:
        return old
    if not options()['render_enabled']:
        raise JobError(503, 'render_submission_disabled')
    job, process, released = None, None, False
    try:
        with launcher.gpu_lock(DATA_ROOT):
            old = existing_submission(index, payload, request_hash)
            if old:
                return old
            check_idle()
            if any(not shutil.which(name) for name in ('blender', 'ffmpeg', 'ffprobe')):
                raise JobError(503, 'render_tools_unavailable')
            try:
                source = repository.resolve(DATA_ROOT, payload['scene_code'], payload['asset_version'], payload['layout_version_id'])
            except LookupError:
                raise JobError(404, 'registered_source_not_found') from None
            except repository.CatalogUnavailable:
                raise JobError(503, 'catalog_unavailable') from None
            except (ValueError, OSError, KeyError, TypeError):
                raise JobError(409, 'registered_source_invalid') from None
            except Exception:
                raise JobError(503, 'catalog_unavailable') from None
            inputs = contract.preflight(source.asset, source.scene/'points.json',
                project_root()/'configs/render/room_fire_round3.json', project_root(),
                reference_manifest=source.reference, require_reference=True)
            is_final = payload['preset'] == 'final'
            direct = is_final and options()['direct_final_enabled'] and not payload.get('approval_job_id')
            spec = contract.build_spec(inputs, 'final' if is_final else 'short', payload['preset'],
                camera_mode=payload['camera_mode'], direct_final=direct)
            approval = None
            if is_final and not direct:
                if not payload.get('approval_job_id'):
                    raise JobError(409, 'final_requires_approval_or_server_policy')
                approval = inside(source.scene, source.asset.parent.parent/'render_jobs'/token(payload['approval_job_id'])/'approval.json')
                contract.verify_approval(approval, source.asset.parent.parent/'render_jobs', spec)
            elif not is_final and payload.get('approval_job_id'):
                raise JobError(422, 'test_does_not_accept_approval')
            with bind_context(scene_code=source.scene.name, room_id='Room8', asset_version=source.asset_version):
                root = source.asset.parent.parent/'render_jobs'
                if root.resolve() != root:
                    raise JobError(409, 'unsafe_job_path')
                job = contract.create_job(root, spec)
                with bind_context(job_id=job.name), stage('room.api', 'reserve_and_launch'):
                    database_id = repository.create_summary(source, job, spec)
                    record = {'schema_version': 1, 'source': 'room_job_api', 'job_id': job.name,
                              'scene_code': source.scene.name, 'request_fingerprint': request_hash,
                              'snapshot_signature': spec['signature'], 'trace_id': current_context()['trace_id'],
                              'database_job_id': database_id, 'approval_job_id': payload.get('approval_job_id')}
                    contract.write_json(job/'api_request.json', record)
                    index.parent.mkdir(mode=0o700, exist_ok=True)
                    with index.open('x', encoding='utf-8') as out:
                        json.dump(record, out)
                    env = dict(os.environ); env.update(child_environment())
                    with (job/'api_launcher.log').open('xb') as output:
                        process = subprocess.Popen([sys.executable, '-u', '-m', 'backend.cli.run_room_job', '--job', str(job)],
                            cwd=project_root(), stdin=subprocess.PIPE, stdout=output, stderr=subprocess.STDOUT,
                            env=env, start_new_session=True, close_fds=True)
                    contract.write_json(job/'api_launch.json', {'pid': process.pid, 'at': datetime.now(timezone.utc).isoformat()})
        # Child cannot acquire the same GPU lock until this explicit handoff.
        process.stdin.write(b'go\n'); process.stdin.flush(); process.stdin.close()
        released = True
        with bind_context(scene_code=payload['scene_code'], room_id='Room8', job_id=job.name,
                          asset_version=payload['asset_version']):
            start_reaper(process)
        emit('accepted', operation='room.api', stage='launcher_handoff', job_id=job.name,
             scene_code=payload['scene_code'], room_id='Room8')
        return {**get_job(payload['scene_code'], job.name), 'reused': False,
                'database_job_id': database_id, 'submission_trace_id': record['trace_id']}
    except BaseException as exc:
        if process is not None and not released and process.stdin is not None:
            process.stdin.close()
            with bind_context(job_id=job.name, scene_code=payload['scene_code'], room_id='Room8'):
                start_reaper(process)
        if job is not None and not released:
            mark_submission_failed(job, type(exc).__name__)
            try:
                repository.sync(payload['scene_code'], job.name, spec['signature'], 'failed')
            except Exception:
                pass  # File state and operation logs retain the original failure.
        raise


def run_reserved(job: Path) -> None:
    """Called only by the independent CLI after the parent has released its lock."""
    relative = job.resolve().relative_to(DATA_ROOT.resolve()).parts
    if len(relative) != 5 or relative[1:4] != ('rooms', 'Room8', 'render_jobs'):
        raise ValueError('Invalid reserved job path')
    scene_code, job_id = relative[0], relative[4]
    job = job_directory(scene_code, job_id)
    record = read_document(job, 'api_request.json')
    if record.get('source') != 'room_job_api' or record.get('job_id') != job_id:
        raise ValueError('API reservation required')
    spec = snapshot(job, scene_code)
    if record['snapshot_signature'] != spec['signature']:
        raise ValueError('Reservation signature differs')
    animation, inputs = spec['animation'], spec['inputs']
    direct = animation.get('authorization', {}).get('mode') == 'explicit_direct_final'
    try:
        if sys.stdin.readline() != 'go\n':
            raise ValueError('Missing parent handoff')
        # Parent writes api_launch.json after Popen returns, then sends go.
        # Reading its PID before that handshake would race process startup.
        if read_document(job, 'api_launch.json')['pid'] != os.getpid():
            raise ValueError('Launcher PID differs')
        if direct and not options()['direct_final_enabled']:
            raise ValueError('Direct final policy withdrawn')
        approval = (inside(job.parent, job.parent/token(record['approval_job_id'])/'approval.json')
                    if record.get('approval_job_id') else None)
        args = argparse.Namespace(asset=Path(inputs['asset']), points=Path(inputs['points']), config=Path(inputs['config']),
            stage=animation['stage'], preset=animation['preset'], camera_mode=animation['camera_mode'],
            reference_samples=Path(inputs['camera_reference']['manifest']), wall_height=animation['wall_height'],
            drop_component=animation['drop_components'], direct_final=direct, approval=approval, resume=job)
        if launcher.execute(args) != job:
            raise ValueError('Launcher returned a different job')
    except BaseException as exc:
        mark_submission_failed(job, type(exc).__name__)
        raise
    finally:
        try:
            repository.sync(scene_code, job_id, spec['signature'], read_document(job, 'status.json')['state'])
        except Exception:
            # Do not turn a completed video into a render failure or rerun it.
            emit('failure', operation='room.api', stage='summary_sync', error_code='catalog_sync_failed')
