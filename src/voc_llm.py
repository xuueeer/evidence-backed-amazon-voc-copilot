"""Optional OpenAI-compatible extraction for normalized VOC reviews.

This module deliberately stops at extracting and validating model-provided
labels and references. Evidence counts, strength ratings, and recommendations
that drive business decisions belong to the deterministic VOC engine.
"""

from __future__ import annotations

import ipaddress
import json
import math
import os
import re
import socket
from collections.abc import Mapping, Sequence
from datetime import date, datetime
from typing import Any
from urllib.parse import urlsplit

import httpx

from src.voc.analysis import (
    EVIDENCE_STRENGTH_RULES,
    TOPICS,
    classify_evidence_strength,
)
from src.voc.models import AnalysisResult, Insight, Recommendation, ReviewRecord


DEFAULT_BASE_URL = "https://api.openai.com/v1"
DEFAULT_MODEL = "gpt-4o-mini"
DEFAULT_ALLOWED_ENDPOINT_HOSTS = frozenset({"api.openai.com"})
ALLOWED_INSIGHT_TYPES = frozenset({"fact", "inference", "unknown"})
_REVIEW_FIELDS = (
    "review_id",
    "product_id",
    "rating",
    "review_text",
    "review_date",
    "source_type",
)
_FENCED_JSON_RE = re.compile(
    r"^```(?:json)?\s*(?P<payload>.*?)\s*```$",
    flags=re.IGNORECASE | re.DOTALL,
)


class VocLLMError(RuntimeError):
    """Raised when an LLM request or structured response cannot be trusted."""


def extract_structured_insights(
    reviews: Sequence[Mapping[str, Any] | object],
    *,
    api_key: str,
    base_url: str = DEFAULT_BASE_URL,
    model: str = DEFAULT_MODEL,
    client: httpx.Client | None = None,
    timeout: float = 30.0,
) -> dict[str, Any]:
    """Extract structured VOC labels through an OpenAI-compatible endpoint.

    ``api_key`` is intentionally accepted only for this call. It is placed in
    the request authorization header and is never attached to an object,
    returned, or logged. An injected ``client`` is useful for tests and for
    callers that already manage connection pooling.
    """

    if not isinstance(api_key, str) or not api_key.strip():
        raise VocLLMError("An API key is required for BYOK extraction.")
    if not isinstance(base_url, str) or not base_url.strip():
        raise VocLLMError("A non-empty OpenAI-compatible base URL is required.")
    if not isinstance(model, str) or not model.strip():
        raise VocLLMError("A non-empty model name is required.")

    normalized_reviews = _normalize_reviews(reviews)
    review_ids = {review["review_id"] for review in normalized_reviews}
    request_body = {
        "model": model.strip(),
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": _system_prompt()},
            {
                "role": "user",
                "content": json.dumps(
                    {"reviews": normalized_reviews},
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
            },
        ],
    }
    headers = {
        "Authorization": f"Bearer {api_key.strip()}",
        "Content-Type": "application/json",
    }
    endpoint = _validated_chat_completions_url(base_url)

    try:
        if client is None:
            with httpx.Client(timeout=timeout) as owned_client:
                response = owned_client.post(
                    endpoint,
                    headers=headers,
                    json=request_body,
                    follow_redirects=False,
                )
        else:
            response = client.post(
                endpoint,
                headers=headers,
                json=request_body,
                timeout=timeout,
                follow_redirects=False,
            )
        if response.is_redirect:
            raise VocLLMError(
                "The OpenAI-compatible endpoint returned a redirect, which is "
                "not followed for security reasons."
            )
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise VocLLMError(
            f"The OpenAI-compatible endpoint returned HTTP {exc.response.status_code}."
        ) from exc
    except httpx.HTTPError as exc:
        raise VocLLMError("The OpenAI-compatible request failed.") from exc

    content = _extract_message_content(response)
    payload = parse_structured_response(content)
    validate_structured_response(payload, review_ids)
    return payload


def extract_analysis_result(
    reviews: Sequence[Mapping[str, Any] | object],
    *,
    api_key: str,
    base_url: str = DEFAULT_BASE_URL,
    model: str = DEFAULT_MODEL,
    client: httpx.Client | None = None,
    timeout: float = 30.0,
) -> AnalysisResult:
    """Run BYOK extraction and deterministically build an evidence ledger."""

    payload = extract_structured_insights(
        reviews,
        api_key=api_key,
        base_url=base_url,
        model=model,
        client=client,
        timeout=timeout,
    )
    return analysis_result_from_structured_insights(reviews, payload)


