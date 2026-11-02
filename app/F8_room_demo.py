"""【F8-D｜当前展示修正/火灾预览】只加载已生成的 room.blend，另存派生版。

inspect: 更新三视图；samples: 三张火灾样帧；short: 最长8秒短片。
复用 F8-B 的 UV 保留建网格/展示截断，不重做户型对齐或房间平面裁切。
不修改基础 room.blend/glb、数据库、源模型、核验记录或历史视频。
远端 Blender 4.2 独立执行；同目录需 F8_prepare_room_asset.py、room_demo_plan.py。
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import sys
import time
import uuid

import bpy
from mathutils import Vector

sys.path.insert(0,str(Path(__file__).resolve().parent))
from F8_prepare_room_asset import below, digest, dump, make_mesh, interior_camera
from room_demo_plan import display_faces, room_timeline, envelope


def mesh_faces(obj: bpy.types.Object) -> list[dict]:
    mesh = obj.data
    if not mesh.uv_layers.active or any(len(p.vertices)!=3 for p in mesh.polygons):
        raise ValueError('Triangular room mesh and UVs required')
    return [{'material':mesh.materials[p.material_index].name,'corners':
        [list(obj.matrix_world @ mesh.vertices[mesh.loops[i].vertex_index].co)+list(mesh.uv_layers.active.data[i].uv)
         for i in p.loop_indices]} for p in mesh.polygons]


def material_audit(obj: bpy.types.Object) -> list[dict]:
    result = []
    for i,mat in enumerate(obj.data.materials):
        images = [n.image for n in mat.node_tree.nodes if n.type=='TEX_IMAGE' and n.image] if mat.use_nodes else []
        shaders = [n for n in mat.node_tree.nodes if n.type=='BSDF_PRINCIPLED'] if mat.use_nodes else []
        degenerate=0
        if obj.data.uv_layers.active:
            for face in obj.data.polygons:
                if face.material_index!=i:continue
                a,b,c=[obj.data.uv_layers.active.data[j].uv for j in face.loop_indices]
                if abs((b.x-a.x)*(c.y-a.y)-(b.y-a.y)*(c.x-a.x))<1e-12:degenerate+=1
        result.append({'name':mat.name,'face_count':sum(p.material_index==i for p in obj.data.polygons),
            'use_nodes':mat.use_nodes,'image_nodes':[{'name':im.name,'size':list(im.size),
                'packed':bool(im.packed_file)} for im in images],
            'base_color_links':[[link.from_node.name for link in n.inputs['Base Color'].links] for n in shaders],
            'degenerate_uv_faces':degenerate,'original_diffuse_color':list(mat.diffuse_color),
            'backface_culling':mat.use_backface_culling,
            'uv_present':obj.data.uv_layers.active is not None,
            'note':'Image presence does not prove shader linkage or appearance; no automatic material replacement'})
    return result


def camera(scene: bpy.types.Scene, position: list, aim: list, ortho: bool=False, span: float=10) -> bpy.types.Object:
    obj = scene.camera
    if obj is None:
        obj = bpy.data.objects.new('DemoCamera',bpy.data.cameras.new('DemoCamera'))
        scene.collection.objects.link(obj)
        scene.camera = obj
        target = bpy.data.objects.new('DemoTarget',None)
        scene.collection.objects.link(target)
        c = obj.constraints.new('TRACK_TO')
        c.track_axis,c.up_axis,c.target = 'TRACK_NEGATIVE_Z','UP_Y',target
    obj.location = position
    obj.constraints[0].target.location = aim
    obj.data.type = 'ORTHO' if ortho else 'PERSP'
    obj.data.lens,obj.data.clip_start,obj.data.ortho_scale = 18,.03,span*1.3
    bpy.context.view_layer.update()
    return obj


def closest_hit(origin: Vector, direction: Vector, objects: list) -> tuple | None:
    hits = []
    for obj in objects:
        inverse = obj.matrix_world.inverted()
        hit,local,normal,index = obj.ray_cast(inverse @ origin,(inverse.to_3x3() @ direction).normalized())
        if hit:
            world = obj.matrix_world @ local
            world_normal = (inverse.transposed().to_3x3() @ normal).normalized()
            hits.append(((world-origin).length,world,world_normal,index,obj))
    return min(hits,key=lambda value:value[0]) if hits else None


def ray_probe(scene: bpy.types.Scene, objects: list) -> dict:
    """Small fixed grid: distinguish world background from actual surface hits."""
    cam = scene.camera
    frame = cam.data.view_frame(scene=scene)
    xs,ys = [v.x for v in frame],[v.y for v in frame]
    records = []
    for ix in range(7):
        for iy in range(5):
            p = Vector((min(xs)+(max(xs)-min(xs))*(ix+.5)/7,
                        min(ys)+(max(ys)-min(ys))*(iy+.5)/5,frame[0].z))
            direction = cam.matrix_world.to_quaternion() @ p.normalized()
            hit = closest_hit(cam.matrix_world.translation,direction,objects)
            if hit:_,location,normal,index,obj=hit
            mat = None
            if hit and obj.type=='MESH' and 0<=index<len(obj.data.polygons):
                slot = obj.data.polygons[index].material_index
                if slot<len(obj.data.materials):mat=obj.data.materials[slot].name
            records.append({'grid':[ix,iy],'kind':'surface' if hit else 'world_background',
                'object':obj.name if hit else None,'material':mat,
                'normal':list(normal) if hit else None,
                'back_facing':bool(normal.dot(direction)>0) if hit else None})
    return {'background_rays':sum(r['kind']=='world_background' for r in records),'total_rays':len(records),
            'samples':records,'note':'Sparse geometric evidence, not pixel color classification'}


def lighting(scene: bpy.types.Scene, center: list, span: float) -> None:
    scene.render.engine = 'BLENDER_EEVEE_NEXT'
    scene.render.resolution_x,scene.render.resolution_y,scene.render.resolution_percentage = 960,540,100
    scene.world = bpy.data.worlds.new('DemoWorld')
    scene.world.use_nodes = True
    scene.world.node_tree.nodes['Background'].inputs['Color'].default_value = (.32,.36,.42,1)
    scene.world.node_tree.nodes['Background'].inputs['Strength'].default_value = .8
    scene.view_settings.exposure = .8
    for name,offset,energy in [('Key',(0,0,5),1800),('Fill',(-3,-2,3),1000),('Rim',(3,2,4),800)]:
        data = bpy.data.lights.new('Demo'+name,'AREA')
        data.energy,data.size = energy,max(4,span*.7)
        obj = bpy.data.objects.new(data.name,data)
        scene.collection.objects.link(obj)
        obj.location = Vector(center)+Vector(offset)
        obj.rotation_euler = (Vector(center)-obj.location).to_track_quat('-Z','Y').to_euler()


def volume_material(name: str, smoke: bool) -> tuple:
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes; nodes.clear()
    links = mat.node_tree.links
    out = nodes.new('ShaderNodeOutputMaterial')
    volume = nodes.new('ShaderNodeVolumePrincipled')
    links.new(volume.outputs['Volume'],out.inputs['Volume'])
    volume.inputs['Color'].default_value = (.07,.055,.045,1) if smoke else (1,.18,.015,1)
    if 'Absorption Color' in volume.inputs:volume.inputs['Absorption Color'].default_value=(1,1,1,1)
    volume.inputs['Anisotropy'].default_value = .2
    coord=nodes.new('ShaderNodeTexCoord'); noise=nodes.new('ShaderNodeTexNoise')
    noise.noise_dimensions='4D'
    noise.inputs['Scale'].default_value=5 if smoke else 3
    noise.inputs['Detail'].default_value=5
    links.new(coord.outputs['Generated'],noise.inputs['Vector'])
    for frame,value in ((1,0),(145,3)):
        noise.inputs['W'].default_value=value; noise.inputs['W'].keyframe_insert('default_value',frame=frame)
    ramp=nodes.new('ShaderNodeValToRGB')
    ramp.color_ramp.elements[0].position=.42 if smoke else .4
    ramp.color_ramp.elements[1].position=.68
    links.new(noise.outputs['Fac'],ramp.inputs['Fac'])
    separate=nodes.new('ShaderNodeSeparateXYZ'); links.new(coord.outputs['Generated'],separate.inputs[0])
    fade=nodes.new('ShaderNodeMath'); fade.operation='SUBTRACT'; fade.inputs[0].default_value=1
    links.new(separate.outputs['Z'],fade.inputs[1])
    mask=nodes.new('ShaderNodeMath'); mask.operation='MULTIPLY'
    links.new(ramp.outputs['Color'],mask.inputs[0]); links.new(fade.outputs[0],mask.inputs[1])
    # Smooth the radial edge as well as the height; avoid a hard solid container silhouette.
    squares=[]
    for axis in ('X','Y'):
        offset=nodes.new('ShaderNodeMath'); offset.operation='SUBTRACT'; offset.inputs[1].default_value=.5
        links.new(separate.outputs[axis],offset.inputs[0])
        square=nodes.new('ShaderNodeMath'); square.operation='MULTIPLY'
        links.new(offset.outputs[0],square.inputs[0]); links.new(offset.outputs[0],square.inputs[1]); squares.append(square)
    radius=nodes.new('ShaderNodeMath'); radius.operation='ADD'
    for i,node in enumerate(squares):links.new(node.outputs[0],radius.inputs[i])
    scale=nodes.new('ShaderNodeMath'); scale.operation='MULTIPLY'; scale.inputs[1].default_value=4
    links.new(radius.outputs[0],scale.inputs[0])
    radial=nodes.new('ShaderNodeMath'); radial.operation='SUBTRACT'; radial.inputs[0].default_value=1; radial.use_clamp=True
    links.new(scale.outputs[0],radial.inputs[1])
    soft=nodes.new('ShaderNodeMath'); soft.operation='MULTIPLY'
    links.new(mask.outputs[0],soft.inputs[0]); links.new(radial.outputs[0],soft.inputs[1])
    amount=nodes.new('ShaderNodeValue'); amount.outputs[0].default_value=0
    density=nodes.new('ShaderNodeMath'); density.operation='MULTIPLY'
    links.new(soft.outputs[0],density.inputs[0]); links.new(amount.outputs[0],density.inputs[1])
    links.new(density.outputs[0],volume.inputs['Density'])
    if not smoke:
        volume.inputs['Emission Color'].default_value=(1,.14,.008,1)
        volume.inputs['Blackbody Intensity'].default_value=0
        emission=nodes.new('ShaderNodeMath'); emission.operation='MULTIPLY'; emission.inputs[1].default_value=9
        links.new(density.outputs[0],emission.inputs[0]); links.new(emission.outputs[0],volume.inputs['Emission Strength'])
    return mat,amount


def add_fire(scene: bpy.types.Scene, timeline: dict, points: list[dict], floor: float, surfaces: list) -> list[dict]:
    positions={int(p['device']):p['pose']['translation'] for p in points}
    anchors=[]
    for event in timeline['spread_events']:
        device=event['point']; p=positions[device]; start=event['time']; keys=envelope(start,scene.render.fps)
        hit=closest_hit(Vector((p['x'],p['y'],floor+1.15)),Vector((0,0,-1)),surfaces)
        base=max(floor,hit[1].z+.015) if hit else floor
        anchors.append({'device':device,'reference_floor_z':floor,'display_fire_base_z':base,
                        'note':'Visibility anchor on existing display surface; not physical floor identification'})
        for smoke in (False,True):
            if smoke:
                bpy.ops.mesh.primitive_uv_sphere_add(segments=16,ring_count=8,radius=1,
                                                    location=(p['x'],p['y'],base+1.9))
            else:
                bpy.ops.mesh.primitive_cone_add(vertices=16,radius1=.36,radius2=.035,depth=1.7,
                                               location=(p['x'],p['y'],base+.85))
            obj=bpy.context.object; obj.name=('Smoke_' if smoke else 'Flame_')+str(device)
            mat,amount=volume_material(obj.name,smoke); obj.data.materials.append(mat)
            for frame,value in keys:
                amount.outputs[0].default_value=value*(3.5 if smoke else 1.1)
                amount.outputs[0].keyframe_insert('default_value',frame=frame)
                growth=.03+value*.97
                obj.scale=(growth*.65,growth*.65,growth*1.25) if smoke else (growth,growth,growth)
                obj.keyframe_insert('scale',frame=frame)
                if smoke:
                    obj.location.z=base+1.4+max(0,(frame-keys[0][0])/scene.render.fps)*.12
                else:
                    obj.location.z=base+.85*growth
                obj.keyframe_insert('location',frame=frame)
        light=bpy.data.lights.new('FireLight_'+str(device),'POINT')
        light.color=(1,.18,.02); light.shadow_soft_size=.45
        lamp=bpy.data.objects.new(light.name,light); scene.collection.objects.link(lamp)
        lamp.location=(p['x'],p['y'],base+.8)
        for frame,value in keys:
            light.energy=100*value; light.keyframe_insert('energy',frame=frame)
    # Prevent default Bezier handles from overshooting density/scale below zero.
    for action in bpy.data.actions:
        for curve in action.fcurves:
            for key in curve.keyframe_points:
                key.interpolation='BEZIER'; key.handle_left_type=key.handle_right_type='AUTO_CLAMPED'
    return anchors


def run(args: argparse.Namespace) -> Path:
    started=time.perf_counter()
    asset=args.asset.resolve()
    manifest=json.loads((asset/'manifest.json').read_text(encoding='utf-8'))
    validation=json.loads((asset/'validation.json').read_text(encoding='utf-8'))
    if validation['status']!='passed' or not all(validation['checks'].values()):raise ValueError('Base validation failed')
    guards={p:digest(p) for p in asset.iterdir() if p.is_file()}
    for name,h in manifest['artifacts'].items():
        path=(asset/name).resolve()
        if not path.is_relative_to(asset) or digest(path)!=h:raise ValueError('Base artifact fingerprint differs: '+name)
    if args.mode!='inspect' and not args.accept_display:raise ValueError('Inspect views first, then pass --accept-display')
    if not 0<args.duration<=8:raise ValueError('Short preview duration must be 0..8 seconds')
    output=asset.parent/'display_versions'/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_'+uuid.uuid4().hex[:8])
    output.mkdir(parents=True,exist_ok=False)
    try:
        bpy.ops.wm.open_mainfile(filepath=str(asset/'room.blend'))
        scene=bpy.context.scene
        metadata=json.loads(scene['room_asset_metadata']); floor=metadata['floor_z']; polygon=metadata['polygon_raw_xy']
        source=bpy.data.objects['RoomSource']; faces=mesh_faces(source)
        audit=material_audit(source)
        floor_obj=bpy.data.objects['DemoFloorApproximation']
        audit += material_audit(floor_obj)
        materials={m.name:m for m in bpy.data.materials}
        # Recreate only the former DISPLAY cut for the baseline probes, not the full roofed room.
        baseline=make_mesh('BaselineDisplay',below(faces,manifest['previews']['display_cut_z']),materials)
        old=next(v for v in manifest['previews']['views'] if v['image']=='interior.png')
        # Match F8-B's former 800x600 / 20mm view for a comparable baseline.
        scene.render.resolution_x,scene.render.resolution_y,scene.render.resolution_percentage=800,600,100
        camera(scene,old['camera_raw_xyz'],old['target_raw_xyz']).data.lens=20
        baseline_probe=ray_probe(scene,[baseline,floor_obj])
        bpy.data.objects.remove(baseline,do_unlink=True)
        selected,groups=display_faces(faces,args.drop_component)
        for group in groups:
            group['small_elevated_candidate'] = group['diagonal_m']<.5 and group['bounds_min'][2]>floor+.25
        source.hide_render=True; source.hide_viewport=True
        display=make_mesh('RoomDisplay',below(selected,floor+args.wall_height),materials)
        # Copy shaders solely for the display derivative; both sides of scan planes remain visible.
        for i,mat in enumerate(display.data.materials):
            copy=mat.copy(); copy.use_backface_culling=False; display.data.materials[i]=copy
        lo=[min(v[k] for v in polygon) for k in (0,1)]; hi=[max(v[k] for v in polygon) for k in (0,1)]
        cx,cy=[(lo[k]+hi[k])/2 for k in (0,1)]; span=max(hi[k]-lo[k] for k in (0,1))
        lighting(scene,[cx,cy,floor+.4],span)
        ix,iy=interior_camera(polygon)
        views=[('top',(cx,cy,floor+span*1.5),(cx,cy,floor),True),
               ('oblique',(cx+span*.5,cy-span*.65,floor+span*.95),(cx,cy,floor+.3),True),
               ('interior',(ix,iy,floor+4.5),(cx,cy,floor+.2),False)]
        scene.render.image_settings.file_format='PNG'
        for name,position,target,ortho in views:
            camera(scene,position,target,ortho,span)
            scene.render.filepath=str(output/(name+'.png')); bpy.ops.render.render(write_still=True)
        updated_probe=ray_probe(scene,[display,floor_obj])
        report={'mode':args.mode,'base_asset':str(asset),'base_room_sha256':guards[asset/'room.blend'],
            'floor_z':floor,'display_cut_z':floor+args.wall_height,'source_material_audit':audit,
            'baseline_interior_rays':baseline_probe,'updated_interior_rays':updated_probe,
            'components':groups,'removed_component_ids':args.drop_component,
            'gray_surface_findings':'Use ray hits to separate world/geometry; inspect UV/image/normals. No missing-texture assumption.',
            'new_cut_caps_created':False,'base_asset_modified':False,
            'changes':['higher downward internal camera','lower display wall cut only','soft area fill + exposure',
                       'two-sided display material copies; source shaders preserved'],
            'visual_review_required':True}
        if args.mode!='inspect':
            if args.points is None:raise ValueError('--points must explicitly name source points.json for fire preview')
            points_path=args.points.resolve()
            if digest(points_path)!=manifest['source_fingerprints']['points.json']:raise ValueError('Points fingerprint mismatch')
            guards[points_path]=digest(points_path)
            # Guard current source/history files too; no original file is used as an output.
            for name in manifest['source_fingerprints']:
                path=(points_path.parent/name).resolve()
                if path.parent==points_path.parent and path.is_file():guards[path]=digest(path)
            points=json.loads(points_path.read_text(encoding='utf-8'))
            candidate=asset.parent/'candidate.json'
            if digest(candidate)!=manifest['candidate_sha256']:raise ValueError('Bound candidate differs')
            ignition=json.loads(candidate.read_text(encoding='utf-8'))['ignition_device']
            timeline=room_timeline(points,metadata['interior_devices'],ignition)
            dump(output/'room_timeline.json',timeline)
            scene.render.fps=12
            report['fire_visibility_anchors']=add_fire(scene,timeline,points,floor,[display,floor_obj])
            # Use the full-room elevated view so individual events remain visible.
            camera(scene,views[1][1],views[1][2],True,span)
            scene.render.resolution_x,scene.render.resolution_y=640,360
            if args.mode=='samples':
                for seconds in (1,3.5,6):
                    scene.frame_set(round(seconds*12)+1)
                    scene.render.filepath=str(output/f'fire_{seconds:g}s.png'); bpy.ops.render.render(write_still=True)
            else:
                scene.frame_start,scene.frame_end=1,round(args.duration*12)
                scene.render.image_settings.file_format='FFMPEG'; scene.render.ffmpeg.format='MPEG4'
                scene.render.ffmpeg.codec='H264'; scene.render.filepath=str(output/'fire_short.mp4')
                bpy.ops.render.render(animation=True)
            report['timeline']=timeline
        bpy.ops.wm.save_as_mainfile(filepath=str(output/'display.blend'))
        if any(digest(p)!=h for p,h in guards.items()):raise ValueError('Base file changed')
        report['guarded_files']={str(p):h for p,h in guards.items()}
        report['guarded_files_unchanged']=True
        required=['top.png','oblique.png','interior.png','display.blend']
        if args.mode=='samples':required += ['fire_1s.png','fire_3.5s.png','fire_6s.png']
        if args.mode=='short':required += ['fire_short.mp4']
        if any(not (output/name).is_file() or (output/name).stat().st_size<100 for name in required):
            raise ValueError('Expected preview artifact missing/empty')
        report['elapsed_seconds']=round(time.perf_counter()-started,3)
        report['render_config']={'resolution':[scene.render.resolution_x,scene.render.resolution_y],
            'fps':scene.render.fps,'animation_frames':round(args.duration*12) if args.mode=='short' else 0,
            'engine':scene.render.engine}
        report['artifacts']={p.name:digest(p) for p in output.iterdir() if p.is_file()}
        dump(output/'repair_report.json',report)
        print(f'[room-demo] mode={args.mode} output={output} base_unchanged=true',flush=True)
        return output
    except Exception as exc:
        dump(output/'failure.json',{'error':str(exc),'mode':args.mode,'base_unchanged':all(digest(p)==h for p,h in guards.items())})
        raise


def main() -> None:
    p=argparse.ArgumentParser(description='Existing room asset -> display views, fire stills or <=8s preview')
    p.add_argument('--asset',type=Path,required=True)
    p.add_argument('--mode',choices=('inspect','samples','short'),default='inspect')
    p.add_argument('--wall-height',type=float,default=1.1)
    p.add_argument('--drop-component',type=int,action='append',default=[])
    p.add_argument('--points',type=Path)
    p.add_argument('--accept-display',action='store_true')
    p.add_argument('--duration',type=float,default=4)
    args=p.parse_args(sys.argv[sys.argv.index('--')+1:])
    if not math.isfinite(args.wall_height) or not .3<=args.wall_height<=2.4:p.error('Display wall height must be .3..2.4m')
    run(args)


if __name__=='__main__':main()
