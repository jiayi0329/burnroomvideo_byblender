import type { Point } from '@/features/resources/contracts'
import { glbPoint, pointLabel } from '@/features/resources/contracts'
import { Button } from '@/components/ui/button'

export function PointInspector({
  points,
  selectedId,
  onSelect,
}: {
  points: Point[]
  selectedId?: string
  onSelect: (id?: string) => void
}) {
  const point = points.find((p) => String(p.device) === selectedId)
  const format = (values: number[]) => values.map((v) => v.toFixed(3)).join(' / ')
  return (
    <section className="panel point-inspector" aria-label="点位信息">
      <div className="point-selector">
        <label htmlFor="inspect-point">查看扫描点位</label>
        <select
          id="inspect-point"
          value={point ? String(point.device) : ''}
          disabled={!points.length}
          onChange={(e) => onSelect(e.target.value || undefined)}
        >
          <option value="">请选择点位（只读查看）</option>
          {points.map((p) => (
            <option key={p.device} value={p.device}>
              点位 {p.device} · {pointLabel(p)}
            </option>
          ))}
        </select>
        <Button variant="ghost" disabled={!point} onClick={() => onSelect(undefined)}>
          取消选择
        </Button>
      </div>
      <p className="point-legend">
        <span>● 内部点</span>
        <span>● 门口点</span>
        <span>● 当前选中</span>
      </p>
      {point ? (
        <dl className="data-list">
          <div>
            <dt>选中点位</dt>
            <dd>
              {point.device} · {pointLabel(point)}
            </dd>
          </div>
          <div>
            <dt>原始 X / Y / Z（米）</dt>
            <dd>
              <code>{format([point.x, point.y, point.z])}</code>
            </dd>
          </div>
          <div>
            <dt>GLB X / Y / Z（米）</dt>
            <dd>
              <code>{format(glbPoint(point))}</code>
            </dd>
          </div>
        </dl>
      ) : (
        <p className="panel-note">可在模型或下拉列表选中真实点位。未选择任何起火点。</p>
      )}
      <p className="panel-note">
        坐标来自已登记场景的扫描相机位姿，不是火焰底座。选择仅用于高亮与查看，不改变传播或渲染配置。
      </p>
    </section>
  )
}
