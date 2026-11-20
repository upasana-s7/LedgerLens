"""Synthetic seed data for the LedgerLens demo business.

ALL DATA IN THIS FILE IS FICTIONAL. "Bloom & Bean" does not exist, the
customers and vendors are invented, and every GSTIN is a placeholder beginning
with "SYNTH". Nothing here comes from a real business.

The dataset is fully deterministic: it uses its own `random.Random(2026)`
instance, and the fixed demo date from settings (`2026-11-19`) instead of
today's date. Running the seed twice produces byte-identical rows.

How the numbers are made to land exactly
----------------------------------------
Each month (and, for October, each half of the month) has an exact target for
the *net cash movement*. Almost every transaction is a realistic fixed or
jittered amount; exactly one "Counter sales" row per window is left as the
flexible "plug" and is set to whatever amount makes the window add up. That is
why the retail counter sales vary month to month - the way real walk-in takings
would.

Usage
-----
    python -m app.seed.seed_data            # seed if the DB is empty
    python -m app.seed.seed_data --reset    # wipe and rebuild
"""

from __future__ import annotations

import argparse
import hashlib
import random
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import SessionLocal, init_db
from app.models import (
    BusinessProfile,
    ChatMessage,
    Commitment,
    Counterparty,
    Invoice,
    RiskAlert,
    SimulationRun,
    Transaction,
    UploadBatch,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

RNG_SEED = 2026
AS_OF_DATE = date.fromisoformat(settings.AS_OF_DATE)  # 2026-11-19
START_DATE = date(2026, 6, 1)

# Cash in the bank on 2026-06-01, before any seeded transaction.
OPENING_BALANCE = Decimal("250000.00")

# Expected cash balance on the demo "today".
TARGET_CASH = Decimal("342500.00")

# Closing balance for each completed month.
MONTH_END_TARGETS = {
    date(2026, 6, 30): Decimal("310000.00"),
    date(2026, 7, 31): Decimal("355000.00"),
    date(2026, 8, 31): Decimal("328000.00"),
    date(2026, 9, 30): Decimal("392000.00"),
    date(2026, 10, 31): Decimal("365000.00"),
}

# Balance one month before the demo date, used for the "+8.2% vs last month"
# KPI. We allow a small tolerance when checking it.
BALANCE_ON_2026_10_19 = Decimal("316544.00")
BALANCE_TOLERANCE = Decimal("300.00")

# The five most recent transactions, fixed by the product spec (the frontend
# shows exactly these).
LAST_FIVE = [
    ("TXN-1044", date(2026, 11, 15), "Electricity & utilities", "Utilities", Decimal("-6800.00"), "expense"),
    ("TXN-1045", date(2026, 11, 16), "Cafe Bloom — catering", "Sales", Decimal("32750.00"), "income"),
    ("TXN-1046", date(2026, 11, 17), "November workspace rent", "Rent", Decimal("-22000.00"), "expense"),
    ("TXN-1047", date(2026, 11, 18), "FreshKart Wholesale", "Inventory", Decimal("-18400.00"), "expense"),
    ("TXN-1048", date(2026, 11, 19), "Aarav Foods — bulk order", "Sales", Decimal("48500.00"), "income"),
]

# Net cash movement each window must produce. "oct_a" is 1-19 Oct and "oct_b"
# is 20-31 Oct, because the demo also pins the balance on 19 Oct.
WINDOW_TARGETS = {
    "2026-06": Decimal("60000.00"),
    "2026-07": Decimal("45000.00"),
    "2026-08": Decimal("-27000.00"),
    "2026-09": Decimal("64000.00"),
    "2026-10-a": Decimal("-75456.00"),  # 392000 -> 316544
    "2026-10-b": Decimal("48456.00"),   # 316544 -> 365000
    "2026-11": Decimal("-22500.00"),    # 365000 -> 342500
}

# A "plug" row should still look like a believable retail sale.
MIN_FLEX = Decimal("5000.00")
MAX_FLEX = Decimal("45000.00")

CATEGORIES = {"Sales", "Inventory", "Rent", "Utilities", "Payroll", "General"}

# ---------------------------------------------------------------------------
# Business, customers, vendors
# ---------------------------------------------------------------------------

PROFILE = {
    "name": "Bloom & Bean",
    "business_type": "Small business",
    "city": "Bengaluru",
    "industry": "Specialty coffee & bakery supplier",
    "currency": "INR",
    "opening_balance": OPENING_BALANCE,
    "start_date": START_DATE,
    "as_of_date": AS_OF_DATE,
    "min_cash_buffer": Decimal("150000.00"),
    "is_synthetic": True,
}

# GSTINs are deliberately fake placeholders ("SYNTH" + a serial).
COUNTERPARTIES = [
    {"name": "Aarav Foods", "type": "customer", "gstin": "29SYNTH0001A1Z1", "payment_terms_days": 30},
    {"name": "The Daily Table", "type": "customer", "gstin": "29SYNTH0002A1Z1", "payment_terms_days": 30},
    {"name": "Cafe Bloom", "type": "customer", "gstin": "29SYNTH0003A1Z1", "payment_terms_days": 15},
    {"name": "FreshKart Wholesale", "type": "vendor", "gstin": "29SYNTH0004A1Z1", "payment_terms_days": 15},
    {"name": "Sri Lakshmi Packaging", "type": "vendor", "gstin": "29SYNTH0005A1Z1", "payment_terms_days": 7},
]

# ---------------------------------------------------------------------------
# Invoices
# ---------------------------------------------------------------------------
# status is only ever "Draft", "Pending" or "Paid". "Overdue" is computed later
# from due_date vs as_of_date, never stored.
#
# The three Pending invoices are the open receivables (52,000 + 33,000 +
# 24,500 = 109,500). The four paid in November add up to 184,000.
INVOICES = [
    # --- June ---
    {"id": "INV-181", "client": "Aarav Foods", "issue_date": date(2026, 6, 2), "due_date": date(2026, 6, 17), "amount": Decimal("57000.00"), "status": "Paid", "paid_date": date(2026, 6, 19)},
    {"id": "INV-182", "client": "The Daily Table", "issue_date": date(2026, 6, 5), "due_date": date(2026, 6, 20), "amount": Decimal("57000.00"), "status": "Paid", "paid_date": date(2026, 6, 23)},
    {"id": "INV-183", "client": "Cafe Bloom", "issue_date": date(2026, 6, 9), "due_date": date(2026, 6, 24), "amount": Decimal("57000.00"), "status": "Paid", "paid_date": date(2026, 6, 26)},
    {"id": "INV-184", "client": "Aarav Foods", "issue_date": date(2026, 6, 12), "due_date": date(2026, 6, 27), "amount": Decimal("57000.00"), "status": "Paid", "paid_date": date(2026, 6, 29)},
    # --- July ---
    {"id": "INV-185", "client": "The Daily Table", "issue_date": date(2026, 7, 2), "due_date": date(2026, 7, 17), "amount": Decimal("49000.00"), "status": "Paid", "paid_date": date(2026, 7, 17)},
    {"id": "INV-186", "client": "Cafe Bloom", "issue_date": date(2026, 7, 6), "due_date": date(2026, 7, 21), "amount": Decimal("49000.00"), "status": "Paid", "paid_date": date(2026, 7, 21)},
    {"id": "INV-188", "client": "Aarav Foods", "issue_date": date(2026, 7, 9), "due_date": date(2026, 7, 24), "amount": Decimal("49000.00"), "status": "Paid", "paid_date": date(2026, 7, 24)},
    {"id": "INV-190", "client": "The Daily Table", "issue_date": date(2026, 7, 13), "due_date": date(2026, 7, 28), "amount": Decimal("49000.00"), "status": "Paid", "paid_date": date(2026, 7, 28)},
    # --- August ---
    {"id": "INV-192", "client": "Cafe Bloom", "issue_date": date(2026, 8, 3), "due_date": date(2026, 8, 14), "amount": Decimal("52000.00"), "status": "Paid", "paid_date": date(2026, 8, 14)},
    {"id": "INV-194", "client": "Aarav Foods", "issue_date": date(2026, 8, 7), "due_date": date(2026, 8, 19), "amount": Decimal("52000.00"), "status": "Paid", "paid_date": date(2026, 8, 19)},
    {"id": "INV-196", "client": "The Daily Table", "issue_date": date(2026, 8, 12), "due_date": date(2026, 8, 24), "amount": Decimal("52000.00"), "status": "Paid", "paid_date": date(2026, 8, 24)},
    {"id": "INV-199", "client": "Cafe Bloom", "issue_date": date(2026, 8, 17), "due_date": date(2026, 8, 28), "amount": Decimal("52000.00"), "status": "Paid", "paid_date": date(2026, 8, 28)},
    # --- September ---
    {"id": "INV-202", "client": "Aarav Foods", "issue_date": date(2026, 9, 2), "due_date": date(2026, 9, 16), "amount": Decimal("70000.00"), "status": "Paid", "paid_date": date(2026, 9, 16)},
    {"id": "INV-207", "client": "The Daily Table", "issue_date": date(2026, 9, 6), "due_date": date(2026, 9, 19), "amount": Decimal("70000.00"), "status": "Paid", "paid_date": date(2026, 9, 19)},
    {"id": "INV-209", "client": "Cafe Bloom", "issue_date": date(2026, 9, 11), "due_date": date(2026, 9, 24), "amount": Decimal("70000.00"), "status": "Paid", "paid_date": date(2026, 9, 24)},
    {"id": "INV-210", "client": "Aarav Foods", "issue_date": date(2026, 9, 15), "due_date": date(2026, 9, 29), "amount": Decimal("70000.00"), "status": "Paid", "paid_date": date(2026, 9, 29)},
    # --- October ---
    {"id": "INV-197", "client": "Aarav Foods", "issue_date": date(2026, 10, 5), "due_date": date(2026, 10, 16), "amount": Decimal("62000.00"), "status": "Paid", "paid_date": date(2026, 10, 16)},
    {"id": "INV-200", "client": "The Daily Table", "issue_date": date(2026, 10, 12), "due_date": date(2026, 10, 27), "amount": Decimal("55000.00"), "status": "Paid", "paid_date": date(2026, 10, 27)},
    # --- November (paid early in the month: 184,000 in total) ---
    {"id": "INV-205", "client": "Cafe Bloom", "issue_date": date(2026, 10, 20), "due_date": date(2026, 11, 4), "amount": Decimal("62000.00"), "status": "Paid", "paid_date": date(2026, 11, 4)},
    {"id": "INV-201", "client": "Aarav Foods", "issue_date": date(2026, 10, 22), "due_date": date(2026, 11, 6), "amount": Decimal("45000.00"), "status": "Paid", "paid_date": date(2026, 11, 8)},
    {"id": "INV-203", "client": "Aarav Foods", "issue_date": date(2026, 10, 26), "due_date": date(2026, 11, 10), "amount": Decimal("28500.00"), "status": "Paid", "paid_date": date(2026, 11, 12)},
    {"id": "INV-206", "client": "Aarav Foods", "issue_date": date(2026, 10, 30), "due_date": date(2026, 11, 14), "amount": Decimal("48500.00"), "status": "Paid", "paid_date": date(2026, 11, 14)},
    # --- Still open on 2026-11-19 (109,500 outstanding) ---
    {"id": "INV-198", "client": "The Daily Table", "issue_date": date(2026, 10, 9), "due_date": date(2026, 11, 8), "amount": Decimal("33000.00"), "status": "Pending", "paid_date": None},
    {"id": "INV-204", "client": "Aarav Foods", "issue_date": date(2026, 10, 13), "due_date": date(2026, 11, 12), "amount": Decimal("52000.00"), "status": "Pending", "paid_date": None},
    {"id": "INV-211", "client": "Cafe Bloom", "issue_date": date(2026, 11, 10), "due_date": date(2026, 11, 28), "amount": Decimal("24500.00"), "status": "Pending", "paid_date": None},
]

# ---------------------------------------------------------------------------
# Commitments (known future payments)
# ---------------------------------------------------------------------------
# Everything due 2026-11-20 .. 2026-12-19 must total 248,500.
COMMITMENTS = [
    {"label": "Loan EMI", "amount": Decimal("18500.00"), "due_date": date(2026, 12, 5), "category": "General", "is_recurring": True, "counterparty": None},
    {"label": "Inventory restock", "amount": Decimal("48000.00"), "due_date": date(2026, 12, 5), "category": "Inventory", "is_recurring": False, "counterparty": "FreshKart Wholesale"},
    {"label": "Monthly rent", "amount": Decimal("22000.00"), "due_date": date(2026, 12, 1), "category": "Rent", "is_recurring": True, "counterparty": None},
    {"label": "Payroll", "amount": Decimal("76000.00"), "due_date": date(2026, 12, 7), "category": "Payroll", "is_recurring": True, "counterparty": None},
    {"label": "FreshKart payable", "amount": Decimal("41000.00"), "due_date": date(2026, 11, 28), "category": "Inventory", "is_recurring": False, "counterparty": "FreshKart Wholesale"},
    {"label": "Packaging supplies", "amount": Decimal("10000.00"), "due_date": date(2026, 11, 30), "category": "Inventory", "is_recurring": False, "counterparty": "Sri Lakshmi Packaging"},
    {"label": "Utilities & internet", "amount": Decimal("9000.00"), "due_date": date(2026, 12, 10), "category": "Utilities", "is_recurring": True, "counterparty": None},
    {"label": "GST payment", "amount": Decimal("24000.00"), "due_date": date(2026, 12, 18), "category": "General", "is_recurring": False, "counterparty": None},
    # Deliberately outside the 30-day window, so the window filter is testable.
    {"label": "Quarterly advance tax", "amount": Decimal("30000.00"), "due_date": date(2026, 12, 28), "category": "General", "is_recurring": False, "counterparty": None},
]

# Keep things easy to tweak: the months generated by the template loop.
INVENTORY_DAYS = [3, 6, 11, 14, 18, 21, 24, 29]
COUNTER_DAYS = [2, 5, 9, 12, 16, 20, 23, 27]
PACKAGING_DAYS = [9, 22]
MARKETING_DAYS = [12, 26]

# Per-month knobs. `inventory_price` rises over time (~12% from June to Sept),
# which is the planted "costs are creeping up" pattern for the Risk Radar.
MONTH_PARAMS = {
    date(2026, 6, 1): {"inventory_price": Decimal("14000.00"), "electricity": Decimal("6200.00"), "gst": Decimal("21000.00")},
    date(2026, 7, 1): {"inventory_price": Decimal("14300.00"), "electricity": Decimal("6400.00"), "gst": None},
    date(2026, 8, 1): {"inventory_price": Decimal("15200.00"), "electricity": Decimal("6100.00"), "gst": None},
    date(2026, 9, 1): {"inventory_price": Decimal("15700.00"), "electricity": Decimal("6600.00"), "gst": Decimal("24000.00")},
}


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def _money(value) -> Decimal:
    """Round to whole rupees and return a 2-decimal Decimal."""
    return Decimal(value).quantize(Decimal("0.01"))


def _month_end(year: int, month: int) -> date:
    """Last calendar day of a month."""
    if month == 12:
        return date(year, 12, 31)
    return date(year, month + 1, 1) - timedelta(days=1)


def _tx(
    when: date,
    name: str,
    category: str,
    amount,
    kind: str,
    *,
    counterparty: str | None = None,
    invoice_id: str | None = None,
    payment_mode: str = "Bank transfer",
    group: str | None = None,
) -> dict:
    """Build one transaction row.

    `amount=None` marks the flexible "plug" row for the given `group`.
    """
    assert category in CATEGORIES, f"unknown category {category}"
    return {
        "date": when,
        "name": name,
        "category": category,
        "amount": None if amount is None else _money(amount),
        "type": kind,
        "counterparty": counterparty,
        "invoice_id": invoice_id,
        "payment_mode": payment_mode,
        "group": group,
        "source": "synthetic",
    }


def _assign_group(rows: list[dict], group: str) -> list[dict]:
    """Tag every row in a window so its net can be balanced later."""
    for row in rows:
        row["group"] = group
    return rows


def _counter_mode(index: int) -> str:
    """Walk-in customers pay by whatever they have: rotate deterministically."""
    return ("UPI", "Cash", "Card")[index % 3]


# ---------------------------------------------------------------------------
# Building the transactions
# ---------------------------------------------------------------------------


def _template_month(rng: random.Random, month_start: date, params: dict, group: str) -> list[dict]:
    """Generate one ordinary month (June - September) from the template."""
    y, m = month_start.year, month_start.month
    rows: list[dict] = []

    # --- Fixed monthly costs ------------------------------------------------
    rows.append(_tx(date(y, m, 1), "Monthly workspace rent", "Rent", Decimal("-22000.00"), "expense"))
    rows.append(_tx(date(y, m, 5), "Loan EMI — equipment loan", "General", Decimal("-18500.00"), "expense", payment_mode="Bank transfer"))
    rows.append(_tx(date(y, m, 7), "Monthly payroll", "Payroll", Decimal("-76000.00"), "expense"))
    rows.append(_tx(date(y, m, 10), "Internet & phone", "Utilities", Decimal("-2150.00"), "expense", payment_mode="UPI"))
    rows.append(
        _tx(date(y, m, 15), "Electricity & utilities (BESCOM)", "Utilities", -params["electricity"], "expense", payment_mode="UPI")
    )

    if params["gst"] is not None:
        rows.append(_tx(date(y, m, 20), "GST payment", "General", -params["gst"], "expense"))

    # --- Stock purchases from the main vendor -------------------------------
    # Prices creep upward month by month; small jitter keeps it lifelike.
    for day in INVENTORY_DAYS:
        jitter = Decimal(rng.randint(-400, 400))
        price = _money(params["inventory_price"] + jitter)
        rows.append(
            _tx(date(y, m, day), "FreshKart Wholesale", "Inventory", -price, "expense", counterparty="FreshKart Wholesale")
        )

    # --- Packaging and marketing -------------------------------------------
    for i, day in enumerate(PACKAGING_DAYS):
        amount = _money(Decimal(6800 + i * 400 + rng.randint(-200, 200)))
        rows.append(
            _tx(date(y, m, day), "Packaging supplies", "Inventory", -amount, "expense", counterparty="Sri Lakshmi Packaging")
        )

    for i, day in enumerate(MARKETING_DAYS):
        amount = _money(Decimal(6000 + i * 300 + rng.randint(-250, 250)))
        rows.append(_tx(date(y, m, day), "Marketing — Instagram ads", "General", -amount, "expense", payment_mode="Card"))

    # --- Walk-in counter sales ---------------------------------------------
    # The last one in the month is the flexible plug for this window.
    for i, day in enumerate(COUNTER_DAYS):
        is_flex = i == len(COUNTER_DAYS) - 1
        amount = None if is_flex else _money(Decimal(rng.randint(10800, 15200)))
        rows.append(
            _tx(
                date(y, m, day),
                "Counter sales (walk-in)",
                "Sales",
                amount,
                "income",
                payment_mode=_counter_mode(i),
                group=group,
            )
        )

    # --- Invoice settlements ------------------------------------------------
    for inv in INVOICES:
        if inv["client"] and inv["status"] == "Paid" and inv["paid_date"] and inv["paid_date"].month == m and inv["paid_date"].year == y:
            rows.append(
                _tx(
                    inv["paid_date"],
                    f"{inv['client']} — invoice {inv['id']}",
                    "Sales",
                    inv["amount"],
                    "income",
                    counterparty=inv["client"],
                    invoice_id=inv["id"],
                )
            )

    # Everything above belongs to this month's balancing window.
    return _assign_group(rows, group)


def _october_rows() -> list[dict]:
    """October is written out by hand: it has two targets inside one month."""
    rows = [
        # --- 1-19 October (balance must be 316,544 on the 19th) --------------
        _tx(date(2026, 10, 1), "October workspace rent", "Rent", Decimal("-22000.00"), "expense"),
        _tx(date(2026, 10, 3), "FreshKart Wholesale", "Inventory", Decimal("-16500.00"), "expense", counterparty="FreshKart Wholesale"),
        _tx(date(2026, 10, 5), "Loan EMI — equipment loan", "General", Decimal("-18500.00"), "expense"),
        _tx(date(2026, 10, 7), "Monthly payroll", "Payroll", Decimal("-76000.00"), "expense"),
        _tx(date(2026, 10, 10), "Internet & phone", "Utilities", Decimal("-2150.00"), "expense", payment_mode="UPI"),
        _tx(date(2026, 10, 13), "FreshKart Wholesale", "Inventory", Decimal("-18000.00"), "expense", counterparty="FreshKart Wholesale"),
        _tx(date(2026, 10, 15), "Electricity & utilities (BESCOM)", "Utilities", Decimal("-6700.00"), "expense", payment_mode="UPI"),
        _tx(date(2026, 10, 16), "Aarav Foods — invoice INV-197", "Sales", Decimal("62000.00"), "income", counterparty="Aarav Foods", invoice_id="INV-197"),
        _tx(date(2026, 10, 18), "Counter sales (walk-in)", "Sales", None, "income", payment_mode="Cash", group="2026-10-a"),
        # --- 20-31 October (balance must be 365,000 on the 31st) -------------
        _tx(date(2026, 10, 21), "FreshKart Wholesale", "Inventory", Decimal("-15500.00"), "expense", counterparty="FreshKart Wholesale"),
        _tx(date(2026, 10, 22), "Packaging supplies", "Inventory", Decimal("-7000.00"), "expense", counterparty="Sri Lakshmi Packaging"),
        _tx(date(2026, 10, 24), "Counter sales (walk-in)", "Sales", Decimal("13000.00"), "income", payment_mode="UPI"),
        _tx(date(2026, 10, 26), "Marketing — Instagram ads", "General", Decimal("-6500.00"), "expense", payment_mode="Card"),
        _tx(date(2026, 10, 27), "The Daily Table — invoice INV-200", "Sales", Decimal("55000.00"), "income", counterparty="The Daily Table", invoice_id="INV-200"),
        _tx(date(2026, 10, 28), "Packaging supplies", "Inventory", Decimal("-7000.00"), "expense", counterparty="Sri Lakshmi Packaging"),
        _tx(date(2026, 10, 30), "Counter sales (walk-in)", "Sales", None, "income", payment_mode="Card", group="2026-10-b"),
    ]
    # Two windows inside one month: the balance is pinned on the 19th and the
    # 31st, so each half needs its own flexible counter-sale row.
    for row in rows:
        if row["group"] is None:
            row["group"] = "2026-10-a" if row["date"] <= date(2026, 10, 19) else "2026-10-b"
    return rows


def _november_rows() -> list[dict]:
    """1-19 November, written by hand so the last five rows are exactly right.

    Note the deliberate anomalies left for the Risk Radar to discover later:
    a big festive stock order, a van down payment, and a bonus - all plausible,
    nothing flagged in the data itself.
    """
    rows = [
        _tx(date(2026, 11, 2), "Counter sales (walk-in)", "Sales", Decimal("13600.00"), "income", payment_mode="Cash"),
        _tx(date(2026, 11, 3), "FreshKart Wholesale", "Inventory", Decimal("-15600.00"), "expense", counterparty="FreshKart Wholesale"),
        _tx(date(2026, 11, 4), "Cafe Bloom — invoice INV-205", "Sales", Decimal("62000.00"), "income", counterparty="Cafe Bloom", invoice_id="INV-205"),
        _tx(date(2026, 11, 5), "Loan EMI — equipment loan", "General", Decimal("-18500.00"), "expense"),
        _tx(date(2026, 11, 6), "Counter sales (walk-in)", "Sales", Decimal("14200.00"), "income", payment_mode="UPI"),
        _tx(date(2026, 11, 6), "Deepavali staff bonus", "Payroll", Decimal("-25000.00"), "expense"),
        _tx(date(2026, 11, 7), "Monthly payroll", "Payroll", Decimal("-76000.00"), "expense"),
        _tx(date(2026, 11, 8), "Aarav Foods — invoice INV-201", "Sales", Decimal("45000.00"), "income", counterparty="Aarav Foods", invoice_id="INV-201"),
        _tx(date(2026, 11, 9), "Packaging supplies", "Inventory", Decimal("-8400.00"), "expense", counterparty="Sri Lakshmi Packaging"),
        _tx(date(2026, 11, 10), "Internet & phone", "Utilities", Decimal("-2150.00"), "expense", payment_mode="UPI"),
        _tx(date(2026, 11, 10), "GST payment", "General", Decimal("-31000.00"), "expense"),
        _tx(date(2026, 11, 11), "FreshKart Wholesale", "Inventory", Decimal("-21500.00"), "expense", counterparty="FreshKart Wholesale"),
        _tx(date(2026, 11, 11), "FreshKart Wholesale — festive stock", "Inventory", Decimal("-32000.00"), "expense", counterparty="FreshKart Wholesale"),
        _tx(date(2026, 11, 12), "Aarav Foods — invoice INV-203", "Sales", Decimal("28500.00"), "income", counterparty="Aarav Foods", invoice_id="INV-203"),
        _tx(date(2026, 11, 13), "Counter sales (walk-in)", "Sales", None, "income", payment_mode="UPI", group="2026-11"),
        _tx(date(2026, 11, 13), "Delivery van down payment", "General", Decimal("-48000.00"), "expense"),
        _tx(date(2026, 11, 14), "Aarav Foods — invoice INV-206", "Sales", Decimal("48500.00"), "income", counterparty="Aarav Foods", invoice_id="INV-206"),
        _tx(date(2026, 11, 14), "Marketing — festive campaign", "General", Decimal("-6500.00"), "expense", payment_mode="Card"),
        _tx(date(2026, 11, 14), "Business insurance renewal", "General", Decimal("-3900.00"), "expense"),
        # --- The five rows the frontend shows as "recent activity" ----------
        _tx(date(2026, 11, 15), "Electricity & utilities", "Utilities", Decimal("-6800.00"), "expense", payment_mode="UPI"),
        _tx(date(2026, 11, 16), "Cafe Bloom — catering", "Sales", Decimal("32750.00"), "income", counterparty="Cafe Bloom"),
        _tx(date(2026, 11, 17), "November workspace rent", "Rent", Decimal("-22000.00"), "expense"),
        _tx(date(2026, 11, 18), "FreshKart Wholesale", "Inventory", Decimal("-18400.00"), "expense", counterparty="FreshKart Wholesale"),
        _tx(date(2026, 11, 19), "Aarav Foods — bulk order", "Sales", Decimal("48500.00"), "income", counterparty="Aarav Foods"),
    ]
    return _assign_group(rows, "2026-11")


def _apply_window_targets(rows: list[dict]) -> None:
    """Set each flexible counter-sale row so its window hits the target exactly."""
    for group, target in WINDOW_TARGETS.items():
        window_rows = [r for r in rows if r["group"] == group]
        flex_rows = [r for r in window_rows if r["amount"] is None]

        assert len(flex_rows) == 1, f"window {group} needs exactly one flexible row, found {len(flex_rows)}"

        fixed_total = sum((r["amount"] for r in window_rows if r["amount"] is not None), Decimal("0.00"))
        flex_amount = _money(target - fixed_total)

        assert MIN_FLEX <= flex_amount <= MAX_FLEX, (
            f"window {group}: plug amount ₹{flex_amount} is not believable "
            f"(allowed ₹{MIN_FLEX} - ₹{MAX_FLEX}); adjust that window's invoices or costs"
        )
        flex_rows[0]["amount"] = flex_amount


def build_dataset() -> dict:
    """Build the whole synthetic dataset in memory (no database yet)."""
    rng = random.Random(RNG_SEED)

    rows: list[dict] = []
    # June - September are generated from the template, each month balancing
    # to its own exact closing balance.
    for month_start, group in [
        (date(2026, 6, 1), "2026-06"),
        (date(2026, 7, 1), "2026-07"),
        (date(2026, 8, 1), "2026-08"),
        (date(2026, 9, 1), "2026-09"),
    ]:
        rows.extend(_template_month(rng, month_start, MONTH_PARAMS[month_start], group))

    # --- Planted anomalies (Stage 6 will have to spot these) ----------------
    # 1. One unusually large one-off repair in August.
    rows.append(
        _tx(
            date(2026, 8, 21),
            "Cold room compressor replacement",
            "General",
            Decimal("-78000.00"),
            "expense",
            group="2026-08",
        )
    )
    # 2. Two near-identical vendor payments on consecutive days in September:
    #    looks like a duplicate payment to FreshKart.
    rows.append(
        _tx(
            date(2026, 9, 12),
            "FreshKart Wholesale",
            "Inventory",
            Decimal("-14800.00"),
            "expense",
            counterparty="FreshKart Wholesale",
            group="2026-09",
        )
    )
    rows.append(
        _tx(
            date(2026, 9, 13),
            "FreshKart Wholesale",
            "Inventory",
            Decimal("-14800.00"),
            "expense",
            counterparty="FreshKart Wholesale",
            group="2026-09",
        )
    )

    rows.extend(_october_rows())
    rows.extend(_november_rows())

    _apply_window_targets(rows)

    # --- Sort chronologically and number the ids ---------------------------
    # Ids are assigned in date order, so the newest transaction gets the
    # highest number. The sequence ends at TXN-1048 (the id the frontend
    # shows), which means it starts lower down for a multi-month history.
    rows.sort(key=lambda r: (r["date"],))
    # Python's sort is stable, so rows on the same day keep their build order.
    for index, row in enumerate(rows):
        number = 1049 - len(rows) + index
        row["id"] = f"TXN-{number:04d}"

    invoice_rows = []
    for inv in INVOICES:
        invoice_rows.append(
            {
                **inv,
                "gst_amount": Decimal("0.00"),
                "paid_amount": inv["amount"] if inv["status"] == "Paid" else Decimal("0.00"),
                "counterparty": inv["client"],
                "source": "synthetic",
            }
        )

    return {
        "profile": PROFILE,
        "counterparties": COUNTERPARTIES,
        "invoices": invoice_rows,
        "transactions": rows,
        "commitments": COMMITMENTS,
    }


# ---------------------------------------------------------------------------
# Writing to the database
# ---------------------------------------------------------------------------


def _is_seeded(session: Session) -> bool:
    """True when there is already data, so seeding can be skipped."""
    return (session.scalar(select(func.count()).select_from(Transaction)) or 0) > 0


def _wipe_all(session: Session) -> None:
    """Delete every row, children first so foreign keys never dangle."""
    for model in (
        Transaction,
        Invoice,
        Commitment,
        RiskAlert,
        ChatMessage,
        SimulationRun,
        UploadBatch,
        Counterparty,
        BusinessProfile,
    ):
        session.execute(delete(model))
    session.flush()


def _persist(session: Session, data: dict) -> None:
    """Insert the in-memory dataset."""
    session.add(BusinessProfile(**data["profile"]))
    session.flush()

    counterparty_ids: dict[str, int] = {}
    for row in data["counterparties"]:
        party = Counterparty(**row)
        session.add(party)
        session.flush()
        counterparty_ids[party.name] = party.id

    for row in data["invoices"]:
        session.add(
            Invoice(
                id=row["id"],
                invoice_number=row["id"].replace("INV-", "BB-2026-"),
                counterparty_id=counterparty_ids[row["counterparty"]],
                client=row["client"],
                issue_date=row["issue_date"],
                due_date=row["due_date"],
                amount=row["amount"],
                gst_amount=row["gst_amount"],
                status=row["status"],
                paid_amount=row["paid_amount"],
                paid_date=row["paid_date"],
                extraction_json=None,  # only filled by Stage 9 invoice uploads
                confidence=None,
                source=row["source"],
                # Deterministic timestamps keep reseeding byte-identical.
                created_at=datetime.combine(row["issue_date"], time(9, 0)),
            )
        )

    for row in data["transactions"]:
        session.add(
            Transaction(
                id=row["id"],
                date=row["date"],
                name=row["name"],
                category=row["category"],
                amount=row["amount"],
                type=row["type"],
                counterparty_id=counterparty_ids.get(row["counterparty"]) if row["counterparty"] else None,
                payment_mode=row["payment_mode"],
                invoice_id=row["invoice_id"],
                source=row["source"],
                upload_batch_id=None,
                created_at=datetime.combine(row["date"], time(10, 0)),
            )
        )

    for row in data["commitments"]:
        session.add(
            Commitment(
                label=row["label"],
                amount=row["amount"],
                due_date=row["due_date"],
                category=row["category"],
                is_recurring=row["is_recurring"],
                counterparty_id=counterparty_ids.get(row["counterparty"]) if row["counterparty"] else None,
            )
        )


# ---------------------------------------------------------------------------
# Hard targets - checked every time the seed runs
# ---------------------------------------------------------------------------


def _opening_balance(session: Session) -> Decimal:
    return session.scalar(select(BusinessProfile.opening_balance))


def _sum_amounts(session: Session, on_or_before: date | None = None) -> Decimal:
    statement = select(func.sum(Transaction.amount))
    if on_or_before is not None:
        statement = statement.where(Transaction.date <= on_or_before)
    total = session.scalar(statement) or Decimal("0.00")
    return _money(total)


def balance_on(session: Session, when: date) -> Decimal:
    """Cash balance at the end of a given day."""
    return _money(_opening_balance(session) + _sum_amounts(session, on_or_before=when))


def check_hard_targets(session: Session) -> dict:
    """Assert every pinned number. Raises AssertionError if anything is off.

    Returns the numbers so the CLI and the tests can print/compare them.
    """
    cash = balance_on(session, AS_OF_DATE)

    # 1. Cash on the demo date.
    assert cash == TARGET_CASH, f"cash on {AS_OF_DATE} is {cash}, expected {TARGET_CASH}"

    # 2. Closing balance for each completed month.
    month_end = {when: balance_on(session, when) for when in MONTH_END_TARGETS}
    for when, expected in MONTH_END_TARGETS.items():
        assert month_end[when] == expected, f"balance on {when} is {month_end[when]}, expected {expected}"

    # 3. Balance one month before the demo date (feeds the +8.2% KPI).
    month_ago = balance_on(session, date(2026, 10, 19))
    assert abs(month_ago - BALANCE_ON_2026_10_19) <= BALANCE_TOLERANCE, (
        f"balance on 2026-10-19 is {month_ago}, expected {BALANCE_ON_2026_10_19} +/- {BALANCE_TOLERANCE}"
    )

    # 4. The five most recent transactions, exactly as specified.
    latest = session.scalars(
        select(Transaction).order_by(Transaction.date.desc(), Transaction.id.desc()).limit(5)
    ).all()
    latest = list(reversed(latest))
    for row, (txn_id, when, name, category, amount, kind) in zip(latest, LAST_FIVE):
        assert row.id == txn_id, f"expected latest id {txn_id}, got {row.id}"
        assert row.date == when, f"{txn_id} date is {row.date}, expected {when}"
        assert row.name == name, f"{txn_id} name is {row.name!r}, expected {name!r}"
        assert row.category == category, f"{txn_id} category is {row.category}, expected {category}"
        assert _money(row.amount) == amount, f"{txn_id} amount is {row.amount}, expected {amount}"
        assert row.type == kind, f"{txn_id} type is {row.type}, expected {kind}"

    # No transactional history may leak past the demo date.
    newest = session.scalar(select(func.max(Transaction.date)))
    assert newest <= AS_OF_DATE, f"a transaction is dated {newest}, after the as-of date {AS_OF_DATE}"

    # 5. Open (Pending) invoices.
    pending = session.scalars(select(Invoice).where(Invoice.status == "Pending")).all()
    pending_total = _money(sum((_money(inv.amount) for inv in pending), Decimal("0.00")))
    pending_by_id = {inv.id: inv for inv in pending}
    assert set(pending_by_id) == {"INV-198", "INV-204", "INV-211"}, f"pending invoices are {sorted(pending_by_id)}"
    assert pending_by_id["INV-204"].amount == Decimal("52000.00")
    assert pending_by_id["INV-204"].due_date == date(2026, 11, 12)
    assert pending_by_id["INV-198"].amount == Decimal("33000.00")
    assert pending_by_id["INV-198"].due_date == date(2026, 11, 8)
    assert pending_by_id["INV-211"].amount == Decimal("24500.00")
    assert pending_by_id["INV-211"].due_date == date(2026, 11, 28)
    assert pending_total == Decimal("109500.00"), f"pending total is {pending_total}"

    # Overdue is computed, never stored.
    overdue = [inv for inv in pending if inv.due_date < AS_OF_DATE]
    overdue_total = _money(sum((_money(inv.amount) for inv in overdue), Decimal("0.00")))
    assert len(overdue) == 2, f"expected 2 overdue invoices, got {len(overdue)}"
    assert overdue_total == Decimal("85000.00"), f"overdue total is {overdue_total}"
    assert all(inv.status != "Overdue" for inv in pending), "status must never be stored as 'Overdue'"

    # Invoices collected in 1-19 November must total 184,000, each with a
    # matching income transaction linked through invoice_id.
    november_paid = session.scalars(
        select(Invoice).where(
            Invoice.status == "Paid",
            Invoice.paid_date >= date(2026, 11, 1),
            Invoice.paid_date <= AS_OF_DATE,
        )
    ).all()
    collected = _money(sum((_money(inv.amount) for inv in november_paid), Decimal("0.00")))
    assert collected == Decimal("184000.00"), f"November collections total {collected}"
    for inv in november_paid:
        linked = session.scalar(
            select(func.count())
            .select_from(Transaction)
            .where(Transaction.invoice_id == inv.id, Transaction.type == "income")
        )
        assert linked == 1, f"invoice {inv.id} should have exactly one linked income transaction"

    # 6. Commitments due in the next 30 days.
    window_start, window_end = date(2026, 11, 20), date(2026, 12, 19)
    commitments = session.scalars(
        select(Commitment).where(Commitment.due_date >= window_start, Commitment.due_date <= window_end)
    ).all()
    commitment_total = _money(sum((_money(item.amount) for item in commitments), Decimal("0.00")))
    assert commitment_total == Decimal("248500.00"), f"commitments in window total {commitment_total}"
    labelled = {item.label: item for item in commitments}
    expected_items = {
        "Monthly rent": (Decimal("22000.00"), date(2026, 12, 1)),
        "Inventory restock": (Decimal("48000.00"), date(2026, 12, 5)),
        "Payroll": (Decimal("76000.00"), date(2026, 12, 7)),
        "FreshKart payable": (Decimal("41000.00"), date(2026, 11, 28)),
        "Packaging supplies": (Decimal("10000.00"), date(2026, 11, 30)),
        "Loan EMI": (Decimal("18500.00"), date(2026, 12, 5)),
        "Utilities & internet": (Decimal("9000.00"), date(2026, 12, 10)),
        "GST payment": (Decimal("24000.00"), date(2026, 12, 18)),
    }
    for label, (amount, due) in expected_items.items():
        assert label in labelled, f"commitment {label!r} is missing"
        assert _money(labelled[label].amount) == amount, f"{label} amount is {labelled[label].amount}"
        assert labelled[label].due_date == due, f"{label} due date is {labelled[label].due_date}"

    # --- Data hygiene -------------------------------------------------------
    transactions = session.scalars(select(Transaction)).all()
    for row in transactions:
        amount = _money(row.amount)
        assert row.type in {"income", "expense"}, f"{row.id} has type {row.type}"
        assert row.category in CATEGORIES, f"{row.id} has category {row.category}"
        if row.type == "income":
            assert amount > 0, f"{row.id} is income but amount {amount} is not positive"
        else:
            assert amount < 0, f"{row.id} is expense but amount {amount} is not negative"
        assert row.source == "synthetic", f"{row.id} source is {row.source}"

    for inv in session.scalars(select(Invoice)).all():
        assert inv.status in {"Draft", "Pending", "Paid"}, f"{inv.id} has stored status {inv.status}"
        assert inv.source == "synthetic", f"{inv.id} source is {inv.source}"

    assert 150 <= len(transactions) <= 250, f"{len(transactions)} transactions is outside the 150-250 range"

    return {
        "cash_on_as_of": cash,
        "month_end": month_end,
        "month_ago_balance": month_ago,
        "pending_invoices": pending_total,
        "overdue_count": len(overdue),
        "overdue_total": overdue_total,
        "november_collected": collected,
        "commitments_window": commitment_total,
        "transaction_count": len(transactions),
        "latest_ids": [row.id for row in latest],
    }


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------


def seed_database(session: Session, reset: bool = False) -> dict:
    """Seed the database.

    - reset=False and data already present -> does nothing (safe to call on
      every app start).
    - reset=True -> wipes all tables first, then rebuilds identical data.
    """
    if reset:
        _wipe_all(session)
    elif _is_seeded(session):
        return {"seeded": False, "reason": "database already has data"}

    data = build_dataset()
    _persist(session, data)
    session.commit()

    numbers = check_hard_targets(session)

    counts = {
        "business_profiles": session.scalar(select(func.count()).select_from(BusinessProfile)),
        "counterparties": session.scalar(select(func.count()).select_from(Counterparty)),
        "transactions": session.scalar(select(func.count()).select_from(Transaction)),
        "invoices": session.scalar(select(func.count()).select_from(Invoice)),
        "commitments": session.scalar(select(func.count()).select_from(Commitment)),
    }
    return {"seeded": True, "counts": counts, "numbers": numbers}


def seed_if_empty() -> None:
    """Seed on application startup, but only when the database is empty."""
    with SessionLocal() as session:
        if _is_seeded(session):
            return
        seed_database(session)


def dataset_fingerprint(session: Session) -> str:
    """A hash of every seeded row, used to prove reseeding is deterministic."""
    parts: list[str] = []
    for row in session.scalars(select(Transaction).order_by(Transaction.id)).all():
        parts.append(
            f"{row.id}|{row.date}|{row.name}|{row.category}|{row.amount}|{row.type}|"
            f"{row.counterparty_id}|{row.payment_mode}|{row.invoice_id}|{row.source}|{row.created_at}"
        )
    for row in session.scalars(select(Invoice).order_by(Invoice.id)).all():
        parts.append(
            f"{row.id}|{row.client}|{row.issue_date}|{row.due_date}|{row.amount}|{row.status}|"
            f"{row.paid_amount}|{row.paid_date}|{row.created_at}"
        )
    for row in session.scalars(select(Commitment).order_by(Commitment.id)).all():
        parts.append(f"{row.label}|{row.amount}|{row.due_date}|{row.category}")
    for row in session.scalars(select(Counterparty).order_by(Counterparty.id)).all():
        parts.append(f"{row.name}|{row.type}|{row.gstin}|{row.payment_terms_days}")
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()


def format_inr(value: Decimal) -> str:
    """Small display helper for the CLI summary (Western grouping is fine)."""
    return f"Rs {value:,.2f}"


def print_summary(result: dict) -> None:
    """Print the seed result and every pinned number."""
    if not result["seeded"]:
        print(f"Nothing to do - {result['reason']}.")
        print("Use --reset to wipe and rebuild the dataset.")
        return

    counts = result["counts"]
    numbers = result["numbers"]

    print("\nSeeded the synthetic Bloom & Bean dataset (all data is fictional).\n")
    print("Row counts")
    for table, count in counts.items():
        print(f"  {table:<18} {count:>5}")

    print("\nHard targets")
    print(f"  1. Cash on 2026-11-19                 {format_inr(numbers['cash_on_as_of'])}  (target 342,500)")
    print("  2. Month-end balances")
    for when, value in sorted(numbers["month_end"].items()):
        print(f"       {when}                  {format_inr(value)}")
    print(f"  3. Balance on 2026-10-19              {format_inr(numbers['month_ago_balance'])}  (target 316,544 +/- 300)")
    print(f"  4. Latest ids                         {', '.join(numbers['latest_ids'])}")
    print(f"  5. Open invoices                      {format_inr(numbers['pending_invoices'])}  (target 109,500)")
    print(f"     Overdue (computed)                 {numbers['overdue_count']} invoices, {format_inr(numbers['overdue_total'])}")
    print(f"     Collected 1-19 Nov                 {format_inr(numbers['november_collected'])}  (target 184,000)")
    print(f"  6. Commitments 20 Nov - 19 Dec        {format_inr(numbers['commitments_window'])}  (target 248,500)")
    print(f"\nAll hard targets matched. {counts['transactions']} transactions in the demo history.\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed the synthetic Bloom & Bean dataset.")
    parser.add_argument("--reset", action="store_true", help="wipe all tables first, then rebuild")
    args = parser.parse_args()

    init_db()
    with SessionLocal() as session:
        result = seed_database(session, reset=args.reset)

    print_summary(result)
    if result["seeded"]:
        with SessionLocal() as session:
            print(f"Dataset fingerprint: {dataset_fingerprint(session)}")


if __name__ == "__main__":
    main()
