"""PRD current MVP / ARCHITECTURE 2.2-2.3 / PROJECT_ORGANIZATION batch 3.

Checks UV/material/world-coordinate preservation, legacy exports and job guards.
No Blender, GPU, rendering, database or network access; temporary fixtures only.
Run: python -m unittest test.test_blender_room_helpers -v
"""
import ast
from contextlib import chdir, contextmanager
from copy import deepcopy
import hashlib
import importlib
import json
import math
from pathlib import Path
import runpy
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from app import room_animation_job as jobs
from test import test_room_animation as animations
from test.test_room_animation_camera import CameraData, CameraObject

ROOT = Path(__file__).resolve().parents[1]


class Vec(list):
    def __sub__(self, other):
        return Vec(a-b for a, b in zip(self, other))

    @property
    def length(self):
        return math.sqrt(sum(v*v for v in self))

    def normalized(self):
        return Vec(v/self.length for v in self)


class Identity:
    def __matmul__(self, value):
        return Vec(value)

    def inverted(self):
        return self

    def to_3x3(self):
        return self

    def transposed(self):
        return self


class Mesh:
    def __init__(self, name):
        self.name = name
        self.materials = []
        self.uv_layers = SimpleNamespace(active=None, new=self.new_uv)

    def from_pydata(self, vertices, edges, faces):
        self.vertices = [SimpleNamespace(co=Vec(v)) for v in vertices]
        self.loops = []
        self.polygons = []
        for face in faces:
            start = len(self.loops)
            self.loops.extend(SimpleNamespace(index=start+i, vertex_index=v) for i, v in enumerate(face))
            self.polygons.append(SimpleNamespace(vertices=face, loop_indices=list(range(start, len(self.loops))),
                                                 material_index=0))

    def new_uv(self, name):
        result = SimpleNamespace(name=name, data=[SimpleNamespace(uv=None) for _ in self.loops])
        self.uv_layers.active = result
        return result

    def update(self):
        pass


@contextmanager
def loaded():
    """Import actual B/D/E safely; no ops available during module import."""
    linked = []
    scene = SimpleNamespace(camera=None, collection=SimpleNamespace(objects=SimpleNamespace(link=linked.append)))

    def new_object(name, data):
        if isinstance(data, Mesh):
            return SimpleNamespace(name=name, data=data, type='MESH', matrix_world=Identity())
        return CameraObject(name, data)

    fake = SimpleNamespace(data=SimpleNamespace(meshes=SimpleNamespace(new=Mesh),
        objects=SimpleNamespace(new=new_object), cameras=SimpleNamespace(new=CameraData)),
        context=SimpleNamespace(scene=scene, view_layer=SimpleNamespace(update=lambda: None)))
    names = ('F8_room_helpers', 'F8_prepare_room_asset', 'F8_room_demo', 'F8_room_animation')
    with patch.dict(sys.modules, {'bpy': fake, 'mathutils': SimpleNamespace(Vector=Vec)}), \
            patch.object(sys, 'path', [str(ROOT/'app'), *sys.path]):
        for name in names:
            sys.modules.pop(name, None)
        helper = importlib.import_module('F8_room_helpers')
        yield helper, scene


