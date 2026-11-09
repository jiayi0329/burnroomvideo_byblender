"""Read-only OBJ/MTL, source coordinates and byte fingerprints.

PRD engineering baseline / architecture geometry boundary: stdlib only.
No diagnostics, backend, database, bpy, rendering or import-time file access.
Legacy names remain re-exported by inspect_room_asset.
"""
from __future__ import annotations

from collections import Counter
import hashlib
import math
from pathlib import Path
import shlex
from typing import Any

XYZ = tuple[float, float, float]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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
