"""PRD 2.2 / architecture 3.2: readonly geometry sections, continuity, wall evidence.

Synthetic triangles and temp input assets only. Optional Matplotlib Agg PNG test;
no bpy/Docker/server/database. python -m unittest tests.tools.test_room_sections -v
"""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import unittest

from tools.diagnostics import analyze_floorplan as align
from tools.diagnostics import inspect_room_asset as audit
from tools.diagnostics import diagnose_room_sections as diagnostic
from tools.diagnostics import room_section_geometry as geom
import tests.backend.test_room_database as fixtures


SQUARE=[(0,0),(2,0),(2,2),(0,2)]


def wall_triangles(x: float) -> list[dict]:
    points=[(x,0,-1),(x,2,-1),(x,2,2),(x,0,2)]
    mesh={'vertices':points,'faces':[{'corners':[(i,None) for i in face]} for face in ((0,1,2),(0,2,3))]}
    return geom.triangles(mesh)


class SectionGeometry(unittest.TestCase):
    def test_plane_intersection_and_coplanar_edges(self) -> None:
        tri=[(-1,0,0),(1,0,0),(0,1,2)]
        result,flat=geom.plane_segments(tri,[0,0,0],[1,0,0])
        self.assertFalse(flat);self.assertEqual(len(result),1)
        self.assertTrue(all(abs(p[0])<1e-9 for p in result[0]))
        result,flat=geom.plane_segments(tri,[0,0,0],[0,1,0])
        self.assertFalse(flat)
        result,flat=geom.plane_segments([(0,0,0),(0,1,0),(0,0,1)],[0,0,0],[1,0,0])
        self.assertTrue(flat);self.assertEqual(len(result),3)

    def test_parallel_disjoint_plane_no_false_segment(self) -> None:
        segments,flat=geom.plane_segments([(1,0,0),(1,1,0),(1,0,1)],[0,0,0],[1,0,0])
        self.assertEqual(segments,[]);self.assertFalse(flat)

    def test_concave_room_intervals_exclude_notch(self) -> None:
        polygon=[(0,0),(3,0),(3,3),(2,3),(2,1),(1,1),(1,3),(0,3)]
        self.assertEqual(geom.room_intervals(polygon,[0,2],[1,0]),[[0,1],[2,3]])

    def test_clockwise_and_counterclockwise_inward_normals(self) -> None:
        for polygon in (SQUARE,list(reversed(SQUARE))):
            for edge in geom.boundary_edges(polygon):
                point=tuple((edge['a'][k]+edge['b'][k])/2+edge['inward_normal'][k]*.01 for k in (0,1))
                self.assertTrue(align.contains(point,polygon))

    def test_connected_patches_and_height_jump(self) -> None:
        samples=[{'xy':[x,y],'bottom':z} for x,y,z in ((0,0,-1),(1,0,-1),(0,1,-1),(1,1,-.5),(3,0,-1))]
        result=geom.continuity(samples,'bottom',1)
        self.assertEqual(len(result['components']),3)
        self.assertEqual(result['components'][0]['sample_count'],3)
        self.assertEqual(result['jumps_over_15cm'],2)
        self.assertFalse(result['physical_surface_confirmed'])

    def test_wall_pair_does_not_certify_thickness_or_buffer(self) -> None:
        tris=wall_triangles(0)+wall_triangles(-.08)
        rows=geom.wall_evidence(tris,SQUARE,[0,1],[],search=.2)
        left=next(r for r in rows if r['edge_id']=='E03')
        self.assertEqual(left['hit_fraction'],1)
        self.assertAlmostEqual(left['paired_surface_separation_median_m'],.08)
        self.assertIsNone(left['wall_thickness_confirmed_m'])
        self.assertIsNone(left['buffer_approved_m'])
        self.assertAlmostEqual(left['candidate_outward_buffer_p95_plus_2cm_m'],.1)

    def test_search_limit_and_adjacent_room_intrusion(self) -> None:
        tris=wall_triangles(-.4)
        other=[{'room_id':'neighbor','polygon_raw':[(-1,0),(0,0),(0,2),(-1,2)]}]
        nohit=next(r for r in geom.wall_evidence(tris,SQUARE,[0],other,search=.2) if r['edge_id']=='E03')
        self.assertEqual(nohit['hit_fraction'],0)
        hit=next(r for r in geom.wall_evidence(tris,SQUARE,[0],other,search=.6) if r['edge_id']=='E03')
        self.assertIn('large_boundary_surface_offset_over_10cm',hit['review_flags'])
        self.assertIn('neighbor',hit['adjacent_room_intrusion_samples'])

    def test_nontriangular_source_rejected(self) -> None:
        with self.assertRaises(ValueError):
            geom.triangles({'vertices':[(0,0,0)]*4,'faces':[{'corners':[(i,None) for i in range(4)]}]})


