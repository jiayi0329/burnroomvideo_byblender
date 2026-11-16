import { Box, MapPin, ChevronRight, Info } from 'lucide-react'
import { PageHeading } from '@/components/PageHeading'
import { RoomPreview } from '@/features/room-preview/RoomPreview'
import { ParameterPanel } from '@/features/simulation/ParameterPanel'
import { TaskMonitor } from '@/components/TaskMonitor'
export function SimulationPage() {
  return (
    <>
      <PageHeading
        number="03"
        title="火灾模拟工作台"
        description="在独立空间中预览、配置并追踪火灾演示。当前仅提供本地交互。"
      />
      <div className="simulation-layout">
        <aside className="room-navigation panel">
          <div className="panel-heading">
            <h2>
              <Box size={16} />
              空间导航
            </h2>
          </div>
          <div className="room-context">
            <span className="eyebrow">当前场景</span>
            <strong>待连接场景</strong>
            <span className="badge">资源未接入</span>
          </div>
          <div className="room-nav-label">房间列表</div>
          <div className="room-nav-empty">
            <Box size={17} />
            <div>
              待加载房间<small>由已核验资源决定</small>
            </div>
            <ChevronRight size={13} />
          </div>
          <div className="room-nav-label">扫描点位</div>
          <div className="points-empty">
            <MapPin size={22} />
            <p>有效点位待接入</p>
            <small>仅允许选择房间内部有效点</small>
          </div>
          <div className="room-guidance">
            <Info size={15} />
            <p>首个接入对象为 Room8。界面按场景与资产版本组织，可扩展其他已核验房间。</p>
          </div>
        </aside>
        <div className="simulation-center">
          <RoomPreview />
          <TaskMonitor />
        </div>
        <ParameterPanel />
      </div>
    </>
  )
}