def analysis_result_from_structured_insights(
    reviews: Sequence[Mapping[str, Any] | object],
    payload: Mapping[str, Any],
) -> AnalysisResult:
    """Convert validated LLM labels into deterministic ``AnalysisResult`` data.

    The model supplies only claims, topic labels, claim types, and review IDs.
    Every metric, evidence tier, unknown, recommendation, and decision status is
    recomputed here from the current review set. Model-provided values for those
    fields are intentionally ignored.
    """

    normalized_reviews = _normalize_reviews(reviews)
    records = _review_records(normalized_reviews)
    review_by_id = {review.review_id: review for review in records}
    validate_structured_response(payload, set(review_by_id))

    insights: list[Insight] = []
    recommendations: list[Recommendation] = []
    all_evidence_ids: set[str] = set()
    total_reviews = len(records)
    topic_actions = {topic.key: topic.action for topic in TOPICS}

    for index, extracted in enumerate(_require_object_list(payload, "insights")):
        context = f"insights[{index}]"
        claim = _require_non_empty_string(extracted, "claim", context)
        extracted_type = _require_non_empty_string(extracted, "type", context)
        topic = _optional_topic(extracted)
        supporting = _unique_strings(
            _require_string_list(extracted, "supporting_review_ids", context)
        )
        contradicting = _unique_strings(
            _require_string_list(extracted, "contradicting_review_ids", context)
        )

        evidence_ids = set(supporting) | set(contradicting)
        all_evidence_ids.update(evidence_ids)
        product_count = len(
            {review_by_id[review_id].product_id for review_id in evidence_ids}
        )
        coverage = len(evidence_ids) / total_reviews if total_reviews else 0.0
        support_count = len(supporting)
        contradiction_count = len(contradicting)
        strength = classify_evidence_strength(
            support_count=support_count,
            contradiction_count=contradiction_count,
            product_count=product_count,
            coverage=coverage,
        )
        unknowns = _deterministic_unknowns(
            extracted_type=extracted_type,
            support_count=support_count,
            contradiction_count=contradiction_count,
            product_count=product_count,
            coverage=coverage,
        )
        blocked = (
            extracted_type == "unknown"
            or strength == "insufficient"
            or (
                contradiction_count >= support_count
                and contradiction_count > 0
            )
        )
        final_type = "unknown" if blocked else extracted_type
        insight_id = f"llm-{_topic_slug(topic)}-{index + 1}"
        insight = Insight(
            insight_id=insight_id,
            claim=claim,
            type=final_type,
            supporting_review_ids=supporting,
            contradicting_review_ids=contradicting,
            support_count=support_count,
            contradiction_count=contradiction_count,
            evidence_strength=strength,
            assumptions=[
                "The claim, topic, type, and evidence polarity were extracted by an LLM.",
                "Every review reference was validated against the current input.",
                "Evidence strength is a deterministic rule tier, not a probability.",
            ],
            topic=topic,
            product_count=product_count,
            evidence_coverage=round(coverage, 4),
            unknowns=unknowns,
        )
        insights.append(insight)

        # Recommendations are generated from validated supporting evidence only.
        # Model-provided recommendation text is never promoted into the ledger.
        if final_type != "unknown" and supporting:
            risk_flags = ["llm_extracted_evidence"]
            if contradicting:
                risk_flags.append("contradicting_reviews_present")
            if product_count < 2:
                risk_flags.append("single_product_evidence")
            action = topic_actions.get(
                topic,
                (
                    f'Validate the reported "{topic}" issue across representative '
                    "use cases and define measurable supplier acceptance criteria."
                ),
            )
            recommendations.append(
                Recommendation(
                    action=action,
                    rationale=(
                        f"{support_count} of {total_reviews} valid reviews support "
                        f"the {topic} claim across {product_count} product(s); "
                        f"{contradiction_count} review(s) contradict it."
                    ),
                    evidence_refs=list(supporting),
                    risk_flags=risk_flags,
                    unknowns=unknowns,
                )
            )

    overall_coverage = (
        len(all_evidence_ids) / total_reviews if total_reviews else 0.0
    )
    if recommendations and all(insight.type != "unknown" for insight in insights):
        decision_status = "ready"
    elif recommendations:
        decision_status = "partial_evidence"
    else:
        decision_status = "insufficient_evidence"

    return AnalysisResult(
        reviews=records,
        insights=insights,
        recommendations=recommendations,
        evidence_coverage=round(overall_coverage, 4),
        decision_status=decision_status,
        evidence_rules=dict(EVIDENCE_STRENGTH_RULES),
    )


