import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { AppShell } from './App'
import { StatusPanel } from '@/components/StatusPanel'
afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})
function open(path = '/scenes') {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AppShell />
    </MemoryRouter>,
  )
}
describe('中文前端业务骨架', () => {
  it('四页导航完整且不触发真实请求', () => {
    const fetcher = vi.fn()
    vi.stubGlobal('fetch', fetcher)
    open()
    for (const title of ['房间处理工作台', '火灾模拟工作台', '任务与成果中心', '场景资源库']) {
      fireEvent.click(screen.getByRole('link', { name: new RegExp(title) }))
      expect(screen.getByRole('heading', { name: title, level: 1 })).toBeTruthy()
    }
    expect(fetcher).not.toHaveBeenCalled()
  })
  it('参数可修改、越界提示、重置；正式预设限制近景并禁用提交', () => {
    open('/simulation')
    const value = screen.getByRole('spinbutton', { name: '火焰持续时间数值' }) as HTMLInputElement
    fireEvent.change(value, { target: { value: '75' } })
    expect(value.value).toBe('75')
    fireEvent.change(value, { target: { value: '101' } })
    expect(screen.getByRole('alert').textContent).toContain('0–100')
    fireEvent.change(screen.getByLabelText('相机'), { target: { value: 'closeup' } })
    fireEvent.change(screen.getByLabelText('质量预设'), { target: { value: 'final' } })
    expect((screen.getByLabelText('相机') as HTMLSelectElement).value).toBe('overview')
    expect(
      (screen.getByRole('option', { name: '近景（closeup）' }) as HTMLOptionElement).disabled,
    ).toBe(true)
    fireEvent.click(screen.getByRole('button', { name: /重置演示草稿/ }))
    expect(value.value).toBe('50')
    expect(screen.queryByRole('alert')).toBeNull()
    expect((screen.getByRole('button', { name: /开始渲染/ }) as HTMLButtonElement).disabled).toBe(
      true,
    )
  })
  it('媒体切换不生成模型和视频；任务区不伪造进度', () => {
    open('/simulation')
    fireEvent.click(screen.getByRole('button', { name: '火灾视频' }))
    expect(screen.getByRole('heading', { name: '已生成视频待接入' })).toBeTruthy()
    expect(document.querySelector('video,canvas,progress')).toBeNull()
    expect(screen.getByText('尚未连接任务')).toBeTruthy()
  })
  it('统一错误显示安全摘要与追踪信息，支持所有资源状态', () => {
    const { rerender } = render(
      <StatusPanel
        state="error"
        title="视频加载失败"
        description="请凭追踪编号排查"
        traceId="trace-safe"
        jobId="job-safe"
      />,
    )
    expect(screen.getByRole('alert').textContent).toContain('trace-safe')
    expect(screen.getByRole('alert').textContent).toContain('job-safe')
    for (const state of ['unconnected', 'loading', 'empty', 'success'] as const) {
      rerender(<StatusPanel state={state} title="资源状态" />)
      expect(screen.getByRole('status')).toBeTruthy()
    }
  })
  it('未知路由回到资源库', () => {
    open('/missing')
    expect(screen.getByRole('heading', { level: 1, name: '场景资源库' })).toBeTruthy()
  })
})
