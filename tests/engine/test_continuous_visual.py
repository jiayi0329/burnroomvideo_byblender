"""CPU geometry and safety tests, never import bpy or start Blender."""
from collections import Counter
from copy import deepcopy
import importlib
import json
from pathlib import Path
import tempfile
import hashlib
import math
import unittest
from unittest.mock import patch
from experiments.continuous_field import build_field,inside
from experiments.visual_state import geometry,roof_mesh
from experiments.run_visual import main,prepare
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

    def test_adapters_import_without_bpy_and_compile(self):
        importlib.import_module('experiments.blender_visual');importlib.import_module('experiments.blender_worker')
        for p in (ROOT/'experiments').glob('*.py'):compile(p.read_text(),str(p),'exec')

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
