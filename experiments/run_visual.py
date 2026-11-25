"""Independent experiment planner/guarded launcher; default never starts Blender."""
import argparse
from copy import deepcopy
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import uuid

from experiments.continuous_field import field_from_config,inside
from experiments.visual_state import geometry,validate,camera_view_audit
from render_engine.jobs.operation_logging import JsonlSink,bind_context,stage,child_environment
from render_engine.jobs.room_animation_job import fingerprint,check_guards,load_camera_reference

ROOT=Path(__file__).resolve().parents[1]
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def read(path):return json.loads(Path(path).read_text(encoding='utf-8'))


from render_engine.jobs.operation_logging import traced


@traced('room.continuous.camera','verify_formal_v1_camera')
def load_formal_v1_camera(directory,asset,expected_snapshot_sha256):
    """Use final-frame effective records, never substitute the R3 sample camera."""
    directory=Path(directory).resolve(strict=True);asset=Path(asset)
    paths={name:directory/name for name in ('config_snapshot.json','render_manifest.json','effective_settings.json','video_receipt.json')}
    if not expected_snapshot_sha256 or sha(paths['config_snapshot.json'])!=expected_snapshot_sha256:
        raise ValueError('Formal V1 snapshot fingerprint differs')
    spec=read(paths['config_snapshot.json']);unsigned=dict(spec);signature=unsigned.pop('signature')
    if fingerprint(unsigned)!=signature:raise ValueError('Formal V1 snapshot signature differs')
    animation=spec['animation']
    if any(animation.get(k)!=v for k,v in {'stage':'final','preset':'final','camera_mode':'overview','fps':24,'frame_count':576,'duration_seconds':24,'resolution':[1280,720]}.items()):
        raise ValueError('Not the reviewed formal V1 task')
    # Bind the locally mapped asset by content, not by the server's absolute path.
    blend_hash=sha(asset/'room.blend')
    guards=spec['inputs']['guards']
    if not any(Path(p).name=='room.blend' and h==blend_hash for p,h in guards.items()):
        raise ValueError('Formal V1 uses another base asset')
    manifest=read(paths['render_manifest.json'])
    if manifest.get('signature')!=signature:raise ValueError('V1 manifest belongs to another snapshot')
    frames=[r for r in manifest['frames'] if r['path'].startswith('frames/')]
    if len(frames)!=576 or len({r['path'] for r in frames})!=576:raise ValueError('Incomplete formal V1 frame evidence')
    keys=('type','position','target','lens','ortho_scale','clip_start','clip_end','sensor_width','sensor_fit','dof','track_axis','up_axis','rotation_world_euler')
    def camera(record):
        value={k:record[k] for k in keys}
        if value['type']!='ORTHO' or value['dof'] is not False:raise ValueError('Unexpected V1 projection or depth of field')
        if value['track_axis']!='TRACK_NEGATIVE_Z' or value['up_axis']!='UP_Y':raise ValueError('Unsupported V1 camera axes')
        if value['sensor_fit'] not in ('AUTO','HORIZONTAL','VERTICAL'):raise ValueError('Invalid V1 sensor fit')
        for name in ('position','target','rotation_world_euler'):
            if len(value[name])!=3 or not all(math.isfinite(float(v)) for v in value[name]):raise ValueError('Invalid V1 camera vector')
        if sum((a-b)**2 for a,b in zip(value['position'],value['target']))<1e-8:raise ValueError('Invalid V1 camera aim')
        for name in ('lens','ortho_scale','clip_start','clip_end','sensor_width'):
            if not math.isfinite(float(value[name])) or value[name]<=0:raise ValueError('Invalid V1 camera scalar')
        if value['clip_end']<=value['clip_start']:raise ValueError('Invalid V1 clip range')
        return value
    effective=camera(frames[0]['effective']['camera'])
    if any(camera(r['effective']['camera'])!=effective for r in frames):raise ValueError('Formal V1 camera changes between frames')
    settings=read(paths['effective_settings.json'])
    if camera(settings['camera_setup']['overview'])!=effective or camera(manifest['camera_setup']['overview'])!=effective:
        raise ValueError('V1 setup and rendered camera differ')
    # Receipt is kept as provenance; do not infer camera pose from video metadata.
    read(paths['video_receipt.json'])
    return {'kind':'formal_v1_effective_frames','camera':effective,'verified_frame_count':576,
            'snapshot_signature':signature,'guards':{str(p):sha(p) for p in paths.values()}}

def projection_hits(candidate,x,y,ceiling):
    hits=[]
    for face in candidate['geometry']['faces']:
        a,b,c=[p[:3] for p in face['corners']]
        d=(b[1]-c[1])*(a[0]-c[0])+(c[0]-b[0])*(a[1]-c[1])
        if abs(d)<1e-12:continue
        u=((b[1]-c[1])*(x-c[0])+(c[0]-b[0])*(y-c[1]))/d
        v=((c[1]-a[1])*(x-c[0])+(a[0]-c[0])*(y-c[1]))/d
        if min(u,v,1-u-v)<-1e-9:continue
        z=u*a[2]+v*b[2]+(1-u-v)*c[2]
        if z<=ceiling:hits.append(z)
    return sorted(hits)

