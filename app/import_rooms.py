"""Preview/import an explicit alignment report; no rendering, no secret output."""
from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
from typing import Any

from app.analyze_floorplan import analyze, resolve_source, sha256


def build_plan(scene_dir: Path, probe_dir: Path, alignment_dir: Path, review_file: Path | None) -> dict:
    report_path = alignment_dir / 'alignment_report.json'
    report = json.loads(report_path.read_text(encoding='utf-8'))
    if report['scene_code'] != scene_dir.name:
        raise ValueError('Alignment scene mismatch')
    source, _ = resolve_source(probe_dir, scene_dir.name)
    paths = {'floorplan': source, 'probe_report': probe_dir / 'report.json',
             'points': scene_dir / 'points.json', 'mesh': scene_dir / 'mesh.obj',
             'timeline': scene_dir / 'timeline.json'}
    for name, path in paths.items():
        if sha256(path) != report['inputs'][name]['sha256']:
            raise ValueError(f'Input changed: {name}; rerun alignment')
    fresh, _ = analyze(scene_dir, probe_dir, report['floor_index'], report['selected_transform']['id'])
    for key in ('rooms', 'memberships_provisional', 'selected_transform'):
        # JSON roundtrip normalizes tuples/lists from the analyzer.
        if json.loads(json.dumps(fresh[key])) != report[key]:
            raise ValueError(f'Alignment report differs from recomputed {key}')
    review = json.loads(review_file.read_text(encoding='utf-8')) if review_file else {}
    room_map = {r['room_id']: r for r in report['rooms']}
    memberships = {str(r['device']): r for r in report['memberships_provisional']}
    if review:
        if review.get('scene_code') != scene_dir.name or review.get('alignment_report_sha256') != sha256(report_path):
            raise ValueError('Review is not bound to this scene/report')
        if not review.get('reviewed_by') or not review.get('notes'):
            raise ValueError('Review requires author and notes')
        datetime.fromisoformat(review['reviewed_at'].replace('Z', '+00:00'))
        if not isinstance(review.get('xy_verified'), bool):
            raise ValueError('xy_verified must be boolean')
        for device, verdict in review.get('points', {}).items():
            if device not in memberships:
                raise ValueError('Review contains unknown point')
            kind, room_id = verdict.get('kind'), verdict.get('room_id')
            if kind not in ('interior', 'doorway', 'outside', 'unassigned'):
                raise ValueError('Invalid review kind')
            if kind in ('interior', 'doorway'):
                if not room_id or room_id not in room_map or not room_map[room_id]['valid_candidate']:
                    raise ValueError('Review must reference a valid room')
            elif room_id is not None:
                raise ValueError('Outside/unassigned points cannot have a room')
    identity = {'inputs': {k: sha256(v) for k, v in paths.items() if k != 'probe_report'},
                'transform': report['selected_transform']['matrix'], 'rooms': report['rooms'],
                'memberships': report['memberships_provisional'], 'thresholds': report['thresholds_m'],
                'review': review}
    fingerprint = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
    raw_points = json.loads(paths['points'].read_text(encoding='utf-8'))
    files = [(path, kind, None) for kind, path in paths.items()]
    files += [(report_path, 'alignment_report', None)]
    if review_file:
        files.append((review_file, 'review', None))
    files += [(scene_dir / f'{p["device"]}.jpg', 'panorama', int(p['device'])) for p in raw_points]
    assets = []
    for path, kind, device in files:
        if not path.is_file():
            if kind == 'panorama':
                continue
            raise ValueError('Missing input asset')
        resolved = path.resolve()
        if not resolved.is_relative_to(scene_dir.resolve()):
            raise ValueError('Import files must be inside this private scene directory')
        assets.append({'kind': kind, 'device': device, 'path': path,
                       'relative': resolved.relative_to(scene_dir.resolve()).as_posix(),
                       'sha256': sha256(path), 'size': path.stat().st_size})
    return {'scene_code': scene_dir.name, 'fingerprint': fingerprint, 'report': report,
            'review': review, 'points': raw_points, 'assets': assets}


