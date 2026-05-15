from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from app.core.settings import Settings
from app.rag.indexing.sparse import tokenize_query


EXPLICIT_WEB_SEARCH_TERMS = (
    "web search",
    "search web",
    "online search",
    "search online",
    "latest docs",
    "official docs",
    "look up",
    "google",
    "上网查",
    "联网查",
    "搜一下",
    "搜索一下",
    "查一下最新",
    "官方文档",
)

UE_TECHNICAL_TERMS = (
    "unreal",
    "ue",
    "ue5",
    "ue4",
    "blueprint",
    "nanite",
    "lumen",
    "gas",
    "gameplay ability",
    "enhanced input",
    "uobject",
    "actor",
    "component",
    "虚幻",
    "蓝图",
    "资产",
    "材质",
    "增强输入",
    "角色",
    "静态网格",
    "动画",
)

BLOCKED_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "::1"}


@dataclass(frozen=True, slots=True)
class WebSearchItem:
    title: str
    url: str
    domain: str
    snippet: str
    score: float
    source_type: str
    provider: str
    published_at: str | None = None

    def to_dict(self, *, rank: int) -> dict[str, Any]:
        return {
            "rank": rank,
            "title": self.title,
            "url": self.url,
            "domain": self.domain,
            "snippet": self.snippet,
            "published_at": self.published_at,
            "source_type": self.source_type,
            "score": self.score,
            "provider": self.provider,
            "retrieval_source": "web_search",
        }


def is_explicit_web_search_request(query: str) -> bool:
    lowered = query.lower()
    return any(term in lowered or term in query for term in EXPLICIT_WEB_SEARCH_TERMS)


def is_ue_technical_query(query: str) -> bool:
    lowered = query.lower()
    return any(term in lowered or term in query for term in UE_TECHNICAL_TERMS)


def should_trigger_web_search(
    *,
    query: str,
    evidence_sufficient: bool,
    settings: Settings,
    explicit: bool | None = None,
) -> tuple[bool, str]:
    if not settings.web_search_enabled:
        return (False, "disabled_by_settings")
    if settings.web_search_provider.lower().strip() in {"", "disabled", "none", "off"}:
        return (False, "provider_disabled")
    if settings.web_search_max_queries <= 0:
        return (False, "query_budget_exhausted")

    explicit_request = is_explicit_web_search_request(query) if explicit is None else explicit
    if explicit_request:
        return (True, "explicit_user_request")
    if not evidence_sufficient and is_ue_technical_query(query):
        return (True, "kb_evidence_insufficient_for_ue_topic")
    return (False, "kb_evidence_sufficient" if evidence_sufficient else "not_ue_or_no_explicit_search")


