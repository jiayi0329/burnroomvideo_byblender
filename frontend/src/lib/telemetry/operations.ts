/** Browser contract only. No persistent log, console sink, server endpoint or raw payload. */
export type Action = 'navigate' | 'preview_tab' | 'draft_change' | 'draft_reset'
export interface OperationEvent {
  schema_version: 1
  trace_id: string
  ts: string
  operation: Action
  stage: 'browser'
  result: 'success' | 'failure'
  duration_ms: number
  error_code?: 'LOCAL_OPERATION_FAILED'
}
export type EventSink = (event: OperationEvent) => void
export interface Recorder {
  record: (action: Action, task?: () => void) => void
  delivery: 'not_connected'
}
export function createRecorder(sink?: EventSink): Recorder {
  return {
    delivery: 'not_connected',
    record(action, task) {
      const start = performance.now()
      const base = {
        schema_version: 1 as const,
        trace_id: crypto.randomUUID(),
        ts: new Date().toISOString(),
        operation: action,
        stage: 'browser' as const,
      }
      let failed = false
      try {
        task?.()
      } catch (error) {
        failed = true
        throw error
      } finally {
        const event: OperationEvent = {
          ...base,
          result: failed ? 'failure' : 'success',
          duration_ms: Math.max(0, performance.now() - start),
          ...(failed ? { error_code: 'LOCAL_OPERATION_FAILED' as const } : {}),
        }
        try {
          sink?.(event)
        } catch {
          /* Delivery cannot change the local operation result. */
        }
      }
    },
  }
}
export const recorder = createRecorder()
