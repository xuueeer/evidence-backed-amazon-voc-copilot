from __future__ import annotations

from io import StringIO

import pandas as pd
import pytest

from src.voc import (
    ReviewValidationError,
    analysis_to_csv,
    analysis_to_json,
    analysis_to_markdown,
    analyze_reviews,
    read_review_csv,
    validate_review_dataframe,
)


def review_frame(rows: list[dict] | None = None) -> pd.DataFrame:
    rows = rows or [
        {
            "review_id": "R1",
            "product_id": "P1",
            "rating": 1,
            "review_text": "The earbuds fall out during every run.",
            "review_date": "2026-01-01",
            "source_type": "test",
        },
        {
            "review_id": "R2",
            "product_id": "P2",
            "rating": 2,
            "review_text": "The buds work loose and become painful.",
            "review_date": "2026-01-02",
            "source_type": "test",
        },
        {
            "review_id": "R3",
            "product_id": "P3",
            "rating": 5,
            "review_text": "They stayed secure during a 10K.",
            "review_date": "2026-01-03",
            "source_type": "test",
        },
    ]
    return pd.DataFrame(rows)


def test_empty_review_text_is_rejected_and_reported() -> None:
    frame = review_frame()
    frame.loc[0, "review_text"] = " "

    result = validate_review_dataframe(frame)

    assert result.report.valid_rows == 2
    assert result.report.blank_reviews == 1
    assert any(issue.error_code == "blank_review_text" for issue in result.issues)


def test_duplicate_review_keeps_first_row() -> None:
    frame = review_frame()
    duplicate = frame.iloc[[0]].copy()
    duplicate.loc[:, "review_text"] = "Duplicate content"

    result = validate_review_dataframe(pd.concat([frame, duplicate], ignore_index=True))

    assert result.report.duplicate_review_ids == 1
    assert [record.review_id for record in result.records] == ["R1", "R2", "R3"]
    assert result.records[0].review_text != "Duplicate content"


def test_missing_columns_raise_clear_error() -> None:
    with pytest.raises(ReviewValidationError, match="Missing required review columns"):
        validate_review_dataframe(pd.DataFrame([{"review_id": "R1"}]))


def test_conflicting_evidence_is_visible() -> None:
    result = analyze_reviews(review_frame())
    fit = next(insight for insight in result.insights if insight.topic == "fit_comfort")

    assert fit.support_count == 2
    assert fit.contradiction_count == 1
    assert fit.supporting_review_ids == ["R1", "R2"]
    assert fit.contradicting_review_ids == ["R3"]


def test_low_coverage_blocks_deterministic_recommendation() -> None:
    rows = review_frame().to_dict("records")
    rows.extend(
        {
            "review_id": f"N{index}",
            "product_id": f"P{index}",
            "rating": 5,
            "review_text": "Sound quality is clear.",
            "review_date": "2026-01-10",
            "source_type": "test",
        }
        for index in range(4, 34)
    )

    result = analyze_reviews(pd.DataFrame(rows))
    fit = next(insight for insight in result.insights if insight.topic == "fit_comfort")

    assert fit.evidence_strength == "insufficient"
    assert fit.type == "unknown"
    assert all("fit" not in recommendation.rationale for recommendation in result.recommendations)


def test_removing_source_review_recomputes_counts() -> None:
    original = analyze_reviews(review_frame())
    edited = analyze_reviews(review_frame().query("review_id != 'R1'"))
    original_fit = next(i for i in original.insights if i.topic == "fit_comfort")
    edited_fit = next(i for i in edited.insights if i.topic == "fit_comfort")

    assert edited_fit.support_count == original_fit.support_count - 1
    assert "R1" not in edited_fit.supporting_review_ids


def test_exports_include_traceable_evidence() -> None:
    result = analyze_reviews(review_frame())

    assert "R1" in analysis_to_markdown(result)
    assert "contradicting" in analysis_to_csv(result)
    assert '"evidence_rules"' in analysis_to_json(result)


def test_csv_reader_accepts_in_memory_csv() -> None:
    source = StringIO(review_frame().to_csv(index=False))
    result = read_review_csv(source)

    assert result.report.valid_rows == 3


def test_every_recommendation_has_evidence_refs() -> None:
    result = analyze_reviews(pd.read_csv("data/sample_reviews.csv"))

    assert result.recommendations
    assert all(recommendation.evidence_refs for recommendation in result.recommendations)
    known = {review.review_id for review in result.reviews}
    assert all(
        set(recommendation.evidence_refs) <= known
        for recommendation in result.recommendations
    )


def test_annotation_fixture_covers_sample_reviews_once() -> None:
    reviews = pd.read_csv("data/sample_reviews.csv")
    annotations = pd.read_csv("data/evaluation/review_annotations.csv")

    assert len(reviews) == 30
    assert annotations["review_id"].is_unique
    assert set(annotations["review_id"]) == set(reviews["review_id"])
    assert set(annotations["expected_stance"]) <= {"support", "contradict", "neutral"}