def prepare(config_path,candidate_path,asset,points,output_root,reference=None,v1_job=None):
    config_path=Path(config_path).resolve(strict=True);candidate_path=Path(candidate_path).resolve(strict=True)
    asset=Path(asset).resolve(strict=True);points=Path(points).resolve(strict=True);output_root=Path(output_root).resolve()
    config=read(config_path);validate(config);candidate=read(candidate_path);manifest=read(asset/'manifest.json')
    for name,expected in config['asset_binding'].items():
        if name not in ('manifest.json','room.blend','room.glb','validation.json','points.json'):raise ValueError('Unexpected asset binding')
        if sha(points if name=='points.json' else asset/name)!=expected:raise ValueError('Frozen input differs')
    if set(config['asset_binding'])!={'manifest.json','room.blend','room.glb','validation.json','points.json'}:raise ValueError('Missing frozen input binding')
    if sha(candidate_path)!=config['candidate_sha256'] or manifest['candidate_sha256']!=sha(candidate_path):raise ValueError('Candidate binding differs')
    if (candidate['scene_code'],candidate['room_id'])!=(config['scene_code'],config['room_id']) or candidate['ignition_device']!=22:raise ValueError('Namespace mismatch')
    if len(candidate['polygon_raw_xy'])!=11:raise ValueError('Expected reviewed Room8 boundary')
    if sha(points)!=manifest['source_fingerprints']['points.json']:raise ValueError('Points differ')
    for name in ('room.blend','room.glb','validation.json'):
        if sha(asset/name)!=manifest['artifacts'][name]:raise ValueError('Asset differs')
    validation=read(asset/'validation.json')
    if validation['status']!='passed' or not all(v is True for v in validation['checks'].values()):raise ValueError('Asset not validated')
    source=next(p['pose']['translation'] for p in read(points) if int(p['device'])==22)
    seed=[source['x'],source['y']]
    hits=projection_hits(candidate,*seed,candidate['floor_z']+1.15)
    if not hits or abs(hits[-1]-config['seed']['scan_surface_z_m'])>1e-6:raise ValueError('Seed surface projection differs')
    neighborhood=[]
    for dx in (-.2,0,.2):
        for dy in (-.2,0,.2):
            local=projection_hits(candidate,seed[0]+dx,seed[1]+dy,candidate['floor_z']+1.15)
            neighborhood.append({'offset_xy_m':[dx,dy],'inside_room':inside((seed[0]+dx,seed[1]+dy),candidate['polygon_raw_xy']),'surface_z_m':local[-1] if local else None})
    if any(abs(source[k]-config['seed']['raw_camera_xyz_m'][i])>1e-7 for i,k in enumerate(('x','y','z'))):raise ValueError('Seed binding differs')
    if abs(config['seed']['proposed_base_z_m']-config['seed']['scan_surface_z_m']-config['seed']['proposed_surface_offset_m'])>1e-8:raise ValueError('Seed projection arithmetic differs')
    # Geometry projection is a candidate, not a material/collision clearance proof.
    field=field_from_config(config,candidate['polygon_raw_xy'],seed)
    guards={str(p):sha(p) for p in (candidate_path,points,config_path,*[p for p in asset.iterdir() if p.is_file()],*sorted((ROOT/'experiments').glob('*.py')),ROOT/'configs/render/room_fire_round3.json')}
    from render_engine.paths import source_paths
    guards.update({str(p):sha(p) for p in source_paths(ROOT).values()})
    camera_reference=None
    formal=(load_formal_v1_camera(v1_job,asset,config.get('formal_v1_snapshot_sha256')) if v1_job else None)
    if formal:guards.update(formal['guards'])
    if config['camera']=='v1':
        ref=load_camera_reference(asset,Path(reference) if reference else None,True)
        camera_reference=ref['camera'];guards.update(ref['guards'])
    elif config['camera']=='v1_final':
        if formal is None:raise ValueError('Formal V1 evidence required; R3 samples are not a substitute')
        camera_reference=formal['camera']
    elif config['camera']=='scenario':
        from experiments.scenario_timeline import validate_timeline
        validate_timeline(config)
        if formal is None:raise ValueError('Scenario requires formal V1 effective-camera evidence')
        camera_reference=formal['camera']
    elif config['camera'] not in ('low','roof'):raise ValueError('Unknown camera')
    audit_config=deepcopy(config)
    if audit_config['camera']=='scenario':audit_config['camera']='low'
    view_audit=(camera_view_audit(audit_config,seed,candidate['polygon_raw_xy'],candidate['geometry']['faces'])
                if config.get('require_clear_view') is True else None)
    if any(output_root.is_relative_to(p) or p.is_relative_to(output_root) for p in (asset.parent,points.parent)):
        raise ValueError('Output root must be separate from all source scene data')
    output_root.mkdir(parents=True,exist_ok=True)
    run=output_root/('a2-'+uuid.uuid4().hex);run.mkdir(exist_ok=False)
    snapshot={'schema_version':1,'experiment_id':run.name,'config':config,'config_path':str(config_path),'asset_blend':str(asset/'room.blend'),'data_root':str(points.parent.parent),
              'polygon':candidate['polygon_raw_xy'],'seed_xy':seed,'camera_reference':camera_reference,'r3_style':read(ROOT/'configs/render/room_fire_round3.json'),
              'guards':guards,'output':str(run),'reachable_cells':len(field.arrival_s),'unreachable_cells':len(field.unreachable),'scope':'independent_visual_experiment_not_r3_task',
              'seed_audit':{'nearest_surface_z_m':hits[-1],'neighborhood':neighborhood,'visual_collision_clearance_confirmed':False},'view_audit':view_audit}
    snapshot['r3_style']['quality']['resolution']=config['resolution'];snapshot['r3_style']['quality']['fps']=config['fps']
    snapshot['signature']=fingerprint(snapshot)
    (run/'snapshot.json').write_text(json.dumps(snapshot,indent=2),encoding='utf-8')
    if formal:
        low=config['cameras']['low'];base=config['seed']['proposed_base_z_m']
        plan={'first':{'kind':'ignition_perspective','position':[seed[0]+low['offset'][0],seed[1]+low['offset'][1],base+low['offset'][2]],
                       'target':[seed[0],seed[1],base+low['target_height']],'lens':low['lens']},
              'second':formal,'order':['first','second'],'transition_implemented':config['camera']=='scenario','rendered':False}
        (run/'camera-plan.json').write_text(json.dumps(plan,indent=2),encoding='utf-8')
    if config['camera']=='scenario':
        from experiments.scenario_timeline import scenario_report,script_text
        report=scenario_report(config,field,snapshot['polygon'],seed)
        (run/'scenario-script.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        (run/'scenario-script.txt').write_text(script_text(report),encoding='utf-8')
    # CPU-only evaluated geometry counts; no mesh/image files are fabricated.
    stats=[]
    for t in config['key_times_s']:
        state=geometry(field,snapshot['polygon'],config,t)
        stats.append({'seconds':t,'meshes':{name:{'vertices':len(v['vertices']),'faces':len(v['faces'])} for name,v in state.items()}})
    (run/'geometry-plan.json').write_text(json.dumps({'rendered':False,'samples':stats},indent=2),encoding='utf-8')
    check_guards({'guards':guards})
    return run,snapshot


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',type=Path,default=ROOT/'configs/experiments/room8_continuous_a_v02.json')
    for name in ('candidate','asset','points','output-root'):parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--reference-samples',type=Path)
    parser.add_argument('--v1-job',type=Path,help='Read-only formal V1 evidence directory; never a R3 sample directory')
    parser.add_argument('--render-keyframes',action='store_true');parser.add_argument('--confirm-gpu-experiment',action='store_true')
    parser.add_argument('--blender',default='blender')
    args=parser.parse_args(argv)
    config=read(args.config)
    if args.render_keyframes and (not args.confirm_gpu_experiment or config.get('render_authorized') is not True):
        parser.error('GPU rendering needs separately approved config and explicit confirmation; default is plan only')
    trace='a2-'+uuid.uuid4().hex
    with bind_context(trace_id=trace),stage('room.continuous.experiment','prepare_plan'):
        run,snapshot=prepare(args.config,args.candidate,args.asset,args.points,args.output_root,args.reference_samples,args.v1_job)
    if not args.render_keyframes:
        print(json.dumps({'output':str(run),'rendered':False,'reachable_cells':snapshot['reachable_cells']}),flush=True);return 0
    from render_engine.jobs.run_room_animation import gpu_lock,busy_processes
    with bind_context(trace_id=trace,sink=JsonlSink(run/'operations')),stage('room.continuous.experiment','keyframe_render'):
        with gpu_lock(Path(snapshot['data_root'])) as fd:
            checks=busy_processes()
            if not all(v.get('available') for v in checks.values()):raise RuntimeError('GPU occupancy evidence unavailable')
            check_guards({'guards':snapshot['guards']})
            env=dict(os.environ);env.update(child_environment())
            env['ROOM_ANIMATION_LOCK_FD']=str(fd)
            with (run/'blender.log').open('xb') as log:
                subprocess.run([args.blender,'--background','--factory-startup','--disable-autoexec','--python-exit-code','1','--python',str(ROOT/'experiments/blender_worker.py'),'--','--snapshot',str(run/'snapshot.json')],env=env,pass_fds=(fd,),stdout=log,stderr=subprocess.STDOUT,check=True)
            check_guards({'guards':snapshot['guards']})
    print(json.dumps({'output':str(run),'rendered':True}),flush=True);return 0

if __name__=='__main__':raise SystemExit(main())
