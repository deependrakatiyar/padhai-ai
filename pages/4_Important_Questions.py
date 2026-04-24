import streamlit as st
from utils import (require_api_key, show_api_error, ensure_registered,
                   log_usage, show_gov_banner, check_rate_limit, show_disclaimer)
from validation import (CLASSES, SUBJECTS, validate_input,
                        check_topic_relevance, check_response_contamination)
from ai_engine import stream_content, InvalidTopicError

st.set_page_config(page_title="Important Questions - Padhai AI", page_icon="⭐", layout="wide")

QUESTION_TYPES = {
    "All Types (Sabhi)":              "Include all types: 1-mark, 2-mark, 3-mark, 5-mark, and essay questions",
    "1 Mark (Objective)":             "Very short answer — definitions, fill in the blanks, true/false",
    "2-3 Mark (Short Answer)":        "Short answer questions requiring 2-4 sentence answers",
    "4-5 Mark (Long Answer)":         "Detailed questions requiring paragraph answers",
    "Essay / Nibandh (6-8 Marks)":    "Long essay type questions for Hindi and language subjects",
    "Numerical / Practical Problems": "Calculation-based and application problems (for Science, Math)",
}
_Q_INSTRUCTIONS = {
    "All Types (Sabhi)":              "mix 1-mark, 2-3 mark, 4-5 mark questions",
    "1 Mark (Objective)":             "definitions, one-word, fill in blanks, true/false",
    "2-3 Mark (Short Answer)":        "explain/describe/differentiate type",
    "4-5 Mark (Long Answer)":         "detail with diagram, compare/contrast",
    "Essay / Nibandh (6-8 Marks)":    "essay writing, nibandh",
    "Numerical / Practical Problems": "solve/calculate/application problems",
}

# ── UI ────────────────────────────────────────────────────────────────────────

show_gov_banner()
st.markdown("# ⭐ Important Questions")
st.markdown("MP Board exam mein aane wale most important questions — hints ke saath!")
st.divider()

with st.sidebar:
    st.markdown("### Question Settings")
    selected_class   = st.selectbox("Class", CLASSES, index=4)
    selected_subject = st.selectbox("Subject", SUBJECTS[selected_class])
    topic            = st.text_input("Chapter / Topic", placeholder="e.g., Electricity, Mughal Empire")
    q_type           = st.selectbox("Question Type", list(QUESTION_TYPES.keys()))
    medium           = st.radio("Medium", ["Hindi Medium", "English Medium"])
    generate_btn     = st.button("⭐ Questions Generate Karo!", use_container_width=True, type="primary")
    st.divider()
    st.markdown(f"**Selected:** {QUESTION_TYPES[q_type]}")
    st.divider()
    st.markdown("**Legend:**\n⭐ Important\n⭐⭐ Very Important\n⭐⭐⭐ Most Important")

if not require_api_key():
    st.stop()
if not ensure_registered():
    st.stop()

if "iq_content" not in st.session_state: st.session_state.iq_content = ""
if "iq_config"   not in st.session_state: st.session_state.iq_config  = {}

