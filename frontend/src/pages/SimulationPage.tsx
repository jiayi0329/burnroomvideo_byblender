import { useMemo, useState } from 'react'
import { Box, MapPin, ChevronRight, Info } from 'lucide-react'
import { PageHeading } from '@/components/PageHeading'
import { RoomPreview } from '@/features/room-preview/RoomPreview'
import { ParameterPanel } from '@/features/simulation/ParameterPanel'
import { Link } from 'react-router-dom'
import { useResources } from '@/features/resources/context'
import { glbPoint } from '@/features/resources/contracts'
import { recorder } from '@/lib/telemetry/operations'
import { PointInspector } from '@/features/room-preview/PointInspector'
import { TestSubmissionPanel } from '@/features/jobs/TestSubmissionPanel'
import { restoreSubmission } from '@/features/jobs/submission'
export function SimulationPage() {
  const r = useResources()
  const saved = restoreSubmission()
  const currentSubmission =
    saved?.payload.scene_code === r.source?.scene_code &&
    saved?.payload.asset_version === r.source?.asset_version
      ? saved
      : undefined
  const [selection, setSelection] = useState<{ source: string; id?: string }>()
  const sourceKey = r.source
    ? [
        r.source.scene_code,
        r.source.room_id,
        r.source.layout_version_id,
        r.source.asset_version,
      ].join('/')
    : 'unconnected'
  const selectedPointId = selection?.source === sourceKey ? selection.id : undefined
  const selectPoint = (id?: string) =>
    recorder.record('point_select', () => setSelection({ source: sourceKey, id }))
  const glb = r.assets.find((a) => a.kind === 'room_glb' && a.uploaded)
  const images = r.assets.filter((a) => a.kind === 'room_preview' && a.uploaded)
  const [imageId, setImageId] = useState<number>()
  const image = images.find((a) => a.id === imageId) ?? images[0]
  const previewPoints = useMemo(
    () =>
      r.points.map((p) => ({
        id: String(p.device),
        position: glbPoint(p),
        selectable: p.review_kind === 'interior',
      })),
    [r.points],
  )
  const v1 = r.jobs
    .filter(
      (j) =>
        j.preset === 'final' &&
        j.technical_complete &&
        j.video_available &&
        j.asset_version === r.source?.asset_version,
    )
    .sort((a, b) => a.job_id.localeCompare(b.job_id))[0]
  return (
    <>
      <PageHeading
        number="03"
        title="火灾模拟工作台"
        description="查看真实空间与归档成果；受控测试需明确确认，演示草稿不参与渲染。"
      />
      <div className="simulation-layout">
        <aside className="room-navigation panel">
          <div className="panel-heading">
            <h2>
              <Box size={16} />
              空间导航
            </h2>
          </div>
          <div className="room-context">
            <span className="eyebrow">当前场景</span>
            <strong>{r.source?.scene_code ?? '尚未选择'}</strong>
            <span className="badge">{r.source?.room_id ?? '无资源'}</span>
          </div>
          <div className="room-nav-label">房间列表</div>
          <div className="room-nav-empty">
            <Box size={17} />
            <div>
              {r.source?.room_id ?? '待加载房间'}
              <small>{r.source?.asset_version ?? '由登记来源决定'}</small>
            </div>
            <ChevronRight size={13} />
          </div>
          <div className="room-nav-label">扫描点位</div>
          <div className="points-empty">
            <MapPin size={22} />
            <p>{r.points.length ? `${r.points.length} 个真实关联点` : '有效点位待接入'}</p>
            <small>橙色：内部点；蓝色：门口点。点击仅查看，不设置起火点。</small>
          </div>
          <div className="room-guidance">
            <Info size={15} />
            <p>首个接入对象为 Room8。界面按场景与资产版本组织，可扩展其他已核验房间。</p>
          </div>
        </aside>
        <div className="simulation-center">
          {images.length > 1 && (
            <div className="image-select">
              <label htmlFor="inspection-image">检查图片</label>
              <select
                id="inspection-image"
                value={image?.id}
                onChange={(e) =>
                  recorder.record('resource_select', () => setImageId(Number(e.target.value)))
                }
              >
                {images.map((a, index) => (
                  <option key={a.id} value={a.id}>
                    已登记检查图 {index + 1} · 资产 {a.id}
                  </option>
                ))}
              </select>
            </div>
          )}
          <RoomPreview
            key={sourceKey}
            modelUrl={glb ? `/room-assets/${glb.id}` : undefined}
            imageUrl={image ? `/room-assets/${image.id}` : undefined}
            videoUrl={v1?.video_url ?? undefined}
            points={previewPoints}
            selectedPointId={selectedPointId}
            onPointSelect={selectPoint}
          />
          <PointInspector points={r.points} selectedId={selectedPointId} onSelect={selectPoint} />
          <details className="panel resource-provenance">
            <summary className="panel-heading">资源版本与来源</summary>
            <dl className="data-list">
              <div>
                <dt>场景 / 房间</dt>
                <dd>{r.source ? `${r.source.scene_code} / ${r.source.room_id}` : '未选择'}</dd>
              </div>
              <div>
                <dt>户型版本</dt>
                <dd>{r.source?.layout_version_id ?? '未提供'}</dd>
              </div>
              <div>
                <dt>基础资产版本</dt>
                <dd>
                  <code>{r.source?.asset_version ?? '未提供'}</code>
                </dd>
              </div>
              <div>
                <dt>GLB 文件 SHA256</dt>
                <dd>
                  <code>{glb?.sha256 ?? '未提供'}</code>
                </dd>
              </div>
              <div>
                <dt>当前检查图资产</dt>
                <dd>{image?.id ?? '未选择'}</dd>
              </div>
              <div>
                <dt>V1 文件任务</dt>
                <dd>
                  <code>{v1?.job_id ?? '未提供'}</code>
                </dd>
              </div>
            </dl>
          </details>
          <p className="muted tiny">
            已归档边界与历史起火点请到房间处理工作台查看；新摘要未部署验收时保持关闭，不设置新起火点。
          </p>
          <div className="current-task-summary">
            <span>
              {currentSubmission?.job_id
                ? `当前测试任务：${currentSubmission.job_id}，实际进度见任务中心`
                : v1
                  ? `V1 · ${v1.completed_frames}/${v1.total_frames} 帧 · 技术完成，人工审核未记录`
                  : '当前任务：未选择'}
            </span>
            <Link
              to={
                currentSubmission?.job_id
                  ? `/results?scene=${currentSubmission.payload.scene_code}&job=${currentSubmission.job_id}`
                  : '/results'
              }
            >
              查看任务与成果 →
            </Link>
          </div>
        </div>
        <aside>
          <TestSubmissionPanel key={sourceKey} />
          <details className="panel">
            <summary className="panel-heading">仅本地演示草稿（不会提交）</summary>
            <ParameterPanel />
          </details>
        </aside>
      </div>
    </>
  )
}
