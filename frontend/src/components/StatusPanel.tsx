import { CircleDashed, AlertTriangle, LoaderCircle, CheckCircle2, Inbox } from 'lucide-react'
import type { ResourceState } from '@/lib/api/contracts'

export function StatusPanel({
  state = 'unconnected',
  title = '真实数据待接入',
  description = '连接后将展示服务器的实际结果。',
  traceId,
  jobId,
}: {
  state?: ResourceState
  title?: string
  description?: string
  traceId?: string
  jobId?: string
}) {
  const Icon = {
    unconnected: CircleDashed,
    loading: LoaderCircle,
    empty: Inbox,
    error: AlertTriangle,
    success: CheckCircle2,
  }[state]
  return (
    <div className={`status-panel state-${state}`} role={state === 'error' ? 'alert' : 'status'}>
      <Icon size={25} aria-hidden="true" />
      <strong>{title}</strong>
      <p>{description}</p>
      {traceId && <code>追踪编号：{traceId}</code>}
      {jobId && <code>任务编号：{jobId}</code>}
    </div>
  )
}
