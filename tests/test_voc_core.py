from __future__ import annotations

import csv
import json
from io import StringIO
from pathlib import Path

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


REVIEW_COLUMNS = [
    "review_id",
    "product_id",
    "rating",
    "review_text",
    "review_date",
    "source_type",
]


def review_frame(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=REVIEW_COLUMNS)


def row(
    review_id: str,
    product_id: str,
    rating: float,
    text: str,
    *,
    date: str = "2025-01-01",
    source: str = "sample",
) -> dict:
    return {
        "review_id": review_id,
        "product_id": product_id,
        "rating": rating,
        "review_text": text,
        "review_date": date,
        "source_type": source,
    }


def insight_for(result, topic: str):
    return next(insight for insight in result.insights if insight.topic == topic)


def test_validation_requires_stable_review_schema():
    with pytest.raises(ReviewValidationError, match="source_type"):
        validate_review_dataframe(
            pd.DataFrame(
                {
                    "review_id": ["R1"],
                    "product_id": ["P1"],
                    "rating": [5],
                    "review_text": ["Good"],
                    "review_date": ["2025-01-01"],
                }
            )
        )


def test_validation_filters_empty_and_invalid_ratings_and_reports_duplicates():
    frame = review_frame(
        [
            row("R1", "P1", 2, "The fit is too tight."),
            row("R1", "P1", 4, "Duplicate row"),
            row("R2", "P2", 5, "   "),
            row("R3", "P3", 6, "Rating is outside the range"),
        ]
    )

    result = validate_review_dataframe(frame)

    assert [record.review_id for record in result.records] == ["R1"]
    assert result.report.input_rows == 4
    assert result.report.valid_rows == 1
    assert result.report.rejected_rows == 3
    assert result.report.duplicate_review_ids == 1
    assert result.report.blank_reviews == 1
    assert result.report.invalid_ratings == 1
    assert {issue.error_code for issue in result.issues} == {
        "duplicate_review_id",
        "blank_review_text",
        "invalid_rating",
    }


def test_csv_import_normalizes_date_and_source_type():
    csv_text = (
        "review_id,product_id,rating,review_text,review_date,source_type\n"
        "R1,P1,4.5,Comfortable,January 3 2025,\n"
    )

    result = read_review_csv(csv_text)

    assert len(result.records) == 1
    assert result.records[0].review_date == "2025-01-03"
    assert result.records[0].source_type == "unknown"
    assert result.issues[0].error_code == "blank_source_type"


def test_mock_analysis_retains_supporting_and_contradicting_evidence():
    frame = review_frame(
        [
            row("F1", "P1", 2, "The earbuds are uncomfortable and hurt."),
            row("F2", "P2", 2, "They fall out and feel too loose."),
            row("F3", "P3", 5, "Very comfortable with a secure fit."),
            row("D1", "P1", 1, "The case broke and feels flimsy."),
            row("D2", "P2", 2, "The hinge cracked after a week."),
            row("D3", "P3", 5, "It is sturdy and well-built."),
            row("B1", "P1", 1, "The battery dies and drains too fast."),
            row("B2", "P2", 2, "Poor battery life and it won't charge."),
            row("B3", "P3", 5, "Excellent battery life; it holds a charge."),
        ]
    )

    result = analyze_reviews(frame)

    fit = insight_for(result, "fit_comfort")
    durability = insight_for(result, "durability")
    battery = insight_for(result, "battery")
    assert fit.supporting_review_ids == ["F1", "F2"]
    assert fit.contradicting_review_ids == ["F3"]
    assert durability.supporting_review_ids == ["D1", "D2"]
    assert durability.contradicting_review_ids == ["D3"]
    assert battery.supporting_review_ids == ["B1", "B2"]
    assert battery.contradicting_review_ids == ["B3"]
    assert all(insight.product_count == 3 for insight in result.insights)


def test_no_evidence_produces_unknowns_and_no_unreferenced_recommendation():
    frame = review_frame(
        [
            row("R1", "P1", 5, "The color is exactly as pictured."),
            row("R2", "P2", 4, "Fast delivery and useful packaging."),
        ]
    )

    result = analyze_reviews(frame)

    assert result.decision_status == "insufficient_evidence"
    assert result.recommendations == []
    assert all(insight.type == "unknown" for insight in result.insights)
    assert all(
        insight.evidence_strength == "insufficient"
        for insight in result.insights
    )


