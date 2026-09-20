from __future__ import annotations

import pytest

from src.voc.models import AnalysisResult, Insight, Recommendation, ReviewRecord
from src.voc_dashboard import (
    _display_rationale,
    _evidence_balance,
    _evidence_card_html,
    _recommendation_card_html,
    _recommendation_for_insight,
    _replace_cached_result,
    _source_provenance,
    _status_presentation,
    _stretch_kwargs,
    _summary_grid_html,
    inject_app_styles,
)


def test_stretch_kwargs_supports_old_and_new_streamlit_apis() -> None:
    def legacy_component(*, use_container_width: bool = False) -> None:
        pass

    def current_component(*, width: str = "content") -> None:
        pass

    assert _stretch_kwargs(legacy_component) == {"use_container_width": True}
    assert _stretch_kwargs(current_component) == {"width": "stretch"}


def test_shared_app_styles_cover_non_voc_workspace_components(monkeypatch) -> None:
    calls: list[tuple[str, bool]] = []

    def capture(markup: str, *, unsafe_allow_html: bool = False) -> None:
        calls.append((markup, unsafe_allow_html))

    monkeypatch.setattr("src.voc_dashboard.st.markdown", capture)

    inject_app_styles()

    assert len(calls) == 1
    css, unsafe = calls[0]
    assert unsafe is True
    assert ".app-page-header" in css
    assert '[data-testid="stSidebar"]' in css
    assert '[data-testid="stMetric"]' in css
    assert '[data-testid="stDataFrame"]' in css
    assert '[data-testid="stNumberInput"]' in css


def test_deterministic_rationale_is_localized_for_chinese_ui() -> None:
    rationale = (
        "5 of 30 valid reviews support the fit and comfort pain point "
        "across 4 product(s); 3 review(s) contradict it."
    )

    localized = _display_rationale(rationale, "zh-CN")

    assert "30 条有效评论" in localized
    assert "佩戴与舒适度" in localized
    assert "3 条评论提供反向证据" in localized


def test_evidence_balance_handles_empty_evidence() -> None:
    assert _evidence_balance(0, 0) == (0.0, 0.0)


@pytest.mark.parametrize(
    ("support_count", "contradiction_count", "expected"),
    [
        (5, 3, (62.5, 37.5)),
        (2, 0, (100.0, 0.0)),
        (0, 4, (0.0, 100.0)),
    ],
)
def test_evidence_balance_non_empty_shares_sum_to_one_hundred(
    support_count: int,
    contradiction_count: int,
    expected: tuple[float, float],
) -> None:
    support_share, contradiction_share = _evidence_balance(
        support_count,
        contradiction_count,
    )

    assert support_share == pytest.approx(expected[0])
    assert contradiction_share == pytest.approx(expected[1])
    assert support_share + contradiction_share == pytest.approx(100.0)


@pytest.mark.parametrize(
    ("language", "synthetic_marker"),
    [("en", "synthetic"), ("zh-CN", "合成")],
)
def test_uploaded_source_is_not_described_as_synthetic(
    language: str,
    synthetic_marker: str,
) -> None:
    demo = " ".join(_source_provenance("demo", language)).lower()
    upload = " ".join(_source_provenance("upload", language)).lower()

    assert synthetic_marker in demo
    assert synthetic_marker not in upload
    assert demo != upload


@pytest.mark.parametrize(
    ("status", "english_label", "chinese_label"),
    [
        ("ready", "Ready", "可进入评审"),
        ("partial_evidence", "Partial evidence", "部分证据"),
        ("insufficient_evidence", "Insufficient", "证据不足"),
    ],
)
def test_status_presentation_is_complete_and_localized(
    status: str,
    english_label: str,
    chinese_label: str,
) -> None:
    en_label, en_summary, en_css_class = _status_presentation(status, "en")
    zh_label, zh_summary, zh_css_class = _status_presentation(status, "zh-CN")

    assert en_label == english_label
    assert zh_label == chinese_label
    assert en_summary.strip()
    assert zh_summary.strip()
    assert en_css_class.strip()
    assert zh_css_class == en_css_class


def test_status_presentation_uses_distinct_semantic_classes() -> None:
    css_classes = {
        _status_presentation(status, "en")[2]
        for status in ("ready", "partial_evidence", "insufficient_evidence")
    }

    assert len(css_classes) == 3


def test_evidence_card_html_escapes_review_fields() -> None:
    review = ReviewRecord(
        review_id='<script>alert("id")</script>',
        product_id='<img src=x onerror="alert(1)">',
        rating=2,
        review_text="Loose & painful <strong>fit</strong>.",
        review_date="2026-01-01",
        source_type="test",
    )

    rendered = _evidence_card_html(review, "supporting")

    assert "<script>" not in rendered
    assert "<img" not in rendered
    assert "<strong>fit</strong>" not in rendered
    assert "&lt;script&gt;" in rendered
    assert "&lt;img" in rendered
    assert "Loose &amp; painful &lt;strong&gt;fit&lt;/strong&gt;." in rendered
    assert "supporting" in rendered


