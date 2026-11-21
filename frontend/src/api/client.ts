const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || "http://localhost:8000").replace(/\/$/, "");

export class ApiError extends Error {
  status: number;
  detail: string;
  constructor(status: number, detail: string) {
    super(detail);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

async function request<T>(path: string): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}/api${path}`);
  } catch {
    throw new Error("Cannot reach the API. Start the backend and check VITE_API_BASE_URL.");
  }
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = typeof payload.detail === "string" ? payload.detail : `Request failed (${response.status})`;
    throw new ApiError(response.status, detail);
  }
  return payload as T;
}

export interface DashboardTransaction {
  id: string;
  name: string;
  category: string;
  date: string;
  amount: number;
  type: "income" | "expense";
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
  series_range_label: string;
  insight: string;
  ai_cfo: { tag: string; title: string; body: string; updated_at: string; source: "rules" | "gemini" };
  risk_items: { tone: string; title: string; detail: string }[];
  recent_transactions: DashboardTransaction[];
}

export function getDashboard(): Promise<DashboardResponse> {
  return request<DashboardResponse>("/dashboard");
}
