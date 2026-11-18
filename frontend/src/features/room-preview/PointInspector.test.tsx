import { afterEach, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { PointInspector } from './PointInspector'
afterEach(cleanup)
const fixture = [
  { device: 12, x: 1, y: 2, z: 3, review_kind: 'interior' },
  { device: 32, x: 4, y: 5, z: 6, review_kind: 'doorway' },
]
it('只读选择真实传入点，显示原始与GLB坐标并明确不是起火点设置', () => {
  const onSelect = vi.fn()
  const { rerender } = render(<PointInspector points={fixture} onSelect={onSelect} />)
  fireEvent.change(screen.getByLabelText('查看扫描点位'), { target: { value: '12' } })
  expect(onSelect).toHaveBeenCalledWith('12')
  rerender(<PointInspector points={fixture} selectedId="12" onSelect={onSelect} />)
  expect(screen.getByText('1.000 / 2.000 / 3.000')).toBeTruthy()
  expect(screen.getByText('1.000 / 3.000 / -2.000')).toBeTruthy()
  expect(screen.getByText(/不是火焰底座/)).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: '取消选择' }))
  expect(onSelect).toHaveBeenLastCalledWith(undefined)
})
it('空点位及已移除的选择不伪造结果', () => {
  render(<PointInspector points={[]} selectedId="99" onSelect={() => {}} />)
  expect((screen.getByLabelText('查看扫描点位') as HTMLSelectElement).disabled).toBe(true)
  expect(screen.getByText(/未选择任何起火点/)).toBeTruthy()
})
it('显示真实算法归属而不冒充人工核验', () => {
  render(
    <PointInspector
      points={[{ device: 0, x: 1, y: 2, z: 3, review_kind: null, algorithm_status: 'interior' }]}
      selectedId="0"
      onSelect={() => {}}
    />,
  )
  expect(screen.getAllByText(/内部点（算法归属）/).length).toBeGreaterThan(0)
})