class WebSearchService:
    def __init__(self, settings: Settings):
        self.settings = settings

    def status(self) -> dict[str, Any]:
        provider = self._provider()
        mock_path = self._mock_results_path()
        ready = bool(self.settings.web_search_enabled and provider not in {"", "disabled", "none", "off"})
        reason = "ready"
        if not self.settings.web_search_enabled:
            reason = "disabled_by_settings"
        elif provider in {"", "disabled", "none", "off"}:
            reason = "provider_disabled"
        elif provider == "mock" and (not mock_path or not mock_path.exists()):
            reason = "mock_results_path_missing"
        elif provider == "brave" and not self.settings.web_search_api_key.strip():
            reason = "api_key_missing"
        return {
            "enabled": self.settings.web_search_enabled,
            "provider": provider,
            "status": "ready" if ready and reason == "ready" else "disabled" if not ready else "degraded",
            "reason": reason,
            "real_provider_ready": provider == "brave" and bool(self.settings.web_search_api_key.strip()),
            "max_queries": self.settings.web_search_max_queries,
            "max_results": self.settings.web_search_max_results,
            "timeout_ms": self.settings.web_search_timeout_ms,
            "max_content_chars": self.settings.web_search_max_content_chars,
            "endpoint": self._endpoint(provider),
            "allowed_domains": self._allowed_domains(),
            "domain_boosts": self._domain_boosts(),
            "mock_results_path": str(mock_path) if mock_path else "",
        }

    def search(
        self,
        *,
        query: str,
        domain_hints: list[str] | None = None,
        language: str = "auto",
        trigger_reason: str = "manual",
        max_results: int | None = None,
    ) -> dict[str, Any]:
        started_at = time.perf_counter()
        provider = self._provider()
        budget = self._budget(max_results=max_results)
        should_run, skip_reason = should_trigger_web_search(
            query=query,
            evidence_sufficient=False,
            settings=self.settings,
            explicit=True,
        )
        if not should_run:
            return self._empty_result(
                query=query,
                provider=provider,
                status="skipped",
                reason=skip_reason,
                trigger_reason=trigger_reason,
                budget=budget,
                started_at=started_at,
            )
        if not query.strip():
            return self._empty_result(
                query=query,
                provider=provider,
                status="skipped",
                reason="empty_query",
                trigger_reason=trigger_reason,
                budget=budget,
                started_at=started_at,
            )
        if provider == "mock":
            return self._search_mock(
                query=query,
                domain_hints=domain_hints or [],
                language=language,
                trigger_reason=trigger_reason,
                budget=budget,
                started_at=started_at,
            )
        if provider == "brave":
            return self._search_brave(
                query=query,
                domain_hints=domain_hints or [],
                language=language,
                trigger_reason=trigger_reason,
                budget=budget,
                started_at=started_at,
            )
        return self._empty_result(
            query=query,
            provider=provider,
            status="error",
            reason="provider_not_implemented",
            trigger_reason=trigger_reason,
            budget=budget,
            started_at=started_at,
            warnings=[f"web_search_provider_not_implemented:{provider}"],
        )

    def _search_mock(
        self,
        *,
        query: str,
        domain_hints: list[str],
        language: str,
        trigger_reason: str,
        budget: dict[str, Any],
        started_at: float,
    ) -> dict[str, Any]:
        raw_results, load_warnings = self._load_mock_results()
        if not raw_results:
            return self._empty_result(
                query=query,
                provider="mock",
                status="completed",
                reason="no_mock_results",
                trigger_reason=trigger_reason,
                budget=budget,
                started_at=started_at,
                warnings=load_warnings,
            )

        ranked, skipped_domains = self._rank_raw_results(
            raw_results=raw_results,
            provider="mock",
            query=query,
            domain_hints=domain_hints,
            budget=budget,
        )
        elapsed_ms = round((time.perf_counter() - started_at) * 1000, 3)
        allowed_domains = self._allowed_domains()
        terms = _query_terms(query)
        return {
            "query": query,
            "provider": "mock",
            "status": "completed",
            "reason": "matched" if ranked else "no_matching_mock_results",
            "trigger_reason": trigger_reason,
            "language": language,
            "items": [item.to_dict(rank=index) for index, item in enumerate(ranked, start=1)],
            "summary": {
                "result_count": len(ranked),
                "candidate_count": len(ranked),
                "raw_result_count": len(raw_results),
                "skipped_domain_count": skipped_domains,
                "allowed_domains": allowed_domains,
                "domain_hints": domain_hints,
                "terms": terms,
                "elapsed_ms": elapsed_ms,
                "queries_used": 1,
            },
            "budget": budget,
            "warnings": load_warnings,
        }

    def _search_brave(
        self,
        *,
        query: str,
        domain_hints: list[str],
        language: str,
        trigger_reason: str,
        budget: dict[str, Any],
        started_at: float,
    ) -> dict[str, Any]:
        api_key = self.settings.web_search_api_key.strip()
        if not api_key:
            return self._empty_result(
                query=query,
                provider="brave",
                status="error",
                reason="api_key_missing",
                trigger_reason=trigger_reason,
                budget=budget,
                started_at=started_at,
                warnings=["web_search_api_key_missing"],
            )
        try:
            payload = self._request_json(
                method="GET",
                url=self._endpoint("brave"),
                headers={
                    "Accept": "application/json",
                    "X-Subscription-Token": api_key,
                },
                params={
                    "q": query,
                    "count": min(budget["max_results"], 10),
                    "search_lang": _language_code(language),
                },
                timeout=budget["timeout_ms"] / 1000,
            )
        except Exception as exc:
            return self._empty_result(
                query=query,
                provider="brave",
                status="error",
                reason="provider_request_failed",
                trigger_reason=trigger_reason,
                budget=budget,
                started_at=started_at,
                warnings=[f"brave_request_failed:{type(exc).__name__}"],
            )

        raw_results = _brave_results(payload)
        ranked, skipped_domains = self._rank_raw_results(
            raw_results=raw_results,
            provider="brave",
            query=query,
            domain_hints=domain_hints,
            budget=budget,
        )
        elapsed_ms = round((time.perf_counter() - started_at) * 1000, 3)
        return {
            "query": query,
            "provider": "brave",
            "status": "completed",
            "reason": "matched" if ranked else "no_matching_provider_results",
            "trigger_reason": trigger_reason,
            "language": language,
            "items": [item.to_dict(rank=index) for index, item in enumerate(ranked, start=1)],
            "summary": {
                "result_count": len(ranked),
                "candidate_count": len(ranked),
                "raw_result_count": len(raw_results),
                "skipped_domain_count": skipped_domains,
                "allowed_domains": self._allowed_domains(),
                "domain_hints": domain_hints,
                "terms": _query_terms(query),
                "elapsed_ms": elapsed_ms,
                "queries_used": 1,
            },
            "budget": budget,
            "warnings": [],
        }

    def _rank_raw_results(
        self,
        *,
        raw_results: list[dict[str, Any]],
        provider: str,
        query: str,
        domain_hints: list[str],
        budget: dict[str, Any],
    ) -> tuple[list[WebSearchItem], int]:
        allowed_domains = self._allowed_domains()
        boosts = self._domain_boosts()
        terms = _query_terms(query)
        items: list[WebSearchItem] = []
        skipped_domains = 0
        for raw in raw_results:
            item = _normalize_raw_item(raw, provider=provider, max_chars=budget["max_content_chars"])
            if not item:
                continue
            if allowed_domains and not _domain_allowed(item.domain, allowed_domains):
                skipped_domains += 1
                continue
            score = max(item.score, _score_text(item.title, item.snippet, terms))
            score += _domain_boost(item.domain, boosts)
            if domain_hints and any(hint.lower() in item.domain.lower() for hint in domain_hints):
                score += 0.05
            if terms and score <= 0 and not raw.get("always_include"):
                continue
            items.append(
                WebSearchItem(
                    title=item.title,
                    url=item.url,
                    domain=item.domain,
                    snippet=item.snippet,
                    published_at=item.published_at,
                    source_type=item.source_type,
                    score=round(min(score, 1.0), 4),
                    provider=item.provider,
                )
            )
        return (sorted(items, key=lambda item: item.score, reverse=True)[: budget["max_results"]], skipped_domains)

    def _load_mock_results(self) -> tuple[list[dict[str, Any]], list[str]]:
        path = self._mock_results_path()
        if not path:
            return ([], ["mock_results_path_empty"])
        if not path.exists():
            return ([], ["mock_results_path_missing"])
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            return ([], [f"mock_results_parse_failed:{type(exc).__name__}"])
        results = payload.get("results") if isinstance(payload, dict) else payload
        if not isinstance(results, list):
            return ([], ["mock_results_not_a_list"])
        return ([item for item in results if isinstance(item, dict)], [])

    def _provider(self) -> str:
        return self.settings.web_search_provider.strip().lower() or "disabled"

    def _mock_results_path(self) -> Path | None:
        raw = self.settings.web_search_mock_results_path.strip()
        return Path(raw) if raw else None

    def _endpoint(self, provider: str) -> str:
        configured = self.settings.web_search_endpoint.strip()
        if configured:
            return configured
        if provider == "brave":
            return "https://api.search.brave.com/res/v1/web/search"
        return ""

    def _allowed_domains(self) -> list[str]:
        return [item.lower().strip() for item in self.settings.web_search_allowed_domains if item.strip()]

    def _domain_boosts(self) -> dict[str, float]:
        boosts: dict[str, float] = {}
        for item in self.settings.web_search_domain_boosts:
            if ":" not in item:
                continue
            domain, value = item.rsplit(":", 1)
            try:
                boosts[domain.lower().strip()] = float(value.strip())
            except ValueError:
                continue
        return boosts

    def _budget(self, *, max_results: int | None) -> dict[str, Any]:
        try:
            requested_max_results = int(max_results or self.settings.web_search_max_results)
        except (TypeError, ValueError):
            requested_max_results = self.settings.web_search_max_results
        return {
            "max_queries": max(self.settings.web_search_max_queries, 0),
            "max_results": max(1, min(requested_max_results, 10)),
            "timeout_ms": max(self.settings.web_search_timeout_ms, 100),
            "max_content_chars": max(120, min(self.settings.web_search_max_content_chars, 5000)),
        }

    def _request_json(
        self,
        *,
        method: str,
        url: str,
        headers: dict[str, str],
        params: dict[str, Any],
        timeout: float,
    ) -> dict[str, Any]:
        with httpx.Client(timeout=timeout) as client:
            response = client.request(method, url, headers=headers, params=params)
            response.raise_for_status()
            payload = response.json()
        return payload if isinstance(payload, dict) else {}

    @staticmethod
    def _empty_result(
        *,
        query: str,
        provider: str,
        status: str,
        reason: str,
        trigger_reason: str,
        budget: dict[str, Any],
        started_at: float,
        warnings: list[str] | None = None,
    ) -> dict[str, Any]:
        return {
            "query": query,
            "provider": provider,
            "status": status,
            "reason": reason,
            "trigger_reason": trigger_reason,
            "items": [],
            "summary": {
                "result_count": 0,
                "candidate_count": 0,
                "raw_result_count": 0,
                "skipped_domain_count": 0,
                "allowed_domains": [],
                "domain_hints": [],
                "terms": _query_terms(query),
                "elapsed_ms": round((time.perf_counter() - started_at) * 1000, 3),
                "queries_used": 0,
            },
            "budget": budget,
            "warnings": warnings or [],
        }


