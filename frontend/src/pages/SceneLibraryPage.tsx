import { Link } from 'react-router-dom'
import { ArrowDownToLine, Upload, ArrowRight } from 'lucide-react'
import { PageHeading } from '@/components/PageHeading'
import { Button } from '@/components/ui/button'
import { StatusPanel } from '@/components/StatusPanel'
import { useResources } from '@/features/resources/context'
export function SceneLibraryPage() {
  const r = useResources()
  return (
    <>
      <PageHeading
        number="01"
        title="场景资源库"
        description="组织扫描数据与房间资产，让每一步处理都有清晰的来源。"
      >
        <Button variant="outline" disabled>
          <Upload size={15} />
          导入模型 · 待接入
        </Button>
        <Button disabled>
          <ArrowDownToLine size={15} />
          下载场景 · 待接入
        </Button>
      </PageHeading>
      <section className="info-note prototype-note" aria-label="项目说明">
        <p>
          当前为实验室科研原型。Room8 是已验证的演示样例，其验证依据来自既有服务器成果；
          其余功能按实际接入状态显示；当前只读查看，不创建渲染任务。
        </p>
      </section>
      <div className="section-title">
        <h2>场景与房间</h2>
        <span>已核验并登记的房间资源</span>
      </div>
      <section className="panel">
        <div className="table-head">
          <span>场景 / 房间</span>
          <span>原始资源</span>
          <span>处理状态</span>
          <span>资产版本</span>
        </div>
        {r.status === 'connected' ? (
          r.sources.length ? (
            <div className="source-list">
              {r.sources.map((source, index) => (
                <button
                  key={source.scene_code + source.asset_version}
                  className="source-row"
                  onClick={() => r.select(index)}
                >
                  <strong>
                    {source.scene_code} / {source.room_id}
                  </strong>
                  <span>已登记来源</span>
                  <span>户型版本 {source.layout_version_id}</span>
                  <code>{source.asset_version}</code>
                </button>
              ))}
              <h3>当前房间资产</h3>
              <div className="asset-list">
                {r.assets
                  .filter((a) => a.kind.startsWith('room_'))
                  .map((a) => (
                    <div className="asset-row" key={a.id}>
                      <span>{a.kind}</span>
                      <span>{(a.size_bytes / 1024).toFixed(0)} KB</span>
                      <span>{a.uploaded ? '已上传登记' : '仅本地索引'}</span>
                    </div>
                  ))}
              </div>
            </div>
          ) : (
            <StatusPanel
              state="empty"
              title="没有已登记的房间来源"
              description="仅显示服务端实际登记的数据。"
            />
          )
        ) : (
          <StatusPanel
            state={
              r.status === 'error' ? 'error' : r.status === 'loading' ? 'loading' : 'unconnected'
            }
            title={r.status === 'loading' ? '正在读取场景来源' : '资源列表暂不可用'}
            description={r.error ?? '请通过顶部连接状态检查服务。'}
            traceId={r.traceId}
          />
        )}
      </section>
      <section className="entry-card">
        <div className="entry-number">下一步</div>
        <div>
          <h3>探索房间处理流程</h3>
          <p>查看户型、房间裁切与资产核验的界面结构。Room8 为下一阶段首个接入对象。</p>
        </div>
        <Button asChild variant="outline">
          <Link to="/processing">
            进入房间处理 <ArrowRight size={15} />
          </Link>
        </Button>
      </section>
    </>
  )
}
