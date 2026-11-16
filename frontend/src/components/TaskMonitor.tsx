import { Activity, LockKeyhole } from 'lucide-react'
import { StatusPanel } from '@/components/StatusPanel'
export function TaskMonitor() {
  return (
    <section className="panel task-monitor">
      <div className="panel-heading">
        <h2>
          <Activity size={17} />
          任务监控
        </h2>
        <span className="badge">待接入</span>
      </div>
      <div className="pipeline" aria-label="目标处理流程，不代表任务进度">
        {['任务准备', 'GPU 渲染', '视频编码', '完整性核验'].map((name, i) => (
          <div key={name}>
            <span>{String(i + 1).padStart(2, '0')}</span>
            {name}
          </div>
        ))}
      </div>
      <StatusPanel
        title="尚未连接任务"
        description="阶段、完成帧数、实际耗时与错误将在连接真实任务后显示。"
      />
      <div className="monitor-footer">
        <LockKeyhole size={13} />
        提交入口未开启，不创建任务、不自动重试
      </div>
    </section>
  )
}
