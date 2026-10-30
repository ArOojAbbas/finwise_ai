"""
FinWise AI - Streamlit UI.
Run with:  streamlit run app.py
"""
import html
from datetime import datetime

import streamlit as st

from src.config import (
    EXPENSE_CATEGORIES, FINANCIAL_GOALS, CURRENCIES, EDUCATIONAL_DISCLAIMER,
    DEFAULT_MODEL, DEFAULT_TEMPERATURE, CACHE_OPTIONS, MODEL_OPTIONS,
)
from src.financial_calculator import calculate_all, get_score_band
from src.chains import (
    build_llm, build_analysis_chain, run_analysis,
    stream_recommendations, raw_message_demo,
)
from src.cache_manager import set_cache
from src.utils import safe_parse_json, format_money
from src.auth import require_login, show_user_box
from src.bonus import (
    sample_csv, load_history_csv, monthly_summary, row_to_inputs,
    expense_pie, expense_bar, goal_progress, build_pdf_report,
)

st.set_page_config(page_title="FinWise AI", page_icon="💰", layout="wide")

# ---------- Styling (works in light and dark mode) ----------
st.markdown("""
<style>
footer {visibility: hidden;}
.block-container {padding-top: 2rem;}

.hero {background: linear-gradient(135deg, #0f766e, #2563eb);
       padding: 2rem 2.2rem; border-radius: 20px; margin-bottom: 1rem;
       box-shadow: 0 8px 24px rgba(37,99,235,.25);}
.hero h1 {margin: 0; font-size: 2.4rem; font-weight: 800; color: white;}
.hero p {margin: .4rem 0 0; color: rgba(255,255,255,.93); font-size: 1.1rem;}
.pill {display: inline-block; background: rgba(255,255,255,.2); color: white;
       padding: .25rem .8rem; border-radius: 999px; font-size: .8rem;
       margin: .8rem .4rem 0 0;}

.section-title {font-size: 1.35rem; font-weight: 700; margin: 1.6rem 0 .7rem;
       padding-left: .75rem; border-left: 5px solid #2563eb;}

div[data-testid="stMetric"] {background: rgba(127,127,127,.07);
       border: 1px solid rgba(127,127,127,.22); border-left: 4px solid #2563eb;
       padding: .9rem 1rem; border-radius: 14px;
       box-shadow: 0 2px 8px rgba(0,0,0,.05);}

.stTabs [data-baseweb="tab-list"] {gap: .4rem;}
.stTabs [data-baseweb="tab"] {font-size: 1rem; font-weight: 600;
       border-radius: 10px 10px 0 0; padding: .5rem 1rem;}

div[data-testid="stFormSubmitButton"] button, .stDownloadButton button {
       background: linear-gradient(135deg, #0f766e, #2563eb); color: white;
       border: none; border-radius: 12px; padding: .7rem 1.6rem; font-weight: 700;}
div[data-testid="stFormSubmitButton"] button:hover, .stDownloadButton button:hover {
       filter: brightness(1.1); color: white;}

.ring-wrap {position: relative; width: 140px; height: 140px; margin: 0 auto;}
.ring {position: absolute; inset: 0; border-radius: 50%;
       background: conic-gradient(var(--c) calc(var(--p) * 1%), rgba(127,127,127,.22) 0);
       -webkit-mask: radial-gradient(farthest-side, transparent calc(100% - 14px), #000 calc(100% - 13px));
       mask: radial-gradient(farthest-side, transparent calc(100% - 14px), #000 calc(100% - 13px));}
.ring-text {position: absolute; inset: 0; display: flex; flex-direction: column;
       align-items: center; justify-content: center; font-weight: 800;
       font-size: 2rem; line-height: 1;}
.ring-text small {font-size: .7rem; font-weight: 500; opacity: .7; margin-top: .2rem;}
.ring-cap {text-align: center; font-weight: 600; margin-top: .6rem;}

.card {background: rgba(127,127,127,.07); border: 1px solid rgba(127,127,127,.2);
       border-radius: 14px; padding: .8rem 1rem; margin-bottom: .6rem;
       display: flex; gap: .8rem; align-items: flex-start;}
.num {min-width: 32px; height: 32px; border-radius: 50%; color: white;
      background: linear-gradient(135deg, #0f766e, #2563eb); font-weight: 700;
      display: flex; align-items: center; justify-content: center;}
</style>
""", unsafe_allow_html=True)

# ---------- Login gate: app opens only after valid login + OpenAI key ----------
require_login()


