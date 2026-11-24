"""Offline synthetic field checks; no Blender/GPU/API or real data writes."""
import json
from pathlib import Path
import tempfile
import unittest
from experiments.continuous_field import build_field, states, segment_inside, field_from_config
from render_engine.jobs.operation_logging import JsonlSink, bind_context

class ContinuousFieldTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        context=bind_context(trace_id='continuous-test',sink=JsonlSink(Path(self.temp.name)))
        context.__enter__();self.addCleanup(context.__exit__,None,None,None)
        self.ring=[[-2,-2],[2,-2],[2,2],[-2,2]]

    def test_single_source_parent_and_four_connectivity(self):
        field=build_field(self.ring,(0,0),.5,.5)
        self.assertEqual([c for c,t in field.arrival_s.items() if t==0],[(0,0)])
        for child,parent in field.parent.items():
            self.assertEqual(sum(abs(child[k]-parent[k]) for k in (0,1)),1)
            self.assertGreater(field.arrival_s[child],field.arrival_s[parent])
        self.assertEqual(field.arrival_s[(2,0)],2.)

    def test_barrier_excludes_unreachable(self):
        field=build_field(self.ring,(-1,0),.5,.5,blocked={(2,j) for j in range(-4,5)})
        self.assertTrue(field.unreachable)
        self.assertTrue(all(field.xy(c)[0]<0 for c in field.arrival_s))
        self.assertTrue(all(r['cell'] not in field.unreachable for r in states(field,100)))

    def test_concave_edges_cannot_jump_outside(self):
        ring=[[-1,-1],[1,-1],[1,1],[.2,1],[.2,-.2],[-.2,-.2],[-.2,1],[-1,1]]
        self.assertFalse(segment_inside((-.5,.5),(.5,.5),ring))
        field=build_field(ring,(-.5,.5),1,1)
        self.assertEqual(field.arrival_s[(1,0)],3.)  # detour, never the direct 1-second jump

    def test_deterministic_and_monotone_persistent_burning(self):
        a=build_field(self.ring,(0,0),.5,.5);b=build_field(self.ring,(0,0),.5,.5)
        self.assertEqual(a,b)
        previous=set()
        for t in (0,1,3,6,9,12,100):
            current={r['cell'] for r in states(a,t) if r['burning']}
            self.assertTrue(previous<=current);previous=current
        seed=next(r for r in states(a,1) if r['cell']==(0,0))
        self.assertTrue(seed['smoking']);self.assertFalse(seed['burning'])
        self.assertEqual(states(a,0)[0]['smoke_age_s'],0)

    def test_bad_inputs(self):
        for seed,h,v in (((3,0),.5,1),((0,0),0,1),((0,0),.5,0),((0,0),True,1),((0,0),float('nan'),1)):
            with self.assertRaises(ValueError):build_field(self.ring,seed,h,v)
        with self.assertRaises(ValueError):build_field(self.ring,(0,0),blocked={(0,0)})
        with self.assertRaises(ValueError):build_field([[0,0],[2,2],[0,2],[2,0]],(.5,.5))
        field=build_field(self.ring,(0,0))
        with self.assertRaises(ValueError):states(field,1,0)

    def test_experiment_config_is_offline_and_has_no_room_geometry_copy(self):
        path=Path(__file__).resolve().parents[2]/'configs/experiments/room8_continuous_a_v01.json'
        config=json.loads(path.read_text())
        self.assertNotIn('polygon_raw_xy',config)
        self.assertEqual(field_from_config(config,self.ring,(0,0)).origin,(0.,0.))
        with self.assertRaises(ValueError):field_from_config({**config,'render_authorized':True},self.ring,(0,0))

    def test_success_failure_logs_are_correlated_and_sanitized(self):
        build_field(self.ring,(0,0))
        with self.assertRaises(ValueError):build_field(self.ring,(99,0))
        events=[json.loads(line) for p in Path(self.temp.name).glob('*.jsonl') for line in p.read_text().splitlines()]
        self.assertTrue(any(e['event']=='success' and 'duration_ms' in e for e in events))
        self.assertTrue(any(e['event']=='failure' for e in events))
        self.assertTrue(all(e['trace_id']=='continuous-test' for e in events))
        self.assertFalse(any('seed_xy' in e or 'polygon' in e for e in events))
