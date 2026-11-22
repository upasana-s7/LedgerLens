const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || "http://localhost:8000").replace(/\/$/, "");

export class ApiError extends Error {
  status: number;
  detail: string;
  constructor(status: number, detail: string) {
    super(detail); this.name = "ApiError"; this.status = status; this.detail = detail;
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  let response: Response;
  try { response = await fetch(`${API_BASE_URL}/api${path}`, { ...options, credentials: "include" }); }
  catch { throw new Error("Cannot reach the API. Start the backend and check VITE_API_BASE_URL."); }
  const payload = response.status === 204 ? {} : await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = typeof payload.detail === "string" ? payload.detail : `Request failed (${response.status})`;
    throw new ApiError(response.status, detail);
  }
  return payload as T;
}


export interface AuthUser { id: string; name: string; email: string; }
export interface AuthCredentials { email: string; password: string; }
export interface RegisterInput extends AuthCredentials { name: string; }

/**
 * Authentication uses an HttpOnly, server-managed session cookie.
 * The browser never reads or stores passwords or session tokens.
 */
export function register(input: RegisterInput): Promise<AuthUser> {
  return request<AuthUser>("/auth/register", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(input),
  });
}
export function login(input: AuthCredentials): Promise<AuthUser> {
  return request<AuthUser>("/auth/login", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(input),
  });
}
export function getCurrentUser(): Promise<AuthUser> { return request<AuthUser>("/auth/me"); }
export function logout(): Promise<void> { return request<void>("/auth/logout", { method: "POST" }); }
export function updateCurrentUser(input: { name: string; email: string }): Promise<AuthUser> {
  return request<AuthUser>("/auth/me", {
    method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(input),
  });
}

export interface DashboardTransaction {
  id: string; name: string; category: string; date: string; amount: number; type: "income" | "expense";
}
export interface Transaction extends DashboardTransaction {}
export interface TransactionsResponse { total: number; page: number; limit: number; items: Transaction[]; }
export interface CreateTransactionInput {
  name: string; amount: number; type: "income" | "expense"; category?: string; date?: string;
}
export interface CsvUploadResponse {
  imported: number; skipped: number; rows: Transaction[]; errors: { row: number; message: string }[];
}
export interface DashboardResponse {
  workspace: { name: string; type: string; city: string; is_sample_data: boolean };
  period: { label: string; start: string; end: string };
  as_of_date: string;
  kpis: {
    available_cash: { value: number; change: string; note: string; tone: string };
    projected_30d: { value: number; change: string; note: string; tone: string };
    overdue_receivables: { value: number; change: string; note: string; tone: string };
    safe_to_spend: { value: number; change: string; note: string; tone: string };
  };
  cashflow_series: { month: string; month_iso: string; actual: number | null; forecast: number | null }[];
  series_range_label: string; insight: string;
  ai_cfo: { tag: string; title: string; body: string; updated_at: string; source: "rules" | "gemini" };
  risk_items: { tone: string; title: string; detail: string }[];
  recent_transactions: DashboardTransaction[];
}
export function getDashboard(): Promise<DashboardResponse> { return request<DashboardResponse>("/dashboard"); }
export interface CashFlowForecastResponse {
  opening_balance: number;
  inflows_30d: number;
  outflows_30d: number;
  series: { month: string; month_iso: string; actual: number | null; forecast: number | null }[];
  daily_series: { date: string; balance: number }[];
  range_label: string;
  commitments: { label: string; amount: number; date: string }[];
  assumptions: string[];
  lowest_balance: { value: number; date: string };
  shortfall_date: string | null;
  is_sample_data: boolean;
}
export function getCashFlowForecast(days = 90): Promise<CashFlowForecastResponse> {
  return request<CashFlowForecastResponse>(`/cashflow/forecast?days=${days}`);
}

