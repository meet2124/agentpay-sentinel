import { useState, useRef } from 'react'
import { Upload, FileText, CheckCircle2, XCircle, Loader2, Eye, Trash2 } from 'lucide-react'
import { api } from '../services/api'
import type { Evidence } from '../types/api'
import { formatDate, formatINR } from '../utils/format'

export default function EvidencePage() {
  const [evidence, setEvidence] = useState<Evidence | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)

  async function handleUpload(file: File) {
    setLoading(true)
    setError(null)
    try {
      const ev = await api.uploadEvidence(file)
      setEvidence(ev)
    } catch (e: any) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="page-content animate-fade-in">
      <div className="page-header">
        <h1 className="page-title">
          <FileText size={24} style={{ display: 'inline', marginRight: 10, color: 'var(--accent)' }} />
          Evidence
        </h1>
        <p className="page-subtitle">
          Upload invoices, receipts, or purchase orders to attach as supporting evidence for a payment.
          Extraction is performed server-side only.
        </p>
      </div>

      {/* Extraction note */}
      <div className="alert alert-info" style={{ marginBottom: 'var(--sp-6)' }}>
        <Eye size={15} style={{ flexShrink: 0 }} />
        <div>
          <strong>Server-side only:</strong> Evidence processing, field extraction, and confidence scoring happen
          exclusively on the backend. The frontend displays what the server extracted — it does not perform any parsing locally.
          {' '}In Milestone 1, extraction uses a deterministic stub adapter.
        </div>
      </div>

      <div className="grid-2" style={{ alignItems: 'start' }}>

        {/* Upload panel */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--sp-4)' }}>
          <div className="card">
            <h3 style={{ marginBottom: 'var(--sp-4)', fontSize: 'var(--text-md)' }}>Upload Evidence Document</h3>

            {loading ? (
              <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 'var(--sp-4)', padding: 'var(--sp-8)' }}>
                <div className="spinner" style={{ width: 32, height: 32 }} />
                <div style={{ color: 'var(--text-secondary)', fontSize: 'var(--text-sm)' }}>
                  Uploading and extracting evidence…
                </div>
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
                  if (f) handleUpload(f)
                }}
              >
                <div className="upload-icon"><Upload size={26} /></div>
                <div style={{ fontWeight: 600, fontSize: 'var(--text-md)', marginBottom: 'var(--sp-2)', color: 'var(--text-primary)' }}>
                  Drop your invoice here
                </div>
                <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-tertiary)', marginBottom: 'var(--sp-4)' }}>
                  PDF, JPEG, PNG, WebP, or JSON
                </div>
                <button className="btn btn-secondary btn-sm" type="button">
                  <Upload size={13} />
                  Browse Files
                </button>
                <input
                  ref={fileRef} type="file"
                  accept=".pdf,.jpg,.jpeg,.png,.webp,.json"
                  style={{ display: 'none' }}
                  onChange={e => { const f = e.target.files?.[0]; if (f) handleUpload(f) }}
                />
              </div>
            )}

            {error && (
              <div className="alert alert-deny" style={{ marginTop: 'var(--sp-3)' }}>
                <XCircle size={14} style={{ flexShrink: 0 }} />
                {error}
              </div>
            )}
          </div>

          {/* How evidence flows */}
          <div className="card">
            <div style={{ fontSize: 'var(--text-xs)', fontWeight: 700, color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 'var(--sp-4)' }}>
              Evidence → Decision Flow
            </div>
            {[
              { step: '1', label: 'Document Uploaded', desc: 'Sent to backend via POST /evidence/upload' },
              { step: '2', label: 'Extraction', desc: 'Server extracts vendor, amount, currency, dates' },
              { step: '3', label: 'Confidence Scored', desc: 'Extraction confidence computed (threshold: 70%)' },
              { step: '4', label: 'Signal Comparison', desc: 'Compared against intent: payee + amount + currency' },
              { step: '5', label: 'Policy Input', desc: 'Signals feed the deterministic policy engine' },
            ].map(({ step, label, desc }) => (
              <div key={step} style={{ display: 'flex', gap: 'var(--sp-3)', marginBottom: 'var(--sp-4)' }}>
                <div style={{ width: 24, height: 24, borderRadius: 'var(--radius-sm)', background: 'var(--accent-dim)', border: '1px solid rgba(76,158,255,0.2)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 'var(--text-xs)', fontWeight: 700, color: 'var(--accent)', flexShrink: 0 }}>{step}</div>
                <div>
                  <div style={{ fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--text-primary)' }}>{label}</div>
                  <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-tertiary)' }}>{desc}</div>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Evidence viewer */}
        <div>
          {evidence ? (
            <div className="card animate-fade-in" style={{ display: 'flex', flexDirection: 'column', gap: 'var(--sp-5)' }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <h3 style={{ fontSize: 'var(--text-md)' }}>Extracted Evidence</h3>
                <div style={{ display: 'flex', gap: 'var(--sp-2)' }}>
                  <ExtractionBadge confidence={evidence.extraction_confidence} />
                  <button className="btn btn-ghost btn-sm" onClick={() => setEvidence(null)}>
                    <Trash2 size={13} />
                  </button>
                </div>
              </div>

              {/* Evidence ID */}
              <div style={{ background: 'var(--bg-surface)', borderRadius: 'var(--radius-md)', padding: 'var(--sp-3)', fontFamily: 'var(--font-mono)', fontSize: 'var(--text-xs)', color: 'var(--text-tertiary)' }}>
                evidence_id: <span style={{ color: 'var(--accent)' }}>{evidence.evidence_id}</span>
              </div>

              {/* Primary fields */}
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--sp-3)' }}>
                <FieldRow label="Vendor" value={evidence.vendor_name ?? '—'} />
                <FieldRow label="Amount" value={evidence.amount != null ? formatINR(evidence.amount) : '—'} highlight />
                <FieldRow label="Currency" value={evidence.currency ?? '—'} />
                <FieldRow label="Invoice #" value={evidence.invoice_number ?? '—'} />
                {evidence.invoice_date && <FieldRow label="Invoice Date" value={evidence.invoice_date} />}
                {evidence.vendor_gstin && <FieldRow label="GSTIN" value={evidence.vendor_gstin} />}
              </div>

              {/* Line items */}
              {evidence.line_items?.length > 0 && (
                <div>
                  <div style={{ fontSize: 'var(--text-xs)', fontWeight: 700, color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 'var(--sp-3)' }}>
                    Line Items
                  </div>
                  <div className="table-container">
                    <table>
                      <thead>
                        <tr>
                          <th>Description</th>
                          <th>Qty</th>
                          <th>Unit Price</th>
                          <th>Total</th>
                        </tr>
                      </thead>
                      <tbody>
                        {evidence.line_items.map((item, i) => (
                          <tr key={i}>
                            <td style={{ color: 'var(--text-primary)' }}>{item.description}</td>
                            <td style={{ fontFamily: 'var(--font-mono)' }}>{item.quantity}</td>
                            <td style={{ fontFamily: 'var(--font-mono)' }}>₹{item.unit_price}</td>
                            <td style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-primary)', fontWeight: 600 }}>₹{item.total}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {/* Extraction meta */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--sp-2)', background: 'var(--bg-surface)', borderRadius: 'var(--radius-md)', padding: 'var(--sp-4)' }}>
                <div style={{ fontSize: 'var(--text-xs)', fontWeight: 700, color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>Extraction Metadata</div>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 'var(--sp-3)' }}>
                  <div>
                    <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-tertiary)', marginBottom: 3 }}>Method</div>
                    <div style={{ fontFamily: 'var(--font-mono)', fontSize: 'var(--text-sm)', color: 'var(--text-primary)' }}>{evidence.extraction_method}</div>
                  </div>
                  <div>
                    <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-tertiary)', marginBottom: 3 }}>Confidence</div>
                    <div style={{ fontFamily: 'var(--font-mono)', fontSize: 'var(--text-sm)', color: evidence.extraction_confidence >= 0.7 ? 'var(--allow)' : 'var(--deny)', fontWeight: 700 }}>
                      {Math.round(evidence.extraction_confidence * 100)}%
                    </div>
                  </div>
                  <div>
                    <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-tertiary)', marginBottom: 3 }}>Extracted At</div>
                    <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-secondary)' }}>{formatDate(evidence.extracted_at)}</div>
                  </div>
                </div>
              </div>
            </div>
          ) : (
            <div style={{ border: '2px dashed var(--border-subtle)', borderRadius: 'var(--radius-xl)', padding: 'var(--sp-12)', textAlign: 'center', color: 'var(--text-tertiary)' }}>
              <FileText size={40} style={{ marginBottom: 'var(--sp-4)', opacity: 0.3 }} />
              <div style={{ fontWeight: 600 }}>No evidence uploaded</div>
              <div style={{ fontSize: 'var(--text-sm)', marginTop: 'var(--sp-2)' }}>
                Upload a document to see extracted fields here.
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function ExtractionBadge({ confidence }: { confidence: number }) {
  const ok = confidence >= 0.7
  return (
    <span className={`badge ${ok ? 'badge-allow' : 'badge-deny'}`}>
      {ok ? <CheckCircle2 size={10} /> : <XCircle size={10} />}
      {Math.round(confidence * 100)}% confidence
    </span>
  )
}

function FieldRow({ label, value, highlight }: { label: string; value: string; highlight?: boolean }) {
  return (
    <div style={{ background: 'var(--bg-surface)', borderRadius: 'var(--radius-md)', padding: 'var(--sp-3)' }}>
      <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-tertiary)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 4 }}>{label}</div>
      <div style={{ fontFamily: 'var(--font-mono)', fontWeight: 700, color: highlight ? 'var(--allow)' : 'var(--text-primary)', fontSize: 'var(--text-sm)' }}>{value}</div>
    </div>
  )
}
