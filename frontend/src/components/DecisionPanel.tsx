import type { EvaluateResponse } from '../types/api'
import { CheckCircle2, XCircle, AlertTriangle, Shield, CreditCard, ShieldOff } from 'lucide-react'
import { formatINR, formatDate, decisionLabel, RULE_META } from '../utils/format'

export interface DecisionContext {
  intentPayee?: string
  intentAmount?: number
  evidencePayee?: string
  evidenceAmount?: number
}

interface DecisionPanelProps {
  result: EvaluateResponse
  context?: DecisionContext
}

export default function DecisionPanel({ result, context }: DecisionPanelProps) {
  const { authorization: auth } = result
  const d = auth.decision

  const icon = d === 'ALLOW'
    ? <CheckCircle2 size={48} strokeWidth={2.5} />
    : d === 'DENY'
    ? <ShieldOff size={48} strokeWidth={2.5} />
    : <AlertTriangle size={48} strokeWidth={2.5} />

  const clsMap = {
    ALLOW: 'allow',
    DENY: 'deny',
    REQUIRE_HUMAN_APPROVAL: 'human',
  } as const
  const cls = clsMap[d]

  return (
    <div className={`decision-block decision-block-${cls} animate-scale-in`}>
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--sp-2)', marginBottom: 'var(--sp-6)', opacity: 0.8 }}>
          <Shield size={14} color={`var(--${cls})`} />
          <div style={{ fontSize: 'var(--text-xs)', fontWeight: 800, letterSpacing: '0.15em', textTransform: 'uppercase', color: `var(--${cls})` }}>
            Trust Gate
          </div>
        </div>

        <div style={{ color: `var(--${cls})`, marginBottom: 'var(--sp-4)' }}>
          {icon}
        </div>

        <div className={`decision-verdict decision-${cls}`} style={{ fontSize: 'var(--text-4xl)', letterSpacing: '0.02em', textTransform: 'uppercase' }}>
          {d === 'REQUIRE_HUMAN_APPROVAL' ? 'Human Approval' : d}
        </div>

        <p className="decision-reason" style={{ fontSize: 'var(--text-md)', fontWeight: 500, color: 'var(--text-primary)', marginTop: 'var(--sp-2)' }}>
          {auth.reason}
        </p>
      </div>

      {d === 'DENY' && (
        <MismatchDisplay auth={auth} context={context} />
      )}

      {d === 'ALLOW' && auth.payment_result && (
        <SimulatedPayment pr={auth.payment_result} />
      )}

      {d === 'REQUIRE_HUMAN_APPROVAL' && (
        <div style={{
          marginTop: 'var(--sp-8)',
          background: 'rgba(245,158,11,0.08)',
          border: '1px solid rgba(245,158,11,0.2)',
          borderRadius: 'var(--radius-lg)',
          padding: 'var(--sp-5)',
          maxWidth: 560, margin: 'var(--sp-8) auto 0',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 'var(--sp-2)', marginBottom: 'var(--sp-2)' }}>
            <AlertTriangle size={16} color="var(--human)" />
            <span style={{ fontWeight: 700, color: 'var(--human)', fontSize: 'var(--text-sm)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Action Held</span>
          </div>
          <p style={{ color: 'var(--human)', fontSize: 'var(--text-sm)', margin: 0, textAlign: 'center' }}>
            This transaction requires explicit human authorization. No payment has been initiated.
          </p>
        </div>
      )}

      <div style={{ marginTop: 'var(--sp-8)', paddingTop: 'var(--sp-6)', borderTop: '1px solid var(--border-subtle)', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 'var(--sp-3)' }}>
        {auth.matched_rule_ids.length > 0 && (
          <div style={{ display: 'inline-flex', alignItems: 'center', gap: 'var(--sp-2)', background: 'var(--bg-surface)', border: '1px solid var(--border-default)', borderRadius: 'var(--radius-full)', padding: '4px 16px' }}>
            <span style={{ fontSize: 'var(--text-xs)', fontWeight: 700, color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Policy Rule:</span>
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 'var(--text-xs)', color: 'var(--text-secondary)', fontWeight: 600 }}>
              {RULE_META[auth.matched_rule_ids[0]] ?? auth.matched_rule_ids[0]}
            </span>
          </div>
        )}
        <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-tertiary)', fontFamily: 'var(--font-mono)' }}>
          Event ID: {result.audit_event_id}
        </div>
      </div>
    </div>
  )
}

