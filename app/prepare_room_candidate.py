"""Prepare an isolated approximate room candidate. No bpy/DB/network/rendering.

PRD 2.2 (2026-11-02): explicit flat-floor approximation supersedes the old
physical-semantic gate; the original inspection and human XY review stay intact.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import uuid

from app.room_source_io import sha256
from app.room_source_inputs import load_inputs
from app.room_clip_geometry import clip_mesh


def prepare(data_root: Path, inspection: Path, blender_report: Path, alignment_dir: Path,
            floor_z: float, accept_approximation: bool) -> Path:
    if not accept_approximation or not math.isfinite(floor_z):
        raise ValueError('Explicit --accept-flat-floor and finite --floor-z required')
    audit, alignment, mesh, context = load_inputs(data_root, inspection, blender_report, alignment_dir)
    scene = context['scene']
    geometry = clip_mesh(mesh, audit['room_polygon_raw_xy'])
    review = json.loads((alignment_dir/'review.json').read_text(encoding='utf-8'))
    interior, boundary = [], []
    for row in alignment['memberships_provisional']:
        verdict = review.get('points', {}).get(str(row['device']), {})
        room = verdict.get('room_id', row.get('room_id'))
        kind = verdict.get('kind', row['status'])
        if room == audit['room_id']:
            if kind == 'interior':
                interior.append(row['device'])
            elif kind in ('doorway', 'boundary'):
                boundary.append(row['device'])
    points = json.loads((scene/'points.json').read_text(encoding='utf-8'))
    timeline = json.loads((scene/'timeline.json').read_text(encoding='utf-8'))
    if int(timeline['start_point']) not in interior:
        raise ValueError('Ignition is not an interior point of the selected reviewed room')
    lower = audit['height_profile']['bottom_clusters']
    payload = {'schema_version': 1, 'scene_code': audit['scene_code'], 'room_id': audit['room_id'],
        'ready_for_cut': True, 'readiness_basis': 'explicitly accepted engineering approximation, not building semantics',
        'physical_semantics_verified': False, 'floor_z': floor_z,
        'floor_policy': 'flat demonstration floor; dominant lower-envelope reference; not certified physical floor',
        'dominant_lower_envelope_candidate': lower[0] if lower else None,
        'source_z_modified': False, 'raw_to_asset_matrix': [[1,0,0,0],[0,1,0,0],[0,0,1,0],[0,0,0,1]],
        'raw_to_floor_xy': audit['coordinates']['raw_to_floor_xy'],
        'polygon_raw_xy': audit['room_polygon_raw_xy'], 'geometry': geometry,
        'materials': audit['materials'], 'interior_devices': sorted(interior), 'boundary_devices': sorted(boundary),
        'points': [p for p in points if int(p['device']) in interior+boundary],
        'ignition_device': int(timeline['start_point']),
        'point_height_policy': 'camera poses preserved; future fire bases use floor_z, never camera lens Z',
        'provenance': {'inspection_sha256': sha256(inspection), 'blender_report_sha256': sha256(blender_report),
            'alignment_sha256': sha256(alignment_dir/'alignment_report.json'), 'review_sha256': sha256(alignment_dir/'review.json'),
            'blender_report_provenance': context['evidence_provenance']},
        'source_fingerprints': {str(p.relative_to(scene)).replace('\\','/'): h
            for p,h in context['guarded'].items() if p.is_relative_to(scene) and
            (p.parent == scene or str(p.relative_to(scene)).replace('\\','/') in
             set(audit['materials']['textures']) | {m['path'] for m in audit['materials']['libraries']})},
        'next_gate': 'save room.blend / room.glb; reopen and check; inspect top/oblique/interior PNGs before effects',
        'wall_policy': 'strict XY polygon; zero outward buffer; no vertical trim on base; open cut edges permitted',
        'database_accessed': False, 'video_rendered': False}
    output = scene/'rooms'/audit['room_id']/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_'+uuid.uuid4().hex[:8])
    output.mkdir(parents=True, exist_ok=False)
    for p,h in context['guarded'].items():
        if sha256(p) != h:
            raise ValueError('Source changed during preparation')
    (output/'candidate.json').write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description='Prepare isolated room candidate; no Blender or video')
    parser.add_argument('--data-root', type=Path, default=Path('data'))
    parser.add_argument('--inspection', type=Path, required=True)
    parser.add_argument('--blender-report', type=Path, required=True)
    parser.add_argument('--alignment-dir', type=Path, required=True)
    parser.add_argument('--floor-z', type=float, required=True)
    parser.add_argument('--accept-flat-floor', action='store_true')
    args = parser.parse_args()
    output = prepare(args.data_root, args.inspection, args.blender_report, args.alignment_dir,
                     args.floor_z, args.accept_flat_floor)
    print(f'[room-candidate] candidate={output / "candidate.json"}', flush=True)


if __name__ == '__main__':
    main()
