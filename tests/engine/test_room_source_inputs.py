"""PRD engineering baseline / ARCHITECTURE file and geometry boundaries.

Legacy trace: PRD_V1.1 2.2 / architecture 3.2. Covers room_source_inputs,
diagnose_room_sections compatibility and prepare_room_candidate decoupling.
Offline local PowerShell: python -B -m unittest tests.engine.test_room_source_inputs -v
Synthetic fixture reports/assets in temp directories; no DB/network/bpy/render.
"""
from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from tools.diagnostics import diagnose_room_sections as legacy
from render_engine.geometry import prepare_room_candidate as candidate
from render_engine.geometry import room_source_inputs as inputs
from render_engine.geometry import room_source_io as source
from tests.tools import test_room_sections as fixtures


class RoomInputValidation(unittest.TestCase):
    setUp_base = fixtures.DiagnosticInputs.setUp_base
    write_review = fixtures.DiagnosticInputs.write_review
    save_evidence = fixtures.DiagnosticInputs.save_evidence
    setUp = fixtures.DiagnosticInputs.setUp

    def load(self) -> tuple:
        return inputs.load_inputs(self.scene.parent, self.inspection_path, self.blender_path, self.output)

    def bind_inspection(self) -> None:
        self.inspection_path.write_text(json.dumps(self.inspection), encoding='utf-8')
        self.evidence['inspection_sha256'] = source.sha256(self.inspection_path)
        self.save_evidence()

    def test_legacy_and_candidate_interfaces_delegate_to_public_validator(self) -> None:
        self.assertIs(legacy.load_inputs, inputs.load_inputs)
        self.assertIs(candidate.load_inputs, inputs.load_inputs)
        self.assertEqual(legacy.REQUIRED_CHECKS, inputs.REQUIRED_CHECKS)

    def test_validated_context_and_all_input_bytes_unchanged(self) -> None:
        before = {p: source.sha256(p) for p in self.scene.rglob('*') if p.is_file()}
        inspection, alignment, mesh, context = self.load()
        self.assertEqual(inspection, json.loads(json.dumps(self.inspection)))
        self.assertEqual(alignment['scene_code'], self.scene.name)
        self.assertEqual(len(mesh['faces']), 12)
        self.assertIn(self.scene / 'output.mp4', context['guarded'])
        self.assertIn(self.scene / 'texture.jpg', context['guarded'])
        self.assertFalse(inspection['ready_for_cut'])
        self.assertTrue(all(source.sha256(p) == h for p, h in context['guarded'].items()))
        self.assertEqual(before, {p: source.sha256(p) for p in self.scene.rglob('*') if p.is_file()})

    def test_each_source_fingerprint_is_checked_before_parsing(self) -> None:
        for path in (self.scene / 'mesh.obj', self.scene / 'points.json', self.scene / 'timeline.json',
                     self.output / 'alignment_report.json', self.review_path):
            original = path.read_bytes()
            try:
                path.write_bytes(original + b'\n')
                with self.subTest(path=path.name), self.assertRaisesRegex(ValueError, 'Input fingerprint changed:'):
                    self.load()
            finally:
                path.write_bytes(original)

    def test_material_library_and_texture_fingerprints_checked(self) -> None:
        for path in (self.scene / 'mesh.mtl', self.scene / 'texture.jpg'):
            original = path.read_bytes()
            try:
                path.write_bytes(original + b'changed')
                with self.subTest(path=path.name), self.assertRaisesRegex(ValueError, 'Material or source fingerprint changed'):
                    self.load()
            finally:
                path.write_bytes(original)

    def test_human_review_required_even_with_updated_fingerprints(self) -> None:
        self.review['xy_verified'] = False
        self.write_review()
        self.inspection['source_review_sha256'] = source.sha256(self.review_path)
        self.bind_inspection()
        with self.assertRaisesRegex(ValueError, 'Bound human XY review required'):
            self.load()

    def test_transform_and_raw_polygon_cannot_drift(self) -> None:
        original = deepcopy(self.inspection)
        for field in ('transform', 'polygon'):
            self.inspection = deepcopy(original)
            if field == 'transform':
                self.inspection['coordinates']['raw_to_floor_xy'][4] += 1
            else:
                point = self.inspection['room_polygon_raw_xy'][0]
                self.inspection['room_polygon_raw_xy'][0] = [point[0] + .1, point[1]]
            self.bind_inspection()
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, 'transform'):
                self.load()

    def test_each_required_remote_blender_check_must_be_true(self) -> None:
        original = deepcopy(self.evidence)
        for name in inputs.REQUIRED_CHECKS:
            self.evidence = deepcopy(original)
            self.evidence['checks'][name] = False
            self.save_evidence()
            with self.subTest(check=name), self.assertRaisesRegex(ValueError, 'Passed remote Blender import evidence required'):
                self.load()

    def test_blender_evidence_scene_room_hash_and_bounds_bound(self) -> None:
        original = deepcopy(self.evidence)
        changes = ({'scene_code': 'other'}, {'room_id': 'other'}, {'inspection_sha256': 'wrong'},
                   {'source_mesh_sha256': 'wrong'}, {'status': 'failed'},
                   {'bounds_world': {'min': [99, 99, 99], 'max': [100, 100, 100]}})
        for changeset in changes:
            self.evidence = {**deepcopy(original), **changeset}
            self.save_evidence()
            with self.subTest(change=changeset), self.assertRaises(ValueError):
                self.load()

    def test_invalid_scene_and_unknown_room_rejected(self) -> None:
        original = deepcopy(self.inspection)
        for change in ({'scene_code': '../escape'}, {'room_id': 'not-a-room'}):
            self.inspection = {**deepcopy(original), **change}
            self.bind_inspection()
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.load()

    def test_remote_evidence_envelope_provenance_preserved(self) -> None:
        self.blender_path.write_text(json.dumps({'result': self.evidence, 'provenance': 'synthetic terminal receipt'}), encoding='utf-8')
        _, _, _, context = self.load()
        self.assertEqual(context['evidence'], self.evidence)
        self.assertEqual(context['evidence_provenance'], 'synthetic terminal receipt')

    def test_missing_historical_video_is_optional_and_not_created(self) -> None:
        video = self.scene / 'output.mp4'
        video.unlink()
        _, _, _, context = self.load()
        self.assertNotIn(video, context['guarded'])
        self.assertFalse(video.exists())


class ImportIsolation(unittest.TestCase):
    def test_candidate_and_common_modules_import_without_diagnostics_or_backend(self) -> None:
        root = Path(__file__).resolve().parents[2]
        code = '''import json, sys
import render_engine.geometry.room_source_io, render_engine.geometry.room_source_inputs, render_engine.geometry.prepare_room_candidate
forbidden = ('tools.diagnostics.diagnose_room_sections', 'tools.diagnostics.inspect_room_asset', 'backend.cli.import_rooms',
             'tools.diagnostics.analyze_floorplan', 'tools.diagnostics.room_section_geometry', 'tools.diagnostics.room_section_plots',
             'bpy', 'psycopg', 'matplotlib')
print(json.dumps([name for name in forbidden if name in sys.modules]), flush=True)
'''
        environment = {**os.environ, 'PYTHONPATH': str(root)}
        with tempfile.TemporaryDirectory() as folder:
            result = subprocess.run([sys.executable, '-B', '-c', code], cwd=folder, env=environment,
                                    text=True, capture_output=True, check=True, timeout=15)
            self.assertEqual(json.loads(result.stdout), [])
            self.assertEqual(list(Path(folder).iterdir()), [])
