import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react'
import { Context, empty } from './context'
const read = createApiClient({ enabled: true })
import { ApiError, createApiClient } from '@/lib/api/client'
import { assets, jobs, points, sources } from './contracts'
import { recorder } from '@/lib/telemetry/operations'

export function ResourceProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState(empty)
  const version = useRef(0)
  const load = useCallback(async (index = 0, signal?: AbortSignal) => {
    const generation = ++version.current
    setState((old) => ({ ...old, status: 'loading', error: undefined, traceId: undefined }))
    try {
      const config = (await fetch('/local-service/status').then((r) => r.json())) as {
        configured: boolean
      }
      if (!config.configured) {
        if (generation === version.current && !signal?.aborted) setState(empty)
        return
      }
      await read.read('/api/room-jobs/options')
      const all = sources(await read.read('/api/room-jobs/sources'))
      const source = all[index] ?? all[0]
      if (!source) {
        if (generation === version.current && !signal?.aborted)
          setState({ ...empty, status: 'connected', sources: all })
        return
      }
      const [a, p, j] = await Promise.all([
        read.read(`/api/catalog/rooms/${source.database_room_id}/assets`),
        read.read(`/api/catalog/rooms/${source.database_room_id}/points`),
        read.read(`/api/room-jobs?scene_code=${encodeURIComponent(source.scene_code)}&limit=100`),
      ])
      if (generation === version.current && !signal?.aborted)
        setState({
          ...empty,
          status: 'connected',
          sources: all,
          source,
          assets: assets(a),
          points: points(p),
          jobs: jobs(j),
        })
    } catch (error) {
      if (generation === version.current && !signal?.aborted)
        setState({
          ...empty,
          status: 'error',
          error:
            error instanceof ApiError
              ? error.message
              : '读取失败或响应不符合契约，请检查连接后重新获取。',
          traceId: error instanceof ApiError ? error.traceId : undefined,
        })
    }
  }, [])
  useEffect(() => {
    const controller = new AbortController()
    queueMicrotask(() => {
      if (!controller.signal.aborted) void load(0, controller.signal)
    })
    return () => controller.abort()
  }, [load]) // Explicit refresh only; no polling or submit.
  const refresh = () => {
    recorder.record('resource_refresh')
    void load(state.source ? state.sources.indexOf(state.source) : 0)
  }
  return (
    <Context.Provider
      value={{
        ...state,
        refresh,
        select: (index) => {
          recorder.record('resource_select')
          void load(index)
        },
      }}
    >
      {children}
    </Context.Provider>
  )
}
