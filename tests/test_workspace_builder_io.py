import pandas as pd
import pytest

from src.workspace import (
    build_project_workspace,
    export_workspace_json,
    import_workspace_json,
)


def test_build_project_workspace_from_frames():
    product_pool = pd.DataFrame(
        [
            {
                "source_url": "https://supplier.example.com/a",
                "title": "Camera A",
                "brand": "Supplier A",
                "model": "A1",
                "supplier_name": "Supplier A",
                "readiness_score": 86,
                "readiness_status": "Ready for Review",
                "priority": "P1",
                "risk_level": "low",
                "missing_count": 1,
                "follow_up_question_count": 0,
                "recommendation": "Review",
                "next_action": "Compare quote",
            }
        ]
    )
    suppliers = pd.DataFrame(
        [
            {
                "supplier_key": "supplier a",
                "supplier_name": "Supplier A",
                "domain": "supplier.example.com",
                "product_count": 1,
                "average_readiness_score": 86,
                "overall_status": "Strong Candidate",
                "total_follow_up_questions": 0,
                "high_risk_product_count": 0,
                "best_product_title": "Camera A",
            }
        ]
    )
    tasks = pd.DataFrame(
        [
            {
                "source_url": "https://supplier.example.com/a",
                "title": "Camera A",
                "brand": "Supplier A",
                "question": "Please confirm latency.",
                "priority": "Medium",
                "status": "Open",
            }
        ]
    )

    workspace = build_project_workspace(
        project_name="Vehicle Camera Project",
        profile="vehicle_camera",
        product_pool=product_pool,
        supplier_comparison=suppliers,
        supplier_follow_up=tasks,
    )

    assert workspace.project_name == "Vehicle Camera Project"
    assert workspace.metrics.product_count == 1
    assert workspace.metrics.supplier_count == 1
    assert workspace.metrics.review_candidate_count == 1
    assert workspace.metrics.open_follow_up_count == 1
    assert workspace.products[0].title == "Camera A"
    assert workspace.suppliers[0].supplier_name == "Supplier A"
    assert workspace.tasks[0].question == "Please confirm latency."


def test_workspace_json_export_import_round_trip():
    workspace = build_project_workspace(
        project_name="Project",
        product_pool=[{"source_url": "https://example.com/a", "title": "A", "readiness_score": 80}],
    )

    data = export_workspace_json(workspace)
    restored = import_workspace_json(data)

    assert restored.project_name == "Project"
    assert restored.products[0].source_url == "https://example.com/a"


def test_import_workspace_json_rejects_unsupported_schema():
    with pytest.raises(ValueError, match="Unsupported workspace schema"):
        import_workspace_json({"schema_version": "99.0", "project_name": "X"})
