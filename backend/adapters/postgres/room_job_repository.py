"""Registered-source lookup and best-effort task summaries; no schema changes."""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

from backend.adapters.postgres.database import connect
from backend.adapters.postgres.room_asset_repository import binding
from backend.services.room_registration import inside, token
from render_engine.jobs.operation_logging import traced
from render_engine.jobs.room_animation_job import digest


class CatalogUnavailable(Exception):
    """Connection configuration/unavailability, without exposing its details."""


def catalog_connection():
    try:
        return connect()
    except Exception:
        raise CatalogUnavailable('Catalog connection unavailable') from None


@dataclass(frozen=True)
class RoomSource:
    scene: Path
    room_id: str
    asset_version: str
    layout_version_id: int
    provenance: dict
    interior_devices: tuple[int, ...]
    identity: dict
    reference: Path

    @property
    def asset(self) -> Path:
        return self.scene/'rooms'/self.room_id/self.asset_version/'asset'


@traced('room.api', 'registered_sources')
def sources() -> dict:
    with catalog_connection() as conn:
        rows = conn.execute('''SELECT s.scene_code,r.source_room_id AS room_id,r.id AS database_room_id,
            l.id AS layout_version_id,a.id AS blend_asset_id,a.local_relative_path
            FROM scenes s JOIN layout_versions l ON l.scene_id=s.id JOIN rooms r ON r.layout_version_id=l.id
            JOIN assets a ON a.room_id=r.id AND a.scene_id=s.id
            WHERE l.xy_verified AND r.is_valid AND r.source_room_id='Room8'
              AND a.kind='room_blend' AND a.bucket IS NOT NULL
            ORDER BY s.scene_code,l.id DESC,a.id DESC LIMIT 101''').fetchall()
    result = []
    for row in rows[:100]:
        parts = row.pop('local_relative_path').split('/')
        if len(parts) != 5 or parts[:2] != ['rooms', 'Room8'] or parts[3:] != ['asset', 'room.blend']:
            raise ValueError('Registered source path is invalid')
        result.append({**row, 'asset_version': token(parts[2]), 'style_preset': 'r3'})
    return {'sources': result, 'truncated': len(rows) > 100}


@traced('room.api', 'resolve_source')
def resolve(data_root: Path, scene_code: str, asset_version: str, layout_id: int) -> RoomSource:
    expected_scene = data_root.resolve()/token(scene_code)
    scene = expected_scene.resolve(strict=True)
    if scene != expected_scene:
        raise ValueError('Scene escapes data root')
    version = token(asset_version)
    relative = f'rooms/Room8/{version}/asset/room.blend'
    if (scene/relative).parent.resolve() != (scene/relative).parent:
        raise ValueError('Asset namespace contains a symbolic link')
    with catalog_connection() as conn:
        rows = conn.execute('''SELECT a.sha256,a.size_bytes,a.bucket,a.object_key FROM assets a
            JOIN rooms r ON r.id=a.room_id AND r.scene_id=a.scene_id
            JOIN scenes s ON s.id=r.scene_id JOIN layout_versions l ON l.id=r.layout_version_id
            WHERE s.scene_code=%s AND l.id=%s AND l.xy_verified AND r.is_valid
              AND r.source_room_id='Room8' AND a.kind='room_blend' AND a.local_relative_path=%s''',
            (scene_code, layout_id, relative)).fetchall()
        if not rows:
            raise LookupError('Registered source not found')
        if len(rows) != 1:
            raise ValueError('Ambiguous registered source')
        row = rows[0]
        path = inside(scene, scene/relative)
        if (row['bucket'] != 'burnroom-room-assets' or row['object_key'] != f'scenes/{scene_code}/rooms/Room8/assets/{version}/room.blend'
                or row['sha256'] != digest(path) or row['size_bytes'] != path.stat().st_size):
            raise ValueError('Registered source differs from local asset')
        manifest = json.loads(inside(scene, path.parent/'manifest.json').read_text(encoding='utf-8'))
        if (manifest['scene_code'], manifest['room_id']) != (scene_code, 'Room8'):
            raise ValueError('Base asset identity differs')
        source = RoomSource(scene, 'Room8', version, layout_id, manifest['provenance'],
                            tuple(sorted(manifest['interior_devices'])), {}, Path())
        identity = binding(conn, source)
        published = conn.execute('''SELECT j.config FROM render_jobs j WHERE j.scene_id=%s AND j.room_id=%s
            AND j.layout_version_id=%s AND j.status='done' AND j.config->>'asset_version'=%s
            AND j.config->>'registration_schema_version'='1' ORDER BY j.id LIMIT 1''',
            (identity['scene_id'], identity['room_id'], layout_id, version)).fetchone()
        if not published:
            raise ValueError('Published R3 reference required')
        source_job = scene/'rooms/Room8/render_jobs'/token(published['config']['file_job_id'])
        snapshot = json.loads(inside(scene, source_job/'config_snapshot.json').read_text(encoding='utf-8'))
        reference = inside(scene, Path(snapshot['inputs']['camera_reference']['manifest']))
        if not reference.is_relative_to(path.parent.parent/'style_round3'):
            raise ValueError('R3 reference is outside the registered asset version')
        return RoomSource(scene, 'Room8', version, layout_id, source.provenance,
                          source.interior_devices, identity, reference)


@traced('room.api', 'create_summary')
def create_summary(source: RoomSource, job: Path, spec: dict) -> int:
    from psycopg.types.json import Jsonb
    metadata = {'file_job_id': job.name, 'asset_version': source.asset_version,
                'snapshot_signature': spec['signature'], 'runtime_state': 'created',
                'human_acceptance': 'not_recorded', 'preset': spec['animation']['preset'],
                'camera_mode': spec['animation']['camera_mode'], 'style_preset': 'r3'}
    with catalog_connection() as conn:
        conn.execute('SELECT pg_advisory_xact_lock(hashtext(%s))', (source.scene.name,))
        identity = binding(conn, source)
        if conn.execute("SELECT id FROM render_jobs WHERE scene_id=%s AND config->>'file_job_id'=%s",
                        (identity['scene_id'], job.name)).fetchone():
            raise ValueError('Duplicate file job identity')
        return conn.execute('''INSERT INTO render_jobs(scene_id,layout_version_id,room_id,ignition_point_id,config,status,source)
            VALUES (%s,%s,%s,%s,%s,'running','api_submission') RETURNING id''',
            (identity['scene_id'], source.layout_version_id, identity['room_id'], identity['ignition_point_id'], Jsonb(metadata))).fetchone()['id']


@traced('room.api', 'sync_summary')
def sync(scene_code: str, job_id: str, signature: str, state: str) -> None:
    from psycopg.types.json import Jsonb
    mapped = 'done' if state == 'awaiting_visual_review' else 'failed' if state in ('failed', 'interrupted') else 'running'
    with catalog_connection() as conn:
        conn.execute('SELECT pg_advisory_xact_lock(hashtext(%s))', (scene_code,))
        conn.execute('''UPDATE render_jobs j SET status=%s,config=j.config || %s,synced_at=now()
            FROM scenes s WHERE j.scene_id=s.id AND s.scene_code=%s
              AND j.config->>'file_job_id'=%s AND j.config->>'snapshot_signature'=%s''',
            (mapped, Jsonb({'runtime_state': state}), scene_code, job_id, signature))
