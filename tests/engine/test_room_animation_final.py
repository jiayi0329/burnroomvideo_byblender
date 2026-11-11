"""PRD 2.3 / architecture 3.3: explicitly authorized final delivery.

Offline process/encoder stand-ins, temporary synthetic frames only; no render,
network, database or original asset writes.
"""
import argparse
from contextlib import contextmanager
import json
from pathlib import Path
import subprocess
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from render_engine.jobs import room_animation_job as jobs
from render_engine.jobs import run_room_animation as launcher
from tests.engine import test_room_animation as fixtures


class FinalDelivery(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture=fixtures.AnimationJobs()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.f=self.fixture
        self.spec=jobs.build_spec(self.f.inputs,'final','final',direct_final=True)

    def frames(self,job: Path) -> None:
        image=fixtures.png(1280,720); records=[]
        for request in jobs.requests(self.spec):
            path=job/request['path']; path.write_bytes(image)
            records.append({**request,'sha256':jobs.digest(path),'render_seconds':.01,
                'effective':{'camera':{'object':'Room8_Overview','camera_mode':'overview','type':'ORTHO'}}})
        jobs.write_json(job/'render_manifest.json',{'frames':records,'worker_complete':True})

    def probe(self) -> dict:
        return {'streams':[{'codec_type':'video','codec_name':'h264','pix_fmt':'yuv420p',
            'width':1280,'height':720,'avg_frame_rate':'24/1','nb_read_frames':'576'}],
            'format':{'duration':'24.0'}}

    def test_direct_final_exact_delivery_and_frozen_style(self) -> None:
        a=self.spec['animation']; requests=jobs.requests(self.spec)
        self.assertEqual((a['duration_seconds'],a['fps'],a['resolution'],a['frame_count']),
                         (24,24,[1280,720],576))
        self.assertEqual(len(requests),576)
        self.assertTrue(all(r['camera']=='overview' and r['kind']=='video' for r in requests))
        self.assertEqual(requests[-1]['seconds'],575/24)
        self.assertEqual(jobs.fingerprint(self.spec['inputs']['style']),jobs.APPROVED_STYLE_FINGERPRINT)
        self.assertEqual(a['authorization']['mode'],'explicit_direct_final')

    def test_direct_flag_rejects_other_modes_and_quality(self) -> None:
        for stage,preset,mode in [('short','test','overview'),('final','test','overview'),('final','final','closeup')]:
            with self.assertRaisesRegex(ValueError,'Direct final'):
                jobs.build_spec(self.f.inputs,stage,preset,camera_mode=mode,direct_final=True)

    def test_resume_requires_same_authorization_and_config(self) -> None:
        job=jobs.create_job(self.f.job_root,self.spec)
        jobs.check_resume(job,self.spec)
        with self.assertRaisesRegex(ValueError,'differs'):
            jobs.check_resume(job,jobs.build_spec(self.f.inputs,'final','final'))
        self.frames(job)
        request=jobs.requests(self.spec)[0]
        record=jobs.read_json(job/'render_manifest.json')['frames'][0]
        self.assertEqual(jobs.verified_record(job,request,{request['path']:record},[1280,720]),record)

    def test_direct_launcher_no_short_gate_or_estimate_and_validates_video(self) -> None:
        owner=self
        class Process:
            def __init__(self,command: list,**kwargs: object) -> None:
                job=Path(command[command.index('--job')+1]); attempt=command[command.index('--attempt')+1]
                owner.frames(job)
                jobs.write_json(job/'attempts'/attempt/'worker_timing.json',
                    {'blender_startup_and_import_seconds':.01,'worker_prepare_seconds':.01,
                     'renderer':{'available':True,'vendor':'NVIDIA Corporation','renderer':'NVIDIA L20',
                                 'device_type':'NVIDIA','software_rendering_suspected':False}})
            def wait(self,**kwargs: object) -> int:return 0
            def poll(self) -> int:return 0
        def run(command: list,**kwargs: object) -> object:
            if command[0]=='ffmpeg' and command[-1]!='-':Path(command[-1]).write_bytes(b'encoded fixture')
            return SimpleNamespace(stdout=json.dumps(self.probe()),returncode=0)
        @contextmanager
        def lock(root: Path):yield 5
        args=argparse.Namespace(asset=self.f.asset,points=self.f.points,config=self.f.config,
            stage='final',preset='final',camera_mode='overview',direct_final=True,
            wall_height=1.1,drop_component=[],approval=None,resume=None)
        with patch.object(launcher.shutil,'which',return_value='fixture'),\
             patch.object(launcher,'preflight',return_value=self.f.inputs),\
             patch.object(launcher,'gpu_lock',lock),patch.object(launcher,'busy_processes',return_value={}) as busy,\
             patch.object(launcher,'monitor_gpu',return_value=None),\
             patch.object(launcher.subprocess,'Popen',side_effect=Process) as child,\
             patch.object(launcher.subprocess,'run',side_effect=run),\
             patch.object(launcher,'verify_approval',side_effect=AssertionError('no short gate')),\
             patch.object(launcher,'estimate_full',side_effect=AssertionError('no estimate')):
            job=launcher.execute(args)
        busy.assert_called_once(); self.assertEqual(child.call_count,1)
        receipt=jobs.read_json(job/'video_receipt.json')
        self.assertEqual(receipt['frames'],576); self.assertTrue(receipt['full_decode_passed'])
        self.assertTrue((job/'fire_final.mp4').exists())
        self.assertFalse((job/'approval_template.json').exists())
        self.assertTrue(jobs.read_json(job/'render_manifest.json')['technical_complete'])
        self.assertEqual(jobs.read_json(job/'timing_report.json')['full_video_estimate']['status'],'not_requested')
        self.assertEqual(jobs.read_json(job/'status.json')['state'],'awaiting_visual_review')
        jobs.check_guards(self.f.inputs)

    def test_decode_failure_retains_frames_without_publishing_final(self) -> None:
        job=jobs.create_job(self.f.job_root,self.spec); self.frames(job)
        attempt=job/'attempts/decode_failure'; attempt.mkdir()
        def run(command: list,**kwargs: object) -> object:
            if command[-1]=='-':raise subprocess.CalledProcessError(1,command)
            if command[0]=='ffmpeg':Path(command[-1]).write_bytes(b'broken encoded fixture')
            return SimpleNamespace(stdout=json.dumps(self.probe()),returncode=0)
        with patch.object(launcher.subprocess,'run',side_effect=run):
            with self.assertRaises(subprocess.CalledProcessError):launcher.encode(job,attempt,self.spec)
        self.assertFalse((job/'fire_final.mp4').exists())
        self.assertFalse((job/'video_receipt.json').exists())
        self.assertTrue((job/'frames/frame_000576.png').exists())
        self.assertTrue((attempt/'fire_final.mp4').exists())


if __name__=='__main__':unittest.main()