def _query_terms(query: str) -> list[str]:
    terms: list[str] = []
    seen: set[str] = set()
    for token in tokenize_query(query):
        normalized = token.lower().strip()
        if not normalized or normalized in seen:
            continue
        if len(normalized) < 2 and not ("\u4e00" <= normalized <= "\u9fff"):
            continue
        seen.add(normalized)
        terms.append(normalized)
    return terms


def _normalize_raw_item(raw: dict[str, Any], *, provider: str, max_chars: int) -> WebSearchItem | None:
    title = str(raw.get("title") or "").strip()
    url = str(raw.get("url") or raw.get("link") or "").strip()
    snippet = str(raw.get("snippet") or raw.get("content") or raw.get("summary") or "").strip()
    parsed = urlparse(url)
    domain = (raw.get("domain") or parsed.netloc or "").lower().strip()
    if not title or not url or not domain or not _is_safe_public_url(url, domain):
        return None
    source_type = str(raw.get("source_type") or _source_type_for_domain(domain)).strip()
    score = _coerce_score(raw.get("score"))
    return WebSearchItem(
        title=title[:240],
        url=url,
        domain=domain,
        snippet=snippet[:max_chars],
        published_at=str(raw.get("published_at") or "").strip() or None,
        source_type=source_type,
        score=score,
        provider=provider,
    )


