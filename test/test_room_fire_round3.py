"""PRD 2.2 / architecture 3.2: background readability and selective smoke rim light.

Offline config, geometry and Blender-setting stand-ins only. No rendering, DB or
real asset mutation. Run: python -m unittest test.test_room_fire_round3 -v
"""
import ast
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import unittest

from app.room_fire_config import load_config, validate, tongue_specs, flame_mesh, plume_mesh, smoke_state
from test import test_room_demo as demo
from test import test_room_fire_style as runtime


ROOT=Path(__file__).resolve().parents[1]


class VectorStandIn(list):
    def __add__(self,other: list) -> 'VectorStandIn':return VectorStandIn(a+b for a,b in zip(self,other))
    def __sub__(self,other: list) -> 'VectorStandIn':return VectorStandIn(a-b for a,b in zip(self,other))
    def to_track_quat(self,track: str,up: str) -> 'VectorStandIn':return self
    def to_euler(self) -> tuple:return tuple(self)  # Direction placeholder, NOT a Blender quaternion test.


class RoundThree(unittest.TestCase):
    def setUp(self) -> None:
        self.previous=load_config(ROOT/'app/room_fire_round2.json')
        self.config=load_config(ROOT/'app/room_fire_round3.json')

    def test_flames_and_all_geometry_growth_events_cameras_quality_unchanged(self) -> None:
        a,b=self.config,self.previous
        for key in ('flame','seed','closeup'):self.assertEqual(a['art'][key],b['art'][key])
        self.assertEqual(a['events'],b['events']); self.assertEqual(a['quality'],b['quality'])
        for device,primary in ((22,True),(0,False)):
            specs=tongue_specs(a,device,primary)
            self.assertEqual(specs,tongue_specs(b,device,primary))
            self.assertEqual(flame_mesh(specs,9,12),flame_mesh(tongue_specs(b,device,primary),9,12))
            for age in (-1,1,3.5,6,10,20):self.assertEqual(smoke_state(a,age,primary),smoke_state(b,age,primary))
        self.assertEqual(plume_mesh(a,.7),plume_mesh(b,.7))
        changed={k for k in a['art']['smoke'] if a['art']['smoke'][k]!=b['art']['smoke'][k]}
        self.assertEqual(changed,{'edge_color'})

    def test_moderate_background_lift_and_bounded_dark_smoke_edge(self) -> None:
        a,b=self.config['art'],self.previous['art']
        self.assertAlmostEqual(a['exposure']-b['exposure'],.15)
        self.assertEqual(a['world_strength'],.22)
        self.assertEqual(a['smoke']['dark_color'],b['smoke']['dark_color'])
        self.assertTrue(all(old<new<=.06 for old,new in zip(b['smoke']['edge_color'][:3],a['smoke']['edge_color'][:3])))
        self.assertEqual(a['area_lights'][0],b['area_lights'][0])
        self.assertEqual([s['energy'] for s in a['area_lights']],[500,190,340])

    def test_per_light_volume_and_high_rim_target_are_applied_and_recorded(self) -> None:
        tree=ast.parse((ROOT/'render_engine/blender/F8_room_fire_style.py').read_text(encoding='utf-8'))
        functions=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in ('checked','lighting')]
        future=ast.ImportFrom(module='__future__',names=[ast.alias(name='annotations')],level=0)
        sockets={key:SimpleNamespace(default_value=None) for key in ('Color','Strength')}
        objects=[]
        def world(name: str) -> object:
            return SimpleNamespace(node_tree=SimpleNamespace(nodes={'Background':SimpleNamespace(inputs=sockets)}))
        def light(name: str,kind: str) -> object:return SimpleNamespace(name=name,volume_factor=1.0)
        def obj(name: str,data: object) -> object:return SimpleNamespace(name=name,data=data,type='LIGHT')
        bpy=SimpleNamespace(app=SimpleNamespace(version_string='synthetic'),data=SimpleNamespace(
            worlds=SimpleNamespace(new=world),lights=SimpleNamespace(new=light),objects=SimpleNamespace(new=obj)))
        scene=SimpleNamespace(objects=objects,collection=SimpleNamespace(objects=SimpleNamespace(link=objects.append)))
        scope={'bpy':bpy,'Vector':VectorStandIn}
        module=ast.fix_missing_locations(ast.Module(body=[future]+functions,type_ignores=[]))
        exec(compile(module,'offline selective light settings','exec'),scope)
        actual=scope['lighting'](scene,[0,0,0],10,self.config)
        self.assertEqual([s['volume_factor'] for s in actual['area_lights']],[.3,.35,.7])
        self.assertEqual([s['energy'] for s in actual['area_lights']],[500,190,340])
        self.assertEqual(actual['area_lights'][2]['target'],[0,0,1.6])
        self.assertEqual(actual['area_lights'][2]['position'],[3,2,4])
        self.assertEqual(actual['world_color'],self.config['art']['world_color'])

    def test_new_revision_retains_layered_fire_and_absorbing_plume_shader(self) -> None:
        for smoke in (False,True):
            nodes,links=demo.DemoTests().volume(smoke,self.config)
            named={getattr(n,'name',''):n for n in nodes}
            if smoke:
                self.assertIn('SmokeExtraAbsorption',named)
                self.assertEqual(named['EffectColors'].color_ramp.elements[0].color,[.045,.048,.052,1])
                self.assertEqual(named['PrincipledEffect'].inputs['Emission Strength'].default_value,0)
            else:
                self.assertIn('FlameDensityLayers',named)
                self.assertIn('EmissionIndependentOfDensity',named)

    def test_effective_settings_read_back_new_exposure(self) -> None:
        scene=runtime.Owner(); scene.render=runtime.Owner(); scene.render.image_settings=runtime.Owner()
        scene.view_settings=runtime.Owner(); scene.display_settings=runtime.Owner(); scene.eevee=runtime.Owner()
        actual=runtime.RuntimeConfiguration().functions()['configure_render'](scene,self.config)
        self.assertEqual(actual['color_management']['exposure'],-.35)
        self.assertEqual(actual['color_management']['view_transform'],'AgX')
        self.assertFalse(actual['animation_enabled'])

    def test_invalid_selective_light_controls_are_rejected(self) -> None:
        for key,value in (('volume_factor',1.5),('target_offset',[1,2]),('target_offset',[0,0,100])):
            c=deepcopy(self.config);c['art']['area_lights'][2][key]=value
            with self.assertRaises(ValueError):validate(c)
        c=deepcopy(self.config);c['art']['revision']=4
        with self.assertRaises(ValueError):validate(c)


if __name__=='__main__':unittest.main()
