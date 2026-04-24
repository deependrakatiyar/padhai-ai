import streamlit as st
import os
import hmac
import pandas as pd
from datetime import date, timedelta
from utils import _sb_get, run_connection_test, _secret, generate_impact_report

st.set_page_config(page_title="Admin Dashboard - Padhai AI", page_icon="📊", layout="wide")

# ── Auth ──────────────────────────────────────────────────────────────────────

ADMIN_PASS = _secret("ADMIN_PASSWORD")

if not ADMIN_PASS:
    st.error("❌ **ADMIN_PASSWORD secret is not configured.** "
             "Set it in Streamlit secrets before accessing this page.")
    st.stop()

if not st.session_state.get("admin_auth"):
    st.markdown("""
    <div style="background:linear-gradient(90deg,#003087,#0057b8);color:white;
                padding:12px 20px;border-radius:8px;margin-bottom:24px;">
      <div style="font-size:.72rem;opacity:.8;">AN INITIATIVE BY</div>
      <div style="font-weight:700;font-size:1.1rem;">District Administration Raisen | NIC MP</div>
    </div>""", unsafe_allow_html=True)
    st.markdown("## 🔐 Admin Login — NIC Raisen DIO")
    pwd = st.text_input("Password", type="password")
    if st.button("Login", type="primary", use_container_width=True):
        if hmac.compare_digest(pwd, ADMIN_PASS):
            st.session_state.admin_auth = True
            st.rerun()
        else:
            st.error("❌ Wrong password")
    st.stop()

# ── Header ────────────────────────────────────────────────────────────────────

st.markdown("""
<div style="background:linear-gradient(90deg,#003087,#0057b8);color:white;
            padding:12px 20px;border-radius:8px;margin-bottom:4px;
            display:flex;justify-content:space-between;align-items:center;">
  <div>
    <div style="font-size:.7rem;opacity:.8;">AN INITIATIVE BY</div>
    <div style="font-weight:700;font-size:1.05rem;">District Administration Raisen | NIC MP | Digital India</div>
  </div>
  <div style="font-size:2rem;">🏛️ 🇮🇳</div>
</div>""", unsafe_allow_html=True)

st.markdown("# 📊 Padhai AI — Impact Dashboard")
st.caption("NIC Raisen DIO | Real-time Usage Analytics")
st.divider()

# ── Supabase check ────────────────────────────────────────────────────────────

if not (_secret("SUPABASE_URL") and _secret("SUPABASE_KEY")):
    st.warning("⚠️ Supabase credentials missing in Secrets.")
    st.code('SUPABASE_URL = "https://xxxx.supabase.co"\nSUPABASE_KEY = "eyJ..."\nADMIN_PASSWORD = "your_password"', language="toml")
    st.stop()

# ── Date filter ───────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("### 📅 Date Filter")
    preset = st.selectbox("Period", ["All Time", "Last 7 Days", "Last 30 Days", "Last 90 Days"])
    if preset == "Last 7 Days":
        default_from = date.today() - timedelta(days=7)
    elif preset == "Last 30 Days":
        default_from = date.today() - timedelta(days=30)
    elif preset == "Last 90 Days":
        default_from = date.today() - timedelta(days=90)
    else:
        default_from = date(2024, 1, 1)

    date_range = st.date_input("Custom Range", value=(default_from, date.today()),
                               min_value=date(2024, 1, 1), max_value=date.today())
    # date_input can return a single date or a tuple — handle both
    if isinstance(date_range, (list, tuple)) and len(date_range) == 2:
        d_from, d_to = date_range
    else:
        d_from, d_to = default_from, date.today()

    st.divider()
    show_all = st.checkbox("📊 Show All Data (ignore date filter)", value=False)
    st.divider()
    if st.button("🔄 Refresh Data", use_container_width=True):
        st.rerun()
    if st.button("🚪 Logout", use_container_width=True):
        st.session_state.admin_auth = False
        st.rerun()

# ── Load + filter data ────────────────────────────────────────────────────────

