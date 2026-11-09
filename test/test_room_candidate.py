"""PRD 2.2 approximation / architecture 3.2 independent room asset.

app/room_clip_geometry.py + prepare_room_candidate.py: synthetic concave rooms,
UV interpolation, walls, acceptance/provenance, source/history preservation.
F8_prepare_room_asset.py: static workflow check only, NOT Blender validation.
Local PowerShell: python -m unittest test.test_room_candidate -v
No bpy, Docker, network, DB; writes temporary synthetic files only.
"""
from copy import deepcopy
import ast
import json
from pathlib import Path
import unittest

from app import room_clip_geometry as clip
from app.prepare_room_candidate import prepare
from app.analyze_floorplan import contains, sha256
from test import test_room_sections as section_tests


def source(points: list) -> dict:
    return {'vertices':points, 'uvs':[(p[0]/10,p[1]/10) for p in points],
            'faces':[{'corners':[(i,i) for i in range(3)], 'material':'mat'}]}


class ClipGeometry(unittest.TestCase):
    def test_concave_prism_area_and_no_notch_intrusion(self) -> None:
        polygon = [(0,0),(3,0),(3,1),(1,1),(1,3),(0,3)]
        mesh = source([(-10,-10,0),(20,-10,0),(-10,20,0)])
        result = clip.clip_mesh(mesh,polygon)
        self.assertAlmostEqual(sum(clip.area3(f['corners']) for f in result['faces']),5)
        for face in result['faces']:
            center = [sum(v[k] for v in face['corners'])/3 for k in (0,1)]
            self.assertTrue(contains(center,polygon))

    def test_new_corner_uv_and_z_are_linearly_interpolated(self) -> None:
        mesh = source([(-1,-1,-3),(3,-1,1),(-1,3,5)])
        original = deepcopy(mesh)
        result = clip.clip_mesh(mesh,[(0,0),(1,0),(1,1),(0,1)])
        for face in result['faces']:
            self.assertEqual(face['material'],'mat')
            for x,y,z,u,v in face['corners']:
                self.assertAlmostEqual(u,x/10)
                self.assertAlmostEqual(v,y/10)
                self.assertAlmostEqual(z,x+2*y)
        self.assertEqual(mesh,original)

    def test_vertical_wall_on_cell_diagonal_has_no_duplicate_area(self) -> None:
        # Ear clipping of this square shares the diagonal x+y=2.
        mesh = source([(0,2,0),(2,0,0),(0,2,2)])
        result = clip.clip_mesh(mesh,[(0,0),(2,0),(2,2),(0,2)])
        self.assertAlmostEqual(sum(clip.area3(f['corners']) for f in result['faces']),2**1.5)

    def test_boundary_wall_is_retained_and_outside_wall_excluded(self) -> None:
        square = [(0,0),(2,0),(2,2),(0,2)]
        result = clip.clip_mesh(source([(0,0,0),(0,2,0),(0,0,2)]),square)
        self.assertAlmostEqual(sum(clip.area3(f['corners']) for f in result['faces']),2)
        with self.assertRaises(ValueError):
            clip.clip_mesh(source([(-.1,0,0),(-.1,2,0),(-.1,0,2)]),square)

    def test_clockwise_and_tiny_valid_edges(self) -> None:
        polygon = [(0,0),(2,0),(2,2),(1,2),(1,1.999),(0,2)]
        forward = clip.triangulate(polygon)
        reverse = clip.triangulate(list(reversed(polygon)))
        self.assertAlmostEqual(sum(abs(clip.cross(*t))/2 for t in forward),
                               sum(abs(clip.cross(*t))/2 for t in reverse))

    def test_missing_uv_or_nontriangle_rejected(self) -> None:
        mesh = source([(0,0,0),(1,0,0),(0,1,0)])
        mesh['faces'][0]['corners'][0] = (0,None)
        with self.assertRaises(ValueError):
            clip.clip_mesh(mesh,[(0,0),(2,0),(0,2)])


class CandidatePreparation(unittest.TestCase):
    setUp_base = section_tests.DiagnosticInputs.setUp_base
    write_review = section_tests.DiagnosticInputs.write_review
    save_evidence = section_tests.DiagnosticInputs.save_evidence
    setUp = section_tests.DiagnosticInputs.setUp

    def prepare(self, accept: bool=True, floor: float=-1.35) -> Path:
        return prepare(self.scene.parent,self.inspection_path,self.blender_path,self.output,floor,accept)

    def test_explicit_approximation_and_finite_height_required(self) -> None:
        for accept,floor in ((False,-1.35),(True,float('nan'))):
            with self.assertRaises(ValueError):
                self.prepare(accept,floor)
        self.assertFalse((self.scene/'rooms').exists())

    def test_isolated_versioned_candidate_and_all_sources_unchanged(self) -> None:
        before = {p:sha256(p) for p in self.scene.rglob('*') if p.is_file()}
        first,second = self.prepare(),self.prepare()
        self.assertNotEqual(first,second)
        result = json.loads((first/'candidate.json').read_text(encoding='utf-8'))
        self.assertTrue(result['ready_for_cut'])
        self.assertFalse(result['physical_semantics_verified'])
        self.assertEqual(result['floor_z'],-1.35)
        self.assertEqual(result['geometry']['boundary_buffer_m'],0)
        self.assertFalse(result['source_z_modified'])
        self.assertEqual(result['provenance']['review_sha256'],sha256(self.review_path))
        self.assertIn('output.mp4',result['source_fingerprints'])
        for path,h in before.items():
            self.assertEqual(sha256(path),h)

    def test_changed_source_still_rejected_despite_simplification(self) -> None:
        (self.scene/'mesh.obj').write_text('changed',encoding='utf-8')
        with self.assertRaises(ValueError):
            self.prepare()

    def test_blender_script_save_reopen_precedes_preview_and_no_video_operator(self) -> None:
        path = Path(__file__).resolve().parents[1]/'render_engine/blender/F8_prepare_room_asset.py'
        tree = ast.parse(path.read_text(encoding='utf-8'))
        run = next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='run')
        calls = sorted((n.lineno,ast.unparse(n.func)) for n in ast.walk(run) if isinstance(n,ast.Call))
        names = [name for _,name in calls]
        self.assertLess(names.index('bpy.ops.wm.save_as_mainfile'),names.index('bpy.ops.wm.open_mainfile'))
        self.assertLess(names.index('bpy.ops.wm.open_mainfile'),names.index('preview'))
        self.assertFalse(any('animation' in k.arg for n in ast.walk(tree) if isinstance(n,ast.Call) for k in n.keywords if k.arg))


if __name__ == '__main__':
    unittest.main()
