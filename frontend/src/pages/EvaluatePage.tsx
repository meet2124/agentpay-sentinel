import { useState, useRef } from 'react'
import {
  Zap, FileText, Upload, CheckCircle2, XCircle, AlertTriangle,
  ChevronDown, ChevronUp, Loader2, Shield, ArrowRight,
} from 'lucide-react'
import { api } from '../services/api'
import type { EvaluateResponse, Evidence } from '../types/api'
import DecisionPanel, { type DecisionContext } from '../components/DecisionPanel'
import SignalGrid from '../components/SignalGrid'
import { formatDate, formatINR, RULE_META } from '../utils/format'

// ─── Demo scenarios ───────────────────────────────────────────────────────────
const SCENARIOS = [
  {
    id: 'killer_denial',
    label: '🔴  Killer Denial — Agent tries ₹18,500 / XYZ Traders',
    raw_input: 'Pay 18500 to XYZ Traders.',
    evidence: {
      vendor_name: 'ABC Hardware Co.', amount: 1850, currency: 'INR',
      invoice_number: 'INV-042', invoice_date: '2026-09-15',
      extraction_confidence: 0.94, extraction_method: 'STUB',
    },
    tag: 'DENY',
  },
  {
    id: 'happy_path',
    label: '🟢  Happy Path — Full match, ₹1,850 to ABC Hardware',
    raw_input: 'Pay 1850 to ABC Hardware.',
    evidence: {
      vendor_name: 'ABC Hardware Co.', amount: 1850, currency: 'INR',
      invoice_number: 'INV-042', invoice_date: '2026-09-15',
      extraction_confidence: 0.94, extraction_method: 'STUB',
    },
    tag: 'ALLOW',
  },
  {
    id: 'human_approval',
    label: '🟡  Human Approval — Amount exceeds spending limit',
    raw_input: 'Pay 1850 to ABC Hardware.',
    evidence: {
      vendor_name: 'ABC Hardware Co.', amount: 1850, currency: 'INR',
      invoice_number: 'INV-042', invoice_date: '2026-09-15',
      extraction_confidence: 0.94, extraction_method: 'STUB',
    },
    tag: 'HUMAN',
    note: '(Run as usr_basic with ₹1,000 limit)',
  },
  {
    id: 'small_payment',
    label: '🟢  Small Payment — No evidence required (≤₹500)',
    raw_input: 'Pay 300 to Tea Stall.',
    evidence: null,
    tag: 'ALLOW',
  },
  {
    id: 'amount_mismatch',
    label: '🔴  Amount Mismatch Only',
    raw_input: 'Pay 5000 to ABC Hardware.',
    evidence: {
      vendor_name: 'ABC Hardware Co.', amount: 1850, currency: 'INR',
      invoice_number: 'INV-042', invoice_date: '2026-09-15',
      extraction_confidence: 0.94, extraction_method: 'STUB',
    },
    tag: 'DENY',
  },
]

type Step = 'idle' | 'uploading' | 'evaluating' | 'done' | 'error'