def parse_structured_response(content: str) -> dict[str, Any]:
    """Parse either raw JSON or one complete Markdown JSON code fence."""

    if not isinstance(content, str) or not content.strip():
        raise VocLLMError("The model returned empty content instead of JSON.")

    candidate = content.strip()
    fenced = _FENCED_JSON_RE.fullmatch(candidate)
    if fenced:
        candidate = fenced.group("payload").strip()

    try:
        payload = json.loads(candidate)
    except (json.JSONDecodeError, TypeError) as exc:
        raise VocLLMError("The model response is not valid JSON.") from exc

    if not isinstance(payload, dict):
        raise VocLLMError("The model response must be a JSON object.")
    return payload


def validate_structured_response(
    payload: Mapping[str, Any], review_ids: set[str] | frozenset[str],
) -> None:
    """Validate the extraction schema and every cited source review ID."""

    if not isinstance(payload, Mapping):
        raise VocLLMError("The structured response must be a JSON object.")
    known_review_ids = {str(review_id) for review_id in review_ids}
    insights = _require_object_list(payload, "insights")
    recommendations_value = payload.get("recommendations", [])
    if not isinstance(recommendations_value, list) or any(
        not isinstance(item, Mapping) for item in recommendations_value
    ):
        raise VocLLMError("recommendations must be a JSON array of objects.")
    recommendations = recommendations_value

    seen_insight_ids: set[str] = set()
    for index, insight in enumerate(insights):
        context = f"insights[{index}]"
        insight_id_value = insight.get("insight_id")
        insight_id = ""
        if insight_id_value is not None:
            insight_id = _require_non_empty_string(insight, "insight_id", context)
        _require_non_empty_string(insight, "claim", context)
        insight_type = _require_non_empty_string(insight, "type", context)
        if insight_type not in ALLOWED_INSIGHT_TYPES:
            allowed = ", ".join(sorted(ALLOWED_INSIGHT_TYPES))
            raise VocLLMError(
                f"{context}.type must be one of: {allowed}; got {insight_type!r}."
            )
        if insight_id and insight_id in seen_insight_ids:
            raise VocLLMError(f"Duplicate insight_id in model response: {insight_id!r}.")
        if insight_id:
            seen_insight_ids.add(insight_id)

        topic_value = insight.get("topic")
        if topic_value is not None and (
            not isinstance(topic_value, str) or not topic_value.strip()
        ):
            raise VocLLMError(f"{context}.topic must be a non-empty string.")

        supporting = _require_string_list(
            insight, "supporting_review_ids", context
        )
        contradicting = _require_string_list(
            insight, "contradicting_review_ids", context
        )
        if "assumptions" in insight:
            _require_string_list(insight, "assumptions", context)
        _validate_review_references(
            supporting + contradicting,
            known_review_ids,
            context,
        )
        overlap = sorted(set(supporting) & set(contradicting))
        if overlap:
            overlap_text = ", ".join(repr(reference) for reference in overlap)
            raise VocLLMError(
                f"{context} cites review ID(s) on both evidence sides: "
                f"{overlap_text}."
            )

    for index, recommendation in enumerate(recommendations):
        context = f"recommendations[{index}]"
        _require_non_empty_string(recommendation, "action", context)
        _require_non_empty_string(recommendation, "rationale", context)
        evidence_refs = _require_string_list(
            recommendation, "evidence_refs", context
        )
        _require_string_list(recommendation, "risk_flags", context)
        _require_string_list(recommendation, "unknowns", context)
        _validate_review_references(evidence_refs, known_review_ids, context)