def test_low_coverage_is_unknown_and_blocks_deterministic_recommendation():
    rows = [
        row("B1", "P1", 1, "The battery dies too quickly."),
        row("B2", "P2", 2, "Poor battery life."),
    ]
    rows.extend(
        row(f"N{number}", f"P{number % 4}", 4, "Color and packaging feedback.")
        for number in range(1, 29)
    )

    result = analyze_reviews(review_frame(rows))
    battery = insight_for(result, "battery")

    assert battery.support_count == 2
    assert battery.evidence_coverage == pytest.approx(2 / 30, abs=0.0001)
    assert battery.evidence_strength == "insufficient"
    assert battery.type == "unknown"
    assert all(
        "battery" not in recommendation.rationale.lower()
        for recommendation in result.recommendations
    )


def test_conflicting_evidence_is_unknown_when_it_matches_support():
    frame = review_frame(
        [
            row("N1", "P1", 1, "The case broke."),
            row("N2", "P2", 2, "It feels flimsy."),
            row("P1", "P3", 5, "This is sturdy."),
            row("P2", "P4", 5, "Very durable construction."),
        ]
    )

    durability = insight_for(analyze_reviews(frame), "durability")

    assert durability.support_count == 2
    assert durability.contradiction_count == 2
    assert durability.type == "unknown"
    assert "Contradicting evidence" in " ".join(durability.unknowns)


def test_recommendations_always_reference_existing_supporting_reviews():
    frame = review_frame(
        [
            row("B1", "P1", 1, "The battery dies too quickly."),
            row("B2", "P2", 2, "Poor battery life."),
            row("N1", "P3", 4, "The color looks good."),
        ]
    )

    result = analyze_reviews(frame)
    valid_ids = {review.review_id for review in result.reviews}

    assert result.recommendations
    for recommendation in result.recommendations:
        assert recommendation.evidence_refs
        assert set(recommendation.evidence_refs) <= valid_ids


def test_changed_source_review_is_recomputed_without_stale_evidence():
    frame = review_frame(
        [
            row("F1", "P1", 1, "The fit is too tight."),
            row("F2", "P2", 2, "These feel uncomfortable."),
            row("N1", "P3", 4, "The color looks good."),
        ]
    )
    first = analyze_reviews(frame)
    assert insight_for(first, "fit_comfort").type == "inference"

    frame.loc[frame["review_id"] == "F2", "review_text"] = "The color looks good."
    second = analyze_reviews(frame)
    fit = insight_for(second, "fit_comfort")

    assert fit.supporting_review_ids == ["F1"]
    assert fit.type == "unknown"
    assert not any(
        "fit" in recommendation.rationale.lower()
        for recommendation in second.recommendations
    )


def test_markdown_csv_and_json_exports_preserve_evidence_traceability():
    frame = review_frame(
        [
            row("B1", "P1", 1, "The battery dies too quickly."),
            row("B2", "P2", 2, "Poor battery life."),
            row("B3", "P3", 5, "Excellent battery life."),
        ]
    )
    result = analyze_reviews(frame)

    markdown = analysis_to_markdown(result)
    csv_text = analysis_to_csv(result)
    json_data = json.loads(analysis_to_json(result))
    csv_rows = list(csv.DictReader(StringIO(csv_text)))

    assert "[B1] The battery dies too quickly." in markdown
    assert "product: P1; rating: 1/5" in markdown
    assert "Assumptions:" in markdown
    assert "Contradicting evidence" in markdown
    assert "Risk flags: contradicting_reviews_present" in markdown
    assert any(
        item["review_id"] == "B3" and item["evidence_role"] == "contradicting"
        for item in csv_rows
    )
    battery = next(
        insight
        for insight in json_data["insights"]
        if insight["topic"] == "battery"
    )
    assert battery["supporting_review_ids"] == ["B1", "B2"]
    assert json_data["evidence_rules"]["meaning"].endswith(
        "not a calibrated probability."
    )


def test_mock_engine_matches_the_three_supported_topics_in_evaluation_set():
    project_root = Path(__file__).resolve().parents[1]
    reviews = pd.read_csv(project_root / "data" / "sample_reviews.csv")
    annotations = pd.read_csv(
        project_root / "data" / "evaluation" / "review_annotations.csv"
    )
    result = analyze_reviews(reviews)

    for insight in result.insights:
        expected = annotations.loc[annotations["expected_theme"] == insight.topic]
        assert set(insight.supporting_review_ids) == set(
            expected.loc[expected["expected_stance"] == "support", "review_id"]
        )
        assert set(insight.contradicting_review_ids) == set(
            expected.loc[
                expected["expected_stance"] == "contradict", "review_id"
            ]
        )
