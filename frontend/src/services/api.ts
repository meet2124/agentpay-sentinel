// AgentPay Sentinel — API Client
// Single source of truth for all backend communication.
// Frontend NEVER decides authorization. Backend is the authority.

import axios from 'axios'
import type { AxiosInstance, AxiosError } from 'axios';
import type {
  SessionCreateRequest,
  SessionCreateResponse,
  EvaluateRequest,
  EvaluateResponse,
  Evidence,
  AuditListResponse,
  ChainVerifyResponse,
  PolicyListResponse,
  AuthorizationDecision,
  ApiError,
} from '../types/api';

const BASE_URL = import.meta.env.VITE_API_BASE_URL || (import.meta.env.PROD ? 'https://ji7x942vif.execute-api.ap-south-1.amazonaws.com' : 'http://localhost:8000');

class SentinelApiClient {
  private http: AxiosInstance;

  constructor() {
    this.http = axios.create({
      baseURL: BASE_URL,
      headers: { 'Content-Type': 'application/json' },
      timeout: 15000,
    });

    // Attach token to every request
    this.http.interceptors.request.use((config) => {
      const token = this.getToken();
      if (token) {
        config.headers.Authorization = `Bearer ${token}`;
      }
      return config;
    });

    // Normalize errors
    this.http.interceptors.response.use(
      (r) => r,
      (err: AxiosError<ApiError>) => {
        const msg = err.response?.data?.error ?? err.message ?? 'Network error';
        return Promise.reject(new Error(msg));
      }
    );
  }

  // ─── Token management ──────────────────────────────────────────────────────

  private getToken(): string | null {
    return sessionStorage.getItem('sentinel_token');
  }

  setToken(token: string): void {
    sessionStorage.setItem('sentinel_token', token);
  }

  clearToken(): void {
    sessionStorage.removeItem('sentinel_token');
    sessionStorage.removeItem('sentinel_user');
  }

  isAuthenticated(): boolean {
    return !!this.getToken();
  }

  // ─── Auth ─────────────────────────────────────────────────────────────────

  async createSession(body: SessionCreateRequest): Promise<SessionCreateResponse> {
    const r = await this.http.post<SessionCreateResponse>('/auth/session', body);
    this.setToken(r.data.token);
    sessionStorage.setItem('sentinel_user', JSON.stringify(r.data.user));
    return r.data;
  }

  async getMe() {
    const r = await this.http.get('/auth/me');
    return r.data;
  }

  // ─── Evidence ─────────────────────────────────────────────────────────────

  async uploadEvidence(file: File): Promise<Evidence> {
    const form = new FormData();
    form.append('file', file);
    const r = await this.http.post<Evidence>('/evidence/upload', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return r.data;
  }

  async getEvidence(evidenceId: string): Promise<Evidence> {
    const r = await this.http.get<Evidence>(`/evidence/${evidenceId}`);
    return r.data;
  }

  // ─── Payments ─────────────────────────────────────────────────────────────

  async evaluatePayment(body: EvaluateRequest): Promise<EvaluateResponse> {
    // SECURITY: frontend never decides authorization.
    // All signals, policy evaluation, and decision come from backend.
    const r = await this.http.post<EvaluateResponse>('/payments/evaluate', body);
    return r.data;
  }

  async approvePayment(decisionId: string): Promise<AuthorizationDecision> {
    // Human approves a REQUIRE_HUMAN_APPROVAL decision.
    // Backend enforces ownership, expiry, binding hash, and replay protection.
    const r = await this.http.post<AuthorizationDecision>(`/payments/${decisionId}/approve`, {});
    return r.data;
  }

  async denyPayment(decisionId: string): Promise<AuthorizationDecision> {
    // Human explicitly denies a REQUIRE_HUMAN_APPROVAL decision.
    // No payment is ever executed on denial.
    const r = await this.http.post<AuthorizationDecision>(`/payments/${decisionId}/deny`, {});
    return r.data;
  }

  // ─── Audit ────────────────────────────────────────────────────────────────

  async getAuditEvents(params?: {
    limit?: number;
    offset?: number;
    decision?: string;
  }): Promise<AuditListResponse> {
    const r = await this.http.get<AuditListResponse>('/audit/events', { params });
    return r.data;
  }

  async getAuditEvent(eventId: string) {
    const r = await this.http.get(`/audit/events/${eventId}`);
    return r.data;
  }

  async verifyAuditChain(): Promise<ChainVerifyResponse> {
    const r = await this.http.get<ChainVerifyResponse>('/audit/verify');
    return r.data;
  }

  // ─── Policy ───────────────────────────────────────────────────────────────

  async getPolicyRules(): Promise<PolicyListResponse> {
    const r = await this.http.get<PolicyListResponse>('/policies/rules');
    return r.data;
  }

  // ─── Health ───────────────────────────────────────────────────────────────

  async health() {
    const r = await this.http.get('/health');
    return r.data;
  }
}

export const api = new SentinelApiClient();
