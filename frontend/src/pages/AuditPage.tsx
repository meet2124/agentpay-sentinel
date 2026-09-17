import { useState, useEffect, useCallback } from 'react'
import { Activity, RefreshCw, CheckCircle2, XCircle, ChevronDown, ChevronUp, Shield, Clock } from 'lucide-react'
import { api } from '../services/api'
import type { AuditEvent, ChainVerifyResponse } from '../types/api'
import { formatDate, shortHash } from '../utils/format'

const EVENT_TYPE_LABELS: Record<string, string> = {
  SESSION_CREATED:         'Session Created',
  INTENT_EXTRACTED:        'Intent Extracted',
  EVIDENCE_UPLOADED:       'Evidence Uploaded',
  EVIDENCE_EXTRACTED:      'Evidence Extracted',
  SIGNALS_COMPUTED:        'Signals Computed',
  POLICY_EVALUATED:        'Policy Evaluated',
  AUTHORIZATION_DECISION:  'Authorization Decision',
  HUMAN_APPROVAL_REQUESTED:'Human Approval Requested',
  HUMAN_APPROVED:          'Human Approved',
  HUMAN_DENIED:            'Human Denied',
  PAYMENT_SIMULATED:       'Payment Simulated',
  PAYMENT_DENIED:          'Payment Denied',
}

