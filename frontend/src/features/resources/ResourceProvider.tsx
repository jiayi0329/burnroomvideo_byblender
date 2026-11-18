import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react'
import { Context, empty } from './context'
import { ApiError, createApiClient } from '@/lib/api/client'
import { assets, jobs, points, sources, type Source } from './contracts'
import { recorder } from '@/lib/telemetry/operations'
const read = createApiClient({ enabled: true })
const identity = (s: Source) =>
  [s.scene_code, s.room_id, s.layout_version_id, s.asset_version].join('/')
export function ResourceProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState(empty)
  const version = useRef(0)
  const active = useRef<AbortController | null>(null)
  const load = useCallback(async (key?: string) => {
    active.current?.abort()
    const controller = new AbortController()
    active.current = controller
    const signal = controller.signal
    const generation = ++version.current
    setState((old) => ({
      ...old,
      status: 'loading',
      stale: Boolean(old.source),
      error: undefined,
      traceId: undefined,
    }))
    try {
      const response = await fetch('/local-service/status', {
        signal: AbortSignal.any([signal, AbortSignal.timeout(10000)]),
      })
      if (!response.ok) throw Error('config')
      const config = (await response.json()) as {
        configured?: boolean
        test_submit_enabled?: boolean
        spatial_context_enabled?: boolean
      }
      if (typeof config.configured !== 'boolean') throw Error('config')
      if (!config.configured) {
        if (generation === version.current && !signal.aborted) setState(empty)
        return
      }
      const options = await read.read<{
        render_enabled?: boolean
        camera_modes?: string[]
        room_ids?: string[]
        style_presets?: string[]
        presets?: {
          test?: { duration_seconds?: number; fps?: number; resolution?: number[]; stage?: string }
        }
      }>('/api/room-jobs/options', { signal })
      const all = sources(await read.read('/api/room-jobs/sources', { signal }))
      const source = key ? all.find((s) => identity(s) === key) : all[0]
      if (key && !source) throw Error('source_removed')
      if (!source) {
        if (generation === version.current && !signal.aborted)
          setState({
            ...empty,
            status: 'connected',
            sources: all,
            lastUpdated: new Date().toISOString(),
          })
        return
      }
      const [a, p, j] = await Promise.all([
        read.read(`/api/catalog/rooms/${source.database_room_id}/assets`, { signal }),
        read.read(`/api/catalog/rooms/${source.database_room_id}/points`, { signal }),
        read.read(`/api/room-jobs?scene_code=${encodeURIComponent(source.scene_code)}&limit=100`, {
          signal,
        }),
      ])
      if (generation === version.current && !signal.aborted)
        setState({
          ...empty,
          status: 'connected',
          sources: all,
          source,
          assets: assets(a),
          points: points(p),
          jobs: jobs(j),
          submitEnabled: config.test_submit_enabled === true,
          spatialEnabled: config.spatial_context_enabled === true,
          renderEnabled:
            options.render_enabled === true &&
            options.room_ids?.includes('Room8') === true &&
            options.style_presets?.includes('r3') === true &&
            options.presets?.test?.duration_seconds === 4 &&
            options.presets.test.fps === 12 &&
            options.presets.test.stage === 'short' &&
            JSON.stringify(options.presets.test.resolution) === '[960,540]',
          allowedCameras: (options.camera_modes ?? []).filter(
            (v): v is 'overview' | 'closeup' => v === 'overview' || v === 'closeup',
          ),
          lastUpdated: new Date().toISOString(),
        })
    } catch (error) {
      if (generation === version.current && !signal.aborted)
        setState((old) => ({
          ...old,
          status: 'error',
          stale: Boolean(old.source),
          error:
            error instanceof ApiError
              ? error.message
              : '读取失败或所选版本已不可用，请检查连接后重新获取。',
          traceId: error instanceof ApiError ? error.traceId : undefined,
        }))
    }
  }, [])
  useEffect(() => {
    let mounted = true
    queueMicrotask(() => {
      if (mounted) void load()
    })
    return () => {
      mounted = false
      active.current?.abort()
    }
  }, [load])
  return (
    <Context.Provider
      value={{
        ...state,
        refresh: () => {
          recorder.record('resource_refresh')
          void load(state.source ? identity(state.source) : undefined)
        },
        select: (index) => {
          const source = state.sources[index]
          if (!source) return
          recorder.record('resource_select')
          void load(identity(source))
        },
      }}
    >
      {children}
    </Context.Provider>
  )
}