# ---------- Helpers ----------
def esc(text) -> str:
    return html.escape(str(text))


def score_color(score: float) -> str:
    if score >= 80:
        return "#16a34a"
    if score >= 60:
        return "#65a30d"
    if score >= 40:
        return "#f59e0b"
    return "#dc2626"


def ring(score: int, caption: str):
    st.markdown(
        f'<div class="ring-wrap"><div class="ring" style="--p:{score};--c:{score_color(score)}"></div>'
        f'<div class="ring-text">{score}<small>out of 100</small></div></div>'
        f'<div class="ring-cap">{esc(caption)}</div>',
        unsafe_allow_html=True,
    )


def num_cards(items, prefix=""):
    for n, text in enumerate(items, 1):
        st.markdown(
            f'<div class="card"><div class="num">{n}</div>'
            f'<div>{prefix}{esc(text)}</div></div>',
            unsafe_allow_html=True,
        )


def section(title: str):
    st.markdown(f'<div class="section-title">{title}</div>', unsafe_allow_html=True)


def disclaimer_box():
    st.warning(f"⚠️ {EDUCATIONAL_DISCLAIMER}")


def friendly_error(e: Exception) -> str:
    msg = str(e)
    if "401" in msg or "api key" in msg.lower() or "OPENAI_API_KEY" in msg:
        return "OpenAI API key problem. Please log out and log in again with a valid key."
    return f"Something went wrong: {msg}"


def reset_session():
    """Form/results saaf karo, lekin user ko logout mat karo."""
    keep = {k: st.session_state[k] for k in ("user", "openai_key") if k in st.session_state}
    st.session_state.clear()
    st.session_state.update(keep)


def build_calc(income, expenses, savings, goal, currency) -> dict:
    calc = calculate_all(income, expenses, savings)   # Python maths only
    calc.update({"financial_goal": goal, "currency": currency, "expenses": expenses})
    return calc


def start_new_analysis(calc: dict):
    st.session_state.calc = calc
    st.session_state.analysis = None
    st.session_state.narrative = None
    st.session_state.error = None


def use_history_month():
    """CSV ke ek mahine ko analysis ke liye use karo (button callback)."""
    df = st.session_state.get("hist_df")
    if df is None:
        return
    income, expenses, savings = row_to_inputs(df, st.session_state.hist_month)
    start_new_analysis(build_calc(
        income, expenses, savings,
        st.session_state.hist_goal, st.session_state.hist_currency,
    ))


# ---------- Session state ----------
for key in ("calc", "analysis", "narrative", "error", "hist_df"):
    st.session_state.setdefault(key, None)
st.session_state.setdefault("history", [])

# ---------- Sidebar ----------
with st.sidebar:
    st.markdown("## 💰 FinWise AI")
    st.caption("AI-Powered Personal Financial Analysis & Smart Budget Assistant")
    show_user_box()
    st.divider()

    with st.expander("ℹ️ Project info", expanded=True):
        st.write(
            "A LangChain + Streamlit FinTech prototype. Python calculates your "
            "ratios; an LLM turns them into educational budgeting insights."
        )
    st.warning(EDUCATIONAL_DISCLAIMER)

    st.subheader("⚙️ Model settings")
    model = st.selectbox("OpenAI model", MODEL_OPTIONS,
                         index=MODEL_OPTIONS.index(DEFAULT_MODEL))
    temperature = st.slider("Temperature (creativity)", 0.0, 1.0,
                            DEFAULT_TEMPERATURE, 0.1)

    st.subheader("🗄️ Cache")
    cache_choice = st.selectbox(
        "Cache type", CACHE_OPTIONS,
        help="InMemoryCache = RAM (cleared on restart). "
             "SQLiteCache = saved in a .db file (survives restart).",
    )
    if st.session_state.get("active_cache") != cache_choice:
        st.session_state.cache_msg = set_cache(cache_choice)
        st.session_state.active_cache = cache_choice
    st.caption(st.session_state.cache_msg)

    st.divider()
    st.button("🔄 Reset session", on_click=reset_session)

# ---------- Hero ----------
st.markdown("""
<div class="hero">
  <h1>💰 FinWise AI</h1>
  <p>See where your money goes and get a simple, educational plan to improve your budget.</p>
  <span class="pill">LangChain</span><span class="pill">OpenAI</span>
  <span class="pill">Streamlit</span><span class="pill">Educational use only</span>
</div>
""", unsafe_allow_html=True)
disclaimer_box()

