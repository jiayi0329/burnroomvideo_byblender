"""Shared read-only floorplan parsing, geometry and alignment analysis.

Stdlib only; no CLI, report writes, network, database, tools or bpy imports.
Functions are extracted without changing geometry or membership decisions.
"""
from __future__ import annotations

from collections import Counter
import hashlib
import json
import math
from pathlib import Path
from typing import Any

Point = tuple[float, float]
MIN_AREA = 0.05
MIN_WIDTH = 0.05
BOUNDARY_TOLERANCE = 0.10


def finite(value: Any) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("Coordinates must be finite")
    return number


def area(polygon: list[Point]) -> float:
    return abs(sum(a[0] * b[1] - b[0] * a[1] for a, b in edges(polygon))) / 2


def edges(polygon: list[Point]) -> list[tuple[Point, Point]]:
    return list(zip(polygon, polygon[1:] + polygon[:1]))


def segment_distance(point: Point, a: Point, b: Point) -> float:
    dx, dy = b[0] - a[0], b[1] - a[1]
    denominator = dx * dx + dy * dy
    t = max(0.0, min(1.0, ((point[0] - a[0]) * dx + (point[1] - a[1]) * dy) / denominator)) if denominator else 0.0
    return math.hypot(point[0] - a[0] - t * dx, point[1] - a[1] - t * dy)


def cross(a: Point, b: Point, c: Point) -> float:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def segments_intersect(a: Point, b: Point, c: Point, d: Point) -> bool:
    signs = (cross(a, b, c), cross(a, b, d), cross(c, d, a), cross(c, d, b))
    if signs[0] * signs[1] < 0 and signs[2] * signs[3] < 0:
        return True
    return any(
        abs(sign) < 1e-9 and segment_distance(point, start, end) < 1e-9
        for sign, point, start, end in (
            (signs[0], c, a, b), (signs[1], d, a, b), (signs[2], a, c, d), (signs[3], b, c, d)
        )
    )


def self_intersects(polygon: list[Point]) -> bool:
    segments = edges(polygon)
    for i, (a, b) in enumerate(segments):
        for j in range(i + 1, len(segments)):
            if j == i + 1 or (i == 0 and j == len(segments) - 1):
                continue
            if segments_intersect(a, b, *segments[j]):
                return True
    return False


def contains(point: Point, polygon: list[Point]) -> bool:
    """射线法；边界距离由独立逻辑处理，不强行归属门口点。"""
    x, y = point
    inside = False
    for a, b in edges(polygon):
        if (a[1] > y) != (b[1] > y):
            if x < (b[0] - a[0]) * (y - a[1]) / (b[1] - a[1]) + a[0]:
                inside = not inside
    return inside


def parse_rooms(floor: dict) -> list[dict]:
    raw_points = floor.get("points", {})
    if not isinstance(raw_points, dict):
        raise ValueError("Expected floorplan.json points dictionary")
    rooms: list[dict] = []
    seen: set[str] = set()
    for raw in floor.get("rooms", []):
        room_id = str(raw.get("roomId", ""))
        problems: list[str] = []
        warnings: list[str] = []
        if not room_id or room_id in seen:
            raise ValueError("Missing or duplicate room ID")
        seen.add(room_id)
        polygon: list[Point] = []
        for key in raw.get("wallPointIDs", []):
            if key not in raw_points:
                problems.append("missing_boundary_point")
                continue
            p = raw_points[key]
            xy = (finite(p["x"]), finite(p["y"]))
            if not polygon or xy != polygon[-1]:
                polygon.append(xy)
        if len(polygon) > 1 and polygon[0] == polygon[-1]:
            polygon.pop()
        computed_area = area(polygon) if len(polygon) >= 3 else 0.0
        if len(set(polygon)) < 3:
            problems.append("too_few_vertices")
        if computed_area < MIN_AREA:
            problems.append("tiny_area")
        if polygon and min(
            max(p[k] for p in polygon) - min(p[k] for p in polygon) for k in (0, 1)
        ) < MIN_WIDTH:
            problems.append("narrow_bounds")
        if len(polygon) >= 3 and self_intersects(polygon):
            problems.append("self_intersection")
        declared_area = raw.get("area")
        if declared_area is not None and abs(finite(declared_area) - computed_area) > max(0.1, computed_area * 0.1):
            warnings.append("declared_area_mismatch")
        if raw.get("childrenRooms"):
            problems.append("child_room_holes_require_review")
        rooms.append({
            "room_id": room_id, "label": raw.get("tagName") or raw.get("name") or room_id,
            "polygon": polygon, "area_m2": computed_area,
            "valid_candidate": not problems, "problems": problems, "warnings": warnings,
        })
    return rooms


