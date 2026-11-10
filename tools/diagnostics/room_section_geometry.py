"""Read-only triangle sections, spatial continuity and boundary surface evidence.

Labels describe geometric evidence, never certify floor/ceiling/wall semantics.
"""
from __future__ import annotations

from collections import Counter, deque
import math
from statistics import median
from typing import Any

from render_engine.geometry.floorplan_alignment import contains, edges


def cross(a: list | tuple, b: list | tuple) -> float:
    return a[0] * b[1] - a[1] * b[0]


def quantile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    at = (len(ordered) - 1) * q
    lo = int(at)
    return ordered[lo] + (ordered[min(lo + 1, len(ordered) - 1)] - ordered[lo]) * (at - lo)


def triangles(mesh: dict) -> list[dict]:
    result = []
    for i, face in enumerate(mesh['faces']):
        if len(face['corners']) != 3:
            raise ValueError('Section diagnostics requires triangular source faces; no implicit triangulation')
        p = [mesh['vertices'][v] for v, _ in face['corners']]
        u = [p[1][k] - p[0][k] for k in range(3)]
        v = [p[2][k] - p[0][k] for k in range(3)]
        n = [u[1]*v[2]-u[2]*v[1], u[2]*v[0]-u[0]*v[2], u[0]*v[1]-u[1]*v[0]]
        norm = math.sqrt(sum(c*c for c in n))
        if norm < 1e-12:
            continue
        result.append({'face_id': i, 'points': p, 'normal': [c/norm for c in n],
                       'center': [sum(v[k] for v in p)/3 for k in range(3)], 'area': norm/2})
    return result


def plane_segments(points: list, origin: list | tuple, normal: list | tuple, eps: float = 1e-8) -> tuple[list, bool]:
    """Intersect one triangle with a plane; coplanar triangles expose all edges."""
    d = [sum((p[k]-origin[k])*normal[k] for k in range(3)) for p in points]
    if all(abs(v) <= eps for v in d):
        return [(points[i], points[(i+1)%3]) for i in range(3)], True
    hits = []
    for i in range(3):
        j = (i+1)%3
        if abs(d[i]) <= eps:
            hits.append(points[i])
        if d[i]*d[j] < 0:
            t = d[i]/(d[i]-d[j])
            hits.append(tuple(points[i][k]+t*(points[j][k]-points[i][k]) for k in range(3)))
    unique = []
    for p in hits:
        if not any(sum((p[k]-q[k])**2 for k in range(3)) <= eps**2 for q in unique):
            unique.append(p)
    return ([(unique[0], unique[1])] if len(unique) == 2 else []), False


def room_intervals(polygon: list, origin: list, direction: list) -> list[list[float]]:
    normal = [-direction[1], direction[0]]
    positions = []
    for a, b in edges(polygon):
        da = sum((a[k]-origin[k])*normal[k] for k in (0,1))
        db = sum((b[k]-origin[k])*normal[k] for k in (0,1))
        if abs(da) < 1e-9:
            positions.append(sum((a[k]-origin[k])*direction[k] for k in (0,1)))
        if da*db < 0:
            t = da/(da-db)
            p = [a[k]+t*(b[k]-a[k]) for k in (0,1)]
            positions.append(sum((p[k]-origin[k])*direction[k] for k in (0,1)))
    ordered = sorted(set(round(p,9) for p in positions))
    return [[a,b] for a,b in zip(ordered,ordered[1:])
            if contains(tuple(origin[k]+(a+b)/2*direction[k] for k in (0,1)), polygon)]


def boundary_edges(polygon: list) -> list[dict]:
    ccw = sum(cross(a,b) for a,b in edges(polygon)) > 0
    result = []
    for i,(a,b) in enumerate(edges(polygon)):
        length = math.dist(a,b)
        if length < 1e-10:
            continue
        tangent = [(b[k]-a[k])/length for k in (0,1)]
        normal = [-tangent[1], tangent[0]]
        if not ccw:
            normal = [-v for v in normal]
        result.append({'edge_id': f'E{i:02}', 'a': a, 'b': b, 'length_m': length,
                       'inward_normal': normal, 'tangent': tangent})
    return result


