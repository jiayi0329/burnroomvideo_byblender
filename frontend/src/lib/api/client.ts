import type { OperationEvent } from '@/lib/telemetry/operations'

export class ApiError extends Error {
  code: 'NOT_CONNECTED' | 'NETWORK_ERROR' | 'HTTP_ERROR' | 'INVALID_RESPONSE'
  traceId: string
  requestId?: string
  constructor(code: ApiError['code'], traceId: string, requestId?: string) {
    super(
      {
        NOT_CONNECTED: '真实接口待接入',
        NETWORK_ERROR: '网络连接失败，请先查询原任务，勿重复提交',
        HTTP_ERROR: '服务端返回错误，请凭追踪编号排查',
        INVALID_RESPONSE: '服务端响应格式异常',
      }[code],
    )
    this.code = code
    this.traceId = traceId
    this.requestId = requestId
  }
}
export interface RequestEvent {
  trace_id: string
  request_id?: string
  ts: string
  operation: 'api_read'
  stage: 'http'
  result: OperationEvent['result']
  duration_ms: number
  error_code?: ApiError['code']
}
export function createApiClient(
  options: { enabled?: boolean; fetcher?: typeof fetch; sink?: (event: RequestEvent) => void } = {},
) {
  return {
    async read<T>(path: string): Promise<T> {
      const traceId = crypto.randomUUID()
      // Explicitly read-only allowlist. No legacy API, submission, arbitrary URL or credential forwarding.
      if (
        !options.enabled ||
        !/^\/api\/(room-jobs(?:[/?]|$)|catalog\/)/.test(path) ||
        path.includes('..') ||
        path.includes('://') ||
        path.includes('\\')
      )
        throw new ApiError('NOT_CONNECTED', traceId)
      const start = performance.now()
      let requestId: string | undefined
      let failure: ApiError | undefined
      try {
        const response = await (options.fetcher ?? fetch)(path, {
          headers: { 'X-Trace-ID': traceId },
          credentials: 'same-origin',
        })
        const incoming = response.headers.get('X-Request-ID')
        requestId = incoming && /^[A-Za-z0-9_.:-]{1,96}$/.test(incoming) ? incoming : undefined
        if (!response.ok) throw new ApiError('HTTP_ERROR', traceId, requestId)
        try {
          return (await response.json()) as T
        } catch {
          throw new ApiError('INVALID_RESPONSE', traceId, requestId)
        }
      } catch (error) {
        failure =
          error instanceof ApiError ? error : new ApiError('NETWORK_ERROR', traceId, requestId)
        throw failure
      } finally {
        try {
          options.sink?.({
            trace_id: traceId,
            request_id: requestId,
            ts: new Date().toISOString(),
            operation: 'api_read',
            stage: 'http',
            result: failure ? 'failure' : 'success',
            duration_ms: Math.max(0, performance.now() - start),
            ...(failure ? { error_code: failure.code } : {}),
          })
        } catch {
          /* Do not alter the request result. */
        }
      }
    },
  }
}
export const api = createApiClient()