def classify(point: Point, rooms: list[dict], tolerance: float = BOUNDARY_TOLERANCE) -> dict:
    inside: list[str] = []
    nearby: list[str] = []
    distances: dict[str, float] = {}
    invalid_hits: list[str] = []
    for room in rooms:
        polygon = room["polygon"]
        if not polygon:
            continue
        distance = min(segment_distance(point, a, b) for a, b in edges(polygon))
        hit = contains(point, polygon) if len(polygon) >= 3 else False
        if not room["valid_candidate"]:
            if hit or distance <= tolerance:
                invalid_hits.append(room["room_id"])
            continue
        distances[room["room_id"]] = distance
        if hit:
            inside.append(room["room_id"])
        if distance <= tolerance:
            nearby.append(room["room_id"])
    if len(inside) > 1:
        status = "overlap"
    elif nearby:
        status = "boundary"
    elif len(inside) == 1:
        status = "interior"
    else:
        status = "outside"
    return {
        "status": status, "room_id": inside[0] if status == "interior" else None,
        "inside_rooms": inside, "near_boundary_rooms": nearby, "invalid_room_hits": invalid_hits,
        "nearest_boundary_m": min(distances.values()) if distances else None,
    }


def room_overlap_candidates(rooms: list[dict]) -> list[list[str]]:
    """查找存在内部交叠迹象的房间；共享墙边不作为重叠。"""
    found: list[list[str]] = []
    valid = [room for room in rooms if room["valid_candidate"]]
    for i, left in enumerate(valid):
        for right in valid[i + 1:]:
            p, q = left["polygon"], right["polygon"]
            crossing = any(
                cross(a, b, c) * cross(a, b, d) < -1e-12 and cross(c, d, a) * cross(c, d, b) < -1e-12
                for a, b in edges(p) for c, d in edges(q)
            )
            internal = False
            for source, target in ((p, q), (q, p)):
                samples = source + [((a[0] + b[0]) / 2, (a[1] + b[1]) / 2) for a, b in edges(source)]
                internal |= any(
                    contains(point, target) and min(segment_distance(point, a, b) for a, b in edges(target)) > 1e-8
                    for point in samples
                )
            if crossing or internal or set(p) == set(q):
                found.append([left["room_id"], right["room_id"]])
    return found


def apply_transform(point: Point, matrix: list[float]) -> Point:
    a, b, c, d, tx, ty = matrix
    return a * point[0] + b * point[1] + tx, c * point[0] + d * point[1] + ty


def axis_candidates() -> list[dict]:
    return [
        {"id": name, "matrix": matrix}
        for name, matrix in (
            ("xy", [1, 0, 0, 1, 0, 0]), ("x_neg_y", [1, 0, 0, -1, 0, 0]),
            ("neg_x_y", [-1, 0, 0, 1, 0, 0]), ("neg_x_neg_y", [-1, 0, 0, -1, 0, 0]),
            ("yx", [0, 1, 1, 0, 0, 0]), ("y_neg_x", [0, 1, -1, 0, 0, 0]),
            ("neg_y_x", [0, -1, 1, 0, 0, 0]), ("neg_y_neg_x", [0, -1, -1, 0, 0, 0]),
        )
    ]