def select_sections(polygon: list, samples: list, ignition: list | None, wall_window: float) -> list[dict]:
    result = []
    for axis in (0,1):
        for q in (.2,.5,.8):
            value = quantile([p['xy'][axis] for p in samples], q)
            origin = [value,0.0] if axis == 0 else [0.0,value]
            direction = [0.0,1.0] if axis == 0 else [1.0,0.0]
            result.append({'id': f'{"X" if axis==0 else "Y"}{int(q*100)}', 'kind': 'interior',
                           'origin': origin, 'direction': direction})
    if ignition:
        for axis in (0,1):
            result.append({'id': f'IGN_{"X" if axis==0 else "Y"}', 'kind': 'ignition',
                           'origin': ignition[:2], 'direction': [0.,1.] if axis==0 else [1.,0.]})
    for edge in boundary_edges(polygon):
        if edge['length_m'] >= .3:
            result.append({'id': 'W_'+edge['edge_id'], 'kind': 'boundary', 'edge_id': edge['edge_id'],
                           'origin': [(edge['a'][k]+edge['b'][k])/2 for k in (0,1)],
                           'direction': edge['inward_normal'], 'window': [-wall_window,wall_window]})
    for section in result:
        section['room_intervals'] = room_intervals(polygon,section['origin'],section['direction'])
        if 'window' not in section:
            ts = [sum((p[k]-section['origin'][k])*section['direction'][k] for k in (0,1)) for p in polygon]
            section['window'] = [min(ts)-.4,max(ts)+.4]
    return result


def surface_role(triangle: dict, samples: list, spacing: float) -> str:
    nz = abs(triangle['normal'][2])
    if nz <= .25:
        return 'vertical_wall_like'
    if nz < .95:
        return 'sloped_or_uncertain'
    x,y,z = triangle['center']
    nearest = min(samples, key=lambda p:(p['xy'][0]-x)**2+(p['xy'][1]-y)**2)
    if math.dist(nearest['xy'],(x,y)) > spacing*1.7:
        return 'horizontal_uncertain'
    if nearest['bottom'] is not None and abs(z-nearest['bottom']) <= .08:
        return 'lower_envelope_candidate'
    if nearest['top'] is not None and abs(z-nearest['top']) <= .08:
        return 'upper_envelope_candidate'
    return 'interior_horizontal_candidate'


def section_geometry(tris: list[dict], section: dict) -> dict:
    origin = [*section['origin'],0.0]
    u = section['direction']
    normal = [-u[1],u[0],0.0]
    result = []; coplanar = 0
    for tri in tris:
        segments, flat = plane_segments(tri['points'],origin,normal)
        coplanar += flat
        for a,b in segments:
            pair = [[sum((p[k]-origin[k])*u[k] for k in (0,1)),p[2]] for p in (a,b)]
            if max(p[0] for p in pair) < section['window'][0] or min(p[0] for p in pair) > section['window'][1]:
                continue
            result.append({'face_id':tri['face_id'],'role':tri['role'],'coplanar':flat,'tz':pair})
    return {**section,'segments':result,'coplanar_triangles':coplanar}


def continuity(samples: list, field: str, spacing: float) -> dict[str, Any]:
    if not samples:
        raise ValueError('Height sample set is empty')
    x0 = min(p['xy'][0] for p in samples); y0 = min(p['xy'][1] for p in samples)
    cells = {(round((p['xy'][0]-x0)/spacing),round((p['xy'][1]-y0)/spacing)):p
             for p in samples if p[field] is not None}
    bins = {key:round(p[field]/.05) for key,p in cells.items()}
    pending = set(cells); components = []
    while pending:
        seed = min(pending); pending.remove(seed); queue = deque([seed]); keys = []
        while queue:
            key = queue.popleft(); keys.append(key)
            for near in ((key[0]-1,key[1]),(key[0]+1,key[1]),(key[0],key[1]-1),(key[0],key[1]+1)):
                if near in pending and bins[near] == bins[seed]:
                    pending.remove(near); queue.append(near)
        xy = [cells[k]['xy'] for k in keys]
        components.append({'z_bin_m':round(bins[seed]*.05,3),'sample_count':len(keys),
            'sampled_area_estimate_m2':len(keys)*spacing*spacing,
            'xy_bounds':{'min':[min(p[k] for p in xy) for k in (0,1)],'max':[max(p[k] for p in xy) for k in (0,1)]},
            'sample_xy':xy})
    components.sort(key=lambda c:(-c['sample_count'],c['z_bin_m']))
    differences = [abs(p[field]-cells[near][field]) for key,p in cells.items()
                   for near in ((key[0]+1,key[1]),(key[0],key[1]+1)) if near in cells]
    return {'components':components,'height_bin_m':.05,'connectivity':'4-neighbor, same 5cm bin',
            'neighbor_pairs':len(differences),'jumps_over_15cm':sum(v>.15 for v in differences),
            'neighbor_jump_p90_m':quantile(differences,.9),'physical_surface_confirmed':False}


def ray_segment(origin: list, direction: list, a: list, b: list) -> float | None:
    delta = [b[k]-a[k] for k in (0,1)]; base = [a[k]-origin[k] for k in (0,1)]
    den = cross(direction,delta)
    if abs(den) < 1e-10:
        return None
    t = cross(base,delta)/den; u = cross(base,direction)/den
    return t if -1e-8 <= u <= 1+1e-8 else None


