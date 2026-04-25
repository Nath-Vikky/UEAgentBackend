from __future__ import annotations

import re

_CJK_RE = re.compile(r"[\u4e00-\u9fff]")

DEFAULT_OUTPUT_LANGUAGE = "zh-CN"
SUPPORTED_OUTPUT_LANGUAGES = {"zh-CN", "en-US"}

_AUTO_LANGUAGE_VALUES = {
    "auto",
    "default",
    "detect",
    "system",
}

_ZH_LANGUAGE_VALUES = {
    "zh",
    "zh-cn",
    "zh-hans",
    "chinese",
    "simplifiedchinese",
    "\u4e2d\u6587",
    "\u7b80\u4f53\u4e2d\u6587",
}

_EN_LANGUAGE_VALUES = {
    "en",
    "en-us",
    "english",
    "usenglish",
}

ENGLISH_REPLY_HINTS = (
    "reply in english",
    "answer in english",
    "use english",
    "respond in english",
    "\u7528\u82f1\u6587\u56de\u7b54",
    "\u8bf7\u7528\u82f1\u6587",
    "\u82f1\u6587\u56de\u7b54",
)

CHINESE_REPLY_HINTS = (
    "reply in chinese",
    "answer in chinese",
    "use chinese",
    "respond in chinese",
    "\u7528\u4e2d\u6587\u56de\u7b54",
    "\u8bf7\u7528\u4e2d\u6587",
    "\u4e2d\u6587\u56de\u7b54",
)


def detect_language(text: str) -> str:
    if _CJK_RE.search(text):
        return "zh-CN"
    return "en-US"


def localized(language: str, zh_text: str, en_text: str) -> str:
    return zh_text if language.startswith("zh") else en_text


def normalize_output_language(value: str | None) -> str | None:
    raw = str(value or "").strip()
    if not raw:
        return None

    lowered = raw.lower().replace("_", "-")
    compact = lowered.replace(" ", "")
    if compact in _AUTO_LANGUAGE_VALUES:
        return "auto"
    if compact in _ZH_LANGUAGE_VALUES or lowered.startswith("zh"):
        return "zh-CN"
    if compact in _EN_LANGUAGE_VALUES or lowered.startswith("en"):
        return "en-US"
    return None


def detect_message_language_override(text: str) -> str | None:
    lowered = text.lower()
    if any(hint in lowered or hint in text for hint in ENGLISH_REPLY_HINTS):
        return "en-US"
    if any(hint in lowered or hint in text for hint in CHINESE_REPLY_HINTS):
        return "zh-CN"
    return None