with st.spinner("Data load ho raha hai..."):
    regs  = _sb_get("registrations")
    usage = _sb_get("usage_logs")

def to_df(rows):
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    # Strip timezone safely: parse as UTC then convert to naive
    df["created_at"] = (pd.to_datetime(df["created_at"], utc=True)
                          .dt.tz_convert(None))
    return df

reg_df_all   = to_df(regs)
usage_df_all = to_df(usage)

# Debug: show raw fetch counts
with st.sidebar:
    st.divider()
    st.caption(f"DB: {len(regs)} registrations, {len(usage)} usage logs fetched")
    if not regs and not usage:
        st.warning("⚠️ Supabase returned 0 rows. If RLS is enabled, add SUPABASE_SERVICE_KEY to secrets.")

def filter_df(df):
    if df.empty:
        return df
    mask = (df["created_at"].dt.date >= d_from) & (df["created_at"].dt.date <= d_to)
    return df[mask]

if show_all:
    reg_df   = reg_df_all
    usage_df = usage_df_all
else:
    reg_df   = filter_df(reg_df_all)
    usage_df = filter_df(usage_df_all)

# ── KPI cards ─────────────────────────────────────────────────────────────────

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("👨‍🎓 Students",   len(reg_df),
          delta=f"All time: {len(reg_df_all)}" if len(reg_df) != len(reg_df_all) else None)
c2.metric("🔍 Queries",     len(usage_df),
          delta=f"All time: {len(usage_df_all)}" if len(usage_df) != len(usage_df_all) else None)
c3.metric("🏫 Schools",     reg_df["school_name"].nunique() if not reg_df.empty else 0)
c4.metric("📍 Districts",   reg_df["district"].nunique()    if not reg_df.empty else 0)
avg_q = round(len(usage_df) / max(len(reg_df), 1), 1)
c5.metric("📈 Avg Q/Student", avg_q)

st.divider()

if usage_df.empty and reg_df.empty:
    st.info(f"No data for selected period ({d_from} to {d_to}). Adjust date filter or wait for registrations.")
    st.stop()

# ── Charts ────────────────────────────────────────────────────────────────────

col_l, col_r = st.columns(2)

with col_l:
    st.markdown("### 🎯 Feature-wise Usage")
    if not usage_df.empty:
        fc = usage_df["feature"].value_counts().reset_index()
        fc.columns = ["Feature", "Queries"]
        st.bar_chart(fc.set_index("Feature"), color="#0057b8")

    st.markdown("### 🎓 Class-wise Students")
    if not reg_df.empty:
        cc = reg_df["class"].value_counts().sort_index().reset_index()
        cc.columns = ["Class", "Students"]
        st.bar_chart(cc.set_index("Class"), color="#003087")

with col_r:
    st.markdown("### 📚 Top Subjects")
    if not usage_df.empty:
        sc = (usage_df[usage_df["subject"].fillna("") != ""]["subject"]
              .value_counts().head(10).reset_index())
        sc.columns = ["Subject", "Queries"]
        st.bar_chart(sc.set_index("Subject"), color="#0099cc")

    st.markdown("### 📍 District Reach")
    if not reg_df.empty:
        dc = reg_df["district"].value_counts().reset_index()
        dc.columns = ["District", "Students"]
        st.bar_chart(dc.set_index("District"), color="#006633")

st.divider()

# ── Daily activity ────────────────────────────────────────────────────────────

st.markdown("### 📅 Daily Activity")
if not usage_df.empty:
    daily = (usage_df.groupby(usage_df["created_at"].dt.date)
             .size().reset_index(name="Queries"))
    daily.columns = ["Date", "Queries"]
    st.line_chart(daily.set_index("Date"))

# ── School leaderboard ────────────────────────────────────────────────────────

st.markdown("### 🏫 School-wise Leaderboard")
if not usage_df.empty and not reg_df.empty:
    s_use = usage_df.groupby("school_name").size().reset_index(name="Total Queries")
    s_reg = reg_df.groupby("school_name").size().reset_index(name="Students")
    merged = s_use.merge(s_reg, on="school_name", how="left").fillna(0)
    merged.columns = ["School", "Total Queries", "Students"]
    merged["Students"] = merged["Students"].astype(int)
    merged = merged.sort_values("Total Queries", ascending=False)
    st.dataframe(merged, use_container_width=True, hide_index=True)

