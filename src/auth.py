import hashlib
import html
import os
import re
import secrets
import smtplib
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime
from email.message import EmailMessage

import openai
import streamlit as st

from src import config  # also loads the .env file

AUTH_DB_PATH = "users.db"
RESET_MINUTES = 10
MAX_RESET_ATTEMPTS = 5
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


# =====================================================================
# PART 1: Database and security
# =====================================================================
@contextmanager
def _db():
    conn = sqlite3.connect(AUTH_DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with _db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                email TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                salt TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL,
                reset_hash TEXT,
                reset_expires REAL,
                reset_attempts INTEGER DEFAULT 0
            )
        """)


def normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def validate_email(email: str) -> bool:
    return bool(EMAIL_PATTERN.match(email or ""))


def validate_password(password: str):
    """Returns an error message, or None if the password is fine."""
    if len(password or "") < 8:
        return "Password must be at least 8 characters long."
    if not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
        return "Password must contain both letters and numbers."
    return None


def _hash(value: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256", value.encode(), bytes.fromhex(salt), 200_000
    ).hex()


def get_user(email: str):
    with _db() as conn:
        return conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()


def create_user(name: str, email: str, password: str) -> str:
    """Returns 'ok' or 'exists'."""
    salt = secrets.token_hex(16)
    try:
        with _db() as conn:
            conn.execute(
                "INSERT INTO users (email, name, salt, password_hash, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (email, name, salt, _hash(password, salt),
                 datetime.now().isoformat(timespec="seconds")),
            )
        return "ok"
    except sqlite3.IntegrityError:
        return "exists"


def authenticate(email: str, password: str):
    """Returns (status, user): status is 'ok', 'no_user' or 'bad_password'."""
    row = get_user(email)
    if row is None:
        return "no_user", None
    if not secrets.compare_digest(_hash(password, row["salt"]), row["password_hash"]):
        return "bad_password", None
    return "ok", {"name": row["name"], "email": row["email"]}


def start_password_reset(email: str) -> str:
    """Creates a 6-digit code (stored only as a hash) and returns it."""
    row = get_user(email)
    code = f"{secrets.randbelow(10 ** 6):06d}"
    with _db() as conn:
        conn.execute(
            "UPDATE users SET reset_hash = ?, reset_expires = ?, reset_attempts = 0 "
            "WHERE email = ?",
            (_hash(code, row["salt"]), time.time() + RESET_MINUTES * 60, email),
        )
    return code


def send_reset_email(to_email: str, name: str, code: str):
    """Sends the code by SMTP. Returns (sent, error_message)."""
    host = os.getenv("SMTP_HOST")
    user = os.getenv("SMTP_USER")
    password = os.getenv("SMTP_PASSWORD")
    port = int(os.getenv("SMTP_PORT", "587"))
    if not (host and user and password):
        return False, "Email is not configured."

    msg = EmailMessage()
    msg["Subject"] = "Your FinWise AI password reset code"
    msg["From"] = os.getenv("SMTP_FROM", user)
    msg["To"] = to_email
    msg.set_content(
        f"Hello {name},\n\n"
        f"Your FinWise AI password reset code is: {code}\n\n"
        f"It expires in {RESET_MINUTES} minutes. "
        "If you did not ask for this, you can ignore this email.\n\n"
        "FinWise AI is for educational use only."
    )
    try:
        if port == 465:
            with smtplib.SMTP_SSL(host, port, timeout=20) as server:
                server.login(user, password)
                server.send_message(msg)
        else:
            with smtplib.SMTP(host, port, timeout=20) as server:
                server.starttls()
                server.login(user, password)
                server.send_message(msg)
        return True, ""
    except Exception as e:
        return False, str(e)


def reset_password(email: str, code: str, new_password: str):
    """Returns (ok, message)."""
    row = get_user(email)
    if row is None or not row["reset_hash"]:
        return False, "Please request a new reset code."
    if time.time() > (row["reset_expires"] or 0):
        return False, "This code has expired. Please request a new one."
    if row["reset_attempts"] >= MAX_RESET_ATTEMPTS:
        return False, "Too many wrong attempts. Please request a new code."

    if not secrets.compare_digest(_hash(code.strip(), row["salt"]), row["reset_hash"]):
        with _db() as conn:
            conn.execute(
                "UPDATE users SET reset_attempts = reset_attempts + 1 WHERE email = ?",
                (email,),
            )
        left = MAX_RESET_ATTEMPTS - row["reset_attempts"] - 1
        return False, f"Incorrect code. {left} attempt(s) left."

    problem = validate_password(new_password)
    if problem:
        return False, problem

    new_salt = secrets.token_hex(16)
    with _db() as conn:
        conn.execute(
            "UPDATE users SET salt = ?, password_hash = ?, reset_hash = NULL, "
            "reset_expires = NULL, reset_attempts = 0 WHERE email = ?",
            (new_salt, _hash(new_password, new_salt), email),
        )
    return True, "Password updated."


def verify_openai_key(api_key: str):
    """Returns (ok, message). Listing models costs nothing."""
    key = (api_key or "").strip()
    if not key.startswith("sk-"):
        return False, "An OpenAI API key starts with 'sk-'. Please check it."
    client = openai.OpenAI(api_key=key, timeout=20)
    try:
        client.models.list()
        return True, ""
    except openai.AuthenticationError:
        return False, "This OpenAI API key is not valid. Please check it and try again."
    except openai.PermissionDeniedError:
        # Restricted keys may not list models: try a tiny request instead.
        try:
            client.chat.completions.create(
                model=config.DEFAULT_MODEL,
                messages=[{"role": "user", "content": "hi"}],
                max_tokens=1,
            )
            return True, ""
        except openai.RateLimitError:
            return False, "The key is valid but has no credit or quota left. Check your OpenAI billing."
        except Exception as e:
            return False, f"Could not verify the key: {e}"
    except Exception as e:
        return False, f"Could not verify the key. Check your internet connection. ({e})"


# =====================================================================
# PART 2: Screens (login, sign up, forgot password)
# =====================================================================
AUTH_CSS = """
<style>
footer {visibility: hidden;}
.block-container {padding-top: 2.2rem; max-width: 1200px;}

