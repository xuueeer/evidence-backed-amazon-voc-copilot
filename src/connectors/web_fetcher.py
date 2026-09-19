from __future__ import annotations

import ipaddress
import socket
import time
from urllib.parse import urljoin, urlparse, urlunparse

import httpx

from .models import ConnectorIssue, FetchLog, FetchResult, ProductPageRecord


DEFAULT_TIMEOUT_SECONDS = 12.0
MAX_REDIRECTS = 5
DEFAULT_USER_AGENT = (
    "kirrrto-product-research-bot/0.2 "
    "(public product page connector; contact via GitHub)"
)


class WebFetchError(ValueError):
    """Raised when a URL is invalid or cannot be fetched."""


def normalize_url(raw_url: str) -> str:
    """Normalize a user-supplied URL while preserving path and query string."""

    value = str(raw_url or "").strip()
    if not value:
        raise WebFetchError("URL is empty.")

    parsed = urlparse(value)
    if not parsed.scheme:
        parsed = urlparse("https://" + value)

    scheme = parsed.scheme.lower()
    if scheme not in {"http", "https"}:
        raise WebFetchError(
            f"Unsupported URL scheme '{parsed.scheme}'. Only http and https are supported."
        )

    if not parsed.netloc:
        raise WebFetchError("URL must include a domain.")

    normalized = parsed._replace(
        scheme=scheme,
        netloc=parsed.netloc.lower(),
        fragment="",
    )
    return urlunparse(normalized)


def validate_public_url(raw_url: str) -> str:
    """Validate that the URL is suitable for the public page connector.

    This function intentionally accepts only http and https URLs. It does not
    attempt to access private network addresses, login-only pages or any
    page that requires bypassing access controls.
    """

    url = normalize_url(raw_url)
    parsed = urlparse(url)
    host = parsed.hostname or ""

    try:
        parsed.port
    except ValueError as exc:
        raise WebFetchError("URL contains an invalid port.") from exc

    if parsed.username is not None or parsed.password is not None:
        raise WebFetchError("URLs containing credentials are not supported.")

    normalized_host = host.rstrip(".").lower()
    if normalized_host == "localhost" or normalized_host.endswith(".localhost"):
        raise WebFetchError("Localhost URLs are not supported by this connector.")

    try:
        address = ipaddress.ip_address(normalized_host)
    except ValueError:
        address = None
    if address is not None and not address.is_global:
        raise WebFetchError("Private or non-public network addresses are not supported.")

    return url


def _validate_resolved_destination(url: str) -> str:
    """Reject hostnames resolving to any non-public network address."""

    validated = validate_public_url(url)
    parsed = urlparse(validated)
    host = parsed.hostname or ""
    port = parsed.port or (443 if parsed.scheme == "https" else 80)

    try:
        resolved = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except (socket.gaierror, UnicodeError) as exc:
        raise WebFetchError("The URL host could not be resolved.") from exc

    addresses = {
        ipaddress.ip_address(sockaddr[0])
        for _family, _type, _proto, _canonname, sockaddr in resolved
    }
    if not addresses or any(not address.is_global for address in addresses):
        raise WebFetchError(
            "The URL resolves to a private or non-public network address."
        )
    return validated


def _get_with_validated_redirects(
    client: httpx.Client,
    url: str,
    *,
    timeout_seconds: float,
) -> httpx.Response:
    """Follow redirects only after validating every destination."""

    current_url = url
    for redirect_count in range(MAX_REDIRECTS + 1):
        current_url = _validate_resolved_destination(current_url)
        response = client.get(
            current_url,
            timeout=timeout_seconds,
            follow_redirects=False,
        )
        if response.status_code not in {301, 302, 303, 307, 308}:
            return response

        location = response.headers.get("location")
        if not location:
            return response
        if redirect_count == MAX_REDIRECTS:
            raise WebFetchError(f"The URL exceeded {MAX_REDIRECTS} redirects.")
        current_url = urljoin(current_url, location)

    raise WebFetchError(f"The URL exceeded {MAX_REDIRECTS} redirects.")


