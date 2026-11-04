"""PRD 2.3 / architecture 3.3: file-only animation contracts, timing and gates.

Stdlib only; no bpy, database, network or rendering side effects on import.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path
import statistics
import struct
import uuid

if __package__:
    from .room_fire_config import curve_value, smoke_state, load_config
    from .room_demo_plan import room_timeline
else:
    from room_fire_config import curve_value, smoke_state, load_config
    from room_demo_plan import room_timeline


REVIEW_CHECKS=('visual_matches_round3','ignition_and_bfs','flame_smoke_continuity',
               'late_smoke','no_geometry_or_boundary_artifacts','camera_and_lighting_stable',
               'performance_budget_accepted')
CODE_FILES=('run_room_animation.py','room_animation_job.py','F8_room_animation.py',
            'F8_room_demo.py','F8_room_fire_style.py','room_fire_config.py',
            'room_demo_plan.py','F8_prepare_room_asset.py')
APPROVED_STYLE_FINGERPRINT='599020bd89f3f8a961ee039ca664feb1598961c162949238153e8beb5857a6ae'


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding='utf-8'))


def write_json(path: Path, value: object) -> None:
    temporary=path.with_name(path.name+'.tmp')
    temporary.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    temporary.replace(path)


def digest(path: Path) -> str:
    h=hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda:source.read(1024*1024),b''):h.update(block)
    return h.hexdigest()


def fingerprint(value: object) -> str:
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def confined(root: Path, relative: str) -> Path:
    path=(root/relative).resolve()
    if not path.is_relative_to(root.resolve()) or path==root.resolve():raise ValueError('Output escapes job directory')
    return path


def full_duration(config: dict, timeline: dict) -> int:
    last=max(e['time'] for e in timeline['spread_events'])
    end=max(config['events']['fire_curve'][-1][0],config['art']['smoke']['density_curve'][-1][0])
    return math.ceil(last+end)+1  # One second after all effect envelopes reach zero.


def preflight(asset: Path, points: Path, config: Path, code_root: Path,
              reference_manifest: Path | None=None, require_reference: bool=False) -> dict:
    asset=asset.resolve(); points=points.resolve(); config=config.resolve()
    style=load_config(config)
    if style['art'].get('revision')!=3:raise ValueError('Animation baseline must be round three')
    if fingerprint(style)!=APPROVED_STYLE_FINGERPRINT:raise ValueError('Frozen round-three configuration differs; a new visual review is required')
    manifest=read_json(asset/'manifest.json'); validation=read_json(asset/'validation.json')
    if manifest['room_id']!='Room8' or validation['status']!='passed' or not validation['checks'] or not all(validation['checks'].values()):
        raise ValueError('Validated Room8 asset required')
    guards={str(p.resolve()):digest(p) for p in asset.iterdir() if p.is_file()}
    for name,h in manifest['artifacts'].items():
        path=confined(asset,name)
        if digest(path)!=h:raise ValueError('Base asset fingerprint mismatch: '+name)
    candidate=asset.parent/'candidate.json'
    if digest(candidate)!=manifest['candidate_sha256']:raise ValueError('Candidate fingerprint mismatch')
    if digest(points)!=manifest['source_fingerprints']['points.json']:raise ValueError('Point fingerprint mismatch')
    guards[str(candidate)]=digest(candidate); guards[str(points)]=digest(points); guards[str(config)]=digest(config)
    for name in (*manifest['source_fingerprints'],'output.mp4','timeline.json'):
        path=points.parent/name
        if path.resolve().parent!=points.parent:raise ValueError('Invalid source filename')
        if path.is_file():
            current=digest(path)
            if name in manifest['source_fingerprints'] and current!=manifest['source_fingerprints'][name]:
                raise ValueError('Source changed since asset validation: '+name)
            guards[str(path.resolve())]=current
    payload=read_json(candidate)
    interior=payload['interior_devices']; ignition=payload['ignition_device']
    if len(interior)!=13 or len(set(interior))!=13 or ignition!=22 or set(interior)&{32,42}:
        raise ValueError('Reviewed 13-point Room8 membership / ignition required')
    timeline=room_timeline(json.loads(points.read_text(encoding='utf-8')),interior,ignition,style['events']['layer_seconds'])
    if len(timeline['spread_events'])!=13 or timeline['unreachable_interior_devices']:
        raise ValueError('All 13 interior points must be reachable')
    if max(e['time'] for e in timeline['spread_events'])!=3:
        raise ValueError('Reviewed Room8 activation schedule changed; review duration/stage model first')
    codes={name:digest(code_root/name) for name in CODE_FILES}
    guards.update({str((code_root/name).resolve()):h for name,h in codes.items()})
    result={'asset':str(asset),'points':str(points),'config':str(config),'style':style,
            'guards':guards,'timeline':timeline,'codes':codes}
    result['camera_reference']=load_camera_reference(asset,reference_manifest,require_reference)
    if result['camera_reference']:
        guards.update(result['camera_reference']['guards'])
    return result


def load_camera_reference(asset: Path, manifest_path: Path | None, required: bool) -> dict | None:
    """Read verified round-three overview evidence; never edit source samples."""
    choices=([manifest_path.resolve()] if manifest_path is not None else
             sorted((asset.parent/'style_round3').glob('*/sample_manifest.json'),key=lambda p:p.stat().st_mtime,reverse=True))
    errors=[]
    for path in choices:
        try:
            requested=path.parent/'requested_config.json'
            if fingerprint(read_json(requested))!=APPROVED_STYLE_FINGERPRINT:raise ValueError('Reference style differs')
            samples=read_json(path)['samples']
            sample=next(s for s in samples if s['image']=='overview_3.5s.png')
            image=confined(path.parent,sample['image'])
            if digest(image)!=sample['sha256'] or sample['effective']['camera']['type']!='ORTHO' or not png_ok(image,[960,540]):
                raise ValueError('Reference image fingerprint or camera differs')
            repair=path.parent/'repair_report.json'; guards={str(p):digest(p) for p in (path,requested,image)}
            if not repair.exists() or read_json(repair).get('base_room_sha256')!=digest(asset/'room.blend'):
                raise ValueError('Reference must bind the same base room asset')
            guards[str(repair)]=digest(repair)
            return {'manifest':str(path),'image':str(image),'sha256':sample['sha256'],
                    'camera':sample['effective']['camera'],'guards':guards}
        except (OSError,ValueError,KeyError,StopIteration) as exc:errors.append(str(exc))
    if required or manifest_path is not None:
        raise ValueError('Verified round-three overview reference required; use --reference-samples. '+str(errors))
    return None


def check_guards(inputs: dict) -> None:
    for name,h in inputs['guards'].items():
        if digest(Path(name))!=h:raise ValueError('Protected input changed: '+name)


def build_spec(inputs: dict, stage: str, preset: str='test', wall_height: float=1.1,
               drops: list[int] | None=None, camera_mode: str='overview') -> dict:
    if stage not in ('camera_check','short','final') or preset not in ('test','final'):raise ValueError('Invalid stage/preset')
    if camera_mode not in ('overview','closeup'):raise ValueError('Invalid camera mode')
    if stage in ('camera_check','short') and preset!='test':raise ValueError('Camera/short baseline is 960x540 / 12fps')
    if not math.isfinite(wall_height) or not .3<=wall_height<=2.4:raise ValueError('Invalid display wall height')
    fps,resolution=(12,[960,540]) if preset=='test' else (24,[1280,720])
    duration=0 if stage=='camera_check' else 4 if stage=='short' else full_duration(inputs['style'],inputs['timeline'])
    animation={'stage':stage,'preset':preset,'fps':fps,'resolution':resolution,'duration_seconds':duration,
               'frame_count':1 if stage=='camera_check' else duration*fps,'camera_mode':camera_mode,
               'wall_height':wall_height,'drop_components':sorted(set(drops or []))}
    spec={'schema_version':1,'inputs':inputs,'animation':animation}
    spec['signature']=fingerprint(spec)
    return spec


def create_job(root: Path, spec: dict) -> Path:
    root.mkdir(parents=True,exist_ok=True)
    run_id=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_'+uuid.uuid4().hex[:8]
    job=root/run_id; job.mkdir(exist_ok=False)
    for name in ('frames','keyframes','attempts'):confined(job,name).mkdir()
    write_json(job/'config_snapshot.json',spec)
    write_json(job/'status.json',{'state':'created','run_id':run_id})
    return job


def check_resume(job: Path, spec: dict) -> None:
    if read_json(job/'config_snapshot.json')!=spec:raise ValueError('Resume config, inputs or code differs')
    if read_json(job/'status.json')['state']=='awaiting_visual_review':raise ValueError('Completed job needs review, not resume')


def effect_state(config: dict, seconds: float, start: float, phase: float, primary: bool) -> dict:
    """Absolute-time state, algebraically identical to approved style keyframes.

    No accumulators, random calls, frame history or simulation cache.
    """
    age=seconds-start; f=config['art']['flame']
    a=curve_value(config['events']['fire_curve'],age)
    flicker=1+f['flicker_amplitude']*(.65*math.sin(2*math.pi*f['flicker_hz']*max(0,age)+phase)+
                .35*math.sin(2*math.pi*f['flicker_hz']*.61*max(0,age)+phase*1.7))
    return {'density':f['density']*a,'emission':f['emission']*a*flicker,'light_energy':f['light_energy']*a*flicker,
            'flame_scale':[.35+.65*a,.35+.65*a,(.04+.96*a)*(1+(flicker-1)*.5)],
            'flame_rotation':[f['sway_radians']*math.sin(age*5+phase),f['sway_radians']*math.cos(age*4+phase),0],
            'smoke':smoke_state(config,age,primary)}


def phase_name(seconds: float) -> str:
    # Labels are presentation stages for this frozen 0/1.5/3s Room8 timeline.
    for end,name in ((1.5,'ignition'),(3,'secondary_ignition'),(6,'growth'),(11,'flame_decay'),(23,'residual_smoke')):
        if seconds<end:return name
    return 'cleared'


def requests(spec: dict) -> list[dict]:
    a=spec['animation']; fps=a['fps']; count=a['frame_count']
    mode=a['camera_mode']
    if a['stage']=='camera_check':
        name='overview' if mode=='overview' else 'closeup_22'
        return [{'path':f'keyframes/{name}_3.5s.png','frame':round(3.5*fps)+1,'seconds':3.5,'camera':mode,'kind':'camera_check'}]
    result=[{'path':f'frames/frame_{frame:06d}.png','frame':frame,'seconds':(frame-1)/fps,
             'camera':mode,'kind':'video'} for frame in range(1,count+1)]
    times=[1,3.5,6]
    if a['stage']=='short':times+= [5.5,6.5,10,16,23]
    for seconds in sorted(set(times)):
        for camera in ('overview','closeup') if seconds in (1,3.5,6) else ('overview',):
            frame=round(seconds*fps)+1
            label='closeup_22' if camera=='closeup' else 'overview'
            item={'path':f'keyframes/{label}_{seconds:g}s.png','frame':frame,'seconds':seconds,'camera':camera,'kind':'keyframe'}
            if camera==mode and frame<=count:item['copy_from']=f'frames/frame_{frame:06d}.png'
            result.append(item)
    return result


def png_ok(path: Path, resolution: list[int]) -> bool:
    try:
        with path.open('rb') as f:
            header=f.read(24); f.seek(-12,2); tail=f.read(12)
        return (header[:8]==b'\x89PNG\r\n\x1a\n' and header[12:16]==b'IHDR' and
                list(struct.unpack('>II',header[16:24]))==resolution and tail[4:8]==b'IEND')
    except (OSError,struct.error):return False


def verified_record(job: Path, request: dict, records: dict, resolution: list[int]) -> dict | None:
    path=confined(job,request['path']); record=records.get(request['path'])
    if not path.exists():return None
    if not record or any(record[key]!=request[key] for key in ('frame','seconds','camera','kind')) or not png_ok(path,resolution) or digest(path)!=record['sha256']:
        raise ValueError('Unverified/corrupt existing frame retained; use a new job: '+request['path'])
    return record


def frame_stats(records: list[dict]) -> dict:
    values=sorted(r['render_seconds'] for r in records if not r.get('copied'))
    if not values:return {'count':0}
    return {'count':len(values),'mean_seconds':statistics.mean(values),'median_seconds':statistics.median(values),
            'p90_seconds':values[math.ceil(.9*len(values))-1],'max_seconds':max(values),'sum_seconds':sum(values),
            'first_record_seconds':next(r['render_seconds'] for r in records if not r.get('copied'))}


def summarize(records: list[dict], spec: dict) -> dict:
    main=[r for r in records if r['kind']=='video']; groups=defaultdict(list)
    for record in records:
        if record['camera']=='overview' and not record.get('copied'):groups[phase_name(record['seconds'])].append(record)
    return {'video_frames':frame_stats(main),'extra_keyframes':frame_stats([r for r in records if r['kind']!='video']),
            'overview_stages':{name:frame_stats(items) for name,items in groups.items()},
            'video_frame_count':0 if spec['animation']['stage']=='camera_check' else spec['animation']['frame_count']}


def verify_effective_cameras(records: list[dict], spec: dict) -> None:
    for record in records:
        if record['kind'] not in ('video','camera_check'):continue
        actual=(record.get('effective') or {}).get('camera') or {}
        mode=spec['animation'].get('camera_mode',spec['animation'].get('camera','overview'))
        if (record['camera']!=mode or actual.get('camera_mode')!=mode or not actual.get('object') or
            actual.get('type')!=('ORTHO' if mode=='overview' else 'PERSP')):
            raise ValueError('Effective rendered camera does not match task camera_mode')


def estimate_full(stats: dict, spec: dict, prep_seconds: float, encode_seconds: float) -> dict:
    if spec['animation']['camera_mode']!='overview':return {'status':'not_applicable_to_overview','reason':'Closeup timings cannot estimate overview performance'}
    mean=stats['video_frames'].get('mean_seconds')
    if mean is None:return {'status':'not_measured'}
    # Empirical phase means where available; absent phases use observed P90 conservatively.
    fallback=stats['video_frames']['p90_seconds']; stages=stats['overview_stages']
    phases=[('ignition',1.5),('secondary_ignition',1.5),('growth',3),('flame_decay',5),('residual_smoke',12),('cleared',1)]
    weighted=sum(stages.get(name,{}).get('mean_seconds',fallback)*duration for name,duration in phases)/24
    missing=[name for name,_ in phases if name not in stages]
    source_pixels=math.prod(spec['animation']['resolution'])
    candidates=[]
    for fps,res in ((12,[960,540]),(24,[1280,720])):
        ratio=math.prod(res)/source_pixels; count=24*fps
        lower=min(mean,weighted)*count*ratio
        upper=max(weighted,fallback,stats['video_frames']['max_seconds'])*count*ratio
        candidates.append({'fps':fps,'resolution':res,'duration_seconds':24,'frames':count,
            'heuristic_render_seconds_range':[lower,upper],
            'heuristic_total_seconds_range':[lower+prep_seconds+encode_seconds,upper+prep_seconds+encode_seconds]})
    return {'status':'extrapolated_not_measured','candidates':candidates,'unmeasured_stages':missing,
            'note':'24s requires actual last activation=3s and smoke lifetime=20s. Some late stages have only one sample; these are heuristic scenarios, not confidence intervals. Pixel scaling is a heuristic; FPS changes frame count. Short encoding cost is only a placeholder for full encoding. No 20-minute guarantee.'}


def encoding_command(job: Path, target: Path, spec: dict) -> list[str]:
    a=spec['animation']
    return ['ffmpeg','-hide_banner','-loglevel','warning','-nostdin','-n','-framerate',str(a['fps']),
            '-start_number','1','-i',str(job/'frames/frame_%06d.png'),'-frames:v',str(a['frame_count']),
            '-c:v','libx264','-preset','medium','-crf','20','-threads','2','-pix_fmt','yuv420p',
            '-movflags','+faststart',str(target)]


def verify_video(probe: dict, spec: dict) -> dict:
    streams=[s for s in probe['streams'] if s.get('codec_type')=='video']
    if len(streams)!=1:raise ValueError('Exactly one video stream required')
    s=streams[0]; a=spec['animation']; duration=float(probe['format']['duration'])
    if ([s['width'],s['height']]!=a['resolution'] or Fraction(s['avg_frame_rate'])!=a['fps'] or
        int(s['nb_read_frames'])!=a['frame_count'] or abs(duration-a['duration_seconds'])>1/a['fps']+.001 or
        s['codec_name']!='h264' or s['pix_fmt']!='yuv420p'):raise ValueError('Encoded video differs from job contract')
    return {'duration_seconds':duration,'frames':int(s['nb_read_frames']),'resolution':[s['width'],s['height']],
            'fps':str(s['avg_frame_rate']),'codec':s['codec_name'],'pixel_format':s['pix_fmt']}


def review_binding(spec: dict) -> str:
    a=spec['animation']
    display={key:a[key] for key in ('wall_height','drop_components')}
    display['camera_mode']=a.get('camera_mode',a.get('camera','overview'))
    return fingerprint({'inputs':spec['inputs'],'display':display})


def historical_summary(job: Path) -> dict:
    """Read-only extraction, including legacy incorrectly labelled overview frames."""
    manifest=read_json(job/'render_manifest.json')
    timing=read_json(job/'timing_report.json') if (job/'timing_report.json').is_file() else {}
    video=manifest.get('video') or {}
    frames=[r for r in manifest.get('frames',[]) if r.get('kind')=='video']
    cameras=[r.get('effective',{}).get('camera',{}) for r in frames]
    types=sorted({c.get('type','unrecorded') for c in cameras})
    labelled=sorted({r.get('camera','unrecorded') for r in frames})
    mismatch='overview' in labelled and any(c.get('type')!='ORTHO' for c in cameras)
    return {'source':str(job.resolve()),'read_only':True,'measured_video_frames':len(frames),
            'video_frames':timing.get('frames',{}).get('video_frames',frame_stats(frames)),
            'extra_keyframes':timing.get('frames',{}).get('extra_keyframes'),
            'encoding_seconds':timing.get('encoding_seconds_original',video.get('encoding_seconds')),
            'total_seconds':timing.get('total_seconds_this_attempt'),'blender':timing.get('blender'),
            'gpu':timing.get('gpu'),'video':{k:v for k,v in video.items() if k!='encoding_command'},
            'labelled_camera_modes':labelled,'actual_camera_types':types,'actual_first_camera':cameras[0] if cameras else None,
            'camera_mismatch':mismatch,'usable_as_overview_performance_baseline':not mismatch and bool(cameras) and types==['ORTHO'],
            'note':'Preserve original timings. A mislabelled perspective/software run is not an overview/L20 performance measurement. No new overview estimate is inferred.'}


def approval_template(job: Path, spec: dict) -> dict:
    evidence=('config_snapshot.json','render_manifest.json','timing_report.json','fire_short.mp4')
    return {'approved':False,'reviewer':'','reviewed_at':'','source_job':str(job.resolve()),
            'binding':review_binding(spec),'evidence':{name:digest(job/name) for name in evidence},
            'checks':{name:False for name in REVIEW_CHECKS},'approved_final_presets':[],'notes':''}


def verify_approval(path: Path, root: Path, spec: dict) -> dict:
    approval=read_json(path); source=Path(approval['source_job']).resolve()
    if not source.is_relative_to(root.resolve()) or source.parent!=root.resolve():raise ValueError('Review source must be a sibling render job')
    if approval.get('approved') is not True or not approval.get('reviewer','').strip():raise ValueError('Explicit named human approval required')
    if datetime.fromisoformat(approval['reviewed_at'].replace('Z','+00:00')).tzinfo is None:
        raise ValueError('Review timestamp requires a timezone')
    if any(approval.get('checks',{}).get(name) is not True for name in REVIEW_CHECKS):raise ValueError('All visual/performance checks must be approved')
    if spec['animation']['preset'] not in approval.get('approved_final_presets',[]):raise ValueError('Final quality preset has not been approved')
    previous=read_json(source/'config_snapshot.json'); manifest=read_json(source/'render_manifest.json')
    if previous['animation']['stage']!='short' or read_json(source/'status.json')['state']!='awaiting_visual_review' or manifest.get('technical_complete') is not True:
        raise ValueError('Successful short job evidence required')
    verify_effective_cameras(manifest['frames'],previous)
    if approval['binding']!=review_binding(spec) or review_binding(previous)!=review_binding(spec):raise ValueError('Approved baseline, inputs, code or camera differs')
    for name in ('config_snapshot.json','render_manifest.json','timing_report.json','fire_short.mp4'):
        if digest(source/name)!=approval.get('evidence',{}).get(name):raise ValueError('Review evidence changed: '+name)
    records={r['path']:r for r in manifest['frames']}
    for request in requests(previous):
        if not verified_record(source,request,records,previous['animation']['resolution']):
            raise ValueError('Missing reviewed frame: '+request['path'])
    return approval
