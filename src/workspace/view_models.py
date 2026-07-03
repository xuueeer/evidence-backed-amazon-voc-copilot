from __future__ import annotations

import pandas as pd

from .models import ProjectWorkspace


def product_card_rows(workspace: ProjectWorkspace) -> pd.DataFrame:
    rows = [
        {
            "priority": product.priority,
            "title": product.title,
            "brand": product.brand,
            "model": product.model,
            "supplier_name": product.supplier_name,
            "readiness_score": product.readiness_score,
            "readiness_status": product.readiness_status,
            "risk_level": product.risk_level,
            "missing_count": product.missing_count,
            "follow_up_question_count": product.follow_up_question_count,
            "next_action": product.next_action,
            "source_url": product.source_url,
        }
        for product in workspace.products
    ]
    frame = pd.DataFrame(rows)
    if frame.empty:
        return pd.DataFrame(
            columns=[
                "priority",
                "title",
                "brand",
                "model",
                "supplier_name",
                "readiness_score",
                "readiness_status",
                "risk_level",
                "missing_count",
                "follow_up_question_count",
                "next_action",
                "source_url",
            ]
        )
    return frame.sort_values(by=["priority", "readiness_score"], ascending=[True, False], ignore_index=True)


def supplier_card_rows(workspace: ProjectWorkspace) -> pd.DataFrame:
    rows = [
        {
            "supplier_name": supplier.supplier_name,
            "domain": supplier.domain,
            "product_count": supplier.product_count,
            "average_readiness_score": supplier.average_readiness_score,
            "overall_status": supplier.overall_status,
            "total_follow_up_questions": supplier.total_follow_up_questions,
            "high_risk_product_count": supplier.high_risk_product_count,
            "best_product_title": supplier.best_product_title,
            "next_action": supplier.next_action,
        }
        for supplier in workspace.suppliers
    ]
    frame = pd.DataFrame(rows)
    if frame.empty:
        return pd.DataFrame(
            columns=[
                "supplier_name",
                "domain",
                "product_count",
                "average_readiness_score",
                "overall_status",
                "total_follow_up_questions",
                "high_risk_product_count",
                "best_product_title",
                "next_action",
            ]
        )
    return frame.sort_values(by=["average_readiness_score", "product_count"], ascending=[False, False], ignore_index=True)


def task_rows(workspace: ProjectWorkspace) -> pd.DataFrame:
    rows = [task.as_dict() for task in workspace.tasks]
    frame = pd.DataFrame(rows)
    if frame.empty:
        return pd.DataFrame(
            columns=[
                "source_url",
                "title",
                "supplier_name",
                "task_type",
                "priority",
                "question",
                "status",
                "owner",
                "notes",
            ]
        )
    return frame.sort_values(by=["priority", "title"], ascending=[True, True], ignore_index=True)
