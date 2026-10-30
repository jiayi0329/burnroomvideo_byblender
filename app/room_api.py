"""Internal read-only catalog API. Authentication is outside this first stage."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.database import connect

router = APIRouter(prefix='/api/catalog', tags=['room catalog'])

EFFECTIVE_ROOM = 'CASE WHEN m.review_kind IS NULL THEN m.algorithm_room_id ELSE m.reviewed_room_id END'


def query(statement: str, params: tuple) -> list[dict[str, Any]]:
    try:
        with connect() as conn:
            return conn.execute(statement, params).fetchall()
    except Exception:
        raise HTTPException(503, 'Room catalog unavailable; check database migration and connection') from None


def version(scene_code: str, layout_version_id: int | None) -> dict:
    rows = query('SELECT l.id,l.xy_verified FROM layout_versions l JOIN scenes s ON s.id=l.scene_id WHERE s.scene_code=%s AND (%s::bigint IS NULL OR l.id=%s) ORDER BY l.id DESC LIMIT 1',
                 (scene_code, layout_version_id, layout_version_id))
    if not rows:
        raise HTTPException(404, 'No imported layout for this scene/version')
    return rows[0]


@router.get('/scenes/{scene_code}/rooms')
def list_rooms(scene_code: str, layout_version_id: int | None = Query(None, ge=1), include_invalid: bool = False) -> dict:
    layout = version(scene_code, layout_version_id)
    rows = query(f'''SELECT r.id,r.source_room_id,r.name,r.area_m2,r.is_valid,r.problems,
      count(m.point_id) FILTER (WHERE COALESCE(m.review_kind,m.algorithm_status)='interior') AS interior_points,
      count(m.point_id) FILTER (WHERE m.review_kind='doorway') AS doorway_points,
      count(m.point_id) AS associated_points
      FROM rooms r LEFT JOIN point_room_memberships m ON ({EFFECTIVE_ROOM})=r.id
      WHERE r.layout_version_id=%s AND (%s OR r.is_valid)
      GROUP BY r.id ORDER BY r.id''', (layout['id'], include_invalid))
    return {'layout_version_id': layout['id'], 'xy_verified': layout['xy_verified'], 'rooms': rows}


def require_room(room_id: int) -> None:
    if not query('SELECT id FROM rooms WHERE id=%s', (room_id,)):
        raise HTTPException(404, 'Room not found')


@router.get('/rooms/{room_id}/points')
def list_points(room_id: int) -> dict:
    require_room(room_id)
    rows = query(f'''SELECT p.device,p.x,p.y,p.z,m.algorithm_status,m.review_kind,m.review
      FROM point_room_memberships m JOIN points p ON p.id=m.point_id
      WHERE ({EFFECTIVE_ROOM})=%s ORDER BY p.device''', (room_id,))
    return {'room_id': room_id, 'points': rows}


@router.get('/rooms/{room_id}/assets')
def list_assets(room_id: int, limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0)) -> dict:
    require_room(room_id)
    rows = query(f'''SELECT a.id,a.kind,a.size_bytes,a.sha256,a.bucket IS NOT NULL AS uploaded,p.device
      FROM assets a LEFT JOIN points p ON p.id=a.point_id
      WHERE a.room_id=%s OR EXISTS (SELECT 1 FROM point_room_memberships m
        WHERE m.point_id=a.point_id AND ({EFFECTIVE_ROOM})=%s)
      ORDER BY a.id LIMIT %s OFFSET %s''', (room_id, room_id, limit, offset))
    return {'room_id': room_id, 'assets': rows, 'limit': limit, 'offset': offset}


@router.get('/assets/{asset_id}/share')
def share_asset(asset_id: int) -> dict:
    rows = query('SELECT bucket,object_key FROM assets WHERE id=%s', (asset_id,))
    if not rows:
        raise HTTPException(404, 'Asset not found')
    if not rows[0]['bucket']:
        raise HTTPException(409, 'Asset is catalogued locally; upload before sharing')
    from datetime import timedelta
    from app.s3_io import get_public_minio_client
    try:
        client = get_public_minio_client()
        url = client.presigned_get_object(rows[0]['bucket'], rows[0]['object_key'], expires=timedelta(days=7))
    except Exception:
        raise HTTPException(502, 'Asset link unavailable; check MinIO configuration') from None
    return {'url': url, 'expires_in_seconds': 604800}
