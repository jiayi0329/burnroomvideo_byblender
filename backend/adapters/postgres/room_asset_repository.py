"""Bind a publication to an imported layout; upload and DB transactions stay separate.

Uses existing eight tables. file_job_id/asset_version are versioned config
metadata until a separately reviewed schema migration adds dedicated columns.
All writers of these summaries must acquire the same per-scene advisory lock.
"""
from __future__ import annotations

import json

from backend.adapters.postgres.database import connect
from backend.services.room_registration import RegistrationPlan, inside, verify_unchanged
from render_engine.jobs.operation_logging import traced
from render_engine.jobs.room_animation_job import digest


def binding(conn, plan: RegistrationPlan) -> dict:
    row = conn.execute('''SELECT s.id AS scene_id,r.id AS room_id,l.xy_verified,l.review
        FROM scenes s JOIN layout_versions l ON l.scene_id=s.id
        JOIN rooms r ON r.layout_version_id=l.id AND r.scene_id=s.id
        WHERE s.scene_code=%s AND l.id=%s AND r.source_room_id=%s AND r.is_valid''',
        (plan.scene.name, plan.layout_version_id, plan.room_id)).fetchone()
    if not row or row['xy_verified'] is not True:
        raise ValueError('Imported, verified, valid room required')
    if row['review'].get('alignment_report_sha256') != plan.provenance['alignment_sha256']:
        raise ValueError('Imported layout differs from asset provenance')
    for kind, key in (('alignment_report', 'alignment_sha256'), ('review', 'review_sha256')):
        sources = conn.execute('SELECT local_relative_path FROM assets WHERE scene_id=%s AND kind=%s AND sha256=%s',
                               (row['scene_id'], kind, plan.provenance[key])).fetchall()
        if not sources:
            raise ValueError('Imported source evidence is missing')
        for source in sources:
            path = inside(plan.scene, plan.scene/source['local_relative_path'])
            if digest(path) != plan.provenance[key]:
                raise ValueError('Imported source file changed')
            if kind == 'review' and json.loads(path.read_text(encoding='utf-8')) != row['review']:
                raise ValueError('Imported review differs from source')
    memberships = conn.execute('''SELECT p.device,COALESCE(m.review_kind,m.algorithm_status) AS kind,
        r.source_room_id FROM point_room_memberships m JOIN points p ON p.id=m.point_id
        LEFT JOIN rooms r ON r.id=CASE WHEN m.review_kind IS NULL THEN m.algorithm_room_id ELSE m.reviewed_room_id END
        WHERE m.scene_id=%s AND m.layout_version_id=%s''', (row['scene_id'], plan.layout_version_id)).fetchall()
    interior = sorted(m['device'] for m in memberships if m['source_room_id'] == plan.room_id and m['kind'] == 'interior')
    if interior != list(plan.interior_devices):
        raise ValueError('Database and asset interior memberships differ')
    special = {m['device']: m for m in memberships if m['device'] in (22, 32, 42)}
    if (len(special) != 3 or (special[22]['kind'], special[22]['source_room_id']) != ('interior', plan.room_id)
            or (special[32]['kind'], special[32]['source_room_id']) != ('doorway', plan.room_id)
            or (special[42]['kind'], special[42]['source_room_id']) != ('outside', None)):
        raise ValueError('Required human point associations differ')
    ignition = conn.execute('SELECT id FROM points WHERE scene_id=%s AND device=22', (row['scene_id'],)).fetchone()
    if not ignition:
        raise ValueError('Ignition point missing')
    return {'scene_id': row['scene_id'], 'room_id': row['room_id'], 'ignition_point_id': ignition['id']}