class DiagnosticInputs(unittest.TestCase):
    setUp_base=fixtures.ImportValidation.setUp
    write_review=fixtures.ImportValidation.write_review

    def setUp(self) -> None:
        self.setUp_base()
        vertices=[(x,y,z) for z in (0,2) for x,y in ((0,0),(3,0),(3,3),(0,3))]
        faces=[(0,1,2),(0,2,3),(4,6,5),(4,7,6),(0,4,5),(0,5,1),
               (1,5,6),(1,6,2),(2,6,7),(2,7,3),(3,7,4),(3,4,0)]
        obj='mtllib mesh.mtl\n'+''.join('v %s %s %s\n'%v for v in vertices)
        obj+=''.join('vt 0 0\n' for _ in vertices)+'usemtl mat\n'
        obj+=''.join('f '+' '.join(f'{i+1}/{i+1}' for i in face)+'\n' for face in faces)
        mesh_path=self.scene/'mesh.obj';mesh_path.write_text(obj,encoding='utf-8')
        (self.scene/'mesh.mtl').write_text('newmtl mat\nmap_Kd texture.jpg\n',encoding='utf-8')
        (self.scene/'texture.jpg').write_bytes(b'synthetic texture')
        (self.scene/'output.mp4').write_bytes(b'historical video')
        probe_path=self.probe/'report.json';probe=json.loads(probe_path.read_text(encoding='utf-8'))
        probe['local_baseline']['mesh']['bytes']=mesh_path.stat().st_size
        probe_path.write_text(json.dumps(probe),encoding='utf-8')
        report,_=align.analyze(self.scene,self.probe,transform_id='xy')
        (self.output/'alignment_report.json').write_text(json.dumps(report),encoding='utf-8')
        self.review['alignment_report_sha256']=align.sha256(self.output/'alignment_report.json');self.write_review()
        self.inspection=audit.inspect(self.scene,self.probe,self.output,self.review_path,'R',.5)
        self.inspection_path=self.scene/'inspection.json'
        self.inspection_path.write_text(json.dumps(self.inspection),encoding='utf-8')
        self.evidence={'status':'passed','checks':{k:True for k in diagnostic.REQUIRED_CHECKS},
            'scene_code':self.scene.name,'room_id':'R','blender_version':'4.2.0',
            'source_mesh_sha256':align.sha256(mesh_path),'inspection_sha256':align.sha256(self.inspection_path),
            'bounds_world':self.inspection['coordinates']['raw_bounds']}
        self.blender_path=self.scene/'blender.json';self.save_evidence()

    def save_evidence(self) -> None:
        self.blender_path.write_text(json.dumps(self.evidence),encoding='utf-8')

    def load(self) -> tuple:
        return diagnostic.load_inputs(self.scene.parent,self.inspection_path,self.blender_path,self.output)

    def test_passed_evidence_and_no_auto_approval(self) -> None:
        inspection,alignment,mesh,_=self.load()
        result=diagnostic.diagnose(inspection,alignment,mesh,self.scene)
        self.assertFalse(result['ready_for_cut']);self.assertFalse(result['database_accessed'])
        self.assertTrue(all(v is None for v in result['unconfirmed'].values()))
        self.assertEqual(len(result['sections']),12)
        self.assertTrue(result['surface_region_hypotheses'])
        self.assertTrue(all(not region['physical_label_confirmed'] for region in result['surface_region_hypotheses']))

    def test_wrong_evidence_binding_or_check_rejected(self) -> None:
        original=deepcopy(self.evidence)
        for change in ({'inspection_sha256':'wrong'},{'room_id':'other'}, {'status':'failed'},
                       {'checks':{**original['checks'],'uv_finite':False}}):
            self.evidence={**original,**change};self.save_evidence()
            with self.assertRaises(ValueError):self.load()

    def test_changed_texture_or_source_rejected(self) -> None:
        (self.scene/'texture.jpg').write_bytes(b'changed')
        with self.assertRaises(ValueError):self.load()

    @unittest.skipUnless(importlib.util.find_spec('matplotlib'),'Optional PNG diagnostics dependency')
    def test_png_report_and_all_source_files_unchanged(self) -> None:
        before={p:align.sha256(p) for p in self.scene.rglob('*') if p.is_file()}
        report,output=diagnostic.run(self.scene.parent,self.inspection_path,self.blender_path,self.output)
        self.assertTrue(report['source_and_history_unchanged'])
        self.assertFalse(report['ready_for_cut'])
        self.assertTrue((output/'index.html').is_file())
        for name in report['images']:
            content=(output/name).read_bytes()
            self.assertTrue(content.startswith(b'\x89PNG\r\n\x1a\n'))
            self.assertGreater(len(content),1000)
        for path,digest in before.items():self.assertEqual(align.sha256(path),digest)