export function getTransactions(params: { q?: string; type?: "income" | "expense"; page?: number; limit?: number } = {}): Promise<TransactionsResponse> {
  const search = new URLSearchParams();
  if (params.q) search.set("q", params.q);
  if (params.type) search.set("type", params.type);
  search.set("page", String(params.page ?? 1)); search.set("limit", String(params.limit ?? 200));
  return request<TransactionsResponse>(`/transactions?${search.toString()}`);
}
export function createTransaction(input: CreateTransactionInput): Promise<Transaction> {
  return request<Transaction>("/transactions", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(input) });
}
export function uploadTransactions(file: File): Promise<CsvUploadResponse> {
  const form = new FormData(); form.append("file", file);
  return request<CsvUploadResponse>("/transactions/upload", { method: "POST", body: form });
}


export interface SimulatorResponse {
  base_balance: number; scenario_cost: number; additional_revenue: number;
  projected_balance: number; verdict: string; verdict_label: string;
  threshold: number; explanation: string; explanation_source: string;
}
export function runSimulator(input: { purchase_amount: number; revenue_uplift_pct: number }): Promise<SimulatorResponse> {
  return request<SimulatorResponse>("/simulator/run", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(input) });
}

export interface RiskEvidence { kind: string; id: string; label: string; }
export interface RiskAlert {
  id: string; severity: string; tone: string; title: string; subtitle: string;
  metric: string; body: string; impact_label: string; impact_value: string;
  action_label: string; evidence: RiskEvidence[];
}
export interface RiskAlertsResponse {
  summary: { attention_count: number; note: string; tag: string };
  alerts: RiskAlert[];
}
export function getRiskAlerts(): Promise<RiskAlertsResponse> { return request<RiskAlertsResponse>("/risk/alerts"); }

export interface CopilotMessage { role: "user" | "assistant"; text: string; }
export interface CopilotChatResponse {
  reply: string; suggested_questions: string[];
  citations: { kind: string; id: string; label: string }[];
  source: "gemini" | "fallback";
}
export interface CopilotSuggestionsResponse { chips: string[]; panel: string[]; }
export function getCopilotSuggestions(): Promise<CopilotSuggestionsResponse> { return request<CopilotSuggestionsResponse>("/copilot/suggestions"); }
export function sendCopilotMessage(message: string, history: CopilotMessage[]): Promise<CopilotChatResponse> {
  return request<CopilotChatResponse>("/copilot/chat", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ message, history: history.slice(-8) }) });
}

export interface Invoice {
  id: string; client: string; due_date: string; amount: number;
  status: "Draft" | "Pending" | "Overdue" | "Paid"; days_overdue: number;
}
export interface InvoicesResponse {
  summary: { total_outstanding: number; outstanding_count: number; overdue_total: number; collected_this_month: number };
  items: Invoice[];
}
export interface InvoiceUploadResponse {
  id: string; status: "Draft"; fields: { client: string; due_date: string; amount: number; invoice_number: string };
  confidence: number; warnings: string[];
}
export interface InvoiceConfirmResponse { id: string; status: string; invoice: Invoice; }
export interface MarkPaidResponse { id: string; status: "Paid"; paid_at: string; outstanding_total: number; overdue_count: number; }
export function getInvoices(): Promise<InvoicesResponse> { return request<InvoicesResponse>("/invoices"); }
export function uploadInvoice(file: File): Promise<InvoiceUploadResponse> {
  const form = new FormData(); form.append("file", file);
  return request<InvoiceUploadResponse>("/invoices/upload", { method: "POST", body: form });
}
export function confirmInvoice(id: string, input: { client: string; due_date: string; amount: number; invoice_number: string }): Promise<InvoiceConfirmResponse> {
  return request<InvoiceConfirmResponse>(`/invoices/${encodeURIComponent(id)}/confirm`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(input) });
}
export function markInvoicePaid(id: string): Promise<MarkPaidResponse> {
  return request<MarkPaidResponse>(`/invoices/${encodeURIComponent(id)}/mark-paid`, { method: "POST" });
}

export interface ReceivablesResponse {
  outstanding_total: number; overdue_count: number; collection_progress_pct: number;
  aging_buckets: { label: string; count: number; amount: number }[];
  items: Invoice[];
}
export function getReceivables(): Promise<ReceivablesResponse> { return request<ReceivablesResponse>("/receivables"); }
