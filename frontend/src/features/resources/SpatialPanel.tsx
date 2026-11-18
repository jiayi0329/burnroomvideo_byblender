import { useEffect, useState } from 'react'
import { createApiClient, ApiError } from '@/lib/api/client'
import { useResources } from './context'
interface Spatial {
  file_job_id: string
  boundary: { polygon_raw_xy: number[][]; floor_z: number }
  ignition: { device: number; position_raw_xyz: number[] }
  members: { interior: number[]; boundary: number[] }
  source: { glb_sha256: string }
}
export function SpatialPanel() {
  const r = useResources()
  return (
    <SpatialContent
      key={[r.source?.scene_code, r.source?.asset_version, r.spatialEnabled, r.lastUpdated].join(
        '/',
      )}
    />
  )
}
function SpatialContent() {
  const r = useResources(),
    [state, setState] = useState<{ data?: Spatial; error?: string; trace?: string }>({}),
    [retry, setRetry] = useState(0)
  const job = r.jobs
    .filter(
      (j) =>
        j.preset === 'final' && j.technical_complete && j.asset_version === r.source?.asset_version,
    )
    .sort((a, b) => a.job_id.localeCompare(b.job_id))[0]
  const scene = r.source?.scene_code,
    version = r.source?.asset_version,
    glb = r.assets.find((a) => a.kind === 'room_glb')?.sha256
  useEffect(() => {
    if (!r.spatialEnabled || !scene || !job) return
    const controller = new AbortController()
    const api = createApiClient({ enabled: true })
    void api
      .read<Record<string, unknown>>(
        `/api/room-jobs/${job.job_id}/spatial-context?scene_code=${scene}`,
        { signal: controller.signal },
      )
      .then((raw) => {
        const d = raw as unknown as Spatial
        if (
          raw.verified !== true ||
          raw.verification_scope !== 'file_consistency_only' ||
          raw.scene_code !== scene ||
          raw.room_id !== 'Room8' ||
          raw.asset_version !== version ||
          d.file_job_id !== job.job_id ||
          !glb ||
          !/^[a-f0-9]{64}$/.test(glb) ||
          d.source.glb_sha256 !== glb ||
          !Array.isArray(d.boundary.polygon_raw_xy) ||
          d.boundary.polygon_raw_xy.length < 3 ||
          d.boundary.polygon_raw_xy.length > 128 ||
          !d.boundary.polygon_raw_xy.every(
            (p) => Array.isArray(p) && p.length === 2 && p.every(Number.isFinite),
          ) ||
          !Number.isFinite(d.boundary.floor_z) ||
          !Array.isArray(d.members.interior) ||
          !Array.isArray(d.members.boundary) ||
          !d.members.interior.includes(d.ignition.device) ||
          new Set([...d.members.interior, ...d.members.boundary]).size !==
            d.members.interior.length + d.members.boundary.length ||
          r.points.length !== d.members.interior.length + d.members.boundary.length ||
          !r.points.every((p) => [...d.members.interior, ...d.members.boundary].includes(p.device))
        )
          throw Error('contract')
        const p = r.points.find((p) => p.device === d.ignition.device)
        if (!p || ![p.x, p.y, p.z].every((n, i) => n === d.ignition.position_raw_xyz[i]))
          throw Error('point')
        if (!controller.signal.aborted) setState({ data: d })
      })
      .catch((e) => {
        if (!controller.signal.aborted)
          setState({
            error: e instanceof ApiError ? e.message : '摘要与当前资产/点位不一致，拒绝绘制。',
            trace: e instanceof ApiError ? e.traceId : undefined,
          })
      })
    return () => controller.abort()
  }, [r.spatialEnabled, r.points, scene, version, glb, job, retry])
  const d = state.data,
    ring = d?.boundary.polygon_raw_xy,
    xs = ring?.map((p) => p[0]) ?? [],
    ys = ring?.map((p) => p[1]) ?? [],
    x = Math.min(...xs),
    y = Math.max(...ys),
    span = ring ? Math.max(Math.max(...xs) - x, y - Math.min(...ys), 1) : 1
  return (
    <section className="panel">
      <div className="panel-heading">
        <h2>已归档边界与历史起火点</h2>
        <button
          className="ui-button button-outline"
          disabled={!r.spatialEnabled}
          onClick={() => {
            setState({})
            setRetry((v) => v + 1)
          }}
        >
          重新读取空间摘要
        </button>
      </div>
      {!r.spatialEnabled ? (
        <p className="panel-note">待空间摘要部署与线上只读验收后启用，不用下载副本冒充API响应。</p>
      ) : !job ? (
        <p className="panel-note">当前版本没有可核验的已归档正式任务。</p>
      ) : state.error ? (
        <p role="alert" className="panel-note">
          {state.error} {state.trace ?? ''}
        </p>
      ) : !d ? (
        <p role="status" className="panel-note">
          正在核验空间摘要…
        </p>
      ) : (
        <>
          <svg
            role="img"
            aria-label="已核验Room8边界与真实点位"
            viewBox={`${x - span * 0.15} ${-y - span * 0.15} ${span * 1.3} ${span * 1.3}`}
            style={{ width: '100%', height: 300 }}
          >
            <polygon
              points={ring!.map((p) => `${p[0]},${-p[1]}`).join(' ')}
              fill="#253749"
              stroke="#9dafc3"
              strokeWidth={span * 0.006}
            />
            {r.points.map((p) => (
              <g key={p.device}>
                <circle
                  cx={p.x}
                  cy={-p.y}
                  r={span * 0.015}
                  fill={
                    p.device === d.ignition.device
                      ? '#ffe29c'
                      : d.members.interior.includes(p.device)
                        ? '#ff803d'
                        : '#8ec6ed'
                  }
                />
                <text x={p.x + span * 0.025} y={-p.y} fill="white" fontSize={span * 0.035}>
                  {p.device}
                </text>
              </g>
            ))}
          </svg>
          <p className="panel-note">
            {ring!.length}顶点 · {d.members.interior.length}内部点 · {d.members.boundary.length}
            边界/门口点 · 历史起火点{d.ignition.device}（只读存档配置）。工程地板
            {d.boundary.floor_z}米，不代表真实建筑语义。
          </p>
        </>
      )}
    </section>
  )
}
