"""
Padhai AI — Centralized NCERT-Aligned AI Engine.
All AI calls go through this module to enforce academic correctness.
"""
import re as _re
import time
from typing import Optional, Generator
from utils import MODEL, get_client

_MAX_RETRIES = 3
_BACKOFF_BASE = 2  # seconds; wait = BACKOFF_BASE ** attempt, capped at 30s

_TRANSIENT_CODES = ("429", "500", "502", "503", "504")
_TRANSIENT_KEYWORDS = ("rate_limit", "connection", "timeout", "overloaded")


def _is_transient(err: str) -> bool:
    return any(c in err for c in _TRANSIENT_CODES) or \
           any(k in err.lower() for k in _TRANSIENT_KEYWORDS)


def _retry_wait(err: str, attempt: int) -> float:
    """Return seconds to wait before the next attempt."""
    m = _re.search(r'try again in (\d+\.?\d*)s', err)
    return min(float(m.group(1)) + 1 if m else _BACKOFF_BASE ** (attempt + 1), 30)


def _call_with_retry(fn):
    """Call fn() up to _MAX_RETRIES times, backing off on transient errors."""
    for attempt in range(_MAX_RETRIES):
        try:
            return fn()
        except Exception as e:
            err = str(e)
            if not _is_transient(err) or attempt == _MAX_RETRIES - 1:
                raise
            time.sleep(_retry_wait(err, attempt))


class InvalidTopicError(Exception):
    """Raised when the model returns its out-of-scope refusal marker."""
    pass


_INVALID_MARKER = "INVALID INPUT"
_BUFFER_SIZE = 40  # chars buffered before first yield — enough to detect the marker


def _check_invalid(text: str) -> None:
    """Raise InvalidTopicError if the model returned the refusal marker."""
    if text.strip().upper().startswith(_INVALID_MARKER):
        raise InvalidTopicError(
            "Yeh topic is subject ke syllabus mein nahi hai. "
            "Kripya sahi subject aur topic enter karein."
        )

_SYSTEM_TEMPLATE = (
    "You are Padhai AI, an NCERT-certified academic assistant for MP Board students.\n\n"
    "Assignment:\n"
    "  Class  : {cls}\n"
    "  Subject: {subject}\n"
    "  Language: {medium_instruction}\n\n"
    "STRICT RULES:\n"
    "1. Generate content ONLY about {subject} — refuse out-of-subject requests.\n"
    "2. Follow MP Board / NCERT {cls} syllabus strictly; no out-of-syllabus content.\n"
    "3. Do NOT fabricate facts, formulas, dates, or examples not in the curriculum.\n"
    "4. If the topic is completely outside {subject} scope, respond exactly: INVALID INPUT\n"
    "5. Keep all explanations age-appropriate and clear for {cls} students."
)

_FEATURE_INSTRUCTIONS: dict = {
    "AI Tutor": (
        "Explain the following question step-by-step with clear examples.\n"
        "- Bold **key terms** and use `code blocks` for formulas.\n"
        "- Keep the answer focused and concise (max ~500 words).\n"
        "- End with ONE follow-up question to check the student's understanding."
    ),
    "Quiz": (
        "Generate {n} multiple-choice questions (MCQs) for the given topic.\n"
        "Return ONLY valid JSON — no markdown, no extra text:\n"
        '{{"questions":[{{"question":"...","options":{{"A":"...","B":"...","C":"...","D":"..."}},'
        '"correct":"A","explanation":"1-line reason"}}]}}'
    ),
    "Notes": (
        "{note_type_instruction}\n"
        "Format: ## headings, **bold** key terms, `formulas` in code blocks, "
        "tables where useful.\n"
        "End with a '## Yaad Rakho' section listing exactly 5 key takeaways."
    ),
    "Important Questions": (
        "List 12 important MP Board exam questions ({q_type}).\n"
        "Format each exactly as:\n"
        "**Q[N]. [question]** ([marks] marks) [⭐/⭐⭐/⭐⭐⭐]\n"
        "💡 Hint: [1-line exam tip]\n"
        "---"
    ),
}


def _build_messages(cls: str, subject: str, topic: str, medium: str,
                    feature: str, extra: Optional[dict] = None,
                    history: Optional[list] = None) -> list:
    med_instr = (
        "Hindi — write all content in Devanagari script"
        if medium == "Hindi Medium"
        else "English"
    )
    system_content = _SYSTEM_TEMPLATE.format(
        cls=cls, subject=subject, medium_instruction=med_instr
    )

    feat_instr = _FEATURE_INSTRUCTIONS.get(feature, "Provide accurate educational content.")
    if extra:
        try:
            feat_instr = feat_instr.format(**extra)
        except KeyError:
            pass

    user_content = (
        f"Class: {cls}\n"
        f"Subject: {subject}\n"
        f"Topic: {topic}\n\n"
        f"{feat_instr}"
    )

    messages = [{"role": "system", "content": system_content}]
    if history:
        # AI Tutor multi-turn: history already contains the latest user message
        messages.extend(history)
    else:
        messages.append({"role": "user", "content": user_content})
    return messages


def stream_content(cls: str, subject: str, topic: str, medium: str,
                   feature: str = "AI Tutor",
                   extra: Optional[dict] = None,
                   history: Optional[list] = None,
                   max_tokens: int = 1000) -> Generator:
    """
    Streaming generator for AI Tutor, Notes, and Important Questions.
    Buffers the first _BUFFER_SIZE chars to detect INVALID INPUT before
    yielding anything to the caller. Raises InvalidTopicError or API errors —
    caller is responsible for handling.
    """
    messages = _build_messages(cls, subject, topic, medium, feature, extra, history)
    stream = _call_with_retry(lambda: get_client().chat.completions.create(
        model=MODEL, messages=messages, stream=True, max_tokens=max_tokens,
    ))
    buffer = ""
    buffer_flushed = False
    for chunk in stream:
        text = chunk.choices[0].delta.content
        if not text:
            continue
        if not buffer_flushed:
            buffer += text
            if len(buffer) >= _BUFFER_SIZE:
                _check_invalid(buffer)
                buffer_flushed = True
                yield buffer
                buffer = ""
        else:
            yield text
    # Flush remainder — handles short responses that never filled the buffer
    if buffer:
        _check_invalid(buffer)
        yield buffer


def generate_json(cls: str, subject: str, topic: str, medium: str,
                  extra: Optional[dict] = None) -> str:
    """
    Non-streaming JSON mode call for Quiz generation.
    Returns raw JSON string. Raises InvalidTopicError or API errors — caller handles.
    """
    messages = _build_messages(cls, subject, topic, medium, "Quiz", extra)
    response = _call_with_retry(lambda: get_client().chat.completions.create(
        model=MODEL,
        messages=messages,
        response_format={"type": "json_object"},
        max_tokens=2000,
    ))
    content = (response.choices[0].message.content or "").strip()
    _check_invalid(content)
    return content