def fetch_url(
    raw_url: str,
    *,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    user_agent: str = DEFAULT_USER_AGENT,
    client: httpx.Client | None = None,
) -> tuple[ProductPageRecord, FetchLog, ConnectorIssue | None, str]:
    """Fetch a single public URL and return an auditable result.

    The returned HTML string is intentionally separate from the record so
    later parser modules can process it without changing fetch metadata.
    """

    started = time.perf_counter()
    html = ""

    try:
        url = validate_public_url(raw_url)
    except WebFetchError as exc:
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        record = ProductPageRecord(
            source_url=str(raw_url),
            status="failed",
            error_message=str(exc),
        )
        log = FetchLog(
            source_url=str(raw_url),
            domain="",
            success=False,
            status_code=None,
            elapsed_ms=elapsed_ms,
            error_message=str(exc),
        )
        issue = ConnectorIssue(
            source_url=str(raw_url),
            severity="error",
            error_code="invalid_url",
            message=str(exc),
        )
        return record, log, issue, html

    parsed = urlparse(url)
    try:
        if client is None:
            with httpx.Client(
                timeout=timeout_seconds,
                follow_redirects=False,
                headers={"User-Agent": user_agent},
            ) as owned_client:
                response = _get_with_validated_redirects(
                    owned_client,
                    url,
                    timeout_seconds=timeout_seconds,
                )
        else:
            response = _get_with_validated_redirects(
                client,
                url,
                timeout_seconds=timeout_seconds,
            )

        elapsed_ms = int((time.perf_counter() - started) * 1000)
        status_code = int(response.status_code)
        success = 200 <= status_code < 400
        content_type = response.headers.get("content-type", "")

        if success and "text/html" not in content_type.lower():
            success = False
            message = (
                "The URL was fetched but did not return an HTML document "
                f"(content-type: {content_type or 'unknown'})."
            )
        elif success:
            message = ""
            html = response.text
        else:
            message = f"HTTP {status_code} returned for URL."

        record = ProductPageRecord(
            source_url=url,
            status="fetched" if success else "failed",
            status_code=status_code,
            error_message=message,
        )
        log = FetchLog(
            source_url=url,
            domain=parsed.netloc.lower(),
            success=success,
            status_code=status_code,
            elapsed_ms=elapsed_ms,
            error_message=message,
        )
        issue = (
            None
            if success
            else ConnectorIssue(
                source_url=url,
                severity="error",
                error_code="fetch_failed",
                message=message,
            )
        )
        return record, log, issue, html

    except httpx.TimeoutException as exc:
        message = f"Request timed out after {timeout_seconds:g} seconds."
    except WebFetchError as exc:
        message = str(exc)
    except httpx.HTTPError as exc:
        message = str(exc)

    elapsed_ms = int((time.perf_counter() - started) * 1000)
    record = ProductPageRecord(
        source_url=url,
        status="failed",
        error_message=message,
    )
    log = FetchLog(
        source_url=url,
        domain=parsed.netloc.lower(),
        success=False,
        status_code=None,
        elapsed_ms=elapsed_ms,
        error_message=message,
    )
    issue = ConnectorIssue(
        source_url=url,
        severity="error",
        error_code="fetch_failed",
        message=message,
    )
    return record, log, issue, html


def fetch_urls(urls: list[str]) -> FetchResult:
    """Fetch user-provided URLs sequentially with explicit error records."""

    result = FetchResult()
    seen: set[str] = set()

    for raw_url in urls:
        if not str(raw_url).strip():
            continue

        try:
            normalized = validate_public_url(raw_url)
        except WebFetchError:
            normalized = str(raw_url).strip()

        if normalized in seen:
            result.issues.append(
                ConnectorIssue(
                    source_url=normalized,
                    severity="warning",
                    error_code="duplicate_url",
                    message="Duplicate URL was skipped.",
                )
            )
            continue
        seen.add(normalized)

        record, log, issue, _html = fetch_url(normalized)
        result.records.append(record)
        result.fetch_logs.append(log)
        if issue is not None:
            result.issues.append(issue)

    return result
