from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

import httpx
import pandas as pd
import pytest

from src.connectors.export import build_product_page_workbook
from src.connectors.models import ConnectorIssue, FetchLog, FetchResult, ProductPageRecord
from src.connectors.product_page import collect_product_pages
from src.connectors.web_fetcher import (
    WebFetchError,
    fetch_url,
    normalize_url,
    validate_public_url,
)

FIXTURES = Path(__file__).parent / "fixtures" / "product_pages"


def read_fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_normalize_url_adds_https_and_removes_fragment():
    assert normalize_url("Supplier.Example.com/path#section") == "https://supplier.example.com/path"


def test_validate_public_url_rejects_non_http_and_localhost():
    with pytest.raises(WebFetchError, match="Unsupported URL scheme"):
        validate_public_url("ftp://example.com/file")

    with pytest.raises(WebFetchError, match="Localhost"):
        validate_public_url("http://localhost:8501")


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.2/admin",
        "http://10.0.0.8/internal",
        "http://169.254.169.254/latest/meta-data",
        "http://[::1]/admin",
        "http://[fe80::1]/internal",
    ],
)
def test_validate_public_url_rejects_non_public_ip_ranges(url: str):
    with pytest.raises(WebFetchError, match="non-public"):
        validate_public_url(url)


def test_fetch_url_revalidates_redirect_destinations():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "93.184.216.34":
            return httpx.Response(
                302,
                request=request,
                headers={"location": "http://169.254.169.254/latest/meta-data"},
            )
        raise AssertionError("A non-public redirect destination must not be requested.")

    with httpx.Client(
        transport=httpx.MockTransport(handler),
        follow_redirects=True,
    ) as client:
        record, log, issue, html = fetch_url(
            "https://93.184.216.34/product",
            client=client,
        )

    assert record.status == "failed"
    assert log.success is False
    assert issue is not None
    assert "non-public" in issue.message
    assert html == ""


def test_validate_public_url_rejects_invalid_port():
    with pytest.raises(WebFetchError, match="invalid port"):
        validate_public_url("https://example.com:99999/product")


def test_collect_product_pages_uses_fetch_logs_and_parses_records(monkeypatch):
    html = read_fixture("jsonld_product.html")

    def fake_fetch_url(raw_url: str):
        record = ProductPageRecord(
            source_url=raw_url,
            status="fetched",
            status_code=200,
            fetched_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        log = FetchLog(
            source_url=raw_url,
            domain="supplier.example.com",
            success=True,
            status_code=200,
            elapsed_ms=12,
            fetched_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        return record, log, None, html

    monkeypatch.setattr("src.connectors.product_page.fetch_url", fake_fetch_url)

    result = collect_product_pages(["https://supplier.example.com/camera-a"])

    assert len(result.records) == 1
    assert len(result.fetch_logs) == 1
    assert result.records[0].title == "4G Solar Security Camera"
    assert result.records[0].status == "parsed"
    assert result.products_frame.loc[0, "title"] == "4G Solar Security Camera"
    assert bool(result.fetch_logs_frame.loc[0, "success"]) is True
    assert result.issues_frame.empty


def test_collect_product_pages_skips_duplicate_urls(monkeypatch):
    def fake_fetch_url(raw_url: str):
        record = ProductPageRecord(source_url=raw_url, status="fetched", status_code=200)
        log = FetchLog(
            source_url=raw_url,
            domain="supplier.example.com",
            success=True,
            status_code=200,
            elapsed_ms=1,
        )
        return record, log, None, "<html><title>Camera</title></html>"

    monkeypatch.setattr("src.connectors.product_page.fetch_url", fake_fetch_url)

    result = collect_product_pages([
        "https://supplier.example.com/camera-a",
        "https://supplier.example.com/camera-a",
    ])

    assert len(result.records) == 1
    assert any(issue.error_code == "duplicate_url" for issue in result.issues)


def test_product_page_workbook_contains_expected_sheets():
    record = ProductPageRecord(
        source_url="https://supplier.example.com/camera",
        status="parsed",
        status_code=200,
        title="Wireless Backup Camera",
        brand="RoadSight",
        raw_specs=[{"name": "Resolution", "value": "1080P", "parser": "html.table"}],
    )
    result = FetchResult(
        records=[record],
        fetch_logs=[
            FetchLog(
                source_url=record.source_url,
                domain=record.domain,
                success=True,
                status_code=200,
                elapsed_ms=15,
            )
        ],
        issues=[
            ConnectorIssue(
                source_url=record.source_url,
                severity="info",
                error_code="example",
                message="Example issue",
            )
        ],
    )

    workbook = build_product_page_workbook(result)
    excel = pd.ExcelFile(BytesIO(workbook), engine="openpyxl")

    assert excel.sheet_names == [
        "Products",
        "Raw Specifications",
        "Normalized Specifications",
        "Specification Matrix",
        "Coverage Summary",
        "Gap Analysis",
        "Product Requirement Draft",
        "Supplier Follow-up Questions",
        "Decision Summary",
        "Product Readiness Summary",
        "Supplier Comparison",
        "Product Pool Summary",
        "Fetch Logs",
        "Issues",
    ]

    products = pd.read_excel(BytesIO(workbook), sheet_name="Products", engine="openpyxl")
    specs = pd.read_excel(BytesIO(workbook), sheet_name="Raw Specifications", engine="openpyxl")
    normalized = pd.read_excel(
        BytesIO(workbook),
        sheet_name="Normalized Specifications",
        engine="openpyxl",
    )
    matrix = pd.read_excel(
        BytesIO(workbook),
        sheet_name="Specification Matrix",
        engine="openpyxl",
    )
    coverage = pd.read_excel(
        BytesIO(workbook),
        sheet_name="Coverage Summary",
        engine="openpyxl",
    )
    gaps = pd.read_excel(
        BytesIO(workbook),
        sheet_name="Gap Analysis",
        engine="openpyxl",
    )

    assert products.loc[0, "title"] == "Wireless Backup Camera"
    assert specs.loc[0, "spec_name"] == "Resolution"
    assert normalized.loc[0, "standard_field"] == "resolution"
    assert "resolution" in matrix.columns
    assert "coverage_rate" in coverage.columns
    assert "risk_level" in gaps.columns
