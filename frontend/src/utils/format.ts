// Utility helpers for the UI layer
import type { Decision } from '../types/api'

export function formatINR(amount: number): string {
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    maximumFractionDigits: 2,
  }).format(amount)
}

export function formatDate(iso: string): string {
  return new Date(iso).toLocaleString('en-IN', {
    day: '2-digit', month: 'short', year: 'numeric',
    hour: '2-digit', minute: '2-digit',
    hour12: true,
  })
}

export function shortHash(hash?: string): string {
  if (!hash || hash === 'GENESIS') return hash ?? ''
  const raw = hash.replace('sha256:', '')
  return `${raw.slice(0, 8)}…${raw.slice(-6)}`
}

export function decisionClass(d: Decision | string): string {
  if (d === 'ALLOW') return 'allow'
  if (d === 'DENY')  return 'deny'
  return 'human'
}

export function decisionLabel(d: Decision | string): string {
  if (d === 'ALLOW') return 'ALLOW'
  if (d === 'DENY')  return 'DENY'
  return 'HUMAN APPROVAL'
}

export function pct(v: number): string {
  return `${Math.round(v * 100)}%`
}

// Signal metadata — human-readable labels and descriptions
export const SIGNAL_META: Record<string, { label: string; desc: string }> = {
  amount_match: {
    label: 'Amount Match',
    desc: 'Proposed amount matches the amount in the verified evidence document.',
  },
  payee_match: {
    label: 'Payee Match',
    desc: 'Proposed payee name sufficiently matches the vendor in evidence (≥85% similarity).',
  },
  evidence_present: {
    label: 'Evidence Present',
    desc: 'A supporting invoice or receipt was provided with this transaction.',
  },
  evidence_extraction_ok: {
    label: 'Evidence Quality',
    desc: 'Evidence was successfully extracted with sufficient confidence (≥70%).',
  },
  currency_match: {
    label: 'Currency Match',
    desc: 'Proposed currency matches the currency in the evidence document.',
  },
  amount_within_limit: {
    label: 'Within Spending Limit',
    desc: 'Transaction amount is within your authorised spending limit.',
  },
  payee_seen_before: {
    label: 'Known Payee',
    desc: 'This payee has received a payment from your account before.',
  },
}

// Rule ID → human readable
export const RULE_META: Record<string, string> = {
  deny_evidence_missing_high_amount:        'No evidence — high amount',
  deny_amount_mismatch:                     'Amount mismatch',
  deny_payee_mismatch:                      'Payee mismatch',
  deny_low_confidence_extraction:           'Low-confidence evidence extraction',
  human_approval_exceeds_limit:             'Exceeds spending limit',
  human_approval_unknown_payee_medium_amount: 'Unknown payee — medium amount',
  allow_full_match:                         'Full evidence match',
  allow_small_no_evidence:                  'Small payment — no evidence required',
}
