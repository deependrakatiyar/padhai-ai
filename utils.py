import streamlit as st
import re
import os
import uuid
from datetime import datetime

try:
    from groq import Groq as _Groq
except ImportError:
    _Groq = None

try:
    import requests as _req
except ImportError:
    _req = None

MODEL = "llama-3.3-70b-versatile"
MAX_REQUESTS_PER_SESSION = 20

# ── Credentials ───────────────────────────────────────────────────────────────

def _secret(key: str) -> str:
    try:
        return st.secrets[key]
    except Exception:
        return os.environ.get(key, "")

# ── Groq ──────────────────────────────────────────────────────────────────────

def get_api_key() -> str:
    return _secret("GROQ_API_KEY") or st.session_state.get("groq_api_key", "")

def get_client():
    if _Groq is None:
        st.error("groq package not installed.")
        st.stop()
    return _Groq(api_key=get_api_key())

def require_api_key() -> bool:
    if get_api_key():
        return True
    st.sidebar.divider()
    st.sidebar.markdown("### 🔑 Groq API Key")
    st.sidebar.markdown("**Free key (30 sec):**\n1. [console.groq.com](https://console.groq.com)\n2. API Keys → Create Key\n3. Paste below")
    key = st.sidebar.text_input("Groq API Key", type="password", placeholder="gsk_...")
    if key:
        st.session_state.groq_api_key = key
        st.rerun()
    st.info("👈 Sidebar mein apni **free Groq API key** enter karo.")
    return False

def _server_request_count(session_id: str) -> int:
    """Count today's AI calls for this session_id from Supabase. Returns 0 on any error (fail-open)."""
    if _req is None:
        return 0
    base = _sb_base()
    if not base:
        return 0
    key = _secret("SUPABASE_SERVICE_KEY") or _secret("SUPABASE_KEY")
    if not key:
        return 0
    try:
        today = datetime.now().strftime("%Y-%m-%d")
        r = _req.get(
            f"{base}/rest/v1/usage_logs",
            headers={
                "apikey": key,
                "Authorization": f"Bearer {key}",
                "Prefer": "count=exact",
            },
            params={
                "session_id": f"eq.{session_id}",
                "ai_called": "eq.true",
                "created_at": f"gte.{today}T00:00:00",
                "select": "session_id",
                "limit": "0",
            },
            timeout=2,
        )
        if r.status_code == 200:
            cr = r.headers.get("Content-Range", "*/0")
            try:
                return int(cr.split("/")[-1])
            except (ValueError, IndexError):
                return 0
    except Exception:
        pass
    return 0


def check_rate_limit() -> bool:
    count = st.session_state.get("request_count", 0)

    # Client-side fast check
    if count >= MAX_REQUESTS_PER_SESSION:
        st.warning(
            f"⚠️ **Session limit ({MAX_REQUESTS_PER_SESSION} requests) reach ho gayi.**  \n"
            "Browser tab refresh karo ya kal dobara aao. Groq free tier ka fair-use limit hai."
        )
        return False

    # Server-side check only on the first request of a session —
    # syncs the client counter with actual DB usage so multi-tab and
    # post-refresh abuse is caught without adding latency to every call.
    if count == 0:
        session_id = st.session_state.get("user_info", {}).get("session_id", "")
        if session_id:
            server_count = _server_request_count(session_id)
            if server_count >= MAX_REQUESTS_PER_SESSION:
                st.warning(
                    f"⚠️ **Aaj ki limit ({MAX_REQUESTS_PER_SESSION} requests) reach ho gayi.**  \n"
                    "Kal dobara aao. Groq free tier ka fair-use limit hai."
                )
                return False
            # Sync client counter with server so the client limit is accurate
            st.session_state.request_count = server_count
            count = server_count

    st.session_state.request_count = count + 1
    return True

def show_api_error(e: Exception):
    err = str(e)
    if "429" in err or "rate_limit" in err.lower():
        m = re.search(r'try again in (\d+\.?\d*)s', err)
        secs = int(float(m.group(1))) + 1 if m else 30
        st.warning(f"⏳ **Rate limit — {secs} seconds baad dobara try karo.**")
    elif "401" in err or "invalid_api_key" in err.lower():
        st.error("❌ **Invalid API Key.** Sidebar mein sahi Groq API key enter karo.")
        st.session_state.pop("groq_api_key", None)
        # No st.rerun() — let the user read the error and enter a new key naturally
    else:
        st.error("❌ Error:")
        st.code(err, language="text")

