# 📚 Padhai AI — MP Board School Study Platform

AI-powered study platform for MP Board students (Class 6–12). Completely **free to run** using Groq API + Streamlit Community Cloud + Supabase.

**Features:** AI Tutor | MCQ Quiz | Study Notes | Important Questions  
**Languages:** Hindi + English Medium  
**Subjects:** All MP Board subjects, Class 6–12  
**Initiative:** District Administration Raisen | NIC (National Informatics Centre) MP

---

## ⚡ Total Cost = ₹0

| Service | Free Limit | Cost |
|---------|-----------|------|
| Groq API (`llama-3.3-70b-versatile`) | 30 req/min, 6000 tokens/min (free tier) | **FREE** |
| Streamlit Community Cloud (hosting) | Unlimited public apps | **FREE** |
| Supabase (database) | 500 MB, 50,000 rows | **FREE** |
| GitHub | Free for public repos | **FREE** |

---

## 🔑 Step 1 — Free Groq API Key lena

1. **Groq Console** pe jao: `https://console.groq.com`
2. **Sign up / Login** karo
3. **"API Keys"** → **"Create API Key"** dabao
4. Key copy karo — aise dikhegi: `gsk_XXXXXXXXXXXXXXXXXXXX`

> Koi credit card nahi chahiye. No billing. Completely free.

---

## 🗄️ Step 2 — Supabase Setup (Optional but recommended for analytics)

1. `https://supabase.com` pe free account banao
2. **"New project"** create karo
3. SQL Editor mein ye run karo:

```sql
-- Student registrations
CREATE TABLE registrations (
  id          bigserial PRIMARY KEY,
  created_at  timestamptz DEFAULT now(),
  name        text,
  class       text,
  school_name text,
  district    text,
  session_id  text
);

-- Usage / analytics logs
CREATE TABLE usage_logs (
  id             bigserial PRIMARY KEY,
  created_at     timestamptz DEFAULT now(),
  user_name      text,
  user_class     text,
  school_name    text,
  district       text,
  feature        text,
  subject        text,
  topic          text,
  session_id     text,
  valid_input    boolean DEFAULT true,
  ai_called      boolean DEFAULT true,
  response_valid boolean DEFAULT true
);

-- Enable RLS (Row Level Security)
ALTER TABLE registrations ENABLE ROW LEVEL SECURITY;
ALTER TABLE usage_logs    ENABLE ROW LEVEL SECURITY;

-- Allow anonymous INSERT only (students write, can't read others' data)
CREATE POLICY "insert_only_reg" ON registrations FOR INSERT TO anon WITH CHECK (true);
CREATE POLICY "insert_only_log" ON usage_logs    FOR INSERT TO anon WITH CHECK (true);
```

4. **Settings → API** mein note karo:
   - `URL` (e.g. `https://xxxx.supabase.co`)
   - `anon public` key → `SUPABASE_KEY`
   - `service_role` key → `SUPABASE_SERVICE_KEY` (admin dashboard reads)

---

## 🚀 Step 3 — Streamlit Community Cloud pe Deploy karna

### 3a. Streamlit Cloud pe account banao

1. `https://share.streamlit.io` pe jao
2. **"Sign in with GitHub"** — GitHub account se login karo

### 3b. App deploy karo

1. **"New app"** button dabao

2. Fill karo:
   ```
   Repository:  deependrakatiyar/padhai-ai
   Branch:      main
   Main file:   app.py
   ```

3. **"Advanced settings"** → **"Secrets"** tab mein ye add karo:
   ```toml
   GROQ_API_KEY        = "gsk_XXXXXXXXXXXXXXXXXXXX"

   # Supabase (optional — app works without it, just no analytics)
   SUPABASE_URL        = "https://xxxx.supabase.co"
   SUPABASE_KEY        = "eyJ..."          # anon/public key
   SUPABASE_SERVICE_KEY = "eyJ..."         # service_role key (for admin dashboard)

   # Admin dashboard password (required — no default fallback)
   ADMIN_PASSWORD      = "your-strong-password"
   ```

4. **"Deploy!"** dabao → 2-3 minute mein app live!

---

## 💻 Local Machine pe Run karna (Testing)

```bash
# 1. Clone karo
git clone https://github.com/deependrakatiyar/padhai-ai.git
cd padhai-ai

# 2. Install karo
pip install -r requirements.txt

# 3. Secrets file banao
mkdir -p .streamlit
cat > .streamlit/secrets.toml << 'EOF'
GROQ_API_KEY         = "gsk_XXXXXXXXXXXXXXXXXXXX"
SUPABASE_URL         = "https://xxxx.supabase.co"
SUPABASE_KEY         = "eyJ..."
SUPABASE_SERVICE_KEY = "eyJ..."
ADMIN_PASSWORD       = "your-strong-password"
EOF

# 4. Run karo
streamlit run app.py
```

Browser mein khulega: `http://localhost:8501`

---

## 📁 File Structure

```
padhai-ai/
├── app.py                          ← Home page
├── ai_engine.py                    ← Groq API wrapper (NCERT-aligned prompts)
├── utils.py                        ← Supabase, auth, rate limiting, branding
├── validation.py                   ← Input safety & cross-subject checks
├── requirements.txt                ← Python dependencies
├── runtime.txt                     ← Python version pin
├── README.md                       ← This file
├── LICENSE                         ← MIT License
└── pages/
    ├── 1_AI_Tutor.py               ← Chat with AI tutor
    ├── 2_Quiz.py                   ← MCQ Practice
    ├── 3_Notes.py                  ← Study Notes generator
    ├── 4_Important_Questions.py    ← Board exam questions
    └── 5_Admin_Dashboard.py        ← Analytics (admin only)
```

---

## ✅ Testing Checklist

App run hone ke baad ye test karo:

- [ ] Home page khulta hai
- [ ] Registration form aata hai (first visit on any feature page)
- [ ] **AI Tutor** — sawal pucho, jawab aaye
- [ ] **Quiz** — Class 10 > Science > "Electricity" > 5 questions generate karo
- [ ] **Notes** — Class 10 > Science > "Electricity" > Summary Notes generate karo
- [ ] **Important Questions** — Class 10 > Science > "Electricity" > All Types
- [ ] Hindi medium select karo — Hindi mein jawab aaye
- [ ] Rate limit: 20 requests ke baad warning aaye
- [ ] Admin Dashboard: `ADMIN_PASSWORD` se login ho

---

## ❓ Common Problems

| Problem | Solution |
|---------|----------|
| `GROQ_API_KEY not found` | Key sahi se set karo in secrets.toml / Streamlit Cloud Secrets |
| `Rate limit` error | Groq free tier ka limit — thodi der baad retry karo |
| `Quiz JSON error` | Topic thoda alag likhke retry karo |
| Admin page: "ADMIN_PASSWORD not configured" | Set `ADMIN_PASSWORD` in Streamlit Secrets |
| Supabase 0 rows in admin | Add `SUPABASE_SERVICE_KEY` — RLS bypass ke liye service_role key chahiye |
| Streamlit Cloud deploy fail | Secrets mein keys add ki? Format check karo |

---

## 🔒 Security Notes

- Students enter their own Groq API key in the sidebar (optional — admin can pre-set one)
- Student PII (name, school, district) is stored in Supabase under RLS
- Admin dashboard requires a strong password set via `ADMIN_PASSWORD` secret
- All AI output is validated for cross-subject contamination before display
