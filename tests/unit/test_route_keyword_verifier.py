from __future__ import annotations

from app.agent.route_keyword_verifier import analyze_route_keywords, target_kind_from_keyword_report


def test_keyword_verifier_detects_active_context_and_asset_domain() -> None:
    report = analyze_route_keywords("Can you analyze this asset?")

    assert report["active_context_reference"] is True
    assert report["top_domain"] == "asset"
    assert report["pure_smalltalk_signal"] is False
    assert target_kind_from_keyword_report(report) == "selected_asset"


def test_keyword_verifier_detects_write_signal_without_executing_anything() -> None:
    report = analyze_route_keywords("Rename this asset to SM_Rock_A.")

    assert report["hard_write_signal"] is True
    assert report["active_context_reference"] is True
    assert "rename" in report["matched"]["hard_write"]


def test_keyword_verifier_marks_pure_smalltalk() -> None:
    report = analyze_route_keywords("Thanks!")

    assert report["smalltalk_signal"] is True
    assert report["pure_smalltalk_signal"] is True
    assert report["task_signal_count"] == 0
