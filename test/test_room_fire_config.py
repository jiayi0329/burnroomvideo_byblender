"""PRD 2.2 round-one approval / architecture 3.2: separated config and fire mesh.

app/room_fire_config.py; pure synthetic/unit tests. No Blender, network, DB or
real scene writes. Local: python -m unittest test.test_room_fire_config -v
"""
from collections import Counter
from copy import deepcopy
import math
from pathlib import Path
import unittest

from app.room_fire_config import load_config,validate,curve_value,tongue_specs,flame_mesh


CONFIG=Path(__file__).resolve().parents[1]/'app/room_fire_round1.json'


class StyleConfig(unittest.TestCase):
    def setUp(self) -> None:
        self.config=load_config(CONFIG)

    def test_approved_lighting_and_unchanged_event_policy(self) -> None:
        self.assertEqual(self.config['art']['exposure'],-.5)
        self.assertEqual(self.config['art']['world_strength'],.15)
        self.assertEqual([l['energy'] for l in self.config['art']['area_lights']],[500,150,300])
        self.assertEqual(self.config['events']['layer_seconds'],1.5)
        self.assertEqual(self.config['events']['excluded_devices'],[32,42])

    def test_config_does_not_permit_changing_membership_policy(self) -> None:
        for key,value in (('layer_seconds',2),('excluded_devices',[])):
            config=deepcopy(self.config); config['events'][key]=value
            with self.assertRaises(ValueError):validate(config)

    def test_bad_numbers_counts_bloom_or_flicker_rejected(self) -> None:
        for group,key,value in [('flame','primary_tongues',9),('flame','secondary_tongues',0),
                               ('flame','density',float('nan')),('flame','flicker_hz',20)]:
            config=deepcopy(self.config); config['art'][group][key]=value
            with self.assertRaises(ValueError):validate(config)
        config=deepcopy(self.config);config['quality']['bloom']=True
        with self.assertRaises(ValueError):validate(config)

    def test_smoke_persists_and_grows_after_flame_declines(self) -> None:
        fire=curve_value(self.config['events']['fire_curve'],6)
        smoke=curve_value(self.config['art']['smoke']['density_curve'],6)
        self.assertAlmostEqual(fire,.2);self.assertEqual(smoke,1)
        self.assertGreater(curve_value(self.config['art']['smoke']['growth_curve'],8),
                           curve_value(self.config['art']['smoke']['growth_curve'],3))
        self.assertGreater(curve_value(self.config['art']['smoke']['density_curve'],10),0)
        self.assertEqual(curve_value(self.config['art']['smoke']['density_curve'],-.1),0)

    def test_seed_is_stable_but_secondary_shapes_differ(self) -> None:
        before=deepcopy(self.config)
        primary=tongue_specs(self.config,22,True)
        self.assertEqual(primary,tongue_specs(self.config,22,True))
        self.assertEqual(len(primary),4)
        self.assertEqual(len(tongue_specs(self.config,0,False)),2)
        self.assertNotEqual(tongue_specs(self.config,0,False),tongue_specs(self.config,2,False))
        self.assertGreater(len({t['height'] for t in primary}),1)
        self.assertEqual(before,self.config)

    def test_curved_tongue_mesh_is_closed_and_finite(self) -> None:
        specs=tongue_specs(self.config,22,True)
        vertices,faces=flame_mesh(specs,9,12)
        self.assertEqual(len(vertices),4*9*12)
        self.assertTrue(all(math.isfinite(v) for p in vertices for v in p))
        edges=Counter(tuple(sorted((face[i],face[(i+1)%len(face)]))) for face in faces for i in range(len(face)))
        self.assertTrue(all(count==2 for count in edges.values()))
        self.assertTrue(all(0<=i<len(vertices) for face in faces for i in face))
        bottom=vertices[:12]; top=vertices[8*12:9*12]
        self.assertNotEqual([sum(p[k] for p in bottom)/12 for k in (0,1)],
                            [sum(p[k] for p in top)/12 for k in (0,1)])


if __name__=='__main__':unittest.main()
