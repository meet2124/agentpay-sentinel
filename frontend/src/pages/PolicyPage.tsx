import { useState, useEffect } from 'react'
import { Shield, RefreshCw, XCircle, CheckCircle2, AlertTriangle } from 'lucide-react'
import { api } from '../services/api'
import type { PolicyRule, PolicyListResponse } from '../types/api'
import { RULE_META } from '../utils/format'

const DECISION_ICONS: Record<string, React.ReactNode> = {
  ALLOW: <CheckCircle2 size={14} color="var(--allow)" />,
  DENY:  <XCircle size={14} color="var(--deny)" />,
  REQUIRE_HUMAN_APPROVAL: <AlertTriangle size={14} color="var(--human)" />,
}

export default function PolicyPage() {
  const [policy, setPolicy] = useState<PolicyListResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function load() {
    setLoading(true)
    setError(null)
    try {
      const res = await api.getPolicyRules()
      setPolicy(res)
    } catch (e: any) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  const deny = policy?.rules.filter(r => r.action === 'DENY') ?? []
  const human = policy?.rules.filter(r => r.action === 'REQUIRE_HUMAN_APPROVAL') ?? []
  const allow = policy?.rules.filter(r => r.action === 'ALLOW') ?? []

  return (
    <div className="page-content animate-fade-in">
      <div className="page-header">
        <h1 className="page-title">
          <Shield size={24} style={{ display: 'inline', marginRight: 10, color: 'var(--accent)' }} />
          Policy Rules
        </h1>
        <p className="page-subtitle">
          The deterministic authorization engine. Rules are evaluated in priority order — first match wins.
          No floating-point risk score makes the authorization decision.
        </p>
      </div>

      {/* Principle box */}
      <div style={{
        background: 'linear-gradient(135deg, rgba(76,158,255,0.06) 0%, rgba(99,102,241,0.04) 100%)',
        border: '1px solid rgba(76,158,255,0.15)',
        borderRadius: 'var(--radius-xl)',
        padding: 'var(--sp-6)',
        marginBottom: 'var(--sp-6)',
        display: 'flex', gap: 'var(--sp-5)', alignItems: 'flex-start',
      }}>
        <div style={{ fontSize: 36 }}>🔐</div>
        <div>
          <h3 style={{ marginBottom: 'var(--sp-2)' }}>LLM understands. Policies decide.</h3>
          <p style={{ margin: 0, fontSize: 'var(--text-sm)' }}>
            The LLM extracts intent and evidence as natural language understanding tasks. Those outputs are
            immediately schema-validated by Pydantic. The schema-validated signals — explicit boolean/numeric
            values — are then evaluated by this deterministic rule engine. The LLM output
            never directly authorizes or denies a payment.
          </p>
        </div>
      </div>

      {/* Controls */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 'var(--sp-5)' }}>
        <div style={{ display: 'flex', gap: 'var(--sp-2)' }}>
          <span className="badge badge-deny">{deny.length} Deny</span>
          <span className="badge badge-human">{human.length} Human Approval</span>
          <span className="badge badge-allow">{allow.length} Allow</span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--sp-3)' }}>
          {policy && <span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-tertiary)', fontFamily: 'var(--font-mono)' }}>v{policy.version}</span>}
          <button className="btn btn-secondary btn-sm" onClick={load} disabled={loading}>
            <RefreshCw size={13} />
            Refresh
          </button>
        </div>
      </div>

      {error && (
        <div className="alert alert-deny" style={{ marginBottom: 'var(--sp-4)' }}>
          <XCircle size={14} style={{ flexShrink: 0 }} />
          {error}
        </div>
      )}

      {policy && (
        <>
          {policy.note && (
            <div className="alert alert-info" style={{ marginBottom: 'var(--sp-5)' }}>
              <Shield size={14} style={{ flexShrink: 0 }} />
              {policy.note}
            </div>
          )}

          {/* Rule groups */}
          {[
            { label: 'Deny Rules', rules: deny, cls: 'deny' },
            { label: 'Human Approval Rules', rules: human, cls: 'human' },
            { label: 'Allow Rules', rules: allow, cls: 'allow' },
          ].map(({ label, rules, cls }) => rules.length > 0 && (
            <div key={cls} style={{ marginBottom: 'var(--sp-8)' }}>
              <div style={{ 
                fontSize: 'var(--text-sm)', fontWeight: 800, color: `var(--${cls})`, 
                textTransform: 'uppercase', letterSpacing: '0.1em', 
                marginBottom: 'var(--sp-4)', display: 'flex', alignItems: 'center', gap: 'var(--sp-3)',
                background: `var(--${cls}-dim)`,
                padding: 'var(--sp-3) var(--sp-4)', borderRadius: 'var(--radius-md)',
                borderLeft: `3px solid var(--${cls})`
              }}>
                {DECISION_ICONS[rules[0].action]}
                {label}
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--sp-3)' }}>
                {rules.sort((a, b) => a.priority - b.priority).map(rule => (
                  <PolicyRuleCard key={rule.rule_id} rule={rule} cls={cls} />
                ))}
              </div>
            </div>
          ))}
        </>
      )}

      {loading && !policy && (
        <div style={{ display: 'flex', justifyContent: 'center', padding: 'var(--sp-12)' }}>
          <div className="spinner" style={{ width: 32, height: 32 }} />
        </div>
      )}
    </div>
  )
}

