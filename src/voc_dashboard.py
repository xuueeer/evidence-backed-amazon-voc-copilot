from __future__ import annotations

import inspect
import re
from html import escape
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

from src.voc import (
    AnalysisResult,
    ReviewValidationError,
    analysis_to_csv,
    analysis_to_json,
    analysis_to_markdown,
    analyze_reviews,
    read_review_csv,
)
from src.voc_llm import VocLLMError, extract_analysis_result


ROOT = Path(__file__).resolve().parent.parent
SAMPLE_REVIEWS = ROOT / "data" / "sample_reviews.csv"

TOPIC_LABELS = {
    "fit_comfort": {"en": "Fit and comfort", "zh-CN": "佩戴与舒适度"},
    "durability": {"en": "Durability", "zh-CN": "耐用性"},
    "battery": {"en": "Battery life", "zh-CN": "续航表现"},
}

TYPE_LABELS = {
    "fact": {"en": "Fact", "zh-CN": "事实"},
    "inference": {"en": "Inference", "zh-CN": "推断"},
    "unknown": {"en": "Unknown", "zh-CN": "未知"},
}

STRENGTH_LABELS = {
    "insufficient": {"en": "Insufficient", "zh-CN": "证据不足"},
    "low": {"en": "Low", "zh-CN": "较低"},
    "medium": {"en": "Medium", "zh-CN": "中等"},
    "high": {"en": "High", "zh-CN": "较高"},
}

CLAIM_LABELS = {
    "fit_comfort": {
        "inference": "佩戴与舒适度是当前评论样本中反复出现的用户痛点。",
        "unknown": "当前证据不足以判断佩戴与舒适度是否为反复出现的用户痛点。",
    },
    "durability": {
        "inference": "耐用性是当前评论样本中反复出现的用户痛点。",
        "unknown": "当前证据不足以判断耐用性是否为反复出现的用户痛点。",
    },
    "battery": {
        "inference": "续航与充电是当前评论样本中反复出现的用户痛点。",
        "unknown": "当前证据不足以判断续航与充电是否为反复出现的用户痛点。",
    },
}

ACTION_LABELS = {
    (
        "Validate fit across representative use cases and add clear sizing "
        "or fit guidance before launch."
    ): "在上市前覆盖代表性使用场景验证佩戴稳定性，并补充清晰的尺寸与佩戴指引。",
    (
        "Run durability tests on the reported failure modes and document "
        "the resulting supplier quality requirements."
    ): "针对评论中的失效模式开展耐用性测试，并将结果转化为供应商质量要求。",
    (
        "Benchmark real-world battery runtime and charging reliability, "
        "then set measurable supplier acceptance criteria."
    ): "实测真实场景下的续航和充电可靠性，再设定可量化的供应商验收标准。",
}

UNKNOWN_LABELS = {
    "Fewer than 2 supporting reviews were found.": "支持评论少于 2 条。",
    "Topic coverage is below the 10% decision gate.": "主题覆盖率低于 10% 决策门槛。",
    (
        "Contradicting evidence equals or exceeds supporting evidence."
    ): "反向证据数量不少于支持证据。",
    "Evidence may be specific to a single product.": "证据可能只适用于单个产品。",
    "The extraction labeled this claim as unknown.": "AI 抽取将该结论标记为未知。",
}

RISK_LABELS = {
    "contradicting_reviews_present": "存在反向证据",
    "single_product_evidence": "证据仅来自单个产品",
    "llm_extracted_evidence": "证据关系由 AI 抽取，需人工复核",
}

TOPIC_TEXT_LABELS = {
    "fit and comfort": "佩戴与舒适度",
    "durability": "耐用性",
    "battery life and charging": "续航与充电",
}


def _tr(language: str, en: str, zh: str) -> str:
    return zh if language == "zh-CN" else en


def _stretch_kwargs(component: Any) -> dict[str, Any]:
    """Use the current width API while retaining Streamlit 1.35 support."""

    try:
        parameters = inspect.signature(component).parameters
    except (TypeError, ValueError):
        parameters = {}
    if "width" in parameters:
        return {"width": "stretch"}
    return {"use_container_width": True}


