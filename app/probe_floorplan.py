"""只读探测户型 API；仅写 diagnostics，不导入 bpy、不启动渲染。

服务器现有容器：python3 -m app.probe_floorplan --scene KK-EEz16cmU14
本地资产分析：python app/probe_floorplan.py --scene KK-EEz16cmU14 --data-root data --offline
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import ipaddress
import json
from pathlib import Path
import re
import time
from typing import Any
from urllib.parse import urlsplit
import uuid
import zipfile
import os

API_URL = "https://api.4dkankan.com/scene/getSceneViewUserFile"
MAX_BYTES = 32 * 1024 * 1024
MAX_JSON_BYTES = 4 * 1024 * 1024
MAX_MEMBERS = 500
MAX_LINKS = 4
HINTS = ("room", "wall", "floor", "polygon", "contour", "bound", "unit", "transform", "matrix", "vertex", "vertices")
URL_PATTERN = re.compile(r"https?://[^\s\"<>]+", re.IGNORECASE)


def redact(value: Any, secret: str = "") -> Any:
    """保留结构与几何数值，移除凭证和临时 URL（包括嵌入字符串）。"""
    if isinstance(value, dict):
        return {
            key: "[REDACTED]" if any(
                word in key.lower() for word in ("token", "password", "secret", "appkey", "authorization", "signature", "credential")
            ) else redact(item, secret)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact(item, secret) for item in value]
    if isinstance(value, str):
        text = value.replace(secret, "[REDACTED]") if secret else value
        return URL_PATTERN.sub("[URL REDACTED]", text)
    return value


def save_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def field_hints(value: Any) -> list[dict]:
    """仅标记候选字段，不把关键字命中判作有效户型。"""
    found: list[dict] = []
    visited = 0

    def walk(item: Any, path: str, depth: int) -> None:
        nonlocal visited
        visited += 1
        if depth > 12 or visited > 20000 or len(found) >= 100:
            return
        if isinstance(item, dict):
            for key, child in item.items():
                child_path = f"{path}.{key}"
                if any(hint in key.lower() for hint in HINTS):
                    entry = {"path": child_path, "type": type(child).__name__}
                    if isinstance(child, (dict, list)):
                        entry["length"] = len(child)
                    found.append(entry)
                walk(child, child_path, depth + 1)
        elif isinstance(item, list):
            for index, child in enumerate(item[:20]):
                walk(child, f"{path}[{index}]", depth + 1)

    walk(value, "$", 0)
    return found[:100]


def download_links(value: Any) -> list[str]:
    links: list[str] = []

    def walk(item: Any) -> None:
        if isinstance(item, str) and item.startswith(("https://", "http://")):
            if item not in links:
                links.append(item)
        elif isinstance(item, dict):
            for child in item.values():
                walk(child)
        elif isinstance(item, list):
            for child in item:
                walk(child)

    walk(value)
    return links


def validate_download_url(url: str) -> None:
    parsed = urlsplit(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Invalid download URL")
    if parsed.hostname.lower() == "localhost" or parsed.hostname.lower().endswith(".local"):
        raise ValueError("Local download host rejected")
    try:
        address = ipaddress.ip_address(parsed.hostname)
    except ValueError:
        return
    if not address.is_global:
        raise ValueError("Non-public download address rejected")


def bounded_body(response: Any, limit: int) -> bytes:
    content = bytearray()
    for chunk in response.iter_content(chunk_size=65536):
        content.extend(chunk)
        if len(content) > limit:
            raise ValueError("Response exceeds probe size limit")
    return bytes(content)


def inspect_archive(path: Path, output_dir: Path, secret: str = "") -> dict:
    """只读取有限大小的 ZIP/JSON，不向文件系统解压成员。"""
    if not zipfile.is_zipfile(path):
        result: dict = {"format": "non_zip", "bytes": path.stat().st_size}
        if path.stat().st_size <= MAX_JSON_BYTES:
            try:
                value = json.loads(path.read_text(encoding="utf-8-sig"))
                save_json(output_dir / f"{path.stem}_json_redacted.json", redact(value, secret))
                result.update(format="json", field_hints=field_hints(value))
            except (ValueError, UnicodeError):
                pass
        return result
    result = {"format": "zip", "members": [], "json_documents": []}
    total_json_bytes = 0
    with zipfile.ZipFile(path) as archive:
        members = archive.infolist()
        result["member_count"] = len(members)
        result["inventory_truncated"] = len(members) > MAX_MEMBERS
        for index, member in enumerate(members[:MAX_MEMBERS]):
            result["members"].append({"name": redact(member.filename, secret), "bytes": member.file_size})
            if not member.filename.lower().endswith(".json") or member.is_dir():
                continue
            record = {"member_index": index, "name": redact(member.filename, secret)}
            result["json_documents"].append(record)
            if member.file_size > MAX_JSON_BYTES or total_json_bytes + member.file_size > MAX_BYTES:
                record["status"] = "skipped_size_limit"
                continue
            if member.flag_bits & 1:
                record["status"] = "skipped_encrypted"
                continue
            try:
                with archive.open(member) as source:
                    raw = source.read(MAX_JSON_BYTES + 1)
                if len(raw) > MAX_JSON_BYTES:
                    raise ValueError("JSON exceeds limit")
                total_json_bytes += len(raw)
                value = json.loads(raw.decode("utf-8-sig"))
                filename = f"{path.stem}_member_{index:04d}_redacted.json"
                save_json(output_dir / filename, redact(value, secret))
                record.update(status="inspected", saved_as=filename, field_hints=field_hints(value))
            except (ValueError, UnicodeError, OSError, RuntimeError, zipfile.BadZipFile) as exc:
                record.update(status="unreadable", error_type=type(exc).__name__)
    return result


def local_baseline(scene_dir: Path) -> dict:
    result: dict = {}
    points_path = scene_dir / "points.json"
    if points_path.is_file():
        points = json.loads(points_path.read_text(encoding="utf-8"))
        rooms = Counter(str(point.get("room", "missing")) for point in points)
        result["points"] = {
            "count": len(points), "room_counts": dict(rooms),
            "group_counts": dict(Counter(str(point.get("group", "missing")) for point in points)),
            "warning": "Room labels require geometric validation; identical labels do not prove one room.",
        }
    timeline_path = scene_dir / "timeline.json"
    if timeline_path.is_file():
        timeline = json.loads(timeline_path.read_text(encoding="utf-8"))
        events = timeline.get("spread_events", [])
        legacy_frames = int(max((event["time"] for event in events), default=0)) * 24 + 73
        result["timeline"] = {
            "start_point": timeline.get("start_point"), "event_count": len(events),
            "legacy_frame_count_at_24fps": legacy_frames,
            "20min_seconds_per_frame_before_overhead": round(1200 / legacy_frames, 3),
        }
    mesh_path = scene_dir / "mesh.obj"
    if mesh_path.is_file():
        counts: Counter = Counter()
        mins = [float("inf")] * 3
        maxs = [float("-inf")] * 3
        with mesh_path.open(encoding="utf-8", errors="replace") as stream:
            for line in stream:
                prefix = line.partition(" ")[0]
                if prefix in ("v", "f", "o", "g"):
                    counts[prefix] += 1
                if prefix == "v":
                    for axis, text in enumerate(line.split()[1:4]):
                        value = float(text)
                        mins[axis] = min(mins[axis], value)
                        maxs[axis] = max(maxs[axis], value)
        result["mesh"] = {"bytes": mesh_path.stat().st_size, "element_counts": dict(counts)}
        if counts["v"]:
            result["mesh"]["raw_xyz_bounds"] = {"min": mins, "max": maxs}
    return result


def probe_api(scene_code: str, output_dir: Path, secret: str) -> dict:
    import requests  # 使用服务器既有依赖；本地离线分析不需要安装 requests。

    started = time.monotonic()
    with requests.post(
        API_URL, headers={"Content-Type": "application/json", "Authorization": secret},
        json={"sceneCode": scene_code}, timeout=(10, 40), stream=True,
    ) as response:
        response.raise_for_status()
        payload = json.loads(bounded_body(response, MAX_JSON_BYTES))
    if not isinstance(payload, dict):
        raise ValueError("API response must be an object")
    save_json(output_dir / "api_response_redacted.json", redact(payload, secret))
    result: dict = {
        "http_status": response.status_code, "code": redact(payload.get("code"), secret),
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "data_type": type(payload.get("data")).__name__,
        "field_hints": field_hints(payload.get("data")), "assets": [],
    }
    if payload.get("code") != 0:
        result["status"] = "api_rejected"
        return result
    if not payload.get("data"):
        result["status"] = "no_data"
        return result
    links = download_links(payload["data"])
    result.update(status="inspected", link_count=len(links), links_truncated=len(links) > MAX_LINKS)
    for index, url in enumerate(links[:MAX_LINKS]):
        record: dict = {"index": index}
        result["assets"].append(record)
        try:
            validate_download_url(url)
            # 不向资源主机发送 appkey，不自动跟随重定向到其他地址。
            with requests.get(url, timeout=(10, 40), stream=True, allow_redirects=False) as asset:
                if asset.status_code != 200:
                    record.update(status="download_rejected", http_status=asset.status_code)
                    continue
                content = bounded_body(asset, MAX_BYTES)
            path = output_dir / f"asset_{index:02d}.bin"
            path.write_bytes(content)
            record.update(status="downloaded", saved_as=path.name, **inspect_archive(path, output_dir, secret))
        except Exception as exc:
            record.update(status="failed", error_type=type(exc).__name__)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe floorplan data without rendering")
    parser.add_argument("--scene", required=True)
    parser.add_argument("--data-root", type=Path, default=Path("/app/data"))
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9_-]+", args.scene):
        parser.error("Invalid scene code")
    scene_dir = args.data_root / args.scene
    if not scene_dir.is_dir():
        parser.error("Scene directory does not exist")
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid.uuid4().hex[:8]
    output_dir = scene_dir / "diagnostics" / "floorplan" / run_id
    output_dir.mkdir(parents=True)
    report: dict = {
        "scene_code": args.scene, "status": "offline" if args.offline else "pending",
        "floorplan_ready_for_crop": False,
        "review_required": ["room boundaries", "coordinate axes and origin", "units and scale", "point/OBJ alignment"],
    }
    exit_code = 0
    try:
        report["local_baseline"] = local_baseline(scene_dir)
        if not args.offline:
            secret = os.getenv("DK_APPKEY", "")
            if not secret:
                report["error_code"] = "missing_DK_APPKEY"
                raise ValueError("DK_APPKEY is not configured")
            report["api"] = probe_api(args.scene, output_dir, secret)
            report["status"] = report["api"]["status"]
            if report["status"] != "inspected" or any(
                item["status"] != "downloaded" for item in report["api"]["assets"]
            ) or report["api"].get("links_truncated"):
                exit_code = 1
    except Exception as exc:
        report.update(status="failed", error_type=type(exc).__name__)
        exit_code = 1
    save_json(output_dir / "report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)
    print(f"[floorplan-probe] report={output_dir / 'report.json'}", flush=True)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
