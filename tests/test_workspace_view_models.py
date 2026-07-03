from src.workspace.models import (
    ProductItem,
    ProjectWorkspace,
    SupplierItem,
    WorkspaceTask,
)
from src.workspace.view_models import product_card_rows, supplier_card_rows, task_rows


def workspace():
    return ProjectWorkspace(
        project_name="Project",
        products=(
            ProductItem(source_url="u1", title="A", priority="P2", readiness_score=70),
            ProductItem(source_url="u2", title="B", priority="P1", readiness_score=90),
        ),
        suppliers=(
            SupplierItem(supplier_key="b", supplier_name="B", average_readiness_score=50, product_count=1),
            SupplierItem(supplier_key="a", supplier_name="A", average_readiness_score=80, product_count=2),
        ),
        tasks=(
            WorkspaceTask(source_url="u1", title="A", supplier_name="A", priority="High", question="Q1"),
        ),
    )


def test_product_card_rows_sort_by_priority_then_score():
    rows = product_card_rows(workspace())
    assert list(rows["title"]) == ["B", "A"]


def test_supplier_card_rows_sort_by_average_readiness():
    rows = supplier_card_rows(workspace())
    assert list(rows["supplier_name"]) == ["A", "B"]


def test_task_rows_preserve_questions():
    rows = task_rows(workspace())
    assert rows.loc[0, "question"] == "Q1"


def test_empty_workspace_views_have_columns():
    empty = ProjectWorkspace(project_name="Empty")
    assert "title" in product_card_rows(empty).columns
    assert "supplier_name" in supplier_card_rows(empty).columns
    assert "question" in task_rows(empty).columns
