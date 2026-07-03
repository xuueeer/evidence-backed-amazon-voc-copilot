from __future__ import annotations

from statistics import mean
from typing import Any

import pandas as pd

from .models import (
    ProductItem,
    ProjectMetrics,
    ProjectWorkspace,
    SupplierItem,
    WorkspaceTask,
)


def _records(value: pd.DataFrame | list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    if value is None:
        return []
    if isinstance(value, pd.DataFrame):
        return value.to_dict("records")
    return list(value or [])


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _is_high_risk(row: dict[str, Any]) -> bool:
    risk = str(row.get("risk_level", "") or "").lower()
    status = str(row.get("readiness_status", "") or row.get("product_pool_status", "") or "").lower()
    return risk == "high" or "high risk" in status or "高风险" in status


def _is_review_candidate(row: dict[str, Any]) -> bool:
    priority = str(row.get("priority", "") or "").upper()
    status = str(row.get("readiness_status", "") or row.get("product_pool_status", "") or "").lower()
    return priority == "P1" or "ready for review" in status or "review candidate" in status or "评审" in status


def build_project_workspace(
    *,
    project_name: str,
    profile: str = "generic_hardware",
    language: str = "en",
    product_pool: pd.DataFrame | list[dict[str, Any]] | None = None,
    supplier_comparison: pd.DataFrame | list[dict[str, Any]] | None = None,
    supplier_follow_up: pd.DataFrame | list[dict[str, Any]] | None = None,
) -> ProjectWorkspace:
    product_rows = _records(product_pool)
    supplier_rows = _records(supplier_comparison)
    task_rows = _records(supplier_follow_up)

    product_items = tuple(
        ProductItem(
            source_url=str(row.get("source_url", "") or ""),
            title=str(row.get("title", "") or ""),
            brand=str(row.get("brand", "") or ""),
            model=str(row.get("model", "") or ""),
            supplier_name=str(row.get("supplier_name", "") or row.get("brand", "") or ""),
            readiness_score=round(_as_float(row.get("readiness_score")), 2),
            readiness_status=str(row.get("readiness_status", "") or row.get("product_pool_status", "") or ""),
            priority=str(row.get("priority", "") or ""),
            risk_level=str(row.get("risk_level", "") or ""),
            missing_count=_as_int(row.get("missing_count")),
            follow_up_question_count=_as_int(row.get("follow_up_question_count")),
            recommendation=str(row.get("recommendation", "") or ""),
            next_action=str(row.get("next_action", "") or ""),
        )
        for row in product_rows
    )

    supplier_items = tuple(
        SupplierItem(
            supplier_key=str(row.get("supplier_key", "") or ""),
            supplier_name=str(row.get("supplier_name", "") or ""),
            domain=str(row.get("domain", "") or ""),
            product_count=_as_int(row.get("product_count")),
            average_readiness_score=round(_as_float(row.get("average_readiness_score")), 2),
            overall_status=str(row.get("overall_status", "") or ""),
            total_follow_up_questions=_as_int(row.get("total_follow_up_questions")),
            high_risk_product_count=_as_int(row.get("high_risk_product_count")),
            best_product_title=str(row.get("best_product_title", "") or ""),
            recommendation=str(row.get("recommendation", "") or ""),
            next_action=str(row.get("next_action", "") or ""),
        )
        for row in supplier_rows
    )

    tasks = tuple(
        WorkspaceTask(
            source_url=str(row.get("source_url", "") or ""),
            title=str(row.get("title", "") or ""),
            supplier_name=str(row.get("brand", "") or row.get("supplier_name", "") or ""),
            question=str(row.get("question", "") or ""),
            priority=str(row.get("priority", "") or ""),
            status=str(row.get("status", "") or "Open"),
            owner=str(row.get("owner", "") or ""),
            notes=str(row.get("notes", "") or ""),
        )
        for row in task_rows
        if str(row.get("question", "") or "").strip()
    )

    readiness_scores = [_as_float(row.get("readiness_score")) for row in product_rows]
    metrics = ProjectMetrics(
        product_count=len(product_items),
        supplier_count=len(supplier_items),
        review_candidate_count=sum(1 for row in product_rows if _is_review_candidate(row)),
        high_risk_product_count=sum(1 for row in product_rows if _is_high_risk(row)),
        open_follow_up_count=len(tasks),
        average_readiness_score=round(mean(readiness_scores), 2) if readiness_scores else 0.0,
    )

    return ProjectWorkspace(
        project_name=project_name,
        profile=profile,
        language=language,
        metrics=metrics,
        products=product_items,
        suppliers=supplier_items,
        tasks=tasks,
    )
