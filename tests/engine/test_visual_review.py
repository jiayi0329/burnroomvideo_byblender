"""Synthetic CPU checks for visual support, R3 geometry and comparison isolation."""
from copy import deepcopy
import json
import math
from pathlib import Path
import tempfile
import unittest
from experiments.continuous_field import field_from_config,inside
from experiments.visual_state import geometry,mesh_components,adaptation_style
from experiments.visual_composition import composition,patch_layout,local_arrival
from experiments.visual_review import comparison_config,fit_overview
from experiments.scenario_timeline import camera_at,footprint
from render_engine.jobs.operation_logging import bind_context,JsonlSink

ROOT=Path(__file__).resolve().parents[2]
class VisualReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        ctx=bind_context(trace_id='v05-test',sink=JsonlSink(Path(self.temp.name)));ctx.__enter__();self.addCleanup(ctx.__exit__,None,None,None)
        self.c=json.loads((ROOT/'configs/experiments/room8_continuous_a_v05.json').read_text())
        self.ring=[[-1.5,-1.5],[1.5,-1.5],[1.5,1.5],[-1.5,1.5]]
        self.field=field_from_config(self.c,self.ring,[0,0])

    def test_clock_single_source_parent_order_and_no_early_fire(self):
        self.assertAlmostEqual(self.field.arrival_s[(0,0)],.5)
        for cell,parent in self.field.parent.items():self.assertLess(self.field.arrival_s[parent],self.field.arrival_s[cell])
        self.assertFalse(geometry(self.field,self.ring,self.c,.5)['flame']['faces'])
        self.assertFalse(geometry(self.field,self.ring,self.c,1.5)['flame']['faces'])
        self.assertTrue(geometry(self.field,self.ring,self.c,1)['smoke']['faces'])
        self.assertTrue(all(not p['faces'] for p in geometry(self.field,self.ring,self.c,0).values()))

    def test_boundary_connected_support_and_nine_second_coverage(self):
        areas=[]
        for t in (3,4,6,9,12):
            p=geometry(self.field,self.ring,self.c,t)['flame']
            self.assertEqual(mesh_components(p),1)
            self.assertTrue(all(inside(v[:2],self.ring) for v in p['vertices']))
            areas.append(footprint(p,[0,0],0)['area_m2'])
        self.assertEqual(areas,sorted(areas));self.assertGreaterEqual(areas[3]/areas[-1],.8)
        c=deepcopy(self.c);c['accelerated_visual']['front_distance_m'][2][1]=0
        with self.assertRaises(ValueError):field_from_config(c,self.ring,[0,0])

    def test_coarse_irregular_layout_not_one_object_per_cell(self):
        patches=patch_layout(self.field,self.c)
        self.assertEqual(patches,patch_layout(self.field,self.c))
        self.assertLess(len(patches),len(self.field.arrival_s)/4)
        self.assertTrue(all(math.dist(a['xy'],b['xy'])>=.65 for i,a in enumerate(patches) for b in patches[i+1:]))
        bad=deepcopy(self.c);bad['accelerated_visual']['max_patches']=0
        with self.assertRaises(ValueError):patch_layout(self.field,bad)
        events=[json.loads(line) for p in Path(self.temp.name).glob('*.jsonl') for line in p.read_text().splitlines()]
        self.assertTrue(any(e['event']=='failure' and e['operation']=='room.continuous.visual' and e['trace_id']=='v05-test' and 'duration_ms' in e for e in events))

    def test_real_r3_closed_tongues_and_plumes_are_inside_active_support(self):
        layout=patch_layout(self.field,self.c)
        a=composition(self.field,self.ring,self.c,9,layout)
        self.assertEqual(a,composition(self.field,self.ring,self.c,9,layout))
        self.assertIn('tongue',{p['kind'] for p in a});self.assertIn('plume',{p['kind'] for p in a})
        base=self.c['seed']['proposed_base_z_m'];roof=self.c['visual']['roof_z_m']
        self.assertGreater(max(v[2]-base for p in a if p['kind']=='tongue' for v in p['mesh']['vertices']),2)
        for part in a:
            self.assertGreaterEqual(mesh_components(part['mesh']),1)
            for v in part['mesh']['vertices']:
                self.assertTrue(inside(v[:2],self.ring));self.assertLess(v[2],roof)
                arrival=local_arrival(self.field,v[:2]);self.assertIsNotNone(arrival)
                self.assertLess(arrival+(1 if part['kind']=='tongue' else 0),9)

    def test_comparison_modes_preserve_camera_exposure_and_quality(self):
        for mode in 'ABCDE':
            c=comparison_config(self.c,mode)
            self.assertEqual(c['cameras'],self.c['cameras']);self.assertEqual(c['exposure'],self.c['exposure'])
            self.assertEqual(c['experimental_quality'],self.c['experimental_quality']);self.assertFalse(c['render_authorized'])
        a=comparison_config(self.c,'A');self.assertTrue(all(not p['faces'] for p in geometry(self.field,self.ring,a,9).values()))
        b=comparison_config(self.c,'B');self.assertFalse(geometry(self.field,self.ring,b,9)['smoke']['faces'])
        c=comparison_config(self.c,'C');self.assertFalse(geometry(self.field,self.ring,c,9)['flame']['faces'])

    def test_third_camera_is_absolute_and_original_reference_is_unchanged(self):
        self.assertEqual(camera_at(self.c,3.99),'low');self.assertEqual(camera_at(self.c,4),'v1_final')
        self.assertEqual(camera_at(self.c,9),'late');self.assertEqual(camera_at(self.c,6),'v1_final')
        camera={'position':[3,-6,7],'target':[0,0,0],'ortho_scale':16,'type':'ORTHO'};original=deepcopy(camera)
        fitted=fit_overview(camera,self.ring,-1.3,1.85,16/9)
        self.assertEqual(camera,original);self.assertGreater(fitted['ortho_scale'],0)
        old=[a-b for a,b in zip(camera['target'],camera['position'])];new=[a-b for a,b in zip(fitted['target'],fitted['position'])]
        self.assertTrue(all(abs(a-b)<1e-9 for a,b in zip(old,new)))
        self.assertEqual(adaptation_style(self.c)['art']['flame']['primary_tongues'],4)

    def test_single_r3_tongue_and_plume_keep_original_generated_coordinates(self):
        import sys
        from unittest.mock import MagicMock,patch
        from experiments.blender_visual import adapted_material
        for kind,smoke in (('tongue',False),('plume',True)):
            mat=MagicMock();factory=MagicMock(return_value=(mat,{}));module=MagicMock(volume_material=factory)
            with patch.dict(sys.modules,{'render_engine.blender.F8_room_fire_style':module}):
                adapted_material(MagicMock(),'test',self.c,kind)
            self.assertEqual(factory.call_args.args[1],smoke)
            mat.node_tree.nodes.new.assert_not_called()
