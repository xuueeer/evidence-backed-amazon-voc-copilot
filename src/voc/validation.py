from __future__ import annotations

from io import BytesIO, StringIO
from os import PathLike
from pathlib import Path
from typing import IO, Any

import pandas as pd

from .models import (
    ReviewRecord,
    ReviewValidationReport,
    ReviewValidationResult,
    ValidationIssue,
)


REQUIRED_REVIEW_COLUMNS = (
    "review_id",
    "product_id",
    "rating",
    "review_text",
    "review_date",
    "source_type",
)


class ReviewValidationError(ValueError):
    """Raised when a review file cannot satisfy the review schema."""


def _is_blank(value: Any) -> bool:
    if value is None:
        return True
    try:
        if bool(pd.isna(value)):
            return True
    except (TypeError, ValueError):
        pass
    return str(value).strip() == ""


def _display_value(value: Any) -> str:
    return "(blank)" if _is_blank(value) else str(value)


def _parse_rating(value: Any) -> float | None:
    if _is_blank(value):
        return None
    match = pd.Series([str(value)], dtype="string").str.extract(
        r"([-+]?(?:\d+(?:\.\d*)?|\.\d+))", expand=False
    )
    parsed = pd.to_numeric(match, errors="coerce").iloc[0]
    if pd.isna(parsed):
        return None
    rating = float(parsed)
    return rating if 1 <= rating <= 5 else None


def _parse_date(value: Any) -> tuple[str | None, bool]:
    if _is_blank(value):
        return None, True
    parsed = pd.to_datetime(value, errors="coerce", utc=True)
    if pd.isna(parsed):
        return None, False
    return parsed.date().isoformat(), True


def _normalize_columns(frame: pd.DataFrame) -> pd.DataFrame:
    data = frame.copy()
    data.columns = [str(column).strip().lower() for column in data.columns]
    if data.columns.duplicated().any():
        duplicates = sorted(set(data.columns[data.columns.duplicated()].tolist()))
        raise ReviewValidationError(
            "Duplicate columns after normalization: " + ", ".join(duplicates)
        )
    missing = [
        column for column in REQUIRED_REVIEW_COLUMNS if column not in data.columns
    ]
    if missing:
        raise ReviewValidationError(
            "Missing required review columns: " + ", ".join(missing)
        )
    return data


