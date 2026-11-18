export interface Source {
  scene_code: string
  room_id: string
  database_room_id: number
  layout_version_id: number
  asset_version: string
}
export interface Asset {
  id: number
  kind: string
  size_bytes: number
  sha256: string
  uploaded: boolean
}
export interface Point {
  device: number
  x: number
  y: number
  z: number
  review_kind: string | null
}
export interface Job {
  scene_code?: string
  room_id?: string
  style_preset?: string
  camera_mode?: string
  fps?: number
  resolution?: number[]
  job_id: string
  asset_version?: string
  runtime_state: string
  technical_complete?: boolean
  human_acceptance?: string
  preset?: string
  completed_frames?: number
  total_frames?: number
  total_seconds?: number
  video_available?: boolean
  video_url?: string | null
  error_code?: string | null
  duration_seconds?: number
}
function object(v: unknown): Record<string, unknown> {
  if (!v || typeof v !== 'object' || Array.isArray(v)) throw Error('invalid')
  return v as Record<string, unknown>
}
export function list(v: unknown, key: string): unknown[] {
  const value = object(v)[key]
  if (!Array.isArray(value)) throw Error('invalid')
  return value
}
const token = (v: unknown): v is string =>
  typeof v === 'string' && /^[A-Za-z0-9][A-Za-z0-9_-]{0,95}$/.test(v)
export function sources(v: unknown): Source[] {
  return list(v, 'sources').map((item) => {
    const s = object(item)
    if (
      !token(s.scene_code) ||
      !token(s.room_id) ||
      !token(s.asset_version) ||
      !Number.isInteger(s.database_room_id) ||
      Number(s.database_room_id) < 1 ||
      !Number.isInteger(s.layout_version_id)
    )
      throw Error('invalid')
    return s as unknown as Source
  })
}
export function assets(v: unknown): Asset[] {
  return list(v, 'assets').map((item) => {
    const a = object(item)
    if (
      !Number.isInteger(a.id) ||
      Number(a.id) < 1 ||
      typeof a.kind !== 'string' ||
      typeof a.uploaded !== 'boolean' ||
      typeof a.sha256 !== 'string' ||
      !/^[a-f0-9]{64}$/.test(a.sha256) ||
      !Number.isFinite(a.size_bytes)
    )
      throw Error('invalid')
    return a as unknown as Asset
  })
}
export function points(v: unknown): Point[] {
  return list(v, 'points').map((item) => {
    const p = object(item)
    if (
      !Number.isInteger(p.device) ||
      ![p.x, p.y, p.z].every((x) => typeof x === 'number' && Number.isFinite(x)) ||
      !(p.review_kind === null || typeof p.review_kind === 'string')
    )
      throw Error('invalid')
    return p as unknown as Point
  })
}
export function jobs(v: unknown): Job[] {
  return list(v, 'jobs').map((item) => {
    const j = object(item)
    if (!token(j.job_id) || typeof j.runtime_state !== 'string') throw Error('invalid')
    if (
      j.video_url != null &&
      (typeof j.video_url !== 'string' ||
        !/^\/api\/room-jobs\/[A-Za-z0-9_-]+\/video\?/.test(j.video_url) ||
        j.video_url.includes('://'))
    )
      throw Error('invalid')
    return j as unknown as Job
  })
}
export function glbPoint(p: Point): [number, number, number] {
  return [p.x, p.z, -p.y]
}
