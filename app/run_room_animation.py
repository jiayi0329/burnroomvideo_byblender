"""F8-E safe launcher: exclusive job, Blender subprocess, metrics, H.264 and review.

Run in the remote Linux app-server container. No bpy or database imports.
"""
from __future__ import annotations

import argparse
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import threading
import time
import traceback
import uuid

if __package__:
    from .room_animation_job import (preflight, build_spec, create_job, check_resume, check_guards,
        read_json, write_json, digest, confined, requests, verified_record, summarize, estimate_full,
        encoding_command, verify_video, approval_template, verify_approval, historical_summary, verify_effective_cameras, verify_nvidia_renderer)
else:
    from room_animation_job import (preflight, build_spec, create_job, check_resume, check_guards,
        read_json, write_json, digest, confined, requests, verified_record, summarize, estimate_full,
        encoding_command, verify_video, approval_template, verify_approval, historical_summary, verify_effective_cameras, verify_nvidia_renderer)


@contextmanager
def gpu_lock(data_root: Path) -> Iterator[int]:
    """Linux kernel lock, shared by all A-stage jobs, inherited by Blender.

    Conservatively reserve all visible GPUs: EEVEE graphics selection is not
    reliably controlled by CUDA_VISIBLE_DEVICES. Never unlink the lock inode.
    """
    import fcntl
    with (data_root/'.room_animation_gpu.lock').open('a+',encoding='utf-8') as handle:
        try:fcntl.flock(handle.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError as exc:raise RuntimeError('Another A-stage rendering task holds the GPU lock') from exc
        handle.seek(0); handle.truncate()
        json.dump({'pid':os.getpid(),'started_at':datetime.now(timezone.utc).isoformat(),'scope':'all_visible_gpus'},handle)
        handle.flush()
        # Closing releases only our reference; inherited worker reference keeps
        # the kernel lock held if this launcher is unexpectedly killed.
        yield handle.fileno()


def busy_processes() -> dict:
    local=[]
    for path in Path('/proc').glob('[0-9]*/comm'):
        try:
            if path.read_text().strip().lower().startswith('blender'):local.append(int(path.parent.name))
        except (OSError,ValueError):continue
    if local:raise RuntimeError('Existing Blender process(es), do not start a second task: '+str(local))
    checks={}
    for name,command in (
        ('compute',['nvidia-smi','--query-compute-apps=pid,process_name','--format=csv,noheader,nounits']),
        ('graphics_and_compute',['nvidia-smi','pmon','-c','1'])):
        try:
            result=subprocess.run(command,capture_output=True,text=True,timeout=10)
            checks[name]={'available':result.returncode==0,'output':result.stdout.strip(),'error':result.stderr.strip()}
        except (FileNotFoundError,subprocess.TimeoutExpired) as exc:
            checks[name]={'available':False,'error':type(exc).__name__}; continue
        if result.returncode:continue
        for line in result.stdout.splitlines():
            if name=='compute' and line.split(',')[0].strip().isdigit():raise RuntimeError('GPU compute process already running: '+line)
            fields=line.split()
            if name=='graphics_and_compute' and len(fields)>2 and fields[0].isdigit() and fields[1].isdigit() and any(c in fields[2] for c in ('G','C')):
                raise RuntimeError('GPU graphics/compute process already running: '+line)
    return checks


def gpu_sample() -> dict:
    command=['nvidia-smi','--query-gpu=index,uuid,utilization.gpu,memory.used,memory.total,temperature.gpu',
             '--format=csv,noheader,nounits']
    try:
        result=subprocess.run(command,capture_output=True,text=True,timeout=5)
        if result.returncode:return {'available':False,'reason':result.stderr.strip()}
        rows=[]
        for line in result.stdout.splitlines():
            values=[v.strip() for v in line.split(',')]
            rows.append({'index':int(values[0]),'uuid':values[1],'util_pct':float(values[2]),
                         'memory_used_mb':float(values[3]),'memory_total_mb':float(values[4]),'temperature_c':float(values[5])})
        return {'available':bool(rows),'gpus':rows}
    except (OSError,ValueError,IndexError,subprocess.TimeoutExpired) as exc:return {'available':False,'reason':type(exc).__name__}


def stop_child(process: subprocess.Popen) -> None:
    if process.poll() is None:
        process.terminate()
        try:process.wait(timeout=5)
        except subprocess.TimeoutExpired:process.kill(); process.wait(timeout=10)


def monitor_gpu(stop: threading.Event, process: subprocess.Popen, path: Path, samples: list, thermal: dict) -> None:
    while not stop.is_set():
        sample={'at':datetime.now(timezone.utc).isoformat(),**gpu_sample()}; samples.append(sample)
        with path.open('a',encoding='utf-8') as stream:stream.write(json.dumps(sample)+'\n')
        temperatures=[g['temperature_c'] for g in sample.get('gpus',[])]
        if temperatures and max(temperatures)>=85:
            print(f'[room-animation] gpu_temperature_warning={max(temperatures)}',flush=True)
        if temperatures and max(temperatures)>=90:
            thermal['terminated']=True; stop_child(process); return
        stop.wait(5)


def encode(job: Path, attempt_dir: Path, spec: dict) -> tuple[dict,float,float]:
    name='fire_short.mp4' if spec['animation']['stage']=='short' else 'fire_final.mp4'
    final=job/name; receipt=job/'video_receipt.json'
    if final.exists():
        if not receipt.exists() or read_json(receipt)['sha256']!=digest(final):raise ValueError('Unverified existing video retained; start new job')
        return read_json(receipt),0.0,0.0
    records={r['path']:r for r in read_json(job/'render_manifest.json')['frames']}
    verify_effective_cameras(list(records.values()),spec)
    for request in requests(spec):
        if not verified_record(job,request,records,spec['animation']['resolution']):raise ValueError('Missing frame: '+request['path'])
    temporary=attempt_dir/name; command=encoding_command(job,temporary,spec)
    before=time.perf_counter()
    with (attempt_dir/'encode.log').open('w',encoding='utf-8') as stream:
        subprocess.run(command,stdout=stream,stderr=subprocess.STDOUT,check=True)
    encoding_seconds=time.perf_counter()-before
    before=time.perf_counter()
    probe_command=['ffprobe','-v','error','-count_frames','-show_streams','-show_format','-of','json',str(temporary)]
    probe=json.loads(subprocess.run(probe_command,capture_output=True,text=True,check=True).stdout)
    actual=verify_video(probe,spec); probe_seconds=time.perf_counter()-before
    before=time.perf_counter()
    decode_command=['ffmpeg','-v','error','-xerror','-i',str(temporary),'-map','0:v:0','-f','null','-']
    with (attempt_dir/'decode.log').open('w',encoding='utf-8') as stream:
        subprocess.run(decode_command,stdout=stream,stderr=subprocess.STDOUT,check=True)
    decode_seconds=time.perf_counter()-before
    if final.exists():raise ValueError('Refusing to overwrite existing video')
    temporary.replace(final)
    actual.update({'file':name,'bytes':final.stat().st_size,'sha256':digest(final),'encoding_command':command,
                   'encoding_seconds':encoding_seconds,'probe_seconds':probe_seconds,
                   'full_decode_passed':True,'decode_seconds':decode_seconds,'decode_command':decode_command})
    write_json(receipt,actual)
    return actual,encoding_seconds,probe_seconds


def execute(args: argparse.Namespace) -> Path:
    started=time.perf_counter(); code_root=Path(__file__).resolve().parent
    for tool in ('blender',) if args.stage=='camera_check' else ('blender','ffmpeg','ffprobe'):
        if not shutil.which(tool):raise RuntimeError('Required executable missing: '+tool)
    mode=getattr(args,'camera_mode','overview')
    inputs=preflight(args.asset,args.points,args.config,code_root,
                     reference_manifest=getattr(args,'reference_samples',None),require_reference=args.stage=='camera_check' and mode=='overview')
    spec=build_spec(inputs,args.stage,args.preset,args.wall_height,args.drop_component,
                    camera_mode=mode,direct_final=getattr(args,'direct_final',False))
    root=args.asset.resolve().parent.parent/'render_jobs'; data_root=args.points.resolve().parent.parent
    # Approval checked before creating a final directory or starting Blender.
    approval=None
    if getattr(args,'direct_final',False) and args.approval is not None:
        raise ValueError('Choose --direct-final or --approval, not both')
    if args.stage=='final' and not getattr(args,'direct_final',False):
        if args.approval is None:raise ValueError('Final rendering requires --approval from an explicitly reviewed short job')
        approval=verify_approval(args.approval,root,spec)
    with gpu_lock(data_root) as lock_fd:
        busy=busy_processes()
        if args.resume:
            job=args.resume.resolve()
            if job.parent!=root.resolve():raise ValueError('Resume directory must belong to this Room8 render_jobs')
            check_resume(job,spec)
        else:job=create_job(root,spec)
        attempt=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_'+uuid.uuid4().hex[:6]
        attempt_dir=confined(job,'attempts/'+attempt); attempt_dir.mkdir(exist_ok=False)
        if approval:write_json(attempt_dir/'approved_short_review.json',approval)
        print(f'[room-animation] job={job} attempt={attempt} stage={args.stage}',flush=True)
        write_json(job/'status.json',{'state':'preparing','attempt':attempt,'launcher_pid':os.getpid()})
        write_json(job/'timing_report.json',{'measurement_status':'incomplete','attempt':attempt})
        samples=[]; thermal={}; stop=threading.Event(); process=None; thread=None
        preparation=time.perf_counter()-started
        try:
            launch_monotonic=time.monotonic()
            command=['blender','--background','--factory-startup','--python-exit-code','1',
                     '--python',str(code_root/'F8_room_animation.py'),'--','--job',str(job),
                     '--attempt',attempt,'--launch-monotonic',str(launch_monotonic)]
            env=dict(os.environ); env['ROOM_ANIMATION_LOCK_FD']=str(lock_fd)
            write_json(attempt_dir/'launch.json',{'command':command,'gpu_conflict_checks':busy,'reservation':'all_visible_gpus'})
            with (attempt_dir/'blender.log').open('w',encoding='utf-8') as log:
                process=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT,env=env,pass_fds=(lock_fd,),start_new_session=True)
                thread=threading.Thread(target=monitor_gpu,args=(stop,process,job/'gpu_metrics.jsonl',samples,thermal),daemon=True)
                thread.start(); code=process.wait()
            process_seconds=time.monotonic()-launch_monotonic
            stop.set(); thread.join(timeout=6)
            if thermal.get('terminated'):raise RuntimeError('GPU >=90C: this job terminated; frames retained')
            if code:raise RuntimeError(f'Blender exited {code}; see {attempt_dir}/blender.log')
            manifest=read_json(job/'render_manifest.json')
            if manifest.get('worker_complete') is not True:raise RuntimeError('Worker did not finish all requested outputs')
            verify_effective_cameras(manifest['frames'],spec)
            worker=read_json(attempt_dir/'worker_timing.json')
            if spec['animation'].get('require_nvidia_graphics'):verify_nvidia_renderer(worker.get('renderer',{}))
            if args.stage=='camera_check':
                video=None; encoding_seconds=probe_seconds=0.0
            else:
                write_json(job/'status.json',{'state':'encoding','attempt':attempt})
                video,encoding_seconds,probe_seconds=encode(job,attempt_dir,spec)
            check_guards(inputs)
            stats=summarize(manifest['frames'],spec)
            prep=preparation+worker['blender_startup_and_import_seconds']+worker['worker_prepare_seconds']
            original_encoding=video['encoding_seconds'] if video else 0.0
            estimate=({'status':'not_requested','reason':'Final job records actual delivery timings; no performance pretest or estimate'}
                      if args.stage=='final' else estimate_full(stats,spec,prep,original_encoding))
            gpu_rows=[g for s in samples for g in s.get('gpus',[])]
            costs={'preparation':prep,'png_rendering':stats['video_frames'].get('sum_seconds',0)+stats['extra_keyframes'].get('sum_seconds',0),
                   'encoding':original_encoding}
            current_records=[r for r in manifest['frames'] if r.get('attempt')==attempt]
            current_render=sum(r['render_seconds'] for r in current_records)
            report={'measurement_status':'measured_remote_run','attempt':attempt,
                'launcher_preparation_seconds':preparation,'blender':worker,'blender_process_seconds':process_seconds,
                'frames':stats,'encoding_seconds_this_attempt':encoding_seconds,'ffprobe_seconds_this_attempt':probe_seconds,
                'state_update_seconds_this_attempt':sum(r.get('state_update_seconds',0) for r in current_records),
                'worker_non_render_overhead_seconds':max(0,process_seconds-worker['blender_startup_and_import_seconds']-worker['worker_prepare_seconds']-current_render),
                'encoding_seconds_original':original_encoding,'video':video,'camera_mode':spec['animation']['camera_mode'],
                'total_seconds_this_attempt':time.perf_counter()-started,
                'frame_timing_scope':'Frame records retain original timings when resumed; this-attempt total excludes historical attempts',
                'gpu':{'available':bool(gpu_rows),'sample_count':len(samples),'renderer':worker.get('renderer',{'available':False}),
                    'peak_memory_mb':max((g['memory_used_mb'] for g in gpu_rows),default=None),
                    'peak_util_pct':max((g['util_pct'] for g in gpu_rows),default=None),
                    'note':'Samples cover Blender, every ~5s; all visible GPU device totals, not exclusive per-process allocation'},
                'full_video_estimate':estimate,'review_required':True,
                'bottleneck_hint':max(costs,key=costs.get)}
            write_json(attempt_dir/'timing_report.json',report); write_json(job/'timing_report.json',report)
            manifest.update(technical_complete=True,video=video,guarded_files_unchanged=True,review_required=True,
                            authorization=spec['animation'].get('authorization',{'mode':'short_review' if approval else 'preview'}))
            write_json(job/'render_manifest.json',manifest)
            write_json(job/'status.json',{'state':'awaiting_visual_review','attempt':attempt,'automatic_final_render':False})
            if args.stage=='short':write_json(job/'approval_template.json',approval_template(job,spec))
            if video:
                print(f'[room-animation] done video={job/video["file"]} frames={video["frames"]} total_seconds={report["total_seconds_this_attempt"]:.3f} status=awaiting_visual_review',flush=True)
            else:
                print(f'[room-animation] camera_check={job/manifest["frames"][0]["path"]} total_seconds={report["total_seconds_this_attempt"]:.3f} status=awaiting_visual_review',flush=True)
            return job
        except BaseException as exc:
            if process is not None:stop_child(process)
            stop.set()
            if thread is not None:thread.join(timeout=6)
            failure={'state':'interrupted' if isinstance(exc,KeyboardInterrupt) else 'failed','attempt':attempt,
                     'error':str(exc),'elapsed_seconds_this_attempt':time.perf_counter()-started,'frames_retained':True}
            write_json(job/'status.json',failure); write_json(attempt_dir/'failure.json',failure)
            write_json(job/'timing_report.json',{'measurement_status':'incomplete',**failure})
            (attempt_dir/'failure.log').write_text(traceback.format_exc(),encoding='utf-8')
            print(f'[room-animation] failed job={job} frames_retained=true error={exc}',flush=True)
            raise


