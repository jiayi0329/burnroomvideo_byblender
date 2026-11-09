"""PRD 2.2 / architecture 3.2: concave XY prism clipping with corner UVs.

Pure Python; source triangles are never mutated. Coordinates remain in raw OBJ.
"""
from __future__ import annotations

import math

EPS = 1e-9


def cross(a: list, b: list, c: list) -> float:
    return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])


def triangulate(polygon: list) -> list[list]:
    """Ear clipping; retain tiny but valid edges in the reviewed boundary."""
    p = [list(v) for v in polygon]
    if len(p) < 3 or any(len(v) != 2 or not all(math.isfinite(x) for x in v) for v in p):
        raise ValueError('Invalid room polygon')
    area = sum(p[i][0]*p[(i+1)%len(p)][1]-p[(i+1)%len(p)][0]*p[i][1] for i in range(len(p)))
    if abs(area) < EPS:
        raise ValueError('Empty polygon')
    if area < 0:
        p.reverse()
    pending = list(range(len(p)))
    result = []
    while len(pending) > 3:
        found = False
        for j, b in enumerate(pending):
            a, c = pending[j-1], pending[(j+1)%len(pending)]
            if cross(p[a], p[b], p[c]) <= EPS:
                continue
            if any(all(cross(u, v, p[k]) >= -EPS for u, v in
                       ((p[a], p[b]), (p[b], p[c]), (p[c], p[a])))
                   for k in pending if k not in (a, b, c)):
                continue
            result.append([p[a], p[b], p[c]])
            pending.pop(j)
            found = True
            break
        if not found:
            raise ValueError('Cannot triangulate room polygon; check duplicate/collinear/self-intersecting edges')
    result.append([p[k] for k in pending])
    return result


def halfplane(corners: list[list], a: list, b: list) -> list[list]:
    """Sutherland-Hodgman; each corner carries XYZ and UV (five scalars)."""
    if not corners:
        return []
    result = []
    previous = corners[-1]
    dp = cross(a, b, previous)
    for current in corners:
        dc = cross(a, b, current)
        if (dc >= -EPS) != (dp >= -EPS):
            t = dp/(dp-dc)
            result.append([previous[k]+t*(current[k]-previous[k]) for k in range(5)])
        if dc >= -EPS:
            result.append(list(current))
        previous, dp = current, dc
    clean = []
    for v in result:
        if not clean or sum((v[k]-clean[-1][k])**2 for k in range(3)) > EPS**2:
            clean.append(v)
    if len(clean) > 1 and sum((clean[0][k]-clean[-1][k])**2 for k in range(3)) <= EPS**2:
        clean.pop()
    return clean


def area3(corners: list[list]) -> float:
    a, b, c = corners
    u, v = [[q[k]-a[k] for k in range(3)] for q in (b, c)]
    return .5*math.sqrt(sum(x*x for x in
        (u[1]*v[2]-u[2]*v[1], u[2]*v[0]-u[0]*v[2], u[0]*v[1]-u[1]*v[0])))


def clip_mesh(mesh: dict, polygon: list) -> dict:
    cells = triangulate(polygon)
    faces = []
    for face_id, face in enumerate(mesh['faces']):
        if len(face['corners']) != 3 or any(uv is None for _, uv in face['corners']):
            raise ValueError('Triangular source faces with complete UVs required')
        source = [list(mesh['vertices'][v])+list(mesh['uvs'][uv]) for v, uv in face['corners']]
        seen = set()
        for cell in cells:
            clipped = source
            for j in range(3):
                clipped = halfplane(clipped, cell[j], cell[(j+1)%3])
            for j in range(1, len(clipped)-1):
                triangle = [clipped[0], clipped[j], clipped[j+1]]
                if area3(triangle) <= 1e-12:
                    continue
                # A vertical source face on a shared cell edge belongs only once.
                signature = tuple(sorted(tuple(round(x, 8) for x in v[:3]) for v in triangle))
                if signature in seen:
                    continue
                seen.add(signature)
                faces.append({'source_face': face_id, 'material': face['material'], 'corners': triangle})
    if not faces:
        raise ValueError('Room intersection is empty')
    return {'faces': faces, 'source_face_count': len(mesh['faces']),
            'retained_source_face_count': len({f['source_face'] for f in faces}),
            'triangle_count': len(faces), 'polygon_cells': cells,
            'coordinate_basis': 'raw OBJ XYZ; identity transform', 'boundary_buffer_m': 0.0,
            'open_cut_edges': True, 'note': 'No watertightness or physical wall thickness claim'}
