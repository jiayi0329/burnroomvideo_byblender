import { useEffect, useState } from 'react'
import { ApiError, createApiClient, type RequestEvent } from '@/lib/api/client'
import { jobs, type Job } from '@/features/resources/contracts'
export function useJob(scene: string | null, jobId: string | null) {
  const [value, setValue] = useState<{
      job?: Job
      error?: string
      trace?: RequestEvent
      loading: boolean
      key?: string
    }>({ loading: false }),
    [retry, setRetry] = useState(0)
  useEffect(() => {
    if (
      !scene ||
      !jobId ||
      !/^[-A-Za-z0-9_]{1,96}$/.test(scene) ||
      !/^[-A-Za-z0-9_]{1,96}$/.test(jobId)
    )
      return
    let disposed = false
    let timer: ReturnType<typeof setTimeout> | undefined
    const controller = new AbortController()
    let trace: RequestEvent | undefined
    const api = createApiClient({
      enabled: true,
      sink: (event) => {
        trace = event
      },
    })
    async function poll() {
      try {
        const response = await api.read(
          `/api/room-jobs/${jobId}?scene_code=${encodeURIComponent(scene!)}`,
          { signal: controller.signal },
        )
        const job = jobs({ jobs: [response] })[0]
        if (job.job_id !== jobId || job.scene_code !== scene) throw Error('namespace')
        if (disposed) return
        setValue({ job, loading: false, trace, key: `${scene}/${jobId}` })
        if (['created', 'preparing', 'rendering', 'encoding'].includes(job.runtime_state))
          timer = setTimeout(() => void poll(), 3000)
      } catch (e) {
        if (!disposed)
          setValue((old) => ({
            ...old,
            loading: false,
            error: e instanceof ApiError ? e.message : '任务响应格式异常',
            trace,
          }))
      }
    }
    queueMicrotask(() => {
      if (!disposed) {
        setValue({ loading: true, key: `${scene}/${jobId}` })
        void poll()
      }
    })
    return () => {
      disposed = true
      controller.abort()
      clearTimeout(timer)
    }
  }, [scene, jobId, retry])
  return {
    ...(value.key === `${scene}/${jobId}` ? value : { loading: Boolean(jobId) }),
    refresh: () => setRetry((n) => n + 1),
  }
}