# ── Input validation ──────────────────────────────────────────────────────────

def validate_text(value: str, field: str, min_len=2, max_len=100) -> str:
    v = value.strip()
    if len(v) < min_len:
        return f"{field}: kam se kam {min_len} characters chahiye"
    if len(v) > max_len:
        return f"{field}: {max_len} se zyada characters allowed nahi"
    return ""

# ── Supabase ──────────────────────────────────────────────────────────────────

def _sb_headers() -> dict:
    key = _secret("SUPABASE_KEY")
    return {"apikey": key, "Authorization": f"Bearer {key}",
            "Content-Type": "application/json", "Prefer": "return=minimal"}

def _sb_base() -> str:
    return _secret("SUPABASE_URL").rstrip("/")

_AUDIT_COLS = frozenset({"valid_input", "ai_called", "response_valid"})

def _sb_post(table: str, data: dict):
    if _req is None or not _sb_base() or not _secret("SUPABASE_KEY"):
        return
    try:
        r = _req.post(f"{_sb_base()}/rest/v1/{table}",
                      headers=_sb_headers(), json=data, timeout=4)
        if r.status_code in (400, 422):
            # Audit columns may not exist yet — retry with core fields only
            core = {k: v for k, v in data.items() if k not in _AUDIT_COLS}
            if core != data:
                _req.post(f"{_sb_base()}/rest/v1/{table}",
                          headers=_sb_headers(), json=core, timeout=4)
    except Exception:
        pass

def _sb_get(table: str, select: str = "*", order: str = "created_at.desc", limit: int = 5000):
    if _req is None:
        return []
    base = _sb_base()
    if not base:
        return []
    # Prefer service role key for reads — bypasses RLS so admin dashboard always works.
    # Students still write with the anon key (SUPABASE_KEY) via _sb_post.
    key = _secret("SUPABASE_SERVICE_KEY") or _secret("SUPABASE_KEY")
    if not key:
        return []
    try:
        r = _req.get(
            f"{base}/rest/v1/{table}",
            headers={"apikey": key, "Authorization": f"Bearer {key}"},
            params={"select": select, "order": order, "limit": limit},
            timeout=8,
        )
        if r.status_code == 200:
            data = r.json()
            return data if isinstance(data, list) else []
        # Surface the real error so the dashboard can display it
        try:
            st.session_state["_sb_read_error"] = (
                f"HTTP {r.status_code} on {table}: {r.text[:300]}"
            )
        except Exception:
            pass
        return []
    except Exception as exc:
        try:
            st.session_state["_sb_read_error"] = f"{type(exc).__name__}: {exc}"
        except Exception:
            pass
        return []

# ── AI Disclaimer ─────────────────────────────────────────────────────────────

_DISCLAIMER = """
<div style="background:#fff8e1;border-left:4px solid #f9a825;border-radius:6px;
            padding:10px 14px;margin:12px 0;font-size:0.82rem;color:#555;">
  <strong>⚠️ AI-Generated Content — Disclaimer:</strong><br>
  Yeh content AI (Large Language Model) dwara generate kiya gaya hai.
  Yeh <strong>sirf padhai mein help</strong> ke liye hai.
  Exam ya important kaam ke liye hamesha <strong>NCERT books / official sources</strong> se verify karein.
  District Administration Raisen ya NIC is content ki accuracy ki guarantee nahi deta.
</div>"""

def show_disclaimer():
    st.markdown(_DISCLAIMER, unsafe_allow_html=True)

# ── Government branding ───────────────────────────────────────────────────────

_GOV_BANNER = """
<div style="background:linear-gradient(90deg,#003087,#0057b8);color:white;
            padding:10px 18px;border-radius:8px;margin-bottom:18px;
            display:flex;align-items:center;gap:12px;">
  <div style="font-size:2rem;">🏛️</div>
  <div>
    <div style="font-size:0.72rem;opacity:0.8;letter-spacing:.5px;">AN INITIATIVE BY</div>
    <div style="font-weight:700;font-size:1rem;line-height:1.2;">
      District Administration Raisen &nbsp;|&nbsp; NIC (National Informatics Centre)
    </div>
    <div style="font-size:0.68rem;opacity:0.75;">Madhya Pradesh Government &nbsp;·&nbsp; Digital India</div>
  </div>
  <div style="margin-left:auto;text-align:right;">
    <div style="font-size:1.4rem;">🇮🇳</div>
    <div style="font-size:0.65rem;opacity:.8;">Digital India</div>
  </div>
</div>"""

