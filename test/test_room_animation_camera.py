"""PRD 2.3 / architecture 3.3: camera alias regression and one-frame comparison.

Offline execution of the REAL legacy camera helper plus Blender stand-ins;
temporary synthetic samples only. No real Blender/GPU/DB/ffmpeg or scene writes.
Run: python -m unittest test.test_room_animation_camera -v
"""
import argparse
import ast
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from app import room_animation_job as jobs
from app import run_room_animation as launcher
from test import test_room_animation as animations


ROOT=Path(__file__).resolve().parents[1]


class Vec(list):
    x=property(lambda self:self[0]); y=property(lambda self:self[1]); z=property(lambda self:self[2])


class Matrix:
    def __init__(self,obj: object) -> None:self.obj=obj
    @property
    def translation(self) -> Vec:return Vec(self.obj.location)
    def inverted(self) -> 'Matrix':return self
    def to_euler(self) -> Vec:return Vec([0,0,0])
    def __matmul__(self,point: list) -> Vec:return Vec(point)  # Synthetic camera-space test points.


class Constraints(list):
    def new(self,kind: str) -> object:
        item=SimpleNamespace(type=kind,target=None); self.append(item); return item


class CameraData:
    def __init__(self,name: str) -> None:
        self.name=name; self.clip_end=1000; self.sensor_width=36; self.sensor_fit='AUTO'
        self.dof=SimpleNamespace(use_dof=False)
    def view_frame(self,scene: object) -> list:
        x=self.ortho_scale/2; y=x/(scene.render.resolution_x/scene.render.resolution_y)
        return [Vec([a*x,b*y,-1]) for a,b in ((-1,-1),(-1,1),(1,1),(1,-1))]


class CameraObject:
    def __init__(self,name: str,data: object) -> None:
        self.name=name; self.data=data; self.constraints=Constraints(); self.location=[0,0,0]
        self.rotation_euler=[0,0,0]; self.matrix_world=Matrix(self)


