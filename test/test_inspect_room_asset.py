"""PRD 2.1 / room asset preparation; architecture 3.1 and Blender process isolation.

app/inspect_room_asset.py: offline synthetic geometry, UV, texture and hash checks.
F8_inspect_room_import.py: static no-render/no-save guard only; Blender checks run remotely.
Run locally: python -m unittest test.test_inspect_room_asset -v
"""
import ast
import json
from pathlib import Path
import tempfile
import unittest

from app import inspect_room_asset as audit
import test.test_room_database as fixtures


class GeometryInspection(unittest.TestCase):
    def test_axis_inverse_not_hardcoded_to_xy(self) -> None:
        self.assertEqual(audit.inverse_xy([(2, 3)], [0, 1, -1, 0, 1, 2]), [(-1, 1)])
        with self.assertRaises(ValueError):
            audit.inverse_xy([(0, 0)], [1, 1, 1, 1, 0, 0])

    def test_vertical_hit_interior_outside_and_vertical_face(self) -> None:
        tri = [(0, 0, -1), (2, 0, -1), (0, 2, -1)]
        self.assertAlmostEqual(audit.vertical_hit(.5, .5, tri), -1)
        self.assertIsNone(audit.vertical_hit(2, 2, tri))
        self.assertIsNone(audit.vertical_hit(0, 0, [(0, 0, 0), (0, 0, 2), (0, 2, 0)]))

    def test_height_envelopes_do_not_certify_physical_planes(self) -> None:
        vertices = [(x, y, z) for z in (-1, 0, 2) for x, y in ((0, 0), (2, 0), (2, 2), (0, 2))]
        faces = [{'corners': [(v, None) for v in indices]} for level in range(3)
                 for indices in ((level*4, level*4+1, level*4+2), (level*4, level*4+2, level*4+3))]
        profile = audit.height_profile({'vertices': vertices, 'faces': faces}, [(0,0),(2,0),(2,2),(0,2)], .5)
        self.assertEqual(profile['bottom_clusters'][0]['z_m'], -1)
        self.assertEqual(profile['top_clusters'][0]['z_m'], 2)
        self.assertIsNone(profile['floor_z_confirmed'])
        self.assertIsNone(profile['ceiling_z_confirmed'])
        self.assertEqual(profile['with_upper_and_lower'], profile['sample_count'])

    def test_nontriangle_faces_reported_not_fan_triangulated(self) -> None:
        mesh = {'vertices': [(0,0,0),(2,0,0),(2,2,0),(0,2,0)],
                'faces': [{'corners': [(i,None) for i in range(4)]}]}
        profile = audit.height_profile(mesh, [(0,0),(2,0),(2,2),(0,2)], .5)
        self.assertEqual(profile['unsupported_nontriangle_faces'], 1)
        self.assertEqual(profile['without_surface'], profile['sample_count'])


class SourceAssets(unittest.TestCase):
    def test_uv_material_texture_and_negative_indices(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'texture.jpg').write_bytes(b'synthetic')
            (root / 'mesh.mtl').write_text('newmtl mat\nmap_Kd texture.jpg\n', encoding='utf-8')
            path = root / 'mesh.obj'
            path.write_text('mtllib mesh.mtl\nv 0 0 0\nv 1 0 0\nv 0 1 0\nvt 0 0\nvt 1 0\nvt 0 1\nusemtl mat\nf -3/-3 -2/-2 -1/-1\n', encoding='utf-8')
            mesh = audit.read_obj(path)
            self.assertEqual(mesh['faces'][0]['corners'], [(0,0),(1,1),(2,2)])
            self.assertTrue(audit.materials(root, mesh)['ready_for_preservation'])
            (root / 'texture.jpg').unlink()
            self.assertIn('missing_texture:texture.jpg', audit.materials(root, mesh)['issues'])

    def test_missing_uv_and_external_paths_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            path = root / 'mesh.obj'
            path.write_text('v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n', encoding='utf-8')
            self.assertFalse(audit.materials(root, audit.read_obj(path))['uv_complete'])
            with self.assertRaises(ValueError):
                audit.confined(root, '../outside.mtl')
            path.write_text('v nan 0 0\nf 1 1 1\n', encoding='utf-8')
            with self.assertRaises(ValueError):
                audit.read_obj(path)


class InspectionWorkflow(unittest.TestCase):
    setUp = fixtures.ImportValidation.setUp
    write_review = fixtures.ImportValidation.write_review

    def test_generic_room_read_only_and_no_cut_authorization(self) -> None:
        video = self.scene / 'output.mp4'
        video.write_bytes(b'historical-video')
        before = {p: audit.sha256(p) for p in self.scene.rglob('*') if p.is_file()}
        result = audit.inspect(self.scene, self.probe, self.output, self.review_path, 'R', .5)
        self.assertEqual(result['room_id'], 'R')
        self.assertFalse(result['ready_for_cut'])
        self.assertFalse(result['database_required'])
        self.assertFalse(result['render_started'])
        self.assertFalse(result['wall_policy']['permanent_geometry_removed'])
        self.assertEqual(before, {p: audit.sha256(p) for p in self.scene.rglob('*') if p.is_file()})

    def test_unreviewed_axis_or_missing_room_rejected(self) -> None:
        with self.assertRaises(ValueError):
            audit.inspect(self.scene, self.probe, self.output, self.review_path, 'unknown')
        self.review['xy_verified'] = False
        self.write_review()
        with self.assertRaises(ValueError):
            audit.inspect(self.scene, self.probe, self.output, self.review_path, 'R')


class BlenderDiagnosticBoundary(unittest.TestCase):
    def test_script_has_no_render_cut_or_blend_save_calls(self) -> None:
        path = Path(__file__).resolve().parents[1] / 'tools/diagnostics/blender/F8_inspect_room_import.py'
        source = path.read_text(encoding='utf-8')
        tree = ast.parse(source)
        calls = [ast.unparse(node.func) for node in ast.walk(tree) if isinstance(node, ast.Call)]
        self.assertIn('bpy.ops.wm.obj_import', calls)
        self.assertFalse(any('render.render' in name or 'save_as_mainfile' in name or 'bisect' in name for name in calls))
        self.assertIn('source_and_history_unchanged', source)
