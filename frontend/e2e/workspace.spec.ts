import { test, expect } from '@playwright/test'

test('四个中文页面桌面/窄屏访问，无真实API请求或横向溢出', async ({ page }) => {
  const apiRequests: string[] = []
  const errors: string[] = []
  page.on('pageerror', (e) => errors.push(e.message))
  await page.route('**/api/**', (route) => {
    apiRequests.push(route.request().url())
    return route.abort()
  })
  for (const width of [1440, 390]) {
    await page.setViewportSize({ width, height: 1000 })
    for (const [path, title] of [
      ['scenes', '场景资源库'],
      ['processing', '房间处理工作台'],
      ['simulation', '火灾模拟工作台'],
      ['results', '任务与成果中心'],
    ]) {
      await page.goto(`/${path}`)
      await expect(page).toHaveTitle('基于三维场景的火灾可视化与视频生成平台')
      await expect(
        page.getByRole('link', { name: '基于三维场景的火灾可视化与视频生成平台首页' }),
      ).toBeVisible()
      if (path === 'scenes') {
        await expect(page.getByRole('region', { name: '项目说明' })).toContainText('实验室科研原型')
        await expect(page.getByRole('region', { name: '项目说明' })).toContainText('Room8 是已验证的演示样例')
      }
      await expect(page.getByRole('heading', { level: 1, name: title })).toBeVisible()
      expect(
        await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
      ).toBe(true)
      if (path === 'simulation')
        await page.screenshot({ path: `test-results/模拟工作台-${width}.png`, fullPage: true })
    }
  }
  expect(errors).toEqual([])
  expect(apiRequests).toEqual([])
})

test('实际浏览器草稿交互、中文错误、预览切换与导航', async ({ page }) => {
  await page.goto('/simulation')
  const value = page.getByRole('spinbutton', { name: '火焰持续时间数值' })
  await value.fill('75')
  await expect(value).toHaveValue('75')
  await value.fill('101')
  await expect(page.getByRole('alert')).toContainText('0–100')
  await page.getByRole('button', { name: '重置演示草稿' }).click()
  await expect(value).toHaveValue('50')
  await expect(page.getByRole('alert')).toHaveCount(0)
  await page.getByLabel('质量预设').selectOption('final')
  await expect(page.getByLabel('相机')).toHaveValue('overview')
  await expect(page.getByRole('button', { name: '开始渲染 · 待接入' })).toBeDisabled()
  await page.getByRole('button', { name: '火灾视频', exact: true }).click()
  await expect(page.getByRole('heading', { name: '已生成视频待接入' })).toBeVisible()
  await page.getByRole('link', { name: /任务与成果中心/ }).click()
  await expect(page).toHaveURL(/\/results$/)
  await page.screenshot({ path: 'test-results/任务与成果中心.png', fullPage: true })
})
