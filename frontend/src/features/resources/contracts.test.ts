import { describe, it, expect } from 'vitest'
import { assets, sources, points, jobs, glbPoint, pointCategory, pointLabel } from './contracts'
import { allowedApiPath, requestLog } from '../../../local/readonly-proxy'
describe('只读资源边界', () => {
  it('人工归属优先，算法归属明确标记，缺失分类不猜测', () => {
    const point = { device: 0, x: 1, y: 2, z: 3, review_kind: null, algorithm_status: 'interior' }
    expect(pointCategory(point)).toBe('interior')
    expect(pointLabel(point)).toBe('内部点（算法归属）')
    expect(pointCategory({ ...point, review_kind: 'doorway' })).toBe('doorway')
    expect(pointLabel({ ...point, review_kind: 'doorway' })).toBe('门口点')
    expect(pointCategory({ ...point, review_kind: 'excluded' })).toBe('other')
    expect(pointCategory({ ...point, algorithm_status: undefined })).toBe('other')
    expect(() => points({ points: [{ ...point, algorithm_status: 13 }] })).toThrow()
  })
  it('拒绝错误身份和任意媒体地址，不混淆业务号与数据库主键', () => {
    expect(() =>
      sources({ sources: [{ scene_code: 'scene', room_id: 'Room8', database_room_id: '6' }] }),
    ).toThrow()
    expect(() =>
      assets({ assets: [{ id: 1, kind: 'room_glb', uploaded: true, sha256: 'wrong' }] }),
    ).toThrow()
    expect(() =>
      jobs({
        jobs: [{ job_id: 'job', runtime_state: 'done', video_url: 'https://elsewhere/video' }],
      }),
    ).toThrow()
    expect(() =>
      points({ points: [{ device: 1, x: NaN, y: 2, z: 3, review_kind: 'interior' }] }),
    ).toThrow()
  })
  it('原始XYZ转换一次到GLB坐标，不变换模型本身', () => {
    expect(glbPoint({ device: 1, x: 2, y: 3, z: 4, review_kind: 'interior' })).toEqual([2, 4, -3])
  })
  it('只允许新版读取路由，日志无路径、凭证或签名字段', () => {
    expect(allowedApiPath('/api/render/scene')).toBe(false)
    expect(allowedApiPath('/api/catalog/assets/60/share')).toBe(false)
    expect(allowedApiPath('/api/room-jobs/options')).toBe(true)
    expect(allowedApiPath('/api/room-jobs/job-1/spatial-context')).toBe(true)
    expect(allowedApiPath('/api/room-jobs/job-1/arbitrary-file')).toBe(false)
    const log = requestLog('trace-test', false, 12)
    expect(log).toMatchObject({
      schema_version: 1,
      trace_id: 'trace-test',
      event: 'failure',
      duration_ms: 12,
    })
    for (const field of ['url', 'headers', 'body']) expect(log).not.toHaveProperty(field)
    expect(JSON.stringify(log)).not.toMatch(/Authorization|signature|http:\/\//)
  })
})