def validate_review_dataframe(frame: pd.DataFrame) -> ReviewValidationResult:
    """Validate and normalize review rows, retaining the first duplicate ID."""

    if not isinstance(frame, pd.DataFrame):
        raise TypeError("frame must be a pandas DataFrame")
    data = _normalize_columns(frame)
    issues: list[ValidationIssue] = []
    records: list[ReviewRecord] = []
    seen_review_ids: set[str] = set()
    rejected_rows: set[int] = set()
    duplicate_count = 0
    blank_review_count = 0
    invalid_rating_count = 0

    for position, (_, row) in enumerate(data.iterrows(), start=2):
        raw_review_id = row.get("review_id")
        review_id = "" if _is_blank(raw_review_id) else str(raw_review_id).strip()

        if review_id and review_id in seen_review_ids:
            duplicate_count += 1
            rejected_rows.add(position)
            issues.append(
                ValidationIssue(
                    row_number=position,
                    severity="warning",
                    field="review_id",
                    error_code="duplicate_review_id",
                    raw_value=_display_value(raw_review_id),
                    message="Duplicate review_id; only the first row was retained.",
                )
            )
            continue
        if review_id:
            seen_review_ids.add(review_id)

        row_errors = False
        if not review_id:
            row_errors = True
            issues.append(
                ValidationIssue(
                    position,
                    "error",
                    "review_id",
                    "missing_review_id",
                    "review_id is required; the row was rejected.",
                    _display_value(raw_review_id),
                )
            )

        raw_product_id = row.get("product_id")
        product_id = "" if _is_blank(raw_product_id) else str(raw_product_id).strip()
        if not product_id:
            row_errors = True
            issues.append(
                ValidationIssue(
                    position,
                    "error",
                    "product_id",
                    "missing_product_id",
                    "product_id is required; the row was rejected.",
                    _display_value(raw_product_id),
                )
            )

        raw_text = row.get("review_text")
        review_text = "" if _is_blank(raw_text) else " ".join(str(raw_text).split())
        if not review_text:
            row_errors = True
            blank_review_count += 1
            issues.append(
                ValidationIssue(
                    position,
                    "error",
                    "review_text",
                    "blank_review_text",
                    "Blank review text was filtered out.",
                    _display_value(raw_text),
                )
            )

        raw_rating = row.get("rating")
        rating = _parse_rating(raw_rating)
        if rating is None:
            row_errors = True
            invalid_rating_count += 1
            issues.append(
                ValidationIssue(
                    position,
                    "error",
                    "rating",
                    "invalid_rating",
                    "rating must be a number from 1 through 5; the row was rejected.",
                    _display_value(raw_rating),
                )
            )

        review_date, date_is_valid = _parse_date(row.get("review_date"))
        if not date_is_valid:
            issues.append(
                ValidationIssue(
                    position,
                    "warning",
                    "review_date",
                    "invalid_review_date",
                    "review_date could not be parsed and was set to null.",
                    _display_value(row.get("review_date")),
                )
            )

        raw_source_type = row.get("source_type")
        source_type_is_blank = _is_blank(raw_source_type)
        source_type = (
            "unknown"
            if source_type_is_blank
            else str(raw_source_type).strip()
        )
        if source_type_is_blank:
            issues.append(
                ValidationIssue(
                    position,
                    "warning",
                    "source_type",
                    "blank_source_type",
                    "Blank source_type was normalized to 'unknown'.",
                    _display_value(raw_source_type),
                )
            )

        if row_errors:
            rejected_rows.add(position)
            continue

        records.append(
            ReviewRecord(
                review_id=review_id,
                product_id=product_id,
                rating=rating,
                review_text=review_text,
                review_date=review_date,
                source_type=source_type,
            )
        )

    report = ReviewValidationReport(
        input_rows=int(len(data)),
        valid_rows=len(records),
        rejected_rows=len(rejected_rows),
        duplicate_review_ids=duplicate_count,
        blank_reviews=blank_review_count,
        invalid_ratings=invalid_rating_count,
    )
    return ReviewValidationResult(records=records, issues=issues, report=report)


def _read_csv_frame(
    source: str | bytes | PathLike[str] | IO[str] | IO[bytes],
    *,
    encoding: str,
) -> pd.DataFrame:
    if isinstance(source, bytes):
        try:
            text = source.decode(encoding)
        except UnicodeDecodeError:
            text = source.decode("gb18030")
        return pd.read_csv(StringIO(text))
    if isinstance(source, PathLike):
        return pd.read_csv(Path(source), encoding=encoding)
    if isinstance(source, str):
        if "\n" in source or "\r" in source:
            return pd.read_csv(StringIO(source))
        return pd.read_csv(source, encoding=encoding)
    if isinstance(source, BytesIO):
        position = source.tell()
        try:
            return pd.read_csv(source, encoding=encoding)
        except UnicodeDecodeError:
            source.seek(position)
            return pd.read_csv(source, encoding="gb18030")
    return pd.read_csv(source)


def read_review_csv(
    source: str | bytes | PathLike[str] | IO[str] | IO[bytes],
    *,
    encoding: str = "utf-8-sig",
) -> ReviewValidationResult:
    """Read a CSV source and return normalized review records plus row issues."""

    try:
        frame = _read_csv_frame(source, encoding=encoding)
    except (
        OSError,
        UnicodeError,
        pd.errors.EmptyDataError,
        pd.errors.ParserError,
    ) as exc:
        raise ReviewValidationError(f"Could not read review CSV: {exc}") from exc
    return validate_review_dataframe(frame)


validate_reviews = validate_review_dataframe