def _normalize_reviews(
    reviews: Sequence[Mapping[str, Any] | object],
) -> list[dict[str, Any]]:
    if isinstance(reviews, (str, bytes)) or not isinstance(reviews, Sequence):
        raise VocLLMError("Reviews must be a sequence of normalized records.")
    if not reviews:
        raise VocLLMError("At least one normalized review is required.")

    normalized: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for index, review in enumerate(reviews):
        record = {field: _review_value(review, field) for field in _REVIEW_FIELDS}
        for field in ("review_id", "product_id", "review_text"):
            value = record[field]
            if value is None or not str(value).strip():
                raise VocLLMError(
                    f"Review at index {index} has no non-empty {field}."
                )
            record[field] = str(value).strip()

        review_id = record["review_id"]
        if review_id in seen_ids:
            raise VocLLMError(f"Duplicate review_id in input: {review_id!r}.")
        seen_ids.add(review_id)

        review_date = record["review_date"]
        if isinstance(review_date, (date, datetime)):
            record["review_date"] = review_date.isoformat()
        elif review_date is not None:
            record["review_date"] = str(review_date)
        if record["source_type"] is not None:
            record["source_type"] = str(record["source_type"])
        normalized.append(record)
    return normalized


def _review_records(normalized_reviews: Sequence[Mapping[str, Any]]) -> list[ReviewRecord]:
    records: list[ReviewRecord] = []
    for index, review in enumerate(normalized_reviews):
        try:
            rating = float(review["rating"])
        except (KeyError, TypeError, ValueError) as exc:
            raise VocLLMError(
                f"Review at index {index} has an invalid normalized rating."
            ) from exc
        if not math.isfinite(rating) or not 1 <= rating <= 5:
            raise VocLLMError(
                f"Review at index {index} has an invalid normalized rating."
            )
        review_date = review.get("review_date")
        source_type = review.get("source_type")
        records.append(
            ReviewRecord(
                review_id=str(review["review_id"]),
                product_id=str(review["product_id"]),
                rating=rating,
                review_text=str(review["review_text"]),
                review_date=None if review_date is None else str(review_date),
                source_type=(
                    "unknown"
                    if source_type is None or not str(source_type).strip()
                    else str(source_type).strip()
                ),
            )
        )
    return records


def _optional_topic(insight: Mapping[str, Any]) -> str:
    topic = insight.get("topic")
    if isinstance(topic, str) and topic.strip():
        return topic.strip()
    # Older responses did not contain topic. Retain compatibility without
    # pretending that the application inferred a real theme.
    return "unclassified"


def _unique_strings(values: Sequence[str]) -> list[str]:
    return list(dict.fromkeys(values))


