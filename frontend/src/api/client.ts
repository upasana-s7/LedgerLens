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
  try { response = await fetch(`${API_BASE_URL}/api${path}`, options); }
  catch { throw new Error("Cannot reach the API. Start the backend and check VITE_API_BASE_URL."); }
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = typeof payload.detail === "string" ? payload.detail : `Request failed (${response.status})`;
    throw new ApiError(response.status, detail);
  }
  return payload as T;
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
