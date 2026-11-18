import { test, expect } from '@playwright/test'

// Isolated browser fixtures only; never evidence of a real GPU task or video.
test('离线契约：确认提交、异步任务、轮询、刷新恢复及断线停止', async ({ page }) => {
  const source = {
    scene_code: 'fixture-scene',
    room_id: 'Room8',
    database_room_id: 81,
    layout_version_id: 9,
    asset_version: 'fixture-version',
  }
  const job = {
    scene_code: source.scene_code,
    room_id: 'Room8',
    job_id: 'fixture-test-job',
    asset_version: source.asset_version,
    runtime_state: 'rendering',
    preset: 'test',
    style_preset: 'r3',
    camera_mode: 'overview',
    fps: 12,
    resolution: [960, 540],
    total_frames: 48,
    completed_frames: 3,
    technical_complete: false,
    human_acceptance: 'not_recorded',
    video_available: false,
    video_url: null,
  }
  let posts = 0,
    reads = 0,
    offline = false
  const errors: string[] = []
  page.on('pageerror', (e) => errors.push(e.message))
  await page.route('**/local-service/status', (route) =>
    route.fulfill({
      json: { configured: true, test_submit_enabled: true, spatial_context_enabled: false },
    }),
  )
  await page.route('**/api/**', async (route) => {
    const request = route.request(),
      url = new URL(request.url())
    if (request.method() === 'POST') {
      expect(url.pathname).toBe('/api/room-jobs')
      const payload = request.postDataJSON()
      expect(payload).toEqual({
        scene_code: source.scene_code,
        room_id: 'Room8',
        asset_version: source.asset_version,
        layout_version_id: 9,
        style_preset: 'r3',
        preset: 'test',
        camera_mode: 'overview',
        confirm_render: true,
      })
      expect(request.headers()['idempotency-key']).toMatch(/^[a-z0-9-]{36}$/)
      posts++
      return route.fulfill({
        status: 202,
        headers: { 'X-Request-ID': 'fixture-request' },
        json: job,
      })
    }
    if (url.pathname.endsWith('/options'))
      return route.fulfill({
        json: {
          render_enabled: true,
          camera_modes: ['overview', 'closeup'],
          room_ids: ['Room8'],
          style_presets: ['r3'],
          presets: {
            test: { stage: 'short', duration_seconds: 4, fps: 12, resolution: [960, 540] },
          },
        },
      })
    if (url.pathname.endsWith('/sources')) return route.fulfill({ json: { sources: [source] } })
    if (url.pathname.endsWith('/assets')) return route.fulfill({ json: { assets: [] } })
    if (url.pathname.endsWith('/points')) return route.fulfill({ json: { points: [] } })
    if (url.pathname === '/api/room-jobs') return route.fulfill({ json: { jobs: [] } })
    expect(url.pathname).toBe('/api/room-jobs/fixture-test-job')
    reads++
    if (offline)
      return route.fulfill({ status: 503, json: { detail: { code: 'fixture_unavailable' } } })
    return route.fulfill({ json: { ...job, completed_frames: reads > 1 ? 12 : 3 } })
  })
  await page.goto('/simulation')
  const submit = page.getByRole('button', { name: '确认并提交测试渲染' })
  await expect(submit).toBeDisabled()
  await page.getByRole('checkbox').check()
  await expect(submit).toBeEnabled()
  await submit.click()
  await expect(page).toHaveURL(/results\?scene=fixture-scene&job=fixture-test-job/)
  await expect(page.getByRole('progressbar')).toHaveAttribute('value', '3')
  await expect(page.getByRole('progressbar')).toHaveAttribute('value', '12')
  await expect(page.getByText('fixture-request', { exact: false })).toBeVisible()
  await page.reload()
  await expect(page.getByRole('progressbar')).toHaveAttribute('value', '12')
  expect(posts).toBe(1)
  offline = true
  await page.getByRole('button', { name: '重新读取任务' }).click()
  await expect(page.getByRole('alert')).toContainText('进度已停止刷新')
  const stoppedAt = reads
  await page.waitForTimeout(3300)
  expect(reads).toBe(stoppedAt)
  offline = false
  await page.getByRole('button', { name: '重新读取任务' }).click()
  await expect(page.getByRole('progressbar')).toHaveAttribute('value', '12')
  expect(posts).toBe(1)
  expect(errors).toEqual([])
})