if generate_btn:
    # Gate 1: basic sanitisation
    valid, err = validate_input(selected_subject, topic, selected_class)
    if not valid:
        st.error(f"❌ {err}")
        log_usage("Important Questions", selected_subject, topic,
                  valid_input=False, ai_called=False, response_valid=False)
    else:
        # Gate 2: topic-domain relevance (blocks e.g. Sanskrit + quadratic equation)
        rel_ok, rel_err = check_topic_relevance(selected_subject, topic)
        if not rel_ok:
            st.error(f"❌ {rel_err}")
            log_usage("Important Questions", selected_subject, topic,
                      valid_input=False, ai_called=False, response_valid=False)
        elif not check_rate_limit():
            pass
        else:
            st.session_state.iq_config  = {"class": selected_class, "subject": selected_subject,
                                            "topic": topic, "type": q_type, "medium": medium}
            st.session_state.iq_content = ""
            col1, col2, col3 = st.columns(3)
            col1.metric("Class", selected_class)
            col2.metric("Subject", selected_subject)
            col3.metric("Type", q_type.split("(")[0].strip())
            st.markdown(f"**Topic:** {topic} | **Medium:** {medium}")
            st.divider()
            placeholder = st.empty()
            full_text   = ""
            response_valid = True
            try:
                with st.spinner("Important questions dhundhe ja rahe hain..."):
                    for chunk in stream_content(
                        cls=selected_class, subject=selected_subject,
                        topic=topic, medium=medium, feature="Important Questions",
                        extra={"q_type": q_type,
                               "type_instruction": _Q_INSTRUCTIONS.get(q_type, "")},
                        max_tokens=1200,
                    ):
                        full_text += chunk
                        placeholder.markdown(full_text + "▌")
                placeholder.markdown(full_text)

                clean, warn = check_response_contamination(selected_subject, full_text)
                if not clean:
                    response_valid = False
                    st.warning(f"⚠️ {warn}")
            except InvalidTopicError as e:
                st.error(f"❌ {e}")
                response_valid = False
                log_usage("Important Questions", selected_subject, topic,
                          valid_input=False, ai_called=True, response_valid=False)
                st.stop()
            except Exception as e:
                show_api_error(e)
                response_valid = False
                st.stop()

            st.session_state.iq_content = full_text
            log_usage("Important Questions", selected_subject, topic,
                      valid_input=True, ai_called=True, response_valid=response_valid)
            show_disclaimer()
            st.divider()
            col1, col2 = st.columns(2)
            col1.success("✅ Questions ready!")
            col2.download_button("⬇️ Download (.txt)", data=full_text,
                                 file_name=f"{selected_class}_{selected_subject}_{topic}_questions.txt",
                                 mime="text/plain", use_container_width=True)

elif st.session_state.iq_content:
    cfg = st.session_state.iq_config
    col1, col2, col3 = st.columns(3)
    col1.metric("Class", cfg["class"])
    col2.metric("Subject", cfg["subject"])
    col3.metric("Type", cfg["type"].split("(")[0].strip())
    st.markdown(f"**Topic:** {cfg['topic']} | **Medium:** {cfg['medium']}")
    st.divider()
    st.markdown(st.session_state.iq_content)
    st.divider()
    st.download_button("⬇️ Download (.txt)", data=st.session_state.iq_content,
                       file_name=f"{cfg['class']}_{cfg['subject']}_{cfg['topic']}_questions.txt",
                       mime="text/plain", use_container_width=True)
else:
    st.info("👈 Left sidebar mein class, subject, topic fill karo aur **Questions Generate Karo** button dabao!")
    st.markdown("### Board Exam Tips")
    tips = [
        ("📅", "Timetable Banao", "Har subject ko equal time do."),
        ("📖", "NCERT Pehle Padho", "MP Board mein 80% questions NCERT se aate hain."),
        ("✍️", "Likhkar Practice Karo", "Exam mein likhna hota hai, practice writing karein."),
        ("🔄", "Revision Zaruri Hai", "Spaced repetition se yaad zyada rehta hai."),
        ("📝", "Previous Papers", "Pichle 5 saal ke papers solve karo."),
        ("😴", "Neend Poori Lo", "Exam se pehle achi neend lo."),
    ]
    cols = st.columns(3)
    for i, (icon, title, desc) in enumerate(tips):
        with cols[i % 3]:
            st.markdown(f"""
            <div style="background:#e8f5e9; border-radius:12px; padding:16px; margin-bottom:12px; border-left:4px solid #2e7d32;">
                <h4 style="color:#1b5e20; margin:0 0 6px;">{icon} {title}</h4>
                <p style="color:#444; font-size:0.88rem; margin:0;">{desc}</p>
            </div>
            """, unsafe_allow_html=True)
