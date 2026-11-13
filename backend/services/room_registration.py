"""Read-only publication plan for verified Room8 assets and completed videos.

Never imports bpy or runs render/encoding processes. Historical evidence stays
unchanged; remote registration is explicit and handled by the CLI.
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import re

from render_engine.jobs.operation_logging import traced
from render_engine.jobs.room_animation_job import APPROVED_STYLE_FINGERPRINT, digest, fingerprint


@dataclass(frozen=True)
class PublicationFile:
    path: Path
    relative: str
    kind: str
    role: str | None
    bucket: str
    key: str
    sha256: str
    size: int
    content_type: str

    def summary(self) -> dict:
        return {'relative': self.relative, 'kind': self.kind, 'role': self.role,
                'bucket': self.bucket, 'object_key': self.key, 'sha256': self.sha256,
                'size_bytes': self.size, 'content_type': self.content_type}


@dataclass(frozen=True)
class RegistrationPlan:
    scene: Path
    room_id: str
    asset_version: str
    file_job_id: str
    layout_version_id: int
    provenance: dict
    interior_devices: tuple[int, ...]
    files: tuple[PublicationFile, ...]
    guards: dict[Path, str]
    video: dict
    signature: str

    def summary(self) -> dict:
        return {'scene_code': self.scene.name, 'room_id': self.room_id,
                'asset_version': self.asset_version, 'file_job_id': self.file_job_id,
                'layout_version_id': self.layout_version_id,
                'human_acceptance': 'not_recorded', 'runtime_state': 'awaiting_visual_review',
                'files': [file.summary() for file in self.files]}


def token(value: str) -> str:
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,95}', value):
        raise ValueError('Invalid identifier')
    return value


def inside(root: Path, path: Path) -> Path:
    resolved = path.resolve(strict=True)
    if not resolved.is_relative_to(root) or not resolved.is_file():
        raise ValueError('Publication input escapes scene or is not a file')
    return resolved


@traced('catalog.register', 'verify_local_inputs')
def build_plan(data_root: Path, scene_code: str, asset: Path, job: Path,
               layout_version_id: int) -> RegistrationPlan:
    """Preview has no DB/MinIO calls; paths always come from explicit versions."""
    if isinstance(layout_version_id, bool) or layout_version_id < 1:
        raise ValueError('Explicit positive layout version required')
    scene = (data_root.resolve() / token(scene_code)).resolve(strict=True)
    if not scene.is_relative_to(data_root.resolve()):
        raise ValueError('Scene escapes data root')
    asset, job = asset.resolve(strict=True), job.resolve(strict=True)
    version, job_id = token(asset.parent.name), token(job.name)
    room = 'Room8'  # Only this room has an accepted rendering baseline.
    if asset != scene/'rooms'/room/version/'asset' or job != scene/'rooms'/room/'render_jobs'/job_id:
        raise ValueError('Explicit canonical Room8 asset/job directories required')
    guards: dict[Path, str] = {}

    def protect(path: Path, expected: str | None = None) -> Path:
        path = inside(scene, path)
        actual = digest(path)
        if expected is not None and actual != expected:
            raise ValueError('Publication fingerprint mismatch')
        if path in guards and guards[path] != actual:
            raise ValueError('Input changed while reading')
        guards[path] = actual
        return path

    def document(path: Path) -> dict:
        path = protect(path)
        content = path.read_bytes()
        if hashlib.sha256(content).hexdigest() != guards[path]:
            raise ValueError('Document changed while reading')
        result = json.loads(content)
        if not isinstance(result, dict):
            raise ValueError('Expected JSON document')
        return result

    manifest = document(asset/'manifest.json')
    validation = document(asset/'validation.json')
    if (manifest['scene_code'], manifest['room_id']) != (scene_code, room):
        raise ValueError('Asset identity differs')
    if (validation.get('status') != 'passed' or not validation.get('checks')
            or any(value is not True for value in validation['checks'].values())):
        raise ValueError('Base asset technical validation required')
    for name, sha in manifest['artifacts'].items():
        if Path(name).name != name or '\\' in name:
            raise ValueError('Invalid artifact name')
        protect(asset/name, sha)
    protect(asset.parent/'candidate.json', manifest['candidate_sha256'])
    for name in ('mesh.obj', 'points.json', 'timeline.json'):
        protect(scene/name, manifest['source_fingerprints'][name])
    interior = tuple(sorted(manifest['interior_devices']))
    if (len(interior) != 13 or len(set(interior)) != 13 or 22 not in interior
            or set(interior) & {32, 42} or manifest['boundary_devices'] != [32]):
        raise ValueError('Reviewed Room8 memberships required')
    provenance = {key: manifest['provenance'][key] for key in ('alignment_sha256', 'review_sha256')}
    if any(not re.fullmatch(r'[0-9a-f]{64}', value) for value in provenance.values()):
        raise ValueError('Bound alignment/review fingerprints required')

    spec = document(job/'config_snapshot.json')
    signature = spec['signature']
    if fingerprint({k: v for k, v in spec.items() if k != 'signature'}) != signature:
        raise ValueError('Historical snapshot signature differs')
    animation = spec['animation']
    if (animation['stage'], animation['preset'], animation['camera_mode']) != ('final', 'final', 'overview'):
        raise ValueError('Only reviewed final overview publication is supported')
    if fingerprint(spec['inputs']['style']) != APPROVED_STYLE_FINGERPRINT:
        raise ValueError('Frozen R3 style required')
    expected_asset = f'/rooms/{room}/{version}/asset'
    if not str(spec['inputs']['asset']).replace('\\', '/').endswith(expected_asset):
        raise ValueError('Video references a different base asset')
    for path in (asset/'manifest.json', asset/'room.blend', asset/'room.glb', asset.parent/'candidate.json'):
        expected = protect(path)
        suffix = '/'+expected.relative_to(scene).as_posix()
        hashes = [sha for key, sha in spec['inputs']['guards'].items()
                  if key.replace('\\', '/').endswith(suffix)]
        if hashes != [guards[expected]]:
            raise ValueError('Historical video must bind the exact base asset')

    render = document(job/'render_manifest.json')
    receipt = document(job/'video_receipt.json')
    state = document(job/'status.json')
    if (state.get('state') != 'awaiting_visual_review' or render.get('technical_complete') is not True
            or render.get('worker_complete') is not True or render.get('guarded_files_unchanged') is not True
            or render.get('signature') != signature or render.get('camera_mode') != 'overview'
            or receipt.get('full_decode_passed') is not True):
        raise ValueError('Completed, technically verified final video required')
    events = render['timeline']['spread_events']
    if (sorted(event['point'] for event in events) != list(interior)
            or render['timeline'] != spec['inputs']['timeline']
            or render['timeline']['start_point'] != 22):
        raise ValueError('Video propagation differs from reviewed membership')
    expected = {'duration_seconds': animation['duration_seconds'], 'frames': animation['frame_count'],
                'resolution': animation['resolution'], 'file': 'fire_final.mp4'}
    if (expected != {'duration_seconds': 24, 'frames': 576, 'resolution': [1280, 720], 'file': 'fire_final.mp4'}
            or any(receipt.get(key) != value for key, value in expected.items())
            or Fraction(receipt['fps']) != 24 or animation['fps'] != 24
            or receipt.get('codec') != 'h264' or receipt.get('pixel_format') != 'yuv420p'
            or len(render['frames']) != 576):
        raise ValueError('Final video properties differ from the frozen baseline')
    video = {key: receipt[key] for key in (*expected, 'fps', 'codec', 'pixel_format', 'sha256', 'bytes', 'full_decode_passed')}
    if any(render['video'].get(key) != value for key, value in video.items()):
        raise ValueError('Video receipt and render manifest disagree')
    video_path = protect(job/'fire_final.mp4', receipt['sha256'])
    if video_path.stat().st_size != receipt['bytes']:
        raise ValueError('Video byte count differs')

    files = []
    selected = [('room.blend', 'room_blend', 'application/x-blender'),
                ('room.glb', 'room_glb', 'model/gltf-binary'),
                *[(name+'.png', 'room_preview', 'image/png') for name in ('top', 'oblique', 'interior')]]
    for name, kind, media in selected:
        path = protect(asset/name, manifest['artifacts'][name])
        files.append(PublicationFile(path, path.relative_to(scene).as_posix(), kind,
            'input' if name == 'room.blend' else None,
            'burnroom-room-assets', f'scenes/{scene_code}/rooms/{room}/assets/{version}/{name}',
            guards[path], path.stat().st_size, media))
    files.append(PublicationFile(video_path, video_path.relative_to(scene).as_posix(), 'room_video', 'output',
        'burnroom-room-outputs', f'scenes/{scene_code}/rooms/{room}/render_jobs/{job_id}/fire_final.mp4',
        guards[video_path], video_path.stat().st_size, 'video/mp4'))
    return RegistrationPlan(scene, room, version, job_id, layout_version_id, provenance,
                            interior, tuple(files), guards, video, signature)


def verify_unchanged(plan: RegistrationPlan) -> None:
    for path, expected in plan.guards.items():
        if inside(plan.scene, path) != path or digest(path) != expected:
            raise ValueError('Publication input changed; create a new plan')