/* ---------- Left side: hero ---------- */
.auth-hero {position: relative; overflow: hidden; min-height: 650px;
       padding: 2.6rem 2.6rem; border-radius: 26px; color: white;
       display: flex; flex-direction: column; justify-content: center;
       background: radial-gradient(circle at 12% 8%, rgba(255,255,255,.20), transparent 42%),
                   linear-gradient(145deg, #0f766e 0%, #0e7490 45%, #2563eb 100%);
       box-shadow: 0 16px 40px rgba(37,99,235,.30);}
.auth-hero::before {content: ""; position: absolute; width: 340px; height: 340px;
       border-radius: 50%; right: -120px; top: -120px; background: rgba(255,255,255,.10);}
.auth-hero::after {content: ""; position: absolute; width: 260px; height: 260px;
       border-radius: 50%; left: -90px; bottom: -90px; background: rgba(255,255,255,.08);}
.auth-hero > * {position: relative; z-index: 1;}
.auth-brand {display: flex; align-items: center; gap: .8rem; margin-bottom: 1.8rem;}
.auth-logo {width: 54px; height: 54px; border-radius: 16px; font-size: 1.7rem;
       background: rgba(255,255,255,.20); border: 1px solid rgba(255,255,255,.3);
       display: flex; align-items: center; justify-content: center;}
.auth-brand-name {font-size: 1.5rem; font-weight: 800; letter-spacing: .3px;}
.auth-headline {font-size: 2.6rem; font-weight: 800; line-height: 1.15; margin: 0;}
.auth-headline span {color: #a7f3d0;}
.auth-tagline {margin: .9rem 0 1.5rem; font-size: 1.1rem; line-height: 1.5;
       color: rgba(255,255,255,.92); max-width: 460px;}
.auth-feat {display: flex; gap: .9rem; align-items: center; padding: .75rem 1rem;
       margin-bottom: .7rem; border-radius: 16px;
       background: rgba(255,255,255,.12); border: 1px solid rgba(255,255,255,.22);}
.auth-feat-ic {width: 42px; height: 42px; flex: none; border-radius: 12px; font-size: 1.25rem;
       background: rgba(255,255,255,.20); display: flex; align-items: center; justify-content: center;}
.auth-feat-title {font-weight: 700; font-size: 1rem;}
.auth-feat-text {font-size: .85rem; opacity: .85; margin-top: .1rem;}
.auth-preview {margin-top: 1rem; padding: 1rem 1.2rem; border-radius: 18px;
       background: rgba(255,255,255,.95); color: #0f172a;
       box-shadow: 0 10px 24px rgba(0,0,0,.18);}
.ap-row {display: flex; justify-content: space-between; font-size: .95rem; font-weight: 700;}
.ap-row span {color: #0f766e;}
.ap-bar {height: 10px; border-radius: 999px; background: #e2e8f0; margin: .6rem 0 .5rem; overflow: hidden;}
.ap-bar div {height: 100%; border-radius: 999px; background: linear-gradient(90deg, #0f766e, #2563eb);}
.ap-note {font-size: .78rem; color: #64748b;}
.auth-foot {margin-top: 1.2rem; font-size: .8rem; opacity: .8;}

/* ---------- Right side: card ---------- */
.st-key-auth_card {border-radius: 22px; padding: 1.2rem 1.4rem;
       box-shadow: 0 10px 30px rgba(0,0,0,.08);}
.auth-title {font-size: 1.8rem; font-weight: 800; margin: .3rem 0 .1rem; text-align: center;}
.auth-sub {opacity: .75; margin-bottom: 1rem; text-align: center;}
.auth-note {text-align: center; opacity: .7; font-size: .85rem; margin: .7rem 0 .4rem;}

/* Big, centered main buttons */
div[data-testid="stFormSubmitButton"] {display: flex; justify-content: center; width: 100%;}
div[data-testid="stFormSubmitButton"] button {
       width: 100%; min-width: 420px;
       background: linear-gradient(135deg, #0f766e, #2563eb); color: white;
       border: none; border-radius: 12px; padding: .75rem 1.6rem; font-weight: 700;}
div[data-testid="stFormSubmitButton"] button:hover {filter: brightness(1.1); color: white;}



/* Link-style buttons: centered / left / right */
div[class*="st-key-center_"] div[data-testid="stButton"] {display: flex; justify-content: center;}
div[class*="st-key-left_"] div[data-testid="stButton"] {display: flex; justify-content: flex-start;}
div[class*="st-key-right_"] div[data-testid="stButton"] {display: flex; justify-content: flex-end;}

@media (max-width: 900px) {.auth-hero {min-height: auto;} .auth-headline {font-size: 2rem;}}
</style>
"""

AUTH_HERO_HTML = """
<div class="auth-hero">
<div class="auth-brand"><div class="auth-logo">💰</div><div class="auth-brand-name">FinWise AI</div></div>
<div class="auth-headline">Understand your money.<br><span>Plan it smarter.</span></div>
<div class="auth-tagline">Enter your income and expenses, and get a simple, educational plan to improve your monthly budget.</div>
<div class="auth-feat"><div class="auth-feat-ic">🔒</div><div><div class="auth-feat-title">Secure login</div><div class="auth-feat-text">Passwords are hashed. Your API key is never stored.</div></div></div>
<div class="auth-feat"><div class="auth-feat-ic">📊</div><div><div class="auth-feat-title">Smart dashboard</div><div class="auth-feat-text">Ratios, charts and goal tracking in one place.</div></div></div>
<div class="auth-feat"><div class="auth-feat-ic">🤖</div><div><div class="auth-feat-title">AI insights</div><div class="auth-feat-text">Clear priorities and a next-month action plan.</div></div></div>
<div class="auth-preview"><div class="ap-row"><b>Financial health score</b><span>78 / 100</span></div><div class="ap-bar"><div style="width:78%"></div></div><div class="ap-note">Sample preview · Savings ratio 24% · Risk LOW</div></div>
<div class="auth-foot">For educational use only. Not financial advice.</div>
</div>
"""


def _go(page: str):
    st.session_state.auth_page = page
    if page == "forgot":
        st.session_state.reset_stage = "request"


def _heading(title: str, subtitle: str):
    st.markdown(
        f'<div class="auth-title">{title}</div><div class="auth-sub">{subtitle}</div>',
        unsafe_allow_html=True,
    )


def logout():
    st.session_state.clear()


def _login_page():
    _heading("Welcome👋", "Log in to open your financial dashboard.")

    flash = st.session_state.pop("flash", None)
    if flash:
        st.success(flash)

    with st.form("login_form", border=False):
        email = st.text_input("Email", key="login_email", placeholder="you@example.com")
        password = st.text_input("Password", type="password", key="login_password")
        api_key = st.text_input(
            "OpenAI API key", type="password", placeholder="sk-...",
            help="Used only during this session to talk to OpenAI. It is never saved.",
        )
        st.caption("Do not have a key? "
                   "[Create one on the OpenAI platform](https://platform.openai.com/api-keys)")
        submitted = st.form_submit_button("Login")

    if submitted:
        email_n = normalize_email(email)
        if not email_n or not password or not api_key.strip():
            st.error("Please fill in your email, password and OpenAI API key.")
        else:
            status, user = authenticate(email_n, password)
            if status == "no_user":
                st.error("No account found with this email. Please sign up first.")
            elif status == "bad_password":
                st.error("Incorrect password. Try again, or use 'Forgot password?'.")
            else:
                with st.spinner("Checking your OpenAI API key..."):
                    ok, message = verify_openai_key(api_key)
                if not ok:
                    st.error(message)
                else:
                    st.session_state.user = user
                    st.session_state.openai_key = api_key.strip()
                    st.session_state.just_logged_in = True
                    st.rerun()

    st.markdown('<div class="auth-note">🔐 Your key is used only for this session '
                'and is never stored.</div>', unsafe_allow_html=True)

    c1, c2 = st.columns(2)
    c1.button("Forgot password?", key="left_forgot", on_click=_go,
              args=("forgot",), type="tertiary")
    c2.button("New here? Create an account", key="right_signup", on_click=_go,
              args=("signup",), type="tertiary")


def _signup_page():
    _heading("Create your account ✨", "It takes less than a minute.")

    with st.form("signup_form", border=False):
        name = st.text_input("Full name", placeholder="Arooj")
        email = st.text_input("Email", placeholder="you@example.com")
        password = st.text_input("Password", type="password")
        confirm = st.text_input("Confirm password", type="password")
        st.caption("Password: at least 8 characters, with letters and numbers.")
        submitted = st.form_submit_button("Sign up")

    if submitted:
        email_n = normalize_email(email)
        clean_name = " ".join(name.split()).title()
        problem = validate_password(password)
        if not clean_name:
            st.error("Please enter your name.")
        elif not validate_email(email_n):
            st.error("Please enter a valid email address.")
        elif problem:
            st.error(problem)
        elif password != confirm:
            st.error("The two passwords do not match.")
        elif create_user(clean_name, email_n, password) == "exists":
            st.error("This email is already registered. Please log in instead.")
        else:
            st.session_state.flash = "🎉 Account created! Please log in to continue."
            st.session_state.login_email = email_n
            st.session_state.auth_page = "login"
            st.rerun()

    st.button("Already have an account? Log in", key="center_to_login", on_click=_go,
              args=("login",), type="tertiary")


def _forgot_page():
    _heading("Reset your password 🔑", "We will email you a 6-digit code.")
    stage = st.session_state.get("reset_stage", "request")

    if stage == "request":
        with st.form("forgot_request_form", border=False):
            email = st.text_input("Your account email", placeholder="you@example.com")
            send = st.form_submit_button("Send reset code")
        if send:
            email_n = normalize_email(email)
            row = get_user(email_n) if validate_email(email_n) else None
            if row is None:
                st.error("No account found with this email.")
            else:
                code = start_password_reset(email_n)
                sent, _ = send_reset_email(email_n, row["name"], code)
                st.session_state.reset_email = email_n
                st.session_state.reset_notice = {"sent": sent, "code": None if sent else code}
                st.session_state.reset_stage = "verify"
                st.rerun()
    else:
        email_n = st.session_state.get("reset_email", "")
        notice = st.session_state.get("reset_notice", {})
        if notice.get("sent"):
            st.success(f"A 6-digit code was sent to **{html.escape(email_n)}**. "
                       f"It expires in {RESET_MINUTES} minutes.")
        else:
            st.warning(
                "Email sending is not set up on this computer (demo mode), "
                f"so your code is shown here: **{notice.get('code')}**"
            )

        with st.form("forgot_verify_form", border=False):
            code_in = st.text_input("6-digit code", max_chars=6)
            new_pw = st.text_input("New password", type="password")
            confirm = st.text_input("Confirm new password", type="password")
            st.caption("Password: at least 8 characters, with letters and numbers.")
            update = st.form_submit_button("Update password")

        if update:
            if not code_in.strip():
                st.error("Please enter the 6-digit code.")
            elif new_pw != confirm:
                st.error("The two passwords do not match.")
            else:
                ok, message = reset_password(email_n, code_in, new_pw)
                if not ok:
                    st.error(message)
                else:
                    for key in ("reset_email", "reset_notice", "reset_stage"):
                        st.session_state.pop(key, None)
                    st.session_state.flash = "✅ Password updated! Please log in with your new password."
                    st.session_state.login_email = email_n
                    st.session_state.auth_page = "login"
                    st.rerun()

        st.button("Send a new code / use another email", key="center_new_code",
                  on_click=_go, args=("forgot",), type="tertiary")

    st.button("← Back to login", key="center_back_login", on_click=_go,
              args=("login",), type="tertiary")


def require_login():
    """Shows the auth pages and stops the app until a valid login happens."""
    st.session_state.setdefault("auth_page", "login")
    if st.session_state.get("user") and st.session_state.get("openai_key"):
        return

    init_db()
    st.markdown(AUTH_CSS, unsafe_allow_html=True)
    left, right = st.columns([1.1, 1], gap="large", vertical_alignment="center")
    with left:
        st.markdown(AUTH_HERO_HTML, unsafe_allow_html=True)
    with right:
        with st.container(border=True, key="auth_card"):
            page = st.session_state.auth_page
            if page == "signup":
                _signup_page()
            elif page == "forgot":
                _forgot_page()
            else:
                _login_page()
        st.warning(f"⚠️ {config.EDUCATIONAL_DISCLAIMER}")
    st.stop()


def show_user_box():
    """Greeting + logout button (called inside the sidebar)."""
    user = st.session_state.get("user")
    if not user:
        return
    if st.session_state.pop("just_logged_in", False):
        st.toast(f"Welcome, {user['name']} 👋")
    st.markdown(f"**👋 Welcome, {html.escape(user['name'])}**")
    st.caption(user["email"])
    st.button("🚪 Logout", on_click=logout)
def show_user_box():
    """Greeting + logout button (called inside the sidebar)."""
    user = st.session_state.get("user")
    if not user:
        return
    if st.session_state.pop("just_logged_in", False):
        st.toast(f"Welcome, {user['name']} 👋")
    st.markdown(f"**👋 Welcome, {html.escape(user['name'])}**")
    st.caption(user["email"])
    st.button("🚪 Logout", on_click=logout)