tab_main, tab_charts, tab_goal, tab_hist, tab_log = st.tabs([
    "📝 Analyse", "📊 Charts", "🎯 Goal Tracker",
    "📂 Monthly History (CSV)", "🕘 Session History",
])

# =====================================================================
# TAB 1: Form + overview + AI dashboard
# =====================================================================
with tab_main:
    with st.expander("📖 How to use this app"):
        st.write(
            "1. Enter your income, savings, goal and currency.\n"
            "2. Fill your monthly expenses.\n"
            "3. Click **Analyse My Finances** and read your dashboard."
        )

    with st.form("finance_form"):
        tab_income, tab_expenses = st.tabs(["💵 Income & Goal", "🧾 Monthly Expenses"])
        with tab_income:
            c1, c2 = st.columns(2)
            with c1:
                monthly_income = st.number_input("Monthly income", min_value=0.0,
                                                 value=5000.0, step=100.0)
                savings = st.number_input("Current monthly savings", min_value=0.0,
                                          value=0.0, step=50.0)
            with c2:
                currency = st.selectbox("Currency", CURRENCIES)
                goal = st.selectbox("Financial goal", FINANCIAL_GOALS)
        with tab_expenses:
            expenses = {}
            cols = st.columns(3)
            for i, category in enumerate(EXPENSE_CATEGORIES):
                with cols[i % 3]:
                    expenses[category] = st.number_input(
                        category, min_value=0.0, value=0.0, step=50.0,
                        key=f"exp_{category}",
                    )
        submitted = st.form_submit_button("🚀 Analyse My Finances")

    if submitted:
        start_new_analysis(build_calc(monthly_income, expenses, savings, goal, currency))

    calc = st.session_state.calc

    if not calc:
        st.info("👆 Fill the form above and click **Analyse My Finances** to begin.")
    else:
        cur = calc["currency"]

        # ----- Overview -----
        section("📊 Financial Overview")
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Monthly Income", format_money(calc["monthly_income"], cur))
        m2.metric("Total Expenses", format_money(calc["total_expenses"], cur))
        m3.metric("Remaining Balance", format_money(calc["remaining_income"], cur),
                  delta="Surplus" if calc["remaining_income"] >= 0 else "-Deficit")
        m4.metric("Current Savings", format_money(calc["savings"], cur))

        # ----- Python calculations -----
        section("🧮 Python Calculations (no AI)")
        p1, p2 = st.columns([1, 2])
        with p1:
            ring(calc["preliminary_score"], f"Rule-based score · {calc['score_band']}")
        with p2:
            q1, q2 = st.columns(2)
            q1.metric("Savings Ratio", f"{calc['savings_ratio']}%")
            q2.metric("Expense Ratio", f"{calc['expense_ratio']}%")
            st.progress(min(max(calc["preliminary_score"], 0), 100) / 100,
                        text=f"Preliminary score: {calc['preliminary_score']}/100")
            st.caption("Fixed Python formulas: the same inputs always give the same results.")

        # ----- AI analysis -----
        section("🤖 AI Analysis (LLM insights)")
        if calc["monthly_income"] <= 0:
            st.warning("Please enter a monthly income greater than 0 to get AI insights.")
        else:
            if st.session_state.analysis is None and st.session_state.error is None:
                with st.spinner("Analysing your finances with AI..."):
                    try:
                        llm = build_llm(model, temperature, st.session_state.openai_key)
                        raw = run_analysis(build_analysis_chain(llm), calc)
                        data, problem = safe_parse_json(raw)
                        if data is None:
                            st.session_state.error = problem
                        else:
                            st.session_state.analysis = data
                            st.session_state.history.append({
                                "Time": datetime.now().strftime("%Y-%m-%d %H:%M"),
                                "Currency": cur,
                                "Income": calc["monthly_income"],
                                "Expenses": calc["total_expenses"],
                                "Remaining": calc["remaining_income"],
                                "Python score": calc["preliminary_score"],
                                "AI score": data["financial_health_score"],
                                "Risk": data["risk_level"],
                                "Goal": calc["financial_goal"],
                                "Summary": data["financial_summary"],
                            })
                    except Exception as e:
                        st.session_state.error = friendly_error(e)

            if st.session_state.error:
                st.error(st.session_state.error)
                st.info("Click **Analyse My Finances** again to retry.")
            elif st.session_state.analysis:
                a = st.session_state.analysis
                ai_score = a["financial_health_score"]

                r1, r2, r3 = st.columns([1, 1, 2])
                with r1:
                    ring(ai_score, f"AI health score · {get_score_band(ai_score)}")
                with r2:
                    st.metric("AI Score", f"{ai_score}/100")
                    st.metric("Python Score", f"{calc['preliminary_score']}/100")
                with r3:
                    risk = a["risk_level"]
                    if risk == "LOW":
                        st.success("🟢 Risk level: LOW")
                    elif risk == "MEDIUM":
                        st.warning("🟡 Risk level: MEDIUM")
                    elif risk == "HIGH":
                        st.error("🔴 Risk level: HIGH")
                    else:
                        st.info("Risk level: not available")
                    st.info(f"**Summary:** {a['financial_summary']}")
                st.progress(ai_score / 100,
                            text=f"AI health score: {ai_score}/100 · {get_score_band(ai_score)}")

                t1, t2, t3, t4 = st.tabs([
                    "🔍 Spending Analysis", "🎯 Top Priorities",
                    "💡 Budget & Savings", "📅 Next Month Plan",
                ])
                with t1:
                    if not a["spending_analysis"]:
                        st.info("No spending analysis returned.")
                    for i, item in enumerate(a["spending_analysis"]):
                        with st.expander(f"📌 {item['category']}", expanded=(i == 0)):
                            st.write(f"**Observation:** {item['observation']}")
                            st.success(f"**Recommendation:** {item['recommendation']}")
                    st.caption(f"⚠️ {EDUCATIONAL_DISCLAIMER}")
                with t2:
                    num_cards(a["top_priorities"])
                    st.caption(f"⚠️ {EDUCATIONAL_DISCLAIMER}")
                with t3:
                    b1, b2 = st.columns(2)
                    with b1:
                        st.markdown("#### 🧾 Budget recommendations")
                        for item in a["budget_recommendations"]:
                            st.markdown(f"- {item}")
                    with b2:
                        st.markdown("#### 🏦 Savings strategy")
                        for item in a["savings_strategy"]:
                            st.markdown(f"- {item}")
                    st.caption(f"⚠️ {EDUCATIONAL_DISCLAIMER}")
                with t4:
                    num_cards(a["next_month_action_plan"], prefix="<b>Step:</b> ")
                    st.caption(f"⚠️ {EDUCATIONAL_DISCLAIMER}")

                # ----- Streaming recommendation -----
                section("✍️ Written Recommendation")
                if st.session_state.narrative is None:
                    try:
                        llm = build_llm(model, temperature, st.session_state.openai_key)
                        st.session_state.narrative = st.write_stream(
                            stream_recommendations(llm, calc))
                    except Exception as e:
                        st.session_state.narrative = f"⚠️ {friendly_error(e)}"
                        st.error(friendly_error(e))
                else:
                    st.markdown(st.session_state.narrative)
                st.caption(f"⚠️ {EDUCATIONAL_DISCLAIMER}")

                # ----- PDF report (bonus) -----
                try:
                    pdf_bytes = build_pdf_report(calc, a, st.session_state.narrative)
                    st.download_button("📄 Download PDF Report", pdf_bytes,
                                       file_name="finwise_report.pdf",
                                       mime="application/pdf")
                except Exception as e:
                    st.warning(f"Could not build the PDF report: {e}")

        # ----- Message demo -----
        with st.expander("🧪 Under the hood: System / Human / AI messages demo"):
            st.write("Shows how SystemMessage, HumanMessage and AIMessage form a conversation.")
            if st.button("Run message demo"):
                try:
                    st.info(raw_message_demo(
                        build_llm(model, temperature, st.session_state.openai_key), calc))
                except Exception as e:
                    st.error(friendly_error(e))

