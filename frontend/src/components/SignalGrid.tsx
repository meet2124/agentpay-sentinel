import type { TransactionSignals } from '../types/api'
import { CheckCircle2, XCircle } from 'lucide-react'
import { SIGNAL_META, pct } from '../utils/format'

interface SignalGridProps {
  signals: TransactionSignals
}

interface SignalCardProps {
  signalKey: string
  value: boolean | number
  type: 'boolean' | 'number'
}

const BOOLEAN_SIGNALS: (keyof TransactionSignals)[] = [
  'amount_match', 'payee_match', 'evidence_present',
  'evidence_extraction_ok', 'currency_match',
  'amount_within_limit', 'payee_seen_before',
]

function SignalCard({ signalKey, value, type }: SignalCardProps) {
  const meta = SIGNAL_META[signalKey]
  const isPass = type === 'boolean' ? Boolean(value) : true
  const displayVal =
    type === 'boolean'
      ? Boolean(value)
        ? 'Verified'
        : 'Failed'
      : typeof value === 'number'
      ? pct(value)
      : String(value)

  return (
    <div className={`signal-card ${isPass ? 'pass' : 'fail'}`} style={{ animationDelay: '0.05s', minHeight: 120 }}>
      <div className="signal-header" style={{ marginBottom: 'var(--sp-2)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--sp-2)' }}>
          {type === 'boolean' ? (
            isPass
              ? <CheckCircle2 size={16} color="var(--allow)" />
              : <XCircle size={16} color="var(--deny)" />
          ) : null}
          <span className="signal-name" style={{ fontSize: 'var(--text-sm)', textTransform: 'uppercase', letterSpacing: '0.05em', color: isPass ? 'var(--text-primary)' : 'var(--deny)', fontWeight: 700 }}>
            {meta?.label ?? signalKey}
          </span>
        </div>
        <span className={`signal-value ${isPass ? 'pass' : 'fail'}`} style={{ fontSize: '10px', textTransform: 'uppercase', letterSpacing: '0.1em' }}>
          {displayVal}
        </span>
      </div>
      <div className="signal-desc" style={{ fontSize: 'var(--text-xs)', color: isPass ? 'var(--text-secondary)' : 'rgba(239,68,68,0.9)', lineHeight: 1.6, flex: 1 }}>{meta?.desc ?? ''}</div>
      <div style={{ marginTop: 'var(--sp-3)', paddingTop: 'var(--sp-3)', borderTop: `1px solid ${isPass ? 'var(--border-subtle)' : 'rgba(239,68,68,0.15)'}` }}>
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: '10px', color: isPass ? 'var(--text-tertiary)' : 'rgba(239,68,68,0.6)' }}>
          {signalKey} = {String(value).toLowerCase()}
        </span>
      </div>
    </div>
  )
}

export default function SignalGrid({ signals }: SignalGridProps) {
  return (
    <div>
      <div className="signal-grid animate-fade-in" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))' }}>
        {BOOLEAN_SIGNALS.map((key) => (
          <SignalCard
            key={key}
            signalKey={key}
            value={signals[key] as boolean}
            type="boolean"
          />
        ))}
      </div>

      {/* Quantitative signals */}
      <div style={{
        marginTop: 'var(--sp-4)',
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))',
        gap: 'var(--sp-3)',
      }}>
        <div className="card card-sm" style={{ display: 'flex', flexDirection: 'column', gap: 'var(--sp-1)' }}>
          <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.06em', fontWeight: 600 }}>Payee Similarity</div>
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 'var(--text-lg)', fontWeight: 700, color: signals.payee_match ? 'var(--allow)' : 'var(--deny)' }}>
            {pct(signals.payee_similarity)}
          </div>
          <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-tertiary)' }}>Threshold: 85%</div>
        </div>

        <div className="card card-sm" style={{ display: 'flex', flexDirection: 'column', gap: 'var(--sp-1)' }}>
          <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.06em', fontWeight: 600 }}>Amount Delta</div>
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 'var(--text-lg)', fontWeight: 700, color: signals.amount_match ? 'var(--allow)' : 'var(--deny)' }}>
            ₹{signals.amount_delta_inr.toLocaleString('en-IN')}
          </div>
          <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-tertiary)' }}>Threshold: ≤ ₹1</div>
        </div>

        <div className="card card-sm" style={{ display: 'flex', flexDirection: 'column', gap: 'var(--sp-1)' }}>
          <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.06em', fontWeight: 600 }}>Extraction Confidence</div>
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 'var(--text-lg)', fontWeight: 700, color: signals.evidence_extraction_ok ? 'var(--allow)' : 'var(--deny)' }}>
            {pct(signals.evidence_extraction_confidence)}
          </div>
          <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-tertiary)' }}>Threshold: 70%</div>
        </div>

        <div className="card card-sm" style={{ display: 'flex', flexDirection: 'column', gap: 'var(--sp-1)' }}>
          <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.06em', fontWeight: 600 }}>Limit Utilization</div>
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 'var(--text-lg)', fontWeight: 700, color: signals.amount_within_limit ? 'var(--allow)' : 'var(--deny)' }}>
            {pct(Math.min(signals.amount_vs_limit_ratio, 9.99))}
          </div>
          <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-tertiary)' }}>Of spending limit</div>
        </div>

        <div className="card card-sm" style={{ display: 'flex', flexDirection: 'column', gap: 'var(--sp-1)' }}>
          <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.06em', fontWeight: 600 }}>Risk Indicator</div>
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 'var(--text-lg)', fontWeight: 700, color: signals.display_risk_score > 40 ? 'var(--deny)' : signals.display_risk_score > 20 ? 'var(--human)' : 'var(--allow)' }}>
            {signals.display_risk_score}/100
          </div>
          <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-tertiary)' }}>UI display only — not used in policy</div>
        </div>
      </div>
    </div>
  )
}
