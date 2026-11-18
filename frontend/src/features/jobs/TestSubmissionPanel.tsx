import { useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useResources } from '@/features/resources/context'
import {
  testPayload,
  restoreSubmission,
  submitTest,
  SubmissionError,
  type PendingSubmission,
} from './submission'
import { Button } from '@/components/ui/button'
export function TestSubmissionPanel() {
  const r = useResources(),
    navigate = useNavigate()
  const [camera, setCamera] = useState('overview'),
    [confirmed, setConfirmed] = useState(false),
    [busy, setBusy] = useState(false),
    [pending, setPending] = useState<PendingSubmission | undefined>(restoreSubmission),
    [error, setError] = useState<SubmissionError>()
  const lock = useRef(false)
  const uncertain = pending && !pending.job_id ? pending : undefined
  const effectiveCamera = uncertain?.payload.camera_mode ?? camera
  const sameSource =
    !uncertain ||
    (uncertain.payload.scene_code === r.source?.scene_code &&
      uncertain.payload.asset_version === r.source?.asset_version &&
      uncertain.payload.layout_version_id === r.source?.layout_version_id)
  const allowed =
    sameSource &&
    r.allowedCameras.includes(effectiveCamera as 'overview' | 'closeup') &&
    r.status === 'connected' &&
    !r.stale &&
    r.submitEnabled &&
    r.renderEnabled &&
    r.source?.room_id === 'Room8'
  async function submit() {
    if (lock.current || !allowed || !confirmed || !r.source) return
    lock.current = true
    setBusy(true)
    setError(undefined)
    try {
      const request =
        pending && !pending.job_id
          ? pending
          : { key: crypto.randomUUID(), payload: testPayload(r.source, camera) }
      setPending(request)
      const result = await submitTest(request)
      setPending(result)
      navigate(
        `/results?scene=${encodeURIComponent(result.payload.scene_code)}&job=${result.job_id}`,
      )
    } catch (e) {
      setError(
        e instanceof SubmissionError
          ? e
          : new SubmissionError('本地提交准备或存储失败，未确认结果，请检查原请求。', true),
      )
    } finally {
      setBusy(false)
      lock.current = false
    }
  }
  return (
    <section className="panel test-submission">
      <div className="panel-heading">
        <h2>受控GPU测试短片</h2>
        <span className="badge">仅 test / R3</span>
      </div>
      <div className="parameter-body">
        <p className="tiny muted">
          4秒 · 960×540 · 12帧/秒 · 48帧。起火点沿用冻结配置，不使用0–100演示滑块。
        </p>
        <label className="field">
          测试机位
          <select
            aria-label="测试机位"
            value={effectiveCamera}
            disabled={busy || Boolean(pending && !pending.job_id)}
            onChange={(e) => {
              setCamera(e.target.value)
              setConfirmed(false)
            }}
          >
            {(r.allowedCameras ?? ['overview']).map((c) => (
              <option key={c} value={c}>
                {c === 'overview' ? '总览' : '近景'}（{c}）
              </option>
            ))}
          </select>
        </label>
        <dl className="data-list">
          <div>
            <dt>场景/房间</dt>
            <dd>{r.source ? `${r.source.scene_code} / ${r.source.room_id}` : '未选择'}</dd>
          </div>
          <div>
            <dt>资产版本</dt>
            <dd>
              {pending && !pending.job_id
                ? pending.payload.asset_version
                : (r.source?.asset_version ?? '未选择')}
            </dd>
          </div>
        </dl>
        {!allowed && (
          <p role="status" className="tiny muted">
            真实提交未获批准或服务未就绪。需部署窗口和单次GPU验收分别批准后启用。
          </p>
        )}
        {pending && !pending.job_id && (
          <p role="alert">
            存在原提交键。继续操作将复用其原配置和原键，可能确认既有任务，也可能首次创建；请先检查任务历史，不要换键重发。
          </p>
        )}
        <label className="confirmation">
          <input
            type="checkbox"
            checked={confirmed}
            disabled={!allowed || busy}
            onChange={(e) => setConfirmed(e.target.checked)}
          />
          我已核对以上配置，确认提交一个独立测试任务（原V1不覆盖）。
        </label>
        <Button disabled={!allowed || !confirmed || busy} onClick={() => void submit()}>
          {busy
            ? '正在等待任务受理…'
            : pending && !pending.job_id
              ? '确认复用原键核对提交'
              : '确认并提交测试渲染'}
        </Button>
        {error && (
          <div role="alert">
            <p>{error.message}</p>
            {error.traceId && <code>trace_id：{error.traceId}</code>}
            {error.requestId && <p>request_id：{error.requestId}</p>}
          </div>
        )}
        <p>
          <Link to="/results">查看已有任务及提交结果 →</Link>
        </p>
      </div>
    </section>
  )
}
