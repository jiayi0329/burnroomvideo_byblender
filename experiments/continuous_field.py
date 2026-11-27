"""A2 CPU-only single-source arrival field. No bpy, subprocess, DB or renderer.

Coordinates are raw scan XY in metres. Times/speeds are artistic controls,
not fire physics. A grid support is not a rendered continuous flame surface.
"""
from dataclasses import dataclass
import heapq
import math

from render_engine.jobs.operation_logging import traced

Cell = tuple[int, int]


def finite(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError('Expected finite number')
    return float(value)


def inside(p, ring):
    x, y = p
    result = False
    for a, b in zip(ring, ring[1:] + ring[:1]):
        cross = (x-a[0])*(b[1]-a[1])-(y-a[1])*(b[0]-a[0])
        if abs(cross) < 1e-10 and min(a[0], b[0])-1e-10 <= x <= max(a[0], b[0])+1e-10 and min(a[1], b[1])-1e-10 <= y <= max(a[1], b[1])+1e-10:
            return True
        if (a[1] > y) != (b[1] > y) and x < (b[0]-a[0])*(y-a[1])/(b[1]-a[1])+a[0]:
            result = not result
    return result


def segment_inside(a, b, ring):
    """Both endpoints inside is insufficient for a concave room: test intervals."""
    def cross(u, v): return u[0]*v[1]-u[1]*v[0]
    direction = (b[0]-a[0], b[1]-a[1])
    cuts = [0., 1.]
    for c, d in zip(ring, ring[1:]+ring[:1]):
        edge = (d[0]-c[0], d[1]-c[1]); offset = (c[0]-a[0], c[1]-a[1])
        determinant = cross(direction, edge)
        if abs(determinant) > 1e-12:
            t, u = cross(offset, edge)/determinant, cross(offset, direction)/determinant
            if 0 <= t <= 1 and 0 <= u <= 1: cuts.append(t)
    cuts = sorted(set(cuts))
    return all(inside((a[0]+direction[0]*(lo+hi)/2, a[1]+direction[1]*(lo+hi)/2), ring) for lo, hi in zip(cuts, cuts[1:]))


@dataclass
class ArrivalField:
    origin: tuple[float, float]
    spacing_m: float
    allowed: frozenset[Cell]
    arrival_s: dict[Cell, float]
    parent: dict[Cell, Cell]
    distance_m: dict[Cell,float] | None = None

    def xy(self, cell):
        return (self.origin[0]+cell[0]*self.spacing_m, self.origin[1]+cell[1]*self.spacing_m)

    @property
    def unreachable(self):
        return self.allowed-self.arrival_s.keys()


@traced('room.continuous.experiment', 'build_arrival_field')
def build_field(polygon, seed_xy, spacing_m=0.2, speed_m_s=0.35, blocked=()):
    # Reuse strict geometry validation, not the R3 task/worker or its signatures.
    from render_engine.geometry.room_clip_geometry import triangulate
    if not isinstance(polygon, (list, tuple)) or not 3 <= len(polygon) <= 128:
        raise ValueError('Invalid polygon')
    ring = [tuple(finite(v) for v in p) for p in polygon]
    if any(abs(v)>1e6 for p in ring for v in p):raise ValueError('Coordinate budget exceeded')
    if any(len(p) != 2 for p in ring) or len(set(ring)) != len(ring): raise ValueError('Invalid vertices')
    def orient(a,b,c): return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
    edges=list(zip(ring,ring[1:]+ring[:1]))
    for i,(a,b) in enumerate(edges):
        for j,(c,d) in enumerate(edges):
            if j<=i+1 or i==0 and j==len(edges)-1: continue
            if all(max(min(a[k],b[k]),min(c[k],d[k])) <= min(max(a[k],b[k]),max(c[k],d[k]))+1e-12 for k in (0,1)) and orient(a,b,c)*orient(a,b,d)<=0 and orient(c,d,a)*orient(c,d,b)<=0:
                raise ValueError('Self intersecting polygon')
    triangulate(ring)
    if len(seed_xy)!=2:raise ValueError('Invalid seed')
    seed=tuple(finite(v) for v in seed_xy)
    spacing, speed=finite(spacing_m),finite(speed_m_s)
    if not .02<=spacing<=1 or not .001<=speed<=10 or not inside(seed,ring):raise ValueError('Invalid seed or grid controls')
    blocked=set(blocked)
    if any(not isinstance(c,tuple) or len(c)!=2 or any(type(v) is not int for v in c) for c in blocked):raise ValueError('Invalid blocked cells')
    bounds=[(math.ceil((min(p[k] for p in ring)-seed[k])/spacing),math.floor((max(p[k] for p in ring)-seed[k])/spacing)) for k in (0,1)]
    if math.prod(hi-lo+1 for lo,hi in bounds)>100000:raise ValueError('Grid budget exceeded')
    def xy(c):return (seed[0]+c[0]*spacing,seed[1]+c[1]*spacing)
    allowed=frozenset((i,j) for i in range(bounds[0][0],bounds[0][1]+1) for j in range(bounds[1][0],bounds[1][1]+1) if (i,j) not in blocked and inside(xy((i,j)),ring))
    if (0,0) not in allowed:raise ValueError('Blocked seed')
    times={(0,0):0.}; parent={};queue=[(0.,(0,0))]
    while queue:
        time,cell=heapq.heappop(queue)
        if time!=times[cell]:continue
        for di,dj in ((-1,0),(0,-1),(0,1),(1,0)):
            other=(cell[0]+di,cell[1]+dj)
            if other not in allowed or not segment_inside(xy(cell),xy(other),ring):continue
            arrival=time+spacing/speed
            if arrival<times.get(other,math.inf):
                times[other]=arrival;parent[other]=cell;heapq.heappush(queue,(arrival,other))
    return ArrivalField(seed,spacing,allowed,times,parent)


@traced('room.continuous.experiment','configured_arrival_field')
def field_from_config(config, polygon, seed_xy):
    """Caller supplies fingerprint-verified geometry, not a hardcoded room outline.

    This helper does not verify private asset bytes or authorize rendering.
    """
    scope=config.get('scope')
    if config.get('schema_version')!=1 or scope not in ('offline_arrival_field_only','independent_visual_experiment') or type(config.get('render_authorized')) is not bool or (scope=='offline_arrival_field_only' and config['render_authorized']):
        raise ValueError('Offline experiment configuration required')
    controls=config['field']
    if controls['neighborhood']!=4:raise ValueError('Only four-neighbor propagation supported')
    field=build_field(polygon,seed_xy,controls['spacing_m'],controls['visual_speed_m_s'],
                      blocked=[tuple(c) for c in controls['blocked_cells']])
    if 'accelerated_visual' in config:
        a=config['accelerated_visual'];curve=a['front_distance_m'];lead=finite(config['visual']['smoke_lead_s'])
        if a['domain_kind']!='explicit_hypothetical_room8_visual_support':raise ValueError('Explicit visual domain required')
        if len(curve)<2 or curve[0][1]!=0 or curve[0][0]<lead:raise ValueError('Invalid accelerated front origin')
        if abs(curve[0][0]-lead-finite(a['smoke_start_s']))>1e-9:raise ValueError('Seed smoke time differs from front schedule')
        if any(not 0<=finite(t)<=60 or finite(d)<0 for t,d in curve):raise ValueError('Invalid front curve')
        if any(b[0]<=c[0] or b[1]<=c[1] for c,b in zip(curve,curve[1:])):raise ValueError('Front curve must increase')
        def inverse(distance):
            if distance>curve[-1][1]:return curve[-1][0]+(distance-curve[-1][1])/(curve[-1][1]-curve[-2][1])*(curve[-1][0]-curve[-2][0])
            for left,right in zip(curve,curve[1:]):
                if distance<=right[1]:return left[0]+(right[0]-left[0])*(distance-left[1])/(right[1]-left[1])
        times={c:inverse(t*controls['visual_speed_m_s'])-lead for c,t in field.arrival_s.items()}
        field=ArrivalField(field.origin,field.spacing_m,field.allowed,times,field.parent,{c:t*controls['visual_speed_m_s'] for c,t in field.arrival_s.items()})
    return field


def states(field, seconds, flame_delay_s=1.5):
    """Future renderer input only: no meshes/materials/smoke simulation created."""
    t,delay=finite(seconds),finite(flame_delay_s)
    if t<0 or delay<=0:raise ValueError('Nonnegative time and positive smoke lead required')
    return [{'cell':cell,'xy_m':field.xy(cell),'arrival_s':arrival,
             'smoke_age_s':max(0.,t-arrival),'flame_age_s':max(0.,t-arrival-delay),
             'smoking':t>arrival,'burning':t>arrival+delay}
            for cell,arrival in sorted(field.arrival_s.items()) if arrival<=t]
