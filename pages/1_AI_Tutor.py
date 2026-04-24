import streamlit as st
from utils import (require_api_key, show_api_error, ensure_registered,
                   log_usage, show_gov_banner, show_gov_footer,
                   check_rate_limit, show_disclaimer)
from validation import CLASSES, SUBJECTS, validate_input, check_response_contamination
from ai_engine import stream_content, InvalidTopicError

st.set_page_config(page_title="AI Tutor - Padhai AI", page_icon="🤖", layout="wide")

MAX_HISTORY = 6

# ── UI ────────────────────────────────────────────────────────────────────────

show_gov_banner()
st.markdown("# 🤖 AI Tutor (AI Shikshak)")
st.markdown("Koi bhi sawal pucho — AI step-by-step samjhayega!")
st.divider()

with st.sidebar:
    st.markdown("### Apni Details Bharo")
    selected_class   = st.selectbox("Apni Class Chuniye", CLASSES, index=4)
    selected_subject = st.selectbox("Subject Chuniye", SUBJECTS[selected_class])
    medium           = st.radio("Medium", ["Hindi Medium", "English Medium"])
    st.divider()
    if st.button("🗑️ Chat Clear Karo", use_container_width=True):
        st.session_state.tutor_messages = []
        st.rerun()
    st.divider()
    st.markdown("**Tips:**\n- Sawal clearly likhein\n- Chapter bhi batayein\n- 'Aur explain karo' bol sakte ho")

if not require_api_key():
    st.stop()
if not ensure_registered():
    st.stop()

if "tutor_messages" not in st.session_state:
    st.session_state.tutor_messages = []

# Display chat history
for msg in st.session_state.tutor_messages:
    avatar = "🧑‍🎓" if msg["role"] == "user" else "🤖"
    with st.chat_message(msg["role"], avatar=avatar):
        st.markdown(msg["content"])

if not st.session_state.tutor_messages:
    st.markdown("**Suggested Sawale:**")
    suggestions = {
        "Mathematics": ["Pythagoras theorem kya hai?", "Quadratic equation solve kaise karte hain?", "Trigonometry ke basic formulas kya hain?"],
        "Science":     ["Photosynthesis kya hoti hai?", "Newton ke teen laws explain karo", "Atom aur molecule mein kya farak hai?"],
        "Physics":     ["Newton ke laws of motion explain karo", "Ohm's law kya hai?", "Refraction of light kya hota hai?"],
        "Chemistry":   ["Periodic table kya hai?", "Acid aur base mein kya farak hai?", "Chemical bonding explain karo"],
        "Biology":     ["Cell kya hoti hai?", "Photosynthesis ka process explain karo", "DNA kya hota hai?"],
        "Hindi":       ["Samas kya hota hai? Uske prakar batao", "Ras kise kehte hain?", "Kriya ke bhed batao"],
        "History":     ["1857 ki kranti ke karan kya the?", "Mughal samrajya kab sthapit hua?", "Gandhi ji ka yogdan batao"],
        "English":     ["What is a figure of speech?", "Explain active and passive voice", "What are types of sentences?"],
    }.get(selected_subject, ["Aaj ka topic kya padhna hai?", "Is subject mein kya mushkil lag raha hai?", "Koi formula samajhna hai?"])
    cols = st.columns(3)
    for i, q in enumerate(suggestions[:3]):
        if cols[i].button(q, use_container_width=True, key=f"sug_{i}"):
            st.session_state.tutor_messages.append({"role": "user", "content": q})
            st.rerun()

if prompt := st.chat_input(f"Apna sawal likhein... ({selected_class} | {selected_subject})"):
    # Validate: sanitise query; max 800 chars for conversational questions
    valid, err = validate_input(selected_subject, prompt, selected_class, max_len=800)
    if not valid:
        st.error(f"❌ {err}")
        log_usage("AI Tutor", selected_subject, prompt[:80],
                  valid_input=False, ai_called=False, response_valid=False)
        st.stop()

    if not check_rate_limit():
        st.stop()

    st.session_state.tutor_messages.append({"role": "user", "content": prompt})
    with st.chat_message("user", avatar="🧑‍🎓"):
        st.markdown(prompt)

    # Build trimmed history for the AI (includes the message we just appended)
    history = [
        {"role": m["role"], "content": m["content"]}
        for m in st.session_state.tutor_messages[-MAX_HISTORY:]
    ]

    with st.chat_message("assistant", avatar="🤖"):
        placeholder = st.empty()
        full_text = ""
        response_valid = True
        try:
            for chunk in stream_content(
                cls=selected_class, subject=selected_subject,
                topic=prompt, medium=medium, feature="AI Tutor",
                history=history, max_tokens=800,
            ):
                full_text += chunk
                placeholder.markdown(full_text + "▌")
            placeholder.markdown(full_text)

            # Soft cross-subject contamination check
            clean, warn = check_response_contamination(selected_subject, full_text)
            if not clean:
                response_valid = False
                st.caption(f"⚠️ {warn}")

            show_disclaimer()
            show_gov_footer()
        except InvalidTopicError as e:
            placeholder.empty()
            st.error(f"❌ {e}")
            response_valid = False
        except Exception as e:
            show_api_error(e)
            response_valid = False

        log_usage("AI Tutor", selected_subject, prompt[:80],
                  valid_input=True, ai_called=True, response_valid=response_valid)

    if full_text:
        st.session_state.tutor_messages.append({"role": "assistant", "content": full_text})