export default function AuditPage() {
  const [events, setEvents] = useState<AuditEvent[]>([])
  const [total, setTotal] = useState(0)
  const [chain, setChain] = useState<ChainVerifyResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [chainLoading, setChainLoading] = useState(false)
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await api.getAuditEvents({ limit: 50 })
      setEvents(res.events)
      setTotal(res.total)
    } catch (e: any) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }, [])

  const verifyChain = useCallback(async () => {
    setChainLoading(true)
    try {
      const res = await api.verifyAuditChain()
      setChain(res)
    } catch (e: any) {
      setError(e.message)
    } finally {
      setChainLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
    verifyChain()
  }, [load, verifyChain])

  function toggleExpand(id: string) {
    setExpandedId(prev => prev === id ? null : id)
  }

  return (
    <div className="page-content animate-fade-in">
      <div className="page-header">
        <h1 className="page-title">
          <Activity size={24} style={{ display: 'inline', marginRight: 10, color: 'var(--accent)' }} />
          Audit Trail
        </h1>
        <p className="page-subtitle">
          Tamper-evident, cryptographically verifiable record of all Trust Gateway events.
          Each event is SHA-256 hashed and chained to the previous event.
        </p>
      </div>

      {/* Chain verification banner */}
      <div style={{ marginBottom: 'var(--sp-6)' }}>
        {chainLoading ? (
          <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--sp-3)', padding: 'var(--sp-5)', background: 'var(--bg-surface)', border: '1px solid var(--border-subtle)', borderRadius: 'var(--radius-lg)' }}>
            <div className="spinner" />
            <span style={{ color: 'var(--text-secondary)', fontWeight: 600, letterSpacing: '0.05em', textTransform: 'uppercase' }}>Verifying SHA-256 chain…</span>
          </div>
        ) : chain ? (
          chain.chain_valid ? (
            <div style={{
              display: 'flex', alignItems: 'center', gap: 'var(--sp-4)', padding: 'var(--sp-5)',
              background: 'rgba(16,185,129,0.1)', border: '1px solid rgba(16,185,129,0.3)',
              borderRadius: 'var(--radius-xl)', color: 'var(--allow)',
              boxShadow: '0 4px 24px rgba(16,185,129,0.05)'
            }}>
              <Shield size={32} strokeWidth={2.5} />
              <div>
                <div style={{ fontWeight: 800, fontSize: 'var(--text-lg)', letterSpacing: '0.05em', textTransform: 'uppercase' }}>SHA-256 Chain Intact</div>
                <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-primary)', marginTop: 2, fontFamily: 'var(--font-mono)' }}>
                  {chain.events_checked} event{chain.events_checked !== 1 ? 's' : ''} cryptographically verified · No tampering detected
                </div>
              </div>
              <button className="btn btn-ghost btn-sm" onClick={verifyChain} style={{ marginLeft: 'auto', color: 'var(--allow)', background: 'rgba(16,185,129,0.1)' }}>
                <RefreshCw size={14} /> Re-verify
              </button>
            </div>
          ) : (
            <div style={{
              display: 'flex', alignItems: 'flex-start', gap: 'var(--sp-4)', padding: 'var(--sp-5)',
              background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.3)',
              borderRadius: 'var(--radius-xl)', color: 'var(--deny)',
              boxShadow: '0 4px 24px rgba(239,68,68,0.1)'
            }}>
              <XCircle size={32} strokeWidth={2.5} style={{ marginTop: 2 }} />
              <div style={{ flex: 1 }}>
                <div style={{ fontWeight: 800, fontSize: 'var(--text-lg)', letterSpacing: '0.05em', textTransform: 'uppercase' }}>⚠ Chain Integrity Failure</div>
                <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-primary)', marginTop: 2, fontFamily: 'var(--font-mono)' }}>
                  {chain.errors.length} error{chain.errors.length !== 1 ? 's' : ''} detected. The audit chain has been tampered with.
                </div>
                {chain.errors.length > 0 && (
                  <ul style={{ marginTop: 'var(--sp-3)', fontSize: 'var(--text-xs)', color: 'var(--deny)', paddingLeft: 'var(--sp-4)', background: 'rgba(239,68,68,0.1)', padding: 'var(--sp-3)', borderRadius: 'var(--radius-md)', fontFamily: 'var(--font-mono)' }}>
                    {chain.errors.slice(0, 3).map((e, i) => <li key={i} style={{ marginBottom: 4 }}>{e}</li>)}
                  </ul>
                )}
              </div>
              <button className="btn btn-ghost btn-sm" onClick={verifyChain} style={{ color: 'var(--deny)', background: 'rgba(239,68,68,0.1)' }}>
                <RefreshCw size={14} /> Re-verify
              </button>
            </div>
          )
        ) : null}
      </div>

      {/* Controls */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 'var(--sp-4)' }}>
        <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-tertiary)' }}>
          {total} total event{total !== 1 ? 's' : ''} · Showing {events.length}
        </div>
        <button className="btn btn-secondary btn-sm" onClick={load} disabled={loading}>
          <RefreshCw size={13} style={{ animation: loading ? 'spin 0.7s linear infinite' : undefined }} />
          Refresh
        </button>
      </div>

      {error && (
        <div className="alert alert-deny" style={{ marginBottom: 'var(--sp-4)' }}>
          <XCircle size={14} style={{ flexShrink: 0 }} />
          {error}
        </div>
      )}

      {/* Events list */}
      {events.length === 0 && !loading ? (
        <div style={{ textAlign: 'center', padding: 'var(--sp-12)', color: 'var(--text-tertiary)' }}>
          <Activity size={36} style={{ marginBottom: 'var(--sp-4)', opacity: 0.3 }} />
          <div style={{ fontWeight: 600 }}>No audit events yet</div>
          <div style={{ fontSize: 'var(--text-sm)', marginTop: 'var(--sp-2)' }}>
            Run an evaluation to generate audit events.
          </div>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--sp-2)' }}>
          {events.map((event, idx) => (
            <AuditEventRow
              key={event.event_id}
              event={event}
              index={idx}
              isExpanded={expandedId === event.event_id}
              onToggle={() => toggleExpand(event.event_id)}
            />
          ))}
        </div>
      )}

      {/* Chain design note */}
      <div className="card" style={{ marginTop: 'var(--sp-8)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--sp-3)', marginBottom: 'var(--sp-4)' }}>
          <Shield size={16} color="var(--accent)" />
          <span style={{ fontWeight: 700, fontSize: 'var(--text-sm)' }}>Tamper-Evident Design</span>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: 'var(--sp-4)' }}>
          {[
            { label: 'Event Hash', desc: "SHA-256 of each event\u2019s canonical JSON payload" },
            { label: 'Chained Hash', desc: 'SHA-256(event_hash + prev_event_hash)' },
            { label: 'Genesis Block', desc: 'First event uses GENESIS as prev_hash' },
            { label: 'Tamper Detection', desc: 'Modifying any field changes the hash, breaking all subsequent links' },
          ].map(({ label, desc }) => (
            <div key={label}>
              <div style={{ fontSize: 'var(--text-xs)', fontWeight: 700, color: 'var(--accent)', marginBottom: 4 }}>{label}</div>
              <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-tertiary)', lineHeight: 1.5 }}>{desc}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

function decisionBadgeClass(d?: string) {
  if (d === 'ALLOW') return 'badge-allow'
  if (d === 'DENY')  return 'badge-deny'
  if (d === 'REQUIRE_HUMAN_APPROVAL') return 'badge-human'
  return 'badge-info'
}

function AuditEventRow({ event, index, isExpanded, onToggle }: {
  event: AuditEvent; index: number; isExpanded: boolean; onToggle: () => void
}) {
  const isDecision = event.event_type === 'AUTHORIZATION_DECISION'

  return (
    <div className="card card-sm" style={{
      borderColor: isDecision ? (
        event.decision === 'ALLOW' ? 'rgba(34,197,94,0.15)' :
        event.decision === 'DENY' ? 'rgba(239,68,68,0.15)' :
        'rgba(245,158,11,0.15)'
      ) : 'var(--border-subtle)',
      animationDelay: `${index * 0.04}s`,
    }}>
      {/* Row header */}
      <div
        style={{ display: 'flex', alignItems: 'center', gap: 'var(--sp-3)', cursor: 'pointer' }}
        onClick={onToggle}
      >
        {/* Index dot */}
        <div style={{
          width: 28, height: 28, borderRadius: 'var(--radius-sm)',
          background: isDecision ? (
            event.decision === 'ALLOW' ? 'var(--allow-dim)' :
            event.decision === 'DENY' ? 'var(--deny-dim)' : 'var(--human-dim)'
          ) : 'var(--bg-surface)',
          border: '1px solid var(--border-default)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          fontSize: 'var(--text-xs)', fontFamily: 'var(--font-mono)', color: 'var(--text-tertiary)',
          flexShrink: 0,
        }}>
          {index + 1}
        </div>

        {/* Type */}
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontWeight: 600, fontSize: 'var(--text-sm)', color: 'var(--text-primary)' }}>
            {EVENT_TYPE_LABELS[event.event_type] ?? event.event_type}
          </div>
          <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-tertiary)', fontFamily: 'var(--font-mono)' }}>
            {event.event_id}
          </div>
        </div>

        {/* Decision badge */}
        {event.decision && (
          <span className={`badge ${decisionBadgeClass(event.decision)}`}>
            {event.decision === 'REQUIRE_HUMAN_APPROVAL' ? 'HUMAN' : event.decision}
          </span>
        )}

        {/* Timestamp */}
        <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-tertiary)', textAlign: 'right', flexShrink: 0 }}>
          <Clock size={10} style={{ display: 'inline', marginRight: 4 }} />
          {formatDate(event.timestamp)}
        </div>

        {/* Expand icon */}
        {isExpanded ? <ChevronUp size={14} color="var(--text-tertiary)" /> : <ChevronDown size={14} color="var(--text-tertiary)" />}
      </div>

      {/* Expanded detail */}
      {isExpanded && (
        <div style={{ marginTop: 'var(--sp-4)', borderTop: '1px solid var(--border-subtle)', paddingTop: 'var(--sp-4)', display: 'flex', flexDirection: 'column', gap: 'var(--sp-3)' }}>
          {/* Hash chain */}
          <div style={{ background: 'var(--bg-surface)', borderRadius: 'var(--radius-md)', padding: 'var(--sp-3)', display: 'flex', flexDirection: 'column', gap: 'var(--sp-2)' }}>
            <div style={{ fontSize: 'var(--text-xs)', fontWeight: 700, color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>Hash Chain</div>
            <HashRow label="event_hash" value={event.event_hash} />
            <HashRow label="prev_event_hash" value={event.prev_event_hash} />
            <HashRow label="chained_hash" value={event.chained_hash} />
          </div>

          {/* Refs */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(140px, 1fr))', gap: 'var(--sp-3)' }}>
            {event.intent_id && <RefItem label="intent_id" value={event.intent_id} />}
            {event.evidence_id && <RefItem label="evidence_id" value={event.evidence_id} />}
            {event.decision_id && <RefItem label="decision_id" value={event.decision_id} />}
            {event.session_id && <RefItem label="session_id" value={event.session_id} />}
          </div>
        </div>
      )}
    </div>
  )
}

function HashRow({ label, value }: { label: string; value?: string }) {
  if (!value) return null
  return (
    <div style={{ display: 'flex', gap: 'var(--sp-3)', alignItems: 'flex-start' }}>
      <span style={{ fontFamily: 'var(--font-mono)', fontSize: 'var(--text-xs)', color: 'var(--accent)', minWidth: 140, flexShrink: 0 }}>{label}</span>
      <span className="hash-value" style={{ fontSize: 'var(--text-xs)' }}>
        {value === 'GENESIS' ? (
          <span style={{ color: 'var(--human)', fontWeight: 600 }}>GENESIS</span>
        ) : value}
      </span>
    </div>
  )
}

function RefItem({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-tertiary)', fontWeight: 600, marginBottom: 3 }}>{label}</div>
      <div style={{ fontFamily: 'var(--font-mono)', fontSize: 'var(--text-xs)', color: 'var(--text-secondary)', wordBreak: 'break-all' }}>{value}</div>
    </div>
  )
}
