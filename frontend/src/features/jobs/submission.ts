import type { Source } from '@/features/resources/contracts'
export interface TestPayload {
  scene_code: string
  room_id: 'Room8'
  asset_version: string
  layout_version_id: number
  style_preset: 'r3'
  preset: 'test'
  camera_mode: 'overview' | 'closeup'
  confirm_render: true
}
export interface PendingSubmission {
  key: string
  payload: TestPayload
  job_id?: string
  trace_id?: string
  request_id?: string
  submission_trace_id?: string
}
export const submissionSlot = 'burnscape.test-submission.v1'
export function testPayload(source: Source, camera: string): TestPayload {
  if (
    !/^[A-Za-z0-9][A-Za-z0-9_-]{0,95}$/.test(source.scene_code) ||
    !/^[A-Za-z0-9][A-Za-z0-9_-]{0,95}$/.test(source.asset_version) ||
    !Number.isInteger(source.layout_version_id) ||
    source.layout_version_id < 1 ||
    source.room_id !== 'Room8' ||
    !['overview', 'closeup'].includes(camera)
  )
    throw Error('只允许Room8受控测试配置')
  return {
    scene_code: source.scene_code,
    room_id: 'Room8',
    asset_version: source.asset_version,
    layout_version_id: source.layout_version_id,
    style_preset: 'r3',
    preset: 'test',
    camera_mode: camera as TestPayload['camera_mode'],
    confirm_render: true,
  }
}
export function restoreSubmission(): PendingSubmission | undefined {
  try {
    const p = JSON.parse(window.localStorage.getItem(submissionSlot) ?? 'null')
    if (
      !p ||
      !/^[-a-zA-Z0-9_]{8,96}$/.test(p.key) ||
      !p.payload ||
      JSON.stringify(testPayload(p.payload, p.payload.camera_mode)) !== JSON.stringify(p.payload)
    )
      return
    return p
  } catch {
    return
  }
}
export class SubmissionError extends Error {
  traceId?: string
  requestId?: string
  ambiguous: boolean
  constructor(message: string, ambiguous: boolean, trace?: string, request?: string) {
    super(message)
    this.ambiguous = ambiguous
    this.traceId = trace
    this.requestId = request
  }
}
const id = (value: string | null) =>
  value && /^[A-Za-z0-9_.:-]{1,96}$/.test(value) ? value : undefined
export async function submitTest(
  pending: PendingSubmission,
  fetcher: typeof fetch = fetch,
): Promise<PendingSubmission> {
  // Persist BEFORE the request. A failed storage write must not launch a job.
  window.localStorage.setItem(submissionSlot, JSON.stringify(pending))
  const trace = crypto.randomUUID()
  let response: Response
  try {
    response = await fetcher('/api/room-jobs', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Idempotency-Key': pending.key,
        'X-Trace-ID': trace,
      },
      body: JSON.stringify(pending.payload),
      signal: AbortSignal.timeout(15000),
    })
  } catch {
    throw new SubmissionError(
      '提交响应未确认。请勿新建请求；先检查任务历史，必要时明确确认后复用原提交键。',
      true,
      trace,
    )
  }
  const traceId = id(response.headers.get('X-Trace-ID')) ?? trace,
    requestId = id(response.headers.get('X-Request-ID'))
  if (!response.ok) {
    const code = await response
      .json()
      .then((v) => v.detail?.code ?? v.code)
      .catch(() => undefined)
    const messages: Record<string, string> = {
      render_conflict_or_launcher_error: 'GPU忙碌或存在冲突任务，请查看任务中心。',
      render_conflict: 'GPU忙碌或存在冲突任务。',
      room_render_active: '已有房间渲染任务占用GPU，请到任务中心查看，禁止重复启动。',
      legacy_render_active: '服务器存在其他渲染任务，当前测试已被安全机制阻止。',
      render_submission_disabled: '服务器已关闭渲染提交入口，请等待批准窗口。',
      render_tools_unavailable: '服务器渲染工具不可用，未确认任务启动，请联系维护者核查。',
      registered_source_not_found: '所选来源已不可用，请重新获取场景，勿更换幂等键重发原请求。',
      registered_source_invalid: '已登记资产未通过后端预检，提交被拒绝。',
      catalog_unavailable: '资产目录或数据库查询不可用，提交结果请凭追踪编号核查。',
      submission_not_approved: '尚未批准真实GPU测试，提交入口关闭。',
      idempotency_key_reused_with_different_request: '提交键与原配置不一致，禁止换参数重复提交。',
    }
    throw new SubmissionError(
      messages[code] ?? `提交未成功（HTTP ${response.status}）。请凭追踪编号检查。`,
      response.status >= 500,
      traceId,
      requestId,
    )
  }
  const value = await response.json().catch(() => null)
  if (
    !value ||
    !/^[A-Za-z0-9][A-Za-z0-9_-]{0,95}$/.test(value.job_id) ||
    value.scene_code !== pending.payload.scene_code ||
    value.room_id !== 'Room8'
  )
    throw new SubmissionError('响应格式无法确认，请先核对原请求。', true, traceId, requestId)
  const result = {
    ...pending,
    job_id: value.job_id,
    trace_id: traceId,
    request_id: requestId,
    submission_trace_id: id(value.submission_trace_id ?? null),
  }
  window.localStorage.setItem(submissionSlot, JSON.stringify(result))
  return result
}