class CameraFix(unittest.TestCase):
    def fixture(self) -> object:
        value=animations.AnimationJobs(methodName='runTest'); value.setUp()
        self.addCleanup(value.doCleanups); return value

    def camera_scope(self) -> tuple:
        objects=[]
        bpy=SimpleNamespace(data=SimpleNamespace(objects=SimpleNamespace(new=CameraObject),
            cameras=SimpleNamespace(new=CameraData)),context=SimpleNamespace(view_layer=SimpleNamespace(update=lambda:None)))
        scene=SimpleNamespace(camera=None,collection=SimpleNamespace(objects=SimpleNamespace(link=objects.append)),
                              render=SimpleNamespace(resolution_x=960,resolution_y=540))
        old=ast.parse((ROOT/'app/F8_room_helpers.py').read_text(encoding='utf-8'))
        legacy=next(n for n in old.body if isinstance(n,ast.FunctionDef) and n.name=='camera')
        new=ast.parse((ROOT/'app/F8_room_animation.py').read_text(encoding='utf-8'))
        selected=[n for n in new.body if isinstance(n,ast.FunctionDef) and n.name in
                  ('independent_camera','camera_parameters','activate_camera','fit_overview')]
        future=ast.ImportFrom(module='__future__',names=[ast.alias(name='annotations')],level=0)
        scope={'bpy':bpy,'Vector':Vec}
        module=ast.fix_missing_locations(ast.Module(body=[future,legacy]+selected,type_ignores=[]))
        exec(compile(module,'real camera helpers / offline scene stand-ins','exec'),scope)
        return scope,scene

    def test_reproduce_old_alias_with_real_legacy_helper(self) -> None:
        scope,scene=self.camera_scope()
        overview=scope['camera'](scene,[0,0,10],[0,0,0],True,10)
        close=scope['camera'](scene,[1,2,3],[1,2,0],False,10)
        self.assertIs(overview,close)
        self.assertEqual(overview.data.type,'PERSP')
        self.assertEqual(overview.location,[1,2,3])

    def test_fixed_cameras_have_independent_object_data_target_and_selection(self) -> None:
        scope,scene=self.camera_scope(); create=scope['independent_camera']
        overview=create(scene,'Room8_Overview',[0,0,10],[0,0,0],True,10)
        close=create(scene,'Room8_Closeup22',[1,2,3],[1,2,0],False,10); close.data.lens=30
        self.assertIsNot(overview,close); self.assertIsNot(overview.data,close.data)
        self.assertIsNot(overview.constraints[0].target,close.constraints[0].target)
        modes={'overview':overview,'closeup':close}
        for mode in ('closeup','overview','closeup','overview'):
            actual=scope['activate_camera'](scene,modes,mode)
            self.assertEqual(actual['type'],'ORTHO' if mode=='overview' else 'PERSP')
            self.assertEqual(actual['object'],modes[mode].name)
        self.assertEqual(overview.data.ortho_scale,13)
        self.assertEqual(overview.constraints[0].target.location,[0,0,0])

    def test_camera_alias_and_wrong_type_fail_before_render(self) -> None:
        scope,scene=self.camera_scope(); create=scope['independent_camera']
        overview=create(scene,'OV',[0,0,10],[0,0,0],True,10)
        with self.assertRaisesRegex(ValueError,'independent'):
            scope['activate_camera'](scene,{'overview':overview,'closeup':overview},'overview')
        close=create(scene,'CU',[1,2,3],[1,2,0],False,10)
        overview.data.type='PERSP'
        with self.assertRaisesRegex(ValueError,'differs'):
            scope['activate_camera'](scene,{'overview':overview,'closeup':close},'overview')

    def test_overview_fit_only_enlarges_scale_preserving_pose(self) -> None:
        scope,scene=self.camera_scope()
        obj=scope['independent_camera'](scene,'OV',[0,0,10],[0,0,0],True,10)
        before=(deepcopy(obj.location),deepcopy(obj.constraints[0].target.location))
        points=[[x,y,-2] for x in (-9,9) for y in (-6,6)]
        fit=scope['fit_overview'](scene,obj,points)
        self.assertTrue(fit['passed']); self.assertTrue(fit['scale_enlarged'])
        self.assertEqual((obj.location,obj.constraints[0].target.location),before)
        again=scope['fit_overview'](scene,obj,points)
        self.assertFalse(again['scale_enlarged'])

    def test_camera_check_is_exactly_one_3_5s_frame_without_video_requests(self) -> None:
        f=self.fixture(); spec=jobs.build_spec(f.inputs,'camera_check')
        self.assertEqual(spec['animation']['camera_mode'],'overview')
        requests=jobs.requests(spec); self.assertEqual(len(requests),1)
        self.assertEqual(requests[0]['frame'],43); self.assertEqual(requests[0]['seconds'],3.5)
        self.assertEqual(requests[0]['path'],'keyframes/overview_3.5s.png')
        self.assertEqual(requests[0]['kind'],'camera_check')

    def test_closeup_is_explicit_option_and_cannot_reuse_overview_frames(self) -> None:
        f=self.fixture(); spec=jobs.build_spec(f.inputs,'short',camera_mode='closeup')
        req=jobs.requests(spec)
        self.assertTrue(all(r['camera']=='closeup' for r in req if r['kind']=='video'))
        self.assertTrue(all(r['camera']=='closeup' for r in req if r.get('copy_from')))
        with self.assertRaises(ValueError):jobs.build_spec(f.inputs,'short',camera_mode='unexpected')
        self.assertEqual(jobs.estimate_full({'video_frames':{'mean_seconds':1}},spec,0,0)['status'],'not_applicable_to_overview')

    def test_mislabelled_perspective_frames_cannot_be_encoded_as_overview(self) -> None:
        f=self.fixture()
        record={'kind':'video','camera':'overview','effective':{'camera':{'camera_mode':'overview','type':'PERSP','object':'Wrong'}}}
        with self.assertRaisesRegex(ValueError,'camera_mode'):jobs.verify_effective_cameras([record],f.spec)

    def reference(self,f: object) -> Path:
        folder=f.asset.parent/'style_round3/reference'; folder.mkdir(parents=True)
        image=folder/'overview_3.5s.png'; image.write_bytes(animations.png(960,540))
        jobs.write_json(folder/'requested_config.json',f.inputs['style'])
        jobs.write_json(folder/'repair_report.json',{'base_room_sha256':jobs.digest(f.asset/'room.blend')})
        manifest=folder/'sample_manifest.json'
        jobs.write_json(manifest,{'samples':[{'image':image.name,'sha256':jobs.digest(image),
            'effective':{'camera':{'type':'ORTHO','position':[0,0,10],'target':[0,0,0],'ortho_scale':13}}}]})
        return manifest

    def test_reference_binds_original_style_image_and_same_base_asset(self) -> None:
        f=self.fixture(); manifest=self.reference(f)
        reference=jobs.load_camera_reference(f.asset,None,True)
        self.assertEqual(reference['manifest'],str(manifest))
        self.assertIn(str(manifest.parent/'overview_3.5s.png'),reference['guards'])
        (manifest.parent/'overview_3.5s.png').write_bytes(b'corrupted')
        with self.assertRaisesRegex(ValueError,'reference'):jobs.load_camera_reference(f.asset,None,True)

    def test_historical_report_is_read_only_and_keeps_actual_costs(self) -> None:
        f=self.fixture(); folder=f.new_job(); f.populate_frames(folder)
        manifest=jobs.read_json(folder/'render_manifest.json')
        for r in manifest['frames']:
            if r['kind']=='video':r['effective']['camera']['type']='PERSP'
        jobs.write_json(folder/'render_manifest.json',manifest)
        jobs.write_json(folder/'timing_report.json',{'total_seconds_this_attempt':100,
            'frames':{'video_frames':{'count':48,'mean_seconds':1,'sum_seconds':48}},'encoding_seconds_original':.7})
        guards={p.name:jobs.digest(p) for p in folder.iterdir() if p.is_file()}
        result=jobs.historical_summary(folder)
        self.assertEqual(result['total_seconds'],100); self.assertEqual(result['video_frames']['sum_seconds'],48)
        self.assertTrue(result['camera_mismatch']); self.assertFalse(result['usable_as_overview_performance_baseline'])
        self.assertEqual(guards,{p.name:jobs.digest(p) for p in folder.iterdir() if p.is_file()})

    def test_report_cli_needs_no_asset_gpu_or_render(self) -> None:
        with patch('sys.argv',['run_room_animation.py','--report-job','fixture']),\
             patch.object(launcher,'historical_summary',return_value={'read_only':True}),\
             patch.object(launcher,'execute',side_effect=AssertionError('must not render')),patch('builtins.print') as output:
            launcher.main()
        self.assertIn('read_only',output.call_args.args[0])

    def test_camera_check_launcher_does_not_encode_or_create_short_approval(self) -> None:
        f=self.fixture()
        args=argparse.Namespace(asset=f.asset,points=f.points,config=f.config,stage='camera_check',preset='test',
            wall_height=1.1,drop_component=[],approval=None,resume=None,camera_mode='overview',reference_samples=None)
        class Process:
            def __init__(self,command: list,**kwargs: object) -> None:
                job=Path(command[command.index('--job')+1]); attempt=command[command.index('--attempt')+1]
                spec=jobs.read_json(job/'config_snapshot.json'); request=jobs.requests(spec)[0]
                path=job/request['path']; path.write_bytes(animations.png(960,540))
                record={**request,'sha256':jobs.digest(path),'render_seconds':1,'attempt':attempt,
                        'effective':{'camera':{'type':'ORTHO','camera_mode':'overview','object':'Room8_Overview'}}}
                jobs.write_json(job/'render_manifest.json',{'frames':[record],'worker_complete':True})
                jobs.write_json(job/'attempts'/attempt/'worker_timing.json',{
                    'blender_startup_and_import_seconds':.1,'worker_prepare_seconds':.2})
            def wait(self) -> int:return 0
            def poll(self) -> int:return 0
        @contextmanager
        def lock(root: Path):yield 5
        with patch.object(launcher.shutil,'which',return_value='fixture'),patch.object(launcher,'preflight',return_value=f.inputs),\
             patch.object(launcher,'gpu_lock',lock),patch.object(launcher,'busy_processes',return_value={}),\
             patch.object(launcher,'monitor_gpu',return_value=None),patch.object(launcher.subprocess,'Popen',side_effect=Process),\
             patch.object(launcher,'encode',side_effect=AssertionError('must not encode')):
            folder=launcher.execute(args)
        self.assertFalse((folder/'fire_short.mp4').exists()); self.assertFalse((folder/'approval_template.json').exists())
        self.assertTrue((folder/'keyframes/overview_3.5s.png').exists())
        self.assertEqual(jobs.read_json(folder/'status.json')['state'],'awaiting_visual_review')


if __name__=='__main__':unittest.main()
