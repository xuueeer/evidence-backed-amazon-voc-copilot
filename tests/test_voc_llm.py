from __future__ import annotations

import json
from datetime import date

import httpx
import pytest

import src.voc_llm as voc_llm
from src.voc_llm import (
    VocLLMError,
    analysis_result_from_structured_insights,
    extract_analysis_result,
    extract_structured_insights,
    parse_structured_response,
    validate_structured_response,
)
from src.voc.models import AnalysisResult


@pytest.fixture(autouse=True)
def resolve_test_endpoints_to_public_ip(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep HTTP mock tests offline while exercising production URL validation."""

    monkeypatch.setenv(
        "VOC_LLM_ALLOWED_HOSTS",
        ",".join(
            [
                "api.example.com",
                "llm.example.test",
                "missing.example.test",
                "mixed.example.test",
                "unsafe.example.test",
            ]
        ),
    )
    monkeypatch.setattr(
        voc_llm.socket,
        "getaddrinfo",
        lambda _host, port, *, type: [
            (voc_llm.socket.AF_INET, type, 6, "", ("8.8.8.8", port))
        ],
    )


def sample_reviews() -> list[dict[str, object]]:
    return [
        {
            "review_id": "R-001",
            "product_id": "P-01",
            "rating": 2,
            "review_text": "The earbuds become loose while running.",
            "review_date": date(2026, 1, 3),
            "source_type": "sample",
        },
        {
            "review_id": "R-002",
            "product_id": "P-02",
            "rating": 5,
            "review_text": "They stayed secure throughout my workout.",
            "review_date": "2026-01-05",
            "source_type": "sample",
        },
    ]


def valid_payload() -> dict[str, object]:
    return {
        "insights": [
            {
                "insight_id": "I-001",
                "claim": "Fit varies during exercise.",
                "type": "inference",
                "topic": "fit_comfort",
                "supporting_review_ids": ["R-001"],
                "contradicting_review_ids": ["R-002"],
                "assumptions": ["Workout intensity is not normalized."],
            }
        ],
        "recommendations": [
            {
                "action": "Test more ear-tip sizes.",
                "rationale": "Fit evidence is mixed.",
                "evidence_refs": ["R-001", "R-002"],
                "risk_flags": ["Small sample"],
                "unknowns": ["Ear shape and workout type"],
            }
        ],
    }


def completion_response(content: str, request: httpx.Request) -> httpx.Response:
    return httpx.Response(
        200,
        request=request,
        json={"choices": [{"message": {"content": content}}]},
    )


def test_extract_posts_normalized_reviews_to_configured_endpoint() -> None:
    captured: dict[str, object] = {}
    secret = "sk-session-only"

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["authorization"] = request.headers.get("authorization")
        captured["body"] = json.loads(request.content)
        return completion_response(json.dumps(valid_payload()), request)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = extract_structured_insights(
            sample_reviews(),
            api_key=secret,
            base_url="https://llm.example.test/v1/",
            model="example-json-model",
            client=client,
        )

    assert result == valid_payload()
    assert captured["url"] == "https://llm.example.test/v1/chat/completions"
    assert captured["authorization"] == f"Bearer {secret}"
    body = captured["body"]
    assert isinstance(body, dict)
    assert body["model"] == "example-json-model"
    assert body["temperature"] == 0
    assert body["response_format"] == {"type": "json_object"}
    system_prompt = body["messages"][0]["content"]
    assert "topic" in system_prompt
    assert "Do not return recommendations" in system_prompt
    assert "deterministic application code" in system_prompt
    prompt = body["messages"][1]["content"]
    assert secret not in prompt
    prompt_reviews = json.loads(prompt)["reviews"]
    assert prompt_reviews[0]["review_id"] == "R-001"
    assert prompt_reviews[0]["review_date"] == "2026-01-03"
    assert set(prompt_reviews[0]) == {
        "review_id",
        "product_id",
        "rating",
        "review_text",
        "review_date",
        "source_type",
    }


def test_extract_resolves_endpoint_host_and_port(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resolved: list[tuple[str, int]] = []

    def resolver(host: str, port: int, *, type: int) -> list[tuple[object, ...]]:
        resolved.append((host, port))
        return [
            (voc_llm.socket.AF_INET, type, 6, "", ("8.8.8.8", port)),
            (
                voc_llm.socket.AF_INET6,
                type,
                6,
                "",
                ("2606:4700:4700::1111", port, 0, 0),
            ),
        ]

    def handler(request: httpx.Request) -> httpx.Response:
        return completion_response(json.dumps(valid_payload()), request)

    monkeypatch.setattr(voc_llm.socket, "getaddrinfo", resolver)
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        extract_structured_insights(
            sample_reviews(),
            api_key="temporary",
            base_url="https://llm.example.test:8443/v1",
            client=client,
        )

    assert resolved == [("llm.example.test", 8443)]


@pytest.mark.parametrize(
    "base_url",
    [
        "http://api.example.com/v1",
        "ftp://api.example.com/v1",
        "//api.example.com/v1",
    ],
)
def test_extract_rejects_non_https_endpoints_before_request(base_url: str) -> None:
    called = False

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return completion_response(json.dumps(valid_payload()), request)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(VocLLMError, match="HTTPS"):
            extract_structured_insights(
                sample_reviews(),
                api_key="temporary",
                base_url=base_url,
                client=client,
            )

    assert called is False


@pytest.mark.parametrize(
    "resolved_address",
    [
        "127.0.0.1",
        "10.0.0.1",
        "169.254.169.254",
        "224.0.0.1",
        "240.0.0.1",
        "0.0.0.0",
        "100.64.0.1",
        "192.0.2.1",
        "::1",
        "fc00::1",
        "fe80::1",
        "ff02::1",
        "2001:db8::1",
        "::",
        "::ffff:127.0.0.1",
    ],
)
def test_extract_rejects_non_global_resolved_addresses_before_request(
    resolved_address: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called = False

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return completion_response(json.dumps(valid_payload()), request)

    monkeypatch.setattr(
        voc_llm,
        "_resolve_host_addresses",
        lambda _host, _port: {resolved_address},
    )
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(VocLLMError, match="globally routable"):
            extract_structured_insights(
                sample_reviews(),
                api_key="temporary",
                base_url="https://unsafe.example.test/v1",
                client=client,
            )

    assert called is False


@pytest.mark.parametrize(
    "base_url",
    [
        "https://127.0.0.1/v1",
        "https://169.254.169.254/latest",
        "https://[::1]/v1",
        "https://[fe80::1]/v1",
    ],
)
def test_extract_rejects_direct_non_global_ip_endpoints_before_request(
    base_url: str,
) -> None:
    called = False

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return completion_response(json.dumps(valid_payload()), request)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(VocLLMError, match="globally routable"):
            extract_structured_insights(
                sample_reviews(),
                api_key="temporary",
                base_url=base_url,
                client=client,
            )

    assert called is False


def test_extract_rejects_hostname_with_mixed_public_and_private_dns_answers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        voc_llm,
        "_resolve_host_addresses",
        lambda _host, _port: {"8.8.8.8", "10.0.0.8"},
    )

    with httpx.Client(transport=httpx.MockTransport(lambda request: None)) as client:
        with pytest.raises(VocLLMError, match="globally routable"):
            extract_structured_insights(
                sample_reviews(),
                api_key="temporary",
                base_url="https://mixed.example.test/v1",
                client=client,
            )


def test_extract_rejects_unresolvable_hostname_before_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def resolver(_host: str, _port: int, *, type: int) -> list[tuple[object, ...]]:
        raise voc_llm.socket.gaierror("name not known")

    monkeypatch.setattr(voc_llm.socket, "getaddrinfo", resolver)

    with httpx.Client(transport=httpx.MockTransport(lambda request: None)) as client:
        with pytest.raises(VocLLMError, match="could not be resolved"):
            extract_structured_insights(
                sample_reviews(),
                api_key="temporary",
                base_url="https://missing.example.test/v1",
                client=client,
            )


def test_extract_rejects_redirect_without_following_it() -> None:
    requests: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(str(request.url))
        return httpx.Response(
            302,
            request=request,
            headers={"location": "https://127.0.0.1/latest/meta-data/"},
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(VocLLMError, match="redirect"):
            extract_structured_insights(
                sample_reviews(), api_key="temporary", client=client
            )

    assert requests == ["https://api.openai.com/v1/chat/completions"]


@pytest.mark.parametrize(
    "base_url",
    [
        "https://user:password@api.example.com/v1",
        "https://api.example.com/v1#fragment",
    ],
)
def test_extract_rejects_ambiguous_endpoint_authority_before_request(
    base_url: str,
) -> None:
    with httpx.Client(transport=httpx.MockTransport(lambda request: None)) as client:
        with pytest.raises(VocLLMError, match="credentials|fragment"):
            extract_structured_insights(
                sample_reviews(),
                api_key="temporary",
                base_url=base_url,
                client=client,
            )


def test_extract_rejects_public_host_not_enabled_by_operator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("VOC_LLM_ALLOWED_HOSTS", "")

    with httpx.Client(transport=httpx.MockTransport(lambda request: None)) as client:
        with pytest.raises(VocLLMError, match="not enabled"):
            extract_structured_insights(
                sample_reviews(),
                api_key="temporary",
                base_url="https://unapproved.example.test/v1",
                client=client,
            )


def test_extract_accepts_json_code_fence() -> None:
    fenced = f"```json\n{json.dumps(valid_payload())}\n```"

    def handler(request: httpx.Request) -> httpx.Response:
        return completion_response(fenced, request)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = extract_structured_insights(
            sample_reviews(), api_key="temporary", client=client
        )

    assert result["insights"][0]["insight_id"] == "I-001"


@pytest.mark.parametrize(
    "content",
    [
        "not JSON",
        "```json\n{broken}\n```",
        "[]",
        "",
    ],
)
def test_parse_rejects_malformed_or_non_object_json(content: str) -> None:
    with pytest.raises(VocLLMError, match="JSON|empty"):
        parse_structured_response(content)


def test_validation_rejects_invalid_insight_type() -> None:
    payload = valid_payload()
    payload["insights"][0]["type"] = "opinion"

    with pytest.raises(VocLLMError, match="fact, inference, unknown"):
        validate_structured_response(payload, {"R-001", "R-002"})


@pytest.mark.parametrize(
    ("section", "field"),
    [
        ("insights", "supporting_review_ids"),
        ("insights", "contradicting_review_ids"),
        ("recommendations", "evidence_refs"),
    ],
)
def test_validation_rejects_unknown_review_references(
    section: str, field: str
) -> None:
    payload = valid_payload()
    payload[section][0][field] = ["R-missing"]

    with pytest.raises(VocLLMError, match="unknown review ID.*R-missing"):
        validate_structured_response(payload, {"R-001", "R-002"})


def test_extract_rejects_invalid_completion_envelope() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, request=request, json={"choices": []})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(VocLLMError, match=r"choices\[0\]"):
            extract_structured_insights(
                sample_reviews(), api_key="temporary", client=client
            )


def test_http_error_is_sanitized_and_does_not_expose_api_key() -> None:
    secret = "sk-never-in-errors"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            401,
            request=request,
            json={"error": {"message": f"bad key {secret}"}},
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(VocLLMError, match="HTTP 401") as captured:
            extract_structured_insights(
                sample_reviews(), api_key=secret, client=client
            )

    assert secret not in str(captured.value)


def test_duplicate_input_review_ids_are_rejected_before_request() -> None:
    reviews = sample_reviews()
    reviews[1]["review_id"] = "R-001"
    called = False

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return completion_response(json.dumps(valid_payload()), request)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(VocLLMError, match="Duplicate review_id"):
            extract_structured_insights(
                reviews, api_key="temporary", client=client
            )

    assert called is False


def adapter_reviews() -> list[dict[str, object]]:
    return [
        {
            "review_id": "S-1",
            "product_id": "P-1",
            "rating": 1,
            "review_text": "Loose during running.",
            "review_date": "2026-02-01",
            "source_type": "test",
        },
        {
            "review_id": "S-2",
            "product_id": "P-2",
            "rating": 2,
            "review_text": "The fit hurts.",
            "review_date": "2026-02-02",
            "source_type": "test",
        },
        {
            "review_id": "S-3",
            "product_id": "P-3",
            "rating": 2,
            "review_text": "The buds slip out.",
            "review_date": "2026-02-03",
            "source_type": "test",
        },
        {
            "review_id": "C-1",
            "product_id": "P-4",
            "rating": 5,
            "review_text": "Secure throughout a workout.",
            "review_date": "2026-02-04",
            "source_type": "test",
        },
    ]


def extracted_fit_payload() -> dict[str, object]:
    return {
        "insights": [
            {
                "claim": "Fit problems recur during exercise.",
                "type": "inference",
                "topic": "fit_comfort",
                "supporting_review_ids": ["S-1", "S-2", "S-2", "S-3"],
                "contradicting_review_ids": ["C-1"],
                # These untrusted values must never enter AnalysisResult.
                "support_count": 999,
                "product_count": 999,
                "evidence_coverage": 9.99,
                "evidence_strength": "high",
                "unknowns": ["model-authored unknown"],
            }
        ],
        "recommendations": [
            {
                "action": "Use the model recommendation verbatim.",
                "rationale": "The model says so.",
                "evidence_refs": [],
                "risk_flags": [],
                "unknowns": [],
            }
        ],
    }


def test_adapter_recomputes_all_metrics_and_recommendation_gate() -> None:
    result = analysis_result_from_structured_insights(
        adapter_reviews(), extracted_fit_payload()
    )

    assert isinstance(result, AnalysisResult)
    assert len(result.insights) == 1
    insight = result.insights[0]
    assert insight.insight_id == "llm-fit-comfort-1"
    assert insight.topic == "fit_comfort"
    assert insight.supporting_review_ids == ["S-1", "S-2", "S-3"]
    assert insight.support_count == 3
    assert insight.contradiction_count == 1
    assert insight.product_count == 4
    assert insight.evidence_coverage == 1.0
    assert insight.evidence_strength == "medium"
    assert "model-authored unknown" not in insight.unknowns
    assert result.evidence_coverage == 1.0
    assert result.decision_status == "ready"

    assert len(result.recommendations) == 1
    recommendation = result.recommendations[0]
    assert recommendation.action != "Use the model recommendation verbatim."
    assert recommendation.evidence_refs == ["S-1", "S-2", "S-3"]
    assert set(recommendation.evidence_refs) <= {
        review.review_id for review in result.reviews
    }


def test_adapter_downgrades_low_evidence_and_discards_model_recommendation() -> None:
    payload = {
        "insights": [
            {
                "claim": "Portability is a recurring pain point.",
                "type": "fact",
                "topic": "portability",
                "supporting_review_ids": ["R-001"],
                "contradicting_review_ids": [],
            }
        ],
        "recommendations": [
            {
                "action": "Launch a smaller version.",
                "rationale": "One review mentioned it.",
                "evidence_refs": [],
                "risk_flags": [],
                "unknowns": [],
            }
        ],
    }

    result = analysis_result_from_structured_insights(sample_reviews(), payload)

    assert result.insights[0].type == "unknown"
    assert result.insights[0].evidence_strength == "insufficient"
    assert "Fewer than 2" in " ".join(result.insights[0].unknowns)
    assert result.recommendations == []
    assert result.decision_status == "insufficient_evidence"


def test_adapter_accepts_minimal_new_schema_and_legacy_missing_topic() -> None:
    payload = {
        "insights": [
            {
                "claim": "The theme needs more evidence.",
                "type": "unknown",
                "supporting_review_ids": [],
                "contradicting_review_ids": [],
            }
        ]
    }

    result = analysis_result_from_structured_insights(sample_reviews(), payload)

    assert result.insights[0].topic == "unclassified"
    assert result.insights[0].type == "unknown"
    assert result.recommendations == []


def test_validation_rejects_review_cited_on_both_sides() -> None:
    payload = {
        "insights": [
            {
                "claim": "Fit evidence is mixed.",
                "type": "inference",
                "topic": "fit_comfort",
                "supporting_review_ids": ["R-001"],
                "contradicting_review_ids": ["R-001"],
            }
        ]
    }

    with pytest.raises(VocLLMError, match="both evidence sides"):
        validate_structured_response(payload, {"R-001", "R-002"})


def test_extract_analysis_result_returns_deterministic_model() -> None:
    payload = {
        "insights": [
            {
                "claim": "Fit evidence is mixed.",
                "type": "inference",
                "topic": "fit_comfort",
                "supporting_review_ids": ["R-001"],
                "contradicting_review_ids": ["R-002"],
            }
        ]
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return completion_response(json.dumps(payload), request)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = extract_analysis_result(
            sample_reviews(), api_key="temporary", client=client
        )

    assert isinstance(result, AnalysisResult)
    assert result.insights[0].support_count == 1
    assert result.insights[0].contradiction_count == 1
    assert result.insights[0].type == "unknown"
    assert result.decision_status == "insufficient_evidence"