def main() -> None:
    parser=argparse.ArgumentParser(description='A-stage isolated Room8 animation, no legacy API')
    parser.add_argument('--asset',type=Path); parser.add_argument('--points',type=Path)
    parser.add_argument('--config',type=Path,default=Path(__file__).with_name('room_fire_round3.json'))
    parser.add_argument('--stage',choices=('camera_check','short','final'),default='camera_check')
    parser.add_argument('--camera-mode',choices=('overview','closeup'),default='overview')
    parser.add_argument('--reference-samples',type=Path)
    parser.add_argument('--report-job',type=Path,help='Read historical timing/camera evidence only; no GPU lock or render')
    parser.add_argument('--preset',choices=('test','final'),default='test')
    parser.add_argument('--approval',type=Path); parser.add_argument('--resume',type=Path)
    parser.add_argument('--direct-final',action='store_true',
                        help='Explicitly authorized 24s / 720p / 24fps overview delivery, without a short-job review file')
    parser.add_argument('--wall-height',type=float,default=1.1)
    parser.add_argument('--drop-component',type=int,action='append',default=[])
    args=parser.parse_args()
    if args.report_job:
        print(json.dumps(historical_summary(args.report_job),ensure_ascii=False,indent=2),flush=True)
        return
    if args.asset is None or args.points is None:parser.error('--asset and --points are required for rendering')
    execute(args)


if __name__=='__main__':main()
