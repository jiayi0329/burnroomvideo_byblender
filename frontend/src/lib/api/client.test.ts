import { describe, expect, it, vi } from 'vitest'
import { createApiClient } from './client'
describe('只读请求适配边界', () => {
  it('默认不调用真实服务，拒绝旧API和外部地址', async () => {
    const fetcher = vi.fn()
    await expect(createApiClient({ fetcher }).read('/api/room-jobs/options')).rejects.toMatchObject(
      { code: 'NOT_CONNECTED' },
    )
    for (const path of [
      '/api/render/scene',
      'https://private/api/room-jobs',
      '/api/room-jobs/../render',
    ]) {
      await expect(createApiClient({ enabled: true, fetcher }).read(path)).rejects.toMatchObject({
        code: 'NOT_CONNECTED',
      })
    }
    expect(fetcher).not.toHaveBeenCalled()
  })
  it('只读请求关联追踪编号，每次请求独立；不记录路径、正文或签名', async () => {
    const fetcher = vi
      .fn()
      .mockImplementation(
        async () =>
          new Response(JSON.stringify({ render_enabled: false }), {
            headers: { 'X-Request-ID': 'server-request-1' },
          }),
      )
    const sink = vi.fn()
    const client = createApiClient({ enabled: true, fetcher, sink })
    expect(await client.read('/api/room-jobs/options')).toEqual({ render_enabled: false })
    await client.read('/api/room-jobs/options')
    expect(sink.mock.calls[0][0]).toMatchObject({
      request_id: 'server-request-1',
      stage: 'http',
      result: 'success',
    })
    expect(sink.mock.calls[0][0].trace_id).not.toBe(sink.mock.calls[1][0].trace_id)
    expect(fetcher.mock.calls[0][1].headers['X-Trace-ID']).toBe(sink.mock.calls[0][0].trace_id)
    expect(JSON.stringify(sink.mock.calls)).not.toContain('/api/')
  })
  it('网络超时不会重试或泄漏错误正文', async () => {
    const fetcher = vi.fn().mockRejectedValue(Error('Authorization secret signed-url'))
    const sink = vi.fn()
    await expect(
      createApiClient({ enabled: true, fetcher, sink }).read('/api/room-jobs/options'),
    ).rejects.toMatchObject({ code: 'NETWORK_ERROR' })
    expect(fetcher).toHaveBeenCalledOnce()
    expect(JSON.stringify(sink.mock.calls)).not.toMatch(/secret|signed-url|Authorization/)
  })
  it('HTTP失败和非法JSON转换为安全错误', async () => {
    for (const [response, code] of [
      [new Response('private error body', { status: 503 }), 'HTTP_ERROR'],
      [new Response('not json'), 'INVALID_RESPONSE'],
    ] as const) {
      const sink = vi.fn()
      await expect(
        createApiClient({ enabled: true, fetcher: vi.fn().mockResolvedValue(response), sink }).read(
          '/api/room-jobs/options',
        ),
      ).rejects.toMatchObject({ code })
      expect(sink.mock.calls[0][0]).toMatchObject({ result: 'failure', error_code: code })
      expect(JSON.stringify(sink.mock.calls)).not.toContain('private')
    }
  })
})
