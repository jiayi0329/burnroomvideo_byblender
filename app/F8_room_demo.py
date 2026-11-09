"""【F8-D｜当前展示修正/火灾预览】只加载已生成的 room.blend，另存派生版。

inspect: 更新三视图；samples: 中近景/总览六张对比样帧。静帧审核期间禁用动画入口。
复用 F8_room_helpers 的 UV 保留建网格/展示截断，不重做户型对齐或房间平面裁切。
不修改基础 room.blend/glb、数据库、源模型、核验记录或历史视频。
远端 Blender 4.2 独立执行；当前第三轮操作见 docs/room_style_round3.md。
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
from F8_room_helpers import (below, digest, dump, make_mesh, interior_camera,
                             mesh_faces, camera, closest_hit)
from room_demo_plan import display_faces, room_timeline
from room_fire_config import load_config
from F8_room_fire_style import configure_render, lighting, add_fire, snapshot_settings


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


def run(args: argparse.Namespace) -> Path:
    started=time.perf_counter()
    if args.mode not in ('inspect','samples'):raise ValueError('Only still images permitted; animation is paused')
    config=load_config(args.config)
    if args.mode=='samples' and args.points is None:raise ValueError('--points required for fire samples')
    asset=args.asset.resolve()
    manifest=json.loads((asset/'manifest.json').read_text(encoding='utf-8'))
    validation=json.loads((asset/'validation.json').read_text(encoding='utf-8'))
    if validation['status']!='passed' or not all(validation['checks'].values()):raise ValueError('Base validation failed')
    guards={p:digest(p) for p in asset.iterdir() if p.is_file()}
    for name,h in manifest['artifacts'].items():
        path=(asset/name).resolve()
        if not path.is_relative_to(asset) or digest(path)!=h:raise ValueError('Base artifact fingerprint differs: '+name)
    guards[args.config.resolve()]=digest(args.config)
    code_files=('F8_room_demo.py','F8_room_fire_style.py','room_fire_config.py','room_demo_plan.py','F8_prepare_room_asset.py','F8_room_helpers.py')
    code_hashes={name:digest(Path(__file__).resolve().parent/name) for name in code_files}
    points=None; ignition=None
    if args.mode=='samples':
        points_path=args.points.resolve()
        if digest(points_path)!=manifest['source_fingerprints']['points.json']:raise ValueError('Points fingerprint mismatch')
        for name in manifest['source_fingerprints']:
            path=(points_path.parent/name).resolve()
            if path.parent==points_path.parent and path.is_file():guards[path]=digest(path)
        points=json.loads(points_path.read_text(encoding='utf-8'))
        candidate=asset.parent/'candidate.json'
        if digest(candidate)!=manifest['candidate_sha256']:raise ValueError('Bound candidate differs')
        guards[candidate]=digest(candidate)
        ignition=json.loads(candidate.read_text(encoding='utf-8'))['ignition_device']
    revision=config['art'].get('revision',1)
    output=asset.parent/('style_round'+str(revision))/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_'+uuid.uuid4().hex[:8])
    output.mkdir(parents=True,exist_ok=False)
    dump(output/'requested_config.json',config)
    samples=[]
    try:
        bpy.ops.wm.open_mainfile(filepath=str(asset/'room.blend'))
        scene=bpy.context.scene
        metadata=json.loads(scene['room_asset_metadata']); floor=metadata['floor_z']; polygon=metadata['polygon_raw_xy']
        source=bpy.data.objects['RoomSource']; faces=mesh_faces(source)
        audit=material_audit(source)
        floor_obj=bpy.data.objects['DemoFloorApproximation']
        audit += material_audit(floor_obj)
        selected,groups=display_faces(faces,args.drop_component)
        source.hide_render=True; source.hide_viewport=True
        materials={m.name:m for m in bpy.data.materials}
        display=make_mesh('RoomDisplay',below(selected,floor+args.wall_height),materials)
        # Copy shaders solely for the display derivative; both sides of scan planes remain visible.
        for i,mat in enumerate(display.data.materials):
            copy=mat.copy(); copy.use_backface_culling=False; display.data.materials[i]=copy
        lo=[min(v[k] for v in polygon) for k in (0,1)]; hi=[max(v[k] for v in polygon) for k in (0,1)]
        cx,cy=[(lo[k]+hi[k])/2 for k in (0,1)]; span=max(hi[k]-lo[k] for k in (0,1))
        actual=configure_render(scene,config)
        actual['style_revision']=revision
        actual['lighting']=lighting(scene,[cx,cy,floor+.4],span,config)
        dump(output/'effective_settings.json',actual)
        ix,iy=interior_camera(polygon)
        views=[('top',(cx,cy,floor+span*1.5),(cx,cy,floor),True),
               ('oblique',(cx+span*.5,cy-span*.65,floor+span*.95),(cx,cy,floor+.3),True),
               ('interior',(ix,iy,floor+4.5),(cx,cy,floor+.2),False)]
        report={'mode':args.mode,'base_asset':str(asset),'base_room_sha256':guards[asset/'room.blend'],
            'floor_z':floor,'display_cut_z':floor+args.wall_height,'source_material_audit':audit,
            'components':groups,'removed_component_ids':args.drop_component,
            'new_cut_caps_created':False,'base_asset_modified':False,
            'code_fingerprints':code_hashes,'config_sha256':digest(args.config),
            'style_revision':revision,
            'changes':['Exposure -0.5 / world .15 / soft lights 500,150,300 candidate profile',
                'deterministic curved multi-tongue cluster; independent emission/density',
                'independent persistent rising smoke; paired closeup/overview stills'],
            'visual_review_required':True,'animation_enabled':False,'effective_settings':actual}
        requests=[]
        if args.mode=='samples':
            if set(metadata['interior_devices']) & set(config['events']['excluded_devices']):
                raise ValueError('Room memberships include an excluded propagation point')
            timeline=room_timeline(points,metadata['interior_devices'],ignition,config['events']['layer_seconds'])
            dump(output/'room_timeline.json',timeline)
            effects=add_fire(scene,timeline,points,floor,[display,floor_obj],config,closest_hit)
            actual['effects']=effects
            dump(output/'effective_settings.json',actual)
            if revision>=2:
                report['changes']=['Preserve round-one tongue topology, color ramp, emission, exposure and surface lighting',
                    'Primary height x1.75 / radius x1.45; secondary height x1.3; four radial density layers',
                    'Replace smoke spheres with curled narrow-base plumes; independent extinction and growth',
                    'Reduce volume illumination only; fire light cutoff 5m, energy unchanged; closeup 30mm/target 1.3m']
            if revision==3:
                report['changes']=['Preserve round-two flame parameters, plume geometry/growth, propagation, cameras and quality',
                    'Exposure -0.35 / world .22 with subtly lighter charcoal background',
                    'Key 500W unchanged; fill 190W volume .35; rim 340W volume .7 aimed 1.6m above scene lighting center',
                    'Only thin smoke scattering edge slightly brighter; dark core, density and absorption unchanged']
            report['effects']=effects
            report['timeline']=timeline
            anchor=next(p for p in effects['anchors'] if p['device']==ignition)
            point=next(p for p in points if int(p['device'])==ignition)['pose']['translation']
            close=config['art']['closeup']; base=anchor['display_fire_base_z']
            close_position=[point['x']+close['offset'][0],point['y']+close['offset'][1],base+close['offset'][2]]
            close_target=[point['x'],point['y'],base+close['target_height']]
            for seconds in config['quality']['sample_times']:
                frame=round(seconds*scene.render.fps)+1
                requests.extend([(f'overview_{seconds:g}s',frame,views[1][1],views[1][2],True,None),
                    (f'closeup_{ignition}_{seconds:g}s',frame,close_position,close_target,False,close['lens'])])
        else:
            requests=[(name,1,position,target,ortho,None) for name,position,target,ortho in views]
        for name,frame,position,target,ortho,lens in requests:
            scene.frame_set(frame)
            cam=camera(scene,position,target,ortho,span)
            cam.data.dof.use_dof=False
            if lens is not None:cam.data.lens=lens
            scene.render.filepath=str(output/(name+'.png'))
            before=time.perf_counter()
            bpy.ops.render.render(write_still=True)
            path=output/(name+'.png')
            if not path.is_file() or path.stat().st_size<100:raise ValueError('Missing sample: '+name)
            samples.append({'image':path.name,'seconds':(frame-1)/scene.render.fps,
                'render_seconds':round(time.perf_counter()-before,3),'sha256':digest(path),
                'effective':snapshot_settings(scene)})
            dump(output/'sample_manifest.json',{'status':'partial','samples':samples})
            print(f'[room-demo] sample={name} render_seconds={samples[-1]["render_seconds"]}',flush=True)
        bpy.ops.wm.save_as_mainfile(filepath=str(output/'display.blend'))
        if any(digest(p)!=h for p,h in guards.items()):raise ValueError('Base file changed')
        report['guarded_files']={str(p):h for p,h in guards.items()}
        report['guarded_files_unchanged']=True
        report['elapsed_seconds']=round(time.perf_counter()-started,3)
        report['total_still_render_seconds']=sum(item['render_seconds'] for item in samples)
        report['samples']=samples
        report['artifacts']={p.name:digest(p) for p in output.iterdir() if p.is_file()}
        dump(output/'sample_manifest.json',{'status':'awaiting_visual_review','samples':samples})
        dump(output/'repair_report.json',report)
        print(f'[room-demo] mode={args.mode} output={output} base_unchanged=true',flush=True)
        return output
    except Exception as exc:
        dump(output/'failure.json',{'error':str(exc),'mode':args.mode,'base_unchanged':all(digest(p)==h for p,h in guards.items())})
        raise


def main() -> None:
    p=argparse.ArgumentParser(description='Versioned paired stills only; animation paused pending review')
    p.add_argument('--asset',type=Path,required=True)
    p.add_argument('--mode',choices=('inspect','samples'),default='samples')
    p.add_argument('--config',type=Path,default=Path(__file__).with_name('room_fire_round3.json'))
    p.add_argument('--wall-height',type=float,default=1.1)
    p.add_argument('--drop-component',type=int,action='append',default=[])
    p.add_argument('--points',type=Path)
    args=p.parse_args(sys.argv[sys.argv.index('--')+1:])
    if not math.isfinite(args.wall_height) or not .3<=args.wall_height<=2.4:p.error('Display wall height must be .3..2.4m')
    run(args)


if __name__=='__main__':main()