class SharedHelpers(unittest.TestCase):
    def faces(self):
        return [
            {'material': 'z', 'corners': [[0,0,-1.35,0,0], [1,0,-1.35,1,0], [0,1,-1.35,0,1]]},
            {'material': 'a', 'corners': [[0,0,-1.35,.25,.75], [0,1,-1.35,.5,1], [-1,0,-1.35,0,.5]]},
        ]

    def test_mesh_roundtrip_preserves_uv_seams_material_assignment_and_raw_z(self):
        with loaded() as (h, scene):
            faces = self.faces(); before = deepcopy(faces)
            obj = h.make_mesh('Room', faces, {name: SimpleNamespace(name=name) for name in ('z','a')})
            self.assertEqual(h.mesh_faces(obj), before)
            self.assertEqual(faces, before)
            self.assertEqual([m.name for m in obj.data.materials], ['a','z'])
            self.assertEqual([p.material_index for p in obj.data.polygons], [1,0])
            self.assertNotEqual(obj.data.uv_layers.active.data[0].uv, obj.data.uv_layers.active.data[3].uv)

    def test_mesh_reader_uses_world_coordinates_and_rejects_missing_uv_or_nontriangles(self):
        class Shift:
            def __matmul__(self, value):
                return Vec([value[0]+10, value[1]-3, value[2]+2])
        with loaded() as (h, scene):
            obj = h.make_mesh('Room', self.faces(), {name: SimpleNamespace(name=name) for name in ('z','a')})
            obj.matrix_world = Shift()
            corner = h.mesh_faces(obj)[0]['corners'][0]
            for actual, expected in zip(corner, [10,-3,.65,0,0]):
                self.assertAlmostEqual(actual, expected)
            uv = obj.data.uv_layers.active; obj.data.uv_layers.active = None
            with self.assertRaises(ValueError): h.mesh_faces(obj)
            obj.data.uv_layers.active = uv; obj.data.polygons[0].vertices = [0,1,2,3]
            with self.assertRaises(ValueError): h.mesh_faces(obj)

    def test_display_cut_interpolates_uv_without_mutating_input_or_material(self):
        with loaded() as (h, scene):
            faces = [{'material':'wall','corners':[[0,0,0,0,0],[2,0,2,1,0],[0,2,0,0,1]]}]
            original = deepcopy(faces); result = h.below(faces, 1)
            self.assertEqual(faces, original); self.assertEqual(len(result), 2)
            self.assertTrue(all(f['material']=='wall' for f in result))
            corners = [v for f in result for v in f['corners']]
            self.assertIn([1,0,1,.5,0], corners)
            self.assertTrue(all(v[2]<=1 for v in corners))
            with self.assertRaises(ValueError): h.below(faces, -1)

    def test_internal_camera_remains_inside_concave_polygon(self):
        with loaded() as (h, scene):
            polygon = [[0,0],[4,0],[4,1],[1,1],[1,4],[0,4]]
            position = h.interior_camera(polygon)
            self.assertTrue(h.contains(*position, polygon))
            self.assertFalse(h.contains(2,2,polygon))
            with self.assertRaises(ValueError): h.interior_camera([[0,0],[1,0],[2,0]])

    def test_raycast_returns_nearest_world_hit_and_none_when_no_hits(self):
        with loaded() as (h, scene):
            def obj(z, hit=True):
                return SimpleNamespace(matrix_world=Identity(),
                    ray_cast=lambda *args: (hit, Vec([0,0,z]), Vec([0,0,1]), 7))
            far, near = obj(5), obj(2)
            result = h.closest_hit(Vec([0,0,0]), Vec([0,0,1]), [far, obj(0,False), near])
            self.assertEqual(result[:4], (2, [0,0,2], [0,0,1], 7)); self.assertIs(result[4], near)
            self.assertIsNone(h.closest_hit(Vec([0,0,0]), Vec([0,0,1]), [obj(0,False)]))

    def test_file_hash_and_json_format_keep_original_contract(self):
        with loaded() as (h, scene), tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'report.json'; value = {'room':'客厅'}
            h.dump(path, value)
            self.assertEqual(path.read_text(encoding='utf-8'), json.dumps(value,ensure_ascii=False,indent=2))
            self.assertEqual(h.digest(path), hashlib.sha256(path.read_bytes()).hexdigest())

    def test_legacy_modules_reexport_identical_functions_without_entrypoint_imports(self):
        exports = {'F8_prepare_room_asset': ('below','contains','digest','dump','interior_camera','make_mesh'),
                   'F8_room_demo': ('below','digest','dump','make_mesh','interior_camera','mesh_faces','camera','closest_hit'),
                   'F8_room_animation': ('below','make_mesh','mesh_faces','camera','closest_hit')}
        with loaded() as (h, scene):
            for name, functions in exports.items():
                module = importlib.import_module(name)
                for function in functions:
                    self.assertIs(getattr(module,function), getattr(h,function), (name,function))
                tree = ast.parse((ROOT/'app'/f'{name}.py').read_text(encoding='utf-8'))
                imports = {node.module for node in ast.walk(tree) if isinstance(node,ast.ImportFrom)}
                self.assertIn('F8_room_helpers',imports)
                self.assertFalse(imports & (set(exports)-{name}))
            self.assertIsNone(scene.camera)  # Imports create no camera or asset.

    def test_launchers_and_backend_do_not_import_blender_helper(self):
        for name in ('run_room_animation.py','room_animation_job.py','room_api.py','main.py'):
            tree = ast.parse((ROOT/'app'/name).read_text(encoding='utf-8'))
            imports = [node.module for node in ast.walk(tree) if isinstance(node,ast.ImportFrom)]
            imports += [alias.name for node in ast.walk(tree) if isinstance(node,ast.Import) for alias in node.names]
            self.assertFalse({'bpy','F8_room_helpers','app.F8_room_helpers'} & set(imports), name)

    def test_renamed_asset_script_imports_sibling_helper_from_unrelated_directory(self):
        with loaded(), tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            script = folder/'burnroom_prepare_room_asset.py'
            script.write_bytes((ROOT/'app/F8_prepare_room_asset.py').read_bytes())
            (folder/'F8_room_helpers.py').write_bytes((ROOT/'app/F8_room_helpers.py').read_bytes())
            working = folder/'elsewhere'; working.mkdir()
            sys.modules.pop('F8_room_helpers')
            # Match Blender --python with only the uploaded files and no app package.
            paths = [p for p in sys.path if Path(p).resolve() not in (ROOT, ROOT/'app')]
            with patch.object(sys, 'path', paths), chdir(working):
                scope = runpy.run_path(str(script), run_name='uploaded_asset_check')
                helper = sys.modules['F8_room_helpers']
                self.assertEqual(Path(helper.__file__), folder/'F8_room_helpers.py')
                self.assertIs(scope['make_mesh'], helper.make_mesh)
                self.assertIs(scope['below'], helper.below)


