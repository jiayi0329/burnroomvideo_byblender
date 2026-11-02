"""PRD 2.2 / architecture 3.2: F8-B saved room point/section checks.

Offline tests execute selected helper AST functions from F8_prepare_room_asset.py
with synthetic data / object stand-ins, without importing bpy or starting Blender.
They do not validate Blender APIs, actual GLB export or GPU picture quality.
Local: python -m unittest test.test_prepare_room_asset -v
No network, DB or filesystem mutation; independent F8 role labels also checked.
"""
import ast
from copy import deepcopy
import math
from pathlib import Path
from types import SimpleNamespace
import unittest


ROOT = Path(__file__).resolve().parents[1]


def helpers() -> dict:
    tree = ast.parse((ROOT/'app/F8_prepare_room_asset.py').read_text(encoding='utf-8'))
    selected = {'verify_point_mapping','verify_saved_point_anchors','below','contains','interior_camera'}
    module = ast.Module(body=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in selected],
                        type_ignores=[])
    scope = {'math': math}
    exec(compile(module,'F8-B offline helper functions','exec'),scope)
    return scope


class AssetHelpers(unittest.TestCase):
    def setUp(self) -> None:
        self.functions = helpers()
        self.points = [{'device':k,'pose':{'translation':{'x':x,'y':y,'z':.1}}}
                       for k,x,y in ((1,.5,.5),(2,2,1))]
        self.payload = {'points':deepcopy(self.points),'interior_devices':[1],
                        'boundary_devices':[2],'ignition_device':1,'floor_z':-1.35}

    def test_source_mapping_preserves_camera_height(self) -> None:
        before = deepcopy(self.payload)
        self.functions['verify_point_mapping'](self.payload,self.points)
        self.assertEqual(self.payload,before)

    def test_overlapping_memberships_or_missing_selected_point_rejected(self) -> None:
        for update in ({'boundary_devices':[1,2]}, {'points':self.points[:1]},
                       {'ignition_device':2}):
            with self.subTest(update=update), self.assertRaises(ValueError):
                self.functions['verify_point_mapping']({**self.payload,**update},self.points)

    def test_changed_source_pose_or_duplicate_source_ids_rejected(self) -> None:
        changed = deepcopy(self.points)
        changed[0]['pose']['translation']['z'] = -1.35
        for points in (changed,self.points+self.points[:1]):
            with self.assertRaises(ValueError):
                self.functions['verify_point_mapping'](self.payload,points)

    def anchors(self) -> dict:
        class Anchor(dict):
            type = 'EMPTY'
        objects = {}
        for point in self.points:
            device = point['device']
            obj = Anchor(source_device=device,membership='interior' if device==1 else 'doorway_boundary',
                         fire_reference_z=-1.35)
            obj.matrix_world = SimpleNamespace(translation=[point['pose']['translation'][k] for k in ('x','y','z')])
            objects[f'Point_{device}'] = obj
        self.functions['bpy'] = SimpleNamespace(data=SimpleNamespace(objects=objects))
        return objects

    def test_reloaded_anchor_checks_record_camera_and_separate_fire_height(self) -> None:
        self.anchors()
        result = self.functions['verify_saved_point_anchors'](self.payload)
        self.assertEqual(len(result),2)
        self.assertEqual(result[0]['camera_raw_xyz'],[.5,.5,.1])
        self.assertEqual(result[0]['fire_reference_xyz'],[.5,.5,-1.35])
        self.assertEqual(result[1]['membership'],'doorway_boundary')

    def test_missing_shifted_or_wrong_membership_anchor_rejected(self) -> None:
        for mode in ('missing','shifted','wrong_kind'):
            objects = self.anchors()
            if mode=='missing':
                del objects['Point_1']
            elif mode=='shifted':
                objects['Point_1'].matrix_world.translation[0] += .1
            else:
                objects['Point_1']['membership'] = 'doorway_boundary'
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                self.functions['verify_saved_point_anchors'](self.payload)

    def test_section_only_clips_derivative_and_interpolates_uv(self) -> None:
        faces = [{'material':'m','corners':[[0,0,0,0,0],[2,0,2,1,0],[0,2,2,0,1]]}]
        before = deepcopy(faces)
        result = self.functions['below'](faces,1)
        self.assertTrue(result)
        for face in result:
            self.assertEqual(face['material'],'m')
            for x,y,z,u,v in face['corners']:
                self.assertLessEqual(z,1)
                self.assertAlmostEqual(u,x/2)
                self.assertAlmostEqual(v,y/2)
        self.assertEqual(faces,before)

    def test_camera_candidate_is_inside_concave_room(self) -> None:
        polygon = [(0,0),(3,0),(3,1),(1,1),(1,3),(0,3)]
        point = self.functions['interior_camera'](polygon)
        self.assertTrue(self.functions['contains'](*point,polygon))
        self.assertFalse(self.functions['contains'](2,2,polygon))

    def test_three_f8_headers_identify_current_entry(self) -> None:
        for name,label in (('F8_inspect_room_import.py','F8-A'),
                           ('F8_prepare_room_asset.py','F8-B'),('F8_blender_render.py','F8-C')):
            doc = ast.get_docstring(ast.parse((ROOT/'app'/name).read_text(encoding='utf-8')))
            self.assertIn(label,doc)
        tree = ast.parse((ROOT/'app/F8_prepare_room_asset.py').read_text(encoding='utf-8'))
        for node in ast.walk(tree):
            if isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id=='print':
                self.assertTrue(any(k.arg=='flush' and isinstance(k.value,ast.Constant) and k.value.value is True
                                    for k in node.keywords))


if __name__=='__main__':
    unittest.main()
