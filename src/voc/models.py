from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class ReviewRecord:
    review_id: str
    product_id: str
    rating: float
    review_text: str
    review_date: str | None
    source_type: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Insight:
    insight_id: str
    claim: str
    type: str
    supporting_review_ids: list[str]
    contradicting_review_ids: list[str]
    support_count: int
    contradiction_count: int
    evidence_strength: str
    assumptions: list[str]
    topic: str = ""
    product_count: int = 0
    evidence_coverage: float = 0.0
    unknowns: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Recommendation:
    action: str
    rationale: str
    evidence_refs: list[str]
    risk_flags: list[str]
    unknowns: list[str]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ValidationIssue:
    row_number: int | None
    severity: str
    field: str
    error_code: str
    message: str
    raw_value: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ReviewValidationReport:
    input_rows: int
    valid_rows: int
    rejected_rows: int
    duplicate_review_ids: int
    blank_reviews: int
    invalid_ratings: int

    def as_dict(self) -> dict[str, int]:
        return asdict(self)


@dataclass
class ReviewValidationResult:
    records: list[ReviewRecord]
    issues: list[ValidationIssue]
    report: ReviewValidationReport

    def as_dict(self) -> dict[str, Any]:
        return {
            "records": [record.as_dict() for record in self.records],
            "issues": [issue.as_dict() for issue in self.issues],
            "report": self.report.as_dict(),
        }


@dataclass
class AnalysisResult:
    reviews: list[ReviewRecord] = field(default_factory=list)
    insights: list[Insight] = field(default_factory=list)
    recommendations: list[Recommendation] = field(default_factory=list)
    validation_issues: list[ValidationIssue] = field(default_factory=list)
    evidence_coverage: float = 0.0
    decision_status: str = "insufficient_evidence"
    evidence_rules: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "summary": {
                "review_count": len(self.reviews),
                "insight_count": len(self.insights),
                "recommendation_count": len(self.recommendations),
                "evidence_coverage": self.evidence_coverage,
                "decision_status": self.decision_status,
            },
            "reviews": [review.as_dict() for review in self.reviews],
            "insights": [insight.as_dict() for insight in self.insights],
            "recommendations": [
                recommendation.as_dict()
                for recommendation in self.recommendations
            ],
            "validation_issues": [
                issue.as_dict() for issue in self.validation_issues
            ],
            "evidence_rules": dict(self.evidence_rules),
        }