# =====================================================================
# TAB 2: Charts (bonus)
# =====================================================================
with tab_charts:
    calc = st.session_state.calc
    section("📊 Expense Visualization")
    if not calc:
        st.info("Run an analysis first to see your charts.")
    else:
        pie, bar = expense_pie(calc["expenses"]), expense_bar(calc["expenses"])
        if pie is None:
            st.info("All expenses are 0, so there is nothing to chart.")
        else:
            ch1, ch2 = st.columns(2)
            with ch1:
                st.markdown("**Share of each category**")
                st.altair_chart(pie)
            with ch2:
                st.markdown("**Biggest categories**")
                st.altair_chart(bar)
    st.caption(f"⚠️ {EDUCATIONAL_DISCLAIMER}")

# =====================================================================
# TAB 3: Goal tracker (bonus)
# =====================================================================
with tab_goal:
    calc = st.session_state.calc
    section("🎯 Financial Goal Tracker")
    st.write("Track how close you are to a savings target.")
    g_cur = calc["currency"] if calc else CURRENCIES[0]
    g1, g2, g3 = st.columns(3)
    target = g1.number_input(f"Target amount ({g_cur})", min_value=0.0, value=0.0, step=500.0)
    saved = g2.number_input(f"Saved so far ({g_cur})", min_value=0.0, value=0.0, step=100.0)
    monthly = g3.number_input(f"Monthly contribution ({g_cur})", min_value=0.0,
                              value=float(calc["savings"]) if calc else 0.0, step=50.0)
    result = goal_progress(target, saved, monthly)
    if result is None:
        st.info("Enter a target amount greater than 0.")
    else:
        st.progress(result["percent"] / 100, text=f"{result['percent']:.0f}% of your goal")
        k1, k2 = st.columns(2)
        k1.metric("Still to save", format_money(result["remaining"], g_cur))
        if result["months_needed"] is None:
            k2.metric("Estimated months", "n/a")
            st.warning("Add a monthly contribution to estimate the time needed.")
        else:
            k2.metric("Estimated months", result["months_needed"])
            st.caption("A simple estimate only. Real results can change.")
    st.caption(f"⚠️ {EDUCATIONAL_DISCLAIMER}")

