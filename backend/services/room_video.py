"""Verified local MP4 streaming with single-range support on existing Starlette."""
from __future__ import annotations

from functools import lru_cache
import os
from pathlib import Path
import re

from starlette.responses import Response, StreamingResponse

from render_engine.jobs.room_animation_job import digest


def identity(stat) -> tuple:
    return stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns


@lru_cache(maxsize=64)
def verified(path: Path, sha: str, attributes: tuple) -> None:
    if digest(path) != sha or identity(path.stat()) != attributes:
        raise ValueError('Video fingerprint differs')


def verify_bytes(path: Path, sha: str, size: int) -> None:
    if not isinstance(sha, str) or not re.fullmatch(r'[0-9a-f]{64}', sha) or not isinstance(size, int) or size <= 0:
        raise ValueError('Invalid video receipt')
    stat = path.stat()
    if stat.st_size != size:
        raise ValueError('Video size differs')
    verified(path, sha, identity(stat))


def byte_range(value: str | None, size: int) -> tuple[int, int]:
    if value is None:
        return 0, size-1
    match = re.fullmatch(r'bytes=(\d*)-(\d*)', value)
    if not match or not any(match.groups()):
        raise ValueError('Unsupported range')
    left, right = match.groups()
    if not left:
        length = int(right)
        if length <= 0:
            raise ValueError('Invalid suffix range')
        return max(0, size-length), size-1
    start, end = int(left), min(int(right), size-1) if right else size-1
    if start >= size or end < start:
        raise ValueError('Unsatisfiable range')
    return start, end


def response(path: Path, sha: str, *, method: str, range_header: str | None, if_range: str | None):
    stat = path.stat()
    etag = '"'+sha+'"'
    if if_range and if_range != etag:
        range_header = None
    headers = {'Accept-Ranges': 'bytes', 'ETag': etag, 'Cache-Control': 'private, no-cache',
               'Content-Disposition': f'inline; filename="{path.name}"'}
    try:
        start, end = byte_range(range_header, stat.st_size)
    except (ValueError, OverflowError):
        return Response(status_code=416, headers={**headers, 'Content-Range': f'bytes */{stat.st_size}'})
    length = end-start+1
    headers['Content-Length'] = str(length)
    status = 206 if range_header else 200
    if status == 206:
        headers['Content-Range'] = f'bytes {start}-{end}/{stat.st_size}'
    if method == 'HEAD':
        return Response(status_code=status, media_type='video/mp4', headers=headers)

    def chunks():
        with path.open('rb') as source:
            opened = identity(os.fstat(source.fileno()))
            expected = identity(stat)
            # Windows path stat and handle fstat may expose different ctime
            # values immediately after a write. Inode/size/mtime still agree;
            # Linux retains the additional ctime check. SHA was checked above.
            if opened[:4] != expected[:4] or (os.name != 'nt' and opened[4] != expected[4]):
                raise OSError('Video changed before streaming')
            source.seek(start)
            remaining = length
            while remaining:
                chunk = source.read(min(1024*1024, remaining))
                if not chunk:
                    raise OSError('Video truncated during streaming')
                remaining -= len(chunk)
                yield chunk

    return StreamingResponse(chunks(), status_code=status, media_type='video/mp4', headers=headers)
