from __future__ import annotations

import re
from collections import Counter

TOKEN_RE = re.compile(r"[A-Za-z0-9_/.:-]+|[\u4e00-\u9fff]")


def tokenize(text: str) -> list[str]:
    return [item.lower() for item in TOKEN_RE.findall(text)]


def token_counter(text: str) -> Counter[str]:
    return Counter(tokenize(text))
