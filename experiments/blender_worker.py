"""Future approved keyframes only; direct invocation without inherited lock fails."""
import argparse
import json
import os
from pathlib import Path
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from render_engine.jobs.room_animation_job import fingerprint,check_guards,verify_nvidia_renderer
from render_engine.jobs.operation_logging import JsonlSink,inherited_context,stage

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--snapshot',type=Path,required=True)
    args=parser.parse_args(sys.argv[sys.argv.index('--')+1:])
    snapshot=json.loads(args.snapshot.read_text());signature=snapshot.pop('signature')
    if fingerprint(snapshot)!=signature or snapshot['config'].get('render_authorized') is not True:raise ValueError('Unapproved/corrupt snapshot')
    if json.loads(Path(snapshot['config_path']).read_text())!=snapshot['config']:raise ValueError('Snapshot differs from guarded configuration')
    out=args.snapshot.resolve().parent
    if out!=Path(snapshot['output']).resolve():raise ValueError('Output binding differs')
    fd=int(os.getenv('ROOM_ANIMATION_LOCK_FD','-1'));lock=Path(snapshot['data_root'])/'.room_animation_gpu.lock'
    if fd<3 or (os.fstat(fd).st_dev,os.fstat(fd).st_ino)!=(lock.stat().st_dev,lock.stat().st_ino):raise ValueError('Inherited GPU lock required')
    check_guards({'guards':snapshot['guards']})
    import bpy
    from experiments.blender_visual import construct
    from render_engine.blender.F8_room_animation import renderer_info
    with inherited_context(JsonlSink(out/'operations')),stage('room.continuous.experiment','blender_keyframes'):
        scene,apply=construct(snapshot);records=[]
        for seconds in snapshot['config']['key_times_s']:
            check_guards({'guards':snapshot['guards']})
            path=out/('key-'+str(seconds)+'s.png')
            if path.exists():raise ValueError('Refuse overwrite')
            scene.frame_set(round(seconds*scene.render.fps)+1);apply(seconds);scene.render.filepath=str(path)
            start=time.perf_counter();bpy.ops.render.render(write_still=True)
            renderer=renderer_info();verify_nvidia_renderer(renderer)
            if not path.is_file():raise RuntimeError('Image missing')
            check_guards({'guards':snapshot['guards']})
            records.append({'seconds':seconds,'file':path.name,'render_seconds':time.perf_counter()-start,'renderer':renderer})
            (out/'render-receipt.json').write_text(json.dumps({'visual_approved':False,'frames':records},indent=2))

if __name__=='__main__':main()
