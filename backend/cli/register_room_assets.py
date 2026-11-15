"""Preview, then explicitly upload and register one verified Room8 delivery."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.services.room_registration import build_plan, verify_unchanged
from render_engine.jobs.operation_logging import bind_context, cli_operation, stage


@contextmanager
def registration_lock(directory: Path):
    """Serialize cooperating uploaders; stale lock requires manual inspection."""
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    path = directory/'registration.lock'
    identity = uuid.uuid4().hex
    with path.open('x', encoding='utf-8') as out:
        out.write(identity)
    try:
        yield
    finally:
        if path.read_text(encoding='utf-8') == identity:
            path.unlink()


def save_receipt(path: Path, receipt: dict) -> None:
    # Each run owns a new directory. Never write into a render job/base asset.
    with path.open('x', encoding='utf-8') as out:
        json.dump(receipt, out, ensure_ascii=False, indent=2)
        out.write('\n')


def apply(plan) -> dict:
    from backend.adapters.minio.s3_io import get_minio_client
    from backend.adapters.minio.room_objects import ensure_object, private_bucket
    from backend.adapters.postgres.room_asset_repository import preflight, register

    root = plan.scene/'rooms'/plan.room_id/'registrations'
    receipt = {**plan.summary(), 'upload_status': 'not_uploaded',
               'registration_status': 'not_registered', 'verified_objects': [],
               'started_at': datetime.now(timezone.utc).isoformat()}
    run = None
    try:
        with registration_lock(root):
            run = root/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_'+uuid.uuid4().hex[:8])
            run.mkdir(mode=0o700)
            preflight(plan)  # Validate source binding before any remote upload.
            verify_unchanged(plan)
            client = get_minio_client()
            for bucket in sorted({file.bucket for file in plan.files}):
                private_bucket(client, bucket)
            for file in plan.files:
                verify_unchanged(plan)
                receipt['verified_objects'].append(ensure_object(client, file))
            receipt['upload_status'] = 'verified'
            for bucket in sorted({file.bucket for file in plan.files}):
                private_bucket(client, bucket)
            verify_unchanged(plan)
            receipt.update(register(plan))
    except BaseException as exc:
        receipt['error_type'] = type(exc).__name__
        receipt['finished_at'] = datetime.now(timezone.utc).isoformat()
        if run:
            save_receipt(run/'registration_receipt.json', receipt)
        raise
    receipt['finished_at'] = datetime.now(timezone.utc).isoformat()
    save_receipt(run/'registration_receipt.json', receipt)
    return {'mode': 'apply', 'scene_code': plan.scene.name, 'room_id': plan.room_id,
            'layout_version_id': plan.layout_version_id, 'file_job_id': plan.file_job_id,
            'file_count': len(plan.files), **{key: receipt[key] for key in (
                'database_job_id', 'database_room_id', 'reused_job', 'upload_status', 'registration_status')},
            'receipt': str(run/'registration_receipt.json')}


@cli_operation('catalog.register')
def main() -> int:
    parser = argparse.ArgumentParser(description='Register a verified Room8 delivery; preview by default')
    parser.add_argument('--data-root', type=Path, default=Path('/app/data'))
    parser.add_argument('--scene', required=True)
    parser.add_argument('--asset', type=Path, required=True)
    parser.add_argument('--job', type=Path, required=True)
    parser.add_argument('--layout-version-id', type=int, required=True)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    try:
        plan = build_plan(args.data_root, args.scene, args.asset, args.job, args.layout_version_id)
        with bind_context(scene_code=plan.scene.name, room_id=plan.room_id,
                          job_id=plan.file_job_id, asset_version=plan.asset_version):
            if args.apply:
                with stage('catalog.register', 'publication'):
                    result = apply(plan)
            else:
                result = {'mode': 'preview', 'upload_status': 'not_uploaded',
                          'registration_status': 'not_registered', **plan.summary()}
            print(json.dumps(result, ensure_ascii=False), flush=True)
        return 0
    except Exception as exc:
        print(f'[room-register] failed: {type(exc).__name__}; inputs retained; check operation logs and registration receipts', flush=True)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
