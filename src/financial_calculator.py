"""
Deterministic financial calculations (NO AI here).
Same inputs always give the same outputs.
"""

DEBT_KEY = "Loan/Debt"


def _clamp(value, low, high):
    return max(low, min(high, value))


def calculate_total_expenses(expenses: dict) -> float:
    return sum(expenses.values())


def calculate_remaining_income(monthly_income: float, total_expenses: float) -> float:
    return monthly_income - total_expenses


def calculate_savings_ratio(savings: float, monthly_income: float) -> float:
    if monthly_income <= 0:          # divide-by-zero guard
        return 0.0
    return (savings / monthly_income) * 100


def calculate_expense_ratio(total_expenses: float, monthly_income: float) -> float:
    if monthly_income <= 0:          # divide-by-zero guard
        return 0.0
    return (total_expenses / monthly_income) * 100


def calculate_preliminary_score(monthly_income, total_expenses,
                                remaining_income, savings, debt) -> int:
    """
    Weighted 0-100 heuristic:
      savings ratio   -> 30 marks (20% or more = full marks)
      leftover income -> 25 marks (20% or more = full marks)
      expense ratio   -> 25 marks (50% or less = full, 100%+ = zero)
      debt burden     -> 20 marks (10% or less = full, 40%+ = zero)
    """
    if monthly_income <= 0:
        return 0

    savings_pct = (savings / monthly_income) * 100
    leftover_pct = (remaining_income / monthly_income) * 100
    expense_pct = (total_expenses / monthly_income) * 100
    debt_pct = (debt / monthly_income) * 100

    savings_pts = _clamp(savings_pct / 20, 0, 1) * 30
    leftover_pts = _clamp(leftover_pct / 20, 0, 1) * 25
    expense_pts = _clamp((100 - expense_pct) / 50, 0, 1) * 25
    debt_pts = _clamp((40 - debt_pct) / 30, 0, 1) * 20

    return round(savings_pts + leftover_pts + expense_pts + debt_pts)


def get_score_band(score: float) -> str:
    """Score bands from the assignment (educational only)."""
    if score >= 80:
        return "Strong"
    if score >= 60:
        return "Generally healthy"
    if score >= 40:
        return "Needs improvement"
    return "High attention"


def format_expense_breakdown(expenses: dict) -> str:
    """Turn the expense dict into text for the prompt."""
    return "\n".join(f"- {name}: {amount}" for name, amount in expenses.items())


def calculate_all(monthly_income: float, expenses: dict, savings: float) -> dict:
    """Run every calculation and return one dictionary."""
    total = calculate_total_expenses(expenses)
    remaining = calculate_remaining_income(monthly_income, total)
    score = calculate_preliminary_score(
        monthly_income, total, remaining, savings, expenses.get(DEBT_KEY, 0)
    )
    return {
        "monthly_income": monthly_income,
        "total_expenses": total,
        "remaining_income": remaining,
        "savings": savings,
        "savings_ratio": round(calculate_savings_ratio(savings, monthly_income), 2),
        "expense_ratio": round(calculate_expense_ratio(total, monthly_income), 2),
        "preliminary_score": score,
        "score_band": get_score_band(score),
        "expense_breakdown": format_expense_breakdown(expenses),
    }