export default function EvaluatePage() {
  const [rawInput, setRawInput] = useState('')
  const [selectedScenario, setSelectedScenario] = useState<string | null>(null)
  const [evidence, setEvidence] = useState<Evidence | null>(null)
  const [evidenceFile, setEvidenceFile] = useState<File | null>(null)
  const [step, setStep] = useState<Step>('idle')
  const [result, setResult] = useState<EvaluateResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [showSignals, setShowSignals] = useState(false)
  const [showPolicy, setShowPolicy] = useState(false)
  const [decisionCtx, setDecisionCtx] = useState<DecisionContext | undefined>(undefined)
  const fileRef = useRef<HTMLInputElement>(null)

  async function applyScenario(s: typeof SCENARIOS[0]) {
    setSelectedScenario(s.id)
    setRawInput(s.raw_input)
    setResult(null)
    setError(null)
    setEvidence(null)
    setEvidenceFile(null)
    setShowSignals(false)
    setShowPolicy(false)
    setDecisionCtx(undefined)

    // Auto-upload evidence JSON fixture
    if (s.evidence) {
      const ctx: DecisionContext = {
        evidencePayee: s.evidence.vendor_name,
        evidenceAmount: s.evidence.amount,
      }
      const blob = new Blob([JSON.stringify(s.evidence)], { type: 'application/json' })
      const file = new File([blob], 'scenario_evidence.json', { type: 'application/json' })
      setEvidenceFile(file)
      try {
        setStep('uploading')
        const ev = await api.uploadEvidence(file)
        setEvidence(ev)
        setDecisionCtx(ctx)
        setStep('idle')
      } catch (e: any) {
        setError(e.message)
        setStep('error')
      }
    }
  }

  async function handleFileUpload(file: File) {
    setEvidenceFile(file)
    setStep('uploading')
    setError(null)
    try {
      const ev = await api.uploadEvidence(file)
      setEvidence(ev)
      setStep('idle')
    } catch (e: any) {
      setError(e.message)
      setStep('error')
    }
  }

  async function evaluate() {
    if (!rawInput.trim()) return
    setStep('evaluating')
    setResult(null)
    setError(null)
    setShowSignals(false)
    setShowPolicy(false)
    // Build context from scenario or uploaded evidence
    const ctx: DecisionContext = {
      ...decisionCtx,
      // Parse a rough intent amount from raw_input (numbers like 18500 or 1850)
      intentAmount: (() => {
        const m = rawInput.match(/(\d[\d,]*)/)
        return m ? parseFloat(m[1].replace(/,/g, '')) : undefined
      })(),
      // Parse a rough payee from "to <Payee>" pattern
      intentPayee: (() => {
        const m = rawInput.match(/\bto\s+([\w\s]+?)\s*\.?$/i)
        return m ? m[1].trim() : undefined
      })(),
    }
    try {
      const res = await api.evaluatePayment({
        raw_input: rawInput.trim(),
        evidence_id: evidence?.evidence_id,
      })
      setResult(res)
      setDecisionCtx(ctx)
      setStep('done')
    } catch (e: any) {
      setError(e.message)
      setStep('error')
    }
  }

  function reset() {
    setResult(null); setError(null); setStep('idle')
    setRawInput(''); setEvidence(null); setEvidenceFile(null)
    setSelectedScenario(null); setShowSignals(false); setShowPolicy(false)
    setDecisionCtx(undefined)
  }

  const isLoading = step === 'uploading' || step === 'evaluating'

  return (
    <div className="page-content animate-fade-in">
      <div className="page-header">
        <h1 className="page-title">
          <Zap size={24} style={{ display: 'inline', marginRight: 10, color: 'var(--accent)' }} />
          Evaluate Payment
        </h1>
        <p className="page-subtitle">
          The Trust Gateway intercepts the AI agent's proposed action and evaluates it against intent, evidence and policy.
        </p>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'minmax(380px, 420px) 1fr', gap: 'var(--sp-8)', alignItems: 'start' }}>

        {/* ── Left: Input panel ── */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--sp-4)' }}>

          {/* Demo Scenarios */}
          <div className="card">
            <div style={{ fontSize: 'var(--text-xs)', fontWeight: 700, color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 'var(--sp-3)' }}>
              Demo Scenarios
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--sp-2)' }}>
              {SCENARIOS.map((s) => (
                <button
                  key={s.id}
                  className={`btn btn-secondary btn-sm${selectedScenario === s.id ? ' active' : ''}`}
                  style={{
                    justifyContent: 'flex-start', textAlign: 'left', fontWeight: 500,
                    borderColor: selectedScenario === s.id ? 'var(--accent)' : undefined,
                    background: selectedScenario === s.id ? 'var(--accent-dim)' : undefined,
                  }}
                  onClick={() => applyScenario(s)}
                  disabled={isLoading}
                >
                  {s.label}
                </button>
              ))}
            </div>
          </div>

          {/* Raw Input */}
          <div className="card">
            <div style={{ fontSize: 'var(--text-xs)', fontWeight: 700, color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 'var(--sp-3)', display: 'flex', alignItems: 'center', gap: 'var(--sp-2)' }}>
              <span style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--deny)', display: 'inline-block' }} />
              AI Agent Instruction
            </div>
            <div className="form-group">
              <textarea
                className="form-textarea"
                placeholder="e.g. Pay ₹1,850 to ABC Hardware for electrical fittings."
                value={rawInput}
                onChange={e => setRawInput(e.target.value)}
                rows={3}
                disabled={isLoading}
              />
              <div className="form-hint">
                This is the raw instruction from the AI agent — treated as untrusted input.
              </div>
            </div>
          </div>

          {/* Evidence Upload */}
          <div className="card">
            <div style={{ fontSize: 'var(--text-xs)', fontWeight: 700, color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 'var(--sp-3)', display: 'flex', alignItems: 'center', gap: 'var(--sp-2)' }}>
              <FileText size={12} />
              Evidence Document
              {evidence && <span className="badge badge-allow" style={{ marginLeft: 'auto' }}>Uploaded</span>}
            </div>

            {evidence ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--sp-2)' }}>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--sp-3)' }}>
                  <EvidenceField label="Vendor" value={evidence.vendor_name ?? '—'} />
                  <EvidenceField label="Amount" value={evidence.amount != null ? formatINR(evidence.amount) : '—'} />
                  <EvidenceField label="Invoice #" value={evidence.invoice_number ?? '—'} />
                  <EvidenceField label="Confidence" value={`${Math.round(evidence.extraction_confidence * 100)}%`} highlight={evidence.extraction_confidence >= 0.7} />
                </div>
                <button className="btn btn-ghost btn-sm" onClick={() => { setEvidence(null); setEvidenceFile(null) }}>
                  Remove evidence
                </button>
              </div>
            ) : step === 'uploading' ? (
              <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--sp-3)', padding: 'var(--sp-4)' }}>
                <div className="spinner" />
                <span style={{ color: 'var(--text-secondary)', fontSize: 'var(--text-sm)' }}>Uploading and extracting evidence…</span>
              </div>
            ) : (
              <div
                className="upload-area"
                onClick={() => fileRef.current?.click()}
                onDragOver={e => { e.preventDefault(); e.currentTarget.classList.add('drag-over') }}
                onDragLeave={e => e.currentTarget.classList.remove('drag-over')}
                onDrop={async e => {
                  e.preventDefault(); e.currentTarget.classList.remove('drag-over')
                  const f = e.dataTransfer.files[0]
                  if (f) handleFileUpload(f)
                }}
              >
                <div className="upload-icon"><Upload size={22} /></div>
                <div style={{ fontWeight: 600, marginBottom: 'var(--sp-1)', color: 'var(--text-primary)' }}>Drop invoice or receipt</div>
                <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-tertiary)' }}>PDF, JPEG, PNG · or click to browse</div>
                <input ref={fileRef} type="file" accept=".pdf,.jpg,.jpeg,.png,.webp,.json" style={{ display: 'none' }}
                  onChange={e => { const f = e.target.files?.[0]; if (f) handleFileUpload(f) }} />
              </div>
            )}
          </div>

          {/* Evaluate button */}
          <button
            className="btn btn-primary btn-lg w-full"
            onClick={evaluate}
            disabled={!rawInput.trim() || isLoading}
          >
            {step === 'evaluating' ? (
              <><Loader2 size={18} className="spin" style={{ animation: 'spin 0.7s linear infinite' }} />Evaluating…</>
            ) : (
              <><Shield size={18} />Run Trust Evaluation</>
            )}
          </button>

          {result && (
            <button className="btn btn-ghost btn-sm w-full" onClick={reset}>
              ← New Evaluation
            </button>
          )}
        </div>

        {/* ── Right: Results panel ── */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--sp-4)' }}>

          {/* Pipeline steps */}
          {(step !== 'idle' || result) && (
            <PipelineProgress step={step} hasEvidence={!!evidence} />
          )}

          {/* Error */}
          {error && (
            <div className="alert alert-deny animate-fade-in">
              <XCircle size={16} style={{ flexShrink: 0 }} />
              <div>
                <strong>Request failed: </strong>{error}
                <br />
                <span style={{ fontSize: 'var(--text-xs)', opacity: 0.7 }}>Is the backend running at localhost:8000?</span>
              </div>
            </div>
          )}

          {/* Decision */}
          {result && (
            <>
              <DecisionPanel result={result} context={decisionCtx} />

              {/* Signals expandable */}
              <div className="card">
                <button
                  className="btn btn-ghost btn-sm"
                  style={{ width: '100%', justifyContent: 'space-between', color: 'var(--text-secondary)' }}
                  onClick={() => setShowSignals(v => !v)}
                >
                  <span style={{ fontWeight: 600 }}>Transaction Signals</span>
                  {showSignals ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                </button>
                {showSignals && (
                  <div style={{ marginTop: 'var(--sp-4)', borderTop: '1px solid var(--border-subtle)', paddingTop: 'var(--sp-4)' }}>
                    <SignalGrid signals={result.authorization.signals} />
                  </div>
                )}
              </div>

              {/* Policy explainer expandable */}
              <div className="card">
                <button
                  className="btn btn-ghost btn-sm"
                  style={{ width: '100%', justifyContent: 'space-between', color: 'var(--text-secondary)' }}
                  onClick={() => setShowPolicy(v => !v)}
                >
                  <span style={{ fontWeight: 600 }}>Policy Explanation</span>
                  {showPolicy ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                </button>
                {showPolicy && (
                  <PolicyExplainer result={result} />
                )}
              </div>
            </>
          )}

          {/* Idle state */}
          {step === 'idle' && !result && !error && (
            <div style={{
              border: '2px dashed var(--border-subtle)', borderRadius: 'var(--radius-xl)',
              padding: 'var(--sp-12)', textAlign: 'center', color: 'var(--text-tertiary)',
            }}>
              <Shield size={36} style={{ marginBottom: 'var(--sp-4)', opacity: 0.3 }} />
              <div style={{ fontWeight: 600, marginBottom: 'var(--sp-2)' }}>Awaiting Evaluation</div>
              <div style={{ fontSize: 'var(--text-sm)' }}>Select a scenario or enter an instruction to begin.</div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function EvidenceField({ label, value, highlight }: { label: string; value: string; highlight?: boolean }) {
  return (
    <div>
      <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-tertiary)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: 3 }}>{label}</div>
      <div style={{ fontFamily: 'var(--font-mono)', fontWeight: 600, color: highlight === false ? 'var(--deny)' : 'var(--text-primary)', fontSize: 'var(--text-sm)' }}>{value}</div>
    </div>
  )
}

type PipelineStepState = 'pending' | 'active' | 'pass' | 'fail'

interface PipelineItem { label: string; sub: string; state: PipelineStepState }

function PipelineProgress({ step, hasEvidence }: { step: Step; hasEvidence: boolean }) {
  const steps: PipelineItem[] = [
    { label: 'Intent Extraction', sub: 'LLM → Pydantic schema validation', state: step === 'idle' && !hasEvidence ? 'pending' : ['uploading', 'evaluating', 'done', 'error'].includes(step) || hasEvidence ? 'pass' : 'pending' },
    { label: 'Evidence Processing', sub: 'Server-side extraction', state: hasEvidence ? 'pass' : step === 'uploading' ? 'active' : 'pending' },
    { label: 'Signal Computation', sub: 'Deterministic comparison', state: step === 'evaluating' ? 'active' : step === 'done' ? 'pass' : step === 'error' ? 'fail' : 'pending' },
    { label: 'Policy Evaluation', sub: 'Priority-ordered rules', state: step === 'evaluating' ? 'active' : step === 'done' ? 'pass' : step === 'error' ? 'fail' : 'pending' },
    { label: 'Authorization Decision', sub: 'ALLOW / DENY / HUMAN', state: step === 'done' ? 'pass' : step === 'error' ? 'fail' : 'pending' },
    { label: 'Audit Trail Written', sub: 'Tamper-evident hash chain', state: step === 'done' ? 'pass' : step === 'error' ? 'fail' : 'pending' },
  ]

  return (
    <div className="card animate-slide-in">
      <div style={{ fontSize: 'var(--text-xs)', fontWeight: 700, color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 'var(--sp-4)' }}>
        Evaluation Pipeline
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 0 }}>
        {steps.map((s, i) => (
          <div key={i} style={{ display: 'flex', alignItems: 'stretch', gap: 'var(--sp-3)' }}>
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', width: 28, flexShrink: 0 }}>
              <div style={{
                width: 28, height: 28, borderRadius: 'var(--radius-md)', flexShrink: 0,
                background: s.state === 'pass' ? 'var(--allow-dim)' : s.state === 'fail' ? 'var(--deny-dim)' : s.state === 'active' ? 'var(--accent-dim)' : 'var(--bg-elevated)',
                border: `1px solid ${s.state === 'pass' ? 'rgba(34,197,94,0.3)' : s.state === 'fail' ? 'rgba(239,68,68,0.3)' : s.state === 'active' ? 'rgba(76,158,255,0.3)' : 'var(--border-default)'}`,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                color: s.state === 'pass' ? 'var(--allow)' : s.state === 'fail' ? 'var(--deny)' : s.state === 'active' ? 'var(--accent)' : 'var(--text-tertiary)',
                transition: 'all var(--transition-base)',
              }}>
                {s.state === 'pass' ? <CheckCircle2 size={13} /> : s.state === 'fail' ? <XCircle size={13} /> : s.state === 'active' ? <Loader2 size={13} style={{ animation: 'spin 0.7s linear infinite' }} /> : <span style={{ width: 6, height: 6, borderRadius: '50%', background: 'currentColor' }} />}
              </div>
              {i < steps.length - 1 && (
                <div style={{ width: 2, flex: 1, minHeight: 16, margin: '2px 0', background: s.state === 'pass' ? 'var(--allow)' : s.state === 'fail' ? 'var(--deny)' : 'var(--border-subtle)', opacity: 0.4 }} />
              )}
            </div>
            <div style={{ paddingBottom: i < steps.length - 1 ? 'var(--sp-3)' : 0, paddingTop: 3 }}>
              <div style={{ fontSize: 'var(--text-sm)', fontWeight: 600, color: s.state === 'pending' ? 'var(--text-tertiary)' : 'var(--text-primary)' }}>{s.label}</div>
              <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-tertiary)' }}>{s.sub}</div>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

function PolicyExplainer({ result }: { result: EvaluateResponse }) {
  const { authorization: auth } = result
  return (
    <div style={{ marginTop: 'var(--sp-4)', borderTop: '1px solid var(--border-subtle)', paddingTop: 'var(--sp-4)', display: 'flex', flexDirection: 'column', gap: 'var(--sp-3)' }}>
      <div>
        <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-tertiary)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 'var(--sp-2)' }}>Matched Rule</div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--sp-2)' }}>
          {auth.matched_rule_ids.map(rid => (
            <div key={rid} style={{ display: 'flex', alignItems: 'center', gap: 'var(--sp-2)', background: 'var(--bg-surface)', border: '1px solid var(--border-default)', borderRadius: 'var(--radius-md)', padding: 'var(--sp-3)' }}>
              <Shield size={13} color="var(--text-tertiary)" />
              <div>
                <div style={{ fontWeight: 600, fontSize: 'var(--text-sm)', color: 'var(--text-primary)' }}>{RULE_META[rid] ?? rid}</div>
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: 'var(--text-xs)', color: 'var(--text-tertiary)' }}>{rid}</div>
              </div>
            </div>
          ))}
        </div>
      </div>
      <div>
        <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-tertiary)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 'var(--sp-2)' }}>Decision Reason</div>
        <p style={{ fontSize: 'var(--text-sm)', margin: 0, lineHeight: 1.7 }}>{auth.reason}</p>
      </div>
      <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-tertiary)', fontFamily: 'var(--font-mono)', lineHeight: 1.6 }}>
        <span style={{ color: 'var(--text-secondary)', fontWeight: 600 }}>Security note: </span>
        This decision was made by the server-side deterministic policy engine.
        The frontend never computed or decided this result.
      </div>
    </div>
  )
}
