"""PRD 2.2 / architecture 3.2: small display component audit and room-only BFS.

No Blender, DB, network or source mutation. Component IDs are evidence, not
automatic semantic decisions: small/disconnected geometry is preserved by default.
"""
from __future__ import annotations

from collections import deque
import math


def components(faces: list[dict]) -> list[dict]:
    parents = list(range(len(faces)))

    def root(i: int) -> int:
        while parents[i] != i:
            parents[i] = parents[parents[i]]
            i = parents[i]
        return i

    owners = {}
    for i, face in enumerate(faces):
        for corner in face['corners']:
            key = tuple(round(v,5) for v in corner[:3])
            if key in owners:
                a,b = root(i),root(owners[key])
                parents[a] = b
            owners[key] = i
    groups = {}
    for i in range(len(faces)):
        groups.setdefault(root(i),[]).append(i)
    result = []
    for indices in sorted(groups.values(),key=lambda ids:ids[0]):
        points = [v for i in indices for v in faces[i]['corners']]
        lo = [min(p[k] for p in points) for k in range(3)]
        hi = [max(p[k] for p in points) for k in range(3)]
        result.append({'component_id':len(result),'face_indices':indices,'face_count':len(indices),
                       'bounds_min':lo,'bounds_max':hi,'diagonal_m':math.dist(lo,hi),
                       'decision':'preserve; disconnected does not imply useless'})
    return result


def display_faces(faces: list[dict], drops: list[int]) -> tuple[list[dict],list[dict]]:
    groups = components(faces)
    known = {c['component_id'] for c in groups}
    if not set(drops) <= known:
        raise ValueError('Unknown component ID')
    removed = {i for c in groups if c['component_id'] in drops for i in c['face_indices']}
    for c in groups:
        if c['component_id'] in drops:
            c['decision'] = 'hidden in display derivative by explicit user-selected component ID'
    return [f for i,f in enumerate(faces) if i not in removed],groups


def room_timeline(points: list[dict], interior: list[int], ignition: int,
                  layer_seconds: float=1.5) -> dict:
    if not math.isfinite(layer_seconds) or layer_seconds <= 0:
        raise ValueError('Layer interval must be positive')
    allowed = set(interior)
    lookup = {int(p['device']):p for p in points}
    ids = {p['id']:int(p['device']) for p in points}
    if len(lookup)!=len(points) or len(ids)!=len(points):
        raise ValueError('Duplicate device/internal ID')
    if ignition not in allowed or not allowed <= lookup.keys():
        raise ValueError('Room/ignition points missing')
    adjacency = {device:sorted({ids[i] for i in lookup[device].get('visibles',[]) if i in ids} & allowed)
                 for device in allowed}
    depth = {ignition:0}
    pending = deque([ignition])
    while pending:
        current = pending.popleft()
        for neighbor in adjacency[current]:
            if neighbor not in depth:
                depth[neighbor] = depth[current]+1
                pending.append(neighbor)
    return {'start_point':ignition,'spread_events':[{'point':p,'time':d*layer_seconds}
            for p,d in sorted(depth.items(),key=lambda item:(item[1],item[0]))],
            'unreachable_interior_devices':sorted(allowed-depth.keys()),
            'allowed_devices':sorted(allowed),'layer_seconds':layer_seconds,
            'note':'Room-induced graph recomputed; presentation timing, not physical fire simulation. Doorway excluded.'}


def envelope(start: float, fps: int) -> list[tuple[int,float]]:
    # Three-second gradual growth followed by embers; Bezier interpolation.
    if not math.isfinite(start) or start<0 or not isinstance(fps,int) or fps<2:
        raise ValueError('Nonnegative start and integer FPS >=2 required')
    return [(round((start+t)*fps)+1,value) for t,value in
            ((0,0),(.9,.25),(1.9,.6),(3,1),(4.5,.6),(6,.2),(8,0))]