def _brave_results(payload: dict[str, Any]) -> list[dict[str, Any]]:
    web_section = payload.get("web") if isinstance(payload, dict) else {}
    results = web_section.get("results") if isinstance(web_section, dict) else []
    if not isinstance(results, list):
        return []
    normalized: list[dict[str, Any]] = []
    for item in results:
        if not isinstance(item, dict):
            continue
        url = str(item.get("url") or "")
        domain = urlparse(url).netloc.lower()
        normalized.append(
            {
                "title": item.get("title"),
                "url": url,
                "snippet": item.get("description") or item.get("snippet"),
                "published_at": item.get("age") or item.get("published_at"),
                "source_type": _source_type_for_domain(domain),
            }
        )
    return normalized


def _language_code(language: str) -> str:
    lowered = (language or "").lower()
    if lowered.startswith("zh"):
        return "zh-hans"
    if lowered.startswith("en"):
        return "en"
    return "en"


def _is_safe_public_url(url: str, domain: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return False
    clean_domain = domain.split(":")[0].lower()
    if clean_domain in BLOCKED_HOSTS:
        return False
    return not (
        clean_domain.startswith("127.")
        or clean_domain.startswith("10.")
        or clean_domain.startswith("192.168.")
    )


def _domain_allowed(domain: str, allowed_domains: list[str]) -> bool:
    clean_domain = domain.lower().split(":")[0]
    return any(clean_domain == allowed or clean_domain.endswith(f".{allowed}") for allowed in allowed_domains)


def _domain_boost(domain: str, boosts: dict[str, float]) -> float:
    clean_domain = domain.lower().split(":")[0]
    for boosted_domain, boost in boosts.items():
        if clean_domain == boosted_domain or clean_domain.endswith(f".{boosted_domain}"):
            return boost
    return 0.0


def _score_text(title: str, snippet: str, terms: list[str]) -> float:
    if not terms:
        return 0.0
    text = f"{title}\n{snippet}".lower()
    matched = sum(1 for term in terms if re.search(re.escape(term), text))
    return round(matched / max(len(terms), 1) * 0.65, 4)


def _source_type_for_domain(domain: str) -> str:
    if _domain_allowed(domain, ["dev.epicgames.com", "docs.unrealengine.com", "unrealengine.com"]):
        return "official"
    return "web"


def _coerce_score(value: Any) -> float:
    try:
        score = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(score, 1.0))
