"""【F8-B｜当前运行】独立房间资产生成 + 重载核验 + 三张静态检查图。

输入：prepare_room_candidate.py 生成的 candidate.json；远端原始 OBJ/MTL/贴图。
输出：独立 asset/ 下 room.blend、room.glb、validation.json、manifest.json，
      以及 top.png / oblique.png / interior.png、section_preview.blend。
Room8 当前参考地板 -1.35m；工程近似，不代表真实建筑语义确认。
先保存并重载基础房间，再派生去顶展示；不改写源模型、核验文件或历史视频。
只渲染 3 张静态 PNG，不接入火灾效果，不生成 313 帧动画。

仅由远端 Blender 4.2 自带 Python 执行，不可由业务模块 import。
命令见 docs/room_candidate.md；另两个 F8 脚本的用途见 app/README.md。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import sys

import bpy


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            h.update(block)
    return h.hexdigest()


def dump(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def packed_image_hashes() -> set[str]:
    return {hashlib.sha256(bytes(image.packed_file.data)).hexdigest()
            for image in bpy.data.images if image.packed_file and image.size[0]>0}


def verify_point_mapping(payload: dict, source_points: list) -> None:
    """Validate memberships and unchanged camera coordinates against the source."""
    source = {int(p['device']): p for p in source_points}
    if len(source) != len(source_points):
        raise ValueError('Duplicate device in source points')
    interior, boundary = set(payload['interior_devices']), set(payload['boundary_devices'])
    selected = [int(p['device']) for p in payload['points']]
    if (interior & boundary or len(selected) != len(set(selected)) or
            set(selected) != interior | boundary or payload['ignition_device'] not in interior):
        raise ValueError('Invalid point membership/ignition mapping')
    for point in payload['points']:
        device = int(point['device'])
        if device not in source or point != source[device]:
            raise ValueError('Candidate point differs from source: '+str(device))


def create_point_anchors(payload: dict) -> None:
    for point in payload['points']:
        device = int(point['device'])
        obj = bpy.data.objects.new(f'Point_{device}', None)
        bpy.context.scene.collection.objects.link(obj)
        position = point['pose']['translation']
        obj.location = tuple(position[k] for k in ('x','y','z'))
        obj['source_device'] = device
        obj['membership'] = 'interior' if device in payload['interior_devices'] else 'doorway_boundary'
        obj['fire_reference_z'] = payload['floor_z']
        obj.empty_display_size = .08


def verify_saved_point_anchors(payload: dict) -> list[dict]:
    records = []
    for point in payload['points']:
        device = int(point['device'])
        obj = bpy.data.objects.get(f'Point_{device}')
        position = point['pose']['translation']
        expected = [position[k] for k in ('x','y','z')]
        kind = 'interior' if device in payload['interior_devices'] else 'doorway_boundary'
        if (obj is None or obj.type != 'EMPTY' or obj.get('source_device') != device or
                obj.get('membership') != kind or obj.get('fire_reference_z') != payload['floor_z'] or
                max(abs(obj.matrix_world.translation[k]-expected[k]) for k in range(3)) > 2e-5):
            raise ValueError('Saved point anchor mismatch: '+str(device))
        records.append({'device':device, 'membership':kind, 'camera_raw_xyz':expected,
                        'fire_reference_xyz':[expected[0],expected[1],payload['floor_z']]})
    return records


def snapshot() -> dict:
    result = {}
    for obj in bpy.context.scene.objects:
        if obj.type != 'MESH':
            continue
        mesh = obj.data
        if not mesh.uv_layers.active:
            raise ValueError('Mesh UV missing: '+obj.name)
        values = {'vertices': [list(v.co) for v in mesh.vertices],
            'faces': [list(p.vertices) for p in mesh.polygons],
            'uvs': [list(v.uv) for v in mesh.uv_layers.active.data],
            'material_indices': [p.material_index for p in mesh.polygons],
            'materials': [m.name for m in mesh.materials],
            'matrix': [list(row) for row in obj.matrix_world]}
        if not all(math.isfinite(x) for point in values['vertices']+values['uvs'] for x in point):
            raise ValueError('Nonfinite geometry/UV')
        result[obj.name] = {'sha256': hashlib.sha256(json.dumps(values, sort_keys=True).encode()).hexdigest(),
                            'triangles': len(mesh.polygons), 'uv_loops': len(values['uvs'])}
    return result


def make_mesh(name: str, faces: list[dict], materials: dict) -> bpy.types.Object:
    mesh = bpy.data.meshes.new(name)
    corners = [v for face in faces for v in face['corners']]
    mesh.from_pydata([v[:3] for v in corners], [], [(i,i+1,i+2) for i in range(0,len(corners),3)])
    uv = mesh.uv_layers.new(name='UVMap')
    for loop in mesh.loops:
        uv.data[loop.index].uv = corners[loop.vertex_index][3:5]
    names = sorted({face['material'] for face in faces})
    for mat in names:
        mesh.materials.append(materials[mat])
    for p, face in zip(mesh.polygons, faces):
        p.material_index = names.index(face['material'])
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def below(faces: list[dict], z: float) -> list[dict]:
    """Display derivative only: clip faces below an explicitly artificial view plane."""
    output = []
    for face in faces:
        result = []
        previous = face['corners'][-1]
        for current in face['corners']:
            if (previous[2] <= z) != (current[2] <= z):
                t = (z-previous[2])/(current[2]-previous[2])
                result.append([previous[k]+t*(current[k]-previous[k]) for k in range(5)])
            if current[2] <= z:
                result.append(current)
            previous = current
        for i in range(1,len(result)-1):
            output.append({'material': face['material'], 'corners': [result[0],result[i],result[i+1]]})
    if not output:
        raise ValueError('Display cut plane removed all source geometry')
    return output


def contains(x: float, y: float, polygon: list) -> bool:
    inside = False
    for i,a in enumerate(polygon):
        b = polygon[(i+1)%len(polygon)]
        if (a[1]>y) != (b[1]>y) and x < (b[0]-a[0])*(y-a[1])/(b[1]-a[1])+a[0]:
            inside = not inside
    return inside


def interior_camera(polygon: list) -> tuple[float,float]:
    lo = [min(v[k] for v in polygon) for k in (0,1)]
    hi = [max(v[k] for v in polygon) for k in (0,1)]
    candidates = []
    for ix in range(1,30):
        for iy in range(1,30):
            p = [lo[0]+(hi[0]-lo[0])*ix/30,lo[1]+(hi[1]-lo[1])*iy/30]
            if not contains(*p, polygon):
                continue
            distances = []
            for i,a in enumerate(polygon):
                b = polygon[(i+1)%len(polygon)]
                length2 = sum((b[k]-a[k])**2 for k in (0,1))
                t = max(0,min(1,sum((p[k]-a[k])*(b[k]-a[k]) for k in (0,1))/length2))
                distances.append(math.dist(p,[a[k]+t*(b[k]-a[k]) for k in (0,1)]))
            candidates.append((min(distances), p))
    if not candidates:
        raise ValueError('No interior camera candidate')
    return tuple(max(candidates)[1])


def preview(output: Path, payload: dict, materials: dict, cut_z: float) -> dict:
    base = bpy.data.objects['RoomSource']
    base.hide_render = True
    base.hide_viewport = True
    make_mesh('SectionDisplay', below(payload['geometry']['faces'], cut_z), materials)
    scene = bpy.context.scene
    scene.render.engine = 'BLENDER_EEVEE_NEXT'
    scene.render.resolution_x, scene.render.resolution_y = 800, 600
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = 'PNG'
    scene.world = bpy.data.worlds.new('InspectionWorld')
    scene.world.use_nodes = True
    scene.world.node_tree.nodes['Background'].inputs['Color'].default_value = (.15,.15,.15,1)
    scene.world.node_tree.nodes['Background'].inputs['Strength'].default_value = .6
    light = bpy.data.lights.new('InspectionArea', 'AREA')
    light.energy, light.shape, light.size = 1200, 'DISK', 8
    lamp = bpy.data.objects.new('InspectionArea', light)
    scene.collection.objects.link(lamp)
    polygon = payload['polygon_raw_xy']
    lo = [min(v[k] for v in polygon) for k in (0,1)]
    hi = [max(v[k] for v in polygon) for k in (0,1)]
    cx, cy = [(lo[k]+hi[k])/2 for k in (0,1)]
    span = max(hi[k]-lo[k] for k in (0,1))
    floor = payload['floor_z']
    lamp.location = (cx,cy,floor+5)
    camera_data = bpy.data.cameras.new('InspectionCamera')
    camera = bpy.data.objects.new('InspectionCamera', camera_data)
    scene.collection.objects.link(camera)
    scene.camera = camera
    constraint = camera.constraints.new('TRACK_TO')
    target = bpy.data.objects.new('InspectionTarget', None)
    scene.collection.objects.link(target)
    constraint.target, constraint.track_axis, constraint.up_axis = target, 'TRACK_NEGATIVE_Z', 'UP_Y'
    ignition = next(p for p in payload['points'] if int(p['device'])==payload['ignition_device'])['pose']['translation']
    ix, iy = interior_camera(polygon)
    views = [('top', (cx,cy,floor+span*1.6), (cx,cy,floor), 'ORTHO'),
             ('oblique', (cx+span*.6,cy-span*.6,cut_z+span*.7), (cx,cy,floor+.5), 'ORTHO'),
             ('interior', (ix,iy,floor+1.6), (ignition['x'],ignition['y'],floor+.7), 'PERSP')]
    records = []
    for name, position, aim, kind in views:
        camera.location, target.location, camera_data.type = position, aim, kind
        camera_data.ortho_scale, camera_data.lens, camera_data.clip_start = span*1.3, 20, .03
        scene.render.filepath = str(output/(name+'.png'))
        bpy.ops.render.render(write_still=True)
        path = output/(name+'.png')
        if not path.is_file() or path.stat().st_size < 1000:
            raise ValueError('Preview PNG missing: '+name)
        records.append({'image': path.name, 'camera_raw_xyz': list(position), 'target_raw_xyz': list(aim)})
    bpy.ops.wm.save_as_mainfile(filepath=str(output/'section_preview.blend'))
    return {'views': records, 'display_cut_z': cut_z, 'base_asset_modified': False,
            'visual_review_required': True, 'note': 'Artificial horizontal display cut, not a physical ceiling determination'}


def run(candidate: Path, data_root: Path, display_height: float) -> Path:
    payload = json.loads(candidate.read_text(encoding='utf-8'))
    if payload.get('ready_for_cut') is not True or payload.get('physical_semantics_verified') is not False:
        raise ValueError('Explicit approximation candidate required')
    scene = (data_root/payload['scene_code']).resolve()
    if scene.parent != data_root.resolve() or not math.isfinite(display_height) or display_height <= 1.6:
        raise ValueError('Invalid scene or display height (must exceed interior camera height 1.6m)')
    guards = {}
    for name,h in payload['source_fingerprints'].items():
        path = (scene/name).resolve()
        if not path.is_relative_to(scene) or digest(path) != h:
            raise ValueError('Remote source differs: '+name)
        guards[path] = h
    # Also guard the current historical video even if it was absent from the local package.
    for name in ('output.mp4','points.json','timeline.json'):
        path = scene/name
        if path.is_file():
            guards[path] = digest(path)
    verify_point_mapping(payload, json.loads((scene/'points.json').read_text(encoding='utf-8')))
    candidate_hash = digest(candidate)
    output = candidate.resolve().parent/'asset'
    output.mkdir(exist_ok=False)
    try:
        for obj in list(bpy.data.objects):
            bpy.data.objects.remove(obj, do_unlink=True)
        bpy.ops.wm.obj_import(filepath=str(scene/'mesh.obj'), up_axis='Z', forward_axis='Y')
        materials = {m.name: m for m in bpy.data.materials}
        for face in payload['geometry']['faces']:
            if face['material'] not in materials:
                raise ValueError('Imported material missing')
        # Import for the previously verified material/texture nodes, then replace geometry.
        for obj in list(bpy.data.objects):
            bpy.data.objects.remove(obj, do_unlink=True)
        make_mesh('RoomSource', payload['geometry']['faces'], materials)
        floor_mat = bpy.data.materials.new('DemoFloorApproximation')
        floor_mat.diffuse_color = (.22,.22,.22,1)
        materials['DemoFloorApproximation'] = floor_mat
        floor_faces = [{'material': 'DemoFloorApproximation', 'corners':
            [[x,y,payload['floor_z'],x,y] for x,y in tri]} for tri in payload['geometry']['polygon_cells']]
        make_mesh('DemoFloorApproximation', floor_faces, materials)
        create_point_anchors(payload)
        metadata = {k:payload[k] for k in ('floor_z','raw_to_asset_matrix','raw_to_floor_xy',
                    'polygon_raw_xy','interior_devices','boundary_devices','provenance')}
        metadata_json = json.dumps(metadata,sort_keys=True)
        bpy.context.scene['room_asset_metadata'] = metadata_json
        # Pack source images into the .blend; GLB export embeds its referenced images.
        bpy.ops.file.pack_all()
        required_images = {item['sha256'] for item in payload['materials']['textures'].values()}
        if not required_images <= packed_image_hashes():
            raise ValueError('Referenced image not loaded and packed')
        expected = snapshot()
        blend = output/'room.blend'
        bpy.ops.wm.save_as_mainfile(filepath=str(blend))
        bpy.ops.wm.open_mainfile(filepath=str(blend))
        reopened = snapshot()
        if reopened != expected:
            raise ValueError('Saved/reloaded geometry, UV, transform or materials differ')
        if not required_images <= packed_image_hashes():
            raise ValueError('Packed textures missing after reopen')
        point_records = verify_saved_point_anchors(payload)
        if bpy.context.scene.get('room_asset_metadata') != metadata_json:
            raise ValueError('Saved asset coordinate/provenance metadata differs')
        bpy.ops.export_scene.gltf(filepath=str(output/'room.glb'), export_format='GLB', export_yup=True,
                                  export_extras=True)
        glb = (output/'room.glb').read_bytes()
        if glb[:4] != b'glTF' or int.from_bytes(glb[8:12],'little') != len(glb):
            raise ValueError('Invalid GLB header/length')
        json_size = int.from_bytes(glb[12:16],'little')
        gltf = json.loads(glb[20:20+json_size])
        if not gltf.get('meshes') or any('uri' in item and not item['uri'].startswith('data:')
            for field in ('buffers','images') for item in gltf.get(field,[])):
            raise ValueError('GLB is empty or has external dependencies')
        if required_images and not gltf.get('images'):
            raise ValueError('GLB texture export missing')
        validation = {'status': 'passed', 'checks': {'blend_reopened_identical': True,
            'packed_textures_loaded_after_reopen': True, 'glb_self_contained': True,
            'source_point_mapping_matches': True, 'reloaded_point_anchors_match': True,
            'reloaded_coordinate_provenance_matches': True},
            'point_count': len(point_records), 'point_records': point_records,
            'objects': reopened, 'visual_review_required': True,
            'ready_for_fire_effects': False, 'physical_semantics_verified': False}
        dump(output/'validation.json', validation)
        # Reacquire material datablocks after open_mainfile (old Python references invalid).
        materials = {m.name: m for m in bpy.data.materials}
        views = preview(output,payload,materials,payload['floor_z']+display_height)
        unchanged = all(digest(p)==h for p,h in guards.items()) and digest(candidate)==candidate_hash
        if not unchanged:
            raise ValueError('Source/history changed during preparation')
        dump(output/'manifest.json', {'scene_code': payload['scene_code'], 'room_id': payload['room_id'],
            'candidate_sha256': candidate_hash, 'provenance': payload['provenance'],
            'source_fingerprints': payload['source_fingerprints'],
            'clipping_parameters': {'polygon_raw_xy':payload['polygon_raw_xy'],
                'boundary_buffer_m':payload['geometry']['boundary_buffer_m'],
                'vertical_trim_on_base':False, 'triangle_count':payload['geometry']['triangle_count']},
            'engineering_policy': {k:payload[k] for k in ('floor_z','floor_policy','physical_semantics_verified','wall_policy')},
            'raw_to_asset_matrix': payload['raw_to_asset_matrix'],
            'raw_to_floor_xy': payload['raw_to_floor_xy'],
            'glb_coordinate_mapping': 'glTF Y-up export: raw (x,y,z) -> (x,z,-y); room.blend retains raw XYZ',
            'points': payload['points'], 'interior_devices': payload['interior_devices'],
            'boundary_devices': payload['boundary_devices'], 'source_and_history_unchanged': unchanged,
            'previews': views, 'validation': validation,
            'artifacts': {name: digest(output/name) for name in
                ('room.blend','room.glb','validation.json','section_preview.blend','top.png','oblique.png','interior.png')}})
        print(f'[room-asset] status=passed visual_review_required=true output={output}', flush=True)
        return output
    except Exception as exc:
        dump(output/'failure.json', {'status':'failed', 'error':str(exc), 'ready_for_fire_effects':False,
                                    'source_and_history_unchanged':all(digest(p)==h for p,h in guards.items())})
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description='Save/reopen room asset, then generate three inspection images; no video')
    parser.add_argument('--candidate',type=Path,required=True)
    parser.add_argument('--data-root',type=Path,default=Path('/app/data'))
    parser.add_argument('--display-height',type=float,default=2.4)
    args = parser.parse_args(sys.argv[sys.argv.index('--')+1:])
    run(args.candidate,args.data_root,args.display_height)


if __name__ == '__main__':
    main()
