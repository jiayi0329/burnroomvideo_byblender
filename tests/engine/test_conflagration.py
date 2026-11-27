"""CPU and mocked shader wiring; does not claim Blender visual acceptance."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock
from experiments.continuous_field import field_from_config,inside
from experiments.visual_state import geometry,mesh_components
from experiments.conflagration import body_height,validate_controls,detail_variation
from experiments.visual_composition import patch_layout,composition
from experiments.conflagration_material import build_material,update_material
from render_engine.jobs.operation_logging import bind_context,JsonlSink

ROOT=Path(__file__).resolve().parents[2]
class ConflagrationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        ctx=bind_context(trace_id='conflagration-test',sink=JsonlSink(Path(self.temp.name)));ctx.__enter__();self.addCleanup(ctx.__exit__,None,None,None)
        self.c=json.loads((ROOT/'configs/experiments/room8_continuous_a_v06.json').read_text())
        self.ring=[[-1.5,-1.5],[1.5,-1.5],[1.5,1.5],[-1.5,1.5]]
        self.field=field_from_config(self.c,self.ring,[0,0])

    def test_connected_body_is_independent_of_detail_count(self):
        a=geometry(self.field,self.ring,self.c,9)
        self.assertEqual(mesh_components(a['body']),1);self.assertEqual(mesh_components(a['flame']),1)
        c=deepcopy(self.c);c['conflagration']['detail_count']=1
        self.assertEqual(geometry(self.field,self.ring,c,9)['body'],a['body'])
        base=self.c['seed']['proposed_base_z_m']
        heights=[v[2]-base for v in a['body']['vertices'] if v[2]>base+.02]
        self.assertGreater(min(heights),1.5);self.assertGreater(max(heights)-min(heights),.15)
        self.assertTrue(all(inside(v[:2],self.ring) and v[2]<1.85 for v in a['body']['vertices']))

    def test_early_visibility_geometry_and_smooth_absolute_transition(self):
        self.assertFalse(self.c['render_authorized'])
        self.assertTrue(all(not m['faces'] for m in geometry(self.field,self.ring,self.c,0).values()))
        self.assertTrue(geometry(self.field,self.ring,self.c,1)['smoke']['faces'])
        self.assertFalse(geometry(self.field,self.ring,self.c,1)['body']['faces'])
        self.assertGreater(body_height(self.c,[0,0],3,.5),.3)
        for t in (4,7):
            self.assertLess(abs(body_height(self.c,[0,0],t+.0001,.5)-body_height(self.c,[0,0],t-.0001,.5)),.001)
        self.assertEqual(geometry(self.field,self.ring,self.c,6),geometry(self.field,self.ring,self.c,6))
        from experiments.visual_review import comparison_config
        for mode in 'BCD':
            c=comparison_config(self.c,mode);state=geometry(self.field,self.ring,c,9)
            self.assertEqual(bool(state['body']['faces']),mode!='C')
            self.assertEqual(bool(state['smoke']['faces']),mode!='B')

    def test_sparse_r3_surface_details_and_real_smoke_plumes(self):
        layout=patch_layout(self.field,self.c);self.assertLessEqual(len(layout),12)
        result=composition(self.field,self.ring,self.c,9,layout)
        self.assertLessEqual(sum(p['kind']=='tongue' for p in result),12)
        self.assertIn('plume',{p['kind'] for p in result})
        self.assertNotEqual(detail_variation(self.c,1),detail_variation(self.c,2))
        for part in result:
            self.assertGreaterEqual(mesh_components(part['mesh']),1)
            self.assertTrue(all(inside(v[:2],self.ring) and v[2]<1.85 for v in part['mesh']['vertices']))

    def test_parameters_change_real_geometry_and_unknown_controls_fail(self):
        h=body_height(self.c,[.2,.3],9,.5)
        for name in ('body_height_m','body_thickness_gain','height_irregularity'):
            c=deepcopy(self.c);c['conflagration'][name]*=.8
            self.assertNotEqual(body_height(c,[.2,.3],9,.5),h)
        bad=deepcopy(self.c);bad['conflagration']['unused_placeholder']=1
        with self.assertRaises(ValueError):validate_controls(bad)

    def shader(self,kind):
        bpy=MagicMock();mat=MagicMock();bpy.data.materials.new.return_value=mat;created=[]
        def make(code):
            n=MagicMock();n.bl_idname=code;created.append(n);return n
        mat.node_tree.nodes.new.side_effect=make
        mat.node_tree.nodes.__getitem__.side_effect=lambda key:next(n for n in created if n.name==key)
        result,controls=build_material(bpy,'fake_cpu_shader',self.c,kind)
        return result,controls,created

    def test_fire_shader_density_floor_and_early_emission_are_wired(self):
        mat,controls,nodes=self.shader('body')
        self.assertIn('ShaderNodeVolumePrincipled',[n.bl_idname for n in nodes])
        self.assertEqual(sum(n.bl_idname=='ShaderNodeTexNoise' for n in nodes),2)
        update_material(mat,controls,self.c,'body',3)
        self.assertEqual(controls['emission'].default_value,10)
        self.assertEqual(controls['density'].default_value,2.4)
        self.assertTrue(mat.node_tree.links.new.called)

    def test_smoke_extinction_and_scattering_are_separate_non_emissive(self):
        for kind in ('smoke','layer'):
            mat,controls,nodes=self.shader(kind)
            types=[n.bl_idname for n in nodes]
            self.assertIn('ShaderNodeVolumeAbsorption',types);self.assertIn('ShaderNodeVolumeScatter',types)
            self.assertNotIn('ShaderNodeVolumePrincipled',types);self.assertNotIn('emission',controls)
            update_material(mat,controls,self.c,kind,9)
            self.assertEqual(controls['density'].default_value,.35)
            self.assertEqual(controls['absorption'].default_value,3.2 if kind=='smoke' else 2.6)
        events=[json.loads(line) for p in Path(self.temp.name).glob('*.jsonl') for line in p.read_text().splitlines()]
        self.assertTrue(all(e['trace_id']=='conflagration-test' for e in events))
