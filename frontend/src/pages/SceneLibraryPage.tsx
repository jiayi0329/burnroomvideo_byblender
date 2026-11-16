import { Link } from 'react-router-dom'
import {
  ArrowDownToLine,
  Upload,
  ArrowRight,
  Database,
  Box,
  Map,
  Film,
  Layers3,
} from 'lucide-react'
import { PageHeading } from '@/components/PageHeading'
import { Button } from '@/components/ui/button'
import { StatusPanel } from '@/components/StatusPanel'
export function SceneLibraryPage() {
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
          当前网页尚未接入真实模型、视频与任务服务。其余功能按实际接入状态显示，未接入功能标注“待接入”。
        </p>
      </section>
      <section className="overview-grid">
        {[
          { title: '原始扫描资源', text: '模型、材质与全景图', icon: Database },
          { title: '户型与点位', text: '对齐数据与人工核验', icon: Map },
          { title: '独立房间资产', text: 'BLEND、GLB 与检查图', icon: Box },
          { title: '视频与运行报告', text: '版本与成果关联', icon: Film },
        ].map(({ title, text, icon: Icon }) => (
          <div className="overview-card" key={title}>
            <Icon size={19} />
            <span className="badge">待接入</span>
            <h3>{title}</h3>
            <p>{text}</p>
          </div>
        ))}
      </section>
      <div className="section-title">
        <h2>场景与房间</h2>
        <span>资源目录尚未连接</span>
      </div>
      <section className="panel">
        <div className="scene-empty">
          <div className="empty-icon">
            <Layers3 size={36} strokeWidth={1.2} />
          </div>
          <div>
            <span className="eyebrow">资源目录</span>
            <h2>先连接真实场景，再开始处理</h2>
            <p>服务器的场景列表、下载状态及资产版本将在这里汇集。当前没有读取真实资源。</p>
          </div>
        </div>
        <div className="table-head">
          <span>场景 / 房间</span>
          <span>原始资源</span>
          <span>处理状态</span>
          <span>资产版本</span>
        </div>
        <StatusPanel
          title="场景列表待接入"
          description="不会将未知状态显示为“已验证”或“处理成功”。"
        />
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
