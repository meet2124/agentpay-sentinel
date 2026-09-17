import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Zap, Activity, Shield, FileText, ArrowRight, CheckCircle2, ShieldCheck, Clock } from 'lucide-react'
import { useAuth } from '../contexts/AuthContext'
import { api } from '../services/api'
import { formatINR, formatDate } from '../utils/format'
import type { AuditEvent } from '../types/api'

export default function OverviewPage() {
  const { user } = useAuth()
  const [recentEvents, setRecentEvents] = useState<AuditEvent[]>([])
  const [loaded, setLoaded] = useState(false)
  const [loading, setLoading] = useState(false)
  const [chainStatus, setChainStatus] = useState<null | { valid: boolean; checked: number }>(null)

  async function loadActivity() {
    if (loaded) return
    setLoading(true)
    try {
      const [eventsRes, chainRes] = await Promise.all([
        api.getAuditEvents({ limit: 5 }),
        api.verifyAuditChain(),
      ])
      setRecentEvents(eventsRes.events)
      setChainStatus({ valid: chainRes.chain_valid, checked: chainRes.events_checked })
    } catch { /* empty state is fine */ }
    setLoaded(true)
    setLoading(false)
  }

  // Load on mount
  useState(() => { loadActivity() })

  return (
    <div className="page-content animate-fade-in">
      {/* Header */}
      <div className="page-header">
        <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--sp-3)', marginBottom: 'var(--sp-2)' }}>
          <ShieldCheck size={28} color="var(--accent)" />
          <h1 className="page-title" style={{ margin: 0 }}>Trust Gateway</h1>
        </div>
        <p className="page-subtitle">
          Evidence-aware authorization for AI-initiated payments.
          LLMs understand. <span style={{ color: 'var(--text-primary)', fontWeight: 600 }}>Policies decide.</span>
        </p>
      </div>

      {/* Pipeline concept */}
      <div className="card" style={{ marginBottom: 'var(--sp-6)', padding: 'var(--sp-6)' }}>
        <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-tertiary)', fontWeight: 600, letterSpacing: '0.06em', textTransform: 'uppercase', marginBottom: 'var(--sp-5)' }}>
          How It Works
        </div>
        <div style={{
          display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: 'var(--sp-2)',
          fontSize: 'var(--text-sm)',
        }}>
          {[
            { label: 'AI Agent Proposes', color: 'var(--accent)' },
            null,
            { label: 'Intent Extracted', color: 'var(--text-secondary)' },
            null,
            { label: 'Evidence Verified', color: 'var(--text-secondary)' },
            null,
            { label: 'Signals Computed', color: 'var(--text-secondary)' },
            null,
            { label: 'Policy Evaluated', color: 'var(--text-secondary)' },
            null,
            { label: 'Decision Made', color: 'var(--allow)' },
            null,
            { label: 'Audit Written', color: 'var(--text-secondary)' },
          ].map((item, i) =>
            item === null ? (
              <ArrowRight key={i} size={14} color="var(--border-strong)" />
            ) : (
              <span key={i} style={{
                padding: '4px 12px',
                borderRadius: 'var(--radius-full)',
                background: 'var(--bg-surface)',
                border: '1px solid var(--border-default)',
                color: item.color,
                fontWeight: 500,
              }}>
                {item.label}
              </span>
            )
          )}
        </div>
      </div>

      {/* Quick stats */}
      <div className="grid-4" style={{ marginBottom: 'var(--sp-6)' }}>
        <StatCard icon={<Shield size={18} />} label="Policy Engine" value="Active" sub="8 deterministic rules" accent="var(--accent)" />
        <StatCard icon={<CheckCircle2 size={18} />} label="Audit Chain" value={
          chainStatus ? (chainStatus.valid ? 'Verified' : 'TAMPERED') : '—'
        } sub={chainStatus ? `${chainStatus.checked} events checked` : 'Loading…'} accent={chainStatus?.valid ? 'var(--allow)' : 'var(--deny)'} />
        <StatCard icon={<Activity size={18} />} label="Recent Events" value={String(recentEvents.length)} sub="Last 5 decisions" accent="var(--accent)" />
        <StatCard icon={<Zap size={18} />} label="Adapter Mode" value="Local" sub="No AWS dependency" accent="var(--human)" />
      </div>

      {/* Main CTA */}
      <div style={{
        background: 'linear-gradient(135deg, rgba(76,158,255,0.08) 0%, rgba(99,102,241,0.05) 100%)',
        border: '1px solid rgba(76,158,255,0.18)',
        borderRadius: 'var(--radius-xl)',
        padding: 'var(--sp-8)',
        marginBottom: 'var(--sp-6)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        gap: 'var(--sp-6)',
        flexWrap: 'wrap',
      }}>
        <div>
          <h2 style={{ marginBottom: 'var(--sp-2)' }}>Evaluate a Payment</h2>
          <p style={{ marginBottom: 0, maxWidth: 440 }}>
            Submit a natural language payment instruction and evidence document.
            Sentinel will verify intent vs evidence and make a deterministic authorization decision.
          </p>
        </div>
        <Link to="/evaluate" className="btn btn-primary btn-lg">
          <Zap size={18} />
          Start Evaluation
        </Link>
      </div>

      {/* Quick nav */}
      <div className="grid-3" style={{ marginBottom: 'var(--sp-8)' }}>
        <QuickNavCard to="/evidence" icon={<FileText size={20} color="var(--accent)" />} title="Upload Evidence" desc="Add an invoice or receipt to attach to your transaction." />
        <QuickNavCard to="/audit" icon={<Activity size={20} color="var(--allow)" />} title="Audit Trail" desc="Review the tamper-evident cryptographic event log." />
        <QuickNavCard to="/policy" icon={<Shield size={20} color="var(--human)" />} title="Policy Rules" desc="Inspect the active deterministic authorization rules." />
      </div>

      {/* User info */}
      {user && (
        <div className="card">
          <div style={{ fontSize: 'var(--text-sm)', fontWeight: 700, color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 'var(--sp-4)' }}>
            Session Context
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(160px, 1fr))', gap: 'var(--sp-4)' }}>
            <InfoRow label="User" value={user.name} />
            <InfoRow label="Tier" value={user.tier} />
            <InfoRow label="Spending Limit" value={formatINR(user.spending_limit_inr)} />
            {user.daily_limit_inr && <InfoRow label="Daily Limit" value={formatINR(user.daily_limit_inr)} />}
          </div>
        </div>
      )}
    </div>
  )
}