def read_mesh(path: Path) -> tuple[list[Point], dict]:
    vertices: list[Point] = []
    mins, maxs = [math.inf] * 3, [-math.inf] * 3
    faces = 0
    with path.open(encoding="utf-8", errors="replace") as stream:
        for line in stream:
            parts = line.split()
            if not parts:
                continue
            if parts[0] == "v" and len(parts) >= 4:
                xyz = [finite(v) for v in parts[1:4]]
                vertices.append((xyz[0], xyz[1]))
                for axis in range(3):
                    mins[axis] = min(mins[axis], xyz[axis])
                    maxs[axis] = max(maxs[axis], xyz[axis])
            elif parts[0] == "f":
                faces += 1
    if not vertices:
        raise ValueError("OBJ has no vertices")
    return vertices, {"vertex_count": len(vertices), "face_count": faces, "bounds_xyz": {"min": mins, "max": maxs}}


def rank_candidates(candidates: list[dict], rooms: list[dict], mesh: list[Point], cameras: list[dict]) -> list[dict]:
    """仅用几何接近程度排序；扫描地面/家具也会命中，不能视为配准通过。"""
    sampled_mesh = mesh[::max(1, math.ceil(len(mesh) / 3000))]
    wall_samples: list[Point] = []
    for room in rooms:
        if room["valid_candidate"]:
            for a, b in edges(room["polygon"]):
                wall_samples.extend((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t) for t in (0.0, 0.5))
    if not wall_samples:
        raise ValueError("No valid room candidates")
    for candidate in candidates:
        transformed = [apply_transform(p, candidate["matrix"]) for p in sampled_mesh]
        distances = sorted(
            math.sqrt(min((p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2 for q in transformed))
            for p in wall_samples
        )
        classifications = [classify(apply_transform(c["xy"], candidate["matrix"]), rooms) for c in cameras]
        candidate.update(
            wall_to_sampled_mesh_mean_m=sum(distances) / len(distances),
            wall_to_sampled_mesh_p90_m=distances[min(len(distances) - 1, int(len(distances) * 0.9))],
            camera_status_counts=dict(Counter(row["status"] for row in classifications)),
        )
    return sorted(candidates, key=lambda item: item["wall_to_sampled_mesh_mean_m"])


def resolve_source(probe_dir: Path, scene_code: str) -> tuple[Path, dict]:
    report_path = probe_dir / "report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if report.get("scene_code") != scene_code or report.get("status") != "inspected":
        raise ValueError("Need the successful server probe directory for this scene (status=inspected)")
    documents = [
        document for asset in report.get("api", {}).get("assets", [])
        for document in asset.get("json_documents", [])
        if document.get("name") == "floorplan.json" and document.get("status") == "inspected"
    ]
    if len(documents) != 1:
        raise ValueError("Expected exactly one inspected floorplan.json; review probe report")
    source = (probe_dir / documents[0]["saved_as"]).resolve()
    if not source.is_relative_to(probe_dir.resolve()):
        raise ValueError("Invalid source path in report")
    return source, report


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def analyze(scene_dir: Path, probe_dir: Path, floor_index: int = 0, transform_id: str | None = None) -> tuple[dict, dict]:
    source, probe_report = resolve_source(probe_dir, scene_dir.name)
    document = json.loads(source.read_text(encoding="utf-8"))
    if document.get("unit") != "m":
        raise ValueError("Expected declared unit m; confirm units before analysis")
    floors = document.get("floors", [])
    if not 0 <= floor_index < len(floors):
        raise ValueError("Invalid floor index")
    if len(floors) != 1:
        raise ValueError("Multi-floor camera membership requires explicit height/membership validation")
    floor = floors[floor_index]
    rooms = parse_rooms(floor)
    raw_cameras = json.loads((scene_dir / "points.json").read_text(encoding="utf-8"))
    cameras = []
    seen_devices: set[int] = set()
    for camera in raw_cameras:
        device = int(camera["device"])
        if device in seen_devices:
            raise ValueError("Duplicate device ID")
        seen_devices.add(device)
        position = camera["pose"]["translation"]
        cameras.append({"device": device, "xy": (finite(position["x"]), finite(position["y"])), "z": finite(position["z"])})
    if not cameras:
        raise ValueError("No camera points")
    mesh, mesh_info = read_mesh(scene_dir / "mesh.obj")
    baseline = probe_report.get("local_baseline", {})
    if baseline.get("points", {}).get("count") != len(cameras) or baseline.get("mesh", {}).get("bytes") != (scene_dir / "mesh.obj").stat().st_size:
        raise ValueError("Scene assets differ from probe baseline; probe the correct server scene again")
    expected_bounds = baseline.get("mesh", {}).get("raw_xyz_bounds")
    if expected_bounds and any(
        abs(finite(expected_bounds[bound][axis]) - mesh_info["bounds_xyz"][bound][axis]) > 1e-6
        for bound in ("min", "max") for axis in range(3)
    ):
        raise ValueError("OBJ bounds differ from the successful probe")
    candidates = rank_candidates(axis_candidates(), rooms, mesh, cameras)
    selected = next((c for c in candidates if c["id"] == transform_id), None) if transform_id else candidates[0]
    if selected is None:
        raise ValueError("Unknown transform ID")
    timeline = json.loads((scene_dir / "timeline.json").read_text(encoding="utf-8"))
    ignition = int(timeline["start_point"])
    if ignition not in seen_devices:
        raise ValueError("Ignition device missing from points.json")
    memberships = []
    event_ids = {int(event["point"]) for event in timeline.get("spread_events", [])}
    for camera in sorted(cameras, key=lambda item: item["device"]):
        xy = apply_transform(camera["xy"], selected["matrix"])
        memberships.append({"device": camera["device"], "raw_xy": camera["xy"], "floor_xy": xy,
                            "ignition": camera["device"] == ignition, "in_timeline": camera["device"] in event_ids,
                            **classify(xy, rooms)})
    ignition_row = next(row for row in memberships if row["ignition"])
    target = ignition_row["room_id"]
    event_candidates = [row["device"] for row in memberships if target and row["room_id"] == target and row["in_timeline"]]
    report = {
        "scene_code": scene_dir.name, "status": "review_required", "floorplan_ready_for_crop": False,
        "alignment_verified": False, "selected_transform": selected,
        "selection_reason": "explicit_axis_hypothesis" if transform_id else "lowest_wall_to_mesh_distance_hypothesis",
        "limitations": [
            "Geometry ranking is not coordinate calibration: floor/furniture vertices may cause false matches.",
            "Only eight unit-scale XY axis hypotheses tested; no fitted translation, rotation, scale, or height.",
            "No reliable camera-to-floorplan correspondences were consumed; inspect panos or supply reviewed correspondences before fitting.",
            "Candidate camera room does not establish the physical fire origin from image content.",
            "No render inputs, meshes, events, or videos were modified.",
        ],
        "thresholds_m": {"boundary": BOUNDARY_TOLERANCE, "min_width": MIN_WIDTH}, "min_room_area_m2": MIN_AREA,
        "floor_index": floor_index, "floor_id": floor.get("id"), "panos_count": len(floor.get("panos", [])),
        "rooms": rooms, "mesh": mesh_info, "transform_candidates": candidates,
        "room_overlap_candidates": room_overlap_candidates(rooms),
        "memberships_provisional": memberships, "ignition_candidate": ignition_row,
        "target_room_event_devices_provisional": event_candidates,
        "inputs": {name: {"path": str(path), "sha256": sha256(path)} for name, path in (
            ("floorplan", source), ("probe_report", probe_dir / "report.json"),
            ("points", scene_dir / "points.json"), ("mesh", scene_dir / "mesh.obj"), ("timeline", scene_dir / "timeline.json"))},
    }
    return report, {"rooms": rooms, "mesh": mesh, "cameras": cameras, "candidates": candidates, "selected": selected["id"], "ignition": ignition}

