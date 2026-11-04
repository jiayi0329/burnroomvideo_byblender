"""F8-E Blender worker: frozen round-three assets/style, absolute-time PNG frames.

Only run through run_room_animation.py; no video/API/DB entry point here.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import os
import shutil
import sys
import time
import traceback

ENTRY_MONOTONIC=time.monotonic()

import bpy
from mathutils import Vector

sys.path.insert(0,str(Path(__file__).resolve().parent))
from F8_room_demo import mesh_faces, camera, closest_hit
from F8_prepare_room_asset import below, make_mesh
from F8_room_fire_style import configure_render, lighting, add_fire, snapshot_settings, checked
from room_demo_plan import display_faces, room_timeline
from room_animation_job import (read_json, write_json, digest, confined, check_guards,
                                effect_state, requests, verified_record, png_ok, phase_name)


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
    overview=camera(scene,(cx+span*.5,cy-span*.65,floor+span*.95),(cx,cy,floor+.3),True,span)
    anchor=next(p for p in effects['anchors'] if p['device']==22)
    p=next(p for p in points if int(p['device'])==22)['pose']['translation']
    close=config['art']['closeup']; base=anchor['display_fire_base_z']
    closeup=camera(scene,(p['x']+close['offset'][0],p['y']+close['offset'][1],base+close['offset'][2]),
                   (p['x'],p['y'],base+close['target_height']),False,span)
    closeup.data.lens=close['lens']
    for cam in (overview,closeup):cam.data.dof.use_dof=False
    scene.frame_start=1; scene.frame_end=a['frame_count']
    bpy.context.view_layer.update()
    timings['effects_and_scene_init_seconds']=time.perf_counter()-before
    timings['simulation_cache_seconds']=0.0
    timings['cache_note']='No simulation bake; procedural effects and absolute-time curves only'
    actual['components']=groups; actual['display_cut_z']=floor+a['wall_height']
    return scene,config,effects,{'overview':overview,'closeup_22':closeup},actual,timings


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
    rendered=0; reused=0
    for request in requests(spec):
        existing=verified_record(job,request,records,spec['animation']['resolution'])
        if existing:
            reused+=1; continue
        target=confined(job,request['path'])
        copied='copy_from' in request
        if copied:
            shutil.copyfile(confined(job,request['copy_from']),target)
            elapsed=0.0; effective=None; state_seconds=0.0
        else:
            state_start=time.perf_counter()
            apply_absolute(scene,config,effects,spec['inputs']['timeline'],request['frame'])
            scene.camera=cameras[request['camera']]
            state_seconds=time.perf_counter()-state_start
            temp=confined(work,target.name)
            if temp.exists():raise ValueError('Attempt staging file already exists')
            scene.render.filepath=str(temp)
            start=time.perf_counter(); started_at=datetime.now(timezone.utc).isoformat()
            bpy.ops.render.render(write_still=True)
            elapsed=time.perf_counter()-start
            if 'renderer' not in timings:timings['renderer']=renderer_info()
            if not png_ok(temp,spec['animation']['resolution']):raise ValueError('Invalid/incomplete PNG: '+str(temp))
            if target.exists():raise ValueError('Refusing to overwrite an existing frame')
            temp.replace(target); effective=snapshot_settings(scene); rendered+=1
        record={**request,'render_seconds':elapsed,'sha256':digest(target),'copied':copied,
                'state_update_seconds':state_seconds,'phase':phase_name(request['seconds']),'attempt':attempt,'effective':effective}
        if not copied:record['started_at']=started_at
        records[request['path']]=record; manifest['frames']=list(records.values())
        write_json(job/'render_manifest.json',manifest)
        write_json(job/'status.json',{'state':'rendering','attempt':attempt,'completed_outputs':len(records),
                                    'last_output':request['path'],'worker_pid':__import__('os').getpid()})
        print(f'[room-animation] output={request["path"]} frame={request["frame"]} time={request["seconds"]:.3f} render_seconds={elapsed:.3f}',flush=True)
    check_guards(spec['inputs']); manifest['guarded_files_unchanged']=True; manifest['worker_complete']=True
    manifest['frames']=list(records.values()); write_json(job/'render_manifest.json',manifest)
    timings['new_rendered_outputs']=rendered; timings['reused_outputs']=reused
    if 'renderer' not in timings:
        timings['renderer']={'available':False,'reason':'All frames reused; no rendering performed in this attempt'}
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
