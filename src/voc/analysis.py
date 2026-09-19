from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable

import pandas as pd

from .models import (
    AnalysisResult,
    Insight,
    Recommendation,
    ReviewRecord,
    ReviewValidationResult,
    ValidationIssue,
)
from .validation import validate_review_dataframe


EVIDENCE_STRENGTH_RULES: dict[str, Any] = {
    "meaning": "Rule-based evidence tier; it is not a calibrated probability.",
    "topic_coverage_definition": (
        "Unique reviews classified as supporting or contradicting for the topic "
        "divided by all valid reviews."
    ),
    "overall_coverage_definition": (
        "Unique reviews used as evidence by any supported topic divided by all "
        "valid reviews."
    ),
    "minimum_supporting_reviews": 2,
    "minimum_topic_coverage": 0.10,
    "low": (
        "Passes the minimum support and coverage gates but does not satisfy the "
        "medium or high tier."
    ),
    "medium": {
        "minimum_supporting_reviews": 3,
        "minimum_products": 2,
        "minimum_topic_coverage": 0.15,
    },
    "high": {
        "minimum_supporting_reviews": 5,
        "minimum_products": 3,
        "minimum_topic_coverage": 0.25,
        "maximum_contradiction_share": 0.25,
    },
    "conflict_gate": (
        "An insight is unknown and cannot create a deterministic recommendation "
        "when contradictions equal or exceed support."
    ),
}


@dataclass(frozen=True)
class _TopicDefinition:
    key: str
    label: str
    negative_patterns: tuple[str, ...]
    positive_patterns: tuple[str, ...]
    generic_patterns: tuple[str, ...]
    action: str


TOPICS = (
    _TopicDefinition(
        key="fit_comfort",
        label="fit and comfort",
        negative_patterns=(
            r"\buncomfortable\b",
            r"\btoo tight\b",
            r"\btoo loose\b",
            r"\bwork loose\b",
            r"(?<!doesn't )(?<!does not )\b(?:fall|falls|fell|falling) out\b",
            r"\bslips?\b",
            r"\bpress(?:es|ing)? against (?:my|the) ear\b",
            r"\bear tips?\b.{0,32}\btoo (?:large|small)\b",
            r"\btoo (?:large|small)\b.{0,32}\bear tips?\b",
            r"\b(?:hurt|hurts|painful)\b",
            r"\bpoor fit\b",
            r"\bdoes(?: not|n't) fit (?:my|the) ears?\b",
        ),
        positive_patterns=(
            r"\bcomfortable (?:for|during|to wear|in (?:my|the) ears?)\b",
            r"\bfits? well\b",
            r"\bsecure fit\b",
            r"\bstayed? secure\b",
            r"\bkeep(?:s|ing)? (?:them|it) stable\b",
            r"\btip sizes?\b.{0,48}\bgood seal\b",
            r"\bstays? (?:in|put)\b",
            r"\bdoes(?: not|n't) fall out\b",
        ),
        generic_patterns=(
            r"\b(?:earbuds?|buds?|wing tips?)\b.{0,48}\b(?:secure|stable|loose|slip|painful)\b",
            r"\b(?:secure|stable|loose|slip|painful)\b.{0,48}\b(?:earbuds?|buds?|wing tips?)\b",
        ),
        action=(
            "Validate fit across representative use cases and add clear sizing "
            "or fit guidance before launch."
        ),
    ),
    _TopicDefinition(
        key="durability",
        label="durability",
        negative_patterns=(
            r"\b(?:broke|broken|cracked|snapped)\b",
            r"\bstopped working\b",
            r"\bstopped charging\b",
            r"\bfell apart\b",
            r"\bscratches?\b",
            r"\bscratched\b",
            r"\bflimsy\b",
            r"\bnot durable\b",
            r"\bpoor build quality\b",
            r"\bonly lasted\b",
        ),
        positive_patterns=(
            r"(?<!not )\bdurable\b",
            r"\bsturdy\b",
            r"\bwell[ -]built\b",
            r"\bstill works?\b",
            r"\bstill looks? new\b",
            r"\bpull(?:s|ed)? .* charging position\b",
            r"\bholds? up\b",
            r"\blong[ -]lasting\b",
        ),
        generic_patterns=(
            r"\bdurability\b",
            r"\bbuild quality\b",
            r"\bconstruction\b",
        ),
        action=(
            "Run durability tests on the reported failure modes and document "
            "the resulting supplier quality requirements."
        ),
    ),
    _TopicDefinition(
        key="battery",
        label="battery life and charging",
        negative_patterns=(
            r"\bbattery (?:dies?|drains?)\b",
            r"\bbattery dropped\b",
            r"\b(?:poor|short|terrible|bad) battery life\b",
            r"\bdrains? (?:too )?(?:fast|quickly)\b",
            r"\bonly lasts?\b",
            r"\bempty in under\b",
        ),
        positive_patterns=(
            r"\b(?:great|excellent|long|strong) battery life\b",
            r"(?<!only )\bbattery lasts?\b",
            r"\bbattery lasted\b",
            r"\blast(?:ed|s) through\b",
            r"\bholds? a charge\b",
        ),
        generic_patterns=(
            r"\bbattery (?:life|runtime)\b",
        ),
        action=(
            "Benchmark real-world battery runtime and charging reliability, "
            "then set measurable supplier acceptance criteria."
        ),
    ),
)


