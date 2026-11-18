import { afterEach, it, expect, vi } from 'vitest'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import { Context, empty } from './context'
import { SpatialPanel } from './SpatialPanel'
afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})
// Synthetic contract inputs, not Room8 evidence.
const source = {
  scene_code: 'fixture-scene',
  room_id: 'Room8',
  database_room_id: 1,
  layout_version_id: 1,
  asset_version: 'fixture-version',
}
const hash = 'a'.repeat(64)
const props = {
  ...empty,
  source,
  spatialEnabled: true,
  assets: [{ id: 1, kind: 'room_glb', sha256: hash, size_bytes: 1, uploaded: true }],
  points: [
    { device: 22, x: 1, y: 1, z: 0, review_kind: 'interior' },
    { device: 32, x: 0, y: 0, z: 0, review_kind: 'boundary' },
  ],
  jobs: [
    {
      job_id: 'fixture-job',
      runtime_state: 'awaiting_visual_review',
      technical_complete: true,
      preset: 'final',
      asset_version: source.asset_version,
    },
  ],
}
const data = {
  scene_code: source.scene_code,
  room_id: 'Room8',
  asset_version: source.asset_version,
  file_job_id: 'fixture-job',
  verified: true,
  verification_scope: 'file_consistency_only',
  source: { glb_sha256: hash },
  boundary: {
    polygon_raw_xy: [
      [0, 0],
      [2, 0],
      [2, 2],
      [0, 2],
    ],
    floor_z: -1.35,
  },
  members: { interior: [22], boundary: [32] },
  ignition: { device: 22, position_raw_xyz: [1, 1, 0] },
}
it('未批准时不访问新接口；摘要与GLB和点位一致才绘制，换版本立即移除旧图', async () => {
  const fetcher = vi.fn(async () => new Response(JSON.stringify(data)))
  vi.stubGlobal('fetch', fetcher)
  const { rerender } = render(
    <Context.Provider value={{ ...props, spatialEnabled: false }}>
      <SpatialPanel />
    </Context.Provider>,
  )
  expect(fetcher).not.toHaveBeenCalled()
  rerender(
    <Context.Provider value={props}>
      <SpatialPanel />
    </Context.Provider>,
  )
  await screen.findByRole('img', { name: '已核验Room8边界与真实点位' })
  expect(screen.getByText(/历史起火点22/)).toBeDefined()
  rerender(
    <Context.Provider value={{ ...props, source: { ...source, asset_version: 'other' } }}>
      <SpatialPanel />
    </Context.Provider>,
  )
  expect(screen.queryByRole('img')).toBeNull()
})
it('拒绝错误GLB指纹，不展示猜测边界', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn(
      async () => new Response(JSON.stringify({ ...data, source: { glb_sha256: 'b'.repeat(64) } })),
    ),
  )
  render(
    <Context.Provider value={props}>
      <SpatialPanel />
    </Context.Provider>,
  )
  await waitFor(() => expect(screen.getByRole('alert').textContent).toContain('拒绝绘制'))
  expect(screen.queryByRole('img')).toBeNull()
})
