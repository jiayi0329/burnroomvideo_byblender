import { test, expect } from '@playwright/test'
import { createHash } from 'node:crypto'

test('真实已有V1任务恢复、播放拖动Range与下载（不依赖MinIO隧道）', async ({ page, request }) => {
  const errors: string[] = [],
    writes: string[] = []
  page.on('pageerror', (e) => errors.push(e.message))
  page.on('console', (m) => {
    if (m.type() === 'error') errors.push(m.text())
  })
  page.on('request', (r) => {
    if (new URL(r.url()).pathname.startsWith('/api/') && !['GET', 'HEAD'].includes(r.method()))
      writes.push(r.method())
  })
  const response = await request.get('/api/room-jobs/sources')
  expect(response.ok()).toBe(true)
  const { sources } = await response.json()
  const source = sources.find((s: { room_id: string }) => s.room_id === 'Room8')
  expect(source).toBeTruthy()
  const history = await request.get(`/api/room-jobs?scene_code=${source.scene_code}&limit=100`)
  const { jobs } = await history.json()
  const v1 = jobs.find((j: { job_id: string }) => j.job_id === '20261105T040552Z_91f5fb7d')
  expect(v1?.video_available).toBe(true)
  await page.goto(`/results?scene=${source.scene_code}&job=${v1.job_id}`)
  const video = page.getByLabel('归档任务视频')
  await expect
    .poll(() => video.evaluate((v: HTMLVideoElement) => v.readyState), { timeout: 20000 })
    .toBeGreaterThanOrEqual(2)
  expect(await video.evaluate((v: HTMLVideoElement) => v.duration)).toBeCloseTo(24, 0)
  await video.evaluate(async (v: HTMLVideoElement) => {
    v.muted = true
    await v.play()
  })
  await expect.poll(() => video.evaluate((v: HTMLVideoElement) => v.currentTime)).toBeGreaterThan(0)
  await video.evaluate((v: HTMLVideoElement) => {
    v.pause()
    v.currentTime = 12
  })
  await expect
    .poll(() =>
      video.evaluate((v: HTMLVideoElement) => Math.abs(v.currentTime - 12) < 0.5 && !v.seeking),
    )
    .toBe(true)
  const range = await request.get(v1.video_url, { headers: { Range: 'bytes=0-0' } })
  expect(range.status()).toBe(206)
  expect((await range.body()).length).toBe(1)
  const bytes = await request.get(v1.video_url)
  expect(bytes.status()).toBe(200)
  expect(
    createHash('sha256')
      .update(await bytes.body())
      .digest('hex'),
  ).toBe('c339c91d12709797b43989c680474286e5b2641a64de160d3fde7902267404dd')
  await page.reload()
  await expect(page.getByLabel('归档任务视频')).toBeVisible()
  const download = page.waitForEvent('download')
  await page.getByRole('link', { name: '下载已有视频' }).click()
  expect(await (await download).failure()).toBeNull()
  await page.getByLabel('归档任务视频').evaluate(async (v: HTMLVideoElement) => {
    v.muted = true
    v.currentTime = 0
    await v.play()
  })
  await expect
    .poll(() => page.getByLabel('归档任务视频').evaluate((v: HTMLVideoElement) => v.ended), {
      timeout: 35000,
      intervals: [500],
    })
    .toBe(true)
  expect(errors).toEqual([])
  expect(writes).toEqual([])
})
test('真实Room8 GLB、点位、检查图与原V1视频只读验收', async ({ page, request }) => {
  const errors: string[] = []
  const writes: string[] = []
  page.on('pageerror', (e) => errors.push(e.message))
  page.on('console', (message) => {
    if (message.type() === 'error') errors.push(message.text())
  })
  page.on('request', (r) => {
    if (new URL(r.url()).pathname.startsWith('/api/') && !['GET', 'HEAD'].includes(r.method()))
      writes.push(r.method())
  })
  const sourceResponse = await request.get('/api/room-jobs/sources')
  expect(sourceResponse.ok()).toBe(true)
  const { sources } = await sourceResponse.json()
  const source = sources.find((s: { room_id: string }) => s.room_id === 'Room8')
  expect(source).toBeTruthy()
  const catalog = await request.get(`/api/catalog/rooms/${source.database_room_id}/assets`)
  const { assets } = await catalog.json()
  const glb = assets.find((a: { kind: string }) => a.kind === 'room_glb')
  const raw = await request.get(`/room-assets/${glb.id}`)
  expect(raw.status()).toBe(200)
  expect(
    createHash('sha256')
      .update(await raw.body())
      .digest('hex'),
  ).toBe(glb.sha256)
  await page.goto('/simulation')
  await expect(page.getByText('真实服务已连接 · 只读', { exact: false })).toBeVisible({
    timeout: 20000,
  })
  await expect(page.getByText(/个点位在模型包围盒内/)).toBeVisible({ timeout: 30000 })
  const pointResponse = await request.get(`/api/catalog/rooms/${source.database_room_id}/points`)
  const { points } = await pointResponse.json()
  const point = points[0]
  await page.getByLabel('查看扫描点位').selectOption(String(point.device))
  await expect(page.getByRole('region', { name: '点位信息' })).toContainText(
    [point.x, point.y, point.z].map((v: number) => v.toFixed(3)).join(' / '),
  )
  await page.getByText('资源版本与来源', { exact: true }).click()
  await expect(page.locator('.resource-provenance')).toContainText(source.asset_version)
  await expect(page.locator('.resource-provenance')).toContainText(glb.sha256)
  const canvas = page.locator('canvas')
  await expect(canvas).toBeVisible()
  const before = await canvas.screenshot()
  const box = await canvas.boundingBox()
  expect(box).toBeTruthy()
  await page.mouse.move(box!.x + box!.width / 2, box!.y + box!.height / 2)
  await page.mouse.down()
  await page.mouse.move(box!.x + box!.width / 2 + 160, box!.y + box!.height / 2 + 40, { steps: 15 })
  await page.mouse.up()
  await page.mouse.wheel(0, 180)
  await page.waitForTimeout(800)
  const after = await canvas.screenshot()
  expect(before.equals(after)).toBe(false)
  await page.mouse.move(box!.x + box!.width / 2, box!.y + box!.height / 2)
  await page.mouse.down({ button: 'right' })
  await page.mouse.move(box!.x + box!.width / 2 + 80, box!.y + box!.height / 2 + 40, { steps: 10 })
  await page.mouse.up({ button: 'right' })
  await page.waitForTimeout(600)
  expect(after.equals(await canvas.screenshot())).toBe(false)
  await page.getByRole('button', { name: '视角复位', exact: true }).click()
  await page.waitForTimeout(800)
  await page.getByRole('button', { name: '全屏', exact: true }).click()
  await expect.poll(() => page.evaluate(() => Boolean(document.fullscreenElement))).toBe(true)
  await page.evaluate(() => document.exitFullscreen())
  await page.screenshot({ path: 'test-results/真实Room8-GLB-点位.png', fullPage: true })
  await page.getByRole('button', { name: '检查图片', exact: true }).click()
  const image = page.getByRole('img', { name: '服务器已登记的房间检查图' })
  await expect
    .poll(() => image.evaluate((el: HTMLImageElement) => el.naturalWidth))
    .toBeGreaterThan(0)
  for (const asset of assets.filter((a: { kind: string }) => a.kind === 'room_preview')) {
    await page.getByLabel('检查图片', { exact: true }).selectOption(String(asset.id))
    await expect
      .poll(() => image.evaluate((el: HTMLImageElement) => el.naturalWidth))
      .toBeGreaterThan(0)
    const picture = await request.get('/room-assets/' + asset.id)
    expect(picture.ok()).toBe(true)
    expect(
      createHash('sha256')
        .update(await picture.body())
        .digest('hex'),
    ).toBe(asset.sha256)
  }
  await page.getByRole('button', { name: '火灾视频', exact: true }).click()
  const video = page.getByLabel('已有火灾视频')
  await expect
    .poll(() => video.evaluate((v: HTMLVideoElement) => v.readyState))
    .toBeGreaterThanOrEqual(2)
  expect(await video.evaluate((v: HTMLVideoElement) => v.duration)).toBeCloseTo(24, 0)
  await video.evaluate((v: HTMLVideoElement) => {
    v.currentTime = 12
  })
  await expect
    .poll(() =>
      video.evaluate((v: HTMLVideoElement) => Math.abs(v.currentTime - 12) < 0.5 && !v.seeking),
    )
    .toBe(true)
  const history = await request.get(`/api/room-jobs?scene_code=${source.scene_code}`)
  const { jobs } = await history.json()
  const v1 = jobs.find((j: { job_id: string }) => j.job_id === '20261105T040552Z_91f5fb7d')
  expect(v1).toBeTruthy()
  const range = await request.get(v1.video_url, { headers: { Range: 'bytes=0-0' } })
  expect(range.status()).toBe(206)
  expect((await range.body()).length).toBe(1)
  const download = await request.get(v1.video_url)
  expect(download.status()).toBe(200)
  expect(
    createHash('sha256')
      .update(await download.body())
      .digest('hex'),
  ).toBe('c339c91d12709797b43989c680474286e5b2641a64de160d3fde7902267404dd')
  await video.evaluate(async (v: HTMLVideoElement) => {
    v.muted = true
    v.currentTime = 0
    await v.play()
  })
  await expect
    .poll(() => video.evaluate((v: HTMLVideoElement) => v.ended), {
      timeout: 35000,
      intervals: [500],
    })
    .toBe(true)
  await page.screenshot({ path: 'test-results/真实Room8-V1播放.png', fullPage: true })
  const downloadEvent = page.waitForEvent('download')
  await page.getByRole('link', { name: '下载视频', exact: true }).click()
  expect(await (await downloadEvent).failure()).toBeNull()
  for (const width of [1440, 390]) {
    await page.setViewportSize({ width, height: 1000 })
    await page.goto('/simulation')
    await expect(page.getByText(/个点位在模型包围盒内/)).toBeVisible({ timeout: 20000 })
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
    ).toBe(true)
    expect(
      await page.locator('.sidebar').evaluate((el) => getComputedStyle(el).overflowY),
    ).not.toBe('auto')
    await page.screenshot({ path: `test-results/真实Room8-${width}.png`, fullPage: true })
  }
  expect(writes).toEqual([])
  expect(errors).toEqual([])
})
