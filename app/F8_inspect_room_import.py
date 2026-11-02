"""【F8-A｜前置检查，已通过】原始完整模型的 Blender 导入核验。

输入 inspection.json；检查导入坐标、UV、材质和贴图；输出 blender_import.json。
不裁切、不保存房间模型、不渲染图片或视频。源资产未变时不必重复运行。
当前要生成房间与三张检查图，应运行 F8_prepare_room_asset.py（F8-B）。
仅供远端 Blender 独立执行，不可由业务模块 import；脚本索引见 app/README.md。

Run remotely: blender --background --factory-startup --python this_file -- --report inspection.json
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import sys
import uuid

import bpy
from mathutils.kdtree import KDTree


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description='Read-only Blender import/UV audit; no rendering')
    parser.add_argument('--report', required=True, type=Path)
    parser.add_argument('--data-root', default=Path('/app/data'), type=Path)
    args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:])
    report = json.loads(args.report.read_text(encoding='utf-8'))
    scene_dir = (args.data_root / report['scene_code']).resolve()
    if scene_dir.parent != args.data_root.resolve():
        raise ValueError('Invalid scene path')
    mesh_path = scene_dir / 'mesh.obj'
    if digest(mesh_path) != report['source_mesh_sha256']:
        raise ValueError('Remote OBJ differs from inspected local input')
    guarded = {mesh_path: digest(mesh_path)}
    for name, key in (('points.json', 'source_points_sha256'), ('timeline.json', 'source_timeline_sha256')):
        path = scene_dir / name
        if digest(path) != report[key]:
            raise ValueError('Remote points/timeline differs from local inspection')
    for item in report['materials']['libraries']:
        path = (scene_dir / item['path']).resolve()
        if not path.is_relative_to(scene_dir) or digest(path) != item['sha256']:
            raise ValueError('Material library differs')
        guarded[path] = item['sha256']
    for name, item in report['materials']['textures'].items():
        path = (scene_dir / name).resolve()
        if not path.is_relative_to(scene_dir) or digest(path) != item['sha256']:
            raise ValueError('Texture differs')
        guarded[path] = item['sha256']
    for name in ('points.json', 'timeline.json', 'output.mp4'):
        path = scene_dir / name
        if path.is_file():
            guarded[path] = digest(path)
    raw_vertices = []
    raw_uvs = []
    for line in mesh_path.read_text(encoding='utf-8-sig').splitlines():
        parts = line.split()
        if parts and parts[0] == 'v':
            raw_vertices.append(tuple(float(v) for v in parts[1:4]))
        elif parts and parts[0] == 'vt':
            raw_uvs.append(tuple(float(v) for v in parts[1:3]))

    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    bpy.ops.wm.obj_import(filepath=str(mesh_path), up_axis='Z', forward_axis='Y')
    objects = [obj for obj in bpy.data.objects if obj.type == 'MESH']
    world_vertices = [obj.matrix_world @ vertex.co for obj in objects for vertex in obj.data.vertices]
    if not world_vertices:
        raise ValueError('No imported mesh')
    tree = KDTree(len(world_vertices))
    for i, point in enumerate(world_vertices):
        tree.insert(point, i)
    tree.balance()
    sampled = raw_vertices[::max(1, math.ceil(len(raw_vertices) / 1000))]
    max_error = max(tree.find(point)[2] for point in sampled)
    bounds = {'min': [min(v[k] for v in world_vertices) for k in range(3)],
              'max': [max(v[k] for v in world_vertices) for k in range(3)]}
    bounds_error = max(abs(bounds[side][i] - report['coordinates']['raw_bounds'][side][i])
                       for side in ('min', 'max') for i in range(3))
    face_count = sum(len(obj.data.polygons) for obj in objects)
    uv_values = [tuple(value.uv) for obj in objects if obj.data.uv_layers.active
                 for value in obj.data.uv_layers.active.data]
    uv_finite = all(math.isfinite(v) for uv in uv_values for v in uv)
    uv_error = None
    if uv_values and raw_uvs:
        uv_tree = KDTree(len(uv_values))
        for i, point in enumerate(uv_values):
            uv_tree.insert((*point, 0.0), i)
        uv_tree.balance()
        uv_error = max(uv_tree.find((*point, 0.0))[2] for point in raw_uvs[::max(1, math.ceil(len(raw_uvs) / 1000))])
    expected_materials = {name for name in report['materials']['faces_per_material'] if name != 'None'}
    actual_materials = {mat.name for obj in objects for mat in obj.data.materials if mat}
    loaded_images = {Path(bpy.path.abspath(image.filepath)).resolve() for image in bpy.data.images if image.source == 'FILE'}
    expected_images = {(scene_dir / name).resolve() for name in report['materials']['textures']}
    checks = {
        'world_coordinates_match_raw': max_error <= 2e-5 and bounds_error <= 2e-5,
        'face_count_matches': face_count == report['geometry']['faces'],
        'uv_loop_count_matches': len(uv_values) == report['materials']['uv_corner_count'],
        'uv_finite': uv_finite,
        'sampled_uv_coordinates_match': uv_error is not None and uv_error <= 2e-5,
        'material_names_present': expected_materials <= actual_materials,
        'referenced_images_loaded': expected_images <= loaded_images,
        'source_and_history_unchanged': all(digest(path) == value for path, value in guarded.items()),
    }
    output = scene_dir / 'diagnostics/room_blender_inspection' / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '_' + uuid.uuid4().hex[:8])
    output.mkdir(parents=True, exist_ok=False)
    result = {'status': 'passed' if all(checks.values()) else 'failed', 'checks': checks,
              'blender_version': bpy.app.version_string, 'scene_code': report['scene_code'], 'room_id': report['room_id'],
              'source_mesh_sha256': report['source_mesh_sha256'], 'inspection_sha256': digest(args.report),
              'max_sampled_vertex_error_m': max_error, 'bounds_error_m': bounds_error,
              'bounds_world': bounds, 'object_count': len(objects), 'face_count': face_count,
              'uv_loop_count': len(uv_values), 'max_sampled_uv_error': uv_error,
              'object_matrices': {obj.name: [list(row) for row in obj.matrix_world] for obj in objects},
              'ready_for_cut': False, 'note': 'Import check only; floor/ceiling and wall thickness still require review.'}
    (output / 'blender_import.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print('[room-import-check] ' + json.dumps(result), flush=True)
    print(f'[room-import-check] report={output / "blender_import.json"}', flush=True)
    if not all(checks.values()):
        raise RuntimeError('Import checks failed; do not cut')


if __name__ == '__main__':
    main()
