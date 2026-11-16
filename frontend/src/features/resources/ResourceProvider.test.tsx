import { afterEach, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { ResourceProvider } from './ResourceProvider'
import { useResources } from './context'
afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})
// Synthetic fixtures are isolated test inputs, never shipped as service data.
const a = {
  scene_code: 'test-scene',
  room_id: 'Room8',
  database_room_id: 1,
  layout_version_id: 1,
  asset_version: 'asset-A',
}
const b = { ...a, database_room_id: 2, asset_version: 'asset-B' }
function Readout() {
  const r = useResources()
  return (
    <>
      <span data-testid="state">{r.status}</span>
      <span data-testid="version">{r.source?.asset_version}</span>
      <span data-testid="stale">{String(r.stale)}</span>
      <time data-testid="updated">{r.lastUpdated}</time>
      <button onClick={r.refresh}>刷新测试</button>
    </>
  )
}
it('刷新失败保留上次已核验数据和时间，恢复后按身份选同一版本而非列表下标', async () => {
  let failed = false
  let reversed = false
  const fetcher = vi.fn(async (input: RequestInfo | URL) => {
    const path = String(input)
    if (path === '/local-service/status') return new Response(JSON.stringify({ configured: true }))
    if (failed) return new Response('private failure details', { status: 503 })
    const body = path.endsWith('/options')
      ? {}
      : path.endsWith('/sources')
        ? { sources: reversed ? [b, a] : [a, b] }
        : path.includes('/assets')
          ? { assets: [] }
          : path.includes('/points')
            ? { points: [] }
            : { jobs: [] }
    return new Response(JSON.stringify(body))
  })
  vi.stubGlobal('fetch', fetcher)
  render(
    <ResourceProvider>
      <Readout />
    </ResourceProvider>,
  )
  await waitFor(() => expect(screen.getByTestId('state').textContent).toBe('connected'))
  const timestamp = screen.getByTestId('updated').textContent
  failed = true
  fireEvent.click(screen.getByText('刷新测试'))
  await waitFor(() => expect(screen.getByTestId('state').textContent).toBe('error'))
  expect(screen.getByTestId('version').textContent).toBe('asset-A')
  expect(screen.getByTestId('stale').textContent).toBe('true')
  expect(screen.getByTestId('updated').textContent).toBe(timestamp)
  failed = false
  reversed = true
  fireEvent.click(screen.getByText('刷新测试'))
  await waitFor(() => expect(screen.getByTestId('state').textContent).toBe('connected'))
  expect(screen.getByTestId('version').textContent).toBe('asset-A')
  expect(screen.getByTestId('stale').textContent).toBe('false')
})
it('缺少服务配置时不读取业务API', async () => {
  const fetcher = vi.fn(async () => new Response(JSON.stringify({ configured: false })))
  vi.stubGlobal('fetch', fetcher)
  render(
    <ResourceProvider>
      <Readout />
    </ResourceProvider>,
  )
  await waitFor(() => expect(fetcher).toHaveBeenCalledOnce())
  expect(fetcher.mock.calls[0]?.length).toBeGreaterThan(0)
  expect(screen.getByTestId('state').textContent).toBe('unconfigured')
})
