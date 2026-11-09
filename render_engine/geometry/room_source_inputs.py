"""Validate reviewed room inputs without importing diagnostic entrypoints.

PRD engineering baseline / architecture file-contract boundary. This preserves
existing fingerprint, human-review and Blender-import checks without deciding
floor heights, cutting meshes, writing files or importing backend/database code.
"""
from __future__ import annotations

import json
from pathlib import Path
import re

from render_engine.geometry.room_source_io import confined, inverse_xy, materials, read_obj, sha256


REQUIRED_CHECKS = ('world_coordinates_match_raw','face_count_matches','uv_loop_count_matches',
                   'uv_finite','sampled_uv_coordinates_match','material_names_present',
                   'referenced_images_loaded','source_and_history_unchanged')


def load_inputs(data_root: Path, inspection_path: Path, blender_path: Path, alignment_dir: Path) -> tuple[dict,dict,dict,dict]:
    inspection = json.loads(inspection_path.read_text(encoding='utf-8'))
    scene_code = inspection['scene_code']
    if not re.fullmatch(r'[A-Za-z0-9_-]+',scene_code):
        raise ValueError('Invalid scene code')
    scene = (data_root/scene_code).resolve()
    if scene.parent != data_root.resolve():
        raise ValueError('Invalid scene directory')
    alignment_path = alignment_dir/'alignment_report.json'; review_path=alignment_dir/'review.json'
    guarded = {inspection_path:sha256(inspection_path),blender_path:sha256(blender_path)}
    for path,key in ((scene/'mesh.obj','source_mesh_sha256'),(scene/'points.json','source_points_sha256'),
                     (scene/'timeline.json','source_timeline_sha256'),(alignment_path,'source_report_sha256'),
                     (review_path,'source_review_sha256')):
        actual=sha256(path)
        if actual != inspection[key]:
            raise ValueError('Input fingerprint changed: '+path.name)
        guarded[path]=actual
    review=json.loads(review_path.read_text(encoding='utf-8'))
    alignment=json.loads(alignment_path.read_text(encoding='utf-8'))
    if review.get('scene_code') != scene_code or alignment.get('scene_code') != scene_code:
        raise ValueError('Alignment/review scene mismatch')
    if inspection['coordinates']['raw_to_floor_xy'] != alignment['selected_transform']['matrix']:
        raise ValueError('Inspection transform differs from reviewed alignment')
    if review.get('xy_verified') is not True or review.get('alignment_report_sha256') != sha256(alignment_path):
        raise ValueError('Bound human XY review required')
    room=next((r for r in alignment['rooms'] if r['room_id']==inspection['room_id']),None)
    if not room or not room['valid_candidate'] or room != inspection['room']:
        raise ValueError('Reviewed room differs from inspection')
    expected_polygon=inverse_xy(room['polygon'],inspection['coordinates']['raw_to_floor_xy'])
    if json.loads(json.dumps(expected_polygon)) != inspection['room_polygon_raw_xy']:
        raise ValueError('Raw room polygon transform mismatch')
    envelope=json.loads(blender_path.read_text(encoding='utf-8'))
    evidence=envelope.get('result',envelope)
    if evidence.get('status') != 'passed' or any(evidence.get('checks',{}).get(k) is not True for k in REQUIRED_CHECKS):
        raise ValueError('Passed remote Blender import evidence required')
    if evidence.get('inspection_sha256') != sha256(inspection_path) or evidence.get('source_mesh_sha256') != inspection['source_mesh_sha256']:
        raise ValueError('Blender evidence is for a different input')
    if evidence.get('scene_code') != scene_code or evidence.get('room_id') != inspection['room_id']:
        raise ValueError('Blender evidence room mismatch')
    if max(abs(evidence['bounds_world'][side][k]-inspection['coordinates']['raw_bounds'][side][k])
           for side in ('min','max') for k in range(3)) > 2e-5:
        raise ValueError('Imported bounds do not match source')
    for item in inspection['materials']['libraries']:
        path=confined(scene,item['path']); guarded[path]=item['sha256']
    for name,item in inspection['materials']['textures'].items():
        path=confined(scene,name); guarded[path]=item['sha256']
    for path,digest in guarded.items():
        if sha256(path) != digest:
            raise ValueError('Material or source fingerprint changed')
    video=scene/'output.mp4'
    if video.is_file():guarded[video]=sha256(video)
    mesh=read_obj(scene/'mesh.obj')
    if not materials(scene,mesh)['ready_for_preservation']:
        raise ValueError('Material/UV preservation audit failed')
    return inspection,alignment,mesh,{'scene':scene,'guarded':guarded,'evidence':evidence,
                                     'evidence_provenance':envelope.get('provenance','provided remote report')}
