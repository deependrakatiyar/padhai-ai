import streamlit as st
from utils import (require_api_key, show_api_error, ensure_registered,
                   log_usage, show_gov_banner, check_rate_limit, show_disclaimer)
from validation import (CLASSES, SUBJECTS, validate_input,
                        check_topic_relevance, check_response_contamination)
from ai_engine import stream_content, InvalidTopicError

st.set_page_config(page_title="Study Notes - Padhai AI", page_icon="📝", layout="wide")

NOTE_TYPES = {
    "Summary Notes (Saar)":      "Concise chapter summary with key points",
    "Detailed Notes (Vistrit)":  "Comprehensive notes with explanations and examples",
    "Formula Sheet (Sutre)":     "All formulas, definitions, and key terms",
    "Revision Notes (Revision)": "Quick revision bullet points for last-minute prep",
    "Mind Map (Diagram Style)":  "Topic breakdown in hierarchical structure",
}
_NOTE_INSTRUCTIONS = {
    "Summary Notes (Saar)":      "Concise 300-400 word summary covering all major concepts",
    "Detailed Notes (Vistrit)":  "Comprehensive notes with explanations, examples, sub-topics (600-800 words)",
    "Formula Sheet (Sutre)":     "Only formulas, definitions, key terms — use tables where helpful",
    "Revision Notes (Revision)": "Bullet-point revision notes, 1-line each, exam-focused",
    "Mind Map (Diagram Style)":  "Hierarchical text mind map using indentation and symbols",
}

# ── UI ────────────────────────────────────────────────────────────────────────

show_gov_banner()
st.markdown("# 📝 Study Notes Generator")
st.markdown("Kisi bhi chapter ke AI-powered notes instant banao — board exam ke liye!")
st.divider()

with st.sidebar:
    st.markdown("### Notes Settings")
    selected_class   = st.selectbox("Class", CLASSES, index=4)
    selected_subject = st.selectbox("Subject", SUBJECTS[selected_class])
    topic            = st.text_input("Chapter / Topic", placeholder="e.g., Electricity, French Revolution")
    note_type        = st.selectbox("Notes ka Type", list(NOTE_TYPES.keys()))
    medium           = st.radio("Medium", ["Hindi Medium", "English Medium"])
    generate_btn     = st.button("📝 Notes Banao!", use_container_width=True, type="primary")
    st.divider()
    st.markdown(f"**Selected:** {NOTE_TYPES[note_type]}")

if not require_api_key():
    st.stop()
if not ensure_registered():
    st.stop()

if "notes_content" not in st.session_state: st.session_state.notes_content = ""
if "notes_config"  not in st.session_state: st.session_state.notes_config  = {}

if generate_btn:
    # Gate 1: basic sanitisation
    valid, err = validate_input(selected_subject, topic, selected_class)
    if not valid:
        st.error(f"❌ {err}")
        log_usage("Notes", selected_subject, topic,
                  valid_input=False, ai_called=False, response_valid=False)
    else:
        # Gate 2: topic-domain relevance
        rel_ok, rel_err = check_topic_relevance(selected_subject, topic)
        if not rel_ok:
            st.error(f"❌ {rel_err}")
            log_usage("Notes", selected_subject, topic,
                      valid_input=False, ai_called=False, response_valid=False)
        elif not check_rate_limit():
            pass
        else:
            st.session_state.notes_config  = {"class": selected_class, "subject": selected_subject,
                                               "topic": topic, "type": note_type, "medium": medium}
            st.session_state.notes_content = ""
            st.markdown(f"### {selected_class} | {selected_subject} | {topic}")
            st.markdown(f"**{note_type}** | {medium}")
            st.divider()
            placeholder = st.empty()
            full_text   = ""
            response_valid = True
            try:
                with st.spinner("Notes generate ho rahi hain..."):
                    for chunk in stream_content(
                        cls=selected_class, subject=selected_subject,
                        topic=topic, medium=medium, feature="Notes",
                        extra={"note_type_instruction": _NOTE_INSTRUCTIONS[note_type]},
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
                log_usage("Notes", selected_subject, topic,
                          valid_input=False, ai_called=True, response_valid=False)
                st.stop()
            except Exception as e:
                show_api_error(e)
                response_valid = False
                st.stop()

            st.session_state.notes_content = full_text
            log_usage("Notes", selected_subject, topic,
                      valid_input=True, ai_called=True, response_valid=response_valid)
            show_disclaimer()
            st.divider()
            st.success("✅ Notes ready!")
            st.download_button("⬇️ Notes Download Karo (.txt)", data=full_text,
                               file_name=f"{selected_class}_{selected_subject}_{topic}_notes.txt",
                               mime="text/plain", use_container_width=True)

elif st.session_state.notes_content:
    cfg = st.session_state.notes_config
    st.markdown(f"### {cfg['class']} | {cfg['subject']} | {cfg['topic']}")
    st.markdown(f"**{cfg['type']}** | {cfg['medium']}")
    st.divider()
    st.markdown(st.session_state.notes_content)
    st.divider()
    st.download_button("⬇️ Notes Download Karo (.txt)", data=st.session_state.notes_content,
                       file_name=f"{cfg['class']}_{cfg['subject']}_{cfg['topic']}_notes.txt",
                       mime="text/plain", use_container_width=True)
else:
    st.info("👈 Left sidebar mein class, subject, topic aur notes type choose karo, phir **Notes Banao** dabao!")
    st.markdown("### Notes ke Types")
    cols = st.columns(2)
    for i, (name, desc) in enumerate(NOTE_TYPES.items()):
        with cols[i % 2]:
            st.markdown(f"""
            <div style="background:#f3e5f5; border-radius:10px; padding:14px; margin-bottom:12px; border-left:4px solid #7b1fa2;">
                <strong>{name}</strong><br><span style="color:#555; font-size:0.9rem;">{desc}</span>
            </div>
            """, unsafe_allow_html=True)
