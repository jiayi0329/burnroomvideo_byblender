"""Read-only, file-bound spatial evidence for one explicit historical Room8 job.

No DB, storage client, Blender, current-code guard check, or repair writes. A
relocated archive may be read by its canonical scene-relative data paths; its
frozen absolute guard keys remain unchanged and are never returned to clients.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import re

from backend.services import room_job_service as jobs
from backend.services.room_registration import inside, token
from render_engine.jobs.operation_logging import stage, traced
from render_engine.jobs.room_animation_job import digest

MAX_DOCUMENT_BYTES = 16 * 1024 * 1024
IDENTITY = [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]
GLB_MAPPING = 'glTF Y-up export: raw (x,y,z) -> (x,z,-y); room.blend retains raw XYZ'


def sha(value: object) -> str:
    if not isinstance(value, str) or not re.fullmatch('[a-f0-9]{64}', value):
        raise ValueError('Invalid fingerprint')
    return value


def number(value: object) -> float:
    if type(value) not in (int, float) or abs(value) > 1e6 or not math.isfinite(value):
        raise ValueError('Invalid coordinate')
    return value


def device(value: object) -> int:
    if isinstance(value, str) and re.fullmatch('[0-9]{1,9}', value):
        value = int(value)
    if type(value) is not int or not 0 <= value <= 999999999:
        raise ValueError('Invalid point identifier')
    return value


def members(value: object) -> set[int]:
    if not isinstance(value, list) or len(value) > 128:
        raise ValueError('Invalid point membership')
    result = {device(item) for item in value}
    if len(result) != len(value):
        raise ValueError('Duplicate membership')
    return result


def positions(value: object) -> dict[int, list[float]]:
    if not isinstance(value, list) or len(value) > 10000:
        raise ValueError('Invalid point source')
    result = {}
    for point in value:
        key = device(point['device'])
        if key in result:
            raise ValueError('Duplicate point')
        # Original scans use pose.translation; catalog-shaped test/export data
        # may carry flat XYZ. If both exist they must agree, never pick one.
        nested = point.get('pose', {}).get('translation')
        flat = any(axis in point for axis in ('x', 'y', 'z'))
        if nested is None and not flat:
            raise ValueError('Missing point coordinates')
        xyz = [number((nested if nested is not None else point)[axis]) for axis in ('x', 'y', 'z')]
        if nested is not None and flat and xyz != [number(point[axis]) for axis in ('x', 'y', 'z')]:
            raise ValueError('Ambiguous point coordinates')
        result[key] = xyz
    return result


def polygon(value: object) -> list[list[float]]:
    if not isinstance(value, list) or not 3 <= len(value) <= 129:
        raise ValueError('Invalid polygon')
    ring = []
    for pair in value:
        if not isinstance(pair, list) or len(pair) != 2:
            raise ValueError('Invalid polygon vertex')
        ring.append([number(item) for item in pair])
    if ring[0] == ring[-1]:
        ring.pop()
    if not 3 <= len(ring) <= 128 or len({tuple(pair) for pair in ring}) != len(ring):
        raise ValueError('Duplicate polygon vertices')
    edges = list(zip(ring, ring[1:] + ring[:1]))
    if abs(sum(a[0]*b[1] - b[0]*a[1] for a, b in edges)) < 1e-8:
        raise ValueError('Degenerate polygon')

    def orientation(a, b, c):
        return (b[0]-a[0])*(c[1]-a[1]) - (b[1]-a[1])*(c[0]-a[0])

    def on_segment(a, b, c):
        return (abs(orientation(a, b, c)) < 1e-9
                and min(a[0], b[0])-1e-9 <= c[0] <= max(a[0], b[0])+1e-9
                and min(a[1], b[1])-1e-9 <= c[1] <= max(a[1], b[1])+1e-9)

    for i, (a, b) in enumerate(edges):
        for j, (c, d) in enumerate(edges):
            if j <= i+1 or (i == 0 and j == len(edges)-1):
                continue
            crosses = (orientation(a, b, c)*orientation(a, b, d) < 0
                       and orientation(c, d, a)*orientation(c, d, b) < 0)
            if crosses or any((on_segment(a, b, c), on_segment(a, b, d),
                               on_segment(c, d, a), on_segment(c, d, b))):
                raise ValueError('Self-intersecting polygon')
    return ring


class Evidence:
    def __init__(self, scene: Path):
        self.scene = scene
        self.hashes: dict[Path, str] = {}

    def file(self, path: Path, expected: str | None = None) -> Path:
        resolved = inside(self.scene, path)
        if resolved != path:
            raise ValueError('Aliased evidence path')
        current = digest(resolved)
        if ((expected is not None and current != sha(expected))
                or (resolved in self.hashes and self.hashes[resolved] != current)):
            raise ValueError('Evidence fingerprint mismatch')
        self.hashes[resolved] = current
        return resolved

    def document(self, path: Path, expected: str | None = None):
        path = self.file(path, expected)
        with path.open('rb') as stream:
            content = stream.read(MAX_DOCUMENT_BYTES+1)
        if len(content) > MAX_DOCUMENT_BYTES or hashlib.sha256(content).hexdigest() != self.hashes[path]:
            raise ValueError('Document changed or too large')

        def unique(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError('Duplicate JSON key')
                result[key] = value
            return result

        def invalid_constant(_):
            raise ValueError('Nonfinite JSON value')

        def finite_float(value):
            parsed = float(value)
            if not math.isfinite(parsed):
                raise ValueError('Nonfinite JSON number')
            return parsed

        return json.loads(content, object_pairs_hook=unique, parse_constant=invalid_constant,
                          parse_float=finite_float)

    def recheck(self) -> None:
        for path, expected in self.hashes.items():
            if inside(self.scene, path) != path or digest(path) != expected:
                raise ValueError('Evidence changed during read')


def frozen_path(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError('Invalid frozen path')
    value = value.replace('\\', '/')
    if (not (value.startswith('/') or re.match('^[A-Za-z]:/', value)) or '//' in value
            or any(part in ('.', '..') for part in value.split('/'))):
        raise ValueError('Noncanonical frozen path')
    return value


@traced('room.spatial', 'read_context')
def get_context(scene_code: str, job_id: str) -> dict:
    try:
        return verified_context(scene_code, job_id)
    except jobs.JobError:
        raise
    except FileNotFoundError:
        raise jobs.JobError(409, 'spatial_evidence_missing') from None
    except (OSError, ValueError, KeyError, TypeError, IndexError, AttributeError, RecursionError):
        raise jobs.JobError(409, 'spatial_evidence_invalid') from None


def verified_context(scene_code: str, job_id: str) -> dict:
    job = jobs.job_directory(scene_code, job_id)
    scene = jobs.room_root(scene_code).parents[1]
    evidence = Evidence(scene)
    with stage('room.spatial', 'verify_snapshot'):
        spec = evidence.document(job/'config_snapshot.json')
        if type(spec.get('schema_version')) is not int or spec['schema_version'] != 1:
            raise ValueError('Unsupported snapshot schema')
        if jobs.snapshot(job, scene_code) != spec:
            raise ValueError('Snapshot changed')
        inputs = spec['inputs']
        original_asset = frozen_path(inputs['asset']).rstrip('/')
        version = token(original_asset.split('/')[-2])
        suffix = f'/rooms/Room8/{version}/asset'
        original_scene = original_asset[:-len(suffix)]
        if not original_scene.endswith('/'+scene_code) or original_asset != original_scene+suffix:
            raise ValueError('Wrong scene namespace')
        if frozen_path(inputs['points']) != original_scene+'/points.json':
            raise ValueError('Wrong points namespace')
        guards = {}
        for name, expected in inputs['guards'].items():
            name = frozen_path(name)
            if name in guards:
                raise ValueError('Ambiguous frozen guard')
            guards[name] = sha(expected)

        def guarded(original: str) -> str:
            return guards[original]

    with stage('room.spatial', 'verify_asset', asset_version=version):
        asset = scene/'rooms/Room8'/version/'asset'
        manifest = evidence.document(asset/'manifest.json', guarded(original_asset+'/manifest.json'))
        candidate_file = asset.parent/'candidate.json'
        candidate = evidence.document(candidate_file, guarded(original_asset.rsplit('/', 1)[0]+'/candidate.json'))
        if type(candidate.get('schema_version')) is not int or candidate['schema_version'] != 1:
            raise ValueError('Unsupported candidate schema')
        if evidence.hashes[candidate_file] != sha(manifest['candidate_sha256']):
            raise ValueError('Candidate binding mismatch')
        for document in (manifest, candidate):
            if (document['scene_code'], document['room_id']) != (scene_code, 'Room8'):
                raise ValueError('Spatial identity mismatch')
            if document['raw_to_asset_matrix'] != IDENTITY:
                raise ValueError('Unsupported asset transform')
            for row in document['raw_to_asset_matrix']:
                for item in row:
                    number(item)
        if manifest['glb_coordinate_mapping'] != GLB_MAPPING:
            raise ValueError('Unsupported GLB transform')
        validation = evidence.document(asset/'validation.json', sha(manifest['artifacts']['validation.json']))
        if (validation['status'] != 'passed' or not validation['checks']
                or any(value is not True for value in validation['checks'].values())):
            raise ValueError('Unvalidated base asset')
        for name in ('room.blend', 'room.glb'):
            evidence.file(asset/name, guarded(original_asset+'/'+name))
            if evidence.hashes[asset/name] != sha(manifest['artifacts'][name]):
                raise ValueError('Asset artifact mismatch')
        ring = polygon(manifest['clipping_parameters']['polygon_raw_xy'])
        if ring != polygon(candidate['polygon_raw_xy']):
            raise ValueError('Boundary mismatch')
        floor = number(manifest['engineering_policy']['floor_z'])
        if (number(candidate['floor_z']) != floor or candidate['physical_semantics_verified'] is not False
                or manifest['engineering_policy']['physical_semantics_verified'] is not False):
            raise ValueError('Floor policy mismatch')
        if candidate['source_fingerprints'] != manifest['source_fingerprints']:
            raise ValueError('Source fingerprint mismatch')
        provenance = {}
        for key in ('alignment_sha256', 'review_sha256'):
            provenance[key] = sha(manifest['provenance'][key])
            if candidate['provenance'][key] != provenance[key]:
                raise ValueError('Review binding mismatch')

    with stage('room.spatial', 'verify_membership', asset_version=version):
        interior, boundary = members(candidate['interior_devices']), members(candidate['boundary_devices'])
        if (not interior or interior & boundary or interior != members(manifest['interior_devices'])
                or boundary != members(manifest['boundary_devices'])):
            raise ValueError('Membership differs')
        point_file = scene/'points.json'
        raw_points = positions(evidence.document(point_file, guarded(original_scene+'/points.json')))
        if evidence.hashes[point_file] != sha(manifest['source_fingerprints']['points.json']):
            raise ValueError('Point source differs')
        for document in (manifest, candidate):
            anchors = positions(document['points'])
            if set(anchors) != interior | boundary or any(raw_points[key] != anchors[key] for key in anchors):
                raise ValueError('Point anchors differ')
        timeline = inputs['timeline']
        ignition = device(timeline['start_point'])
        if (ignition != device(candidate['ignition_device']) or ignition not in interior
                or members(timeline['allowed_devices']) != interior):
            raise ValueError('Ignition binding mismatch')
        events = timeline['spread_events']
        if not isinstance(events, list) or len(events) != len(interior):
            raise ValueError('Timeline incomplete')
        event_points = set()
        for event in events:
            point, when = device(event['point']), number(event['time'])
            if point in event_points or point not in interior or when < 0 or ((point == ignition) != (when == 0)):
                raise ValueError('Invalid propagation event')
            event_points.add(point)
    with stage('room.spatial', 'recheck_fingerprints', asset_version=version):
        evidence.recheck()
    return {'schema_version': 1, 'scene_code': scene_code, 'room_id': 'Room8',
            'asset_version': version, 'file_job_id': job_id, 'layout_version_id': None,
            'layout_binding': 'file_fingerprints_only', 'layout_fingerprints': provenance,
            'verified': True, 'verification_scope': 'file_consistency_only',
            'source': {'snapshot_sha256': evidence.hashes[job/'config_snapshot.json'],
                       'manifest_sha256': evidence.hashes[asset/'manifest.json'],
                       'candidate_sha256': evidence.hashes[candidate_file],
                       'glb_sha256': evidence.hashes[asset/'room.glb'],
                       'points_sha256': evidence.hashes[point_file]},
            'boundary': {'polygon_raw_xy': ring, 'closed': True, 'floor_z': floor,
                         'policy': 'engineering_clip_boundary', 'physical_semantics_verified': False},
            'ignition': {'device': ignition, 'position_raw_xyz': raw_points[ignition],
                         'source': 'config_snapshot.inputs.timeline.start_point'},
            'members': {'interior': sorted(interior), 'boundary': sorted(boundary)},
            'coordinates': {'raw_to_glb': '(x,z,-y)', 'model_already_converted': True}}
