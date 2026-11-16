import { useState } from 'react'
import { Box, Image, Video, Scan, RotateCcw, Move3D, ZoomIn } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { recorder } from '@/lib/telemetry/operations'

export interface PreviewPoint {
  id: string
  position: [number, number, number]
  selectable: boolean
}
/** Phase 2 adapter: pass verified resource URLs, do not convert GLB coordinates twice. */
export interface RoomPreviewProps {
  modelUrl?: string
  imageUrl?: string
  videoUrl?: string
  points?: PreviewPoint[]
  onPointSelect?: (id: string) => void
  onResetView?: () => void
  onLoadState?: (state: 'loading' | 'success' | 'error') => void
}
const views = [
  { id: 'model', label: '三维模型', icon: Box },
  { id: 'image', label: '检查图片', icon: Image },
  { id: 'video', label: '火灾视频', icon: Video },
] as const
export function RoomPreview(_props: RoomPreviewProps) {
  const [view, setView] = useState('model')
  return (
    <section className="preview">
      <div className="preview-toolbar">
        <div className="segmented" aria-label="预览内容">
          {views.map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              aria-pressed={view === id}
              onClick={() => recorder.record('preview_tab', () => setView(id))}
            >
              <Icon size={15} />
              {label}
            </button>
          ))}
        </div>
        <span className="micro">只读资源视口</span>
      </div>
      <div className="viewport">
        <span className="viewport-corner top-left" />
        <span className="viewport-corner bottom-right" />
        <div className="viewport-content">
          <div className="preview-glyph">
            <Scan size={46} strokeWidth={1} />
          </div>
          <span className="eyebrow">资源预览 / 尚未连接</span>
          <h2>
            {view === 'model'
              ? '让真实空间进入工作台'
              : view === 'image'
                ? '房间检查图片待接入'
                : '已生成视频待接入'}
          </h2>
          <p>
            {view === 'model'
              ? '第二阶段加载真实 GLB 与扫描点位。当前未加载任何模型。'
              : view === 'image'
                ? '连接已登记的检查图，核对独立房间与裁切边界。'
                : '连接已有任务的视频回执后，在此播放与拖动查看。'}
          </p>
          <span className="badge">待接入</span>
        </div>
        <div className="viewport-footer">
          <span>
            <span className="dot" />
            {view === 'model' ? '模型来源未连接' : '媒体来源未连接'}
          </span>
          <span>不展示模拟资源</span>
        </div>
      </div>
      <div className="preview-controls">
        <span>
          <Move3D size={14} />
          旋转 / 平移
        </span>
        <span>
          <ZoomIn size={14} />
          滚轮缩放
        </span>
        <Button variant="ghost" disabled>
          <RotateCcw size={14} />
          视角复位 · 待接入
        </Button>
      </div>
    </section>
  )
}