# ── Recent activity log ───────────────────────────────────────────────────────

st.divider()
st.markdown("### 🕒 Recent Activity Log")
if not usage_df.empty:
    disp = usage_df[["created_at","user_name","user_class","school_name",
                      "district","feature","subject","topic"]].copy()
    disp.columns = ["Time","Student","Class","School","District","Feature","Subject","Topic"]
    disp["Time"] = disp["Time"].dt.strftime("%d %b %H:%M")
    st.dataframe(disp.head(100), use_container_width=True, hide_index=True)

# ── Data quality audit ───────────────────────────────────────────────────────

st.divider()
st.markdown("### 🔬 Data Quality Audit")
if not usage_df.empty:
    has_audit = all(c in usage_df.columns for c in ["valid_input", "ai_called", "response_valid"])
    if has_audit:
        a1, a2, a3 = st.columns(3)
        valid_pct    = int(usage_df["valid_input"].fillna(True).mean() * 100)
        ai_pct       = int(usage_df["ai_called"].fillna(True).mean() * 100)
        resp_pct     = int(usage_df["response_valid"].fillna(True).mean() * 100)
        a1.metric("✅ Valid Inputs",       f"{valid_pct}%",
                  help="% of requests that passed input validation")
        a2.metric("🤖 AI Actually Called", f"{ai_pct}%",
                  help="% of valid requests that reached the AI")
        a3.metric("🔒 Clean Responses",   f"{resp_pct}%",
                  help="% of AI responses with no cross-subject contamination detected")
    else:
        st.info("Run the SQL in the Security expander below to add audit columns, then this section will populate.")
else:
    st.caption("No usage data in selected period.")

# ── Downloads ─────────────────────────────────────────────────────────────────

st.divider()
st.markdown("### ⬇️ Downloads")
c1, c2, c3 = st.columns(3)

if not reg_df.empty:
    c1.download_button("📋 Registrations CSV",
                       data=reg_df.to_csv(index=False),
                       file_name=f"padhai_registrations_{d_from}_{d_to}.csv",
                       mime="text/csv", use_container_width=True)

if not usage_df.empty:
    c2.download_button("📊 Usage Logs CSV",
                       data=usage_df.to_csv(index=False),
                       file_name=f"padhai_usage_{d_from}_{d_to}.csv",
                       mime="text/csv", use_container_width=True)

report_text = generate_impact_report(reg_df_all, usage_df_all)
c3.download_button("🏛️ Impact Report (TXT)",
                   data=report_text,
                   file_name="padhai_ai_impact_report.txt",
                   mime="text/plain", use_container_width=True)

# ── Impact report preview ─────────────────────────────────────────────────────

with st.expander("📄 Preview Impact Report (for District Collector / Presentation)"):
    st.code(report_text, language="text")

# ── Security checklist ────────────────────────────────────────────────────────

st.divider()
with st.expander("🛡️ Security & Supabase RLS — Run this SQL in Supabase"):
    st.markdown("**Step 1 — Add audit columns** (run once after deploying this version):")
    st.code("""
-- Add audit/quality tracking columns to usage_logs
ALTER TABLE usage_logs ADD COLUMN IF NOT EXISTS valid_input    boolean DEFAULT true;
ALTER TABLE usage_logs ADD COLUMN IF NOT EXISTS ai_called      boolean DEFAULT true;
ALTER TABLE usage_logs ADD COLUMN IF NOT EXISTS response_valid boolean DEFAULT true;
""", language="sql")
    st.markdown("**Step 2 — Enable Row Level Security** — prevents students from reading others' data:")
    st.code("""
-- Enable RLS on both tables
ALTER TABLE registrations ENABLE ROW LEVEL SECURITY;
ALTER TABLE usage_logs    ENABLE ROW LEVEL SECURITY;

-- Allow INSERT only (anon key can write but not read)
CREATE POLICY "insert_only_reg"
  ON registrations FOR INSERT TO anon WITH CHECK (true);

CREATE POLICY "insert_only_log"
  ON usage_logs FOR INSERT TO anon WITH CHECK (true);

-- Block all SELECT for anon (admin reads via service_role key)
-- No SELECT policy = no read access for anon key
""", language="sql")
    st.warning("⚠️ After enabling RLS, use `SUPABASE_SERVICE_KEY` (not anon key) in admin dashboard to read data.")

