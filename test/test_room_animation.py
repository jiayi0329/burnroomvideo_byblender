"""PRD 2.3 / architecture 3.3: isolated animation, timing, encoding and review.

Stdlib fixtures + process/Blender/Linux-lock stand-ins; no actual GPU, Docker,
Blender, ffmpeg, network, DB or real scene writes. All files use TemporaryDirectory.
Run: python -m unittest test.test_room_animation -v
"""
import argparse
import ast
from copy import deepcopy
import json
import math
import os
from pathlib import Path
import struct
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zlib

from app import room_animation_job as jobs
from app import run_room_animation as launcher
from test import test_room_demo as demo


ROOT=Path(__file__).resolve().parents[1]


def png(width: int, height: int) -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data))
    header=struct.pack('>IIBBBBB',width,height,8,2,0,0,0)
    pixels=(b'\x00'+b'\x00'*(width*3))*height
    return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',header)+chunk(b'IDAT',zlib.compress(pixels))+chunk(b'IEND',b'')


class AnimationJobs(unittest.TestCase):
    def setUp(self) -> None:
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name); self.scene=self.root/'scene'; self.scene.mkdir()
        self.asset=self.scene/'rooms/Room8/version/asset'; self.asset.mkdir(parents=True)
        self.codes=self.root/'code'; self.codes.mkdir()
        for name in jobs.CODE_FILES:(self.codes/name).write_text('# fixture '+name,encoding='utf-8')
        self.config=self.root/'room_fire_round3.json'
        self.config.write_bytes((ROOT/'app/room_fire_round3.json').read_bytes())
        devices=[0,2,4,6,8,10,12,14,16,18,20,22,40]
        points=[{'id':str(d),'device':d,'visibles':['0'] if d==22 else
                 [str(i) for i in devices if i not in (0,22)] if d==0 else [],
                 'pose':{'translation':{'x':0,'y':0,'z':0}}} for d in devices]
        self.points=self.scene/'points.json'; jobs.write_json(self.points,points)
        (self.scene/'mesh.obj').write_text('original model',encoding='utf-8')
        (self.scene/'output.mp4').write_bytes(b'historical video')
        (self.scene/'timeline.json').write_text('{"original":true}',encoding='utf-8')
        (self.asset/'room.blend').write_bytes(b'independent room')
        jobs.write_json(self.asset.parent/'candidate.json',{'interior_devices':devices,'ignition_device':22})
        jobs.write_json(self.asset/'manifest.json',{'room_id':'Room8','candidate_sha256':jobs.digest(self.asset.parent/'candidate.json'),
            'source_fingerprints':{'points.json':jobs.digest(self.points),'mesh.obj':jobs.digest(self.scene/'mesh.obj')},
            'artifacts':{'room.blend':jobs.digest(self.asset/'room.blend')}})
        jobs.write_json(self.asset/'validation.json',{'status':'passed','checks':{'geometry':True,'uv':True}})
        self.inputs=jobs.preflight(self.asset,self.points,self.config,self.codes)
        self.spec=jobs.build_spec(self.inputs,'short')
        self.job_root=self.asset.parent.parent/'render_jobs'

    def new_job(self) -> Path:return jobs.create_job(self.job_root,self.spec)

    def test_short_is_exact_48_frames_and_keeps_frozen_style(self) -> None:
        self.assertEqual(self.spec['animation']['frame_count'],48)
        self.assertEqual(self.spec['animation']['fps'],12)
        self.assertEqual(self.spec['animation']['resolution'],[960,540])
        self.assertEqual(jobs.fingerprint(self.inputs['style']),jobs.APPROVED_STYLE_FINGERPRINT)
        requests=jobs.requests(self.spec); video=[r for r in requests if r['kind']=='video']
        self.assertEqual(len(video),48); self.assertEqual(video[0]['seconds'],0)
        self.assertAlmostEqual(video[-1]['seconds'],47/12)
        extra=[r for r in requests if r['kind']=='keyframe' and 'copy_from' not in r]
        self.assertEqual(len(extra),9)
        self.assertIn(23,[r['seconds'] for r in extra]); self.assertIn(16,[r['seconds'] for r in extra])

    def test_complete_duration_tracks_3s_activation_and_20s_smoke(self) -> None:
        self.assertEqual(jobs.full_duration(self.inputs['style'],self.inputs['timeline']),24)
        test=jobs.build_spec(self.inputs,'final','test'); final=jobs.build_spec(self.inputs,'final','final')
        self.assertEqual(test['animation']['frame_count'],288)
        self.assertEqual(final['animation']['frame_count'],576)
        with self.assertRaises(ValueError):jobs.build_spec(self.inputs,'short','final')
        modified=deepcopy(self.inputs['style']); modified['art']['smoke']['density_curve'][-1][0]=25
        self.assertEqual(jobs.full_duration(modified,self.inputs['timeline']),29)

    def test_preflight_guards_original_assets_history_and_code(self) -> None:
        jobs.check_guards(self.inputs)
        self.assertIn(str(self.scene/'output.mp4'),self.inputs['guards'])
        self.assertIn(str(self.scene/'timeline.json'),self.inputs['guards'])
        self.assertIn(str(self.codes/'F8_room_animation.py'),self.inputs['guards'])
        (self.scene/'output.mp4').write_bytes(b'changed externally')
        with self.assertRaisesRegex(ValueError,'Protected input'):jobs.check_guards(self.inputs)

    def test_frozen_style_and_input_mutations_are_rejected(self) -> None:
        c=jobs.read_json(self.config); c['art']['flame']['emission']=12; jobs.write_json(self.config,c)
        with self.assertRaisesRegex(ValueError,'Frozen'):jobs.preflight(self.asset,self.points,self.config,self.codes)
        self.config.write_bytes((ROOT/'app/room_fire_round3.json').read_bytes())
        (self.asset/'room.blend').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'fingerprint'):jobs.preflight(self.asset,self.points,self.config,self.codes)

    def test_unvalidated_base_and_doorway_membership_rejected(self) -> None:
        validation=self.asset/'validation.json'; jobs.write_json(validation,{'status':'passed','checks':{}})
        with self.assertRaisesRegex(ValueError,'Validated'):jobs.preflight(self.asset,self.points,self.config,self.codes)
        jobs.write_json(validation,{'status':'passed','checks':{'uv':True}})
        candidate=self.asset.parent/'candidate.json'; c=jobs.read_json(candidate); c['interior_devices'][-1]=32; jobs.write_json(candidate,c)
        manifest=jobs.read_json(self.asset/'manifest.json'); manifest['candidate_sha256']=jobs.digest(candidate)
        jobs.write_json(self.asset/'manifest.json',manifest)
        with self.assertRaisesRegex(ValueError,'membership'):jobs.preflight(self.asset,self.points,self.config,self.codes)

    def test_job_isolation_confinement_and_immutable_snapshot(self) -> None:
        before={name:jobs.digest(Path(name)) for name in self.inputs['guards']}
        first=self.new_job(); second=self.new_job()
        self.assertNotEqual(first,second); self.assertEqual(first.parent,self.job_root)
        self.assertEqual(jobs.read_json(first/'config_snapshot.json'),self.spec)
        with self.assertRaises(ValueError):jobs.confined(first,'../../output.mp4')
        with self.assertRaises(ValueError):jobs.confined(first,str(self.scene/'output.mp4'))
        self.assertEqual(before,{name:jobs.digest(Path(name)) for name in self.inputs['guards']})

    def test_resume_accepts_exact_inputs_rejects_drift_and_completed_job(self) -> None:
        job=self.new_job(); jobs.check_resume(job,self.spec)
        changed=deepcopy(self.spec); changed['animation']['wall_height']=1.2
        with self.assertRaises(ValueError):jobs.check_resume(job,changed)
        jobs.write_json(job/'status.json',{'state':'awaiting_visual_review'})
        with self.assertRaisesRegex(ValueError,'review'):jobs.check_resume(job,self.spec)

    def test_resume_reuses_verified_frame_and_retains_corruption(self) -> None:
        job=self.new_job(); request=jobs.requests(self.spec)[0]; path=job/request['path']
        path.write_bytes(png(960,540)); record={**request,'sha256':jobs.digest(path),'render_seconds':1}
        self.assertEqual(jobs.verified_record(job,request,{request['path']:record},[960,540]),record)
        with self.assertRaises(ValueError):jobs.verified_record(job,request,{},[960,540])
        path.write_bytes(b'broken'); before=path.read_bytes()
        with self.assertRaises(ValueError):jobs.verified_record(job,request,{request['path']:record},[960,540])
        self.assertEqual(path.read_bytes(),before)

    def test_percentiles_and_camera_specific_late_estimates_are_labelled(self) -> None:
        records=[{'render_seconds':i,'seconds':(i-1)/12,'kind':'video','camera':'overview'} for i in range(1,11)]
        stats=jobs.summarize(records,self.spec)
        self.assertEqual(stats['video_frames']['mean_seconds'],5.5)
        self.assertEqual(stats['video_frames']['median_seconds'],5.5)
        self.assertEqual(stats['video_frames']['p90_seconds'],9)
        self.assertEqual(stats['video_frames']['max_seconds'],10)
        estimate=jobs.estimate_full(stats,self.spec,10,2)
        self.assertEqual(estimate['status'],'extrapolated_not_measured')
        self.assertTrue(estimate['unmeasured_stages'])
        self.assertEqual(estimate['candidates'][1]['frames'],576)
        self.assertEqual(jobs.frame_stats([]),{'count':0})

    def probe(self) -> dict:
        return {'streams':[{'codec_type':'video','codec_name':'h264','pix_fmt':'yuv420p','width':960,'height':540,
                            'avg_frame_rate':'12/1','nb_read_frames':'48'}],'format':{'duration':'4.0'}}

    def test_encoding_contract_uses_pngs_h264_faststart_and_no_overwrite(self) -> None:
        job=self.new_job(); command=jobs.encoding_command(job,job/'attempts/clip.mp4',self.spec)
        self.assertEqual(command[0],'ffmpeg'); self.assertIn('-n',command); self.assertNotIn('-y',command)
        self.assertIn('libx264',command); self.assertIn('yuv420p',command); self.assertIn('+faststart',command)
        self.assertEqual(jobs.verify_video(self.probe(),self.spec)['frames'],48)
        for key,value in (('nb_read_frames','47'),('width',1280),('avg_frame_rate','24/1'),('codec_name','hevc')):
            probe=self.probe(); probe['streams'][0][key]=value
            with self.assertRaises(ValueError):jobs.verify_video(probe,self.spec)

    def populate_frames(self,job: Path) -> None:
        image=png(960,540); records=[]
        for request in jobs.requests(self.spec):
            path=job/request['path']; path.write_bytes(image)
            records.append({**request,'sha256':jobs.digest(path),'render_seconds':1,'copied':'copy_from' in request,
                            'effective':{'camera':{'object':'fixture_'+request['camera'],'camera_mode':request['camera'],
                                                   'type':'ORTHO' if request['camera']=='overview' else 'PERSP'}}})
        jobs.write_json(job/'render_manifest.json',{'frames':records})

    def test_encoder_isolated_success_and_failure_preserve_pngs(self) -> None:
        job=self.new_job(); self.populate_frames(job); attempt=job/'attempts/first'; attempt.mkdir()
        def fake_run(command: list,**kwargs: object) -> object:
            if command[0]=='ffmpeg' and command[-1]!='-':Path(command[-1]).write_bytes(b'encoded fixture')
            return SimpleNamespace(stdout=json.dumps(self.probe()),returncode=0)
        with patch.object(launcher.subprocess,'run',side_effect=fake_run):
            result,_,_=launcher.encode(job,attempt,self.spec)
        self.assertEqual(result['frames'],48); self.assertTrue((job/'fire_short.mp4').is_file())
        with patch.object(launcher.subprocess,'run',side_effect=AssertionError('must reuse verified video')):
            self.assertEqual(launcher.encode(job,attempt,self.spec)[0]['sha256'],result['sha256'])
        other=self.new_job(); self.populate_frames(other); failed=other/'attempts/failure'; failed.mkdir()
        original=(other/'frames/frame_000001.png').read_bytes()
        with patch.object(launcher.subprocess,'run',side_effect=subprocess.CalledProcessError(1,['ffmpeg'])):
            with self.assertRaises(subprocess.CalledProcessError):launcher.encode(other,failed,self.spec)
        self.assertEqual((other/'frames/frame_000001.png').read_bytes(),original)
        self.assertFalse((other/'fire_short.mp4').exists())

    def reviewed_job(self) -> tuple[Path,dict]:
        job=self.new_job(); jobs.write_json(job/'status.json',{'state':'awaiting_visual_review'})
        self.populate_frames(job)
        manifest=jobs.read_json(job/'render_manifest.json'); manifest['technical_complete']=True
        jobs.write_json(job/'render_manifest.json',manifest)
        jobs.write_json(job/'timing_report.json',{'measurement_status':'fixture'})
        (job/'fire_short.mp4').write_bytes(b'reviewed fixture')
        review=jobs.approval_template(job,self.spec)
        review.update(approved=True,reviewer='human tester',reviewed_at='2026-11-04T10:00:00+08:00',approved_final_presets=['test','final'])
        review['checks']={name:True for name in jobs.REVIEW_CHECKS}
        path=job/'approved.json'; jobs.write_json(path,review)
        return path,review

    def test_final_gate_requires_all_human_checks_and_matching_evidence(self) -> None:
        path,review=self.reviewed_job(); final=jobs.build_spec(self.inputs,'final','final')
        self.assertEqual(jobs.verify_approval(path,self.job_root,final)['reviewer'],'human tester')
        review['approved_final_presets']=['test']; jobs.write_json(path,review)
        with self.assertRaisesRegex(ValueError,'preset'):jobs.verify_approval(path,self.job_root,final)
        review['approved_final_presets']=['test','final']
        review['checks']['late_smoke']=False; jobs.write_json(path,review)
        with self.assertRaisesRegex(ValueError,'checks'):jobs.verify_approval(path,self.job_root,final)
        review['checks']['late_smoke']=True; jobs.write_json(path,review)
        (path.parent/'fire_short.mp4').write_bytes(b'tampered')
        with self.assertRaisesRegex(ValueError,'evidence'):jobs.verify_approval(path,self.job_root,final)

    def test_final_gate_rejects_code_or_camera_drift(self) -> None:
        path,_=self.reviewed_job(); final=jobs.build_spec(self.inputs,'final','test')
        final['animation']['wall_height']=1.2
        with self.assertRaisesRegex(ValueError,'differs'):jobs.verify_approval(path,self.job_root,final)
        final=jobs.build_spec(self.inputs,'final','test'); final['inputs']['codes']['F8_room_animation.py']='changed'
        with self.assertRaisesRegex(ValueError,'differs'):jobs.verify_approval(path,self.job_root,final)

    def test_review_gate_rechecks_actual_keyframe_bytes(self) -> None:
        path,_=self.reviewed_job(); final=jobs.build_spec(self.inputs,'final','test')
        (path.parent/'keyframes/overview_6s.png').write_bytes(b'changed image')
        with self.assertRaisesRegex(ValueError,'corrupt'):jobs.verify_approval(path,self.job_root,final)

    def launcher_fixture(self,code: int) -> tuple[object,object]:
        owner=self
        class Process:
            def __init__(self,command: list,**kwargs: object) -> None:
                job=Path(command[command.index('--job')+1]); attempt=command[command.index('--attempt')+1]
                owner.populate_frames(job)
                manifest=jobs.read_json(job/'render_manifest.json'); manifest['worker_complete']=True
                jobs.write_json(job/'render_manifest.json',manifest)
                jobs.write_json(job/'attempts'/attempt/'worker_timing.json',{
                    'blender_startup_and_import_seconds':.01,'worker_prepare_seconds':.01})
            def wait(self,**kwargs: object) -> int:return code
            def poll(self) -> int:return code
        def run(command: list,**kwargs: object) -> object:
            if command[0]=='ffmpeg' and command[-1]!='-':Path(command[-1]).write_bytes(b'video fixture')
            return SimpleNamespace(stdout=json.dumps(self.probe()),returncode=0)
        return Process,run

    def test_launcher_success_stops_at_review_with_measured_report(self) -> None:
        args=argparse.Namespace(asset=self.asset,points=self.points,config=self.config,stage='short',preset='test',
                                wall_height=1.1,drop_component=[],approval=None,resume=None)
        process,run=self.launcher_fixture(0)
        from contextlib import contextmanager
        @contextmanager
        def lock(root: Path):yield 5
        with patch.object(launcher.shutil,'which',return_value='fixture'),patch.object(launcher,'preflight',return_value=self.inputs),\
             patch.object(launcher,'gpu_lock',lock),patch.object(launcher,'busy_processes',return_value={}),\
             patch.object(launcher,'monitor_gpu',return_value=None),patch.object(launcher.subprocess,'Popen',side_effect=process) as child,\
             patch.object(launcher.subprocess,'run',side_effect=run):
            job=launcher.execute(args)
        self.assertEqual(child.call_count,1)
        self.assertEqual(jobs.read_json(job/'status.json')['state'],'awaiting_visual_review')
        self.assertFalse(jobs.read_json(job/'approval_template.json')['approved'])
        self.assertEqual(jobs.read_json(job/'timing_report.json')['measurement_status'],'measured_remote_run')
        self.assertFalse((job/'fire_final.mp4').exists())

    def test_launcher_failure_preserves_outputs_and_failure_report(self) -> None:
        args=argparse.Namespace(asset=self.asset,points=self.points,config=self.config,stage='short',preset='test',
                                wall_height=1.1,drop_component=[],approval=None,resume=None)
        process,run=self.launcher_fixture(1)
        from contextlib import contextmanager
        @contextmanager
        def lock(root: Path):yield 5
        with patch.object(launcher.shutil,'which',return_value='fixture'),patch.object(launcher,'preflight',return_value=self.inputs),\
             patch.object(launcher,'gpu_lock',lock),patch.object(launcher,'busy_processes',return_value={}),\
             patch.object(launcher,'monitor_gpu',return_value=None),patch.object(launcher.subprocess,'Popen',side_effect=process),\
             patch.object(launcher.subprocess,'run',side_effect=run):
            with self.assertRaisesRegex(RuntimeError,'Blender exited'):launcher.execute(args)
        job=next(self.job_root.iterdir())
        self.assertEqual(jobs.read_json(job/'status.json')['state'],'failed')
        self.assertEqual(jobs.read_json(job/'timing_report.json')['measurement_status'],'incomplete')
        self.assertTrue((job/'frames/frame_000001.png').is_file())
        self.assertTrue(list((job/'attempts').glob('*/failure.log')))

    def test_final_without_approval_does_not_create_output_or_launch(self) -> None:
        args=argparse.Namespace(asset=self.asset,points=self.points,config=self.config,stage='final',preset='final',
                                wall_height=1.1,drop_component=[],approval=None,resume=None)
        with patch.object(launcher.shutil,'which',return_value='fixture'),patch.object(launcher,'preflight',return_value=self.inputs),\
             patch.object(launcher.subprocess,'Popen',side_effect=AssertionError('must not launch')):
            with self.assertRaisesRegex(ValueError,'approval'):launcher.execute(args)
        self.assertFalse(self.job_root.exists())

    def test_existing_gpu_process_is_rejected_before_new_launch(self) -> None:
        with patch.object(Path,'glob',return_value=[]),patch.object(launcher.subprocess,'run',
                return_value=SimpleNamespace(returncode=0,stdout='1234, blender',stderr='')):
            with self.assertRaisesRegex(RuntimeError,'already running'):launcher.busy_processes()

    def test_missing_gpu_metrics_are_explicit_and_high_temperature_stops_only_child(self) -> None:
        with patch.object(launcher.subprocess,'run',side_effect=FileNotFoundError):self.assertFalse(launcher.gpu_sample()['available'])
        stop=__import__('threading').Event(); process=SimpleNamespace(); thermal={}; samples=[]
        with patch.object(launcher,'gpu_sample',return_value={'available':True,'gpus':[{'temperature_c':90}]}),\
             patch.object(launcher,'stop_child') as terminate:
            launcher.monitor_gpu(stop,process,self.root/'metrics.jsonl',samples,thermal)
        terminate.assert_called_once_with(process); self.assertTrue(thermal['terminated'])

    def test_kernel_lock_conflict_standin_and_lock_inode_not_removed(self) -> None:
        def flock(fd: int,flags: int) -> None:
            if getattr(flock,'held',False):raise BlockingIOError()
            flock.held=True
        fake=SimpleNamespace(flock=flock,LOCK_EX=1,LOCK_NB=2)
        with patch.dict('sys.modules',{'fcntl':fake}):
            with launcher.gpu_lock(self.root) as fd:
                os.fstat(fd)
                with self.assertRaisesRegex(RuntimeError,'lock'):
                    with launcher.gpu_lock(self.root):pass
        self.assertTrue((self.root/'.room_animation_gpu.lock').is_file())
        with self.assertRaises(OSError):os.fstat(fd)

    def test_worker_absolute_seek_matches_repeat_in_any_order(self) -> None:
        nodes,_=demo.DemoTests().volume(True,self.inputs['style'])
        flow=next(n for n in nodes if getattr(n,'name','')=='EffectFlow')
        self.assertEqual(len(flow.inputs[1].keys),2)
        tree=ast.parse((ROOT/'app/F8_room_animation.py').read_text(encoding='utf-8'))
        function=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='apply_absolute')
        def material() -> object:
            nodes={name:demo.Node('fixture') for name in ('DensityEnvelope','EmissionEnvelope','EffectNoise','EffectFlow')}
            return SimpleNamespace(node_tree=SimpleNamespace(nodes=nodes))
        flame=SimpleNamespace(data=SimpleNamespace(materials=[material()]))
        smoke=SimpleNamespace(data=SimpleNamespace(materials=[material()]),location=SimpleNamespace(z=0))
        light=SimpleNamespace(energy=0)
        bpy=SimpleNamespace(data=SimpleNamespace(objects={'flame':flame,'smoke':smoke},lights={'FireLight_22':light}),
                            context=SimpleNamespace(view_layer=SimpleNamespace(update=lambda:None)))
        scope={'bpy':bpy,'effect_state':jobs.effect_state}
        exec(compile(ast.Module(body=[function],type_ignores=[]),'absolute seek stand-in','exec'),scope)
        scene=SimpleNamespace(render=SimpleNamespace(fps=12),frame_set=lambda frame:None)
        effects={'anchors':[{'device':22,'display_fire_base_z':-1.35}],
                 'clusters':[{'device':22,'phase':.4,'primary':True,'flame_object':'flame','smoke_object':'smoke'}]}
        timeline={'spread_events':[{'point':22,'time':0}]}; apply=scope['apply_absolute']
        def state() -> tuple:return deepcopy((flame.scale,flame.rotation_euler,smoke.scale,smoke.location.z,light.energy,
                                             smoke.data.materials[0].node_tree.nodes['EffectNoise'].inputs['W'].default_value))
        apply(scene,self.inputs['style'],effects,timeline,43); expected=state()
        for frame in (277,1,73,13,43):apply(scene,self.inputs['style'],effects,timeline,frame)
        self.assertEqual(state(),expected)
        self.assertEqual(expected[-1],.4+2+3.5*self.inputs['style']['art']['smoke']['morph_speed'])

    def test_effect_state_is_history_free_and_smoke_outlasts_fire(self) -> None:
        style=self.inputs['style']; before=deepcopy(style)
        state=jobs.effect_state(style,3.5,0,.4,True)
        for t in (16,0,23,6,1):jobs.effect_state(style,t,0,.4,True)
        self.assertEqual(state,jobs.effect_state(style,3.5,0,.4,True)); self.assertEqual(style,before)
        late=jobs.effect_state(style,12,0,.4,True)
        self.assertEqual(late['emission'],0); self.assertGreater(late['smoke']['density'],0)

    def test_optional_gpu_renderer_evidence_identifies_software(self) -> None:
        tree=ast.parse((ROOT/'app/F8_room_animation.py').read_text(encoding='utf-8'))
        function=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='renderer_info')
        scope={}; exec(compile(ast.Module(body=[function],type_ignores=[]),'renderer evidence stand-in','exec'),scope)
        platform=SimpleNamespace(renderer_get=lambda:'llvmpipe',vendor_get=lambda:'Mesa',version_get=lambda:'fixture',
                                 device_type_get=lambda:'SOFTWARE',backend_type_get=lambda:'OPENGL')
        with patch.dict('sys.modules',{'gpu':SimpleNamespace(platform=platform)}):
            self.assertTrue(scope['renderer_info']()['software_rendering_suspected'])
        with patch.dict('sys.modules',{'gpu':SimpleNamespace(platform=SimpleNamespace())}):
            self.assertFalse(scope['renderer_info']()['available'])

    def test_animation_code_never_imports_legacy_or_database_and_prints_flush(self) -> None:
        for name in ('run_room_animation.py','room_animation_job.py','F8_room_animation.py'):
            source=(ROOT/'app'/name).read_text(encoding='utf-8'); tree=ast.parse(source)
            self.assertNotIn('F8_blender_render',source); self.assertNotIn('psycopg',source)
            if name!='F8_room_animation.py':self.assertNotIn('import bpy',source)
            for node in ast.walk(tree):
                if isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id=='print':
                    self.assertTrue(any(k.arg=='flush' and k.value.value is True for k in node.keywords))


if __name__=='__main__':unittest.main()