_GOV_FOOTER = """
<div style="text-align:center;padding:14px 0 8px;color:#777;
            font-size:0.78rem;border-top:1px solid #e0e0e0;margin-top:28px;">
  An initiative by <strong>District Administration Raisen</strong> &nbsp;|&nbsp;
  NIC MP &nbsp;|&nbsp; 🇮🇳 Digital India<br>
  <span style="color:#003087;font-weight:600;">Padhai AI</span> — MP Board Students ke liye AI ki Shakti ke Saath
</div>"""

def show_gov_banner():
    st.markdown(_GOV_BANNER, unsafe_allow_html=True)

def show_gov_footer():
    st.markdown(_GOV_FOOTER, unsafe_allow_html=True)

# ── Registration ──────────────────────────────────────────────────────────────

MP_DISTRICTS = [
    "Agar Malwa","Alirajpur","Anuppur","Ashoknagar","Balaghat","Barwani",
    "Betul","Bhind","Bhopal","Burhanpur","Chhatarpur","Chhindwara","Damoh",
    "Datia","Dewas","Dhar","Dindori","Guna","Gwalior","Harda","Hoshangabad",
    "Indore","Jabalpur","Jhabua","Katni","Khandwa","Khargone","Maihar",
    "Mandla","Mandsaur","Mauganj","Morena","Narsinghpur","Neemuch","Niwari",
    "Pandhurna","Panna","Raisen","Rajgarh","Ratlam","Rewa","Sagar","Satna",
    "Sehore","Seoni","Shahdol","Shajapur","Sheopur","Shivpuri","Sidhi",
    "Singrauli","Tikamgarh","Ujjain","Umaria","Vidisha","Other",
]
CLASSES = ["Class 6","Class 7","Class 8","Class 9","Class 10","Class 11","Class 12"]

def ensure_registered() -> bool:
    if st.session_state.get("user_registered"):
        return True

    show_gov_banner()
    st.markdown("## 👋 Padhai AI mein Swagat Hai!")
    st.markdown("Shuru karne se pehle apni details bharo — **sirf ek baar:**")

    st.markdown("""
<div style="background:#fff3e0;border-left:4px solid #e65100;border-radius:6px;
            padding:10px 14px;margin:12px 0;font-size:0.82rem;color:#444;">
  <strong>🔒 Data Privacy Notice (DPDP Act 2023)</strong><br>
  Padhai AI aapka <strong>naam, school, district aur class</strong> collect karta hai
  — sirf usage analytics ke liye (District Administration Raisen / NIC MP).<br>
  Yeh data third parties ko share nahi kiya jata. Koi bhi personal information
  publicly display nahi hogi. Data secure cloud storage (Supabase) mein rakhha jata hai.
  <br><strong>Platform sirf Class 6–12 ke students ke liye hai.</strong>
</div>""", unsafe_allow_html=True)

    st.divider()

    with st.form("reg_form"):
        name  = st.text_input("Aapka Naam *", placeholder="e.g., Rahul Sharma", max_chars=60)
        col1, col2 = st.columns(2)
        cls   = col1.selectbox("Class *", CLASSES)
        dist  = col2.selectbox("District *", MP_DISTRICTS)
        school = st.text_input("School ka Naam *", placeholder="e.g., Govt. HS School Raisen", max_chars=120)
        consent = st.checkbox(
            "Main samajhta/samajhti hoon ki mera naam, school aur class "
            "analytics ke liye securely store kiya jayega. "
            "(**Privacy Notice** upar padhi hai.)"
        )
        done  = st.form_submit_button("✅ Shuru Karein!", use_container_width=True, type="primary")

    if done:
        if not consent:
            st.error("❌ Shuru karne ke liye Privacy Notice accept karna zaroori hai.")
            return False
        err = validate_text(name, "Naam") or validate_text(school, "School ka naam", min_len=3)
        if err:
            st.error(err)
            return False
        info = {
            "name":        name.strip(),
            "class":       cls,
            "school_name": school.strip(),
            "district":    dist,
            "session_id":  uuid.uuid4().hex,
        }
        st.session_state.user_registered = True
        st.session_state.user_info = info
        st.session_state.request_count = 0
        _sb_post("registrations", info)
        st.rerun()
    return False