def _matches(text: str, patterns: tuple[str, ...]) -> bool:
    return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in patterns)


def classify_evidence_strength(
    *,
    support_count: int,
    contradiction_count: int,
    product_count: int,
    coverage: float,
) -> str:
    """Return a transparent rule tier, never a statistical confidence value."""

    if support_count < EVIDENCE_STRENGTH_RULES["minimum_supporting_reviews"]:
        return "insufficient"
    if coverage < EVIDENCE_STRENGTH_RULES["minimum_topic_coverage"]:
        return "insufficient"

    total_evidence = support_count + contradiction_count
    contradiction_share = (
        contradiction_count / total_evidence if total_evidence else 0.0
    )
    high = EVIDENCE_STRENGTH_RULES["high"]
    if (
        support_count >= high["minimum_supporting_reviews"]
        and product_count >= high["minimum_products"]
        and coverage >= high["minimum_topic_coverage"]
        and contradiction_share <= high["maximum_contradiction_share"]
    ):
        return "high"

    medium = EVIDENCE_STRENGTH_RULES["medium"]
    if (
        support_count >= medium["minimum_supporting_reviews"]
        and product_count >= medium["minimum_products"]
        and coverage >= medium["minimum_topic_coverage"]
        and contradiction_count < support_count
    ):
        return "medium"
    return "low"


def _topic_evidence(
    records: list[ReviewRecord], topic: _TopicDefinition
) -> tuple[list[str], list[str]]:
    supporting: list[str] = []
    contradicting: list[str] = []
    for review in records:
        text = review.review_text.lower().replace("’", "'")
        is_negative = _matches(text, topic.negative_patterns)
        is_positive = _matches(text, topic.positive_patterns)

        if not is_negative and not is_positive and _matches(
            text, topic.generic_patterns
        ):
            if review.rating <= 2:
                is_negative = True
            elif review.rating >= 4:
                is_positive = True

        # A single review occupies one side of the ledger. When explicit
        # positive and negative phrases coexist, its rating breaks the tie;
        # low-rated mixed reviews support a pain point and high-rated ones
        # contradict it.
        if is_negative and is_positive:
            if review.rating <= 2:
                is_positive = False
            elif review.rating >= 4:
                is_negative = False
            else:
                is_negative = False
                is_positive = False

        if is_negative:
            supporting.append(review.review_id)
        if is_positive:
            contradicting.append(review.review_id)
    return supporting, contradicting


def _unknowns_for(
    *,
    support_count: int,
    contradiction_count: int,
    product_count: int,
    coverage: float,
) -> list[str]:
    unknowns: list[str] = []
    minimum_support = EVIDENCE_STRENGTH_RULES["minimum_supporting_reviews"]
    minimum_coverage = EVIDENCE_STRENGTH_RULES["minimum_topic_coverage"]
    if support_count < minimum_support:
        unknowns.append(
            f"Fewer than {minimum_support} supporting reviews were found."
        )
    if coverage < minimum_coverage:
        unknowns.append(
            f"Topic coverage is below the {minimum_coverage:.0%} decision gate."
        )
    if contradiction_count >= support_count and contradiction_count > 0:
        unknowns.append(
            "Contradicting evidence equals or exceeds supporting evidence."
        )
    if product_count < 2 and support_count > 0:
        unknowns.append("Evidence may be specific to a single product.")
    return unknowns