def _topic_slug(topic: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", topic.lower()).strip("-")
    return slug or "topic"


def _deterministic_unknowns(
    *,
    extracted_type: str,
    support_count: int,
    contradiction_count: int,
    product_count: int,
    coverage: float,
) -> list[str]:
    unknowns: list[str] = []
    minimum_support = int(EVIDENCE_STRENGTH_RULES["minimum_supporting_reviews"])
    minimum_coverage = float(EVIDENCE_STRENGTH_RULES["minimum_topic_coverage"])
    if support_count < minimum_support:
        unknowns.append(
            f"Fewer than {minimum_support} supporting reviews were found."
        )
    if coverage < minimum_coverage:
        unknowns.append(
            f"Topic coverage is below the {minimum_coverage:.0%} decision gate."
        )
    if contradiction_count >= support_count and contradiction_count > 0:
        unknowns.append(
            "Contradicting evidence equals or exceeds supporting evidence."
        )
    if product_count < 2 and support_count > 0:
        unknowns.append("Evidence may be specific to a single product.")
    if extracted_type == "unknown":
        unknowns.append("The extraction labeled this claim as unknown.")
    return unknowns


def _review_value(review: Mapping[str, Any] | object, field: str) -> Any:
    if isinstance(review, Mapping):
        return review.get(field)
    return getattr(review, field, None)


def _validated_chat_completions_url(base_url: str) -> str:
    normalized = base_url.strip().rstrip("/")
    endpoint = (
        normalized
        if normalized.endswith("/chat/completions")
        else f"{normalized}/chat/completions"
    )
    try:
        parsed = urlsplit(endpoint)
        port = parsed.port
    except ValueError as exc:
        raise VocLLMError("The endpoint URL is invalid.") from exc

    if parsed.scheme.lower() != "https":
        raise VocLLMError("The endpoint must use HTTPS.")
    if not parsed.hostname:
        raise VocLLMError("The endpoint URL must include a hostname.")
    if parsed.username is not None or parsed.password is not None:
        raise VocLLMError("The endpoint URL must not contain user credentials.")
    if parsed.fragment:
        raise VocLLMError("The endpoint URL must not contain a fragment.")
    if parsed.query:
        raise VocLLMError("The endpoint URL must not contain a query string.")

    host = parsed.hostname.rstrip(".")
    if not host or "%" in host:
        raise VocLLMError("The endpoint hostname is invalid.")
    try:
        host = host.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise VocLLMError("The endpoint hostname is invalid.") from exc

    try:
        direct_address = ipaddress.ip_address(host)
    except ValueError:
        addresses = _resolve_host_addresses(host, port or 443)
    else:
        addresses = {str(direct_address)}
    if not addresses:
        raise VocLLMError("The endpoint hostname did not resolve to an IP address.")
    for address_text in addresses:
        try:
            address = ipaddress.ip_address(address_text)
        except ValueError as exc:
            raise VocLLMError(
                "The endpoint hostname resolved to an invalid IP address."
            ) from exc
        if not _is_global_address(address):
            raise VocLLMError(
                "The endpoint must resolve only to globally routable public IP addresses."
            )
    allowed_hosts = DEFAULT_ALLOWED_ENDPOINT_HOSTS | {
        value.strip().rstrip(".").lower()
        for value in os.environ.get("VOC_LLM_ALLOWED_HOSTS", "").split(",")
        if value.strip()
    }
    if host.lower() not in allowed_hosts:
        raise VocLLMError(
            "The endpoint host is not enabled by the server operator."
        )
    return endpoint


def _resolve_host_addresses(host: str, port: int) -> set[str]:
    try:
        results = socket.getaddrinfo(
            host,
            port,
            type=socket.SOCK_STREAM,
        )
    except OSError as exc:
        raise VocLLMError("The endpoint hostname could not be resolved.") from exc
    return {str(sockaddr[0]) for *_prefix, sockaddr in results}


def _is_global_address(
    address: ipaddress.IPv4Address | ipaddress.IPv6Address,
) -> bool:
    unsafe = (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
    )
    if isinstance(address, ipaddress.IPv6Address):
        unsafe = unsafe or address.is_site_local
    return address.is_global and not unsafe


def _extract_message_content(response: httpx.Response) -> str:
    try:
        envelope = response.json()
        content = envelope["choices"][0]["message"]["content"]
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise VocLLMError(
            "The endpoint response did not contain choices[0].message.content."
        ) from exc
    if not isinstance(content, str):
        raise VocLLMError("The endpoint returned non-text message content.")
    return content


def _require_object_list(
    payload: Mapping[str, Any], field: str
) -> list[Mapping[str, Any]]:
    value = payload.get(field)
    if not isinstance(value, list) or any(not isinstance(item, Mapping) for item in value):
        raise VocLLMError(f"{field} must be a JSON array of objects.")
    return value


def _require_non_empty_string(
    payload: Mapping[str, Any], field: str, context: str
) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise VocLLMError(f"{context}.{field} must be a non-empty string.")
    return value.strip()


def _require_string_list(
    payload: Mapping[str, Any], field: str, context: str
) -> list[str]:
    value = payload.get(field)
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise VocLLMError(f"{context}.{field} must be a JSON array of strings.")
    return value


def _validate_review_references(
    references: Sequence[str], known_review_ids: set[str], context: str
) -> None:
    unknown = sorted(set(references) - known_review_ids)
    if unknown:
        unknown_text = ", ".join(repr(reference) for reference in unknown)
        raise VocLLMError(
            f"{context} references unknown review ID(s): {unknown_text}."
        )


def _system_prompt() -> str:
    return (
        "You extract customer-voice evidence from normalized product reviews. "
        "Return JSON only, with one top-level array named insights. "
        "Each insight must contain only claim, type, topic, "
        "supporting_review_ids, and contradicting_review_ids. Use a concise, "
        "stable snake_case topic. "
        "The type must be exactly fact, inference, or unknown. "
        "All review reference fields must use only "
        "review_id values present in the supplied records. Show both supporting "
        "and contradicting evidence when present, and never cite one review on "
        "both sides of the same insight. Do not return recommendations, counts, "
        "coverage, evidence strength, unknowns, scores, or profit metrics; "
        "deterministic application code will calculate them."
    )