function MismatchDisplay({ auth, context }: { auth: EvaluateResponse['authorization']; context?: DecisionContext }) {
  const signals = auth.signals

  const proposedAmount  = context?.intentAmount ?? (signals.amount_delta_inr > 0 ? context?.evidenceAmount ? context.evidenceAmount + signals.amount_delta_inr : signals.amount_delta_inr : 0)
  const evidenceAmount  = context?.evidenceAmount
  const proposedPayee   = context?.intentPayee
  const evidencePayee   = context?.evidencePayee

  return (
    <div style={{ marginTop: 'var(--sp-8)', maxWidth: 640, margin: 'var(--sp-8) auto 0' }}>
      <div style={{
        background: 'var(--bg-base)', border: '1px solid rgba(239,68,68,0.25)',
        borderRadius: 'var(--radius-xl)', overflow: 'hidden',
        boxShadow: '0 8px 32px rgba(0,0,0,0.4)',
      }}>
        {/* Header */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', background: 'rgba(239,68,68,0.05)', borderBottom: '1px solid rgba(239,68,68,0.15)' }}>
          <div style={{ padding: 'var(--sp-4)', textAlign: 'center', borderRight: '1px solid rgba(239,68,68,0.15)' }}>
            <div style={{ fontSize: 'var(--text-xs)', fontWeight: 800, color: 'var(--deny)', letterSpacing: '0.1em', textTransform: 'uppercase' }}>Agent Proposed</div>
          </div>
          <div style={{ padding: 'var(--sp-4)', textAlign: 'center' }}>
            <div style={{ fontSize: 'var(--text-xs)', fontWeight: 800, color: 'var(--allow)', letterSpacing: '0.1em', textTransform: 'uppercase' }}>Verified Evidence</div>
          </div>
        </div>

        {/* Amount Row */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', borderBottom: '1px solid var(--border-subtle)' }}>
          <div style={{ padding: 'var(--sp-5)', textAlign: 'center', borderRight: '1px solid var(--border-subtle)', background: !signals.amount_match ? 'rgba(239,68,68,0.03)' : 'transparent' }}>
            <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 'var(--sp-1)' }}>Amount</div>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 'var(--text-2xl)', fontWeight: 800, color: !signals.amount_match ? 'var(--deny)' : 'var(--text-primary)' }}>
              {proposedAmount ? `₹${proposedAmount.toLocaleString('en-IN')}` : `+₹${signals.amount_delta_inr.toLocaleString('en-IN')}`}
            </div>
          </div>
          <div style={{ padding: 'var(--sp-5)', textAlign: 'center' }}>
            <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 'var(--sp-1)' }}>Amount</div>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 'var(--text-2xl)', fontWeight: 800, color: 'var(--allow)' }}>
              {evidenceAmount ? `₹${evidenceAmount.toLocaleString('en-IN')}` : `—`}
            </div>
          </div>
        </div>

        {/* Payee Row */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr' }}>
          <div style={{ padding: 'var(--sp-5)', textAlign: 'center', borderRight: '1px solid var(--border-subtle)', background: !signals.payee_match ? 'rgba(239,68,68,0.03)' : 'transparent' }}>
            <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 'var(--sp-1)' }}>Payee</div>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 'var(--text-lg)', fontWeight: 700, color: !signals.payee_match ? 'var(--deny)' : 'var(--text-primary)', wordBreak: 'break-word' }}>
              {proposedPayee ?? '—'}
            </div>
          </div>
          <div style={{ padding: 'var(--sp-5)', textAlign: 'center' }}>
            <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 'var(--sp-1)' }}>Payee</div>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 'var(--text-lg)', fontWeight: 700, color: 'var(--allow)', wordBreak: 'break-word' }}>
              {evidencePayee ?? '—'}
            </div>
          </div>
        </div>
      </div>

      <div style={{ marginTop: 'var(--sp-5)', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 'var(--sp-2)' }}>
        <div style={{ display: 'inline-block', background: 'var(--deny)', color: '#fff', padding: 'var(--sp-2) var(--sp-6)', borderRadius: 'var(--radius-full)', fontSize: 'var(--text-sm)', fontWeight: 800, letterSpacing: '0.05em', textTransform: 'uppercase' }}>
          Payment Blocked
        </div>
        <div style={{ fontSize: 'var(--text-xs)', color: 'var(--deny)', fontFamily: 'var(--font-mono)', fontWeight: 600 }}>
          ₹0 EXECUTED
        </div>
      </div>
    </div>
  )
}

function SimulatedPayment({ pr }: { pr: NonNullable<EvaluateResponse['authorization']['payment_result']> }) {
  return (
    <div style={{ marginTop: 'var(--sp-8)', display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
      <div style={{
        background: 'var(--bg-base)', border: '1px solid rgba(16,185,129,0.3)',
        borderRadius: 'var(--radius-xl)', padding: 'var(--sp-6)',
        width: '100%', maxWidth: 520,
        boxShadow: '0 8px 32px rgba(0,0,0,0.4)',
      }}>
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 'var(--sp-4)' }}>
          <div style={{ display: 'inline-block', background: 'var(--allow)', color: '#fff', padding: 'var(--sp-2) var(--sp-6)', borderRadius: 'var(--radius-full)', fontSize: 'var(--text-sm)', fontWeight: 800, letterSpacing: '0.05em', textTransform: 'uppercase' }}>
            Payment Authorized
          </div>
          
          <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--sp-6)', margin: 'var(--sp-2) 0' }}>
            <div style={{ textAlign: 'right' }}>
              <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '4px' }}>Executed</div>
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: 'var(--text-2xl)', fontWeight: 800, color: 'var(--allow)' }}>{formatINR(pr.amount)}</div>
            </div>
            <div style={{ width: 1, height: 40, background: 'var(--border-strong)' }} />
            <div style={{ textAlign: 'left' }}>
              <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '4px' }}>Transaction ID</div>
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: 'var(--text-md)', fontWeight: 600, color: 'var(--text-primary)' }}>{pr.transaction_id}</div>
            </div>
          </div>
        </div>

        <div style={{
          marginTop: 'var(--sp-6)',
          background: 'rgba(245,158,11,0.08)',
          border: '1px dashed rgba(245,158,11,0.3)',
          borderRadius: 'var(--radius-md)',
          padding: 'var(--sp-3)',
          fontSize: 'var(--text-xs)',
          color: 'var(--human)',
          lineHeight: 1.5,
          textAlign: 'center',
          fontWeight: 500,
        }}>
          {pr.disclaimer}
        </div>
      </div>
    </div>
  )
}