def wall_evidence(tris: list, polygon: list, heights: list[float], other_rooms: list,
                  search: float=.6, station_spacing: float=.25) -> list[dict]:
    horizontal = {z:[] for z in heights}
    for z in heights:
        for tri in tris:
            if abs(tri['normal'][2]) > .25:
                continue
            segments,_ = plane_segments(tri['points'],[0,0,z],[0,0,1])
            for a,b in segments:
                horizontal[z].append((a,b,tri))
    result = []
    for edge in boundary_edges(polygon):
        row = {**edge,'height_levels_m':heights,'signed_distance_convention':'positive=inward, negative=outside room',
               'wall_thickness_confirmed_m':None,'buffer_approved_m':None}
        if edge['length_m'] < .3:
            row.update(status='too_short_for_wall_estimate',samples=[]); result.append(row); continue
        n = edge['inward_normal']; samples = []; pairs = []
        count = max(1,math.ceil(edge['length_m']/station_spacing))
        for z in heights:
            candidates = [(a,b,t) for a,b,t in horizontal[z]
                          if abs(sum(t['normal'][k]*n[k] for k in (0,1))) >= math.cos(math.radians(15))]
            for i in range(count):
                distance = edge['length_m']*(i+.5)/count
                point = [edge['a'][k]+edge['tangent'][k]*distance for k in (0,1)]
                hits = sorted((offset,t['face_id']) for a,b,t in candidates
                              if (offset:=ray_segment(point,n,a,b)) is not None and abs(offset) <= search)
                distinct = []
                for offset,face in hits:
                    if not distinct or abs(offset-distinct[-1][0]) > .003:
                        distinct.append((offset,face))
                closest = min(distinct,key=lambda p:abs(p[0]))[0] if distinct else None
                separation = None
                if closest is not None:
                    pair_values = [abs(t-closest) for t,_ in distinct if .02 <= abs(t-closest) <= .5]
                    separation = min(pair_values) if pair_values else None
                if separation is not None:
                    pairs.append(separation)
                samples.append({'along_edge_m':distance,'xy':point,'z_m':z,'nearest_offset_m':closest,
                                'surface_offsets_m':[p[0] for p in distinct], 'face_ids':[p[1] for p in distinct],
                                'paired_surface_separation_candidate_m':separation})
        offsets = [s['nearest_offset_m'] for s in samples if s['nearest_offset_m'] is not None]
        outside = [-offset for sample in samples for offset in sample['surface_offsets_m']
                   if offset < 0 and sample['nearest_offset_m'] is not None
                   and (abs(offset-sample['nearest_offset_m']) <= .003 or .02 <= abs(offset-sample['nearest_offset_m']) <= .5)]
        coverage = len(offsets)/len(samples)
        candidate = math.ceil(((quantile(outside,.95) or 0)+.02)/.005)*.005 if coverage >= .5 else None
        intrusion = Counter()
        if candidate is not None:
            for i in range(count):
                point = [edge['a'][k]+edge['tangent'][k]*edge['length_m']*(i+.5)/count for k in (0,1)]
                for fraction in (.5,1.):
                    outward = tuple(point[k]-n[k]*candidate*fraction for k in (0,1))
                    for room in other_rooms:
                        if contains(outward,room['polygon_raw']):
                            intrusion[room['room_id']] += 1
        row.update(status='review_required',samples=samples,hit_fraction=coverage,
            nearest_offset_median_m=median(offsets) if offsets else None,
            abs_offset_p90_m=quantile([abs(v) for v in offsets],.9),
            outward_observed_max_m=max(outside) if outside else None,
            paired_surface_sample_count=len(pairs),paired_surface_separation_median_m=quantile(pairs,.5),
            paired_surface_separation_p10_m=quantile(pairs,.1),paired_surface_separation_p90_m=quantile(pairs,.9),
            candidate_outward_buffer_p95_plus_2cm_m=candidate, adjacent_room_intrusion_samples=dict(intrusion),
            warning='Parallel surfaces can be furniture or different walls; pair separation is not certified solid wall thickness. Candidate buffer is not applied.')
        row['review_flags']=[]
        if coverage < .75:row['review_flags'].append('incomplete_parallel_surface_coverage')
        if (row['abs_offset_p90_m'] or 0) > .1:row['review_flags'].append('large_boundary_surface_offset_over_10cm')
        if intrusion:row['review_flags'].append('candidate_buffer_enters_adjacent_room_polygon')
        if not pairs:row['review_flags'].append('no_paired_surface_thickness_evidence')
        result.append(row)
    return result
