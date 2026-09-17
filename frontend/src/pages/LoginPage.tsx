import { useState } from 'react'
import { ShieldCheck, Shield, Loader2, XCircle, AlertTriangle } from 'lucide-react'
import { useAuth } from '../contexts/AuthContext'

const DEMO_USERS = [
  { id: 'usr_standard', key: 'sk-dev-standard', label: 'Priya Sharma', sub: 'STANDARD · ₹10,000 limit', tag: 'Recommended' },
  { id: 'usr_basic',    key: 'sk-dev-basic',    label: 'Ananya Patel', sub: 'BASIC · ₹1,000 limit', tag: 'Human approval demo' },
  { id: 'usr_premium',  key: 'sk-dev-premium',  label: 'Arjun Singh',  sub: 'PREMIUM · ₹50,000 limit', tag: '' },
]

export default function LoginPage() {
  const { login, isLoading } = useAuth()
  const [error, setError] = useState<string | null>(null)
  const [selectedUser, setSelectedUser] = useState<string | null>(null)

  async function handleLogin(userId: string, apiKey: string) {
    setSelectedUser(userId)
    setError(null)
    try {
      await login(userId, apiKey)
    } catch (e: any) {
      setError(e.message)
      setSelectedUser(null)
    }
  }

  return (
    <div style={{
      minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center',
      background: 'var(--bg-base)', padding: 'var(--sp-6)',
    }}>
      <div style={{ width: '100%', maxWidth: 440 }}>
        {/* Brand */}
        <div style={{ textAlign: 'center', marginBottom: 'var(--sp-8)' }}>
          <div style={{
            width: 56, height: 56, borderRadius: 'var(--radius-lg)',
            background: 'linear-gradient(135deg, var(--accent), #6366f1)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            margin: '0 auto var(--sp-4)',
            boxShadow: '0 0 32px rgba(76,158,255,0.3)',
          }}>
            <ShieldCheck size={28} color="#fff" />
          </div>
          <h1 style={{ fontSize: 'var(--text-2xl)', marginBottom: 'var(--sp-2)' }}>AgentPay Sentinel</h1>
          <p style={{ fontSize: 'var(--text-sm)', margin: 0 }}>
            Evidence-aware trust gateway for AI-initiated payments
          </p>
        </div>

        {/* Sandbox notice */}
        <div className="alert alert-human" style={{ marginBottom: 'var(--sp-6)' }}>
          <AlertTriangle size={15} style={{ flexShrink: 0 }} />
          <div>
            <strong>Sandbox Environment.</strong> No real payments will be processed.
            All payment execution is simulated only.
          </div>
        </div>

        {/* User selector */}
        <div className="card" style={{ marginBottom: 'var(--sp-4)' }}>
          <div style={{ fontSize: 'var(--text-xs)', fontWeight: 700, color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 'var(--sp-4)' }}>
            Select Demo Session
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--sp-3)' }}>
            {DEMO_USERS.map((u) => (
              <button
                key={u.id}
                className="btn btn-secondary"
                style={{
                  justifyContent: 'flex-start', textAlign: 'left', padding: 'var(--sp-4)',
                  height: 'auto', flexDirection: 'column', alignItems: 'flex-start', gap: 'var(--sp-1)',
                  borderColor: selectedUser === u.id ? 'var(--accent)' : undefined,
                  background: selectedUser === u.id ? 'var(--accent-dim)' : undefined,
                }}
                onClick={() => handleLogin(u.id, u.key)}
                disabled={isLoading}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--sp-2)', width: '100%' }}>
                  <span style={{ fontWeight: 700, color: 'var(--text-primary)' }}>{u.label}</span>
                  {u.tag && <span className="badge badge-info" style={{ marginLeft: 'auto' }}>{u.tag}</span>}
                  {selectedUser === u.id && isLoading && <Loader2 size={14} style={{ animation: 'spin 0.7s linear infinite', marginLeft: 'auto', color: 'var(--accent)' }} />}
                </div>
                <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-tertiary)' }}>{u.sub}</div>
              </button>
            ))}
          </div>
        </div>

        {error && (
          <div className="alert alert-deny">
            <XCircle size={14} style={{ flexShrink: 0 }} />
            <div>
              <strong>Connection failed: </strong>{error}
              <br />
              <span style={{ fontSize: 'var(--text-xs)', opacity: 0.8 }}>
                Start the backend: <code style={{ fontFamily: 'var(--font-mono)' }}>uvicorn app.main:app --port 8000</code>
              </span>
            </div>
          </div>
        )}

        {/* Footer note */}
        <div style={{ textAlign: 'center', marginTop: 'var(--sp-6)', fontSize: 'var(--text-xs)', color: 'var(--text-tertiary)', lineHeight: 1.6 }}>
          <Shield size={12} style={{ display: 'inline', marginRight: 4 }} />
          AgentPay Sentinel · Hackathon Demo · Local Sandbox Only
        </div>
      </div>
    </div>
  )
}
