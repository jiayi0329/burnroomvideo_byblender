"""PRD 2.2 / architecture 3.2: room-only preview and conservative display cleanup.

app/room_demo_plan.py; synthetic offline unit tests, no bpy/DB/network/real files.
Run locally: python -m unittest test.test_room_demo_plan -v
"""
from copy import deepcopy
import unittest
from app.room_demo_plan import components, display_faces, room_timeline, envelope


def face(x: float) -> dict:
    return {'material':'texture','corners':[[x,0,0,0,0],[x+1,0,0,1,0],[x,1,0,0,1]]}


class DisplayComponents(unittest.TestCase):
    def test_coincident_vertices_connect_despite_uv_seams(self) -> None:
        faces=[face(0),{'material':'other','corners':[[1,0,0,.2,.4],[2,0,0,0,0],[2,1,0,0,0]]},face(10)]
        result=components(faces)
        self.assertEqual([c['face_count'] for c in result],[2,1])

    def test_no_automatic_removal_and_original_uv_material_unchanged(self) -> None:
        faces=[face(0),face(10)]; before=deepcopy(faces)
        kept,report=display_faces(faces,[])
        self.assertEqual(kept,faces); self.assertEqual(faces,before)
        self.assertTrue(all(c['decision'].startswith('preserve') for c in report))

    def test_only_explicit_component_is_hidden(self) -> None:
        faces=[face(0),face(10)]
        kept,report=display_faces(faces,[1])
        self.assertEqual(kept,[faces[0]])
        self.assertIn('explicit',report[1]['decision'])
        with self.assertRaises(ValueError):display_faces(faces,[999])


class RoomSpread(unittest.TestCase):
    def points(self) -> list[dict]:
        return [{'id':1,'device':22,'visibles':[2,3]}, {'id':2,'device':32,'visibles':[4]},
                {'id':3,'device':0,'visibles':[]}, {'id':4,'device':40,'visibles':[]}]

    def test_recompute_room_subgraph_does_not_use_outside_bridge(self) -> None:
        result=room_timeline(self.points(),[22,0,40],22)
        self.assertEqual(result['spread_events'],[{'point':22,'time':0},{'point':0,'time':1.5}])
        self.assertEqual(result['unreachable_interior_devices'],[40])
        self.assertNotIn(32,[e['point'] for e in result['spread_events']])

    def test_unknown_neighbors_ignored_and_device_not_internal_id_used(self) -> None:
        points=self.points(); points[2]['visibles']=[4,999]
        before=deepcopy(points)
        result=room_timeline(points,[22,0,40],22,2)
        self.assertEqual(result['spread_events'][-1],{'point':40,'time':4})
        self.assertEqual(points,before)

    def test_bad_ignition_duplicate_or_bad_time_rejected(self) -> None:
        for points,allowed,start,seconds in ((self.points(),[0],22,1),
                (self.points()+self.points()[:1],[22],22,1),(self.points(),[22],22,float('nan'))):
            with self.assertRaises(ValueError):room_timeline(points,allowed,start,seconds)

    def test_gradual_growth_and_embers_have_multiple_levels(self) -> None:
        keys=envelope(1.5,12)
        self.assertEqual([v for _,v in keys],[0,.25,.6,1,.6,.2,0])
        self.assertEqual(keys[3][0]-keys[0][0],36)
        self.assertTrue(all(a[0]<b[0] for a,b in zip(keys,keys[1:])))
        with self.assertRaises(ValueError):envelope(-1,12)


if __name__=='__main__':unittest.main()
