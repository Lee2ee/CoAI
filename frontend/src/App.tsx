import { BrowserRouter, Routes, Route, Navigate, Link, useLocation } from 'react-router-dom'
import { BarChart2, LogOut, Home, KeyRound, Settings } from 'lucide-react'
import { useAuthStore } from './store/auth'
import LoginPage from './pages/LoginPage'
import DashboardPage from './pages/DashboardPage'
import BacktestPage from './pages/BacktestPage'
import ExchangePage from './pages/ExchangePage'
import SettingsPage from './pages/SettingsPage'
import TickerBar from './components/Dashboard/TickerBar'

function Layout({ children }: { children: React.ReactNode }) {
  const { logout, user } = useAuthStore()
  const location = useLocation()

  return (
    <div className="min-h-screen flex flex-col">
      <header className="bg-surface-800 border-b border-surface-700">
        <div className="max-w-7xl mx-auto px-4 h-14 flex items-center justify-between">
          <div className="flex items-center gap-6">
            <span className="font-bold text-slate-100 text-lg">CoAI</span>
            <nav className="flex gap-1">
              <NavLink to="/" label="대시보드" icon={<Home size={15} />} active={location.pathname === '/'} />
              <NavLink to="/backtest" label="백테스트" icon={<BarChart2 size={15} />} active={location.pathname === '/backtest'} />
              <NavLink to="/exchange" label="거래소" icon={<KeyRound size={15} />} active={location.pathname === '/exchange'} />
              <NavLink to="/settings" label="설정" icon={<Settings size={15} />} active={location.pathname === '/settings'} />
            </nav>
          </div>
          <div className="flex items-center gap-3">
            <span className="text-sm text-slate-400">{user?.username}</span>
            <button
              onClick={logout}
              className="flex items-center gap-1.5 text-slate-400 hover:text-slate-200 text-sm transition-colors"
            >
              <LogOut size={15} />
              로그아웃
            </button>
          </div>
        </div>
      </header>

      <TickerBar />

      <main className="flex-1 max-w-7xl mx-auto w-full px-4 py-5">
        {children}
      </main>
    </div>
  )
}

function NavLink({ to, label, icon, active }: {
  to: string; label: string; icon: React.ReactNode; active: boolean
}) {
  return (
    <Link
      to={to}
      className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm transition-colors ${
        active ? 'bg-brand-500/20 text-brand-400' : 'text-slate-400 hover:text-slate-200'
      }`}
    >
      {icon}
      {label}
    </Link>
  )
}

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { token } = useAuthStore()
  return token ? <>{children}</> : <Navigate to="/login" replace />
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/" element={<ProtectedRoute><Layout><DashboardPage /></Layout></ProtectedRoute>} />
        <Route path="/backtest" element={<ProtectedRoute><Layout><BacktestPage /></Layout></ProtectedRoute>} />
        <Route path="/exchange" element={<ProtectedRoute><Layout><ExchangePage /></Layout></ProtectedRoute>} />
        <Route path="/settings" element={<ProtectedRoute><Layout><SettingsPage /></Layout></ProtectedRoute>} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  )
}
