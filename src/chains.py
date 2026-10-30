"""
LangChain parts: ChatOpenAI, LLMChain, raw messages demo, streaming.
"""
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

try:
    from langchain.chains import LLMChain
except ImportError:                      # newer LangChain versions
    from langchain_classic.chains import LLMChain

from src.config import OPENAI_API_KEY, DEFAULT_MODEL, DEFAULT_TEMPERATURE
from src.prompts import (
    SYSTEM_PROMPT,
    HUMAN_TEMPLATE,
    FINANCIAL_PROMPT_TEMPLATE,
    ANALYSIS_CHAT_TEMPLATE,
    NARRATIVE_CHAT_TEMPLATE,
)

# Prompt ke 8 variables (PDF section 11)
PROMPT_VARIABLES = [
    "monthly_income", "total_expenses", "remaining_income", "savings",
    "savings_ratio", "expense_ratio", "financial_goal", "expense_breakdown",
]


def select_prompt_inputs(data: dict) -> dict:
    """Sirf wo values lo jo prompt ko chahiye."""
    return {key: data[key] for key in PROMPT_VARIABLES}


# ---------- ChatOpenAI ----------
def build_llm(model: str = DEFAULT_MODEL, temperature: float = DEFAULT_TEMPERATURE,
              api_key: str = None):
    """User ki login wali key use hoti hai; na ho to .env wali key."""
    key = api_key or OPENAI_API_KEY
    if not key:
        raise ValueError("OPENAI_API_KEY not found. Please log in with a valid key.")
    return ChatOpenAI(model=model, temperature=temperature, api_key=key)


# ---------- LLMChain ----------
def build_analysis_chain(llm, use_chat_prompt: bool = True):
    """Reusable chain: prompt + LLM. Output JSON text deta hai."""
    prompt = ANALYSIS_CHAT_TEMPLATE if use_chat_prompt else FINANCIAL_PROMPT_TEMPLATE
    return LLMChain(llm=llm, prompt=prompt)


def run_analysis(chain, inputs: dict) -> str:
    """Chain chalao aur LLM ka raw text wapas karo."""
    result = chain.invoke(select_prompt_inputs(inputs))
    return result["text"]


# ---------- Raw System / Human / AI message demo ----------
def raw_message_demo(llm, inputs: dict) -> str:
    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=HUMAN_TEMPLATE.format(**select_prompt_inputs(inputs))),
        AIMessage(content="Understood. I will analyse your numbers for educational purposes only."),
        HumanMessage(content="Now give me a one-sentence summary."),
    ]
    return llm.invoke(messages).content


# ---------- Streaming (PDF section 13) ----------
def stream_recommendations(llm, inputs: dict):
    messages = NARRATIVE_CHAT_TEMPLATE.format_messages(**select_prompt_inputs(inputs))
    for chunk in llm.stream(messages):
        if chunk.content:
            yield chunk.content