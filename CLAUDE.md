# Padhai AI — Developer Context for Claude

## What this project is

Padhai AI is a free AI-powered study platform for **MP Board school students (Class 6–12)**, built as a government initiative by **District Administration Raisen | NIC (National Informatics Centre) Madhya Pradesh** under Digital India. It provides an AI Tutor, MCQ Quiz, Study Notes, and Important Questions — all aligned to the NCERT/MP Board curriculum.

The platform serves real school children and carries government branding. Security, privacy (DPDP Act 2023 — India's data protection law for minors), and content accuracy are non-negotiable requirements.

---

## Tech stack

| Layer | Technology |
|-------|-----------|
| App framework | Streamlit 1.36+ (multipage app) |
| AI model | Groq SDK — `llama-3.3-70b-versatile` |
| Database | Supabase (PostgreSQL via REST API — no ORM, raw HTTP) |
| Language | Python 3.11.9 |
| Hosting | Streamlit Community Cloud |

---

## Project structure

```
padhai-ai/
├── app.py                       # Home page only — no AI calls here
├── ai_engine.py                 # ALL Groq calls go through here
├── utils.py                     # Supabase client, auth, rate limiting, branding, registration
├── validation.py                # Input sanitisation and cross-subject safety checks
├── pages/
│   ├── 1_AI_Tutor.py            # Multi-turn chat tutor
│   ├── 2_Quiz.py                # MCQ generation + graded review
│   ├── 3_Notes.py               # Streaming study notes
│   ├── 4_Important_Questions.py # Board exam question lists
│   └── 5_Admin_Dashboard.py     # Analytics — password-protected, admin only
├── requirements.txt
├── runtime.txt                  # python-3.11.9
└── .devcontainer/devcontainer.json
```

---

## Running locally

```bash
pip install -r requirements.txt

# Create secrets file
mkdir -p .streamlit
cat > .streamlit/secrets.toml << 'EOF'
GROQ_API_KEY         = "gsk_..."          # required
SUPABASE_URL         = "https://xxxx.supabase.co"   # optional
SUPABASE_KEY         = "eyJ..."           # optional (anon key)
SUPABASE_SERVICE_KEY = "eyJ..."           # optional (service_role — admin reads)
ADMIN_PASSWORD       = "your-password"   # required for admin dashboard
EOF

streamlit run app.py
```

The app works without Supabase — AI features function, but registrations and usage logs are silently dropped.

---

## Architecture rules — read before touching any AI or data flow

### 1. All AI calls must go through `ai_engine.py`

Never call the Groq SDK directly from a page. `ai_engine.py` enforces:
- NCERT/MP Board system prompt on every call
- `InvalidTopicError` detection (model's `INVALID INPUT` refusal marker)
- Retry/backoff (`_call_with_retry`) for 429/5xx/connection errors
- 40-char buffer in `stream_content` so refusals are caught before any text reaches the UI

```python
# Correct
from ai_engine import stream_content, generate_json, InvalidTopicError

# Never do this from a page
from groq import Groq; Groq(api_key=...).chat.completions.create(...)
```

### 2. Validation pipeline must run before every AI call

Every page follows this gate sequence before calling `ai_engine.py`:

```
validate_input()          # length, unsafe chars, class-subject alignment
    ↓
check_topic_relevance()   # keyword blocklist — stops cross-domain topics
    ↓
check_rate_limit()        # client-side fast check + server-side Supabase sync on first call
    ↓
ai_engine call
    ↓
check_response_contamination()  # soft post-response cross-subject scan
```

Never skip or reorder these gates.

### 3. All AI-generated content must be HTML-escaped before `unsafe_allow_html=True`

```python
import html as _html
q_text = _html.escape(str(q.get("question", "")))
# then inject q_text into the HTML string
```

Raw AI output in an `unsafe_allow_html` block is an XSS vulnerability.

### 4. Admin dashboard is strictly isolated

- `ADMIN_PASSWORD` must come from `st.secrets` — never add a fallback default
- Use `hmac.compare_digest()` for password comparison
- Check `st.session_state.get("admin_auth")` at the top of any admin-only code
- The dashboard reads Supabase via `SUPABASE_SERVICE_KEY` (bypasses RLS); students write via `SUPABASE_KEY` (anon, insert-only under RLS)

### 5. Registration gating

Every feature page calls `ensure_registered()` before showing content. This displays the registration form (with DPDP consent checkbox) on first visit, stores `user_info` in session state, and POSTs to Supabase `registrations`. Do not add features that bypass this.

---

## Key modules — what lives where

### `ai_engine.py`
- `InvalidTopicError` — raised when model returns `INVALID INPUT`
- `stream_content()` — streaming generator for Tutor/Notes/IQ; buffers first 40 chars to detect refusals
- `generate_json()` — non-streaming for Quiz; uses `response_format={"type":"json_object"}`
- `_call_with_retry()` — wraps `.create()` calls with exponential backoff

### `utils.py`
- `_secret(key)` — reads from `st.secrets` then `os.environ`; returns `""` on miss (never raises)
- `_sb_post(table, data)` — fire-and-forget Supabase write; swallows all errors (analytics must not crash features)
- `_sb_get(table)` — Supabase read via service_role key; used only by admin dashboard
- `check_rate_limit()` — client-side counter (fast) + server-side count from `usage_logs` on session start
- `_server_request_count(session_id)` — counts today's `ai_called=true` rows for this session; fails open
- `ensure_registered()` — registration gate with DPDP consent checkbox
- `log_usage(feature, subject, topic, ...)` — must be called after every AI attempt (success or failure)
- `show_api_error(e)` — classifies Groq errors; never call `st.rerun()` after showing error

### `validation.py`
- `CLASS_SUBJECTS` — authoritative subject list per class; this is the source of truth
- `_UNSAFE` — regex blocking `<>{}|\`` in topic input (`$` and `;` are intentionally allowed for Math)
- `check_topic_relevance(subject, topic)` — hard block, 1 keyword hit = blocked
- `check_response_contamination(subject, response)` — soft check, requires 2+ hits to warn

---

## Supabase schema

```sql
-- registrations
id, created_at, name, class, school_name, district, session_id

-- usage_logs
id, created_at, user_name, user_class, school_name, district,
feature, subject, topic, session_id,
valid_input (bool), ai_called (bool), response_valid (bool)
```

RLS policy: anon key can INSERT only. Admin reads via service_role key.

`_sb_get` uses `limit=5000` (no pagination). For very large deployments this will truncate.

---

## Rate limiting

- **Client-side**: `st.session_state.request_count`, limit = `MAX_REQUESTS_PER_SESSION` (20)
- **Server-side**: On the first request of a session, `_server_request_count()` queries today's `ai_called=true` rows in `usage_logs` for this `session_id` and syncs the client counter. Fails open (returns 0) if Supabase is slow.
- Known limitation: session_id is regenerated on re-registration (refresh + new tab). Rate limit per session_id does not survive re-registration.

---

## Content safety constraints

This platform serves school children (Class 6–12) under a government banner. When working on prompts or validation:

- The system prompt instructs the model to respond `INVALID INPUT` for off-topic requests — `ai_engine.py` detects this and raises `InvalidTopicError`
- Do not weaken or remove the subject/class assignment in `_SYSTEM_TEMPLATE`
- Do not reduce the `_TOPIC_CROSS_SIGNALS` or `_CROSS_SIGNALS` lists in `validation.py`
- All error messages shown to students are in Hindi (Hinglish) — keep new messages consistent

---

## Privacy & compliance

- Student PII collected: name, school name, district, class
- Consent checkbox is mandatory before registration (DPDP Act 2023)
- Data is stored in Supabase; not shared with third parties
- Do not add any analytics, tracking, or third-party SDKs without reviewing DPDP implications
- The platform explicitly targets minors — extra care required for any data handling changes

---

## Common development tasks

**Adding a new subject:**
1. Add to `CLASS_SUBJECTS` in `validation.py` (authoritative source)
2. Add cross-signal keywords to `_CROSS_SIGNALS` and `_TOPIC_CROSS_SIGNALS` in `validation.py`
3. Add suggestion questions in `pages/1_AI_Tutor.py`

**Adding a new feature page:**
1. Create `pages/N_FeatureName.py`
2. Call `require_api_key()`, `ensure_registered()`, `check_rate_limit()` before any AI call
3. Catch `InvalidTopicError` before the generic `Exception` handler
4. Call `log_usage()` on every AI attempt path (success and failure)
5. Escape all AI output with `html.escape()` before injecting into `unsafe_allow_html` blocks

**Changing the AI model:**
Update `MODEL` in `utils.py`. The model name is used in both `stream_content` and `generate_json`.

**Deploying:**
Push to `main` on `deependrakatiyar/padhai-ai` — Streamlit Community Cloud auto-deploys.
