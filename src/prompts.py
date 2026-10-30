"""
Prompts: system prompt, JSON schema, PromptTemplate, ChatPromptTemplate.
"""
from langchain_core.prompts import PromptTemplate, ChatPromptTemplate

# ---------- JSON schema (PDF section 12) ----------
JSON_SCHEMA = """{
  "financial_summary": "",
  "financial_health_score": 0,
  "spending_analysis": [
    { "category": "", "observation": "", "recommendation": "" }
  ],
  "risk_level": "",
  "top_priorities": [],
  "budget_recommendations": [],
  "savings_strategy": [],
  "next_month_action_plan": []
}"""

# ---------- System prompt: role + safety ----------
SYSTEM_PROMPT = """You are FinWise AI, an educational personal-finance assistant.

SAFETY RULES:
- This is for educational and informational purposes only.
- Do NOT give guaranteed investment advice.
- Do NOT promise or guarantee any financial outcome.
- Do NOT suggest executing transactions or connecting to bank accounts.
- Always remind the user to consult a qualified financial professional.

SCORE BANDS: 80-100 strong, 60-79 generally healthy, 40-59 needs improvement, below 40 high attention.
risk_level must be exactly one of: LOW, MEDIUM, HIGH."""

JSON_INSTRUCTIONS = """Return ONLY valid JSON in exactly this schema.
No extra text, no markdown, no code fences.

{json_schema}"""

# ---------- Human message: dynamic data ----------
HUMAN_TEMPLATE = """Analyse this monthly financial situation.

Monthly income: {monthly_income}
Total expenses: {total_expenses}
Remaining income: {remaining_income}
Current monthly savings: {savings}
Savings ratio: {savings_ratio}%
Expense ratio: {expense_ratio}%
Financial goal: {financial_goal}

Expense breakdown:
{expense_breakdown}"""

# ---------- 1) PromptTemplate (single string) ----------
FINANCIAL_PROMPT_TEMPLATE = PromptTemplate.from_template(
    SYSTEM_PROMPT + "\n\n" + JSON_INSTRUCTIONS + "\n\n" + HUMAN_TEMPLATE
).partial(json_schema=JSON_SCHEMA)

# ---------- 2) ChatPromptTemplate for JSON analysis ----------
ANALYSIS_CHAT_TEMPLATE = ChatPromptTemplate.from_messages([
    ("system", SYSTEM_PROMPT + "\n\n" + JSON_INSTRUCTIONS),
    ("human", HUMAN_TEMPLATE),
]).partial(json_schema=JSON_SCHEMA)

# ---------- 3) ChatPromptTemplate for streaming text ----------
NARRATIVE_SYSTEM = SYSTEM_PROMPT + """

Now write a short, friendly, plain-text recommendation for the user
(NOT JSON). Use simple language and end with a reminder that this is
educational only."""

NARRATIVE_CHAT_TEMPLATE = ChatPromptTemplate.from_messages([
    ("system", NARRATIVE_SYSTEM),
    ("human", HUMAN_TEMPLATE),
])