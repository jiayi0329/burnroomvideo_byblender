"""Controlled Room8/R3 task API. Reads do not depend on PostgreSQL availability."""
from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Header, HTTPException, Path as PathParam, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from backend.adapters.postgres import room_job_repository
from backend.services import room_job_service as jobs
from backend.services import room_video
from render_engine.jobs.operation_logging import stage

router = APIRouter(prefix='/api/room-jobs', tags=['Room8 jobs'])
Identifier = Annotated[str, Field(pattern=r'^[A-Za-z0-9][A-Za-z0-9_-]{0,95}$', strict=True)]
JobIdentifier = Annotated[str, PathParam(pattern=r'^[A-Za-z0-9][A-Za-z0-9_-]{0,95}$')]


class CreateRoomJob(BaseModel):
    model_config = ConfigDict(extra='forbid')
    scene_code: Identifier
    room_id: Literal['Room8'] = 'Room8'
    asset_version: Identifier
    layout_version_id: Annotated[int, Field(gt=0, strict=True)]
    style_preset: Literal['r3'] = 'r3'
    preset: Literal['test', 'final'] = 'test'
    camera_mode: Literal['overview', 'closeup'] = 'overview'
    confirm_render: Annotated[bool, Field(strict=True)]
    approval_job_id: Identifier | None = None


def call(function, *args, _context=None, **kwargs):
    with stage('room.api', 'request_operation', **(_context or {})):
        return guarded_call(function, *args, **kwargs)


def guarded_call(function, *args, **kwargs):
    try:
        return function(*args, **kwargs)
    except jobs.JobError as exc:
        raise HTTPException(exc.status, detail={'code': exc.code}) from None
    except room_job_repository.CatalogUnavailable:
        raise HTTPException(503, detail={'code': 'catalog_unavailable'}) from None
    except (ValueError, KeyError, TypeError, OSError):
        raise HTTPException(409, detail={'code': 'job_inputs_or_evidence_invalid'}) from None
    except RuntimeError:
        raise HTTPException(409, detail={'code': 'render_conflict_or_launcher_error'}) from None
    except Exception:
        raise HTTPException(503, detail={'code': 'room_job_dependency_unavailable'}) from None


@router.get('/options')
def get_options():
    return jobs.options()


@router.get('/sources')
def get_sources():
    return call(room_job_repository.sources)


@router.post('', status_code=202)
def create_job(body: CreateRoomJob, idempotency_key: Annotated[str, Header(
        min_length=8, max_length=96, pattern=r'^[A-Za-z0-9][A-Za-z0-9_-]{7,95}$')]):
    if body.confirm_render is not True:
        raise HTTPException(422, detail={'code': 'explicit_confirmation_required'})
    if body.preset == 'final' and body.camera_mode != 'overview':
        raise HTTPException(422, detail={'code': 'final_requires_overview'})
    return call(jobs.submit, body.model_dump(), idempotency_key,
                _context={'scene_code': body.scene_code, 'room_id': body.room_id, 'asset_version': body.asset_version})


@router.get('')
def list_jobs(scene_code: Annotated[str, Query(pattern=r'^[A-Za-z0-9][A-Za-z0-9_-]{0,95}$')],
              room_id: Literal['Room8'] = 'Room8', limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0)):
    return call(jobs.history, scene_code, limit, offset, _context={'scene_code': scene_code, 'room_id': room_id})


@router.get('/{job_id}')
def get_job(job_id: JobIdentifier, scene_code: Annotated[str, Query(pattern=r'^[A-Za-z0-9][A-Za-z0-9_-]{0,95}$')],
            room_id: Literal['Room8'] = 'Room8'):
    return call(jobs.get_job, scene_code, job_id,
                _context={'scene_code': scene_code, 'room_id': room_id, 'job_id': job_id})


@router.get('/{job_id}/video')
@router.head('/{job_id}/video')
def video(job_id: JobIdentifier, request: Request,
          scene_code: Annotated[str, Query(pattern=r'^[A-Za-z0-9][A-Za-z0-9_-]{0,95}$')], room_id: Literal['Room8'] = 'Room8'):
    def open_video():
        job = jobs.job_directory(scene_code, job_id)
        spec = jobs.snapshot(job, scene_code)
        path = jobs.verified_video(job, spec)
        receipt = jobs.read_document(job, 'video_receipt.json')
        return room_video.response(path, receipt['sha256'], method=request.method,
            range_header=request.headers.get('range'), if_range=request.headers.get('if-range'))
    return call(open_video, _context={'scene_code': scene_code, 'room_id': room_id, 'job_id': job_id})