def _coerce_records(
    source: pd.DataFrame | ReviewValidationResult | Iterable[ReviewRecord],
) -> tuple[list[ReviewRecord], list[ValidationIssue]]:
    if isinstance(source, pd.DataFrame):
        validated = validate_review_dataframe(source)
        return validated.records, validated.issues
    if isinstance(source, ReviewValidationResult):
        return list(source.records), list(source.issues)
    records = list(source)
    if not all(isinstance(record, ReviewRecord) for record in records):
        raise TypeError(
            "source must be a DataFrame, ReviewValidationResult, or ReviewRecord iterable"
        )
    return records, []


def analyze_reviews(
    source: pd.DataFrame | ReviewValidationResult | Iterable[ReviewRecord],
) -> AnalysisResult:
    """Recompute the evidence ledger from source reviews without cached claims."""

    records, validation_issues = _coerce_records(source)
    review_by_id = {review.review_id: review for review in records}
    insights: list[Insight] = []
    recommendations: list[Recommendation] = []
    all_evidence_ids: set[str] = set()
    total_reviews = len(records)

    for topic in TOPICS:
        supporting, contradicting = _topic_evidence(records, topic)
        evidence_ids = set(supporting) | set(contradicting)
        all_evidence_ids.update(evidence_ids)
        product_ids = {
            review_by_id[review_id].product_id for review_id in evidence_ids
        }
        coverage = len(evidence_ids) / total_reviews if total_reviews else 0.0
        strength = classify_evidence_strength(
            support_count=len(supporting),
            contradiction_count=len(contradicting),
            product_count=len(product_ids),
            coverage=coverage,
        )
        unknowns = _unknowns_for(
            support_count=len(supporting),
            contradiction_count=len(contradicting),
            product_count=len(product_ids),
            coverage=coverage,
        )
        is_unknown = (
            strength == "insufficient"
            or (
                len(contradicting) >= len(supporting)
                and len(contradicting) > 0
            )
        )
        insight_type = "unknown" if is_unknown else "inference"
        if is_unknown:
            claim = (
                f"Evidence is insufficient to determine whether {topic.label} "
                "is a recurring customer pain point."
            )
        else:
            claim = f"{topic.label.capitalize()} is a recurring customer pain point."

        insight = Insight(
            insight_id=f"mock-{topic.key}",
            claim=claim,
            type=insight_type,
            supporting_review_ids=supporting,
            contradicting_review_ids=contradicting,
            support_count=len(supporting),
            contradiction_count=len(contradicting),
            evidence_strength=strength,
            assumptions=[
                "English keyword matches are treated as topic evidence.",
                "A low rating only supplies polarity when the review names the topic.",
                "Evidence strength is a rule tier, not a probability.",
            ],
            topic=topic.key,
            product_count=len(product_ids),
            evidence_coverage=round(coverage, 4),
            unknowns=unknowns,
        )
        insights.append(insight)

        if not is_unknown and supporting:
            risk_flags: list[str] = []
            if contradicting:
                risk_flags.append("contradicting_reviews_present")
            if len(product_ids) < 2:
                risk_flags.append("single_product_evidence")
            recommendations.append(
                Recommendation(
                    action=topic.action,
                    rationale=(
                        f"{len(supporting)} of {total_reviews} valid reviews support "
                        f"the {topic.label} pain point across {len(product_ids)} "
                        f"product(s); {len(contradicting)} review(s) contradict it."
                    ),
                    evidence_refs=list(supporting),
                    risk_flags=risk_flags,
                    unknowns=unknowns,
                )
            )

    overall_coverage = (
        len(all_evidence_ids) / total_reviews if total_reviews else 0.0
    )
    if recommendations and all(insight.type != "unknown" for insight in insights):
        decision_status = "ready"
    elif recommendations:
        decision_status = "partial_evidence"
    else:
        decision_status = "insufficient_evidence"

    return AnalysisResult(
        reviews=records,
        insights=insights,
        recommendations=recommendations,
        validation_issues=validation_issues,
        evidence_coverage=round(overall_coverage, 4),
        decision_status=decision_status,
        evidence_rules=EVIDENCE_STRENGTH_RULES,
    )


analyze_review_records = analyze_reviews
