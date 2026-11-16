import { useMemo, useState } from 'react'
import { Box, MapPin, ChevronRight, Info } from 'lucide-react'
import { PageHeading } from '@/components/PageHeading'
import { RoomPreview } from '@/features/room-preview/RoomPreview'
import { ParameterPanel } from '@/features/simulation/ParameterPanel'
import { Link } from 'react-router-dom'
import { useResources } from '@/features/resources/context'
import { glbPoint } from '@/features/resources/contracts'
import { recorder } from '@/lib/telemetry/operations'
export function SimulationPage() {
  const r = useResources()
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
        description="只读查看已登记空间与归档成果；参数草稿不参与真实渲染。"
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
            key={r.source?.asset_version ?? 'unconnected'}
            modelUrl={glb ? `/room-assets/${glb.id}` : undefined}
            imageUrl={image ? `/room-assets/${image.id}` : undefined}
            videoUrl={v1?.video_url ?? undefined}
            points={previewPoints}
          />
          <p className="muted tiny">
            房间边界与实际起火点：现有只读接口未提供相应核验证据，暂不绘制。
          </p>
          <div className="current-task-summary">
            <span>
              {v1
                ? `V1 · ${v1.completed_frames}/${v1.total_frames} 帧 · 技术完成，人工审核未记录`
                : '当前任务：未选择'}
            </span>
            <Link to="/results">查看任务与成果 →</Link>
          </div>
        </div>
        <ParameterPanel />
      </div>
    </>
  )
}
