from __future__ import annotations

import re

from app.observability.redaction import redact_payload

_MULTISPACE_RE = re.compile(r"[ \t]+")
_TOO_MANY_BLANKS_RE = re.compile(r"\n{3,}")
_HTML_TAG_RE = re.compile(r"<[^>]+>")


def clean_text(raw_text: str, *, is_html: bool = False) -> str:
    text = raw_text.strip()
    if is_html:
        text = _HTML_TAG_RE.sub(" ", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _MULTISPACE_RE.sub(" ", text)
    text = _TOO_MANY_BLANKS_RE.sub("\n\n", text)
    text = redact_payload({"text": text})["text"]
    return text.strip()

