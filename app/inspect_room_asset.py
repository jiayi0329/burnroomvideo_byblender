"""PRD room preparation: read-only OBJ/material/height audit before clipping.

No bpy, database, network, mesh rewrite or rendering. Outputs diagnostics only.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import re
import shlex
from typing import Any
import uuid

from app.analyze_floorplan import contains, edges, segment_distance, sha256
from app.import_rooms import build_plan

XYZ = tuple[float, float, float]


def number(value: str) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise ValueError('Nonfinite OBJ coordinate')
    return result


def index(value: str, count: int) -> int:
    i = int(value)
    result = i - 1 if i > 0 else count + i
    if i == 0 or not 0 <= result < count:
        raise ValueError('Invalid OBJ index')
    return result


def confined(root: Path, name: str) -> Path:
    path = (root / name).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError('External material/texture path requires separate review')
    return path


def inverse_xy(polygon: list, matrix: list[float]) -> list[tuple[float, float]]:
    a, b, c, d, tx, ty = matrix
    det = a * d - b * c
    if abs(det) < 1e-12:
        raise ValueError('Singular XY transform')
    return [((d * (x - tx) - b * (y - ty)) / det,
             (-c * (x - tx) + a * (y - ty)) / det) for x, y in polygon]


def read_obj(path: Path) -> dict[str, Any]:
    vertices: list[XYZ] = []
    uvs: list[tuple[float, float]] = []
    faces: list[dict] = []
    libraries: list[str] = []
    normal_count = 0
    material: str | None = None
    with path.open(encoding='utf-8-sig') as stream:
        for line in stream:
            parts = line.split()
            if not parts or parts[0].startswith('#'):
                continue
            kind = parts[0]
            if kind == 'v':
                vertices.append(tuple(number(v) for v in parts[1:4]))
                if len(vertices[-1]) != 3:
                    raise ValueError('Invalid OBJ vertex')
            elif kind == 'vt':
                uvs.append(tuple(number(v) for v in parts[1:3]))
                if len(uvs[-1]) != 2:
                    raise ValueError('Invalid OBJ UV')
            elif kind == 'vn':
                normal_count += 1
            elif kind == 'mtllib':
                libraries.extend(shlex.split(line.partition(' ')[2]))
            elif kind == 'usemtl':
                material = line.strip().partition(' ')[2]
            elif kind == 'f':
                corners = []
                for value in parts[1:]:
                    ref = value.split('/')
                    vertex = index(ref[0], len(vertices))
                    uv = index(ref[1], len(uvs)) if len(ref) > 1 and ref[1] else None
                    if len(ref) > 2 and ref[2]:
                        index(ref[2], normal_count)
                    corners.append((vertex, uv))
                if len(corners) < 3:
                    raise ValueError('Invalid OBJ face')
                faces.append({'corners': corners, 'material': material})
    if not vertices or not faces:
        raise ValueError('OBJ geometry is empty')
    return {'vertices': vertices, 'uvs': uvs, 'faces': faces, 'libraries': libraries,
            'normal_count': normal_count}


def materials(scene_dir: Path, mesh: dict) -> dict:
    definitions: dict[str, dict] = {}
    textures: dict[str, dict] = {}
    issues: list[str] = []
    libraries = []
    for name in mesh['libraries']:
        path = confined(scene_dir, name)
        if not path.is_file():
            issues.append('missing_material_library:' + name)
            continue
        libraries.append({'path': name, 'sha256': sha256(path)})
        current = None
        for line in path.read_text(encoding='utf-8-sig').splitlines():
            fields = shlex.split(line, comments=True)
            if not fields:
                continue
            if fields[0] == 'newmtl':
                current = ' '.join(fields[1:])
                if current in definitions:
                    issues.append('duplicate_material_definition:' + current)
                definitions[current] = {'texture_maps': []}
            elif current and fields[0].lower().startswith(('map_', 'bump', 'disp', 'norm')):
                if len(fields) != 2 or fields[1].startswith('-'):
                    issues.append('texture_options_require_review:' + current)
                    continue
                texture = confined(scene_dir, str(path.parent.relative_to(scene_dir.resolve()) / fields[1]))
                relative = texture.relative_to(scene_dir.resolve()).as_posix()
                definitions[current]['texture_maps'].append({'socket': fields[0], 'path': relative})
                textures[relative] = {'exists': texture.is_file(), 'sha256': sha256(texture) if texture.is_file() else None}
                if not texture.is_file():
                    issues.append('missing_texture:' + relative)
    used = Counter(face['material'] for face in mesh['faces'])
    for name in used:
        if name is None or name not in definitions:
            issues.append('undefined_face_material:' + str(name))
    corners = [c for face in mesh['faces'] for c in face['corners']]
    uv_corners = sum(uv is not None for _, uv in corners)
    if uv_corners != len(corners):
        issues.append('missing_face_corner_uv')
    return {'libraries': libraries, 'definitions': definitions, 'textures': textures,
            'faces_per_material': {str(k): v for k, v in used.items()}, 'corner_count': len(corners),
            'uv_corner_count': uv_corners, 'uv_complete': uv_corners == len(corners),
            'ready_for_preservation': not issues, 'issues': issues}


def vertical_hit(x: float, y: float, triangle: list[XYZ]) -> float | None:
    a, b, c = triangle
    den = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
    if abs(den) < 1e-12:
        return None
    u = ((b[1] - c[1]) * (x - c[0]) + (c[0] - b[0]) * (y - c[1])) / den
    v = ((c[1] - a[1]) * (x - c[0]) + (a[0] - c[0]) * (y - c[1])) / den
    w = 1 - u - v
    if min(u, v, w) < -1e-8:
        return None
    return u * a[2] + v * b[2] + w * c[2]


def height_profile(mesh: dict, polygon: list, spacing: float = 0.25, inset: float = 0.10) -> dict:
    if not 0.1 <= spacing <= 1.0:
        raise ValueError('Sampling spacing must be 0.1..1.0m')
    triangles = []
    unsupported = 0
    for face in mesh['faces']:
        if len(face['corners']) != 3:
            unsupported += 1
            continue
        tri = [mesh['vertices'][v] for v, _ in face['corners']]
        triangles.append((tri, min(p[0] for p in tri), max(p[0] for p in tri),
                          min(p[1] for p in tri), max(p[1] for p in tri)))
    low = [min(p[k] for p in polygon) for k in (0, 1)]
    high = [max(p[k] for p in polygon) for k in (0, 1)]
    nx, ny = [math.ceil((high[k] - low[k]) / spacing) for k in (0, 1)]
    if nx * ny > 100000:
        raise ValueError('Room extent too large for this sampling budget')
    samples = []
    bottom, top = Counter(), Counter()
    for j in range(ny):
        y = low[1] + (j + 0.5) * spacing
        for i in range(nx):
            x = low[0] + (i + 0.5) * spacing
            if not contains((x, y), polygon) or min(segment_distance((x, y), a, b) for a, b in edges(polygon)) < inset:
                continue
            hits = sorted(z for tri, x0, x1, y0, y1 in triangles
                          if x0 - 1e-8 <= x <= x1 + 1e-8 and y0 - 1e-8 <= y <= y1 + 1e-8
                          if (z := vertical_hit(x, y, tri)) is not None)
            unique = []
            for z in hits:
                if not unique or abs(z - unique[-1]) > 1e-5:
                    unique.append(z)
            # Extrema are geometric envelopes, not certified room surfaces.
            samples.append({'xy': [x, y], 'bottom': unique[0] if unique else None,
                            'top': unique[-1] if len(unique) > 1 else None, 'surface_count': len(unique)})
            if unique:
                bottom[round(unique[0] / 0.05) * 0.05] += 1
            if len(unique) > 1:
                top[round(unique[-1] / 0.05) * 0.05] += 1
    def summarize(counts: Counter) -> list[dict]:
        return [{'z_m': round(z, 3), 'sample_count': count, 'fraction_of_room_samples': round(count / len(samples), 4)}
                for z, count in counts.most_common()] if samples else []
    return {'method': 'vertical triangle intersection, geometric lower/upper envelope only',
            'spacing_m': spacing, 'boundary_inset_m': inset, 'height_bin_m': 0.05,
            'sample_count': len(samples), 'without_surface': sum(p['surface_count'] == 0 for p in samples),
            'with_upper_and_lower': sum(p['surface_count'] >= 2 for p in samples),
            'unsupported_nontriangle_faces': unsupported, 'bottom_clusters': summarize(bottom),
            'top_clusters': summarize(top), 'samples': samples,
            'floor_z_confirmed': None, 'ceiling_z_confirmed': None,
            'warning': 'Furniture, slab thickness and sloped surfaces can affect envelopes; review sections before choosing cut heights.'}


def inspect(scene_dir: Path, probe_dir: Path, alignment_dir: Path, review_file: Path, room_id: str, spacing: float = 0.25) -> dict:
    plan = build_plan(scene_dir, probe_dir, alignment_dir, review_file)
    if not plan['review'].get('xy_verified'):
        raise ValueError('Reviewed XY alignment required')
    room = next((r for r in plan['report']['rooms'] if r['room_id'] == room_id), None)
    if room is None or not room['valid_candidate']:
        raise ValueError('Valid room required')
    mesh_path = scene_dir / 'mesh.obj'
    mesh = read_obj(mesh_path)
    polygon_raw = inverse_xy(room['polygon'], plan['report']['selected_transform']['matrix'])
    lo = [min(v[k] for v in mesh['vertices']) for k in range(3)]
    hi = [max(v[k] for v in mesh['vertices']) for k in range(3)]
    center_xy = [(min(v[k] for v in polygon_raw) + max(v[k] for v in polygon_raw)) / 2 for k in (0, 1)]
    return {'scene_code': scene_dir.name, 'room_id': room_id, 'status': 'review_required',
            'ready_for_cut': False, 'source_mesh_sha256': sha256(mesh_path),
            'source_points_sha256': sha256(scene_dir / 'points.json'),
            'source_timeline_sha256': sha256(scene_dir / 'timeline.json'),
            'source_report_sha256': sha256(alignment_dir / 'alignment_report.json'),
            'source_review_sha256': sha256(review_file), 'room': room,
            'room_polygon_raw_xy': polygon_raw,
            'coordinates': {'units': 'm', 'raw_to_floor_xy': plan['report']['selected_transform']['matrix'],
                'blender_import_verified': False, 'raw_bounds': {'min': lo, 'max': hi},
                'existing_F8_offset_if_import_identity': [-(lo[k] + hi[k]) / 2 for k in range(3)],
                'proposed_room_origin_raw': [*center_xy, 0.0],
                'origin_note': 'Coordinate reference only; a concave room bounding-box center is not guaranteed to be an interior camera target.',
                'raw_to_room_local_translation': [-center_xy[0], -center_xy[1], 0.0],
                'z_policy': 'Keep source Z unchanged until floor/ceiling review; preserve inverse transform.'},
            'geometry': {'vertices': len(mesh['vertices']), 'faces': len(mesh['faces']),
                         'uv_entries': len(mesh['uvs']), 'normal_entries': mesh['normal_count']},
            'materials': materials(scene_dir, mesh), 'height_profile': height_profile(mesh, polygon_raw, spacing),
            'wall_policy': {'permanent_geometry_removed': False,
                'strategy': 'Preserve room-facing walls, doorway geometry and ceiling in base asset; section view is a separate derivative.',
                'boundary_buffer_m': None,
                'buffer_status': 'Measure wall thickness/adjacent-room intrusion before choosing a buffer; do not use F8 2.5m margin.',
                'clipping': 'Intersect faces with the reviewed polygon; interpolate per-corner UV at new vertices; preserve material assignment.',
                'height_status': 'No vertical trim is authorized by this diagnostic.'},
            'next_gate': ['remote Blender world-coordinate/UV/material inspection',
                          'review floor/ceiling sections and wall thickness',
                          'then clip/save a new asset, reopen and verify before section/effects'],
            'database_required': False, 'render_started': False}


def main() -> int:
    parser = argparse.ArgumentParser(description='Inspect a reviewed room before cutting; never render')
    parser.add_argument('--scene', required=True)
    parser.add_argument('--room', required=True)
    parser.add_argument('--data-root', type=Path, default=Path('/app/data'))
    parser.add_argument('--probe-dir', type=Path, required=True)
    parser.add_argument('--alignment-dir', type=Path, required=True)
    parser.add_argument('--review-file', type=Path, required=True)
    parser.add_argument('--spacing', type=float, default=0.25)
    args = parser.parse_args()
    if not all(re.fullmatch(r'[A-Za-z0-9_-]+', x) for x in (args.scene, args.room)):
        parser.error('Invalid scene/room ID')
    try:
        scene_dir = args.data_root / args.scene
        report = inspect(scene_dir, args.probe_dir, args.alignment_dir, args.review_file, args.room, args.spacing)
        output = scene_dir / 'diagnostics/room_inspection' / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '_' + uuid.uuid4().hex[:8])
        output.mkdir(parents=True, exist_ok=False)
        path = output / 'inspection.json'
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps({'status': report['status'], 'ready_for_cut': False, 'report': str(path),
            'uv_complete': report['materials']['uv_complete'],
            'materials_ready': report['materials']['ready_for_preservation'],
            'height_samples': report['height_profile']['sample_count'],
            'bottom_clusters': report['height_profile']['bottom_clusters'][:5],
            'top_clusters': report['height_profile']['top_clusters'][:5]}, ensure_ascii=False, indent=2), flush=True)
        return 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f'[room-inspection] failed: {type(exc).__name__}: {exc}', flush=True)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
