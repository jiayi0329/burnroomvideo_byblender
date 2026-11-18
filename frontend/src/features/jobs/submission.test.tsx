import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { render, screen, fireEvent, cleanup, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { Context, empty } from '@/features/resources/context'
import { TestSubmissionPanel } from './TestSubmissionPanel'
import { testPayload, submitTest, restoreSubmission, submissionSlot } from './submission'
import { validateTestBody, requestLog } from '../../../local/readonly-proxy'
beforeEach(() => {
  const values = new Map<string, string>()
  Object.defineProperty(window, 'localStorage', {
    configurable: true,
    value: {
      getItem: (key: string) => values.get(key) ?? null,
      setItem: (key: string, value: string) => values.set(key, value),
      clear: () => values.clear(),
    },
  })
})
afterEach(() => {
  cleanup()
  window.localStorage.clear()
  vi.unstubAllGlobals()
})
const source = {
  scene_code: 'fixture-scene',
  room_id: 'Room8',
  database_room_id: 1,
  asset_version: 'fixture-version',
  layout_version_id: 1,
}
it('只构造test白名单，代理拒绝正式档与自由参数', () => {
  const payload = testPayload(source, 'overview')
  expect(validateTestBody(payload)).toEqual(payload)
  for (const change of [
    { preset: 'final' },
    { fire_density: 50 },
    { confirm_render: false },
    { camera_mode: 'evil' },
  ])
    expect(() => validateTestBody({ ...payload, ...change })).toThrow()
})
it('提交代理日志只关联真实上游ID与耗时，不含正文、幂等键或签名', () => {
  const log = requestLog('fixture-trace', true, 12, 'POST', 'fixture-request', 'fixture-job')
  expect(log).toMatchObject({
    operation: 'frontend.test_submit',
    stage: 'http',
    trace_id: 'fixture-trace',
    request_id: 'fixture-request',
    job_id: 'fixture-job',
    duration_ms: 12,
    event: 'success',
  })
  expect(requestLog('fixture-trace', false, 1, 'POST')).not.toHaveProperty('request_id')
  expect(JSON.stringify(log)).not.toMatch(/Authorization|signature|headers|body|Idempotency/)
})
it('响应不明保留原键，不自动重试；人工复用原键得到真实返回ID', async () => {
  const pending = { key: 'fixture-key-01', payload: testPayload(source, 'overview') },
    failed = vi.fn().mockRejectedValue(Error('private error'))
  await expect(submitTest(pending, failed)).rejects.toMatchObject({ ambiguous: true })
  expect(failed).toHaveBeenCalledOnce()
  expect(restoreSubmission()?.key).toBe(pending.key)
  const accepted = vi
    .fn()
    .mockResolvedValue(
      new Response(
        JSON.stringify({ job_id: 'fixture-job', scene_code: source.scene_code, room_id: 'Room8' }),
        { status: 202, headers: { 'X-Request-ID': 'actual-fixture-request' } },
      ),
    )
  const result = await submitTest(restoreSubmission()!, accepted)
  expect(result.request_id).toBe('actual-fixture-request')
  expect(result.job_id).toBe('fixture-job')
  expect(accepted.mock.calls[0][1].headers['Idempotency-Key']).toBe(pending.key)
})
it('未批准时按钮禁用；明确确认后快速重复点击仅产生一次POST', async () => {
  let release: (v: Response) => void = () => {}
  const fetcher = vi.fn(
    (_input: RequestInfo | URL, _init?: RequestInit) =>
      new Promise<Response>((resolve) => {
        release = resolve
      }),
  )
  vi.stubGlobal('fetch', fetcher)
  const props = {
    ...empty,
    status: 'connected' as const,
    source,
    submitEnabled: false,
    renderEnabled: true,
    allowedCameras: ['overview' as const],
  }
  const { rerender } = render(
    <MemoryRouter>
      <Context.Provider value={props}>
        <TestSubmissionPanel />
      </Context.Provider>
    </MemoryRouter>,
  )
  expect(
    (screen.getByRole('button', { name: '确认并提交测试渲染' }) as HTMLButtonElement).disabled,
  ).toBe(true)
  rerender(
    <MemoryRouter>
      <Context.Provider value={{ ...props, submitEnabled: true }}>
        <TestSubmissionPanel />
      </Context.Provider>
    </MemoryRouter>,
  )
  fireEvent.click(screen.getByRole('checkbox'))
  const button = screen.getByRole('button', { name: '确认并提交测试渲染' })
  fireEvent.click(button)
  fireEvent.click(button)
  expect(fetcher).toHaveBeenCalledOnce()
  expect(JSON.parse(fetcher.mock.calls[0]?.[1]?.body as string).preset).toBe('test')
  release(
    new Response(
      JSON.stringify({ job_id: 'fixture-job', scene_code: source.scene_code, room_id: 'Room8' }),
      { status: 202 },
    ),
  )
  await waitFor(() =>
    expect(JSON.parse(window.localStorage.getItem(submissionSlot)!).job_id).toBe('fixture-job'),
  )
})
