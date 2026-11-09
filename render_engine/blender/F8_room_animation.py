"""F8-E Blender worker: frozen round-three assets/style, absolute-time PNG frames.

Only run through run_room_animation.py; no video/API/DB entry point here.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import os
import math
import shutil
import sys
import time
import traceback

ENTRY_MONOTONIC=time.monotonic()

import bpy
from mathutils import Vector

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from render_engine.blender.F8_room_helpers import mesh_faces, camera, closest_hit, below, make_mesh
from render_engine.blender.F8_room_fire_style import configure_render, lighting, add_fire, snapshot_settings, checked
from render_engine.propagation.room_demo_plan import display_faces, room_timeline
from render_engine.jobs.room_animation_job import (read_json, write_json, digest, confined, check_guards,
                                effect_state, requests, verified_record, png_ok, phase_name, verify_nvidia_renderer)


def independent_camera(scene: object, name: str, position: list, target: list, ortho: bool, span: float) -> object:
    """Shared camera() MUTATES scene.camera; force a fresh object/data/target here."""
    scene.camera=None
    obj=camera(scene,position,target,ortho,span)
    obj.name=name; obj.data.name=name+'_Data'; obj.constraints[0].target.name=name+'_Target'
    obj.data.dof.use_dof=False
    return obj


def camera_parameters(obj: object) -> dict:
    tracks=[c for c in obj.constraints if c.type=='TRACK_TO']
    if len(tracks)!=1 or tracks[0].target is None:raise ValueError('One valid TRACK_TO target required')
    track=tracks[0]; data=obj.data
    return {'object':obj.name,'data':data.name,'type':data.type,'position':list(obj.matrix_world.translation),
            'rotation_world_euler':list(obj.matrix_world.to_euler()),'rotation_local_euler':list(obj.rotation_euler),
            'target_object':track.target.name,'target':list(track.target.location),
            'track_axis':track.track_axis,'up_axis':track.up_axis,'lens':data.lens,'ortho_scale':data.ortho_scale,
            'clip_start':data.clip_start,'clip_end':data.clip_end,'dof':data.dof.use_dof,
            'sensor_width':data.sensor_width,'sensor_fit':data.sensor_fit}


def activate_camera(scene: object, cameras: dict, mode: str) -> dict:
    if mode not in ('overview','closeup'):raise ValueError('Unknown camera mode')
    overview,close=cameras['overview'],cameras['closeup']
    if overview==close or overview.data==close.data or overview.constraints[0].target==close.constraints[0].target:
        raise ValueError('Overview and closeup must have independent objects, data and targets')
    scene.camera=cameras[mode]
    bpy.context.view_layer.update()
    result=camera_parameters(scene.camera)
    if scene.camera!=cameras[mode] or result['type']!=('ORTHO' if mode=='overview' else 'PERSP'):
        raise ValueError('Effective camera differs from requested mode')
    return {'camera_mode':mode,**result}


def fit_overview(scene: object, obj: object, coverage_points: list, margin: float=.04) -> dict:
    """Only enlarge orthographic scale if needed; retain round-three pose/target.

    Use actual Blender view_frame/aspect, rather than guessing whether scale is
    the horizontal or vertical extent. Coverage concerns room and peak flames,
    not guaranteed unobstructed visibility or all dissipating smoke wisps.
    """
    original=obj.data.ortho_scale
    def project() -> list:
        corners=obj.data.view_frame(scene=scene)
        xmin,xmax=min(p.x for p in corners),max(p.x for p in corners)
        ymin,ymax=min(p.y for p in corners),max(p.y for p in corners)
        inverse=obj.matrix_world.inverted()
        local=[inverse @ Vector(p) for p in coverage_points]
        if any(not obj.data.clip_start<=-p.z<=obj.data.clip_end for p in local):
            raise ValueError('Overview coverage lies outside clipping depth')
        return [((p.x-xmin)/(xmax-xmin),(p.y-ymin)/(ymax-ymin)) for p in local]
    uv=project(); factor=max(max(abs(u-.5),abs(v-.5)) for u,v in uv)/(.5-margin)
    if factor>1:
        obj.data.ortho_scale=original*factor*1.002
        bpy.context.view_layer.update(); uv=project()
    passed=all(margin-1e-5<=u<=1-margin+1e-5 and margin-1e-5<=v<=1-margin+1e-5 for u,v in uv)
    if not passed:raise ValueError('Room/flame framing check failed')
    return {'passed':passed,'point_count':len(coverage_points),'margin':margin,
            'baseline_ortho_scale':original,'effective_ortho_scale':obj.data.ortho_scale,
            'scale_enlarged':obj.data.ortho_scale>original+1e-5,
            'projected_min':[min(p[k] for p in uv) for k in (0,1)],'projected_max':[max(p[k] for p in uv) for k in (0,1)],
            'scope':'Reviewed polygon floor/wall display envelope and all 13 peak flame envelopes; not an occlusion test'}


def prepare(spec: dict) -> tuple:
    inputs=spec['inputs']; a=spec['animation']; timings={}
    check_guards(inputs)
    before=time.perf_counter()
    bpy.ops.wm.open_mainfile(filepath=str(Path(inputs['asset'])/'room.blend'))
    timings['asset_load_seconds']=time.perf_counter()-before
    before=time.perf_counter(); scene=bpy.context.scene
    import json
    metadata=json.loads(scene['room_asset_metadata']); floor=metadata['floor_z']; polygon=metadata['polygon_raw_xy']
    points=json.loads(Path(inputs['points']).read_text(encoding='utf-8'))
    timeline=room_timeline(points,metadata['interior_devices'],22,inputs['style']['events']['layer_seconds'])
    if timeline!=inputs['timeline']:raise ValueError('Blend membership and reviewed candidate timeline differ')
    source=bpy.data.objects['RoomSource']; faces=mesh_faces(source)
    selected,groups=display_faces(faces,a['drop_components'])
    source.hide_render=True; source.hide_viewport=True
    materials={m.name:m for m in bpy.data.materials}
    display=make_mesh('RoomDisplay',below(selected,floor+a['wall_height']),materials)
    for i,mat in enumerate(display.data.materials):
        copied=mat.copy(); copied.use_backface_culling=False; display.data.materials[i]=copied
    lo=[min(p[k] for p in polygon) for k in (0,1)]; hi=[max(p[k] for p in polygon) for k in (0,1)]
    cx,cy=[(lo[k]+hi[k])/2 for k in (0,1)]; span=max(hi[k]-lo[k] for k in (0,1))
    config=deepcopy(inputs['style']); config['quality']['fps']=a['fps']; config['quality']['resolution']=a['resolution']
    actual=configure_render(scene,config); actual['fps_base']=checked(scene.render,'fps_base',1.0)
    actual['lighting']=lighting(scene,[cx,cy,floor+.4],span,config)
    effects=add_fire(scene,timeline,points,floor,[display,bpy.data.objects['DemoFloorApproximation']],config,closest_hit)
    actual['effects']=effects
    marker_bindings=0
    for marker in scene.timeline_markers:
        if marker.camera is not None:marker.camera=None; marker_bindings+=1
    overview=independent_camera(scene,'Room8_Overview',(cx+span*.5,cy-span*.65,floor+span*.95),(cx,cy,floor+.3),True,span)
    anchor=next(p for p in effects['anchors'] if p['device']==22)
    p=next(p for p in points if int(p['device'])==22)['pose']['translation']
    close=config['art']['closeup']; base=anchor['display_fire_base_z']
    closeup=independent_camera(scene,'Room8_Closeup22',(p['x']+close['offset'][0],p['y']+close['offset'][1],base+close['offset'][2]),
                   (p['x'],p['y'],base+close['target_height']),False,span)
    closeup.data.lens=close['lens']
    coverage=[(p[0],p[1],z) for p in polygon for z in (floor,floor+a['wall_height'])]
    for cluster in effects['clusters']:
        obj=bpy.data.objects[cluster['flame_object']]
        padding=max(t['height'] for t in cluster['tongues'])*math.sin(config['art']['flame']['sway_radians'])
        for corner in obj.bound_box:
            # Scale/radian motion maximum from the unchanged round-three envelope.
            for sx in (-1,1):
                for sy in (-1,1):
                    for sz in (-1,1):
                        coverage.append((obj.location.x+corner[0]+sx*padding,obj.location.y+corner[1]+sy*padding,
                                         obj.location.z+corner[2]*(1+config['art']['flame']['flicker_amplitude']*.5)+sz*padding))
    cameras={'overview':overview,'closeup':closeup}
    fit=fit_overview(scene,overview,coverage)
    actual['camera_setup']={'camera_mode':a['camera_mode'],'overview':camera_parameters(overview),
        'closeup':camera_parameters(closeup),'overview_coverage':fit,'cleared_marker_camera_bindings':marker_bindings}
    actual['camera_setup']['selected']=activate_camera(scene,cameras,a['camera_mode'])
    scene.frame_start=1; scene.frame_end=a['frame_count']
    bpy.context.view_layer.update()
    timings['effects_and_scene_init_seconds']=time.perf_counter()-before
    timings['simulation_cache_seconds']=0.0
    timings['cache_note']='No simulation bake; procedural effects and absolute-time curves only'
    actual['components']=groups; actual['display_cut_z']=floor+a['wall_height']
    return scene,config,effects,cameras,actual,timings


def apply_absolute(scene: object, config: dict, effects: dict, timeline: dict, frame: int) -> None:
    """Seek first, then explicitly set every effect from absolute time (no accumulation)."""
    scene.frame_set(frame)
    seconds=(frame-1)/scene.render.fps; starts={e['point']:e['time'] for e in timeline['spread_events']}
    anchors={p['device']:p for p in effects['anchors']}
    for cluster in effects['clusters']:
        device=cluster['device']; phase=cluster['phase']
        state=effect_state(config,seconds,starts[device],phase,cluster['primary'])
        flame=bpy.data.objects[cluster['flame_object']]; smoke=bpy.data.objects[cluster['smoke_object']]
        flame.scale=state['flame_scale']; flame.rotation_euler=state['flame_rotation']
        smoke.scale=(state['smoke']['radius'],state['smoke']['radius'],state['smoke']['height'])
        smoke.location.z=anchors[device]['display_fire_base_z']+state['smoke']['emitter_offset']
        bpy.data.lights['FireLight_'+str(device)].energy=state['light_energy']
        for obj,is_smoke,material_phase in ((flame,False,phase),(smoke,True,phase+2)):
            nodes=obj.data.materials[0].node_tree.nodes; style=config['art']['smoke' if is_smoke else 'flame']
            nodes['DensityEnvelope'].outputs[0].default_value=state['smoke']['density'] if is_smoke else state['density']
            if not is_smoke:nodes['EmissionEnvelope'].outputs[0].default_value=state['emission']
            nodes['EffectNoise'].inputs['W'].default_value=material_phase+seconds*style['morph_speed']
            nodes['EffectFlow'].inputs[1].default_value=(material_phase*.17,material_phase*.11,-seconds*style['flow_speed'])
    bpy.context.view_layer.update()


def renderer_info() -> dict:
    """Optional GPU-context evidence, independent from nvidia-smi availability."""
    try:
        import gpu
        result={name:getattr(gpu.platform,name+'_get')() for name in
                ('renderer','vendor','version','device_type','backend_type')}
        result['available']=True
        result['software_rendering_suspected']=(result['device_type']=='SOFTWARE' or
            any(word in str(result['renderer']).lower() for word in ('llvmpipe','softpipe','software')))
        return result
    except (ImportError,AttributeError,RuntimeError,ValueError,SystemError) as exc:
        return {'available':False,'reason':type(exc).__name__+': '+str(exc)}


def run(job: Path, attempt: str, launch_monotonic: float) -> None:
    spec=read_json(job/'config_snapshot.json'); work=confined(job,'attempts/'+attempt)
    if not work.is_dir():raise ValueError('Launcher attempt directory required')
    descriptor=int(os.environ.get('ROOM_ANIMATION_LOCK_FD','-1'))
    lock=Path(spec['inputs']['points']).parent.parent/'.room_animation_gpu.lock'
    if descriptor<3 or (os.fstat(descriptor).st_dev,os.fstat(descriptor).st_ino)!=(lock.stat().st_dev,lock.stat().st_ino):
        raise ValueError('Inherited GPU lock required; use run_room_animation.py')
    old=read_json(job/'render_manifest.json') if (job/'render_manifest.json').exists() else {}
    records={r['path']:r for r in old.get('frames',[])}
    timings={'blender_startup_and_import_seconds':ENTRY_MONOTONIC-launch_monotonic}
    before=time.perf_counter()
    scene,config,effects,cameras,actual,prep=prepare(spec); timings.update(prep)
    timings['worker_prepare_seconds']=time.perf_counter()-before
    write_json(job/'effective_settings.json',actual)
    write_json(job/'room_timeline.json',spec['inputs']['timeline'])
    manifest={'schema_version':1,'signature':spec['signature'],'technical_complete':False,'worker_complete':False,
              'frozen_style_revision':3,'frames':list(records.values()),'timeline':spec['inputs']['timeline'],
              'absolute_time_state':True,'boundary_volume_clipping':False,
              'note':'Centers follow reviewed interior membership; effect envelopes are not geometrically clipped to room walls. Visual boundary review remains required.'}
    manifest['camera_mode']=spec['animation']['camera_mode']; manifest['camera_setup']=actual['camera_setup']
    rendered=0; reused=0
    for request in requests(spec):
        existing=verified_record(job,request,records,spec['animation']['resolution'])
        if existing:
            reused+=1; continue
        target=confined(job,request['path'])
        copied='copy_from' in request
        if copied:
            shutil.copyfile(confined(job,request['copy_from']),target)
            elapsed=0.0; effective=deepcopy(records[request['copy_from']]['effective']); state_seconds=0.0
        else:
            state_start=time.perf_counter()
            apply_absolute(scene,config,effects,spec['inputs']['timeline'],request['frame'])
            active_camera=activate_camera(scene,cameras,request['camera'])
            state_seconds=time.perf_counter()-state_start
            temp=confined(work,target.name)
            if temp.exists():raise ValueError('Attempt staging file already exists')
            scene.render.filepath=str(temp)
            start=time.perf_counter(); started_at=datetime.now(timezone.utc).isoformat()
            bpy.ops.render.render(write_still=True)
            elapsed=time.perf_counter()-start
            if 'renderer' not in timings:
                timings['renderer']=renderer_info()
                manifest['renderer']=timings['renderer']
                write_json(work/'renderer.json',timings['renderer'])
                write_json(job/'render_manifest.json',manifest)
                print('[room-animation] renderer='+str(timings['renderer']),flush=True)
                if spec['animation'].get('require_nvidia_graphics'):
                    verify_nvidia_renderer(timings['renderer'])
            if not png_ok(temp,spec['animation']['resolution']):raise ValueError('Invalid/incomplete PNG: '+str(temp))
            if target.exists():raise ValueError('Refusing to overwrite an existing frame')
            final_camera={'camera_mode':request['camera'],**camera_parameters(scene.camera)}
            if scene.camera!=cameras[request['camera']] or final_camera['type']!=active_camera['type']:
                raise ValueError('Camera changed during rendering')
            temp.replace(target); effective=snapshot_settings(scene); effective['camera']=final_camera; rendered+=1
        record={**request,'render_seconds':elapsed,'sha256':digest(target),'copied':copied,
                'state_update_seconds':state_seconds,'phase':phase_name(request['seconds']),'attempt':attempt,'effective':effective}
        if not copied:record['started_at']=started_at
        records[request['path']]=record; manifest['frames']=list(records.values())
        write_json(job/'render_manifest.json',manifest)
        write_json(job/'status.json',{'state':'rendering','attempt':attempt,'completed_outputs':len(records),
                                    'last_output':request['path'],'worker_pid':__import__('os').getpid()})
        print(f'[room-animation] output={request["path"]} frame={request["frame"]} time={request["seconds"]:.3f} render_seconds={elapsed:.3f}',flush=True)
    reference=spec['inputs'].get('camera_reference')
    if spec['animation']['stage']=='camera_check' and reference and spec['animation']['camera_mode']=='overview':
        original=reference['camera']; current=manifest['camera_setup']['overview']
        copied_reference=job/'reference_overview_3.5s.png'; shutil.copyfile(reference['image'],copied_reference)
        comparison={'reference_image_sha256':reference['sha256'],'reference_camera':original,'animation_camera':current,
                    'same_type':original['type']==current['type'],
                    'same_position':max(abs(a-b) for a,b in zip(original['position'],current['position']))<1e-4,
                    'same_target':max(abs(a-b) for a,b in zip(original['target'],current['target']))<1e-4,
                    'same_ortho_scale':abs(original['ortho_scale']-current['ortho_scale'])<1e-4,
                    'coverage':actual['camera_setup']['overview_coverage'],'human_composition_review_required':True}
        if not all(comparison[k] for k in ('same_type','same_position','same_target')):
            raise ValueError('Animation overview differs from round-three reference pose/type')
        manifest['camera_comparison']=comparison
        write_json(job/'camera_comparison.json',comparison)
        (job/'camera_comparison.html').write_text(
            '<!doctype html><meta charset="utf-8"><title>Room8 camera comparison</title>'
            '<style>body{background:#222;color:white;font:16px sans-serif}main{display:flex;gap:12px}figure{margin:0;width:49%}img{width:100%}</style>'
            '<h1>Room8 / 3.5s / overview</h1><main><figure><figcaption>Round-three reference</figcaption>'
            '<img src="reference_overview_3.5s.png"></figure><figure><figcaption>Animation overview (fixed)</figcaption>'
            '<img src="keyframes/overview_3.5s.png"></figure></main>',encoding='utf-8')
    check_guards(spec['inputs']); manifest['guarded_files_unchanged']=True; manifest['worker_complete']=True
    manifest['frames']=list(records.values()); write_json(job/'render_manifest.json',manifest)
    timings['new_rendered_outputs']=rendered; timings['reused_outputs']=reused
    if 'renderer' not in timings:
        timings['renderer']=old.get('renderer') or {'available':False,'reason':'All frames reused; no rendering performed in this attempt'}
        if spec['animation'].get('require_nvidia_graphics'):verify_nvidia_renderer(timings['renderer'])
    manifest['renderer']=timings['renderer']; write_json(job/'render_manifest.json',manifest)
    write_json(work/'worker_timing.json',timings)
    print(f'[room-animation] worker_complete=true rendered={rendered} reused={reused}',flush=True)


def main() -> None:
    parser=argparse.ArgumentParser(description='F8-E worker; use the safe Python launcher')
    parser.add_argument('--job',type=Path,required=True); parser.add_argument('--attempt',required=True)
    parser.add_argument('--launch-monotonic',type=float,required=True)
    args=parser.parse_args(sys.argv[sys.argv.index('--')+1:])
    try:run(args.job.resolve(),args.attempt,args.launch_monotonic)
    except Exception:
        work=confined(args.job,'attempts/'+args.attempt)
        (work/'failure_worker.log').write_text(traceback.format_exc(),encoding='utf-8')
        raise


if __name__=='__main__':main()
