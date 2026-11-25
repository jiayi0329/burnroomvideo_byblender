"""CPU geometry and safety tests, never import bpy or start Blender."""
from collections import Counter
from copy import deepcopy
import importlib
import json
from pathlib import Path
import tempfile
import hashlib
import math
import os
from contextlib import nullcontext
import unittest
from unittest.mock import patch
from experiments.continuous_field import build_field,inside
from experiments.visual_state import geometry,roof_mesh,camera_view_audit,sightline_hit
from experiments.run_visual import main,prepare,load_formal_v1_camera
from render_engine.jobs.operation_logging import bind_context,JsonlSink

ROOT=Path(__file__).resolve().parents[2]
class VisualTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        context=bind_context(trace_id='visual-test',sink=JsonlSink(Path(self.temp.name)));context.__enter__();self.addCleanup(context.__exit__,None,None,None)
        self.config=json.loads((ROOT/'configs/experiments/room8_continuous_a_v02.json').read_text())
        self.ring=[[-1,-1],[1,-1],[1,1],[-1,1]];self.field=build_field(self.ring,(0,0),.2,.35)

    def test_smoke_then_flame_and_persistent_support(self):
        self.assertFalse(geometry(self.field,self.ring,self.config,0)['smoke']['faces'])
        early=geometry(self.field,self.ring,self.config,1)
        self.assertTrue(early['smoke']['faces']);self.assertFalse(early['flame']['faces'])
        for t in (3,6,9,12):self.assertTrue(geometry(self.field,self.ring,self.config,t)['flame']['faces'])

    def test_welded_closed_mesh_boundary_and_repeatability(self):
        a=geometry(self.field,self.ring,self.config,6);b=geometry(self.field,self.ring,self.config,6)
        self.assertEqual(a,b)
        for payload in a.values():
            edges=Counter(tuple(sorted((face[i],face[(i+1)%len(face)]))) for face in payload['faces'] for i in range(len(face)))
            self.assertTrue(all(count==2 for count in edges.values()),Counter(edges.values()))
            self.assertTrue(all(inside(p[:2],self.ring) and p[2]<=1.85 for p in payload['vertices']))

    def test_roof_mode_independent_of_layer_and_mode_controls(self):
        a=geometry(self.field,self.ring,self.config,6)
        for mode in ('full','cutaway','outline'):
            c=deepcopy(self.config);c['visual']['roof_mode']=mode
            self.assertEqual(geometry(self.field,self.ring,c,6)['layer'],a['layer'])
            self.assertTrue(roof_mesh(self.ring,1.85,mode)['vertices'])
        c=deepcopy(self.config);c['visual']['mode']='none'
        self.assertTrue(all(not p['faces'] for p in geometry(self.field,self.ring,c,12).values()))
        c['visual']['mode']='smoke';self.assertFalse(geometry(self.field,self.ring,c,12)['flame']['faces'])

    def test_layer_waits_for_roof_and_grows(self):
        self.assertFalse(geometry(self.field,self.ring,self.config,2)['layer']['faces'])
        self.assertTrue(geometry(self.field,self.ring,self.config,6)['layer']['faces'])
        c=deepcopy(self.config);c['visual']['roof_z_m']=2.85
        self.assertFalse(geometry(self.field,self.ring,c,3)['layer']['faces'])

    def test_gpu_unapproved_rejected_before_prepare_or_subprocess(self):
        with patch('experiments.run_visual.subprocess.run') as run,patch('experiments.run_visual.prepare') as prepare_call:
            with self.assertRaises(SystemExit):main(['--candidate','missing','--asset','missing','--points','missing','--output-root',self.temp.name,'--render-keyframes','--confirm-gpu-experiment'])
        run.assert_not_called();prepare_call.assert_not_called()

    def test_launcher_inherits_runtime_environment_and_keeps_lock_and_trace(self):
        # Fake process boundary only: never invoke Blender or acquire a real GPU.
        run_dir=Path(self.temp.name)/'launch';run_dir.mkdir()
        snapshot={'data_root':self.temp.name,'guards':{}}
        environment={'PATH':'/usr/local/blender:/usr/bin','LD_LIBRARY_PATH':'/runtime/nvidia',
                     'OPERATION_LOG_ROOT':str(Path(self.temp.name)/'parent-operations')}
        with patch.dict(os.environ,environment,clear=True), \
             patch('experiments.run_visual.read',return_value={'render_authorized':True}), \
             patch('experiments.run_visual.prepare',return_value=(run_dir,snapshot)), \
             patch('render_engine.jobs.run_room_animation.gpu_lock',return_value=nullcontext(87)) as lock, \
             patch('render_engine.jobs.run_room_animation.busy_processes',return_value={'compute':{'available':True}}) as busy, \
             patch('experiments.run_visual.check_guards') as guards, \
             patch('experiments.run_visual.subprocess.run') as process:
            result=main(['--candidate','unused','--asset','unused','--points','unused',
                         '--output-root',self.temp.name,'--render-keyframes','--confirm-gpu-experiment'])
            self.assertEqual(dict(os.environ),environment)
        self.assertEqual(result,0);lock.assert_called_once_with(Path(self.temp.name));busy.assert_called_once()
        self.assertEqual(guards.call_count,2);process.assert_called_once()
        kwargs=process.call_args.kwargs;env=kwargs['env']
        self.assertEqual(env['PATH'],environment['PATH'])
        self.assertEqual(env['LD_LIBRARY_PATH'],environment['LD_LIBRARY_PATH'])
        self.assertEqual(env['OPERATION_LOG_ROOT'],environment['OPERATION_LOG_ROOT'])
        self.assertEqual(env['ROOM_ANIMATION_LOCK_FD'],'87');self.assertEqual(kwargs['pass_fds'],(87,))
        self.assertTrue(kwargs['check'])
        command=process.call_args.args[0]
        self.assertEqual(command[0],'blender');self.assertIn('--disable-autoexec',command)
        trace=json.loads(env['BURNROOM_OPERATION_CONTEXT'])['trace_id']
        events=[json.loads(line) for p in (run_dir/'operations').glob('*.jsonl') for line in p.read_text().splitlines()]
        self.assertTrue(any(e['event']=='success' and e['stage']=='keyframe_render' for e in events))
        self.assertTrue(all(e['trace_id']==trace for e in events))
        self.assertTrue(all('LD_LIBRARY_PATH' not in json.dumps(e) for e in events))

    def test_launcher_occupancy_failure_stops_before_process_with_failure_log(self):
        run_dir=Path(self.temp.name)/'blocked';run_dir.mkdir()
        with patch('experiments.run_visual.read',return_value={'render_authorized':True}), \
             patch('experiments.run_visual.prepare',return_value=(run_dir,{'data_root':self.temp.name,'guards':{}})), \
             patch('render_engine.jobs.run_room_animation.gpu_lock',return_value=nullcontext(87)), \
             patch('render_engine.jobs.run_room_animation.busy_processes',side_effect=RuntimeError('occupied')), \
             patch('experiments.run_visual.subprocess.run') as process:
            with self.assertRaisesRegex(RuntimeError,'occupied'):
                main(['--candidate','unused','--asset','unused','--points','unused',
                      '--output-root',self.temp.name,'--render-keyframes','--confirm-gpu-experiment'])
        process.assert_not_called()
        events=[json.loads(line) for p in (run_dir/'operations').glob('*.jsonl') for line in p.read_text().splitlines()]
        self.assertTrue(any(e['event']=='failure' and e['stage']=='keyframe_render' and 'trace_id' in e for e in events))

    def test_adapters_import_without_bpy_and_compile(self):
        importlib.import_module('experiments.blender_visual');importlib.import_module('experiments.blender_worker')
        for p in (ROOT/'experiments').glob('*.py'):compile(p.read_text(),str(p),'exec')

    def test_formal_v1_camera_requires_matching_actual_final_frames(self):
        # Synthetic provenance only; never represented as recovered Room8 evidence.
        from render_engine.jobs.room_animation_job import fingerprint
        root=Path(self.temp.name);asset=root/'asset';asset.mkdir();(asset/'room.blend').write_bytes(b'fixture')
        def dump(name,value):
            p=root/name;p.write_text(json.dumps(value));return p
        digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
        spec={'inputs':{'guards':{'/server/room.blend':digest(asset/'room.blend')}},
              'animation':{'stage':'final','preset':'final','camera_mode':'overview','fps':24,'frame_count':576,'duration_seconds':24,'resolution':[1280,720]}}
        spec['signature']=fingerprint(spec);path=dump('config_snapshot.json',spec);expected=digest(path)
        camera={'type':'ORTHO','position':[3,-4,5],'target':[0,0,0],'lens':18,'ortho_scale':16,
                'clip_start':.03,'clip_end':1000,'sensor_width':36,'sensor_fit':'AUTO','dof':False,
                'track_axis':'TRACK_NEGATIVE_Z','up_axis':'UP_Y','rotation_world_euler':[.7,0,.6]}
        manifest={'signature':spec['signature'],'camera_setup':{'overview':camera},'frames':[{'path':f'frames/{i:06}.png','effective':{'camera':deepcopy(camera)}} for i in range(576)]}
        dump('render_manifest.json',manifest);dump('effective_settings.json',{'camera_setup':{'overview':camera}});dump('video_receipt.json',{'synthetic':True})
        recovered=load_formal_v1_camera(root,asset,expected)
        self.assertEqual(recovered['camera'],camera);self.assertEqual(recovered['verified_frame_count'],576)
        with self.assertRaisesRegex(ValueError,'fingerprint'):load_formal_v1_camera(root,asset,'0'*64)
        manifest['frames'][15]['effective']['camera']['position'][0]=4;dump('render_manifest.json',manifest)
        with self.assertRaisesRegex(ValueError,'changes between frames'):load_formal_v1_camera(root,asset,expected)
        manifest['frames'].pop();dump('render_manifest.json',manifest)
        with self.assertRaisesRegex(ValueError,'Incomplete'):load_formal_v1_camera(root,asset,expected)
        events=[json.loads(line) for p in root.glob('*.jsonl') for line in p.read_text().splitlines()]
        failures=[e for e in events if e.get('operation')=='room.continuous.camera' and e['event']=='failure']
        self.assertEqual(len(failures),3)

    def test_clear_camera_has_seed_flame_and_roof_inside_frame(self):
        config=deepcopy(self.config);base=config['seed']['proposed_base_z_m']
        config['cameras']['low']={'offset':[3,0,.25-base],'target_height':1.55,'lens':16}
        ring=[[-4,-4],[4,-4],[4,4],[-4,4]]
        a=camera_view_audit(config,[0,0],ring,[])
        self.assertEqual(a,camera_view_audit(config,[0,0],ring,[]))
        self.assertTrue(all(v['clear'] for v in a['targets'].values()))
        self.assertIn('seed_base',a['targets']);self.assertIn('roof_near_seed',a['targets'])

    def test_camera_rejects_outside_occluded_and_cropped_views_with_log(self):
        config=deepcopy(self.config);base=config['seed']['proposed_base_z_m']
        config['cameras']['low']={'offset':[3,0,.25-base],'target_height':1.55,'lens':16}
        ring=[[-4,-4],[4,-4],[4,4],[-4,4]]
        with self.assertRaisesRegex(ValueError,'outside Room8'):
            camera_view_audit(config,[0,0],self.ring,[])
        wall=[{'corners':[[1,-10,-10],[1,10,-10],[1,0,10]]}]
        with self.assertRaisesRegex(ValueError,'Scan blocks'):
            camera_view_audit(config,[0,0],ring,wall)
        config['cameras']['low']['lens']=80
        with self.assertRaisesRegex(ValueError,'image margin'):
            camera_view_audit(config,[0,0],ring,[])
        events=[json.loads(line) for p in Path(self.temp.name).glob('*.jsonl') for line in p.read_text().splitlines()]
        failures=[e for e in events if e.get('operation')=='room.continuous.camera' and e['event']=='failure']
        self.assertEqual(len(failures),3)
        self.assertTrue(all(e['trace_id']=='visual-test' and 'duration_ms' in e for e in failures))

    def test_sightline_preserves_near_obstacles_and_display_cut(self):
        wall=[{'corners':[[.001,-1,-1],[.001,1,-1],[.001,0,1]]}]
        hit=sightline_hit([0,0,0],[1,0,0],wall)
        self.assertAlmostEqual(hit['distance_m'],.001)
        self.assertIsNone(sightline_hit([0,0,0],[1,0,0],wall,cut_z=-.1))
        endpoint=[{'corners':[[1,-1,-1],[1,1,-1],[1,0,1]]}]
        self.assertIsNone(sightline_hit([0,0,0],[1,0,0],endpoint))

    def test_offline_plan_is_independent_and_pins_inputs(self):
        # Entire fixture, including fake BLEND bytes, is CPU-only synthetic data.
        root=Path(self.temp.name);scene=root/'synthetic-scene';asset=scene/'version/asset';asset.mkdir(parents=True)
        def dump(path,value):path.write_text(json.dumps(value));return path
        def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
        points=dump(scene/'points.json',[{'device':22,'pose':{'translation':{'x':0,'y':0,'z':0}}}])
        candidate=dump(asset.parent/'candidate.json',{'scene_code':self.config['scene_code'],'room_id':'Room8','ignition_device':22,'floor_z':-1,
            'polygon_raw_xy':[[math.cos(i*2*math.pi/11)*1.4,math.sin(i*2*math.pi/11)*1.4] for i in range(11)],
            'geometry':{'faces':[{'corners':[[-3,-3,0],[3,-3,0],[0,3,0]]}]}})
        (asset/'room.blend').write_bytes(b'CPU fixture, not a real blend');(asset/'room.glb').write_bytes(b'CPU fixture')
        dump(asset/'validation.json',{'status':'passed','checks':{'synthetic':True}})
        manifest=dump(asset/'manifest.json',{'candidate_sha256':digest(candidate),'source_fingerprints':{'points.json':digest(points)},'artifacts':{name:digest(asset/name) for name in ('room.blend','room.glb','validation.json')}})
        cfg=deepcopy(self.config);cfg['candidate_sha256']=digest(candidate)
        cfg['asset_binding']={name:digest(points if name=='points.json' else asset/name) for name in cfg['asset_binding']}
        cfg['seed'].update(raw_camera_xyz_m=[0,0,0],scan_surface_z_m=0,proposed_base_z_m=.015)
        config=dump(root/'config.json',cfg)
        before={p:digest(p) for p in (points,candidate,config,manifest,asset/'room.blend',asset/'room.glb')}
        a,snapshot=prepare(config,candidate,asset,points,root/'out');b,_=prepare(config,candidate,asset,points,root/'out')
        self.assertNotEqual(a,b);self.assertFalse(json.loads((a/'geometry-plan.json').read_text())['rendered'])
        self.assertTrue(all(digest(p)==value for p,value in before.items()))
        with self.assertRaises(ValueError):prepare(config,candidate,asset,points,scene/'forbidden-output')
        cfg['require_clear_view']=True;dump(config,cfg)
        with self.assertRaisesRegex(ValueError,'outside Room8'):
            prepare(config,candidate,asset,points,root/'camera-rejected')
        self.assertFalse((root/'camera-rejected').exists())
        from render_engine.jobs.room_animation_job import check_guards
        config.write_text('{}')
        with self.assertRaises(ValueError):check_guards({'guards':snapshot['guards']})

    def test_budget_and_invalid_roof_fail_with_correlated_log(self):
        config=deepcopy(self.config);config['visual']['roof_z_m']=-2
        with self.assertRaises(ValueError):geometry(self.field,self.ring,config,1)
        config=deepcopy(self.config);config['resolution']=[8000,8000]
        with self.assertRaises(ValueError):geometry(self.field,self.ring,config,1)
        geometry(self.field,self.ring,self.config,1)
        events=[json.loads(line) for p in Path(self.temp.name).glob('*.jsonl') for line in p.read_text().splitlines()]
        visual=[e for e in events if e.get('operation')=='room.continuous.visual']
        self.assertTrue(any(e['event']=='failure' for e in visual))
        self.assertTrue(any(e['event']=='success' and 'duration_ms' in e for e in visual))
        self.assertTrue(all(e['trace_id']=='visual-test' for e in visual))