# ── Functionality checklist ───────────────────────────────────────────────────

with st.expander("✅ Functionality Testing Checklist"):
    st.markdown("""
| # | Test | How to Verify |
|---|------|---------------|
| 1 | Registration working | Open AI Tutor → registration form should appear → submit → check Supabase `registrations` table |
| 2 | Usage logging working | After AI response → check `usage_logs` table for new row |
| 3 | Admin login works | Password from `ADMIN_PASSWORD` secret |
| 4 | Date filter works | Change period → KPIs should update |
| 5 | Charts show data | After 1+ registrations + queries |
| 6 | CSV download works | Click download buttons |
| 7 | Rate limit works | Make 20+ requests → warning should appear |
| 8 | App survives Supabase down | Kill SUPABASE_KEY → app should still load (just no logging) |
| 9 | Impact report generates | Click Preview Impact Report expander |
| 10 | Branding visible | Each page should show NIC Raisen banner |
""")

# ── Connection test ───────────────────────────────────────────────────────────

st.divider()
st.markdown("### 🔌 Live Connection Test")
if st.button("Run Test (inserts 1 dummy row in each table)", use_container_width=True):
    with st.spinner("Testing..."):
        res = run_connection_test()
    col1, col2 = st.columns(2)
    col1.metric("registrations", "✅ OK" if res["registration"] else "❌ FAIL")
    col2.metric("usage_logs",    "✅ OK" if res["usage_log"]    else "❌ FAIL")
    if res["error"]:
        st.error(res["error"])
    else:
        st.success("Connection working!")
        rows = _sb_get("registrations", limit=3)
        if rows:
            st.dataframe(pd.DataFrame(rows)[["created_at","name","class","school_name","district"]],
                         hide_index=True, use_container_width=True)

# ── Raw data debug ───────────────────────────────────────────────────────────

st.divider()
with st.expander("🐞 Raw Supabase Data — Debug View"):
    st.caption("Direct fetch bypassing DataFrame parsing and date filter. "
               "If rows appear here but not in the dashboard, the issue is in parsing/filtering.")

    # Show any Supabase read error surfaced by _sb_get
    sb_err = st.session_state.pop("_sb_read_error", None)
    if sb_err:
        st.error(f"🔴 Supabase read error: {sb_err}")
        st.info("If you see a 401/403 here, add `SUPABASE_SERVICE_KEY` to Streamlit Secrets "
                "(Supabase Dashboard → Settings → API → service_role key).")

    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown(f"**registrations** — {len(regs)} rows fetched")
        if regs:
            st.dataframe(pd.DataFrame(regs), use_container_width=True, hide_index=True)
        else:
            st.warning("0 rows. Check SUPABASE_URL, SUPABASE_KEY (and SUPABASE_SERVICE_KEY if RLS is on).")
    with col_b:
        st.markdown(f"**usage_logs** — {len(usage)} rows fetched")
        if usage:
            st.dataframe(pd.DataFrame(usage), use_container_width=True, hide_index=True)
        else:
            st.warning("0 rows. Check secrets, then click 'Run Connection Test' above.")

st.markdown("""
<div style="text-align:center;padding:14px 0 8px;color:#777;
            font-size:0.78rem;border-top:1px solid #e0e0e0;margin-top:28px;">
  An initiative by <strong>District Administration Raisen</strong> | NIC MP | 🇮🇳 Digital India
</div>""", unsafe_allow_html=True)
