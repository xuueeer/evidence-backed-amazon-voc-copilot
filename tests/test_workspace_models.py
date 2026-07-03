from src.workspace.models import (
    ProductItem,
    ProjectMetrics,
    ProjectWorkspace,
    SupplierItem,
    WorkspaceTask,
)


def test_project_workspace_round_trip_dict():
    workspace = ProjectWorkspace(
        project_name="Wireless Backup Camera 2026",
        profile="vehicle_camera",
        metrics=ProjectMetrics(
            product_count=2,
            supplier_count=1,
            review_candidate_count=1,
            high_risk_product_count=0,
            open_follow_up_count=3,
            average_readiness_score=81.5,
        ),
        products=(
            ProductItem(
                source_url="https://supplier.example.com/a",
                title="Camera A",
                supplier_name="Supplier A",
                readiness_score=88.0,
                priority="P1",
            ),
        ),
        suppliers=(
            SupplierItem(
                supplier_key="supplier a",
                supplier_name="Supplier A",
                product_count=1,
                average_readiness_score=88.0,
            ),
        ),
        tasks=(
            WorkspaceTask(
                source_url="https://supplier.example.com/a",
                title="Camera A",
                supplier_name="Supplier A",
                question="Please confirm waterproof rating.",
                priority="High",
            ),
        ),
    )

    payload = workspace.as_dict()
    restored = ProjectWorkspace.from_dict(payload)

    assert restored.project_name == "Wireless Backup Camera 2026"
    assert restored.metrics.product_count == 2
    assert restored.products[0].title == "Camera A"
    assert restored.suppliers[0].supplier_name == "Supplier A"
    assert restored.tasks[0].question == "Please confirm waterproof rating."


def test_workspace_defaults_are_safe():
    workspace = ProjectWorkspace.from_dict({"project_name": "Test"})
    assert workspace.project_name == "Test"
    assert workspace.schema_version == "1.0"
    assert workspace.metrics.product_count == 0
    assert workspace.products == ()
