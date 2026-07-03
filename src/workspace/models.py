from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


SCHEMA_VERSION = "1.0"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class ProductItem:
    source_url: str
    title: str = ""
    brand: str = ""
    model: str = ""
    supplier_name: str = ""
    readiness_score: float = 0.0
    readiness_status: str = ""
    priority: str = ""
    risk_level: str = ""
    missing_count: int = 0
    follow_up_question_count: int = 0
    recommendation: str = ""
    next_action: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SupplierItem:
    supplier_key: str
    supplier_name: str = ""
    domain: str = ""
    product_count: int = 0
    average_readiness_score: float = 0.0
    overall_status: str = ""
    total_follow_up_questions: int = 0
    high_risk_product_count: int = 0
    best_product_title: str = ""
    recommendation: str = ""
    next_action: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class WorkspaceTask:
    source_url: str
    title: str = ""
    supplier_name: str = ""
    task_type: str = "supplier_follow_up"
    priority: str = ""
    question: str = ""
    status: str = "Open"
    owner: str = ""
    notes: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ProjectMetrics:
    product_count: int = 0
    supplier_count: int = 0
    review_candidate_count: int = 0
    high_risk_product_count: int = 0
    open_follow_up_count: int = 0
    average_readiness_score: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ProjectWorkspace:
    project_name: str
    profile: str = "generic_hardware"
    language: str = "en"
    schema_version: str = SCHEMA_VERSION
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)
    metrics: ProjectMetrics = field(default_factory=ProjectMetrics)
    products: tuple[ProductItem, ...] = ()
    suppliers: tuple[SupplierItem, ...] = ()
    tasks: tuple[WorkspaceTask, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "project_name": self.project_name,
            "profile": self.profile,
            "language": self.language,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "metrics": self.metrics.as_dict(),
            "products": [item.as_dict() for item in self.products],
            "suppliers": [item.as_dict() for item in self.suppliers],
            "tasks": [item.as_dict() for item in self.tasks],
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ProjectWorkspace":
        metrics_payload = payload.get("metrics") or {}
        return cls(
            schema_version=str(payload.get("schema_version") or SCHEMA_VERSION),
            project_name=str(payload.get("project_name") or "Untitled Project"),
            profile=str(payload.get("profile") or "generic_hardware"),
            language=str(payload.get("language") or "en"),
            created_at=str(payload.get("created_at") or utc_now_iso()),
            updated_at=str(payload.get("updated_at") or utc_now_iso()),
            metrics=ProjectMetrics(**metrics_payload),
            products=tuple(ProductItem(**item) for item in payload.get("products", [])),
            suppliers=tuple(SupplierItem(**item) for item in payload.get("suppliers", [])),
            tasks=tuple(WorkspaceTask(**item) for item in payload.get("tasks", [])),
        )
