"""
Bonus features: CSV history, charts, goal tracker, PDF report.
"""
import math

import altair as alt
import pandas as pd
from fpdf import FPDF

from src.config import EXPENSE_CATEGORIES, EDUCATIONAL_DISCLAIMER
from src.financial_calculator import (
    calculate_total_expenses, calculate_remaining_income,
    calculate_savings_ratio, calculate_expense_ratio,
)

CSV_COLUMNS = ["Month", "Income", "Savings"] + EXPENSE_CATEGORIES


# ---------- CSV history ----------
def sample_csv() -> str:
    """Template jo user download karke apna data bhar sakta hai."""
    rows = [
        ["2026-08", 5000, 600, 1500, 600, 250, 200, 150, 100, 200, 400, 150],
        ["2026-09", 5000, 700, 1500, 550, 250, 210, 150, 100, 150, 400, 120],
        ["2026-10", 5200, 900, 1500, 520, 240, 190, 150, 120, 120, 350, 100],
    ]
    return pd.DataFrame(rows, columns=CSV_COLUMNS).to_csv(index=False)


def load_history_csv(file):
    """Returns (dataframe, error). Galat file par app crash nahi hoti."""
    try:
        df = pd.read_csv(file)
    except Exception:
        return None, "Could not read the CSV file."
    missing = [c for c in CSV_COLUMNS if c not in df.columns]
    if missing:
        return None, f"Missing columns: {', '.join(missing)}"
    for col in CSV_COLUMNS[1:]:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
    df["Month"] = df["Month"].astype(str)
    return df[CSV_COLUMNS], None


def monthly_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Har mahine ke liye wohi Python calculations."""
    rows = []
    for _, r in df.iterrows():
        expenses = {c: float(r[c]) for c in EXPENSE_CATEGORIES}
        income, savings = float(r["Income"]), float(r["Savings"])
        total = calculate_total_expenses(expenses)
        rows.append({
            "Month": r["Month"],
            "Income": income,
            "Total Expenses": total,
            "Remaining": calculate_remaining_income(income, total),
            "Savings Ratio %": round(calculate_savings_ratio(savings, income), 1),
            "Expense Ratio %": round(calculate_expense_ratio(total, income), 1),
        })
    return pd.DataFrame(rows)


def row_to_inputs(df: pd.DataFrame, month: str):
    r = df[df["Month"] == month].iloc[0]
    expenses = {c: float(r[c]) for c in EXPENSE_CATEGORIES}
    return float(r["Income"]), expenses, float(r["Savings"])


# ---------- Charts ----------
def _expense_df(expenses: dict):
    df = pd.DataFrame({"Category": list(expenses.keys()),
                       "Amount": list(expenses.values())})
    return df[df["Amount"] > 0]


def expense_pie(expenses: dict):
    df = _expense_df(expenses)
    if df.empty:
        return None
    return (alt.Chart(df).mark_arc(innerRadius=70)
            .encode(theta="Amount:Q", color="Category:N",
                    tooltip=["Category", "Amount"])
            .properties(height=340))


def expense_bar(expenses: dict):
    df = _expense_df(expenses)
    if df.empty:
        return None
    return (alt.Chart(df).mark_bar(cornerRadiusTopRight=6, cornerRadiusBottomRight=6)
            .encode(x="Amount:Q", y=alt.Y("Category:N", sort="-x"),
                    color=alt.Color("Category:N", legend=None),
                    tooltip=["Category", "Amount"])
            .properties(height=340))


# ---------- Goal tracker ----------
def goal_progress(target: float, saved_so_far: float, monthly_saving: float):
    if target <= 0:
        return None
    remaining = max(target - saved_so_far, 0)
    months = None
    if remaining == 0:
        months = 0
    elif monthly_saving > 0:
        months = math.ceil(remaining / monthly_saving)
    return {
        "percent": min(saved_so_far / target * 100, 100),
        "remaining": remaining,
        "months_needed": months,
    }


# ---------- PDF report ----------
def _safe(text) -> str:
    """Built-in PDF font sirf latin-1 samajhta hai."""
    text = (str(text).replace("\u2013", "-").replace("\u2014", "-")
            .replace("\u2022", "-").replace("\u2019", "'")
            .replace("**", "").replace("#", ""))
    return text.encode("latin-1", "replace").decode("latin-1")


def _write(pdf, text, size=11, bold=False, gap=1):
    pdf.set_font("Helvetica", "B" if bold else "", size)
    pdf.multi_cell(0, 6, _safe(text), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(gap)


def _bullets(pdf, title, items):
    if not items:
        return
    _write(pdf, title, 13, True)
    for item in items:
        _write(pdf, f"- {item}", 11, False, 0)
    pdf.ln(3)


def build_pdf_report(calc: dict, analysis: dict, narrative=None) -> bytes:
    cur = calc.get("currency", "")
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    _write(pdf, "FinWise AI - Monthly Financial Report", 18, True, 3)
    _write(pdf, EDUCATIONAL_DISCLAIMER, 9, False, 4)

    _write(pdf, "1. Overview (calculated by Python)", 13, True)
    for line in [
        f"Monthly income: {cur} {calc['monthly_income']:,.0f}",
        f"Total expenses: {cur} {calc['total_expenses']:,.0f}",
        f"Remaining balance: {cur} {calc['remaining_income']:,.0f}",
        f"Current savings: {cur} {calc['savings']:,.0f}",
        f"Savings ratio: {calc['savings_ratio']}%",
        f"Expense ratio: {calc['expense_ratio']}%",
        f"Preliminary score: {calc['preliminary_score']}/100 ({calc['score_band']})",
        f"Financial goal: {calc['financial_goal']}",
    ]:
        _write(pdf, line, 11, False, 0)
    pdf.ln(4)

    if analysis:
        _write(pdf, "2. AI Insights (educational only)", 13, True)
        _write(pdf, f"AI health score: {analysis['financial_health_score']}/100", 11, False, 0)
        _write(pdf, f"Risk level: {analysis['risk_level']}", 11, False, 0)
        _write(pdf, f"Summary: {analysis['financial_summary']}", 11, False, 4)

        if analysis["spending_analysis"]:
            _write(pdf, "Spending analysis", 13, True)
            for item in analysis["spending_analysis"]:
                _write(pdf, item["category"], 11, True, 0)
                _write(pdf, f"Observation: {item['observation']}", 11, False, 0)
                _write(pdf, f"Recommendation: {item['recommendation']}", 11, False, 2)
            pdf.ln(2)

        _bullets(pdf, "Top priorities", analysis["top_priorities"])
        _bullets(pdf, "Budget recommendations", analysis["budget_recommendations"])
        _bullets(pdf, "Savings strategy", analysis["savings_strategy"])
        _bullets(pdf, "Next month action plan", analysis["next_month_action_plan"])

    if narrative:
        _write(pdf, "Written recommendation", 13, True)
        _write(pdf, narrative, 11, False, 4)

    _write(pdf, "Reminder: " + EDUCATIONAL_DISCLAIMER, 9, False, 0)
    return bytes(pdf.output())