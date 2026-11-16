import { BrowserRouter, Navigate, NavLink, Route, Routes, useLocation } from 'react-router-dom'
import {
  Flame,
  Layers3,
  ScanLine,
  FolderKanban,
  Cable,
  ShieldCheck,
  ChevronRight,
} from 'lucide-react'
import { SceneLibraryPage } from '@/pages/SceneLibraryPage'
import { RoomProcessingPage } from '@/pages/RoomProcessingPage'
import { SimulationPage } from '@/pages/SimulationPage'
import { ResultsPage } from '@/pages/ResultsPage'
import { recorder } from '@/lib/telemetry/operations'
import { ResourceProvider } from '@/features/resources/ResourceProvider'
import { useResources } from '@/features/resources/context'
import { Button } from '@/components/ui/button'

const navigation = [
  { to: '/scenes', title: '场景资源库', subtitle: '数据与资产', icon: Layers3, number: '01' },
  {
    to: '/processing',
    title: '房间处理工作台',
    subtitle: '空间提取与核验',
    icon: ScanLine,
    number: '02',
  },
  { to: '/simulation', title: '火灾模拟工作台', subtitle: '预览与参数', icon: Flame, number: '03' },
  {
    to: '/results',
    title: '任务与成果中心',
    subtitle: '过程与交付',
    icon: FolderKanban,
    number: '04',
  },
]
export function AppShell() {
  const resources = useResources()
  const location = useLocation()
  const current = navigation.find((n) => n.to === location.pathname) ?? navigation[0]
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <NavLink to="/scenes" className="brand" aria-label="火灾可视化平台首页">
          <div className="brand-mark">
            <Flame size={25} />
          </div>
          <div>
            <strong>火灾可视化平台</strong>
            <small>空间 · 火灾 · 可视化</small>
          </div>
        </NavLink>
        <div className="sidebar-section">
          工作空间 <span>前端第一阶段</span>
        </div>
        <nav aria-label="主导航">
          {navigation.map(({ to, title, subtitle, icon: Icon, number }) => (
            <NavLink
              to={to}
              key={to}
              onClick={() => recorder.record('navigate')}
              className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}
            >
              <Icon size={19} />
              <div>
                <strong>{title}</strong>
                <small>{subtitle}</small>
              </div>
              <span>{number}</span>
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <ShieldCheck size={18} />
          <div>
            <strong>基线保护</strong>
            <small>不改写原始资产与 R3 配置</small>
          </div>
        </div>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <div className="breadcrumb">
            工作空间 <ChevronRight size={13} />
            <span>{current.title}</span>
          </div>
          <div className="connection">
            <span className="dot" />
            <Cable size={14} />
            {
              {
                unconfigured: '真实服务未配置',
                loading: '正在读取真实服务…',
                connected: '真实服务已连接 · 只读',
                error: '真实服务读取失败',
              }[resources.status]
            }
            <Button
              variant="ghost"
              disabled={resources.status === 'loading'}
              onClick={resources.refresh}
            >
              重新获取
            </Button>
            <span className="topbar-divider" />
            本地开发
          </div>
        </header>
        <main>
          <Routes>
            <Route path="/" element={<Navigate to="/scenes" replace />} />
            <Route path="/scenes" element={<SceneLibraryPage />} />
            <Route path="/processing" element={<RoomProcessingPage />} />
            <Route path="/simulation" element={<SimulationPage />} />
            <Route path="/results" element={<ResultsPage />} />
            <Route path="*" element={<Navigate to="/scenes" replace />} />
          </Routes>
          <footer className="page-footer">
            <span>燃境 BurnScape · 实验室科研原型</span>
            <span>程序化视觉演示，非 CFD 火灾动力学仿真</span>
          </footer>
        </main>
      </div>
    </div>
  )
}
export default function App() {
  return (
    <BrowserRouter>
      <ResourceProvider>
        <AppShell />
      </ResourceProvider>
    </BrowserRouter>
  )
}