function StatCard({ icon, label, value, sub, accent }: {
  icon: React.ReactNode; label: string; value: string; sub: string; accent: string
}) {
  return (
    <div className="card" style={{ display: 'flex', flexDirection: 'column', gap: 'var(--sp-3)' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--sp-2)', color: accent }}>
        {icon}
        <span style={{ fontSize: 'var(--text-xs)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.06em', color: 'var(--text-tertiary)' }}>{label}</span>
      </div>
      <div style={{ fontSize: 'var(--text-2xl)', fontWeight: 800, color: accent, lineHeight: 1 }}>{value}</div>
      <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-tertiary)' }}>{sub}</div>
    </div>
  )
}

function QuickNavCard({ to, icon, title, desc }: { to: string; icon: React.ReactNode; title: string; desc: string }) {
  return (
    <Link to={to} style={{ textDecoration: 'none' }}>
      <div className="card" style={{ height: '100%', cursor: 'pointer', transition: 'all var(--transition-base)' }}
        onMouseEnter={e => (e.currentTarget.style.borderColor = 'var(--border-strong)')}
        onMouseLeave={e => (e.currentTarget.style.borderColor = 'var(--border-subtle)')}>
        <div style={{ marginBottom: 'var(--sp-3)' }}>{icon}</div>
        <h4 style={{ marginBottom: 'var(--sp-2)', fontSize: 'var(--text-base)' }}>{title}</h4>
        <p style={{ fontSize: 'var(--text-sm)', margin: 0 }}>{desc}</p>
      </div>
    </Link>
  )
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-tertiary)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 4 }}>{label}</div>
      <div style={{ fontWeight: 600, color: 'var(--text-primary)' }}>{value}</div>
    </div>
  )
}