def existing_job(conn, plan: RegistrationPlan, identity: dict) -> dict | None:
    rows = conn.execute("SELECT id,room_id,layout_version_id,ignition_point_id,config FROM render_jobs WHERE scene_id=%s AND config->>'file_job_id'=%s",
                        (identity['scene_id'], plan.file_job_id)).fetchall()
    if len(rows) > 1:
        raise ValueError('Duplicate file job identity; manual repair required')
    if rows:
        row = rows[0]
        if (row['room_id'] != identity['room_id'] or row['layout_version_id'] != plan.layout_version_id
                or row['ignition_point_id'] != identity['ignition_point_id']
                or row['config'].get('snapshot_signature') != plan.signature
                or row['config'].get('asset_version') != plan.asset_version
                or row['config'].get('video', plan.video) != plan.video):
            raise ValueError('Existing task identity differs; refusing overwrite')
        return row
    return None


def no_asset_conflicts(conn, plan: RegistrationPlan, identity: dict) -> None:
    for file in plan.files:
        rows = conn.execute('SELECT sha256,size_bytes,room_id,kind,bucket,object_key FROM assets WHERE scene_id=%s AND local_relative_path=%s',
                            (identity['scene_id'], file.relative)).fetchall()
        for row in rows:
            if (row['sha256'] != file.sha256 or row['size_bytes'] != file.size
                    or row['room_id'] not in (None, identity['room_id'])
                    or row['kind'] != file.kind or (row['bucket'], row['object_key']) not in ((None, None), (file.bucket, file.key))):
                raise ValueError('Existing asset identity differs; refusing reassignment')


@traced('catalog.register', 'database_preflight')
def preflight(plan: RegistrationPlan) -> None:
    with connect() as conn:
        conn.execute('SELECT pg_advisory_xact_lock(hashtext(%s))', (plan.scene.name,))
        identity = binding(conn, plan)
        existing_job(conn, plan, identity)
        no_asset_conflicts(conn, plan, identity)


@traced('catalog.register', 'database_registration')
def register(plan: RegistrationPlan) -> dict:
    from psycopg.types.json import Jsonb
    verify_unchanged(plan)
    with connect() as conn:
        conn.execute('SELECT pg_advisory_xact_lock(hashtext(%s))', (plan.scene.name,))
        identity = binding(conn, plan)
        old = existing_job(conn, plan, identity)
        no_asset_conflicts(conn, plan, identity)
        metadata = {'registration_schema_version': 1, 'file_job_id': plan.file_job_id,
                    'asset_version': plan.asset_version, 'snapshot_signature': plan.signature,
                    'runtime_state': 'awaiting_visual_review', 'human_acceptance': 'not_recorded',
                    'video': plan.video}
        if old:
            job_id = old['id']
            conn.execute("UPDATE render_jobs SET status='done',synced_at=now() WHERE id=%s", (job_id,))
        else:
            job_id = conn.execute('''INSERT INTO render_jobs(scene_id,layout_version_id,room_id,ignition_point_id,config,status,source)
                VALUES (%s,%s,%s,%s,%s,'done','file_snapshot') RETURNING id''',
                (identity['scene_id'], plan.layout_version_id, identity['room_id'], identity['ignition_point_id'], Jsonb(metadata))).fetchone()['id']
        asset_ids = []
        for file in plan.files:
            asset_id = conn.execute('''INSERT INTO assets(scene_id,room_id,kind,sha256,size_bytes,local_relative_path,bucket,object_key)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(scene_id,local_relative_path,sha256)
                DO UPDATE SET room_id=COALESCE(assets.room_id,EXCLUDED.room_id),bucket=EXCLUDED.bucket,object_key=EXCLUDED.object_key RETURNING id''',
                (identity['scene_id'], identity['room_id'], file.kind, file.sha256, file.size, file.relative, file.bucket, file.key)).fetchone()['id']
            if file.role is not None:
                conn.execute('INSERT INTO render_job_assets(scene_id,job_id,asset_id,role) VALUES (%s,%s,%s,%s) ON CONFLICT DO NOTHING',
                             (identity['scene_id'], job_id, asset_id, file.role))
            asset_ids.append(asset_id)
    return {'database_job_id': job_id, 'database_room_id': identity['room_id'],
            'asset_ids': asset_ids, 'reused_job': old is not None, 'registration_status': 'registered'}
