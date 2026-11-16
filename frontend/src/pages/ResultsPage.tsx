import { Activity, Download, FileText, Film, ListFilter, Cable, Fingerprint } from 'lucide-react'
import { PageHeading } from '@/components/PageHeading'
import { Button } from '@/components/ui/button'
import { StatusPanel } from '@/components/StatusPanel'
import { TaskMonitor } from '@/components/TaskMonitor'
export function ResultsPage() {
  return (
    <>
      <PageHeading
        number="04"
        title="任务与成果中心"
        description="把运行过程、配置与视频交付关联起来，让每次演示可追溯。"
      >
        <Button variant="outline" disabled>
          <Download size={15} />
          下载成果 · 待接入
        </Button>
      </PageHeading>
      <div className="results-layout">
        <section className="panel history-panel">
          <div className="panel-heading">
            <h2>
              <Activity size={17} />
              任务历史
            </h2>
            <span className="badge">待接入</span>
          </div>
          <div className="filter-row">
            <ListFilter size={15} />
            <label htmlFor="task-filter">任务筛选</label>
            <select id="task-filter" disabled>
              <option>连接后按真实状态筛选</option>
            </select>
          </div>
          <StatusPanel
            title="任务目录未连接"
            description="不会自动启动任务，也不会生成演示任务记录。"
          />
          <div className="history-footnote">技术完成与人工审核状态将分别展示。</div>
        </section>
        <div className="results-main">
          <section className="panel">
            <div className="panel-heading">
              <h2>
                <Film size={17} />
                视频成果
              </h2>
              <span className="badge">未选择任务</span>
            </div>
            <StatusPanel
              title="视频来源待接入"
              description="选择已有真实任务后，提供播放、拖动与下载；不自动生成新视频。"
            />
            <div className="result-actions">
              <Button variant="outline" disabled>
                <FileText size={14} />
                任务配置
              </Button>
              <Button variant="outline" disabled>
                <FileText size={14} />
                运行报告
              </Button>
              <Button disabled>
                <Download size={14} />
                下载视频
              </Button>
            </div>
          </section>
          <TaskMonitor />
          <section className="panel">
            <div className="panel-heading">
              <h2>
                <Fingerprint size={17} />
                追踪与接口日志
              </h2>
              <span className="badge">待接入</span>
            </div>
            <dl className="data-list">
              {[
                ['任务编号', '尚未连接任务'],
                ['请求 / 追踪编号', '无真实请求'],
                ['GPU 运行摘要', '待接入'],
                ['前端事件接收与存储', '待接入'],
              ].map(([k, v]) => (
                <div key={k}>
                  <dt>{k}</dt>
                  <dd>{v}</dd>
                </div>
              ))}
            </dl>
            <div className="info-note">
              <Cable size={16} />
              <p>
                前端事件契约与请求适配层已预留，尚未连接可信后端接收、存储和查询接口；当前没有持久化操作日志。
              </p>
            </div>
            <div className="result-actions">
              <Button variant="outline" disabled>
                授权日志查询 · 待接入
              </Button>
            </div>
            <p className="panel-note">
              服务异常时显示脱敏错误与追踪编号。网络超时需先核对原任务，避免重复提交。
            </p>
          </section>
        </div>
      </div>
    </>
  )
}
