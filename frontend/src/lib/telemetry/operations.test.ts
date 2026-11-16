import { describe, it, expect, vi } from 'vitest'
import { createRecorder } from './operations'
describe('本地事件契约', () => {
  it('关联时间、结果和耗时，不将事件正文或敏感异常写入日志', () => {
    const sink = vi.fn()
    const recorder = createRecorder(sink)
    const sensitive = new Error('Authorization=secret https://private/?signature=secret')
    recorder.record('draft_change')
    expect(() =>
      recorder.record('draft_reset', () => {
        throw sensitive
      }),
    ).toThrow(sensitive)
    const events = sink.mock.calls.map((c) => c[0])
    expect(events[0]).toMatchObject({
      schema_version: 1,
      operation: 'draft_change',
      stage: 'browser',
      result: 'success',
    })
    expect(events[1]).toMatchObject({ result: 'failure', error_code: 'LOCAL_OPERATION_FAILED' })
    expect(events[0].trace_id).not.toBe(events[1].trace_id)
    expect(Number.isNaN(Date.parse(events[0].ts))).toBe(false)
    expect(events[0].duration_ms).toBeGreaterThanOrEqual(0)
    expect(JSON.stringify(events)).not.toMatch(/secret|Authorization|signature/)
    expect(recorder.delivery).toBe('not_connected')
  })
  it('日志传输失败不影响本地操作，默认不发送网络请求', () => {
    const operation = vi.fn()
    createRecorder(() => {
      throw Error('offline')
    }).record('draft_change', operation)
    expect(operation).toHaveBeenCalledOnce()
    expect(() => createRecorder().record('navigate')).not.toThrow()
  })
})