# =====================================================================
# TAB 4: CSV history + month-to-month comparison (bonus)
# =====================================================================
with tab_hist:
    section("📂 Expense History (CSV)")
    st.write("Upload several months of data to compare them. Use the template for the right columns.")
    st.download_button("⬇️ Download CSV template", sample_csv(),
                       file_name="finwise_template.csv", mime="text/csv")
    uploaded = st.file_uploader("Upload your expense history", type="csv")

    if uploaded is None:
        st.session_state.hist_df = None
        st.info("Upload a CSV file to see your month-to-month comparison.")
    else:
        df, err = load_history_csv(uploaded)
        if err:
            st.session_state.hist_df = None
            st.error(err)
        else:
            st.session_state.hist_df = df
            summary = monthly_summary(df)
            st.dataframe(summary)

            section("📈 Month-to-Month Comparison")
            if len(summary) >= 2:
                last, prev = summary.iloc[-1], summary.iloc[-2]
                st.caption(f"Comparing {last['Month']} with {prev['Month']}")
                d1, d2, d3 = st.columns(3)
                d1.metric("Total Expenses", f"{last['Total Expenses']:,.0f}",
                          delta=f"{last['Total Expenses'] - prev['Total Expenses']:,.0f}",
                          delta_color="inverse")
                d2.metric("Remaining", f"{last['Remaining']:,.0f}",
                          delta=f"{last['Remaining'] - prev['Remaining']:,.0f}")
                d3.metric("Savings Ratio", f"{last['Savings Ratio %']}%",
                          delta=f"{round(last['Savings Ratio %'] - prev['Savings Ratio %'], 1)}%")
            else:
                st.info("Add at least 2 months to compare them.")
            st.line_chart(summary.set_index("Month")[["Income", "Total Expenses"]])
            st.bar_chart(summary.set_index("Month")[["Savings Ratio %"]])

            section("🤖 Analyse one month with AI")
            h1, h2, h3 = st.columns(3)
            h1.selectbox("Month", df["Month"].tolist(), key="hist_month")
            h2.selectbox("Currency", CURRENCIES, key="hist_currency")
            h3.selectbox("Financial goal", FINANCIAL_GOALS, key="hist_goal")
            st.button("Use this month for analysis", on_click=use_history_month)
            st.caption("After clicking, open the **📝 Analyse** tab to see the results.")
    st.caption(f"⚠️ {EDUCATIONAL_DISCLAIMER}")

# =====================================================================
# TAB 5: Session history (bonus)
# =====================================================================
with tab_log:
    section("🕘 Analyses in this session")
    if not st.session_state.history:
        st.info("Your past analyses in this session will appear here.")
    else:
        st.dataframe([{k: v for k, v in h.items() if k != "Summary"}
                      for h in st.session_state.history])
        for h in reversed(st.session_state.history):
            with st.expander(f"{h['Time']} · AI score {h['AI score']} · Risk {h['Risk']}"):
                st.write(h["Summary"])
    st.caption(f"⚠️ {EDUCATIONAL_DISCLAIMER}")