def _inject_styles() -> None:
    st.markdown(
        """
        <style>
        :root {
          --voc-ink: #172033;
          --voc-muted: #526071;
          --voc-line: #dfe5ec;
          --voc-blue: #1769aa;
          --voc-teal: #087f70;
          --voc-red: #b42318;
          --voc-amber: #9a6700;
          --voc-panel: #f7f9fb;
        }
        .stApp { background: #ffffff; color: var(--voc-ink); }
        [data-testid="stMetric"] {
          background: var(--voc-panel);
          border: 1px solid var(--voc-line);
          border-radius: 6px;
          padding: 14px 16px;
        }
        .voc-kicker {
          color: var(--voc-blue);
          font-size: 0.76rem;
          font-weight: 700;
          letter-spacing: 0;
          margin-bottom: 6px;
          text-transform: uppercase;
        }
        .voc-note {
          border-left: 3px solid var(--voc-blue);
          background: #f4f8fc;
          color: var(--voc-muted);
          padding: 10px 13px;
          margin: 8px 0 18px;
        }
        .voc-claim {
          color: var(--voc-ink);
          font-size: 1.02rem;
          font-weight: 650;
          line-height: 1.5;
          margin: 3px 0 11px;
        }
        .voc-pill {
          border: 1px solid var(--voc-line);
          border-radius: 999px;
          color: var(--voc-muted);
          display: inline-block;
          font-size: 0.78rem;
          margin: 0 6px 6px 0;
          padding: 3px 8px;
        }
        .voc-evidence {
          border: 1px solid var(--voc-line);
          border-radius: 6px;
          margin-bottom: 8px;
          padding: 10px 12px;
        }
        .voc-evidence.supporting { border-left: 4px solid var(--voc-teal); }
        .voc-evidence.contradicting { border-left: 4px solid var(--voc-red); }
        .voc-review-id { color: var(--voc-muted); font-size: 0.76rem; font-weight: 650; }
        .voc-review-text { color: var(--voc-ink); line-height: 1.55; margin-top: 3px; }
        div[data-testid="stExpander"] { border-color: var(--voc-line); border-radius: 6px; }
        div[data-baseweb="tab-list"] { gap: 4px; }
        [data-testid="stTab"] { min-height: 44px !important; }
        div[role="tablist"] { min-height: 44px !important; }
        button[role="radio"] { min-height: 44px !important; }
        @media (max-width: 700px) {
          [data-testid="stAppViewContainer"] h1 {
            font-size: 2rem;
            line-height: 1.2;
          }
          [data-testid="stMetric"] { padding: 11px 12px; }
          .voc-claim { font-size: 0.96rem; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _review_frame(result: AnalysisResult) -> pd.DataFrame:
    return pd.DataFrame([review.as_dict() for review in result.reviews])


def _display_claim(insight: Any, language: str) -> str:
    if language != "zh-CN":
        return insight.claim
    return CLAIM_LABELS.get(insight.topic, {}).get(insight.type, insight.claim)


def _display_unknown(item: str, language: str) -> str:
    if language != "zh-CN":
        return item
    return UNKNOWN_LABELS.get(item, item)


def _display_action(action: str, language: str) -> str:
    if language != "zh-CN":
        return action
    return ACTION_LABELS.get(action, action)


def _display_rationale(rationale: str, language: str) -> str:
    if language != "zh-CN":
        return rationale
    match = re.fullmatch(
        r"(\d+) of (\d+) valid reviews support the (.+?) "
        r"(?:pain point|claim) across (\d+) product\(s\); "
        r"(\d+) review\(s\) contradict it\.",
        rationale,
    )
    if not match:
        return rationale
    support, total, topic, products, contradictions = match.groups()
    topic_label = TOPIC_LABELS.get(topic, {}).get(
        "zh-CN", TOPIC_TEXT_LABELS.get(topic, topic)
    )
    return (
        f"{total} 条有效评论中，{support} 条支持“{topic_label}”结论，"
        f"覆盖 {products} 个产品；{contradictions} 条评论提供反向证据。"
    )


def _display_risk(flag: str, language: str) -> str:
    if language != "zh-CN":
        return flag
    return RISK_LABELS.get(flag, flag.replace("_", " "))


def _render_evidence_rules(result: AnalysisResult, language: str) -> None:
    if language != "zh-CN":
        st.json(result.evidence_rules)
        return
    rules = result.evidence_rules
    medium = rules["medium"]
    high = rules["high"]
    st.markdown(
        "\n".join(
            [
                f"- **最低门槛**：支持评论至少 {rules['minimum_supporting_reviews']} 条，"
                f"主题覆盖率至少 {rules['minimum_topic_coverage']:.0%}。",
                f"- **中等**：支持至少 {medium['minimum_supporting_reviews']} 条，"
                f"覆盖 {medium['minimum_products']} 个产品，主题覆盖率至少 "
                f"{medium['minimum_topic_coverage']:.0%}，且反向证据少于支持证据。",
                f"- **较高**：支持至少 {high['minimum_supporting_reviews']} 条，"
                f"覆盖 {high['minimum_products']} 个产品，主题覆盖率至少 "
                f"{high['minimum_topic_coverage']:.0%}，反向证据占比不超过 "
                f"{high['maximum_contradiction_share']:.0%}。",
                "- **冲突保护**：反向证据数量不少于支持证据时，"
                "结论降级为“未知”。",
            ]
        )
    )


def _review_source_control(language: str) -> str:
    label = _tr(language, "Review source", "评论来源")
    options = ["demo", "upload"]
    labels = {
        "demo": _tr(language, "Synthetic demo", "合成演示数据"),
        "upload": _tr(language, "Upload CSV", "上传 CSV"),
    }
    if hasattr(st, "segmented_control"):
        return st.segmented_control(
            label,
            options=options,
            format_func=labels.__getitem__,
            default="demo",
            selection_mode="single",
        )
    return st.radio(
        label,
        options=options,
        format_func=labels.__getitem__,
        horizontal=True,
    )


def _evidence_card(review: Any, role: str) -> None:
    rating = f"{review.rating:g}/5"
    st.markdown(
        (
            f'<div class="voc-evidence {role}">'
            f'<div class="voc-review-id">{escape(review.review_id)} · '
            f'{escape(review.product_id)} · {rating}</div>'
            f'<div class="voc-review-text">{escape(review.review_text)}</div>'
            "</div>"
        ),
        unsafe_allow_html=True,
    )


def _render_insight(result: AnalysisResult, insight: Any, language: str) -> None:
    review_index = {review.review_id: review for review in result.reviews}
    topic = TOPIC_LABELS.get(insight.topic, {}).get(language, insight.topic)
    type_label = TYPE_LABELS.get(insight.type, {}).get(language, insight.type)
    strength = STRENGTH_LABELS.get(insight.evidence_strength, {}).get(
        language, insight.evidence_strength
    )

    title = f"{topic} · {type_label} · {strength}"
    with st.expander(title, expanded=insight.type != "unknown"):
        st.markdown(
            f'<div class="voc-claim">{escape(_display_claim(insight, language))}</div>',
            unsafe_allow_html=True,
        )
        st.markdown(
            (
                f'<span class="voc-pill">{_tr(language, "Support", "支持")} '
                f'{insight.support_count}</span>'
                f'<span class="voc-pill">{_tr(language, "Counter-evidence", "反向证据")} '
                f'{insight.contradiction_count}</span>'
                f'<span class="voc-pill">{_tr(language, "Products", "涉及产品")} '
                f'{insight.product_count}</span>'
                f'<span class="voc-pill">{_tr(language, "Coverage", "主题覆盖率")} '
                f'{insight.evidence_coverage:.1%}</span>'
            ),
            unsafe_allow_html=True,
        )

        if insight.unknowns:
            st.warning(
                "\n".join(
                    f"- {_display_unknown(item, language)}"
                    for item in insight.unknowns
                )
            )

        support_tab, counter_tab = st.tabs(
            [
                _tr(language, "Supporting evidence", "支持证据"),
                _tr(language, "Counter-evidence", "反向证据"),
            ]
        )
        with support_tab:
            if not insight.supporting_review_ids:
                st.caption(_tr(language, "No supporting review found.", "未找到支持评论。"))
            for review_id in insight.supporting_review_ids:
                review = review_index.get(review_id)
                if review:
                    _evidence_card(review, "supporting")
        with counter_tab:
            if not insight.contradicting_review_ids:
                st.caption(_tr(language, "No counter-evidence found.", "未找到反向评论。"))
            for review_id in insight.contradicting_review_ids:
                review = review_index.get(review_id)
                if review:
                    _evidence_card(review, "contradicting")

        with st.popover(_tr(language, "Evidence rule", "查看计算规则")):
            st.markdown(
                _tr(
                    language,
                    "Evidence tiers are deterministic rules, not calibrated probabilities.",
                    "证据等级来自确定性规则，不代表经过统计校准的概率。",
                )
            )
            _render_evidence_rules(result, language)


def _render_byok_result(result: AnalysisResult, language: str) -> None:
    status_labels = {
        "ready": _tr(language, "Ready", "可进入评审"),
        "partial_evidence": _tr(language, "Partial evidence", "部分证据"),
        "insufficient_evidence": _tr(language, "Insufficient", "证据不足"),
    }
    metrics = st.columns(3)
    metrics[0].metric(
        _tr(language, "Evidence coverage", "证据覆盖率"),
        f"{result.evidence_coverage:.1%}",
    )
    metrics[1].metric(
        _tr(language, "Recommendations", "可执行建议"),
        len(result.recommendations),
    )
    metrics[2].metric(
        _tr(language, "Decision status", "决策状态"),
        status_labels[result.decision_status],
    )

    review_index = {review.review_id: review for review in result.reviews}
    st.markdown("#### " + _tr(language, "AI-assisted evidence ledger", "AI 辅助证据账本"))
    for insight in result.insights:
        topic = TOPIC_LABELS.get(insight.topic, {}).get(language, insight.topic)
        type_label = TYPE_LABELS.get(insight.type, {}).get(language, insight.type)
        strength = STRENGTH_LABELS.get(insight.evidence_strength, {}).get(
            language, insight.evidence_strength
        )
        st.markdown(f"##### {topic} · {type_label} · {strength}")
        st.markdown(
            f'<div class="voc-claim">{escape(insight.claim)}</div>',
            unsafe_allow_html=True,
        )
        st.markdown(
            (
                f'<span class="voc-pill">{_tr(language, "Support", "支持")} '
                f'{insight.support_count}</span>'
                f'<span class="voc-pill">{_tr(language, "Counter-evidence", "反向证据")} '
                f'{insight.contradiction_count}</span>'
                f'<span class="voc-pill">{_tr(language, "Products", "涉及产品")} '
                f'{insight.product_count}</span>'
                f'<span class="voc-pill">{_tr(language, "Coverage", "主题覆盖率")} '
                f'{insight.evidence_coverage:.1%}</span>'
            ),
            unsafe_allow_html=True,
        )
        if insight.unknowns:
            st.warning(
                "\n".join(
                    f"- {_display_unknown(item, language)}"
                    for item in insight.unknowns
                )
            )

        support_column, counter_column = st.columns(2)
        with support_column:
            st.markdown("**" + _tr(language, "Supporting evidence", "支持证据") + "**")
            if not insight.supporting_review_ids:
                st.caption(_tr(language, "No supporting review found.", "未找到支持评论。"))
            for review_id in insight.supporting_review_ids:
                review = review_index.get(review_id)
                if review:
                    _evidence_card(review, "supporting")
        with counter_column:
            st.markdown("**" + _tr(language, "Counter-evidence", "反向证据") + "**")
            if not insight.contradicting_review_ids:
                st.caption(_tr(language, "No counter-evidence found.", "未找到反向评论。"))
            for review_id in insight.contradicting_review_ids:
                review = review_index.get(review_id)
                if review:
                    _evidence_card(review, "contradicting")
        st.divider()

    st.markdown("#### " + _tr(language, "Deterministic recommendations", "确定性建议"))
    if not result.recommendations:
        st.warning(
            _tr(
                language,
                "Evidence is insufficient for a recommendation.",
                "证据不足，不生成建议。",
            )
        )
    for recommendation in result.recommendations:
        st.markdown(f"**{_display_action(recommendation.action, language)}**")
        st.write(_display_rationale(recommendation.rationale, language))
        st.caption(
            _tr(language, "Evidence refs: ", "证据引用：")
            + ", ".join(recommendation.evidence_refs)
        )
        if recommendation.risk_flags:
            st.warning(
                "、".join(
                    _display_risk(flag, language)
                    for flag in recommendation.risk_flags
                )
            )

    st.markdown("#### " + _tr(language, "AI audit exports", "AI 审计导出"))
    download_columns = st.columns(3)
    download_columns[0].download_button(
        "Markdown",
        data=analysis_to_markdown(result),
        file_name="voc_ai_evidence_audit.md",
        mime="text/markdown",
        key="voc_ai_download_markdown",
        **_stretch_kwargs(st.download_button),
    )
    download_columns[1].download_button(
        "CSV",
        data=analysis_to_csv(result),
        file_name="voc_ai_evidence_ledger.csv",
        mime="text/csv",
        key="voc_ai_download_csv",
        **_stretch_kwargs(st.download_button),
    )
    download_columns[2].download_button(
        "JSON",
        data=analysis_to_json(result),
        file_name="voc_ai_analysis.json",
        mime="application/json",
        key="voc_ai_download_json",
        **_stretch_kwargs(st.download_button),
    )


def _render_byok(result: AnalysisResult, language: str) -> None:
    review_signature = tuple(
        (
            review.review_id,
            review.product_id,
            review.rating,
            review.review_text,
            review.review_date,
            review.source_type,
        )
        for review in result.reviews
    )
    signature_key = "voc_byok_review_signature"
    result_key = "voc_byok_analysis_result"
    if st.session_state.get(signature_key) != review_signature:
        st.session_state.pop(result_key, None)
        st.session_state[signature_key] = review_signature

    with st.expander(_tr(language, "Optional AI extraction (BYOK)", "可选 AI 结构化抽取（BYOK）")):
        st.caption(
            _tr(
                language,
                "The API key and current review fields are sent to the selected endpoint for this request. They are not written to project files or logs; Streamlit retains the password widget only for the current browser session.",
                "API Key 和当前评论字段会随本次请求发送到你选择的接口。应用不将它们写入项目文件或日志；Streamlit 密码输入框只在当前浏览器会话中保留。",
            )
        )
        api_key = st.text_input(
            _tr(language, "API key", "API Key"),
            type="password",
            key="voc_byok_api_key",
        )
        col_base, col_model = st.columns(2)
        with col_base:
            base_url = st.text_input(
                _tr(language, "Compatible base URL", "兼容接口 Base URL"),
                value="https://api.openai.com/v1",
                key="voc_byok_base_url",
                help=_tr(
                    language,
                    "Only operator-enabled public HTTPS hosts are accepted. Private network addresses and redirects are blocked.",
                    "仅接受部署者启用的公网 HTTPS 主机；内网地址和接口重定向会被阻止。",
                ),
            )
        with col_model:
            model = st.text_input(
                _tr(language, "Model", "模型"),
                value="gpt-4o-mini",
                key="voc_byok_model",
            )
        if st.button(
            _tr(language, "Run structured extraction", "运行结构化抽取"),
            disabled=not api_key,
        ):
            try:
                llm_result = extract_analysis_result(
                    result.reviews,
                    api_key=api_key,
                    base_url=base_url,
                    model=model,
                )
                st.session_state[result_key] = llm_result
            except VocLLMError as exc:
                st.error(str(exc))

        llm_result = st.session_state.get(result_key)
        if isinstance(llm_result, AnalysisResult):
            st.success(
                _tr(
                    language,
                    "References validated; deterministic metrics recomputed.",
                    "引用已验证，所有证据指标已由确定性代码重新计算。",
                )
            )
            _render_byok_result(llm_result, language)


def render_voc_dashboard(*, language: str) -> None:
    _inject_styles()
    st.markdown(
        '<div class="voc-kicker">Evidence ledger · Amazon US</div>',
        unsafe_allow_html=True,
    )
    st.subheader(_tr(language, "Review evidence workspace", "评论证据工作台"))
    st.markdown(
        '<div class="voc-note">'
        + escape(
            _tr(
                language,
                "Demo reviews are synthetic. Claims below describe only the supplied sample and are not verified Amazon market facts.",
                "当前演示评论为合成数据。以下结论只描述上传样本，不代表已核实的 Amazon 市场事实。",
            )
        )
        + "</div>",
        unsafe_allow_html=True,
    )

    source = _review_source_control(language)

    uploaded = None
    if source == "upload":
        uploaded = st.file_uploader(
            _tr(language, "Upload review CSV", "上传评论 CSV"),
            type=["csv"],
            help="review_id, product_id, rating, review_text, review_date, source_type",
        )
        if uploaded is None:
            st.info(_tr(language, "Upload a CSV to continue.", "请上传 CSV 后继续。"))
            return

    try:
        validation = read_review_csv(
            uploaded.getvalue() if uploaded is not None else SAMPLE_REVIEWS
        )
    except ReviewValidationError as exc:
        st.error(str(exc))
        return

    result = analyze_reviews(validation)
    report = validation.report
    if report.valid_rows == 0:
        st.error(_tr(language, "No valid review rows remain.", "没有可用评论记录。"))
        return

    status_labels = {
        "ready": _tr(language, "Ready", "可进入评审"),
        "partial_evidence": _tr(language, "Partial evidence", "部分证据"),
        "insufficient_evidence": _tr(language, "Insufficient", "证据不足"),
    }
    metrics = st.columns(5)
    metrics[0].metric(_tr(language, "Valid reviews", "有效评论"), report.valid_rows)
    metrics[1].metric(_tr(language, "Products", "涉及产品"), len({r.product_id for r in result.reviews}))
    metrics[2].metric(_tr(language, "Evidence coverage", "证据覆盖率"), f"{result.evidence_coverage:.1%}")
    metrics[3].metric(_tr(language, "Recommendations", "可执行建议"), len(result.recommendations))
    metrics[4].metric(_tr(language, "Decision status", "决策状态"), status_labels[result.decision_status])

    if validation.issues:
        with st.expander(
            _tr(language, f"Import issues ({len(validation.issues)})", f"导入问题（{len(validation.issues)}）")
        ):
            st.dataframe(
                pd.DataFrame([issue.as_dict() for issue in validation.issues]),
                hide_index=True,
                **_stretch_kwargs(st.dataframe),
            )

    tab_insights, tab_decisions, tab_data = st.tabs(
        [
            _tr(language, "Evidence ledger", "证据账本"),
            _tr(language, "Decision audit", "决策审计"),
            _tr(language, "Source data", "源数据"),
        ]
    )

    with tab_insights:
        for insight in result.insights:
            _render_insight(result, insight, language)

    with tab_decisions:
        if not result.recommendations:
            st.warning(
                _tr(
                    language,
                    "Evidence is insufficient for a deterministic recommendation.",
                    "证据不足，不生成确定性建议。",
                )
            )
        for recommendation in result.recommendations:
            with st.container(border=True):
                st.markdown(
                    f"#### {_display_action(recommendation.action, language)}"
                )
                st.write(_display_rationale(recommendation.rationale, language))
                st.caption(
                    _tr(language, "Evidence refs: ", "证据引用：")
                    + ", ".join(recommendation.evidence_refs)
                )
                if recommendation.risk_flags:
                    st.warning(
                        "、".join(
                            _display_risk(flag, language)
                            for flag in recommendation.risk_flags
                        )
                    )

        st.markdown("#### " + _tr(language, "Audit exports", "审计导出"))
        download_columns = st.columns(3)
        download_columns[0].download_button(
            "Markdown",
            data=analysis_to_markdown(result),
            file_name="voc_evidence_audit.md",
            mime="text/markdown",
            **_stretch_kwargs(st.download_button),
        )
        download_columns[1].download_button(
            "CSV",
            data=analysis_to_csv(result),
            file_name="voc_evidence_ledger.csv",
            mime="text/csv",
            **_stretch_kwargs(st.download_button),
        )
        download_columns[2].download_button(
            "JSON",
            data=analysis_to_json(result),
            file_name="voc_analysis.json",
            mime="application/json",
            **_stretch_kwargs(st.download_button),
        )
        _render_byok(result, language)

    with tab_data:
        st.dataframe(
            _review_frame(result),
            hide_index=True,
            height=440,
            **_stretch_kwargs(st.dataframe),
        )
        st.caption(
            _tr(
                language,
                "Changing or removing a source row and uploading the CSV recomputes every count and recommendation.",
                "修改或删除源评论后重新上传，所有计数与建议都会重新计算。",
            )
        )
