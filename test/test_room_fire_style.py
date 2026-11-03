"""PRD 2.2 / architecture 3.2 round-one runtime configuration and still-only guard.

Offline AST/helper execution with setting stand-ins; NOT Blender API/render proof.
Local: python -m unittest test.test_room_fire_style -v
"""
import argparse
import ast
from pathlib import Path
from types import SimpleNamespace
import unittest

from app.room_fire_config import load_config


ROOT=Path(__file__).resolve().parents[1]


class Owner:
    def __getattr__(self,name: str) -> object:return None


class RuntimeConfiguration(unittest.TestCase):
    def functions(self) -> dict:
        tree=ast.parse((ROOT/'app/F8_room_fire_style.py').read_text(encoding='utf-8'))
        selected=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in ('checked','configure_render')]
        future=ast.ImportFrom(module='__future__',names=[ast.alias(name='annotations')],level=0)
        module=ast.fix_missing_locations(ast.Module(body=[future]+selected,type_ignores=[]))
        scope={'bpy':SimpleNamespace(app=SimpleNamespace(version_string='synthetic'))}
        exec(compile(module,'offline Blender settings stand-ins','exec'),scope)
        return scope

    def test_explicit_settings_replace_unknown_inheritance(self) -> None:
        scene=Owner();scene.render=Owner();scene.render.image_settings=Owner()
        scene.view_settings=Owner();scene.display_settings=Owner();scene.eevee=Owner()
        actual=self.functions()['configure_render'](scene,load_config(ROOT/'app/room_fire_round1.json'))
        self.assertEqual(actual['color_management']['exposure'],-.5)
        self.assertEqual(actual['color_management']['view_transform'],'AgX')
        self.assertEqual(actual['eevee']['taa_render_samples'],32)
        self.assertEqual(actual['eevee']['volumetric_tile_size'],'4')
        self.assertTrue(actual['eevee']['use_volumetric_shadows'])
        self.assertFalse(actual['render']['use_compositing'])
        self.assertFalse(actual['animation_enabled'])

    def test_missing_or_clamped_setting_fails_before_render(self) -> None:
        checked=self.functions()['checked']
        with self.assertRaises(RuntimeError):checked(SimpleNamespace(),'unknown',True)
        class Clamp:
            @property
            def value(self) -> float:return 0.0
            @value.setter
            def value(self,value: float) -> None:pass
        with self.assertRaises(RuntimeError):checked(Clamp(),'value',.5)

    def test_short_mode_is_rejected_without_accessing_assets(self) -> None:
        tree=ast.parse((ROOT/'app/F8_room_demo.py').read_text(encoding='utf-8'))
        function=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='run')
        scope={'argparse':argparse,'Path':Path,'time':SimpleNamespace(perf_counter=lambda:0)}
        exec(compile(ast.Module(body=[function],type_ignores=[]),'offline mode guard','exec'),scope)
        with self.assertRaisesRegex(ValueError,'animation is paused'):
            scope['run'](argparse.Namespace(mode='short'))
        render_calls=[n for n in ast.walk(tree) if isinstance(n,ast.Call) and ast.unparse(n.func)=='bpy.ops.render.render']
        self.assertTrue(render_calls)
        self.assertTrue(all(any(k.arg=='write_still' and isinstance(k.value,ast.Constant) and k.value.value is True
                                   for k in n.keywords) for n in render_calls))


if __name__=='__main__':unittest.main()
