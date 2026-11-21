import { useEffect, useMemo, useState, type ReactNode } from "react";
import { createTransaction, getDashboard, getTransactions, uploadTransactions, type DashboardResponse, type Transaction } from "./api/client";
import {
  Activity, AlertCircle, ArrowDownRight, ArrowRight, ArrowUpRight, Bell,
  CalendarDays, CheckCircle2, ChevronDown, ChevronRight, Clock3, Compass,
  FileText, Filter, Gauge, Home, Lightbulb, Menu, MoreHorizontal, Paperclip,
  Plus, Search, Send, Settings, ShieldAlert, SlidersHorizontal, Sparkles,
  TrendingDown, TrendingUp, UploadCloud, Wallet, X,
} from "lucide-react";
import {
  Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { Toaster, toast } from "sonner";

type Page = "Overview" | "Transactions" | "Cash Flow" | "What-If Simulator" | "Invoices" | "Risk Radar" | "AI Financial Copilot" | "Receivables";

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

const initialInvoices = [
  { id: "INV-204", client: "Aarav Foods", due: "12 Nov 2026", amount: 52000, status: "Overdue" },
  { id: "INV-198", client: "The Daily Table", due: "08 Nov 2026", amount: 33000, status: "Overdue" },
  { id: "INV-211", client: "Cafe Bloom", due: "28 Nov 2026", amount: 24500, status: "Pending" },
];

const money = (value: number) => new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 }).format(value);
const compactMoney = (value: number) => value >= 100000 ? `₹${(value / 100000).toFixed(1)}L` : `₹${Math.round(value / 1000)}k`;

function Brand() {
  return <div className="brand-lockup">
    <div className="brand-mark"><Compass size={23} strokeWidth={1.65} /></div>
    <div><div className="brand-name">LedgerLens</div><div className="brand-tagline">See beyond the numbers.</div></div>
  </div>;
}

function Sidebar({ page, setPage, open, close }: { page: Page; setPage: (p: Page) => void; open: boolean; close: () => void }) {
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
        <button className="nav-item muted-nav" onClick={() => toast("Settings will be available in a later build.")}><Settings size={18} /><span>Settings</span></button>
        <div className="profile-row"><div className="profile-avatar">US</div><div className="profile-copy"><strong>Business owner</strong><span>Bloom & Bean</span></div><MoreHorizontal size={18} /></div>
      </div>
    </aside>
  </>;
}

function Header({ page, onMenu }: { page: Page; onMenu: () => void }) {
  return <header className="topbar">
    <div className="topbar-left"><button className="icon-button mobile-menu" onClick={onMenu}><Menu size={20} /></button><div className="breadcrumb">Workspace <ChevronRight size={14} /> <strong>{page}</strong></div></div>
    <div className="topbar-actions"><div className="period-pill"><CalendarDays size={15} /><span>Nov 2026</span><ChevronDown size={14} /></div><button className="icon-button notification-button" onClick={() => toast("You're all caught up.")} aria-label="Notifications"><Bell size={18} /><i /></button><div className="top-avatar">US</div></div>
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
        <div className="cfo-foot"><CheckCircle2 size={14} /> Recommendations are linked to sample financial records.</div>
      </SectionCard>
    </div>
    <div className="lower-grid">
      <SectionCard title="Recent transactions" subtitle="The latest activity in your books" action={<button className="text-action" onClick={() => setPage("Transactions")}>All transactions <ArrowUpRight size={14} /></button>}>
        <TransactionTable transactions={recentTransactions} />
      </SectionCard>
      <SectionCard title="Risk radar" subtitle="A few things to keep on your radar" action={<button className="text-action" onClick={() => setPage("Risk Radar")}>See all <ArrowUpRight size={14} /></button>}>
        <div className="risk-list"><RiskItem tone="coral" title="Overdue customer invoices" detail="2 invoices · ₹85,000 outstanding" /><RiskItem tone="amber" title="Supplier price increase" detail="FreshKart costs rose by 12%" /><RiskItem tone="sage" title="December cash buffer" detail="Review inventory purchases before month-end" /></div>
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
  return <div className="page-stack"><PageIntro title="Cash flow" description="See where your money is going — and where it may take you." /><div className="metrics-grid compact-metrics"><MetricCard label="Opening balance" value="₹3,42,500" note="Current demo balance" icon={Wallet} /><MetricCard label="Expected inflows" value="₹1,24,000" note="Next 30 days" icon={TrendingUp} tone="sage" /><MetricCard label="Expected outflows" value="₹2,48,500" note="Next 30 days" icon={TrendingDown} tone="amber" /></div><SectionCard title="Balance forecast" subtitle="Historical balance and illustrative projection"><div className="chart-legend"><span><i className="legend-dot actual-dot" /> Actual</span><span><i className="legend-line" /> Forecast</span></div><div className="chart-main cashflow-detail-chart"><CashFlowChart detailed /></div></SectionCard><div className="two-col"><SectionCard title="Upcoming commitments" subtitle="Planned cash outflows"><div className="commitment-row"><span>Monthly rent</span><strong>₹22,000</strong><small>01 Dec</small></div><div className="commitment-row"><span>Inventory restock</span><strong>₹48,000</strong><small>05 Dec</small></div><div className="commitment-row"><span>Payroll</span><strong>₹76,000</strong><small>07 Dec</small></div></SectionCard><SectionCard title="Forecast assumptions" subtitle="What shapes this projection"><ul className="assumption-list"><li>Recent average sales and expenses</li><li>Recurring rent and payroll commitments</li><li>Expected collection of open invoices</li><li>Seasonal inventory purchase estimate</li></ul></SectionCard></div><div className="inline-note"><AlertCircle size={15} /> Forecast values are illustrative until the financial engine is connected.</div></div>;
}