# ── Usage logging ─────────────────────────────────────────────────────────────

def log_usage(feature: str, subject: str = "", topic: str = "",
              *, valid_input: bool = True, ai_called: bool = True,
              response_valid: bool = True):
    user = st.session_state.get("user_info", {})
    _sb_post("usage_logs", {
        "user_name":      user.get("name", "Anonymous"),
        "user_class":     user.get("class", ""),
        "school_name":    user.get("school_name", ""),
        "district":       user.get("district", ""),
        "feature":        feature,
        "subject":        subject,
        "topic":          topic[:200],
        "session_id":     user.get("session_id", ""),
        "valid_input":    valid_input,
        "ai_called":      ai_called,
        "response_valid": response_valid,
    })

# ── Impact report ─────────────────────────────────────────────────────────────

def generate_impact_report(reg_df, usage_df) -> str:
    import pandas as pd
    total_s   = len(reg_df)
    total_q   = len(usage_df)
    schools   = reg_df["school_name"].nunique() if not reg_df.empty else 0
    districts = reg_df["district"].nunique()    if not reg_df.empty else 0
    top_sub   = (usage_df[usage_df["subject"] != ""]["subject"].value_counts().index[0]
                 if not usage_df.empty and usage_df["subject"].any() else "N/A")
    top_feat  = (usage_df["feature"].value_counts().index[0]
                 if not usage_df.empty else "N/A")
    line = "=" * 55
    return f"""
{line}
        PADHAI AI — OFFICIAL IMPACT REPORT
   District Administration Raisen | NIC Madhya Pradesh
           Generated: {datetime.now().strftime("%d %B %Y, %I:%M %p")}
{line}

REACH SUMMARY
  Total Students Registered : {total_s}
  Total AI Queries Answered  : {total_q}
  Schools Covered            : {schools}
  Districts Reached          : {districts}

USAGE HIGHLIGHTS
  Most Used Feature          : {top_feat}
  Most Popular Subject       : {top_sub}
  Avg Queries / Student      : {round(total_q / total_s, 1) if total_s else 0}

IMPACT NARRATIVE
  This platform has served {total_s} students across {schools} schools
  in {districts} district(s) of Madhya Pradesh. A total of {total_q}
  AI-powered queries have been resolved, covering subjects aligned
  with the MP Board curriculum for Class 6–12.

  The platform is available 24×7 at zero cost to students,
  hosted on secure cloud infrastructure managed by NIC under
  the Digital India initiative.

{line}
  Certified by: District Administration Raisen (NIC MP)
  Platform URL: https://smartpadhai.streamlit.app
{line}
""".strip()

# ── Connection test ───────────────────────────────────────────────────────────

def run_connection_test() -> dict:
    result = {"registration": False, "usage_log": False, "error": ""}
    if not _sb_base() or not _secret("SUPABASE_KEY"):
        result["error"] = "SUPABASE_URL / SUPABASE_KEY missing in secrets"
        return result
    try:
        r1 = _req.post(f"{_sb_base()}/rest/v1/registrations",
                       headers=_sb_headers(),
                       json={"name":"Test Student","class":"Class 10",
                             "school_name":"Test School","district":"Raisen","session_id":"test_000"},
                       timeout=5)
        result["registration"] = r1.status_code in (200, 201)
        if not result["registration"]:
            result["error"] = f"registrations: HTTP {r1.status_code} — {r1.text[:300]}"
            return result
        r2 = _req.post(f"{_sb_base()}/rest/v1/usage_logs",
                       headers=_sb_headers(),
                       json={"user_name":"Test Student","user_class":"Class 10",
                             "school_name":"Test School","district":"Raisen",
                             "feature":"Connection Test","subject":"Test",
                             "topic":"Supabase Integration Test","session_id":"test_000"},
                       timeout=5)
        result["usage_log"] = r2.status_code in (200, 201)
        if not result["usage_log"]:
            result["error"] = f"usage_logs: HTTP {r2.status_code} — {r2.text[:300]}"
    except Exception as e:
        result["error"] = str(e)
    return result