class HelperFingerprints(unittest.TestCase):
    def fixture(self):
        value = animations.AnimationJobs(methodName='runTest'); value.setUp()
        self.addCleanup(value.doCleanups); return value

    def test_samples_and_animation_include_shared_helper_in_code_guards(self):
        self.assertIn('F8_room_helpers.py', jobs.CODE_FILES)
        tree = ast.parse((ROOT/'app/F8_room_demo.py').read_text(encoding='utf-8'))
        run = next(node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name=='run')
        code_files = next(node.value for node in ast.walk(run) if isinstance(node,ast.Assign)
                          and any(isinstance(t,ast.Name) and t.id=='code_files' for t in node.targets))
        self.assertIn('F8_room_helpers.py', ast.literal_eval(code_files))
        f = self.fixture(); path = f.codes/'F8_room_helpers.py'
        self.assertEqual(f.inputs['guards'][str(path.resolve())], jobs.digest(path))
        self.assertIn(path.name, f.inputs['codes'])

    def test_changed_helper_rejected_by_guard_and_old_job_resume(self):
        f = self.fixture(); job = f.new_job()
        snapshot = (job/'config_snapshot.json').read_bytes()
        (f.codes/'F8_room_helpers.py').write_text('# new helper version',encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'Protected input'): jobs.check_guards(f.inputs)
        inputs = jobs.preflight(f.asset,f.points,f.config,f.codes)
        spec = jobs.build_spec(inputs,'short')
        self.assertNotEqual(spec['signature'],f.spec['signature'])
        with self.assertRaises(ValueError): jobs.check_resume(job,spec)
        self.assertEqual((job/'config_snapshot.json').read_bytes(), snapshot)

    def test_missing_helper_fails_before_job_creation(self):
        f = self.fixture(); (f.codes/'F8_room_helpers.py').unlink()
        with self.assertRaises(FileNotFoundError): jobs.preflight(f.asset,f.points,f.config,f.codes)
        self.assertFalse(f.job_root.exists())