function Simulator() {
  const [purchase, setPurchase] = useState(50000); const [revenue, setRevenue] = useState(15); const [showResult, setShowResult] = useState(false);
  const projected = 218000 - purchase + (purchase * revenue / 100);
  return <div className="page-stack"><PageIntro eyebrow="MAKE THE NEXT MOVE WITH CLARITY" title="What-if simulator" description="Explore a decision before it becomes a commitment." />
    <div className="simulator-layout"><SectionCard title="Build your scenario" subtitle="Adjust the assumptions to explore a possible decision"><div className="scenario-block"><div className="scenario-label"><div><span className="scenario-number">01</span><strong>New inventory purchase</strong></div><strong>{money(purchase)}</strong></div><input className="range-input" type="range" min="10000" max="200000" step="5000" value={purchase} onChange={e => { setPurchase(Number(e.target.value)); setShowResult(false); }} /><div className="range-labels"><span>₹10,000</span><span>₹2,00,000</span></div></div><div className="scenario-block"><div className="scenario-label"><div><span className="scenario-number">02</span><strong>Expected revenue uplift</strong></div><strong>{revenue}%</strong></div><input className="range-input" type="range" min="0" max="40" step="1" value={revenue} onChange={e => { setRevenue(Number(e.target.value)); setShowResult(false); }} /><div className="range-labels"><span>0%</span><span>40%</span></div></div><div className="scenario-summary"><div><span>Current 30-day projected balance</span><strong>₹2,18,000</strong></div><div><span>Scenario cost</span><strong className="amount-negative">−{money(purchase)}</strong></div><div><span>Estimated additional revenue</span><strong className="amount-positive">+{money(purchase * revenue / 100)}</strong></div></div><button className="button button-primary full-button" onClick={() => setShowResult(true)}><Sparkles size={16} /> Run this scenario</button></SectionCard>
      <div className="scenario-result"><div className="result-orbit"><Compass size={26} /></div><span className="eyebrow">YOUR SCENARIO OUTCOME</span><h2>{showResult ? money(projected) : "What could your balance look like?"}</h2><p>{showResult ? "Illustrative closing balance after the purchase and estimated revenue uplift." : "Set your assumptions and run the scenario to see an estimated impact on your cash position."}</p>{showResult && <div className={projected >= 150000 ? "verdict-positive" : "verdict-caution"}>{projected >= 150000 ? <CheckCircle2 size={16} /> : <AlertCircle size={16} />}{projected >= 150000 ? "Within the illustrative comfort range" : "Consider a smaller purchase or staged order"}</div>}<div className="result-foot"><AlertCircle size={14} /> Preview calculation only. Final decision support will use verified backend figures.</div></div></div>
  </div>;
}

function Invoices({ invoices, markPaid }: { invoices: typeof initialInvoices; markPaid: (id: string) => void }) {
  const [uploadName, setUploadName] = useState("");
  return <div className="page-stack"><PageIntro title="Invoices" description="Keep track of what you've billed and what is still due." action={<label className="button button-primary upload-button"><UploadCloud size={16} /> Upload invoice<input type="file" accept=".pdf,.png,.jpg,.jpeg" onChange={e => { const file = e.target.files?.[0]; if (file) { setUploadName(file.name); toast("File selected for the future invoice extraction workflow."); } }} /></label>} />
    {uploadName && <div className="upload-selected"><FileText size={16} /> {uploadName} <button onClick={() => setUploadName("")}><X size={14} /></button></div>}
    <div className="metrics-grid compact-metrics"><MetricCard label="Total outstanding" value="₹1,09,500" note="Across 3 invoices" icon={FileText} /><MetricCard label="Overdue" value="₹85,000" note="Needs follow-up" icon={Clock3} tone="coral" /><MetricCard label="Collected this month" value="₹1,84,000" note="Demo figure" icon={CheckCircle2} tone="sage" /></div>
    <SectionCard title="Invoice register" subtitle="Sample customer invoices"><div className="invoice-list">{invoices.map(inv => <div className="invoice-row" key={inv.id}><div className="invoice-file-icon"><FileText size={19} /></div><div className="invoice-main"><strong>{inv.id} · {inv.client}</strong><span>Due {inv.due}</span></div><strong className="invoice-amount">{money(inv.amount)}</strong><span className={`status-pill ${inv.status === "Overdue" ? "status-overdue" : inv.status === "Paid" ? "status-paid" : "status-pending"}`}>{inv.status}</span>{inv.status !== "Paid" && <button className="button button-small button-outline" onClick={() => markPaid(inv.id)}>Mark paid</button>}</div>)}</div></SectionCard><div className="inline-note"><AlertCircle size={15} /> Upload currently selects a file in the browser only. Secure invoice extraction and confirmation will be connected to the backend.</div></div>;
}

