// AgentPay Sentinel — TypeScript API Types
// Mirror the FastAPI Pydantic models exactly. Do not invent fields.

// ─── Auth ────────────────────────────────────────────────────────────────────

export interface SessionCreateRequest {
  user_id: string;
  api_key: string;
}

export interface User {
  user_id: string;
  name: string;
  email: string;
  tier: 'BASIC' | 'STANDARD' | 'PREMIUM' | 'ENTERPRISE';
  spending_limit_inr: number;
  daily_limit_inr?: number;
  created_at: string;
  is_active: boolean;
}

export interface SessionCreateResponse {
  session_id: string;
  token: string;
  expires_at: string;
  user: User;
}

// ─── Evidence ────────────────────────────────────────────────────────────────

export interface EvidenceItem {
  description: string;
  quantity: number;
  unit_price: number;
  total: number;
  hsn_code?: string;
}

export interface Evidence {
  evidence_id: string;
  intent_id?: string;
  user_id: string;
  source_type: string;
  s3_key?: string;
  original_filename?: string;
  vendor_name?: string;
  vendor_gstin?: string;
  vendor_address?: string;
  amount?: number;
  currency?: string;
  tax_amount?: number;
  invoice_number?: string;
  invoice_date?: string;
  due_date?: string;
  line_items: EvidenceItem[];
  notes?: string;
  extraction_method: string;
  extraction_confidence: number;
  extracted_at: string;
}

// ─── Payments / Authorization ─────────────────────────────────────────────────

export interface TransactionSignals {
  intent_id: string;
  evidence_id?: string;
  amount_match: boolean;
  amount_delta_inr: number;
  payee_match: boolean;
  payee_similarity: number;
  evidence_present: boolean;
  evidence_extraction_ok: boolean;
  evidence_extraction_confidence: number;
  currency_match: boolean;
  amount_within_limit: boolean;
  amount_vs_limit_ratio: number;
  payee_seen_before: boolean;
  display_risk_score: number;
  computed_at: string;
}

export type Decision = 'ALLOW' | 'DENY' | 'REQUIRE_HUMAN_APPROVAL';

export interface MockPaymentResult {
  status: string;
  transaction_id: string;
  payee: string;
  amount: number;
  currency: string;
  simulated_at: string;
  disclaimer: string;
}

export interface AuthorizationDecision {
  decision_id: string;
  intent_id: string;
  user_id: string;
  decision: Decision;
  reason: string;
  matched_rule_ids: string[];
  signals: TransactionSignals;
  requires_human: boolean;
  human_approved?: boolean;
  human_reviewed_at?: string;
  payment_result?: MockPaymentResult;
  expires_at: string;
  decided_at: string;
}

export interface EvaluateRequest {
  raw_input: string;
  evidence_id?: string;
}

export interface EvaluateResponse {
  authorization: AuthorizationDecision;
  audit_event_id: string;
}

// ─── Audit ───────────────────────────────────────────────────────────────────

export interface AuditEvent {
  event_id: string;
  event_type: string;
  user_id: string;
  session_id?: string;
  intent_id?: string;
  evidence_id?: string;
  decision_id?: string;
  decision?: string;
  intent_snapshot?: Record<string, unknown>;
  evidence_snapshot?: Record<string, unknown>;
  signals_snapshot?: Record<string, unknown>;
  policy_snapshot?: Record<string, unknown>;
  payment_result_snapshot?: Record<string, unknown>;
  event_hash?: string;
  prev_event_hash?: string;
  chained_hash?: string;
  timestamp: string;
}

export interface AuditListResponse {
  events: AuditEvent[];
  total: number;
  offset: number;
  limit: number;
}

export interface ChainVerifyResponse {
  user_id: string;
  events_checked: number;
  chain_valid: boolean;
  errors: string[];
}

// ─── Policy ──────────────────────────────────────────────────────────────────

export interface PolicyRule {
  rule_id: string;
  name: string;
  description: string;
  condition: string;
  action: Decision;
  priority: number;
  is_active: boolean;
  version: string;
}

export interface PolicyListResponse {
  rules: PolicyRule[];
  total: number;
  version: string;
  note: string;
}

// ─── API Errors ───────────────────────────────────────────────────────────────

export interface ApiError {
  error: string;
  status_code: number;
  path?: string;
}
