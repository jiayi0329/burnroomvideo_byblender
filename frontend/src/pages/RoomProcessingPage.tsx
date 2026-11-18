import { Link } from 'react-router-dom'
import { ArrowRight, Scissors, Ruler, FileBox, Map } from 'lucide-react'
import { PageHeading } from '@/components/PageHeading'
import { Button } from '@/components/ui/button'
import { useResources } from '@/features/resources/context'
import { SpatialPanel } from '@/features/resources/SpatialPanel'
export function RoomProcessingPage() {
  const r = useResources()
  return (
    <>
      <PageHeading
        number="02"
        title="房间处理工作台"
        description="从全屋扫描提取独立空间，保留几何、材质与核验证据。"
      >
        <Button disabled>
          <Scissors size={15} />
          发起房间裁切 · 待接入
        </Button>
      </PageHeading>
      <div className="processing-layout">
        <section className="panel">
          <div className="panel-heading">
            <h2>
              <Map size={17} />
              户型与扫描点位
            </h2>
            <span className="badge">{r.spatialEnabled ? '只读核验' : '待接入'}</span>
          </div>
          <div className="processing-toolbar">
            <label htmlFor="room-select">选择房间</label>
            <select
              id="room-select"
              disabled={!r.sources.length}
              value={r.source ? r.sources.indexOf(r.source) : ''}
              onChange={(e) => r.select(Number(e.target.value))}
            >
              {r.sources.length ? (
                r.sources.map((source, index) => (
                  <option key={index} value={index}>
                    {source.scene_code} / {source.room_id} / 户型 {source.layout_version_id}
                  </option>
                ))
              ) : (
                <option value="">请先连接场景与核验数据</option>
              )}
            </select>
          </div>
          <SpatialPanel />
          <div className="info-note">
            <p>展示已登记的Room8成果；本轮不重新裁切或执行自动高度检测。</p>
          </div>
        </section>
        <div className="processing-aside">
          <section className="panel">
            <div className="panel-heading">
              <h2>
                <Ruler size={17} />
                高度与空间判定
              </h2>
            </div>
            <dl className="data-list">
              {['地板候选高度', '顶面候选高度', '净高 / 置信度', '人工核验结论'].map((x) => (
                <div key={x}>
                  <dt>{x}</dt>
                  <dd>待接入</dd>
                </div>
              ))}
            </dl>
            <p className="panel-note">自动高度判定尚未实现，不将工程近似值当作自动检测结果。</p>
          </section>
          <section className="panel">
            <div className="panel-heading">
              <h2>
                <FileBox size={17} />
                独立资产与验证
              </h2>
            </div>
            {['基础 BLEND', '浏览器 GLB', '房间检查图', '技术验证报告'].map((name) => (
              <div className="asset-row" key={name}>
                <span>{name}</span>
                <span className="badge">
                  {r.assets.some(
                    (a) =>
                      a.uploaded &&
                      a.kind ===
                        (
                          {
                            '基础 BLEND': 'room_blend',
                            '浏览器 GLB': 'room_glb',
                            房间检查图: 'room_preview',
                          } as Record<string, string>
                        )[name],
                  )
                    ? '已上传登记'
                    : '接口未提供'}
                </span>
              </div>
            ))}
            <p className="panel-note">资产版本与验证状态由真实登记数据提供。</p>
          </section>
        </div>
      </div>
      <section className="entry-card">
        <div className="entry-number">下一步</div>
        <div>
          <h3>进入火灾模拟工作台</h3>
          <p>预览三维交互结构与参数草稿，保留原始房间及 R3 基线。</p>
        </div>
        <Button asChild variant="outline">
          <Link to="/simulation">
            打开模拟工作台 <ArrowRight size={15} />
          </Link>
        </Button>
      </section>
    </>
  )
}
