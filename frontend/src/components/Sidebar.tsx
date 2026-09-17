import { NavLink, useLocation } from 'react-router-dom'
import {
  LayoutDashboard, Zap, FileText, Activity, Shield, LogOut, ShieldCheck,
} from 'lucide-react'
import { useAuth } from '../contexts/AuthContext'

const NAV = [
  { to: '/',        label: 'Overview',    icon: LayoutDashboard },
  { to: '/evaluate', label: 'Evaluate',   icon: Zap },
  { to: '/evidence', label: 'Evidence',   icon: FileText },
  { to: '/audit',   label: 'Audit Trail', icon: Activity },
  { to: '/policy',  label: 'Policy',      icon: Shield },
]

export default function Sidebar() {
  const { user, logout } = useAuth()
  const location = useLocation()

  return (
    <aside className="sidebar">
      <div className="sidebar-brand">
        <div className="brand-mark">
          <div className="brand-icon">
            <ShieldCheck size={18} color="#fff" />
          </div>
          <div>
            <div className="brand-name">Sentinel</div>
            <div className="brand-tag">AgentPay Trust Gateway</div>
          </div>
        </div>
      </div>

      <nav className="sidebar-nav">
        <div className="nav-section-label">Navigation</div>
        {NAV.map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            end={to === '/'}
            className={({ isActive }) => `nav-item${isActive ? ' active' : ''}`}
          >
            <Icon size={16} />
            {label}
          </NavLink>
        ))}
      </nav>

      <div className="sidebar-footer" style={{ display: 'flex', flexDirection: 'column', gap: 'var(--sp-3)' }}>
        {user && (
          <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-tertiary)', lineHeight: 1.5, padding: '0 var(--sp-2)' }}>
            <div style={{ color: 'var(--text-secondary)', fontWeight: 600, marginBottom: 2 }}>{user.name}</div>
            <div>{user.tier} · ₹{user.spending_limit_inr.toLocaleString('en-IN')} limit</div>
          </div>
        )}

        <div className="sandbox-badge">
          <span style={{ width: 6, height: 6, borderRadius: '50%', background: 'currentColor', display: 'inline-block' }} />
          Sandbox Mode
        </div>

        <button className="btn btn-ghost btn-sm w-full" onClick={logout} style={{ justifyContent: 'flex-start' }}>
          <LogOut size={14} />
          Sign out
        </button>
      </div>
    </aside>
  )
}
