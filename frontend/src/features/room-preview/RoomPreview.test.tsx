import { afterEach, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { RoomPreview } from './RoomPreview'
afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})
it('媒体读取失败显示安全追踪号，手动重取成功，切换资源不保留旧错误', async () => {
  let failed = true
  const fetcher = vi.fn(
    async () =>
      new Response(null, {
        status: failed ? 502 : 200,
        headers: { 'X-Trace-ID': 'test-media-trace' },
      }),
  )
  vi.stubGlobal('fetch', fetcher)
  const { rerender } = render(<RoomPreview imageUrl="/room-assets/1" />)
  fireEvent.click(screen.getByRole('button', { name: '检查图片' }))
  await waitFor(() => expect(screen.getByRole('alert').textContent).toContain('test-media-trace'))
  failed = false
  fireEvent.click(screen.getByRole('button', { name: '重新获取' }))
  await screen.findByRole('img', { name: '服务器已登记的房间检查图' })
  expect(screen.queryByRole('alert')).toBeNull()
  rerender(<RoomPreview imageUrl="/room-assets/2" />)
  await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(3))
  expect((screen.getByRole('img') as HTMLImageElement).getAttribute('src')).toBe('/room-assets/2')
  expect(fetcher.mock.calls.length).toBe(3)
})
