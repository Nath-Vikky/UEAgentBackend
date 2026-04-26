from __future__ import annotations

import re
from collections import Counter

TOKEN_RE = re.compile(r"[A-Za-z0-9_/.:-]+|[\u4e00-\u9fff]")

QUERY_EXPANSIONS: tuple[tuple[tuple[str, ...], tuple[str, ...]], ...] = (
    (
        ("生命周期", "life cycle"),
        ("lifecycle", "constructor", "beginplay", "tick", "endplay", "destroy", "garbage", "collection"),
    ),
    (
        ("增强输入", "enhanced input"),
        ("enhanced", "input", "inputmappingcontext", "inputaction", "enhancedinputcomponent", "addmappingcontext", "bindaction"),
    ),
    (
        ("软引用", "soft reference"),
        ("soft", "reference", "tsoftobjectptr", "streamablemanager", "async", "loading"),
    ),
    (
        ("异步加载", "async load"),
        ("async", "loading", "streamablemanager", "requestasyncload", "soft", "reference"),
    ),
    (
        ("蓝图", "blueprint"),
        ("blueprint", "parent", "class", "component", "tick", "replication", "variable"),
    ),
    (
        ("静态网格体", "static mesh", "staticmesh"),
        ("staticmesh", "static", "mesh", "nanite", "lod", "collision", "material", "slots"),
    ),
    (
        ("碰撞", "collision"),
        ("collision", "overlap", "trace", "channel", "query"),
    ),
    (
        ("材质", "material"),
        ("material", "texture", "blend", "mode", "shader"),
    ),
    (
        ("模块", "build.cs", "module"),
        ("module", "build.cs", "dependency", "publicdependency", "privatedependency"),
    ),
    (
        ("子系统", "subsystem"),
        ("subsystem", "gameinstancesubsystem", "worldsubsystem", "initialize", "deinitialize"),
    ),
    (
        ("交互组件", "射线交互", "interaction component", "line trace"),
        ("interaction", "component", "overlap", "line", "trace", "interface"),
    ),
)


def tokenize(text: str) -> list[str]:
    return [item.lower() for item in TOKEN_RE.findall(text)]


def token_counter(text: str) -> Counter[str]:
    return Counter(tokenize(text))


def tokenize_query(text: str) -> list[str]:
    tokens = tokenize(text)
    lowered = text.lower()
    for triggers, expansions in QUERY_EXPANSIONS:
        if any(trigger in lowered for trigger in triggers):
            tokens.extend(expansions)
    deduped: list[str] = []
    seen: set[str] = set()
    for token in tokens:
        normalized = token.strip().lower()
        if not normalized or normalized in seen:
            continue
        deduped.append(normalized)
        seen.add(normalized)
    return deduped


def query_token_counter(text: str) -> Counter[str]:
    return Counter(tokenize_query(text))
