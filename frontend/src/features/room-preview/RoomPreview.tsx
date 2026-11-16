import { Component, Suspense, lazy, useEffect, useRef, useState, type ReactNode } from 'react'
import { Box, Image, Video, RotateCcw, Maximize, RefreshCw } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { recorder } from '@/lib/telemetry/operations'
const ModelCanvas = lazy(() => import('./ModelCanvas'))
export interface PreviewPoint {
  id: string
  position: [number, number, number]
  selectable: boolean
}
export interface RoomPreviewProps {
  modelUrl?: string
  imageUrl?: string
  videoUrl?: string
  points?: PreviewPoint[]
  onPointSelect?: (id: string) => void
  onResetView?: () => void
  onLoadState?: (state: 'loading' | 'success' | 'error') => void
}
class ViewerBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false }
  static getDerivedStateFromError() {
    return { failed: true }
  }
  render() {
    return this.state.failed ? (
      <p role="alert">模型解析或 WebGL 初始化失败，请重新获取资源。</p>
    ) : (
      this.props.children
    )
  }
}
const views = [
  { id: 'model', label: '三维模型', icon: Box },
  { id: 'image', label: '检查图片', icon: Image },
  { id: 'video', label: '火灾视频', icon: Video },
] as const
const noPoints: PreviewPoint[] = []
export function RoomPreview({
  modelUrl,
  imageUrl,
  videoUrl,
  points = noPoints,
  onPointSelect,
  onResetView,
}: RoomPreviewProps) {
  const [view, setView] = useState('model')
  const [reset, setReset] = useState(0)
  const [retry, setRetry] = useState(0)
  const [modelStatus, setModelStatus] = useState<'loading' | 'ready' | 'error'>('loading')
  const [trace, setTrace] = useState<string>()
  const [mediaError, setMediaError] = useState(false)
  const [alignment, setAlignment] = useState('')
  const [fullError, setFullError] = useState('')
  const root = useRef<HTMLElement>(null)
  const url = view === 'model' ? modelUrl : view === 'image' ? imageUrl : videoUrl
  useEffect(() => {
    let active = true
    if (url)
      void fetch(url, { method: 'HEAD' })
        .then((r) => {
          if (!active) return
          const id = r.headers.get('X-Trace-ID')
          if (id && /^[A-Za-z0-9_.:-]{1,96}$/.test(id)) setTrace(id)
          setModelStatus(r.ok ? 'ready' : 'error')
        })
        .catch(() => {
          if (active) setModelStatus('error')
        })
    return () => {
      active = false
    }
  }, [url, retry])
  return (
    <section className="preview" ref={root}>
      <div className="preview-toolbar">
        <div className="segmented" aria-label="预览内容">
          {views.map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              aria-pressed={view === id}
              onClick={() =>
                recorder.record('preview_tab', () => {
                  if (view === id) return
                  setModelStatus('loading')
                  setTrace(undefined)
                  setView(id)
                  setMediaError(false)
                })
              }
            >
              <Icon size={15} />
              {label}
            </button>
          ))}
        </div>
        <Button
          variant="ghost"
          disabled={!url}
          onClick={() => {
            recorder.record('view_fullscreen')
            if (document.fullscreenElement) void document.exitFullscreen()
            else
              void root.current
                ?.requestFullscreen()
                .catch(() => setFullError('浏览器未允许全屏，请检查权限。'))
          }}
        >
          <Maximize size={14} />
          全屏
        </Button>
      </div>
      <div className="viewport">
        {!url ? (
          <div className="viewport-content">
            <h2>
              {view === 'model'
                ? '三维模型待接入'
                : view === 'image'
                  ? '房间检查图片待接入'
                  : '已生成视频待接入'}
            </h2>
            <p>请先连接并选择已登记的真实资源。</p>
          </div>
        ) : modelStatus === 'loading' ? (
          <p role="status">正在检查资源可达性…</p>
        ) : modelStatus === 'error' ? (
          <div className="viewport-content" role="alert">
            <h2>资源读取失败</h2>
            <p>请检查 MinIO 隧道后重新获取。</p>
            {trace && <code>追踪编号：{trace}</code>}
          </div>
        ) : view === 'model' ? (
          <ViewerBoundary key={modelUrl + '-' + retry}>
            <Suspense fallback={<p role="status">正在加载三维组件…</p>}>
              <ModelCanvas
                url={modelUrl!}
                points={points}
                reset={reset}
                onReady={setAlignment}
                onPointSelect={(id) => {
                  recorder.record('point_select')
                  onPointSelect?.(id)
                }}
              />
            </Suspense>
          </ViewerBoundary>
        ) : mediaError ? (
          <div role="alert">媒体读取失败，请检查资源连接并重新获取。</div>
        ) : view === 'image' ? (
          <img
            key={imageUrl + '-' + retry}
            className="room-image"
            src={imageUrl}
            alt="服务器已登记的房间检查图"
            onError={() => setMediaError(true)}
          />
        ) : (
          <video
            key={videoUrl + '-' + retry}
            aria-label="已有火灾视频"
            controls
            preload="metadata"
            src={videoUrl}
            onError={() => setMediaError(true)}
          />
        )}
      </div>
      <div className="preview-controls">
        <span>
          {view === 'model'
            ? alignment || '鼠标旋转 · 右键平移 · 滚轮缩放'
            : '已归档成果，只读查看'}
        </span>
        <Button
          variant="ghost"
          disabled={!modelUrl || modelStatus !== 'ready' || view !== 'model'}
          onClick={() =>
            recorder.record('view_reset', () => {
              setReset((n) => n + 1)
              onResetView?.()
            })
          }
        >
          <RotateCcw size={14} />
          视角复位
        </Button>
        <Button
          variant="ghost"
          disabled={!url}
          onClick={() =>
            recorder.record('media_retry', () => {
              setModelStatus('loading')
              setTrace(undefined)
              setRetry((n) => n + 1)
              setMediaError(false)
            })
          }
        >
          <RefreshCw size={14} />
          重新获取
        </Button>
        {videoUrl && view === 'video' && (
          <a className="ui-button button-outline" href={videoUrl} download="Room8-V1.mp4">
            下载视频
          </a>
        )}
      </div>
      {fullError && <p role="alert">{fullError}</p>}
    </section>
  )
}