function RiskRadar() {
  return <div className="page-stack"><PageIntro title="Risk radar" description="Spot pressure points early, while you still have room to act." /><div className="risk-summary"><div className="risk-summary-icon"><ShieldAlert size={23} /></div><div><strong>2 items need attention</strong><span>Plus 1 planning consideration · sample analysis</span></div><span className="risk-tag">REVIEW RECOMMENDED</span></div><div className="risk-cards"><SectionCard title="Overdue receivables" subtitle="Cash tied up in unpaid invoices"><div className="risk-large-number">₹85,000</div><p className="body-copy">Two customer invoices have passed their due dates. Following up can help improve short-term liquidity.</p><div className="risk-detail"><span>Potential impact</span><strong>Cash collection delay</strong></div><button className="text-action" onClick={() => toast("Opening receivables follow-up workflow soon.")}>Review collection plan <ArrowRight size={14} /></button></SectionCard><SectionCard title="Supplier price movement" subtitle="Input cost pressure"><div className="risk-large-number">+12%</div><p className="body-copy">FreshKart Wholesale's recent sample purchase is higher than the previous baseline.</p><div className="risk-detail"><span>Potential impact</span><strong>Margin compression</strong></div><button className="text-action" onClick={() => toast("Supplier comparison will be available with transaction history.")}>Review supplier costs <ArrowRight size={14} /></button></SectionCard><SectionCard title="December cash buffer" subtitle="Forward-looking watch item"><div className="risk-large-number">90 days</div><p className="body-copy">The current sample forecast remains positive, but inventory timing could narrow the available buffer.</p><div className="risk-detail"><span>Potential impact</span><strong>Reduced flexibility</strong></div><button className="text-action" onClick={() => toast("Try the What-If Simulator to explore this decision.")}>Test a scenario <ArrowRight size={14} /></button></SectionCard></div><div className="inline-note"><AlertCircle size={15} /> These are demonstration alerts, not audited or live risk assessments.</div></div>;
}

function Copilot() {
  const [messages, setMessages] = useState([{ role: "assistant", text: "Hello! I'm your LedgerLens AI CFO. I can help you explore your sample cash flow, receivables and business decisions. What would you like to understand?" }]);
  const [draft, setDraft] = useState("");
  const send = (value = draft) => { if (!value.trim()) return; setMessages(m => [...m, { role: "user", text: value }, { role: "assistant", text: "That's a good question. In this frontend preview, I can show the conversation flow, but evidence-backed answers will be powered by your connected financial records once the backend is integrated. For now, the sample dashboard shows ₹85,000 in overdue receivables and a 30-day projected balance of ₹2,18,000." }]); setDraft(""); };
  return <div className="page-stack"><PageIntro title="Your AI financial copilot" description="Ask clearer questions. Make more confident decisions." /><div className="copilot-layout"><section className="chat-panel"><div className="chat-header"><div className="cfo-avatar"><Sparkles size={18} /></div><div><strong>LedgerLens CFO</strong><span><i className="online-dot" /> Demo assistant · Not connected to live data</span></div><button className="icon-button small" onClick={() => setMessages([{ role: "assistant", text: "Conversation cleared. What would you like to explore?" }])}><MoreHorizontal size={18} /></button></div><div className="chat-messages">{messages.map((m, i) => <div key={i} className={`chat-message ${m.role}`}><div className="message-avatar">{m.role === "assistant" ? <Sparkles size={15} /> : "US"}</div><div className="message-bubble">{m.text}</div></div>)}</div><div className="suggestion-row">{["Can I afford new inventory?", "What needs my attention?", "How much is overdue?"].map(s => <button key={s} onClick={() => send(s)}>{s}</button>)}</div><form className="chat-input-row" onSubmit={e => { e.preventDefault(); send(); }}><button type="button" className="icon-button small" onClick={() => toast("File attachments will be supported in a later integration.")}><Paperclip size={17} /></button><input value={draft} onChange={e => setDraft(e.target.value)} placeholder="Ask your financial copilot..." /><button type="submit" className="send-button" disabled={!draft.trim()}><Send size={17} /></button></form></section><aside className="copilot-side"><SectionCard title="Suggested questions" subtitle="Start with one of these"><div className="question-list">{["Can I afford a ₹50,000 inventory order?", "Which invoices should I follow up on?", "What is changing my cash position?"].map(q => <button key={q} onClick={() => send(q)}>{q}<ArrowUpRight size={15} /></button>)}</div></SectionCard><div className="evidence-note"><ShieldAlert size={17} /><div><strong>Evidence before advice</strong><p>LedgerLens is designed to ground recommendations in transactions, invoices and forecast assumptions — not invented numbers.</p></div></div></aside></div></div>;
}

