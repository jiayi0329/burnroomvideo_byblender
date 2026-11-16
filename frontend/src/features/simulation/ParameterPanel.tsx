import { useState } from 'react'
import { RotateCcw, SlidersHorizontal, LockKeyhole, ChevronDown } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { recorder } from '@/lib/telemetry/operations'

const parameters = [
  { key: 'flameDuration', label: '火焰持续时间' },
  { key: 'flameScale', label: '火焰尺度' },
  { key: 'smokeDensity', label: '烟雾密度' },
  { key: 'smokeDuration', label: '烟雾持续时间' },
  { key: 'light', label: '环境亮度' },
] as const
type Draft = Record<(typeof parameters)[number]['key'], number>
const initial: Draft = {
  flameDuration: 50,
  flameScale: 50,
  smokeDensity: 50,
  smokeDuration: 50,
  light: 50,
}
export function ParameterPanel() {
  const [draft, setDraft] = useState<Draft>({ ...initial })
  const [preset, setPreset] = useState('test')
  const [camera, setCamera] = useState('overview')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const changed = parameters.filter(({ key }) => draft[key] !== initial[key])
  function update(key: keyof Draft, text: string) {
    if (!text.trim() || !Number.isFinite(Number(text)) || Number(text) < 0 || Number(text) > 100) {
      setError('演示刻度请输入 0–100 之间的数值。')
      return
    }
    setError('')
    setNotice('')
    recorder.record('draft_change', () => setDraft({ ...draft, [key]: Number(text) }))
  }
  return (
    <aside className="panel parameters">
      <div className="panel-heading">
        <h2>
          <SlidersHorizontal size={17} />
          模拟与渲染参数
        </h2>
        <span className="badge orange">R3 只读基线</span>
      </div>
      <div className="parameter-body">
        <div className="info-note">
          <LockKeyhole size={15} />
          <p>以下为本地交互预览，不参与真实渲染。R3 原始配置保持只读。</p>
        </div>
        <div className="field">
          <label htmlFor="ignition">起火点</label>
          <select id="ignition" disabled>
            <option>待加载有效房间点位</option>
          </select>
        </div>
        <div className="field">
          <label htmlFor="spread">传播模式</label>
          <select id="spread" disabled>
            <option>R3 内部点 BFS · 待接入</option>
          </select>
        </div>
        <div className="section-label">
          火烟与光照 <span>演示刻度</span>
        </div>
        <p className="muted tiny">
          范围 0–100 仅用于界面操作；引擎默认值、单位与允许范围待确认，初始演示值为 50。
        </p>
        {parameters.map(({ key, label }) => (
          <div className="slider-field" key={key}>
            <div>
              <label htmlFor={key}>{label}</label>
              <input
                aria-label={`${label}数值`}
                type="number"
                min="0"
                max="100"
                value={draft[key]}
                onChange={(e) => update(key, e.target.value)}
              />
            </div>
            <input
              id={key}
              type="range"
              min="0"
              max="100"
              value={draft[key]}
              onChange={(e) => update(key, e.target.value)}
            />
            <div className="range-label">
              <span>0</span>
              <span>100 · 无物理单位</span>
            </div>
          </div>
        ))}
        {error && (
          <p className="inline-error" role="alert">
            {error}
          </p>
        )}
        <div className="section-label">
          镜头与输出 <span>契约选项预览</span>
        </div>
        <div className="field">
          <label htmlFor="quality">质量预设</label>
          <select
            id="quality"
            value={preset}
            onChange={(e) =>
              recorder.record('draft_change', () => {
                setPreset(e.target.value)
                if (e.target.value === 'final') setCamera('overview')
              })
            }
          >
            <option value="test">测试短片 · 960×540 / 12 帧每秒</option>
            <option value="final">正式成片 · 1280×720 / 24 帧每秒</option>
          </select>
        </div>
        <div className="field">
          <label htmlFor="camera">相机</label>
          <select
            id="camera"
            value={camera}
            onChange={(e) => recorder.record('draft_change', () => setCamera(e.target.value))}
          >
            <option value="overview">总览（overview）</option>
            <option value="closeup" disabled={preset === 'final'}>
              近景（closeup）
            </option>
          </select>
        </div>
        <p className="muted tiny">正式档仅允许总览，并需后端核验审批。这里的选择不会发送请求。</p>
        <details className="draft-details">
          <summary>
            查看本次草稿修改{' '}
            <span>
              {changed.length + Number(preset !== 'test') + Number(camera !== 'overview')} 项
            </span>
            <ChevronDown size={14} />
          </summary>
          {changed.length === 0 && preset === 'test' && camera === 'overview' ? (
            <p>尚未修改演示草稿。</p>
          ) : (
            <ul>
              {changed.map((p) => (
                <li key={p.key}>
                  {p.label}：50 → {draft[p.key]}（演示刻度）
                </li>
              ))}
              {preset !== 'test' && <li>质量预设：正式成片</li>}
              {camera !== 'overview' && <li>相机：近景</li>}
            </ul>
          )}
        </details>
        <Button
          variant="outline"
          className="full-width"
          onClick={() =>
            recorder.record('draft_reset', () => {
              setDraft({ ...initial })
              setPreset('test')
              setCamera('overview')
              setError('')
              setNotice('已恢复本地演示初始值，未改写 R3。')
            })
          }
        >
          <RotateCcw size={14} />
          重置演示草稿
        </Button>
        {notice && (
          <p role="status" className="muted tiny">
            {notice}
          </p>
        )}
        <Button variant="ghost" className="full-width" disabled>
          保存为新预设 · 待接入
        </Button>
      </div>
      <div className="parameter-submit">
        <Button className="full-width" disabled>
          <LockKeyhole size={15} />
          开始渲染 · 待接入
        </Button>
        <p>真实资源、参数校验及提交接口尚未连接</p>
      </div>
    </aside>
  )
}
