"""
Helpers: safe JSON parsing + money formatting.
"""
import json

VALID_RISK_LEVELS = ("LOW", "MEDIUM", "HIGH")


def format_money(amount: float, currency: str) -> str:
    return f"{currency} {amount:,.0f}"


def _extract_json_text(raw_text: str) -> str:
    """Code fences ya extra text ho to sirf { ... } wala hissa nikalo."""
    text = (raw_text or "").strip()
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        return text[start:end + 1]
    return text


def _as_list(value) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v) for v in value]
    return [str(value)]


def _clean_analysis(data: dict) -> dict:
    """Missing ya galat fields ko safe values se bhar do."""
    try:
        score = int(float(data.get("financial_health_score", 0)))
    except (TypeError, ValueError):
        score = 0
    score = max(0, min(100, score))

    risk = str(data.get("risk_level", "")).strip().upper()
    if risk not in VALID_RISK_LEVELS:
        risk = "UNKNOWN"

    spending = []
    for item in data.get("spending_analysis") or []:
        if isinstance(item, dict):
            spending.append({
                "category": str(item.get("category", "")),
                "observation": str(item.get("observation", "")),
                "recommendation": str(item.get("recommendation", "")),
            })

    return {
        "financial_summary": str(data.get("financial_summary", "")),
        "financial_health_score": score,
        "spending_analysis": spending,
        "risk_level": risk,
        "top_priorities": _as_list(data.get("top_priorities")),
        "budget_recommendations": _as_list(data.get("budget_recommendations")),
        "savings_strategy": _as_list(data.get("savings_strategy")),
        "next_month_action_plan": _as_list(data.get("next_month_action_plan")),
    }


def safe_parse_json(raw_text: str):
    """
    Returns (data, error_message).
    Agar JSON theek ho to error None hota hai, warna data None.
    App crash nahi hoti.
    """
    text = _extract_json_text(raw_text)
    if not text:
        return None, "The AI returned an empty response. Please try again."
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None, "The AI returned invalid JSON. Please try again."
    if not isinstance(data, dict):
        return None, "The AI response was not in the expected format. Please try again."
    return _clean_analysis(data), None