function PolicyRuleCard({ rule, cls }: { rule: PolicyRule; cls: string }) {
  return (
    <div className="card card-sm" style={{
      display: 'flex', gap: 'var(--sp-4)', alignItems: 'flex-start',
      borderLeftWidth: 3, borderLeftColor: `var(--${cls})`,
      borderLeft: `3px solid var(--${cls})`,
    }}>
      {/* Priority badge */}
      <div style={{
        width: 36, height: 36, borderRadius: 'var(--radius-md)',
        background: `var(--${cls}-dim)`, border: `1px solid rgba(var(--${cls}-rgb), 0.2)`,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        flexShrink: 0,
      }}>
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 'var(--text-sm)', fontWeight: 700, color: `var(--${cls})` }}>
          {rule.priority}
        </span>
      </div>

      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--sp-2)', marginBottom: 'var(--sp-1)', flexWrap: 'wrap' }}>
          <span style={{ fontWeight: 700, fontSize: 'var(--text-sm)', color: 'var(--text-primary)' }}>
            {RULE_META[rule.rule_id] ?? rule.name}
          </span>
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 'var(--text-xs)', color: 'var(--text-tertiary)', background: 'var(--bg-surface)', padding: '1px 8px', borderRadius: 'var(--radius-full)', border: '1px solid var(--border-subtle)' }}>
            {rule.rule_id}
          </span>
          {!rule.is_active && <span className="badge badge-deny">Inactive</span>}
        </div>
        <p style={{ margin: '0 0 var(--sp-2)', fontSize: 'var(--text-sm)' }}>
          {rule.description}
        </p>
        {/* Condition (machine-readable) */}
        {rule.condition && (
          <div style={{
            background: 'var(--bg-surface)', borderRadius: 'var(--radius-sm)',
            padding: 'var(--sp-2) var(--sp-3)',
            fontFamily: 'var(--font-mono)', fontSize: 'var(--text-xs)', color: 'var(--text-secondary)',
          }}>
            {rule.condition}
          </div>
        )}
      </div>

      <div style={{ flexShrink: 0 }}>
        <span className={`badge badge-${cls === 'human' ? 'human' : cls === 'deny' ? 'deny' : 'allow'}`}>
          {DECISION_ICONS[rule.action]}
          {rule.action === 'REQUIRE_HUMAN_APPROVAL' ? 'HUMAN' : rule.action}
        </span>
      </div>
    </div>
  )
}
