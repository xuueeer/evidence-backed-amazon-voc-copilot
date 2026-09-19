from __future__ import annotations

import csv
import json
from io import StringIO

from .models import AnalysisResult


def analysis_to_json(result: AnalysisResult, *, indent: int = 2) -> str:
    return json.dumps(result.as_dict(), ensure_ascii=False, indent=indent)


def _clean_markdown_text(value: str) -> str:
    return " ".join(value.replace("|", "\\|").split())


def analysis_to_markdown(result: AnalysisResult) -> str:
    reviews = {review.review_id: review for review in result.reviews}
    lines = [
        "# Evidence-Backed VOC Audit",
        "",
        "## Summary",
        "",
        f"- Valid reviews: {len(result.reviews)}",
        f"- Evidence coverage: {result.evidence_coverage:.1%}",
        f"- Decision status: `{result.decision_status}`",
        "- Evidence strength is a transparent rule tier, not a calibrated probability.",
        "",
        "## Evidence rules",
        "",
        (
            "A topic is `insufficient` below "
            f"{result.evidence_rules.get('minimum_supporting_reviews', 2)} supporting "
            "reviews or below "
            f"{result.evidence_rules.get('minimum_topic_coverage', 0.10):.0%} coverage."
        ),
        "",
        "## Insights",
        "",
    ]

    for insight in result.insights:
        lines.extend(
            [
                f"### {insight.topic or insight.insight_id}",
                "",
                f"- Claim: {insight.claim}",
                f"- Type: `{insight.type}`",
                f"- Evidence strength: `{insight.evidence_strength}`",
                f"- Supporting / contradicting: {insight.support_count} / {insight.contradiction_count}",
                f"- Products represented: {insight.product_count}",
                f"- Topic coverage: {insight.evidence_coverage:.1%}",
            ]
        )
        if insight.unknowns:
            lines.append("- Unknowns: " + "; ".join(insight.unknowns))
        if insight.assumptions:
            lines.append("- Assumptions: " + "; ".join(insight.assumptions))

        lines.extend(["", "Supporting evidence:", ""])
        if insight.supporting_review_ids:
            for review_id in insight.supporting_review_ids:
                review = reviews.get(review_id)
                quote = review.review_text if review else "Source review unavailable"
                metadata = (
                    f" _(product: {review.product_id}; rating: {review.rating:g}/5)_"
                    if review
                    else ""
                )
                lines.append(
                    f"> [{review_id}] {_clean_markdown_text(quote)}{metadata}"
                )
        else:
            lines.append("> No supporting review evidence found.")

        lines.extend(["", "Contradicting evidence:", ""])
        if insight.contradicting_review_ids:
            for review_id in insight.contradicting_review_ids:
                review = reviews.get(review_id)
                quote = review.review_text if review else "Source review unavailable"
                metadata = (
                    f" _(product: {review.product_id}; rating: {review.rating:g}/5)_"
                    if review
                    else ""
                )
                lines.append(
                    f"> [{review_id}] {_clean_markdown_text(quote)}{metadata}"
                )
        else:
            lines.append("> No contradicting review evidence found.")
        lines.append("")

    lines.extend(["## Recommendations", ""])
    if result.recommendations:
        for recommendation in result.recommendations:
            refs = ", ".join(recommendation.evidence_refs)
            lines.extend(
                [
                    f"- **{recommendation.action}**",
                    f"  - Rationale: {recommendation.rationale}",
                    f"  - Evidence refs: {refs}",
                ]
            )
            if recommendation.risk_flags:
                lines.append(
                    "  - Risk flags: " + ", ".join(recommendation.risk_flags)
                )
            if recommendation.unknowns:
                lines.append(
                    "  - Unknowns: " + "; ".join(recommendation.unknowns)
                )
    else:
        lines.append("Evidence is insufficient for a deterministic recommendation.")

    lines.extend(
        [
            "",
            "## Audit note",
            "",
            "Claims are derived from the supplied review sample. They are not verified Amazon market facts.",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def analysis_to_csv(result: AnalysisResult) -> str:
    """Export one row per supporting or contradicting evidence reference."""

    output = StringIO()
    fieldnames = [
        "insight_id",
        "topic",
        "claim",
        "type",
        "evidence_strength",
        "topic_coverage",
        "support_count",
        "contradiction_count",
        "product_count",
        "evidence_role",
        "review_id",
        "product_id",
        "rating",
        "review_text",
        "review_date",
        "source_type",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    reviews = {review.review_id: review for review in result.reviews}

    for insight in result.insights:
        references = [
            ("supporting", review_id)
            for review_id in insight.supporting_review_ids
        ] + [
            ("contradicting", review_id)
            for review_id in insight.contradicting_review_ids
        ]
        if not references:
            references = [("none", "")]
        for role, review_id in references:
            review = reviews.get(review_id)
            writer.writerow(
                {
                    "insight_id": insight.insight_id,
                    "topic": insight.topic,
                    "claim": insight.claim,
                    "type": insight.type,
                    "evidence_strength": insight.evidence_strength,
                    "topic_coverage": insight.evidence_coverage,
                    "support_count": insight.support_count,
                    "contradiction_count": insight.contradiction_count,
                    "product_count": insight.product_count,
                    "evidence_role": role,
                    "review_id": review_id,
                    "product_id": review.product_id if review else "",
                    "rating": review.rating if review else "",
                    "review_text": review.review_text if review else "",
                    "review_date": review.review_date if review else "",
                    "source_type": review.source_type if review else "",
                }
            )
    return output.getvalue()


export_analysis_json = analysis_to_json
export_analysis_markdown = analysis_to_markdown
export_analysis_csv = analysis_to_csv
