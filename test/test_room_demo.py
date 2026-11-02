"""PRD 2.2 / architecture 3.2: F8-D material evidence and preview isolation.

Offline helper AST tests with synthetic shader-node stand-ins: validate wiring
and parameters, NOT Blender 4.2 API compatibility or rendered appearance.
No bpy import, DB/network, render or real asset mutation.
Local: python -m unittest test.test_room_demo -v
"""
import ast
from pathlib import Path
from types import SimpleNamespace
import unittest

PATH=Path(__file__).resolve().parents[1]/'app/F8_room_demo.py'


class Socket:
    def __init__(self) -> None:
        self.default_value=None
        self.keys=[]
    def keyframe_insert(self, path: str, frame: int) -> None:
        self.keys.append((path,frame))


class Sockets(dict):
    def __missing__(self,key: str) -> Socket:
        self[key]=Socket(); return self[key]


class Node:
    def __init__(self,kind: str) -> None:
        self.kind=kind; self.inputs=Sockets(); self.outputs=Sockets()
        self.color_ramp=SimpleNamespace(elements=[SimpleNamespace(position=0),SimpleNamespace(position=1)])
        self.inputs['Absorption Color']=Socket()


class Nodes(list):
    def new(self,kind: str) -> Node:
        node=Node(kind); self.append(node); return node


class DemoTests(unittest.TestCase):
    def volume(self,smoke: bool) -> tuple:
        nodes=Nodes(); links=[]
        mat=SimpleNamespace(node_tree=SimpleNamespace(nodes=nodes,links=SimpleNamespace(new=lambda a,b:links.append((a,b)))))
        bpy=SimpleNamespace(data=SimpleNamespace(materials=SimpleNamespace(new=lambda name:mat)))
        tree=ast.parse(PATH.read_text(encoding='utf-8'))
        function=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='volume_material')
        scope={'bpy':bpy}
        exec(compile(ast.Module(body=[function],type_ignores=[]),str(PATH),'exec'),scope)
        scope['volume_material']('synthetic',smoke)
        return nodes,links

    def test_flame_density_is_linked_and_emission_explicitly_orange(self) -> None:
        nodes,links=self.volume(False)
        volume=next(n for n in nodes if n.kind=='ShaderNodeVolumePrincipled')
        self.assertIn(volume.inputs['Density'],[b for _,b in links])
        self.assertIn(volume.inputs['Emission Strength'],[b for _,b in links])
        self.assertEqual(volume.inputs['Emission Color'].default_value,(1,.14,.008,1))
        self.assertEqual(volume.inputs['Blackbody Intensity'].default_value,0)
        noise=next(n for n in nodes if n.kind=='ShaderNodeTexNoise')
        self.assertEqual(noise.noise_dimensions,'4D')
        self.assertEqual(len(noise.inputs['W'].keys),2)

    def test_smoke_is_dark_absorption_white_and_non_emissive(self) -> None:
        nodes,links=self.volume(True)
        volume=next(n for n in nodes if n.kind=='ShaderNodeVolumePrincipled')
        self.assertEqual(volume.inputs['Color'].default_value,(.07,.055,.045,1))
        self.assertEqual(volume.inputs['Absorption Color'].default_value,(1,1,1,1))
        self.assertNotIn('Emission Strength',volume.inputs)

    def test_existing_asset_loaded_and_only_preview_output_names_used(self) -> None:
        text=PATH.read_text(encoding='utf-8'); tree=ast.parse(text)
        calls=[ast.unparse(n.func) for n in ast.walk(tree) if isinstance(n,ast.Call)]
        self.assertIn('bpy.ops.wm.open_mainfile',calls)
        self.assertNotIn('bpy.ops.wm.obj_import',calls)
        self.assertNotIn('clip_mesh',calls)
        self.assertNotIn('unlink',calls)
        self.assertIn("output/'fire_short.mp4'",text)
        self.assertIn("output/'display.blend'",text)
        self.assertIn("output/'room_timeline.json'",text)
        self.assertIn('0<args.duration<=8',text)
        for n in ast.walk(tree):
            if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='print':
                self.assertTrue(any(k.arg=='flush' and isinstance(k.value,ast.Constant) and k.value.value is True for k in n.keywords))


if __name__=='__main__':unittest.main()