def import_plan(plan: dict, upload_assets: bool = False) -> dict:
    from app.database import connect
    from psycopg.types.json import Jsonb
    uploaded: dict[str, tuple[str, str]] = {}
    if upload_assets:
        from app.s3_io import ASSETS_BUCKET, ensure_buckets, get_minio_client
        import mimetypes
        client = get_minio_client()
        ensure_buckets(client)
        for asset in plan['assets']:
            key = f"{plan['scene_code']}/catalog/{asset['sha256']}/{asset['path'].name}"
            client.fput_object(ASSETS_BUCKET, key, str(asset['path']),
                               content_type=mimetypes.guess_type(asset['path'].name)[0] or 'application/octet-stream')
            uploaded[asset['relative']] = (ASSETS_BUCKET, key)
    with connect() as conn:
        conn.execute('SELECT pg_advisory_xact_lock(hashtext(%s))', (plan['scene_code'],))
        scene_id = conn.execute('INSERT INTO scenes(scene_code,name) VALUES (%s,%s) ON CONFLICT(scene_code) DO UPDATE SET scene_code=EXCLUDED.scene_code RETURNING id',
                                (plan['scene_code'], plan['scene_code'])).fetchone()['id']
        existing = conn.execute('SELECT id FROM layout_versions WHERE scene_id=%s AND fingerprint=%s', (scene_id, plan['fingerprint'])).fetchone()
        if existing:
            # Never overwrite stored human review, names or polygons on reimport.
            point_ids = {row['device']: row['id'] for row in conn.execute('SELECT id,device FROM points WHERE scene_id=%s', (scene_id,)).fetchall()}
            for asset in plan['assets']:
                bucket, key = uploaded.get(asset['relative'], (None, None))
                conn.execute('INSERT INTO assets(scene_id,point_id,kind,sha256,size_bytes,local_relative_path,bucket,object_key) VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(scene_id,local_relative_path,sha256) DO NOTHING',
                             (scene_id, point_ids.get(asset['device']), asset['kind'], asset['sha256'], asset['size'], asset['relative'], bucket, key))
                if asset['relative'] in uploaded:
                    conn.execute('UPDATE assets SET bucket=%s,object_key=%s WHERE scene_id=%s AND local_relative_path=%s AND sha256=%s',
                                 (bucket, key, scene_id, asset['relative'], asset['sha256']))
            return {'layout_version_id': existing['id'], 'reused': True, 'review_preserved': True}
        for point in plan['points']:
            xyz = point['pose']['translation']
            current = conn.execute('SELECT x,y,z FROM points WHERE scene_id=%s AND device=%s', (scene_id, int(point['device']))).fetchone()
            if current and any(current[k] != float(xyz[k]) for k in ('x', 'y', 'z')):
                raise ValueError('Point coordinates changed; explicit scene revision required')
        review = plan['review']
        version_id = conn.execute('INSERT INTO layout_versions(scene_id,fingerprint,transform,review,xy_verified) VALUES (%s,%s,%s,%s,%s) RETURNING id',
                                  (scene_id, plan['fingerprint'], Jsonb(plan['report']['selected_transform']), Jsonb(review), review.get('xy_verified', False))).fetchone()['id']
        room_ids = {}
        for room in plan['report']['rooms']:
            room_ids[room['room_id']] = conn.execute('INSERT INTO rooms(scene_id,layout_version_id,source_room_id,name,polygon,area_m2,is_valid,problems) VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id',
                (scene_id, version_id, room['room_id'], room['label'], Jsonb(room['polygon']), room['area_m2'], room['valid_candidate'], Jsonb(room['problems']))).fetchone()['id']
        point_ids = {}
        for point in plan['points']:
            xyz = point['pose']['translation']
            device = int(point['device'])
            point_ids[device] = conn.execute('INSERT INTO points(scene_id,device,x,y,z) VALUES (%s,%s,%s,%s,%s) ON CONFLICT(scene_id,device) DO UPDATE SET device=EXCLUDED.device RETURNING id',
                (scene_id, device, xyz['x'], xyz['y'], xyz['z'])).fetchone()['id']
        for row in plan['report']['memberships_provisional']:
            verdict = review.get('points', {}).get(str(row['device']), {})
            conn.execute('INSERT INTO point_room_memberships(scene_id,point_id,layout_version_id,algorithm_status,algorithm_room_id,reviewed_room_id,review_kind,review) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)',
                (scene_id, point_ids[row['device']], version_id, row['status'], room_ids.get(row['room_id']), room_ids.get(verdict.get('room_id')), verdict.get('kind'), Jsonb({'verdict': verdict, 'reviewed_by': review.get('reviewed_by'), 'reviewed_at': review.get('reviewed_at')} if verdict else {})))
        for asset in plan['assets']:
            bucket, key = uploaded.get(asset['relative'], (None, None))
            conn.execute('INSERT INTO assets(scene_id,point_id,kind,sha256,size_bytes,local_relative_path,bucket,object_key) VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(scene_id,local_relative_path,sha256) DO NOTHING',
                         (scene_id, point_ids.get(asset['device']), asset['kind'], asset['sha256'], asset['size'], asset['relative'], bucket, key))
    return {'layout_version_id': version_id, 'reused': False}


def main() -> int:
    parser = argparse.ArgumentParser(description='Preview/import room catalog, without rendering')
    parser.add_argument('--scene', required=True)
    parser.add_argument('--data-root', type=Path, default=Path('/app/data'))
    parser.add_argument('--probe-dir', type=Path, required=True)
    parser.add_argument('--alignment-dir', type=Path, required=True)
    parser.add_argument('--review-file', type=Path)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--upload-assets', action='store_true')
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9_-]+', args.scene):
        parser.error('Invalid scene code')
    if args.upload_assets and not args.apply:
        parser.error('--upload-assets requires --apply')
    try:
        plan = build_plan(args.data_root / args.scene, args.probe_dir, args.alignment_dir, args.review_file)
        result: dict[str, Any] = {'mode': 'apply' if args.apply else 'preview', 'scene_code': args.scene,
            'rooms': len(plan['report']['rooms']), 'points': len(plan['points']), 'assets': len(plan['assets']),
            'xy_verified': plan['review'].get('xy_verified', False)}
        if args.apply:
            result.update(import_plan(plan, args.upload_assets))
        print(json.dumps(result, ensure_ascii=False), flush=True)
        return 0
    except Exception as exc:
        print(f'[room-import] failed: {type(exc).__name__}; check inputs/configuration, no credentials printed', flush=True)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
