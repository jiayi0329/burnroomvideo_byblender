"""PRD engineering baseline; ARCHITECTURE geometry/readonly input boundary.

Legacy trace: PRD_V1.1 2.2 / architecture 3.2. Exercises room_source_io and
inspect_room_asset compatibility. Offline unit tests in local PowerShell:
python -B -m unittest tests.engine.test_room_source_io -v
Only synthetic temporary OBJ/MTL/texture bytes; no real assets, bpy, DB/network.
"""
import hashlib
from pathlib import Path
import tempfile
import unittest

from tools.diagnostics import inspect_room_asset as legacy
from render_engine.geometry import room_source_io as source


class SourceReading(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def mesh(self, text: str) -> dict:
        path = self.root / 'mesh.obj'
        path.write_text(text, encoding='utf-8')
        return source.read_obj(path)

    def test_old_inspection_function_names_still_available(self) -> None:
        for name in ('number', 'index', 'confined', 'inverse_xy', 'read_obj', 'materials', 'sha256'):
            self.assertIs(getattr(legacy, name), getattr(source, name))
        self.assertEqual(legacy.XYZ, source.XYZ)

    def test_coordinate_numbers_and_obj_indices_preserve_validation(self) -> None:
        self.assertEqual(source.number('-1.35'), -1.35)
        for value in ('nan', 'inf', '-inf'):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, 'Nonfinite OBJ coordinate'):
                source.number(value)
        self.assertEqual([source.index(v, 3) for v in ('1', '3', '-1', '-3')], [0, 2, 2, 0])
        for value in ('0', '4', '-4'):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, 'Invalid OBJ index'):
                source.index(value, 3)

    def test_xy_inverse_rotation_scale_translation_and_singular_matrix(self) -> None:
        raw = [(-2, -1), (1, 3), (0, -1.35)]
        matrix = [0, -2, 3, 0, 4, -5]
        transformed = [(matrix[0]*x+matrix[1]*y+matrix[4],
                        matrix[2]*x+matrix[3]*y+matrix[5]) for x, y in raw]
        for actual, expected in zip(source.inverse_xy(transformed, matrix), raw):
            for value, reference in zip(actual, expected):
                self.assertAlmostEqual(value, reference)
        with self.assertRaisesRegex(ValueError, 'Singular XY transform'):
            source.inverse_xy(raw, [1, 2, 2, 4, 0, 0])

    def test_obj_raw_z_corner_uv_seams_normals_and_materials_preserved(self) -> None:
        mesh = self.mesh('mtllib mesh.mtl\nv 0 0 -1.35\nv 2 0 -1.35\nv 0 2 1\n'
                         'vt 0 0\nvt 1 0\nvt 0 1\nvt .5 .5\nvn 0 0 1\n'
                         'usemtl wall\nf -3/-4/-1 -2/-3/-1 -1/-2/-1\n'
                         'usemtl floor\nf 1/4/1 3/3/1 2/2/1\n')
        self.assertEqual(mesh['vertices'], [(0, 0, -1.35), (2, 0, -1.35), (0, 2, 1)])
        self.assertEqual(mesh['faces'][0], {'corners': [(0, 0), (1, 1), (2, 2)], 'material': 'wall'})
        self.assertEqual(mesh['faces'][1]['corners'][0], (0, 3))
        self.assertEqual(mesh['faces'][1]['material'], 'floor')
        self.assertEqual(mesh['normal_count'], 1)

    def test_obj_ngons_not_silently_triangulated(self) -> None:
        mesh = self.mesh('v 0 0 0\nv 2 0 0\nv 2 2 0\nv 0 2 0\nf 1 2 3 4\n')
        self.assertEqual(len(mesh['faces']), 1)
        self.assertEqual(len(mesh['faces'][0]['corners']), 4)
        self.assertTrue(all(uv is None for _, uv in mesh['faces'][0]['corners']))

    def test_malformed_geometry_and_normal_indices_rejected(self) -> None:
        cases = ('# empty\n', 'v 0 0\nf 1 1 1\n',
                 'v 0 0 0\nf 1 1\n', 'v 0 0 0\nf 1//1 1//1 1//1\n',
                 'v 0 0 0\nvt nan 0\nf 1/1 1/1 1/1\n')
        for text in cases:
            with self.subTest(text=text), self.assertRaises(ValueError):
                self.mesh(text)

    def test_quoted_mtl_texture_paths_and_readonly_fingerprints(self) -> None:
        (self.root / 'maps').mkdir()
        texture = self.root / 'maps/surface texture.jpg'
        texture.write_bytes(b'synthetic texture, not an image')
        library = self.root / 'surface material.mtl'
        library.write_text('newmtl surface\nmap_Kd "maps/surface texture.jpg"\n', encoding='utf-8')
        mesh = self.mesh('mtllib "surface material.mtl"\nv 0 0 0\nv 1 0 0\nv 0 1 0\n'
                         'vt 0 0\nvt 1 0\nvt 0 1\nusemtl surface\nf 1/1 2/2 3/3\n')
        before = {p: source.sha256(p) for p in self.root.rglob('*') if p.is_file()}
        report = source.materials(self.root, mesh)
        self.assertTrue(report['ready_for_preservation'])
        self.assertEqual(report['textures']['maps/surface texture.jpg']['sha256'], source.sha256(texture))
        self.assertEqual(report['libraries'][0]['sha256'], source.sha256(library))
        self.assertEqual(before, {p: source.sha256(p) for p in before})

    def test_material_options_duplicates_missing_uv_still_require_review(self) -> None:
        (self.root / 'mesh.mtl').write_text('newmtl m\nnewmtl m\nmap_Kd -s 1 1 1 tex.jpg\n', encoding='utf-8')
        mesh = self.mesh('mtllib mesh.mtl\nv 0 0 0\nf 1 1 1\nusemtl m\nf 1 1 1\n')
        report = source.materials(self.root, mesh)
        self.assertFalse(report['ready_for_preservation'])
        for issue in ('duplicate_material_definition:m', 'texture_options_require_review:m',
                      'undefined_face_material:None', 'missing_face_corner_uv'):
            self.assertIn(issue, report['issues'])

    def test_material_and_texture_paths_cannot_escape_source_root(self) -> None:
        for name in ('../outside.mtl', str(self.root.parent / 'absolute.mtl')):
            with self.subTest(name=name), self.assertRaises(ValueError):
                source.materials(self.root, {'libraries': [name], 'faces': []})
        (self.root / 'mesh.mtl').write_text('newmtl m\nmap_Kd ../outside.jpg\n', encoding='utf-8')
        with self.assertRaises(ValueError):
            source.materials(self.root, {'libraries': ['mesh.mtl'], 'faces': []})

    def test_sha256_hashes_raw_bytes_including_newlines_and_multiple_blocks(self) -> None:
        path = self.root / 'bytes.bin'
        data = b'x' * (1024 * 1024 + 17) + b'\r\n'
        path.write_bytes(data)
        self.assertEqual(source.sha256(path), hashlib.sha256(data).hexdigest())
        path.write_bytes(data[:-2] + b'\n')
        self.assertNotEqual(source.sha256(path), hashlib.sha256(data).hexdigest())