def test_recommendation_card_includes_localized_unknowns_and_escapes_html() -> None:
    recommendation = Recommendation(
        action="Validate fit.",
        rationale="Supporting reviews identify a fit issue.",
        evidence_refs=["R1"],
        risk_flags=["single_product_evidence"],
        unknowns=[
            "Evidence may be specific to a single product.",
            "Missing <script>alert(1)</script> validation.",
        ],
    )

    rendered = _recommendation_card_html(recommendation, "zh-CN")

    assert "证据可能只适用于单个产品。" in rendered
    assert "Missing &lt;script&gt;alert(1)&lt;/script&gt; validation." in rendered
    assert "<script>" not in rendered


def test_replace_cached_result_drops_stale_value_when_refresh_fails() -> None:
    stale = AnalysisResult(decision_status="ready")
    state = {"result": stale}

    def fail() -> AnalysisResult:
        assert "result" not in state
        raise RuntimeError("refresh failed")

    with pytest.raises(RuntimeError, match="refresh failed"):
        _replace_cached_result(state, "result", fail)

    assert "result" not in state


def test_replace_cached_result_stores_successful_refresh() -> None:
    fresh = AnalysisResult(decision_status="partial_evidence")
    state = {"result": AnalysisResult(decision_status="ready")}

    returned = _replace_cached_result(state, "result", lambda: fresh)

    assert returned is fresh
    assert state["result"] is fresh


def test_products_kpi_describes_products_in_valid_reviews() -> None:
    reviews = [
        ReviewRecord(
            review_id="R1",
            product_id="P1",
            rating=5,
            review_text="No classified topic evidence.",
            review_date="2026-01-01",
            source_type="test",
        ),
        ReviewRecord(
            review_id="R2",
            product_id="P2",
            rating=5,
            review_text="Still no classified topic evidence.",
            review_date="2026-01-02",
            source_type="test",
        ),
    ]
    result = AnalysisResult(reviews=reviews)

    english = _summary_grid_html(result, "en")
    chinese = _summary_grid_html(result, "zh-CN")

    assert "Valid reviews span 2 product(s)" in english
    assert "Evidence spans 2 product(s)" not in english
    assert "有效评论涉及 2 个商品" in chinese


def _insight(*, supporting_review_ids: list[str]) -> Insight:
    return Insight(
        insight_id="insight-fit",
        claim="Fit is a recurring pain point.",
        type="inference",
        supporting_review_ids=supporting_review_ids,
        contradicting_review_ids=[],
        support_count=len(supporting_review_ids),
        contradiction_count=0,
        evidence_strength="medium",
        assumptions=[],
        topic="fit_comfort",
    )


def _recommendation(*, evidence_refs: list[str]) -> Recommendation:
    return Recommendation(
        action="Validate fit.",
        rationale="Supporting reviews identify a fit issue.",
        evidence_refs=evidence_refs,
        risk_flags=[],
        unknowns=[],
    )


def test_recommendation_for_insight_requires_the_complete_evidence_set() -> None:
    insight = _insight(supporting_review_ids=["R1", "R2"])
    empty = _recommendation(evidence_refs=[])
    partial = _recommendation(evidence_refs=["R2"])
    unrelated = _recommendation(evidence_refs=["R1", "R3"])
    matching = _recommendation(evidence_refs=["R2", "R1"])
    result = AnalysisResult(
        recommendations=[empty, partial, unrelated, matching]
    )

    selected = _recommendation_for_insight(result, insight)

    assert selected is matching


def test_recommendation_for_insight_returns_none_without_a_complete_match() -> None:
    insight = _insight(supporting_review_ids=["R1"])
    result = AnalysisResult(
        recommendations=[
            _recommendation(evidence_refs=[]),
            _recommendation(evidence_refs=["R1", "R2"]),
        ]
    )

    assert _recommendation_for_insight(result, insight) is None


def test_recommendation_for_insight_preserves_order_when_evidence_sets_overlap() -> None:
    fit = _insight(supporting_review_ids=["R1", "R2"])
    durability = Insight(
        insight_id="insight-durability",
        claim="Durability is a recurring pain point.",
        type="inference",
        supporting_review_ids=["R1", "R2"],
        contradicting_review_ids=[],
        support_count=2,
        contradiction_count=0,
        evidence_strength="medium",
        assumptions=[],
        topic="durability",
    )
    fit_recommendation = _recommendation(evidence_refs=["R1", "R2"])
    durability_recommendation = Recommendation(
        action="Validate durability.",
        rationale="Supporting reviews identify a durability issue.",
        evidence_refs=["R1", "R2"],
        risk_flags=[],
        unknowns=[],
    )
    result = AnalysisResult(
        insights=[fit, durability],
        recommendations=[fit_recommendation, durability_recommendation],
    )

    assert _recommendation_for_insight(result, fit) is fit_recommendation
    assert (
        _recommendation_for_insight(result, durability)
        is durability_recommendation
    )


def test_recommendation_for_insight_rejects_ambiguous_reference_only_matches() -> None:
    insight = _insight(supporting_review_ids=["R1", "R2"])
    result = AnalysisResult(
        recommendations=[
            _recommendation(evidence_refs=["R1", "R2"]),
            _recommendation(evidence_refs=["R2", "R1"]),
        ]
    )

    assert _recommendation_for_insight(result, insight) is None
