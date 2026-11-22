import { useEffect, useMemo, useState, type ReactNode, type FormEvent } from "react";
import { confirmInvoice, createTransaction, getCashFlowForecast, getCopilotSuggestions, getDashboard, getInvoices, getReceivables, getRiskAlerts, getTransactions, markInvoicePaid, runSimulator, sendCopilotMessage, uploadInvoice, uploadTransactions, getCurrentUser, login, logout, register, updateCurrentUser, type AuthUser, type CashFlowForecastResponse, type CopilotMessage, type DashboardResponse, type InvoiceUploadResponse, type Transaction } from "./api/client";
import {
  Activity, AlertCircle, ArrowDownRight, ArrowRight, ArrowUpRight, Bell,
  CalendarDays, CheckCircle2, ChevronDown, ChevronRight, Clock3, Compass,
  FileText, Gauge, Home, Lightbulb, Menu, MoreHorizontal, Paperclip,
  Plus, Search, Send, Settings, ShieldAlert, SlidersHorizontal, Sparkles,
  TrendingDown, TrendingUp, UploadCloud, Wallet, X, LogOut,
} from "lucide-react";
import {
  Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { Toaster, toast } from "sonner";

type Page = "Overview" | "Transactions" | "Cash Flow" | "What-If Simulator" | "Invoices" | "Risk Radar" | "AI Financial Copilot" | "Receivables" | "Account settings";
type DemoProfile = Pick<AuthUser, "name" | "email">;
const initials = (name: string) => name.trim().split(/\s+/).filter(Boolean).slice(0, 2).map(part => part[0]?.toUpperCase() ?? "").join("") || "U";

const navItems: { label: Page; icon: typeof Home }[] = [
  { label: "Overview", icon: Home },
  { label: "Transactions", icon: Activity },
  { label: "Cash Flow", icon: Wallet },
  { label: "What-If Simulator", icon: SlidersHorizontal },
  { label: "Invoices", icon: FileText },
  { label: "Risk Radar", icon: ShieldAlert },
  { label: "AI Financial Copilot", icon: Sparkles },
  { label: "Receivables", icon: Clock3 },
];

const cashData = [
  { month: "Jun", actual: 310000, forecast: 310000 },
  { month: "Jul", actual: 355000, forecast: 355000 },
  { month: "Aug", actual: 328000, forecast: 328000 },
  { month: "Sep", actual: 392000, forecast: 392000 },
  { month: "Oct", actual: 365000, forecast: 365000 },
  { month: "Nov", actual: 342500, forecast: 342500 },
  { month: "Dec", actual: null, forecast: 298000 },
  { month: "Jan", actual: null, forecast: 267000 },
  { month: "Feb", actual: null, forecast: 218000 },
];

const initialTransactions = [
  { id: "TXN-1048", name: "Aarav Foods — bulk order", category: "Sales", date: "19 Nov 2026", amount: 48500, type: "income" },
  { id: "TXN-1047", name: "FreshKart Wholesale", category: "Inventory", date: "18 Nov 2026", amount: -18400, type: "expense" },
  { id: "TXN-1046", name: "November workspace rent", category: "Rent", date: "17 Nov 2026", amount: -22000, type: "expense" },
  { id: "TXN-1045", name: "Cafe Bloom — catering", category: "Sales", date: "16 Nov 2026", amount: 32750, type: "income" },
  { id: "TXN-1044", name: "Electricity & utilities", category: "Utilities", date: "15 Nov 2026", amount: -6800, type: "expense" },
];


const money = (value: number) => new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 }).format(value);
const compactMoney = (value: number) => value >= 100000 ? `₹${(value / 100000).toFixed(1)}L` : `₹${Math.round(value / 1000)}k`;

function Brand() {
  return <div className="brand-lockup">
    <div className="brand-mark"><Compass size={23} strokeWidth={1.65} /></div>
    <div><div className="brand-name">LedgerLens</div><div className="brand-tagline">See beyond the numbers.</div></div>
  </div>;
}

function Sidebar({ page, setPage, open, close, profile }: { page: Page; setPage: (p: Page) => void; open: boolean; close: () => void; profile: DemoProfile }) {
  return <>
    {open && <button className="mobile-scrim" onClick={close} aria-label="Close menu" />}
    <aside className={`sidebar ${open ? "sidebar-open" : ""}`}>
      <div className="sidebar-top"><Brand /><button className="icon-button sidebar-close" onClick={close}><X size={18} /></button></div>
      <div className="workspace-switch"><div className="workspace-avatar">B</div><div className="workspace-copy"><strong>Bloom & Bean</strong><span>Small business</span></div><ChevronDown size={15} /></div>
      <div className="nav-label">WORKSPACE</div>
      <nav className="main-nav">
        {navItems.map(({ label, icon: Icon }) => <button key={label} className={`nav-item ${page === label ? "active" : ""}`} onClick={() => { setPage(label); close(); }}>
          <Icon size={18} strokeWidth={1.8} /><span>{label}</span>
          {label === "Risk Radar" && <span className="nav-count">2</span>}
        </button>)}
      </nav>
      <div className="sidebar-bottom">
        <div className="help-card"><div className="help-icon"><Lightbulb size={16} /></div><strong>A little more clarity?</strong><p>Explore insights to make your next move with confidence.</p><button onClick={() => setPage("AI Financial Copilot")}>Ask your AI CFO <ArrowRight size={14} /></button></div>
        <button className={`nav-item muted-nav ${page === "Account settings" ? "active" : ""}`} onClick={() => { setPage("Account settings"); close(); }}><Settings size={18} /><span>Account settings</span></button>
        <button className="profile-row profile-row-button" onClick={() => { setPage("Account settings"); close(); }}><div className="profile-avatar">{initials(profile.name)}</div><div className="profile-copy"><strong>{profile.name}</strong><span>{profile.email}</span></div><Settings size={16} /></button>
      </div>
    </aside>
  </>;
}

