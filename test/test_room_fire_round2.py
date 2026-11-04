"""PRD 2.2 / architecture 3.2: round-two flame thickness and rising dark plumes.

Pure synthetic geometry/config and shader-wiring checks; no Blender, database,
real asset mutation or rendering. Does not prove visual quality/Blender API support.
Run: python -m unittest test.test_room_fire_round2 -v
"""
import ast
from collections import Counter
from copy import deepcopy
import math
from pathlib import Path
import unittest

from app.room_fire_config import load_config, validate, tongue_specs, plume_mesh, smoke_state, curve_value
from test import test_room_demo as demo


ROOT=Path(__file__).resolve().parents[1]


class RoundTwo(unittest.TestCase):
    def setUp(self) -> None:
        self.old=load_config(ROOT/'app/room_fire_round1.json')
        self.config=load_config(ROOT/'app/room_fire_round2.json')

    def test_dimensions_increase_without_changing_tongue_style(self) -> None:
        f=self.config['art']['flame']; old=self.old['art']['flame']
        self.assertEqual((f['primary_tongues'],f['secondary_tongues']),(4,2))
        for device,primary,height_ratio,radius_ratio in ((22,True,1.75,1.45),(0,False,1.3,1)):
            for a,b in zip(tongue_specs(self.old,device,primary),tongue_specs(self.config,device,primary)):
                self.assertAlmostEqual(b['height']/a['height'],height_ratio)
                self.assertAlmostEqual(b['radius']/a['radius'],radius_ratio)
                self.assertEqual(b['phase'],a['phase'])
        for key in ('colors','emission','noise_scale','noise_detail','noise_low','noise_high','emission_mask_power','flicker_hz'):
            self.assertEqual(f[key],old[key])
        self.assertEqual(self.config['events'],self.old['events'])
        self.assertEqual(self.config['quality'],self.old['quality'])

    def test_surface_lighting_unchanged_but_volume_lighting_reduced(self) -> None:
        a=self.config['art']; b=self.old['art']
        for key in ('exposure','world_color','world_strength','area_lights'):
            self.assertEqual(a[key],b[key])
        self.assertEqual(a['flame']['light_energy'],b['flame']['light_energy'])
        self.assertGreater(a['flame']['light_distance'],b['flame']['light_distance'])
        self.assertLess(a['area_volume_factor'],1)
        self.assertLess(a['flame']['light_volume_factor'],1)

    def test_closed_plume_is_wider_above_narrow_base_and_not_regular(self) -> None:
        vertices,faces=plume_mesh(self.config,.7)
        s=self.config['art']['smoke']; sides=s['sides']
        self.assertEqual(len(vertices),s['rings']*sides)
        edges=Counter(tuple(sorted((face[i],face[(i+1)%len(face)]))) for face in faces for i in range(len(face)))
        self.assertTrue(all(n==2 for n in edges.values()))
        self.assertTrue(all(math.isfinite(v) for p in vertices for v in p))
        def span(ring: int) -> float:
            values=vertices[ring*sides:(ring+1)*sides]
            return max(v[0] for v in values)-min(v[0] for v in values)
        self.assertGreater(span(9),span(0)*3)
        mid=vertices[7*sides:8*sides]
        radii=[math.hypot(p[0],p[1]) for p in mid]
        self.assertGreater(max(radii)-min(radii),.1)
        self.assertNotEqual(vertices,plume_mesh(self.config,2.1)[0])
        self.assertEqual((vertices,faces),plume_mesh(self.config,.7))

    def test_smoke_grows_and_rises_without_floating_base_after_fire_fades(self) -> None:
        early=smoke_state(self.config,3.5,True); late=smoke_state(self.config,6,True)
        for key in ('density','height','radius','growth'):self.assertGreater(late[key],early[key])
        self.assertEqual(late['emitter_offset'],early['emitter_offset'])
        self.assertGreater(smoke_state(self.config,10,True)['density'],0)
        self.assertEqual(curve_value(self.config['events']['fire_curve'],10),0)
        self.assertEqual(smoke_state(self.config,-1,True)['density'],0)
        self.assertEqual(smoke_state(self.config,20,True)['density'],0)
        self.assertLess(smoke_state(self.config,6,False)['height'],late['height'])

    def test_thicker_flame_density_is_separate_from_emission_path(self) -> None:
        nodes,links=demo.DemoTests().volume(False,self.config)
        byname={getattr(n,'name',''):n for n in nodes}
        layer=byname['FlameDensityLayers']
        weights=[e.color[0] for e in layer.color_ramp.elements]
        self.assertEqual(weights,[.06,.45,1,.9])
        self.assertGreater(self.config['art']['flame']['density'],self.old['art']['flame']['density'])
        self.assertEqual(byname['FlameBodyNoise'].inputs[2].default_value,.65)
        density=byname['DensityOnly']; emission=byname['EmissionIndependentOfDensity']
        self.assertIn((byname['FlameDensityHeightFade'].outputs[0],density.inputs[0]),links)
        for n in (density,layer,byname['FlameBodyThickness']):
            self.assertNotIn((n.outputs[0],emission.inputs[0]),links)
            self.assertNotIn((n.outputs[0],emission.inputs[1]),links)

    def test_smoke_has_non_emissive_extinction_and_dark_scattering(self) -> None:
        nodes,links=demo.DemoTests().volume(True,self.config)
        byname={getattr(n,'name',''):n for n in nodes}
        volume=byname['PrincipledEffect']
        self.assertEqual(volume.inputs['Emission Strength'].default_value,0)
        self.assertNotIn(volume.inputs['Emission Strength'],[b for _,b in links])
        self.assertIn('SmokeExtraAbsorption',byname)
        absorption=byname['SmokeExtraAbsorption']
        self.assertIn((absorption.outputs[0],byname['SmokeScatterAndAbsorption'].inputs[1]),links)
        self.assertIn((byname['SmokeAbsorptionRatio'].outputs[0],absorption.inputs['Density']),links)
        self.assertLess(max(byname['EffectColors'].color_ramp.elements[0].color[:3]),.04)

    def test_invalid_layer_shape_darkness_and_light_factors_rejected(self) -> None:
        for group,key,value in [('flame','density_noise_floor',1),('flame','density_layers',[[0,1]]),
                                ('smoke','shape','sphere'),('smoke','rings',100),
                                ('smoke','edge_color',[1,1,1,1]),('smoke','absorption_ratio',-1)]:
            c=deepcopy(self.config); c['art'][group][key]=value
            with self.assertRaises(ValueError):validate(c)
        c=deepcopy(self.config); c['art']['area_volume_factor']=2
        with self.assertRaises(ValueError):validate(c)

    def test_round_two_uses_new_directory_and_rejects_video(self) -> None:
        text=(ROOT/'app/F8_room_demo.py').read_text(encoding='utf-8')
        self.assertIn("('style_round'+str(revision))",text)
        self.assertIn("with_name('room_fire_round3.json')",text)
        self.assertIn("choices=('inspect','samples')",text)
        tree=ast.parse(text)
        calls=[n for n in ast.walk(tree) if isinstance(n,ast.Call) and ast.unparse(n.func)=='bpy.ops.render.render']
        self.assertTrue(calls)
        self.assertTrue(all(any(k.arg=='write_still' and k.value.value is True for k in n.keywords) for n in calls))
        self.assertIn("output/'effective_settings.json'",text)
        self.assertIn("output/'sample_manifest.json'",text)
        self.assertIn("if any(digest(p)!=h for p,h in guards.items())",text)


if __name__=='__main__':unittest.main()