function Receivables({ invoices, markPaid }: { invoices: typeof initialInvoices; markPaid: (id: string) => void }) {
  const outstanding = invoices.filter(i => i.status !== "Paid").reduce((s, i) => s + i.amount, 0);
  return <div className="page-stack"><PageIntro title="Receivables" description="A gentle nudge today can make tomorrow's cash flow easier." /><div className="metrics-grid compact-metrics"><MetricCard label="Outstanding" value={money(outstanding)} note="Open sample invoices" icon={Wallet} /><MetricCard label="Overdue accounts" value={String(invoices.filter(i => i.status === "Overdue").length)} note="Need a follow-up" icon={Clock3} tone="coral" /><MetricCard label="Collection progress" value="62%" note="Illustrative month-to-date" icon={Activity} tone="sage" /></div><SectionCard title="Who owes you" subtitle="Open invoices and follow-up actions"><div className="receivable-list">{invoices.filter(i => i.status !== "Paid").map(i => <div className="receivable-row" key={i.id}><div className="client-avatar">{i.client.slice(0,1)}</div><div className="receivable-client"><strong>{i.client}</strong><span>{i.id} · Due {i.due}</span></div><div className="receivable-amount"><strong>{money(i.amount)}</strong><span className={i.status === "Overdue" ? "negative-change" : "muted-text"}>{i.status}</span></div><button className="button button-small button-outline" onClick={() => toast(`A reminder draft for ${i.client} will be available after backend integration.`)}>Draft reminder</button><button className="button button-small button-primary" onClick={() => markPaid(i.id)}>Mark paid</button></div>)}</div></SectionCard><div className="inline-note"><AlertCircle size={15} /> Marking an invoice paid updates this local preview only. The connected backend will update authoritative balances and forecasts.</div></div>;
}

function OverviewFooter() {
  return <footer className="app-footer"><span>LedgerLens · See beyond the numbers.</span><span><i className="demo-dot" /> Sample workspace · 19 Nov 2026</span></footer>;
}

export default function App() {
  const [page, setPage] = useState<Page>("Overview");
  const [menuOpen, setMenuOpen] = useState(false);
  useEffect(() => {
    getDashboard().then(setDashboard).catch((error: unknown) => {
      const message = error instanceof Error ? error.message : "Could not load dashboard data";
      toast.error(`Backend connection: ${message}`);
    });
  }, []);
  const [transactions, setTransactions] = useState(initialTransactions);
  const [dashboard, setDashboard] = useState<DashboardResponse | null>(null);
  const [invoices, setInvoices] = useState(initialInvoices);
  const addTransaction = (t: Transaction) => { setTransactions(old => [t, ...old]); };
  const markPaid = (id: string) => { setInvoices(old => old.map(i => i.id === id ? { ...i, status: "Paid" } : i)); toast.success("Invoice marked as paid in this preview."); };
  const pageContent = useMemo(() => {
    switch (page) {
      case "Overview": return <Overview setPage={setPage} transactions={transactions} dashboard={dashboard} />;
      case "Transactions": return <Transactions addTransaction={addTransaction} />;
      case "Cash Flow": return <CashFlow />;
      case "What-If Simulator": return <Simulator />;
      case "Invoices": return <Invoices invoices={invoices} markPaid={markPaid} />;
      case "Risk Radar": return <RiskRadar />;
      case "AI Financial Copilot": return <Copilot />;
      case "Receivables": return <Receivables invoices={invoices} markPaid={markPaid} />;
      default: return null;
    }
  }, [page, transactions, invoices]);
  return <div className="app-shell"><Toaster position="top-right" richColors /><Sidebar page={page} setPage={setPage} open={menuOpen} close={() => setMenuOpen(false)} /><main className="main-area"><Header page={page} onMenu={() => setMenuOpen(true)} /><div className="page-container">{pageContent}<OverviewFooter /></div></main></div>;
}