function Header({ page, onMenu, profile, onSettings, onSignOut }: { page: Page; onMenu: () => void; profile: DemoProfile; onSettings: () => void; onSignOut: () => void }) {
  const [profileOpen, setProfileOpen] = useState(false);
  return <header className="topbar">
    <div className="topbar-left"><button className="icon-button mobile-menu" onClick={onMenu}><Menu size={20} /></button><div className="breadcrumb">Workspace <ChevronRight size={14} /> <strong>{page}</strong></div></div>
    <div className="topbar-actions"><div className="period-pill"><CalendarDays size={15} /><span>Nov 2026</span><ChevronDown size={14} /></div><button className="icon-button notification-button" onClick={() => toast("You're all caught up.")} aria-label="Notifications"><Bell size={18} /><i /></button><div className="profile-menu-wrap"><button className="top-profile-button" onClick={() => setProfileOpen(value => !value)} aria-label="Open account menu" aria-expanded={profileOpen}><span className="top-avatar">{initials(profile.name)}</span><ChevronDown size={14} /></button>{profileOpen && <div className="profile-dropdown"><div className="profile-dropdown-heading"><strong>{profile.name}</strong><span>{profile.email}</span><small>Secure account</small></div><button onClick={() => { setProfileOpen(false); onSettings(); }}><Settings size={15} /> Account settings</button><button onClick={() => { setProfileOpen(false); onSignOut(); }}><LogOut size={15} /> Sign out</button></div>}</div></div>
  </header>;
}

function PageIntro({ eyebrow, title, description, action }: { eyebrow?: string; title: string; description: string; action?: ReactNode }) {
  return <div className="page-intro"><div><div className="eyebrow">{eyebrow || "YOUR BUSINESS, IN FOCUS"}</div><h1>{title}</h1><p>{description}</p></div>{action && <div className="intro-action">{action}</div>}</div>;
}

function MetricCard({ label, value, change, note, icon: Icon, tone = "green" }: { label: string; value: string; change?: string; note: string; icon: typeof Wallet; tone?: string }) {
  return <article className="metric-card"><div className="metric-top"><span>{label}</span><span className={`metric-icon ${tone}`}><Icon size={17} /></span></div><div className="metric-value">{value}</div><div className="metric-foot">{change && <span className={tone === "coral" ? "negative-change" : "positive-change"}>{change}</span>}<span>{note}</span></div></article>;
}

function CashFlowChart({ detailed = false, data = cashData }: { detailed?: boolean; data?: { month: string; actual: number | null; forecast: number | null }[] }) {
  return <div className={`chart-wrap ${detailed ? "chart-large" : ""}`}>
    <ResponsiveContainer width="100%" height="100%">
      <AreaChart data={data} margin={{ top: 10, right: 8, left: -18, bottom: 0 }}>
        <defs><linearGradient id="cashFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#6d9b83" stopOpacity={0.22} /><stop offset="95%" stopColor="#6d9b83" stopOpacity={0.01} /></linearGradient></defs>
        <CartesianGrid stroke="#eeeee8" strokeDasharray="3 5" vertical={false} />
        <XAxis dataKey="month" axisLine={false} tickLine={false} tick={{ fill: "#929a95", fontSize: 11 }} dy={9} />
        <YAxis tickFormatter={compactMoney} axisLine={false} tickLine={false} tick={{ fill: "#929a95", fontSize: 10 }} />
        <Tooltip formatter={(value) => money(Number(value))} contentStyle={{ border: "1px solid #e8e7e0", borderRadius: 12, boxShadow: "0 8px 24px #26332f12", fontSize: 12 }} />
        <Area type="monotone" dataKey="forecast" stroke="#9ab5a2" strokeWidth={2} strokeDasharray="5 5" fill="url(#cashFill)" connectNulls />
        <Area type="monotone" dataKey="actual" stroke="#245b4b" strokeWidth={2.6} fill="url(#cashFill)" connectNulls={false} />
      </AreaChart>
    </ResponsiveContainer>
  </div>;
}

function SectionCard({ title, subtitle, action, children, className = "" }: { title: string; subtitle?: string; action?: ReactNode; children: ReactNode; className?: string }) {
  return <section className={`section-card ${className}`}><div className="section-heading"><div><h2>{title}</h2>{subtitle && <p>{subtitle}</p>}</div>{action}</div>{children}</section>;
}

