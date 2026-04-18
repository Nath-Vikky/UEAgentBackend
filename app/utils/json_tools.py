from __future__ import annotations

from typing import Any

import orjson


def to_jsonable(data: Any) -> Any:
    if hasattr(data, "model_dump"):
        return data.model_dump(mode="json")
    return data


def dumps_pretty(data: Any) -> str:
    return orjson.dumps(
        to_jsonable(data),
        option=orjson.OPT_INDENT_2 | orjson.OPT_SORT_KEYS,
    ).decode("utf-8")