function Overview({ setPage, transactions, dashboard }: { setPage: (p: Page) => void; transactions: typeof initialTransactions; dashboard: DashboardResponse | null }) {
  const chartData = dashboard?.cashflow_series ?? cashData;
  const recentTransactions = dashboard?.recent_transactions?.map(t => ({ ...t, date: new Date(`${t.date}T00:00:00`).toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" }) })) ?? transactions.slice(0, 4);
  return <div className="page-stack">
    <PageIntro title="Good evening." description="Here's what's happening with Bloom & Bean today." action={<button className="button button-primary" onClick={() => setPage("Transactions")}><Plus size={16} /> Add transaction</button>} />
    <div className="demo-notice"><span className="demo-dot" /> {dashboard?.workspace.is_sample_data ? "DEMO WORKSPACE" : dashboard ? "CONNECTED WORKSPACE" : "DEMO WORKSPACE"} <span>{dashboard ? `Financial data as of ${dashboard.as_of_date}. ${dashboard.workspace.is_sample_data ? "Illustrative sample data." : "Connected backend data."}` : "Showing sample figures while the backend is unavailable."}</span></div>
    <div className="metrics-grid">
      <MetricCard label="Available cash" value={money(dashboard?.kpis.available_cash.value ?? 342500)} change={dashboard?.kpis.available_cash.change ?? "+8.2%"} note={dashboard?.kpis.available_cash.note ?? "vs. last month"} icon={Wallet} />
      <MetricCard label="30-day projected" value={money(dashboard?.kpis.projected_30d.value ?? 218000)} change={dashboard?.kpis.projected_30d.change ?? "Based on forecast"} note={dashboard?.kpis.projected_30d.note ?? "estimated closing balance"} icon={TrendingUp} tone="sage" />
      <MetricCard label="Overdue receivables" value={money(dashboard?.kpis.overdue_receivables.value ?? 85000)} change={dashboard?.kpis.overdue_receivables.change ?? "2 invoices"} note={dashboard?.kpis.overdue_receivables.note ?? "awaiting payment"} icon={Clock3} tone="amber" />
      <MetricCard label="Safe to spend" value={money(dashboard?.kpis.safe_to_spend.value ?? 68000)} change={dashboard?.kpis.safe_to_spend.change ?? "After commitments"} note={dashboard?.kpis.safe_to_spend.note ?? "available for decisions"} icon={Gauge} tone="coral" />
    </div>
    <div className="overview-grid">
      <SectionCard title="Cash flow outlook" subtitle="Your balance, looking ahead" action={<button className="text-action" onClick={() => setPage("Cash Flow")}>View forecast <ArrowUpRight size={14} /></button>}>
        <div className="chart-legend"><span><i className="legend-dot actual-dot" /> Actual balance</span><span><i className="legend-line" /> Forecast</span><span className="legend-period">{dashboard?.series_range_label ?? "Jun 2026 — Feb 2027"}</span></div>
        <div className="chart-main"><CashFlowChart data={chartData} /></div>
        <div className="chart-insight"><span className="insight-icon"><Lightbulb size={15} /></span><p>{dashboard?.insight ?? "Your projected balance stays positive over the next 90 days, but keep an eye on the December inventory cycle."}</p></div>
      </SectionCard>
      <SectionCard title="Your AI CFO" subtitle="A quick read on your business" action={<button className="icon-button small" onClick={() => setPage("AI Financial Copilot")}><ArrowUpRight size={17} /></button>}>
        <div className="cfo-intro"><div className="cfo-avatar"><Sparkles size={18} /></div><div><strong>One thing worth your attention</strong><span>{dashboard?.ai_cfo.updated_at ? `Updated ${new Date(dashboard.ai_cfo.updated_at).toLocaleString("en-IN")}` : "Sample insight"}</span></div></div>
        <div className="cfo-highlight"><span className="risk-tag">{dashboard?.ai_cfo.tag ?? "CASH FLOW WATCH"}</span><h3>{dashboard?.ai_cfo.title ?? "Two invoices are past due."}</h3><p>{dashboard?.ai_cfo.body ?? "₹85,000 is outstanding across two customers. Following up this week could give your December cash position more breathing room."}</p></div>
        <button className="button button-outline full-button" onClick={() => setPage("AI Financial Copilot")}>Talk to your AI CFO <ArrowRight size={15} /></button>
        <div className="cfo-foot"><CheckCircle2 size={14} /> Recommendations are grounded in the connected workspace records.</div>
      </SectionCard>
    </div>
    <div className="lower-grid">
      <SectionCard title="Recent transactions" subtitle="The latest activity in your books" action={<button className="text-action" onClick={() => setPage("Transactions")}>All transactions <ArrowUpRight size={14} /></button>}>
        <TransactionTable transactions={recentTransactions} />
      </SectionCard>
      <SectionCard title="Risk radar" subtitle="A few things to keep on your radar" action={<button className="text-action" onClick={() => setPage("Risk Radar")}>See all <ArrowUpRight size={14} /></button>}>
        <div className="risk-list">{dashboard?.risk_items?.length ? dashboard.risk_items.map((item, index) => <RiskItem key={`${item.title}-${index}`} tone={item.tone} title={item.title} detail={item.detail} />) : <div className="empty-state">Risk highlights will appear when dashboard data is available.</div>}</div>
      </SectionCard>
    </div>
  </div>;
}

function TransactionTable({ transactions }: { transactions: typeof initialTransactions }) {
  return <div className="table-scroll"><table className="data-table"><thead><tr><th>DESCRIPTION</th><th>DATE</th><th>AMOUNT</th></tr></thead><tbody>{transactions.map((t) => <tr key={t.id}><td><div className="transaction-name"><span className={`transaction-symbol ${t.type}`}>{t.type === "income" ? <ArrowDownRight size={15} /> : <ArrowUpRight size={15} />}</span><span><strong>{t.name}</strong><small>{t.category} · {t.id}</small></span></div></td><td className="date-cell">{t.date}</td><td className={t.amount > 0 ? "amount-positive" : "amount-negative"}>{t.amount > 0 ? "+" : "−"}{money(Math.abs(t.amount))}</td></tr>)}</tbody></table></div>;
}

function RiskItem({ tone, title, detail }: { tone: string; title: string; detail: string }) {
  return <div className="risk-item"><span className={`risk-indicator ${tone}`}><AlertCircle size={16} /></span><div><strong>{title}</strong><span>{detail}</span></div><ChevronRight size={16} className="risk-chevron" /></div>;
}

function formatTransactionDate(isoDate: string) {
  return new Date(`${isoDate}T00:00:00`).toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" });
}

function Transactions({ addTransaction }: { addTransaction: (t: Transaction) => void }) {
  const [filter, setFilter] = useState("All");
  const [query, setQuery] = useState("");
  const [showAdd, setShowAdd] = useState(false);
  const [items, setItems] = useState<Transaction[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);

  useEffect(() => {
    let active = true;
    setLoading(true);
    getTransactions({ q: query.trim() || undefined, type: filter === "All" ? undefined : filter === "Income" ? "income" : "expense", page: 1, limit: 200 })
      .then(result => { if (active) { setItems(result.items); setTotal(result.total); } })
      .catch((error: unknown) => { if (active) toast.error(error instanceof Error ? error.message : "Could not load transactions"); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [filter, query]);

  const handleAdd = async (input: { name: string; amount: number; type: "income" | "expense"; category?: string }) => {
    const created = await createTransaction(input);
    setItems(current => [created, ...current]); setTotal(current => current + 1); addTransaction(created);
    toast.success("Transaction saved successfully.");
  };

  const handleUpload = async (file?: File) => {
    if (!file) return;
    setUploading(true);
    try {
      const result = await uploadTransactions(file);
      toast.success(`Imported ${result.imported} transaction(s); skipped ${result.skipped}.`);
      if (result.errors.length) toast.warning(result.errors.slice(0, 2).map(item => `Row ${item.row}: ${item.message}`).join(" · "));
      const refreshed = await getTransactions({ q: query.trim() || undefined, type: filter === "All" ? undefined : filter === "Income" ? "income" : "expense", page: 1, limit: 200 });
      setItems(refreshed.items); setTotal(refreshed.total);
    } catch (error) { toast.error(error instanceof Error ? error.message : "CSV upload failed"); }
    finally { setUploading(false); }
  };

  return <div className="page-stack"><PageIntro title="Transactions" description="Every movement, in one clear view." action={<button className="button button-primary" onClick={() => setShowAdd(!showAdd)}><Plus size={16} /> Add transaction</button>} />
    {showAdd && <AddTransaction onAdd={handleAdd} onCancel={() => setShowAdd(false)} />}
    <SectionCard title="Your activity" subtitle={`${total} records from your workspace`}>
      <div className="table-tools"><div className="search-box"><Search size={16} /><input value={query} onChange={e => setQuery(e.target.value)} placeholder="Search transactions..." /></div><div className="filter-tabs">{["All", "Income", "Expenses"].map(f => <button key={f} className={filter === f ? "selected" : ""} onClick={() => setFilter(f)}>{f}</button>)}</div><label className="button button-outline upload-button"><UploadCloud size={15} /> {uploading ? "Uploading..." : "Import CSV"}<input type="file" accept=".csv,text/csv" disabled={uploading} onChange={e => { void handleUpload(e.target.files?.[0]); e.currentTarget.value = ""; }} /></label></div>
      {loading ? <div className="empty-state">Loading transactions...</div> : <TransactionTable transactions={items.map(t => ({ ...t, date: formatTransactionDate(t.date) }))} />}
      {!loading && items.length === 0 && <div className="empty-state">No transactions match your search.</div>}
    </SectionCard>
    <div className="inline-note"><AlertCircle size={15} /> Transactions are loaded from the connected LedgerLens API. Imported CSV rows are validated by the backend.</div>
  </div>;
}

function AddTransaction({ onAdd, onCancel }: { onAdd: (t: { name: string; amount: number; type: "income" | "expense"; category?: string }) => Promise<void>; onCancel: () => void }) {
  const [name, setName] = useState(""); const [amount, setAmount] = useState("");
  const [type, setType] = useState<"income" | "expense">("income");
  const [category, setCategory] = useState("Sales"); const [saving, setSaving] = useState(false);
  const save = async () => {
    setSaving(true);
    try { await onAdd({ name: name.trim(), amount: Number(amount), type, category }); onCancel(); }
    catch (error) { toast.error(error instanceof Error ? error.message : "Could not save transaction"); }
    finally { setSaving(false); }
  };
  return <SectionCard title="New transaction" subtitle="Add a transaction to your workspace"><div className="form-grid"><label>Description<input value={name} onChange={e => setName(e.target.value)} placeholder="e.g. Customer payment" /></label><label>Amount (₹)<input type="number" min="1" value={amount} onChange={e => setAmount(e.target.value)} placeholder="25000" /></label><label>Type<select value={type} onChange={e => { const next = e.target.value as "income" | "expense"; setType(next); setCategory(next === "income" ? "Sales" : "General"); }}><option value="income">Income</option><option value="expense">Expense</option></select></label><label>Category<select value={category} onChange={e => setCategory(e.target.value)}>{["Sales", "Inventory", "Rent", "Utilities", "Payroll", "General"].map(option => <option key={option} value={option}>{option}</option>)}</select></label></div><div className="form-actions"><button className="button button-outline" onClick={onCancel}>Cancel</button><button className="button button-primary" disabled={saving || !name.trim() || Number(amount) <= 0} onClick={() => void save()}>{saving ? "Saving..." : "Save transaction"}</button></div></SectionCard>;
}

function CashFlow() {
  const [forecast, setForecast] = useState<CashFlowForecastResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  useEffect(() => {
    getCashFlowForecast(90).then(setForecast).catch((reason: unknown) => {
      const message = reason instanceof Error ? reason.message : "Could not load the cash-flow forecast";
      setError(message);
      toast.error(`Cash-flow forecast: ${message}`);
    }).finally(() => setLoading(false));
  }, []);
  const formatDate = (value: string) => new Date(`${value}T00:00:00`).toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" });
  return <div className="page-stack">
    <PageIntro title="Cash flow" description="See where your money is going — and where it may take you." />
    <div className="metrics-grid compact-metrics">
      <MetricCard label="Opening balance" value={forecast ? money(forecast.opening_balance) : "—"} note="At the start of the forecast" icon={Wallet} />
      <MetricCard label="Expected inflows" value={forecast ? money(forecast.inflows_30d) : "—"} note="Next 30 days" icon={TrendingUp} tone="sage" />
      <MetricCard label="Expected outflows" value={forecast ? money(forecast.outflows_30d) : "—"} note="Next 30 days" icon={TrendingDown} tone="amber" />
    </div>
    <SectionCard title="Balance forecast" subtitle={forecast ? `Historical balance and projection · ${forecast.range_label}` : "Historical balance and projected cash position"}>
      <div className="chart-legend"><span><i className="legend-dot actual-dot" /> Actual</span><span><i className="legend-line" /> Forecast</span></div>
      <div className="chart-main cashflow-detail-chart">
        {forecast && <CashFlowChart detailed data={forecast.series} />}
        {loading && <div className="inline-note">Loading your cash-flow forecast…</div>}
        {error && !forecast && <div className="inline-note"><AlertCircle size={15} /> Forecast unavailable: {error}</div>}
      </div>
      {forecast && <div className="chart-insight"><span className="insight-icon"><Lightbulb size={15} /></span><p>Lowest projected balance: <strong>{money(forecast.lowest_balance.value)}</strong> on {formatDate(forecast.lowest_balance.date)}.{forecast.shortfall_date ? ` The safety buffer is first breached on ${formatDate(forecast.shortfall_date)}.` : " The forecast stays above the safety buffer."}</p></div>}
    </SectionCard>
    <div className="two-col">
      <SectionCard title="Upcoming commitments" subtitle="Planned cash outflows already included in the forecast">
        {forecast?.commitments.length ? forecast.commitments.map((item, index) => <div className="commitment-row" key={`${item.label}-${item.date}-${index}`}><span>{item.label}</span><strong>{money(item.amount)}</strong><small>{formatDate(item.date)}</small></div>) : <div className="empty-state">{loading ? "Loading commitments…" : "No upcoming commitments returned."}</div>}
      </SectionCard>
      <SectionCard title="Forecast assumptions" subtitle="What shapes this projection">
        {forecast?.assumptions.length ? <ul className="assumption-list">{forecast.assumptions.map((item, index) => <li key={index}>{item}</li>)}</ul> : <div className="empty-state">{loading ? "Loading assumptions…" : "Forecast assumptions are unavailable."}</div>}
      </SectionCard>
    </div>
    {forecast && <div className="inline-note"><AlertCircle size={15} /> {forecast.is_sample_data ? "This forecast uses fictional Bloom & Bean demo data." : "This forecast uses connected workspace data."} Values are estimates, not guaranteed future balances.</div>}
  </div>;
}

function Simulator() {
  const [purchase, setPurchase] = useState(50000);
  const [revenue, setRevenue] = useState(15);
  const [result, setResult] = useState<Awaited<ReturnType<typeof runSimulator>> | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const run = async () => {
    setLoading(true); setError("");
    try { setResult(await runSimulator({ purchase_amount: purchase, revenue_uplift_pct: revenue })); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Could not run this scenario"); }
    finally { setLoading(false); }
  };
  return <div className="page-stack"><PageIntro eyebrow="MAKE THE NEXT MOVE WITH CLARITY" title="What-if simulator" description="Explore a decision before it becomes a commitment." />
    <div className="simulator-layout"><SectionCard title="Build your scenario" subtitle="Adjust the assumptions to explore a possible decision">
      <div className="scenario-block"><div className="scenario-label"><div><span className="scenario-number">01</span><strong>New inventory purchase</strong></div><strong>{money(purchase)}</strong></div><input className="range-input" type="range" min="10000" max="200000" step="5000" value={purchase} onChange={e => { setPurchase(Number(e.target.value)); setResult(null); }} /><div className="range-labels"><span>₹10,000</span><span>₹2,00,000</span></div></div>
      <div className="scenario-block"><div className="scenario-label"><div><span className="scenario-number">02</span><strong>Expected revenue uplift</strong></div><strong>{revenue}%</strong></div><input className="range-input" type="range" min="0" max="40" step="1" value={revenue} onChange={e => { setRevenue(Number(e.target.value)); setResult(null); }} /><div className="range-labels"><span>0%</span><span>40%</span></div></div>
      <div className="scenario-summary"><div><span>Current 30-day projected balance</span><strong>{result ? money(result.base_balance) : "Fetched when you run"}</strong></div><div><span>Scenario cost</span><strong className="amount-negative">−{money(purchase)}</strong></div><div><span>Estimated additional revenue</span><strong className="amount-positive">+{money(result?.additional_revenue ?? (purchase * revenue / 100))}</strong></div></div>
      <button className="button button-primary full-button" disabled={loading} onClick={() => void run()}><Sparkles size={16} /> {loading ? "Calculating…" : "Run this scenario"}</button>
      {error && <div className="inline-note"><AlertCircle size={15} /> {error}</div>}
    </SectionCard>
    <div className="scenario-result"><div className="result-orbit"><Compass size={26} /></div><span className="eyebrow">YOUR SCENARIO OUTCOME</span><h2>{result ? money(result.projected_balance) : "What could your balance look like?"}</h2><p>{result ? result.explanation : "Run the scenario to calculate its impact using the backend forecast."}</p>
      {result && <div className={result.verdict === "affordable" || result.verdict === "comfortable" ? "verdict-positive" : "verdict-caution"}>{result.verdict === "affordable" || result.verdict === "comfortable" ? <CheckCircle2 size={16} /> : <AlertCircle size={16} />}{result.verdict_label}</div>}
      {result && <div className="result-foot"><AlertCircle size={14} /> Backend-calculated · {result.explanation_source === "gemini" ? "AI-assisted explanation" : "Rule-based explanation"} · Comfort threshold {money(result.threshold)}</div>}
    </div></div>
  </div>;
}

function formatApiDate(value: string) {
  return new Date(`${value}T00:00:00`).toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" });
}

function Invoices() {
  const [data, setData] = useState<Awaited<ReturnType<typeof getInvoices>> | null>(null);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState("");
  const [draft, setDraft] = useState<InvoiceUploadResponse | null>(null);
  const [client, setClient] = useState("");
  const [dueDate, setDueDate] = useState("");
  const [amount, setAmount] = useState("");
  const [invoiceNumber, setInvoiceNumber] = useState("");
  const [uploading, setUploading] = useState(false);
  const refresh = async () => { setData(await getInvoices()); };
  useEffect(() => { let active = true; getInvoices().then(value => { if (active) setData(value); }).catch(e => toast.error(e instanceof Error ? e.message : "Could not load invoices")).finally(() => { if (active) setLoading(false); }); return () => { active = false; }; }, []);
  const onUpload = async (file?: File) => {
    if (!file) return; setUploading(true);
    try {
      const value = await uploadInvoice(file); setDraft(value);
      setClient(value.fields.client || ""); setDueDate(value.fields.due_date || "");
      setAmount(String(value.fields.amount || "")); setInvoiceNumber(value.fields.invoice_number || "");
      toast.success("Invoice uploaded. Review the extracted details before confirming.");
    } catch (e) { toast.error(e instanceof Error ? e.message : "Invoice upload failed"); }
    finally { setUploading(false); }
  };
  const confirm = async () => {
    if (!draft || !client.trim() || !dueDate || Number(amount) <= 0) return;
    setBusyId(draft.id);
    try { await confirmInvoice(draft.id, { client: client.trim(), due_date: dueDate, amount: Number(amount), invoice_number: invoiceNumber.trim() }); setDraft(null); await refresh(); toast.success("Invoice confirmed and added to your register."); }
    catch (e) { toast.error(e instanceof Error ? e.message : "Could not confirm invoice"); }
    finally { setBusyId(""); }
  };
  const paid = async (id: string) => {
    setBusyId(id);
    try { await markInvoicePaid(id); await refresh(); toast.success("Invoice marked as paid."); }
    catch (e) { toast.error(e instanceof Error ? e.message : "Could not update invoice"); }
    finally { setBusyId(""); }
  };
  return <div className="page-stack"><PageIntro title="Invoices" description="Keep track of what you've billed and what is still due." action={<label className="button button-primary upload-button"><UploadCloud size={16} /> {uploading ? "Uploading…" : "Upload invoice"}<input type="file" accept=".pdf,.png,.jpg,.jpeg" disabled={uploading} onChange={e => { void onUpload(e.target.files?.[0]); e.currentTarget.value = ""; }} /></label>} />
    {draft && <SectionCard title="Review extracted invoice" subtitle={`Draft ${draft.id} · ${Math.round(draft.confidence * 100)}% extraction confidence`}>
      {draft.warnings.length > 0 && <div className="inline-note"><AlertCircle size={15} /> {draft.warnings.join(" · ")}</div>}
      <div className="form-grid"><label>Client<input value={client} onChange={e => setClient(e.target.value)} /></label><label>Due date<input type="date" value={dueDate} onChange={e => setDueDate(e.target.value)} /></label><label>Amount (₹)<input type="number" min="1" value={amount} onChange={e => setAmount(e.target.value)} /></label><label>Invoice number<input value={invoiceNumber} onChange={e => setInvoiceNumber(e.target.value)} /></label></div>
      <div className="form-actions"><button className="button button-outline" onClick={() => setDraft(null)}>Discard draft</button><button className="button button-primary" disabled={!client.trim() || !dueDate || Number(amount) <= 0 || busyId === draft.id} onClick={() => void confirm()}>{busyId === draft.id ? "Confirming…" : "Confirm invoice"}</button></div>
    </SectionCard>}
    <div className="metrics-grid compact-metrics"><MetricCard label="Total outstanding" value={data ? money(data.summary.total_outstanding) : "—"} note={data ? `Across ${data.summary.outstanding_count} invoices` : "Loading"} icon={FileText} /><MetricCard label="Overdue" value={data ? money(data.summary.overdue_total) : "—"} note="Needs follow-up" icon={Clock3} tone="coral" /><MetricCard label="Collected this month" value={data ? money(data.summary.collected_this_month) : "—"} note="Payments received" icon={CheckCircle2} tone="sage" /></div>
    <SectionCard title="Invoice register" subtitle={data ? `${data.items.length} records from your workspace` : "Connected invoice records"}>
      {loading ? <div className="empty-state">Loading invoices…</div> : data?.items.length ? <div className="invoice-list">{data.items.map(inv => <div className="invoice-row" key={inv.id}><div className="invoice-file-icon"><FileText size={19} /></div><div className="invoice-main"><strong>{inv.id} · {inv.client}</strong><span>Due {formatApiDate(inv.due_date)}</span></div><strong className="invoice-amount">{money(inv.amount)}</strong><span className={`status-pill ${inv.status === "Overdue" ? "status-overdue" : inv.status === "Paid" ? "status-paid" : "status-pending"}`}>{inv.status}</span>{inv.status !== "Paid" && inv.status !== "Draft" && <button className="button button-small button-outline" disabled={busyId === inv.id} onClick={() => void paid(inv.id)}>{busyId === inv.id ? "Saving…" : "Mark paid"}</button>}</div>)}</div> : <div className="empty-state">No invoices returned by the API.</div>}
    </SectionCard><div className="inline-note"><AlertCircle size={15} /> Uploaded invoice details are suggestions. Always review extracted fields before confirming them.</div></div>;
}

function RiskRadar() {
  const [data, setData] = useState<Awaited<ReturnType<typeof getRiskAlerts>> | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  useEffect(() => { let active = true; getRiskAlerts().then(value => { if (active) setData(value); }).catch(e => { if (active) setError(e instanceof Error ? e.message : "Could not load risk alerts"); }).finally(() => { if (active) setLoading(false); }); return () => { active = false; }; }, []);
  return <div className="page-stack"><PageIntro title="Risk radar" description="Spot pressure points early, while you still have room to act." />
    {data && <div className="risk-summary"><div className="risk-summary-icon"><ShieldAlert size={23} /></div><div><strong>{data.summary.attention_count} items need attention</strong><span>{data.summary.note}</span></div><span className="risk-tag">{data.summary.tag}</span></div>}
    {loading && <div className="empty-state">Loading risk analysis…</div>}
    {error && <div className="inline-note"><AlertCircle size={15} /> {error}</div>}
    {data && <div className="risk-cards">{data.alerts.map(alert => <SectionCard key={alert.id} title={alert.title} subtitle={alert.subtitle}>
      <div className="risk-large-number">{alert.metric}</div><p className="body-copy">{alert.body}</p>
      <div className="risk-detail"><span>{alert.impact_label}</span><strong>{alert.impact_value}</strong></div>
      <div className="risk-evidence"><strong>Evidence</strong>{alert.evidence.map((item, index) => <div key={`${item.kind}-${item.id}-${index}`}>{item.label}</div>)}</div>
      <span className={`risk-tag ${alert.tone}`}>{alert.action_label}</span>
    </SectionCard>)}</div>}
    <div className="inline-note"><AlertCircle size={15} /> Risk alerts are generated from the connected workspace records and forecast model. Review the underlying evidence before acting.</div>
  </div>;
}

function Copilot() {
  const [messages, setMessages] = useState<CopilotMessage[]>([{ role: "assistant", text: "Hello! I'm your LedgerLens AI CFO. Ask me about cash flow, receivables or a business decision." }]);
  const [draft, setDraft] = useState("");
  const [suggestions, setSuggestions] = useState(["Can I afford new inventory?", "What needs my attention?", "How much is overdue?"]);
  const [panelQuestions, setPanelQuestions] = useState(["Can I afford a Rs 50,000 inventory order?", "Which invoices should I follow up on?", "What is changing my cash position?"]);
  const [sending, setSending] = useState(false);
  const [source, setSource] = useState<"gemini" | "fallback" | null>(null);
  useEffect(() => { getCopilotSuggestions().then(value => { setSuggestions(value.chips); setPanelQuestions(value.panel); }).catch(() => undefined); }, []);
  const send = async (value = draft) => {
    const question = value.trim(); if (!question || sending) return;
    const history = messages;
    setMessages(current => [...current, { role: "user", text: question }]); setDraft(""); setSending(true);
    try {
      const response = await sendCopilotMessage(question, history);
      setMessages(current => [...current, { role: "assistant", text: response.reply + (response.citations.length ? `\n\nSources: ${response.citations.map(citation => citation.label).join(" · ")}` : "") }]); setSource(response.source);
      if (response.suggested_questions?.length) setSuggestions(response.suggested_questions);
    } catch (e) {
      setMessages(current => [...current, { role: "assistant", text: e instanceof Error ? `I couldn't reach the financial service: ${e.message}` : "I couldn't reach the financial service. Please try again." }]);
      toast.error("Copilot request failed");
    } finally { setSending(false); }
  };
  return <div className="page-stack"><PageIntro title="Your AI financial copilot" description="Ask clearer questions. Make more confident decisions." /><div className="copilot-layout">
    <section className="chat-panel"><div className="chat-header"><div className="cfo-avatar"><Sparkles size={18} /></div><div><strong>LedgerLens CFO</strong><span><i className="online-dot" /> {source === "gemini" ? "AI-assisted · Grounded in workspace data" : source === "fallback" ? "Verified fallback · Grounded in workspace data" : "Connected financial assistant"}</span></div><button className="icon-button small" onClick={() => { setMessages([{ role: "assistant", text: "Conversation cleared. What would you like to explore?" }]); setSource(null); }}><MoreHorizontal size={18} /></button></div>
      <div className="chat-messages">{messages.map((m, i) => <div key={i} className={`chat-message ${m.role}`}><div className="message-avatar">{m.role === "assistant" ? <Sparkles size={15} /> : "US"}</div><div className="message-bubble">{m.text}</div></div>)}{sending && <div className="empty-state">Your AI CFO is checking the workspace…</div>}</div>
      <div className="suggestion-row">{suggestions.map(s => <button key={s} disabled={sending} onClick={() => void send(s)}>{s}</button>)}</div>
      <form className="chat-input-row" onSubmit={e => { e.preventDefault(); void send(); }}><button type="button" className="icon-button small" onClick={() => toast("Invoice uploads are available from the Invoices screen.")}><Paperclip size={17} /></button><input value={draft} onChange={e => setDraft(e.target.value)} placeholder="Ask your financial copilot…" /><button type="submit" className="send-button" disabled={!draft.trim() || sending}><Send size={17} /></button></form>
    </section><aside className="copilot-side"><SectionCard title="Suggested questions" subtitle="Start with one of these"><div className="question-list">{panelQuestions.map(q => <button key={q} onClick={() => void send(q)}>{q}<ArrowUpRight size={15} /></button>)}</div></SectionCard><div className="evidence-note"><ShieldAlert size={17} /><div><strong>Evidence before advice</strong><p>Responses are grounded in the platform's financial records. If AI generation is unavailable, a verified fallback response is used.</p></div></div></aside>
  </div></div>;
}

function Receivables() {
  const [data, setData] = useState<Awaited<ReturnType<typeof getReceivables>> | null>(null);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState("");
  const refresh = async () => setData(await getReceivables());
  useEffect(() => { let active = true; getReceivables().then(value => { if (active) setData(value); }).catch(e => toast.error(e instanceof Error ? e.message : "Could not load receivables")).finally(() => { if (active) setLoading(false); }); return () => { active = false; }; }, []);
  const paid = async (id: string) => {
    setBusyId(id);
    try { await markInvoicePaid(id); await refresh(); toast.success("Receivable marked as paid."); }
    catch (e) { toast.error(e instanceof Error ? e.message : "Could not update receivable"); }
    finally { setBusyId(""); }
  };
  return <div className="page-stack"><PageIntro title="Receivables" description="A gentle nudge today can make tomorrow's cash flow easier." />
    <div className="metrics-grid compact-metrics"><MetricCard label="Outstanding" value={data ? money(data.outstanding_total) : "—"} note="Unpaid invoices" icon={Wallet} /><MetricCard label="Overdue accounts" value={data ? String(data.overdue_count) : "—"} note="Need a follow-up" icon={Clock3} tone="coral" /><MetricCard label="Collection progress" value={data ? `${data.collection_progress_pct}%` : "—"} note="Period-to-date" icon={Activity} tone="sage" /></div>
    {data && <SectionCard title="Receivables ageing" subtitle="Outstanding amounts grouped by days overdue"><div className="aging-list">{data.aging_buckets.map(bucket => <div className="commitment-row" key={bucket.label}><span>{bucket.label} · {bucket.count} invoice(s)</span><strong>{money(bucket.amount)}</strong></div>)}</div></SectionCard>}
    <SectionCard title="Who owes you" subtitle="Open invoices and follow-up actions">{loading ? <div className="empty-state">Loading receivables…</div> : data?.items.length ? <div className="receivable-list">{data.items.map(i => <div className="receivable-row" key={i.id}><div className="client-avatar">{i.client.slice(0,1)}</div><div className="receivable-client"><strong>{i.client}</strong><span>{i.id} · Due {formatApiDate(i.due_date)}</span></div><div className="receivable-amount"><strong>{money(i.amount)}</strong><span className={i.status === "Overdue" ? "negative-change" : "muted-text"}>{i.status}{i.days_overdue > 0 ? ` · ${i.days_overdue} days late` : ""}</span></div><button className="button button-small button-primary" disabled={busyId === i.id} onClick={() => void paid(i.id)}>{busyId === i.id ? "Saving…" : "Mark paid"}</button></div>)}</div> : <div className="empty-state">No outstanding receivables.</div>}</SectionCard>
    <div className="inline-note"><AlertCircle size={15} /> Marking an invoice paid updates the backend, so the invoice register, receivables and dashboard can stay in sync.</div>
  </div>;
}


function AuthPage({ onAuthenticated }: { onAuthenticated: (profile: DemoProfile) => Promise<void> }) {
  const [mode, setMode] = useState<"signin" | "signup">("signup");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setError("");
    const cleanEmail = email.trim().toLowerCase();
    if (!/^\\S+@\\S+\\.\\S+$/.test(cleanEmail)) { setError("Enter a valid email address."); return; }
    if (password.length < 8) { setError("Your password must contain at least 8 characters."); return; }
    if (mode === "signup" && !name.trim()) { setError("Enter your full name."); return; }
    if (mode === "signup" && password !== confirmPassword) { setError("The passwords do not match."); return; }

    setLoading(true);
    try {
      const user = mode === "signup"
        ? await register({ name: name.trim(), email: cleanEmail, password })
        : await login({ email: cleanEmail, password });
      await onAuthenticated({ name: user.name, email: user.email });
    } catch (authError) {
      setError(authError instanceof Error ? authError.message : "Authentication failed. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  return <main className="auth-screen"><div className="auth-card"><Brand/>
    <div className="auth-heading"><span className="eyebrow">WELCOME TO LEDGERLENS</span><h1>{mode === "signup" ? "Create your account" : "Welcome back"}</h1><p>{mode === "signup" ? "A clearer view of your business starts here." : "Sign in to continue to your financial workspace."}</p></div>
    <div className="auth-tabs"><button type="button" className={mode === "signup" ? "selected" : ""} onClick={() => { setMode("signup"); setError(""); }}>Create account</button><button type="button" className={mode === "signin" ? "selected" : ""} onClick={() => { setMode("signin"); setError(""); }}>Sign in</button></div>
    <form className="auth-form" onSubmit={submit}>
      {mode === "signup" && <label>Full name<input autoComplete="name" value={name} onChange={e => setName(e.target.value)} placeholder="Your name" required/></label>}
      <label>Email address<input type="email" autoComplete="email" value={email} onChange={e => setEmail(e.target.value)} placeholder="you@gmail.com" required/></label>
      <label>Password<input type="password" autoComplete={mode === "signup" ? "new-password" : "current-password"} value={password} onChange={e => setPassword(e.target.value)} placeholder="At least 8 characters" minLength={8} required/></label>
      {mode === "signup" && <label>Confirm password<input type="password" autoComplete="new-password" value={confirmPassword} onChange={e => setConfirmPassword(e.target.value)} placeholder="Re-enter your password" minLength={8} required/></label>}
      {error && <p className="auth-error" role="alert">{error}</p>}
      <button className="button button-primary full-button" type="submit" disabled={loading}>{loading ? "Please wait…" : mode === "signup" ? "Create account" : "Sign in"} <ArrowRight size={16}/></button>
    </form>
    <div className="auth-demo-note"><ShieldAlert size={15}/><span>Your account is authenticated by the LedgerLens server. Never reuse a password from another service.</span></div>
  </div></main>;
}

function AccountSettings({ profile, onSave }: { profile: DemoProfile; onSave: (profile: DemoProfile) => Promise<void> }) {
  const [name, setName] = useState(profile.name);
  const [email, setEmail] = useState(profile.email);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const submit = async (event: FormEvent) => {
    event.preventDefault(); setError(""); setSaved(false);
    if (!name.trim() || !/^\\S+@\\S+\\.\\S+$/.test(email.trim())) { setError("Enter a valid name and email address."); return; }
    setLoading(true);
    try { await onSave({ name: name.trim(), email: email.trim().toLowerCase() }); setSaved(true); }
    catch (saveError) { setError(saveError instanceof Error ? saveError.message : "Could not update your profile."); }
    finally { setLoading(false); }
  };
  return <div className="page-stack"><PageIntro title="Account settings" description="Manage the details associated with your LedgerLens account."/><SectionCard title="Profile details" subtitle="Your name and email are linked to your authenticated account"><form className="settings-form" onSubmit={submit}>
    <div className="settings-profile-preview"><div className="profile-avatar settings-avatar">{initials(profile.name)}</div><div><strong>{profile.name}</strong><span>LedgerLens account</span></div></div>
    <label>Full name<input autoComplete="name" value={name} onChange={e => { setName(e.target.value); setSaved(false); }} required/></label>
    <label>Email address<input type="email" autoComplete="email" value={email} onChange={e => { setEmail(e.target.value); setSaved(false); }} required/></label>
    {error && <p className="auth-error" role="alert">{error}</p>}
    <div className="form-actions"><button className="button button-primary" type="submit" disabled={loading}>{loading ? "Saving…" : "Save changes"}</button></div>
    {saved && <p className="settings-saved"><CheckCircle2 size={15}/> Profile updated.</p>}
  </form></SectionCard><div className="inline-note"><ShieldAlert size={15}/> Passwords and sessions are managed by the backend. Sign out when using a shared device.</div></div>;
}

function OverviewFooter() {
  return <footer className="app-footer"><span>LedgerLens · See beyond the numbers.</span><span><i className="demo-dot" /> Sample workspace · 19 Nov 2026</span></footer>;
}


export default function App() {
 const [profile, setProfile] = useState<DemoProfile | null>(null);
 const [authChecking, setAuthChecking] = useState(true);
 const [page, setPage] = useState<Page>("Overview"), [menuOpen, setMenuOpen] = useState(false);
 const [transactions, setTransactions] = useState(initialTransactions), [dashboard, setDashboard] = useState<DashboardResponse | null>(null);

 useEffect(() => {
   let active = true;
   getCurrentUser()
     .then(user => { if (active) setProfile({ name: user.name, email: user.email }); })
     .catch((error: unknown) => {
       if (!active) return;
       const status = typeof error === "object" && error !== null && "status" in error ? Number((error as { status: unknown }).status) : 0;
       if (status !== 401) toast.error(error instanceof Error ? error.message : "Could not restore your session.");
       setProfile(null);
     })
     .finally(() => { if (active) setAuthChecking(false); });
   return () => { active = false; };
 }, []);

 useEffect(() => {
   if (!profile) { setDashboard(null); return; }
   getDashboard().then(setDashboard).catch((error: unknown) => toast.error("Backend connection: " + (error instanceof Error ? error.message : "Could not load dashboard data")));
 }, [profile]);

 const addTransaction = (t: Transaction) => setTransactions(old => [t, ...old]);
 const acceptAuthenticatedUser = async (next: DemoProfile) => {
   setProfile(next); setPage("Overview"); toast.success("You're signed in.");
 };
 const saveProfile = async (next: DemoProfile) => {
   const updated = await updateCurrentUser(next);
   setProfile({ name: updated.name, email: updated.email });
   toast.success("Account details updated.");
 };
 const signOut = async () => {
   try { await logout(); }
   catch (error) { toast.error(error instanceof Error ? error.message : "The server could not end the session."); }
   finally { setProfile(null); setPage("Overview"); setDashboard(null); }
 };
 const pageContent = useMemo(() => {
   if (!profile) return null;
   switch (page) {
     case "Overview": return <Overview setPage={setPage} transactions={transactions} dashboard={dashboard}/>;
     case "Transactions": return <Transactions addTransaction={addTransaction}/>;
     case "Cash Flow": return <CashFlow/>;
     case "What-If Simulator": return <Simulator/>;
     case "Invoices": return <Invoices/>;
     case "Risk Radar": return <RiskRadar/>;
     case "AI Financial Copilot": return <Copilot/>;
     case "Receivables": return <Receivables/>;
     case "Account settings": return <AccountSettings profile={profile} onSave={saveProfile}/>;
     default: return null;
   }
 }, [page, transactions, dashboard, profile]);

 if (authChecking) return <main className="auth-screen"><div className="auth-card auth-loading"><Brand/><p>Checking your secure session…</p></div></main>;
 if (!profile) return <><Toaster position="top-right" richColors/><AuthPage onAuthenticated={acceptAuthenticatedUser}/></>;
 return <div className="app-shell"><Toaster position="top-right" richColors/><Sidebar page={page} setPage={setPage} open={menuOpen} close={() => setMenuOpen(false)} profile={profile}/><main className="main-area"><Header page={page} profile={profile} onMenu={() => setMenuOpen(true)} onSettings={() => setPage("Account settings")} onSignOut={signOut}/><div className="page-container">{pageContent}<OverviewFooter/></div></main></div>;
}
