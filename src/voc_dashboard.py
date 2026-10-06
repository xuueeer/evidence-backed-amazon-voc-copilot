from __future__ import annotations

import inspect
import re
from collections.abc import Callable, MutableMapping
from html import escape
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

from src.voc import (
    AnalysisResult,
    Insight,
    Recommendation,
    ReviewRecord,
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


def download_button_options() -> dict[str, Any]:
    options = _stretch_kwargs(st.download_button)
    if "icon" in inspect.signature(st.download_button).parameters:
        options["icon"] = ":material/download:"
    return options


def inject_app_styles() -> None:
    st.markdown(
        """
        <style>
        :root {
          --voc-forest: #0b3d32;
          --voc-forest-2: #10392f;
          --voc-green: #155b49;
          --voc-support: #117a63;
          --voc-support-soft: #e9f6f1;
          --voc-red: #b84a45;
          --voc-red-soft: #fff0ee;
          --voc-amber: #925705;
          --voc-amber-soft: #fff7e8;
          --voc-ink: #17352d;
          --voc-muted: #5f736d;
          --voc-line: #cbdad4;
          --voc-canvas: #f8faf9;
          --voc-panel: #ffffff;
        }
        .stApp {
          background: var(--voc-canvas);
          color: var(--voc-ink);
          font-family: Inter, ui-sans-serif, -apple-system, BlinkMacSystemFont,
            "Segoe UI", sans-serif;
        }
        .stApp * { letter-spacing: 0; }
        [data-testid="stRadio"] label { min-height: 44px; align-items: center; }
        [data-testid="stRadio"] label:has(input:focus-visible) {
          outline: 3px solid #0e7490;
          outline-offset: 2px;
        }
        [data-testid="stAppViewContainer"] .block-container {
          max-width: 1480px;
          padding-top: 2.5rem;
          padding-bottom: 3rem;
        }
        [data-testid="stSidebar"] {
          background: #ffffff;
          border-right: 1px solid var(--voc-line);
        }
        [data-testid="stSidebar"] h1,
        [data-testid="stSidebar"] h2,
        [data-testid="stSidebar"] h3,
        [data-testid="stSidebar"] label,
        [data-testid="stSidebar"] [data-testid="stWidgetLabel"] p,
        [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p {
          color: var(--voc-ink);
        }
        [data-testid="stSidebar"] [data-testid="stCaptionContainer"] p {
          color: var(--voc-muted);
        }
        [data-testid="stSidebar"] hr { border-color: var(--voc-line); }
        [data-testid="stSidebar"] [data-testid="stRadio"] label {
          min-height: 44px;
          padding: 8px 10px;
          border-radius: 6px;
          transition: background 180ms ease;
        }
        [data-testid="stSidebar"] [data-testid="stRadio"] label:hover {
          background: #f1f6f3;
        }
        [data-testid="stSidebar"] [data-testid="stRadio"] label:has(input:checked) {
          background: var(--voc-support-soft);
        }
        [data-testid="stSidebar"] [data-testid="stRadio"] label p {
          font-size: 0.9rem;
        }
        .voc-sidebar-brand {
          align-items: center;
          display: flex;
          gap: 12px;
          margin: 2px 0 24px;
        }
        .voc-sidebar-brand strong,
        .voc-sidebar-brand small {
          display: block;
          overflow-wrap: anywhere;
        }
        .voc-sidebar-brand strong {
          color: var(--voc-forest);
          font-size: 0.94rem;
          font-weight: 650;
        }
        .voc-sidebar-brand small {
          color: var(--voc-muted);
          font-size: 0.8rem;
          margin-top: 2px;
        }
        .voc-sidebar-mark {
          align-items: center;
          background: #13816b;
          border-radius: 8px;
          color: #ffffff;
          display: inline-flex;
          flex: 0 0 40px;
          font-size: 1rem;
          height: 40px;
          justify-content: center;
          width: 40px;
        }
        .app-page-header {
          margin: 4px 0 26px;
          max-width: 780px;
          padding: 5px 0 2px;
        }
        .app-page-header h1 {
          color: var(--voc-forest-2);
          font-size: 2.1rem;
          font-weight: 680;
          line-height: 1.15;
          margin: 6px 0 9px;
          padding: 0;
          overflow-wrap: anywhere;
        }
        .app-page-header p {
          color: var(--voc-muted);
          font-size: 0.94rem;
          line-height: 1.58;
          margin: 0;
          max-width: 70ch;
        }
        .app-page-kicker {
          color: var(--voc-support);
          font-size: 0.72rem;
          font-weight: 700;
          text-transform: uppercase;
        }
        .voc-hero {
          align-items: center;
          display: grid;
          gap: 20px;
          grid-template-columns: minmax(0, 1fr) minmax(260px, 0.42fr);
          margin: 4px 0 8px;
        }
        .voc-hero-copy { padding: 5px 0 2px; }
        .voc-hero h1 {
          color: var(--voc-forest-2);
          font-size: 2rem;
          font-weight: 680;
          line-height: 1.15;
          margin: 8px 0 10px;
          padding: 0;
        }
        .voc-hero p {
          color: var(--voc-muted);
          font-size: 0.94rem;
          line-height: 1.55;
          margin: 0;
        }
        .voc-kicker {
          color: var(--voc-support);
          font-size: 0.72rem;
          font-weight: 700;
          text-transform: uppercase;
        }
        .voc-status-card {
          align-items: flex-start;
          background: transparent;
          border-left: 2px solid #e7bf76;
          display: flex;
          gap: 11px;
          padding: 8px 0 8px 18px;
        }
        .voc-status-card.ready {
          background: transparent;
          border-color: #9bcdbd;
        }
        .voc-status-card.insufficient {
          background: transparent;
          border-color: #e2aaa6;
        }
        .voc-status-dot {
          background: var(--voc-amber);
          border-radius: 50%;
          flex: 0 0 10px;
          height: 10px;
          margin-top: 6px;
          width: 10px;
        }
        .voc-status-card.ready .voc-status-dot { background: var(--voc-support); }
        .voc-status-card.insufficient .voc-status-dot { background: var(--voc-red); }
        .voc-status-label {
          color: var(--voc-ink);
          font-size: 0.9rem;
          font-weight: 700;
        }
        .voc-status-detail {
          color: var(--voc-muted);
          font-size: 0.85rem;
          line-height: 1.45;
          margin-top: 4px;
        }
        .voc-provenance {
          align-items: center;
          border-bottom: 1px solid var(--voc-line);
          display: flex;
          gap: 12px;
          margin: 0 0 16px;
          min-height: 50px;
          padding: 12px 0 16px;
        }
        .voc-provenance-mark {
          align-items: center;
          background: var(--voc-forest);
          border-radius: 50%;
          color: #ffffff;
          display: inline-flex;
          flex: 0 0 28px;
          font-size: 0.76rem;
          font-weight: 700;
          height: 28px;
          justify-content: center;
          width: 28px;
        }
        .voc-provenance-label {
          color: var(--voc-ink);
          font-size: 0.85rem;
          font-weight: 700;
          white-space: nowrap;
        }
        .voc-provenance-code {
          background: var(--voc-amber-soft);
          border: 1px solid #e8c481;
          border-radius: 999px;
          color: var(--voc-amber);
          font-size: 0.72rem;
          padding: 4px 10px;
          white-space: nowrap;
        }
        .voc-provenance-text {
          color: var(--voc-muted);
          flex: 1;
          font-size: 0.78rem;
          line-height: 1.4;
          overflow-wrap: anywhere;
        }
        .voc-summary-grid {
          display: grid;
          gap: 0;
          grid-template-columns: repeat(4, minmax(0, 1fr));
          margin: 0 0 20px;
        }
        .voc-metric-card {
          border-right: 1px solid var(--voc-line);
          min-height: 100px;
          padding: 4px 22px;
        }
        .voc-metric-card:first-child { padding-left: 0; }
        .voc-metric-card:last-child { border-right: 0; }
        .voc-metric-label {
          color: var(--voc-muted);
          font-size: 0.85rem;
          font-weight: 650;
        }
        .voc-metric-value {
          color: var(--voc-forest-2);
          font-size: 2rem;
          font-weight: 620;
          line-height: 1.15;
          margin: 10px 0 3px;
        }
        .voc-metric-note {
          color: var(--voc-muted);
          font-size: 0.8rem;
          line-height: 1.4;
          overflow-wrap: anywhere;
        }
        .voc-section-head {
          align-items: flex-end;
          display: flex;
          justify-content: space-between;
          margin: 4px 0 13px;
        }
        .voc-section-head h2 {
          color: var(--voc-forest-2);
          font-size: 1.28rem;
          font-weight: 650;
          margin: 0;
          padding: 0;
        }
        .voc-section-head p {
          color: var(--voc-muted);
          font-size: 0.85rem;
          margin: 4px 0 0;
        }
        .voc-analysis-shell {
          background: #ffffff;
          border-top: 1px solid var(--voc-line);
          border-bottom: 1px solid var(--voc-line);
          display: grid;
          grid-template-columns: minmax(0, 1.8fr) minmax(280px, 1fr);
          margin-bottom: 12px;
          overflow: hidden;
        }
        .voc-insight-pane { min-width: 0; padding: 24px; }
        .voc-decision-pane {
          border-left: 1px solid var(--voc-line);
          min-width: 0;
          padding: 24px;
          background: #f1f6f3;
        }
        .voc-insight-title-row {
          align-items: center;
          display: flex;
          flex-wrap: wrap;
          gap: 8px;
          margin-bottom: 11px;
        }
        .voc-sequence {
          color: var(--voc-support);
          font-size: 0.72rem;
          font-weight: 700;
          margin-right: 4px;
        }
        .voc-insight-title {
          color: var(--voc-forest-2);
          font-size: 1.2rem;
          font-weight: 680;
          margin-right: auto;
          overflow-wrap: anywhere;
        }
        .voc-claim {
          color: var(--voc-ink);
          font-size: 1rem;
          font-weight: 560;
          line-height: 1.58;
          margin: 0 0 18px;
          overflow-wrap: anywhere;
        }
        .voc-badge {
          background: #f5f8f6;
          border: 1px solid var(--voc-line);
          border-radius: 999px;
          display: inline-block;
          font-size: 0.8rem;
          font-weight: 650;
          padding: 4px 10px;
          white-space: nowrap;
        }
        .voc-badge.inference,
        .voc-badge.high { background: var(--voc-support-soft); border-color: #aed6c9; color: #0d6a56; }
        .voc-badge.medium,
        .voc-badge.low,
        .voc-badge.unknown,
        .voc-badge.insufficient { background: var(--voc-amber-soft); border-color: #eccb91; color: var(--voc-amber); }
        .voc-balance-head {
          align-items: center;
          color: var(--voc-muted);
          display: flex;
          font-size: 0.8rem;
          justify-content: space-between;
          margin-bottom: 6px;
        }
        .voc-balance-track {
          background: #e7eeeb;
          border-radius: 999px;
          display: flex;
          height: 9px;
          overflow: hidden;
          width: 100%;
        }
        .voc-balance-support { background: var(--voc-support); }
        .voc-balance-counter { background: var(--voc-red); }
        .voc-stat-chips {
          display: flex;
          flex-wrap: wrap;
          gap: 7px;
          margin: 10px 0 16px;
        }
        .voc-stat-chip {
          border: 1px solid var(--voc-line);
          border-radius: 999px;
          color: var(--voc-muted);
          font-size: 0.8rem;
          padding: 4px 10px;
        }
        .voc-stat-chip.support { background: var(--voc-support-soft); border-color: #b6dace; color: #0c6b56; }
        .voc-stat-chip.counter { background: var(--voc-red-soft); border-color: #edc2be; color: var(--voc-red); }
        .voc-evidence-columns {
          border-top: 1px solid var(--voc-line);
          display: grid;
          gap: 16px;
          grid-template-columns: repeat(2, minmax(0, 1fr));
          padding-top: 16px;
        }
        .voc-evidence-column + .voc-evidence-column {
          border-left: 1px solid var(--voc-line);
          padding-left: 20px;
        }
        .voc-evidence-heading {
          align-items: center;
          color: var(--voc-ink);
          display: flex;
          font-size: 0.85rem;
          font-weight: 700;
          justify-content: space-between;
          margin-bottom: 9px;
        }
        .voc-evidence {
          background: #fbfdfc;
          border-left: 4px solid var(--voc-support);
          margin-bottom: 9px;
          padding: 12px;
          border-radius: 0 4px 4px 0;
        }
        .voc-evidence.contradicting { background: #fffafa; border-left-color: var(--voc-red); }
        .voc-review-id {
          color: var(--voc-muted);
          font-size: 0.75rem;
          font-variant-numeric: tabular-nums;
          font-weight: 650;
          overflow-wrap: anywhere;
        }
        .voc-review-text {
          color: var(--voc-ink);
          font-size: 0.9rem;
          line-height: 1.65;
          margin-top: 5px;
          overflow-wrap: anywhere;
        }
        .voc-empty-evidence {
          color: var(--voc-muted);
          font-size: 0.76rem;
          padding: 12px 0;
        }
        .voc-unknown-strip {
          background: #fbfcfb;
          border-top: 1px solid var(--voc-line);
          color: var(--voc-muted);
          font-size: 0.85rem;
          line-height: 1.65;
          margin: 20px 0 0;
          padding: 14px 0 0;
        }
        .voc-unknown-strip strong { color: var(--voc-amber); margin-right: 10px; }
        .voc-decision-kicker { color: var(--voc-support); font-size: 0.8rem; font-weight: 700; }
        .voc-decision-title {
          border-bottom: 1px solid var(--voc-line);
          color: var(--voc-forest-2);
          font-size: 1rem;
          font-weight: 660;
          line-height: 1.45;
          margin: 8px 0 17px;
          padding-bottom: 12px;
        }
        .voc-decision-label {
          color: var(--voc-support);
          font-size: 0.8rem;
          font-weight: 700;
          margin-bottom: 7px;
        }
        .voc-decision-body {
          color: var(--voc-ink);
          font-size: 0.95rem;
          line-height: 1.58;
          overflow-wrap: anywhere;
        }
        .voc-decision-meta {
          color: var(--voc-muted);
          font-size: 0.85rem;
          line-height: 1.5;
          margin-top: 8px;
          overflow-wrap: anywhere;
        }
        .voc-risk-block {
          border-top: 1px solid var(--voc-line);
          margin-top: 17px;
          padding-top: 14px;
        }
        .voc-risk-block ul { margin: 7px 0 0; padding-left: 18px; }
        .voc-risk-block li { color: var(--voc-muted); font-size: 0.85rem; line-height: 1.6; }
        .voc-landscape {
          display: grid;
          grid-template-columns: repeat(3, minmax(0, 1fr));
          gap: 24px;
          padding: 18px 0;
          border-bottom: 1px solid var(--voc-line);
          margin-bottom: 8px;
        }
        .voc-landscape-topic { min-width: 0; }
        .voc-landscape-head { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
        .voc-landscape-head strong { font-size: 0.9rem; }
        .voc-landscape-count { font-size: 0.8rem; color: var(--voc-muted); margin-top: 8px; }
        .voc-landscape-track { height: 6px; display: flex; background: #e3e9e6; margin-top: 14px; overflow: hidden; }
        .voc-landscape-track span { min-width: 0; }
        .voc-evidence-more summary,
        .voc-unknown-strip summary {
          cursor: pointer;
          min-height: 44px;
          display: list-item;
          align-content: center;
          color: var(--voc-forest);
          font-size: 0.85rem;
          font-weight: 600;
        }
        .voc-evidence-more summary:hover { color: var(--voc-support); }
        .voc-evidence-more summary:focus-visible,
        .voc-unknown-strip summary:focus-visible {
          outline: 3px solid #0e7490;
          outline-offset: 2px;
        }
        .voc-footer { color: var(--voc-muted); border-top: 1px solid var(--voc-line); margin-top: 28px; padding-top: 16px; font-size: 0.8rem; display: flex; flex-wrap: wrap; justify-content: space-between; gap: 8px; }
        .voc-risk-block li::marker { color: var(--voc-amber); }
        .voc-other-heading {
          color: var(--voc-forest-2);
          font-size: 0.92rem;
          font-weight: 650;
          margin: 22px 0 8px;
        }
        .voc-recommendation-card {
          background: #ffffff;
          border-left: 4px solid var(--voc-support);
          margin: 8px 0;
          padding: 13px 15px;
        }
        .voc-recommendation-card h4 {
          color: var(--voc-forest-2);
          font-size: 0.92rem;
          margin: 0 0 7px;
        }
        .voc-recommendation-card p {
          color: var(--voc-muted);
          font-size: 0.8rem;
          line-height: 1.55;
          margin: 0 0 6px;
        }
        .voc-recommendation-card small { color: #657972; overflow-wrap: anywhere; }
        .voc-empty-state {
          background: #ffffff;
          border: 1px solid var(--voc-line);
          border-left: 4px solid var(--voc-amber);
          border-radius: 8px;
          color: var(--voc-muted);
          font-size: 0.86rem;
          line-height: 1.5;
          margin: 10px 0;
          padding: 12px 14px;
        }
        div[data-testid="stExpander"] {
          background: #ffffff;
          border-color: var(--voc-line);
          border-radius: 8px;
        }
        [data-testid="stHeadingWithActionElements"] h1 {
          color: var(--voc-forest-2);
          font-size: 2.1rem;
          font-weight: 680;
          line-height: 1.15;
        }
        [data-testid="stHeadingWithActionElements"] h2 {
          color: var(--voc-forest-2);
          font-size: 1.28rem;
          font-weight: 650;
          line-height: 1.3;
        }
        [data-testid="stHeadingWithActionElements"] h3 {
          color: var(--voc-forest-2);
          font-size: 1.04rem;
          font-weight: 650;
          line-height: 1.35;
        }
        [data-testid="stMetric"] {
          background: var(--voc-panel);
          border: 1px solid var(--voc-line);
          border-radius: 8px;
          min-height: 108px;
          padding: 14px 16px;
        }
        [data-testid="stMetricLabel"] p {
          color: var(--voc-muted);
          font-size: 0.76rem;
          font-weight: 650;
        }
        [data-testid="stMetricValue"] {
          color: var(--voc-forest-2);
          font-size: 1.72rem;
          font-weight: 620;
        }
        [data-testid="stDataFrame"],
        [data-testid="stDataEditor"] {
          background: var(--voc-panel);
          border: 1px solid var(--voc-line);
          border-radius: 8px;
          overflow: hidden;
        }
        [data-testid="stVerticalBlockBorderWrapper"] {
          background: var(--voc-panel);
          border-color: var(--voc-line) !important;
          border-radius: 8px;
        }
        [data-testid="stAlertContainer"] {
          border-radius: 8px;
        }
        [data-testid="stTab"] {
          color: var(--voc-muted);
          min-height: 44px !important;
        }
        [data-testid="stTab"][aria-selected="true"],
        [data-testid="stTab"][aria-selected="true"] p {
          color: var(--voc-support) !important;
        }
        [data-testid="stTab"] .react-aria-SelectionIndicator {
          background-color: var(--voc-support) !important;
        }
        div[role="tablist"] { min-height: 44px !important; }
        button[role="radio"] { min-height: 44px !important; }
        button[role="radio"][aria-checked="true"] {
          background: var(--voc-support-soft) !important;
          border-color: var(--voc-support) !important;
          color: var(--voc-forest) !important;
        }
        [data-testid="stSidebar"]
        [data-testid="stRadioOption"][data-selected="true"]
        > div > div:first-child {
          background-color: var(--voc-support) !important;
        }
        .stButton button,
        .stDownloadButton button {
          border-radius: 6px;
          min-height: 44px;
          transition: background-color 180ms ease, border-color 180ms ease,
            color 180ms ease;
        }
        .stButton button {
          background: var(--voc-forest);
          border-color: var(--voc-forest);
          color: #ffffff;
        }
        .stDownloadButton button {
          background: #ffffff;
          border-color: var(--voc-support);
          color: var(--voc-forest);
        }
        .stDownloadButton button:hover {
          background: var(--voc-support-soft);
          border-color: var(--voc-support);
          color: var(--voc-forest);
        }
        [data-baseweb="select"] > div,
        [data-testid="stTextInput"] input,
        [data-testid="stNumberInput"] input,
        [data-testid="stTextArea"] textarea {
          border-color: var(--voc-line);
          border-radius: 6px;
          min-height: 44px;
        }
        [data-testid="stNumberInput"] button,
        [data-testid="stPopover"] button,
        [data-testid="stSelectbox"] button,
        [data-testid="stMultiSelect"] button {
          min-height: 44px;
          min-width: 44px;
        }
        [data-testid="stSelectbox"] [role="combobox"] { min-height: 44px; }
        [data-testid="stSidebar"] [data-testid="stNumberInput"] input,
        [data-testid="stSidebar"] [data-baseweb="select"] > div {
          background: #ffffff;
          color: var(--voc-ink);
        }
        .stButton button:hover {
          background: var(--voc-green);
          border-color: var(--voc-green);
          color: #ffffff;
        }
        [data-testid="stFileUploader"] {
          background: #ffffff;
          border: 1px solid var(--voc-line);
          border-radius: 8px;
          padding: 8px;
        }
        [data-testid="stFileUploader"] button {
          border-color: var(--voc-support);
          color: var(--voc-forest);
        }
        button:focus-visible,
        input:focus-visible,
        textarea:focus-visible,
        [role="tab"]:focus-visible,
        [role="radio"]:focus-visible {
          outline: 3px solid #0e7490 !important;
          outline-offset: 2px;
        }
        @media (prefers-reduced-motion: reduce) {
          .stApp *, .stApp *::before, .stApp *::after {
            transition: none !important;
            animation: none !important;
            scroll-behavior: auto !important;
          }
        }
        @media (max-width: 1023px) {
          .voc-hero { grid-template-columns: 1fr; }
          .voc-summary-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
          .voc-metric-card { padding: 12px 16px; }
          .voc-metric-card:nth-child(odd) { padding-left: 0; }
          .voc-metric-card:nth-child(even) { border-right: 0; }
          .voc-analysis-shell { grid-template-columns: 1fr; }
          .voc-decision-pane { border-left: 0; border-top: 1px solid var(--voc-line); }
        }
        @media (max-width: 767px) {
          [data-testid="stAppViewContainer"] .block-container {
            padding-left: 1rem;
            padding-right: 1rem;
            padding-top: 1.25rem;
          }
          .voc-hero h1 { font-size: 1.75rem; }
          .app-page-header { margin-bottom: 20px; }
          .app-page-header h1,
          [data-testid="stHeadingWithActionElements"] h1 { font-size: 1.75rem; }
          .app-page-header p { font-size: 1rem; }
          .voc-hero p,
          .voc-claim,
          .voc-review-text,
          .voc-decision-body { font-size: 1rem; }
          .voc-provenance { align-items: flex-start; flex-wrap: wrap; }
          .voc-provenance-text { flex-basis: calc(100% - 42px); }
          .voc-evidence-columns { grid-template-columns: 1fr; }
          .voc-evidence-column + .voc-evidence-column {
            border-left: 0;
            border-top: 1px solid var(--voc-line);
            padding-left: 0;
            padding-top: 15px;
          }
          .voc-insight-pane,
          .voc-decision-pane { padding: 16px; }
          .voc-unknown-strip { margin: 16px 0 0; padding: 11px 0; }
          .voc-landscape { gap: 12px; }
          .voc-landscape-head { flex-direction: column; align-items: flex-start; gap: 8px; }
          .voc-landscape-head strong { font-size: 0.85rem; line-height: 1.5; }
          .voc-landscape-count { font-size: 0.8rem; line-height: 1.5; }
          .voc-landscape .voc-badge { padding: 3px 8px; }
          .voc-metric-note { font-size: 0.8rem; }
        }
        @media (max-width: 420px) {
          .voc-metric-card { min-height: 110px; }
          .voc-section-head { align-items: flex-start; flex-direction: column; gap: 6px; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _review_frame(result: AnalysisResult) -> pd.DataFrame:
    return pd.DataFrame([review.as_dict() for review in result.reviews])


def _display_claim(
    insight: Any,
    language: str,
    *,
    preserve_original: bool = False,
) -> str:
    if preserve_original or language != "zh-CN":
        return insight.claim
    return CLAIM_LABELS.get(insight.topic, {}).get(insight.type, insight.claim)


def _status_presentation(status: str, language: str) -> tuple[str, str, str]:
    presentations = {
        "ready": (
            _tr(language, "Ready", "可进入评审"),
            _tr(language, "All rule gates are clear.", "已通过全部规则门槛。"),
            "ready",
        ),
        "partial_evidence": (
            _tr(language, "Partial evidence", "部分证据"),
            _tr(language, "Some topics still need validation.", "部分主题仍需验证。"),
            "partial",
        ),
        "insufficient_evidence": (
            _tr(language, "Insufficient", "证据不足"),
            _tr(language, "The decision gate is not met.", "尚未达到决策门槛。"),
            "insufficient",
        ),
    }
    return presentations.get(status, presentations["insufficient_evidence"])


def _source_provenance(source: str, language: str) -> tuple[str, str]:
    if source == "upload":
        return (
            "user_upload",
            _tr(
                language,
                "User-uploaded rows; marketplace origin and authenticity have not been independently verified.",
                "用户上传数据；平台来源与真实性未经独立核验。",
            ),
        )
    return (
        "demo_synthetic",
        _tr(
            language,
            "Synthetic review set for product demonstration; it is not verified Amazon market evidence.",
            "用于产品演示的合成评论集，不属于已核实的 Amazon 市场证据。",
        ),
    )


def _evidence_balance(
    support_count: int,
    contradiction_count: int,
) -> tuple[float, float]:
    support = max(0, support_count)
    contradiction = max(0, contradiction_count)
    total = support + contradiction
    if total == 0:
        return 0.0, 0.0
    support_share = support / total * 100
    return support_share, 100 - support_share


def _recommendation_for_insight(
    result: AnalysisResult,
    insight: Insight,
) -> Recommendation | None:
    supporting_ids = set(insight.supporting_review_ids)
    if not supporting_ids:
        return None

    # Both deterministic and BYOK analysis emit one recommendation for each
    # actionable insight, in insight order. Preserve that association before
    # falling back to evidence-reference matching: different topics can be
    # supported by the same reviews, so references alone may be ambiguous.
    actionable_insights = [
        candidate
        for candidate in result.insights
        if candidate.type != "unknown" and candidate.supporting_review_ids
    ]
    if len(actionable_insights) == len(result.recommendations):
        for candidate, recommendation in zip(
            actionable_insights,
            result.recommendations,
            strict=True,
        ):
            if candidate is not insight:
                continue
            evidence_refs = set(recommendation.evidence_refs)
            if evidence_refs == supporting_ids:
                return recommendation
            return None

    matches: list[Recommendation] = []
    for recommendation in result.recommendations:
        evidence_refs = set(recommendation.evidence_refs)
        if evidence_refs == supporting_ids:
            matches.append(recommendation)
    return matches[0] if len(matches) == 1 else None


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


def _workspace_header_html(
    result: AnalysisResult | None,
    language: str,
) -> str:
    if result is None:
        label = _tr(language, "Awaiting source data", "等待源数据")
        tone = "partial"
        default_detail = _tr(
            language,
            "Upload a valid review CSV before evidence can be assessed.",
            "上传有效评论 CSV 后才能评估证据。",
        )
    else:
        label, default_detail, tone = _status_presentation(
            result.decision_status,
            language,
        )
        unresolved = sum(insight.type == "unknown" for insight in result.insights)
        if result.decision_status == "ready":
            detail = _tr(
                language,
                f"{len(result.recommendations)} recommendation(s) clear the rule gates.",
                f"{len(result.recommendations)} 条建议通过规则门槛。",
            )
        elif result.decision_status == "partial_evidence":
            detail = _tr(
                language,
                f"{len(result.recommendations)} actionable · {unresolved} topic(s) need validation.",
                f"{len(result.recommendations)} 条建议可执行 · {unresolved} 个主题待验证。",
            )
        else:
            detail = _tr(
                language,
                f"No deterministic recommendation · {unresolved} topic(s) unresolved.",
                f"暂无确定性建议 · {unresolved} 个主题未解决。",
            )
        # Keep the status helper useful on its own while allowing the workspace
        # header to add the actual counts for the current dataset.
        if not detail:
            detail = default_detail
    if result is None:
        detail = default_detail
    return (
        '<div class="voc-hero">'
        '<div class="voc-hero-copy">'
        '<div class="voc-kicker">Evidence Ledger / Amazon VOC</div>'
        f'<h1>{escape(_tr(language, "Review evidence workspace", "评论证据工作台"))}</h1>'
        f'<p>{escape(_tr(language, "Customer signals. Traceable evidence. Considered decisions.", "用户声音，原文佐证，审慎决策。"))}</p>'
        '</div>'
        f'<div class="voc-status-card {tone}">'
        '<span class="voc-status-dot"></span><div>'
        f'<div class="voc-status-label">{escape(label)}</div>'
        f'<div class="voc-status-detail">{escape(detail)}</div>'
        '</div></div></div>'
    )


def _provenance_html(source: str, language: str) -> str:
    code, description = _source_provenance(source, language)
    return (
        '<div class="voc-provenance">'
        '<span class="voc-provenance-mark">i</span>'
        f'<span class="voc-provenance-label">{escape(_tr(language, "Data source", "数据来源"))}</span>'
        f'<span class="voc-provenance-code">{escape(code)}</span>'
        f'<span class="voc-provenance-text">{escape(description)}</span>'
        '</div>'
    )


def _metric_card_html(label: str, value: str, note: str) -> str:
    return (
        '<div class="voc-metric-card">'
        f'<div class="voc-metric-label">{escape(label)}</div>'
        f'<div class="voc-metric-value">{escape(value)}</div>'
        f'<div class="voc-metric-note">{escape(note)}</div>'
        '</div>'
    )


def _summary_grid_html(
    result: AnalysisResult,
    language: str,
    *,
    input_rows: int | None = None,
    rejected_rows: int = 0,
) -> str:
    product_count = len({review.product_id for review in result.reviews})
    evidence_ids = {
        review_id
        for insight in result.insights
        for review_id in (
            insight.supporting_review_ids + insight.contradicting_review_ids
        )
    }
    unresolved = sum(insight.type == "unknown" for insight in result.insights)
    valid_note = (
        _tr(
            language,
            f"{rejected_rows} of {input_rows} source row(s) rejected",
            f"{input_rows} 条源记录中拒绝 {rejected_rows} 条",
        )
        if input_rows is not None and rejected_rows
        else _tr(language, "All retained rows passed validation", "保留记录均已通过校验")
    )
    cards = [
        _metric_card_html(
            _tr(language, "Valid reviews", "有效评论"),
            str(len(result.reviews)),
            valid_note,
        ),
        _metric_card_html(
            _tr(language, "Products", "涉及商品"),
            str(product_count),
            _tr(
                language,
                f"Valid reviews span {product_count} product(s)",
                f"有效评论涉及 {product_count} 个商品",
            ),
        ),
        _metric_card_html(
            _tr(language, "Evidence coverage", "证据覆盖率"),
            f"{result.evidence_coverage:.1%}",
            _tr(
                language,
                f"{len(evidence_ids)} review(s) used as topic evidence",
                f"{len(evidence_ids)} 条评论进入主题证据",
            ),
        ),
        _metric_card_html(
            _tr(language, "Actionable recommendations", "可执行建议"),
            str(len(result.recommendations)),
            _tr(
                language,
                f"{unresolved} topic(s) remain below the decision gate",
                f"其余 {unresolved} 个主题仍受门槛保护",
            ),
        ),
    ]
    return '<div class="voc-summary-grid">' + "".join(cards) + "</div>"


def _evidence_landscape_html(result: AnalysisResult, language: str) -> str:
    """Use one shared count scale; these bars are not confidence scores."""
    maximum = max(
        (item.support_count + item.contradiction_count for item in result.insights),
        default=0,
    )
    topics = []
    for insight in result.insights:
        label = TOPIC_LABELS.get(insight.topic, {}).get(language, insight.topic)
        strength = STRENGTH_LABELS.get(insight.evidence_strength, {}).get(
            language, insight.evidence_strength
        )
        support = insight.support_count / maximum * 100 if maximum else 0
        counter = insight.contradiction_count / maximum * 100 if maximum else 0
        counts = _tr(
            language,
            f"{insight.support_count} supporting / {insight.contradiction_count} counter",
            f"{insight.support_count} 条支持 / {insight.contradiction_count} 条反向",
        )
        topics.append(
            '<div class="voc-landscape-topic">'
            '<div class="voc-landscape-head">'
            f'<strong>{escape(label)}</strong>'
            f'<span class="voc-badge {escape(insight.evidence_strength)}">{escape(strength)}</span>'
            '</div>'
            f'<div class="voc-landscape-track" role="img" aria-label="{escape(label + ": " + counts)}">'
            f'<span class="voc-balance-support" style="width:{support:.4f}%"></span>'
            f'<span class="voc-balance-counter" style="width:{counter:.4f}%"></span>'
            '</div>'
            f'<div class="voc-landscape-count">{escape(counts)}</div></div>'
        )
    return '<div class="voc-landscape">' + ''.join(topics) + '</div>'


def _filtered_insights(result: AnalysisResult, scope: str) -> list[Insight]:
    if scope == "actionable":
        return [
            item for item in result.insights
            if _recommendation_for_insight(result, item) is not None
        ]
    if scope == "unresolved":
        return [
            item for item in result.insights
            if _recommendation_for_insight(result, item) is None
        ]
    return list(result.insights)


def _filter_reviews(
    reviews: list[ReviewRecord], query: str, product: str | None = None
) -> list[ReviewRecord]:
    term = query.strip().casefold()
    return [
        review for review in reviews
        if (product is None or review.product_id == product)
        and (
            not term or term in ' '.join(
                (review.review_id, review.product_id, review.review_text)
            ).casefold()
        )
    ]


def _evidence_card_html(review: ReviewRecord, role: str) -> str:
    safe_role = "contradicting" if role == "contradicting" else "supporting"
    rating = f"{review.rating:g}/5"
    return (
        f'<div class="voc-evidence {safe_role}">'
        f'<div class="voc-review-id">{escape(review.review_id)} · '
        f'{escape(review.product_id)} · {rating}</div>'
        f'<div class="voc-review-text">{escape(review.review_text)}</div>'
        '</div>'
    )


def _evidence_column_html(
    review_index: dict[str, ReviewRecord],
    review_ids: list[str],
    role: str,
    language: str,
) -> str:
    supporting = role == "supporting"
    heading = _tr(
        language,
        "Supporting evidence" if supporting else "Counter-evidence",
        "支持证据" if supporting else "反向证据",
    )
    empty_text = _tr(
        language,
        "No supporting review found."
        if supporting
        else "No counter-evidence found.",
        "未找到支持评论。" if supporting else "未找到反向评论。",
    )
    cards: list[str] = []
    for review_id in review_ids:
        review = review_index.get(review_id)
        if review is None:
            cards.append(
                '<div class="voc-empty-evidence">'
                + escape(
                    _tr(
                        language,
                        f"Referenced review {review_id} is unavailable.",
                        f"引用评论 {review_id} 不可用。",
                    )
                )
                + '</div>'
            )
        else:
            cards.append(_evidence_card_html(review, role))
    if not cards:
        cards.append(f'<div class="voc-empty-evidence">{escape(empty_text)}</div>')
    if len(cards) > 3:
        more_label = _tr(language, f"Show {len(cards) - 3} more reviews", f"展开其余 {len(cards) - 3} 条评论")
        cards = cards[:3] + [
            '<details class="voc-evidence-more">'
            f'<summary>{escape(more_label)}</summary>'
            + ''.join(cards[3:]) + '</details>'
        ]
    return (
        '<div class="voc-evidence-column">'
        f'<div class="voc-evidence-heading"><span>{escape(heading)}</span>'
        f'<span>{len(review_ids)}</span></div>'
        + "".join(cards)
        + '</div>'
    )


def _insight_panel_html(
    result: AnalysisResult,
    insight: Insight,
    language: str,
    *,
    sequence: int,
    preserve_claim: bool,
) -> str:
    review_index = {review.review_id: review for review in result.reviews}
    topic = TOPIC_LABELS.get(insight.topic, {}).get(language, insight.topic)
    type_label = TYPE_LABELS.get(insight.type, {}).get(language, insight.type)
    strength = STRENGTH_LABELS.get(insight.evidence_strength, {}).get(
        language, insight.evidence_strength
    )
    support_share, counter_share = _evidence_balance(
        insight.support_count,
        insight.contradiction_count,
    )
    unknowns = [
        _display_unknown(item, language) for item in insight.unknowns
    ] or [_tr(language, "No rule-level unknowns declared.", "当前规则未声明未知项。")]
    assumption_labels = {
        "English keyword matches are treated as topic evidence.": "英文关键词匹配被视为主题证据。",
        "A low rating only supplies polarity when the review names the topic.": "仅在评论提及该主题时，低评分才用于判断倾向。",
        "Evidence strength is a rule tier, not a probability.": "证据强度是规则等级，不是概率。",
    }
    assumptions = [
        assumption_labels.get(item, item) if language == "zh-CN" else item
        for item in insight.assumptions
    ] or [
        _tr(language, "No extraction assumptions supplied.", "未提供抽取假设。")
    ]
    supporting_html = _evidence_column_html(
        review_index,
        insight.supporting_review_ids,
        "supporting",
        language,
    )
    counter_html = _evidence_column_html(
        review_index,
        insight.contradicting_review_ids,
        "contradicting",
        language,
    )
    return (
        '<div class="voc-insight-pane">'
        '<div class="voc-insight-title-row">'
        f'<span class="voc-sequence">{sequence:02d}</span>'
        f'<span class="voc-insight-title">{escape(topic)}</span>'
        f'<span class="voc-badge {escape(insight.type)}">{escape(type_label)}</span>'
        f'<span class="voc-badge {escape(insight.evidence_strength)}">{escape(strength)}</span>'
        '</div>'
        f'<div class="voc-claim">{escape(_display_claim(insight, language, preserve_original=preserve_claim))}</div>'
        '<div class="voc-balance-head">'
        f'<span>{escape(_tr(language, "Evidence balance", "证据平衡"))}</span>'
        f'<span>{insight.support_count} {escape(_tr(language, "support", "支持"))} / '
        f'{insight.contradiction_count} {escape(_tr(language, "counter", "反向"))}</span>'
        '</div>'
        '<div class="voc-balance-track">'
        f'<span class="voc-balance-support" style="width:{support_share:.4f}%"></span>'
        f'<span class="voc-balance-counter" style="width:{counter_share:.4f}%"></span>'
        '</div>'
        '<div class="voc-stat-chips">'
        f'<span class="voc-stat-chip support">{escape(_tr(language, "Support", "支持"))} {insight.support_count}</span>'
        f'<span class="voc-stat-chip counter">{escape(_tr(language, "Counter", "反向"))} {insight.contradiction_count}</span>'
        f'<span class="voc-stat-chip">{insight.product_count} {escape(_tr(language, "products", "个商品"))}</span>'
        f'<span class="voc-stat-chip">{escape(_tr(language, "Coverage", "覆盖率"))} {insight.evidence_coverage:.1%}</span>'
        '</div>'
        '<div class="voc-evidence-columns">'
        + supporting_html
        + counter_html
        + '</div>'
        '<div class="voc-unknown-strip">'
        f'<strong>{escape(_tr(language, "Unknowns", "未知项"))}</strong>{escape(" · ".join(unknowns))}<br>'
        '<details>'
        f'<summary>{escape(_tr(language, "Analysis assumptions", "分析假设"))}</summary>{escape(" · ".join(assumptions))}'
        '</details>'
        '</div></div>'
    )


def _decision_brief_html(
    result: AnalysisResult,
    insight: Insight,
    language: str,
) -> str:
    recommendation = _recommendation_for_insight(result, insight)
    title = _tr(
        language,
        "What action does this evidence support?",
        "这条结论现在能支持什么行动？",
    )
    if recommendation is None:
        action_label = _tr(language, "Decision protection", "决策保护")
        action = _tr(
            language,
            "Evidence is below the decision gate. Do not issue a deterministic recommendation.",
            "证据未通过决策门槛，暂不生成确定性建议。",
        )
        rationale = _tr(
            language,
            f"Current ledger: {insight.support_count} supporting and {insight.contradiction_count} contradicting review(s).",
            f"当前账本包含 {insight.support_count} 条支持证据与 {insight.contradiction_count} 条反向证据。",
        )
        references = _tr(language, "No qualifying evidence refs", "无合格证据引用")
        risk_items = [
            _display_unknown(item, language) for item in insight.unknowns
        ] or [_tr(language, "The claim remains unresolved.", "该结论仍未解决。")]
    else:
        action_label = _tr(language, "Recommended action", "建议动作")
        action = _display_action(recommendation.action, language)
        rationale = _display_rationale(recommendation.rationale, language)
        references = _tr(language, "Evidence refs: ", "证据引用：") + ", ".join(
            recommendation.evidence_refs
        )
        risk_items = [
            _display_risk(flag, language) for flag in recommendation.risk_flags
        ] + [_display_unknown(item, language) for item in recommendation.unknowns]
        if not risk_items:
            risk_items = [
                _tr(
                    language,
                    "No rule-level risk flag; review the quoted evidence before acting.",
                    "当前无规则级风险标记；行动前仍需复核引用原文。",
                )
            ]
    risk_html = "".join(f"<li>{escape(item)}</li>" for item in risk_items)
    return (
        '<div class="voc-decision-pane">'
        f'<div class="voc-decision-kicker">{escape(_tr(language, "Decision brief", "决策摘要"))}</div>'
        f'<div class="voc-decision-title">{escape(title)}</div>'
        f'<div class="voc-decision-label">{escape(action_label)}</div>'
        f'<div class="voc-decision-body">{escape(action)}</div>'
        f'<div class="voc-decision-meta">{escape(rationale)}</div>'
        f'<div class="voc-decision-meta">{escape(references)}</div>'
        '<div class="voc-risk-block">'
        f'<div class="voc-decision-label">{escape(_tr(language, "Risks and evidence gaps", "风险与证据缺口"))}</div>'
        f'<ul>{risk_html}</ul>'
        '</div></div>'
    )


def _analysis_shell_html(
    result: AnalysisResult,
    insight: Insight,
    language: str,
    *,
    sequence: int,
    preserve_claim: bool,
) -> str:
    return (
        '<div class="voc-analysis-shell">'
        + _insight_panel_html(
            result,
            insight,
            language,
            sequence=sequence,
            preserve_claim=preserve_claim,
        )
        + _decision_brief_html(result, insight, language)
        + '</div>'
    )


def _evidence_card(review: ReviewRecord, role: str) -> None:
    """Render one evidence quote for callers that use the legacy helper."""

    st.markdown(_evidence_card_html(review, role), unsafe_allow_html=True)


def _render_insight(result: AnalysisResult, insight: Insight, language: str) -> None:
    """Render a single insight while preserving the pre-redesign entry point."""

    st.markdown(
        _analysis_shell_html(
            result,
            insight,
            language,
            sequence=result.insights.index(insight) + 1,
            preserve_claim=False,
        ),
        unsafe_allow_html=True,
    )


def _primary_insight(result: AnalysisResult) -> Insight | None:
    for insight in result.insights:
        if _recommendation_for_insight(result, insight) is not None:
            return insight
    for insight in result.insights:
        if insight.type != "unknown":
            return insight
    return result.insights[0] if result.insights else None


def _render_analysis_workspace(
    result: AnalysisResult,
    language: str,
    *,
    preserve_claim: bool = False,
    ai_assisted: bool = False,
) -> None:
    primary = _primary_insight(result)
    if primary is None:
        st.warning(_tr(language, "No insight was generated.", "未生成洞察。"))
        return
    heading = _tr(
        language,
        "AI-assisted topic signals" if ai_assisted else "Topic signals",
        "AI 辅助主题信号" if ai_assisted else "主题信号",
    )
    st.markdown(
        '<div class="voc-section-head"><div>'
        f'<h2>{escape(heading)}</h2>'
        '</div></div>',
        unsafe_allow_html=True,
    )
    st.markdown(_evidence_landscape_html(result, language), unsafe_allow_html=True)
    # Streamlit retains formatted option labels across reruns with the same key.
    namespace = f"{'ai' if ai_assisted else 'rules'}_{language}"
    topic_column, scope_column = st.columns([3, 1])
    with scope_column:
        scope = st.selectbox(
            _tr(language, "Decision status", "决策状态"),
            ["all", "actionable", "unresolved"],
            format_func=lambda value: {
                "all": _tr(language, "All topics", "全部主题"),
                "actionable": _tr(language, "Actionable", "可执行"),
                "unresolved": _tr(language, "Needs validation", "待验证"),
            }[value],
            key=f"voc_scope_{namespace}",
        )
    candidates = _filtered_insights(result, scope)
    if not candidates:
        st.info(_tr(language, "No topics match this status.", "当前状态下暂无主题。"))
        return
    with topic_column:
        selected = st.radio(
            _tr(language, "Review topic", "审阅主题"),
            range(len(candidates)),
            format_func=lambda index: TOPIC_LABELS.get(candidates[index].topic, {}).get(language, candidates[index].topic),
            index=candidates.index(primary) if primary in candidates else 0,
            horizontal=True,
            key=f"voc_topic_{namespace}_{scope}",
        )
    primary = candidates[selected]
    primary_index = result.insights.index(primary) + 1
    st.markdown(
        _analysis_shell_html(
            result,
            primary,
            language,
            sequence=primary_index,
            preserve_claim=preserve_claim,
        ),
        unsafe_allow_html=True,
    )
    with st.popover(_tr(language, "View evidence rules", "查看证据规则")):
        st.markdown(
            _tr(
                language,
                "Evidence tiers are deterministic rules, not calibrated probabilities.",
                "证据等级来自确定性规则，不代表经过统计校准的概率。",
            )
        )
        _render_evidence_rules(result, language)

def _recommendation_card_html(
    recommendation: Recommendation,
    language: str,
) -> str:
    risks = " · ".join(
        _display_risk(flag, language) for flag in recommendation.risk_flags
    )
    risk_line = (
        f'<p>{escape(_tr(language, "Risk flags: ", "风险标记：") + risks)}</p>'
        if risks
        else ""
    )
    unknowns = " · ".join(
        _display_unknown(item, language) for item in recommendation.unknowns
    )
    unknown_line = (
        f'<p>{escape(_tr(language, "Unknowns: ", "未知项：") + unknowns)}</p>'
        if unknowns
        else ""
    )
    refs = _tr(language, "Evidence refs: ", "证据引用：") + ", ".join(
        recommendation.evidence_refs
    )
    return (
        '<div class="voc-recommendation-card">'
        f'<h4>{escape(_display_action(recommendation.action, language))}</h4>'
        f'<p>{escape(_display_rationale(recommendation.rationale, language))}</p>'
        + risk_line
        + unknown_line
        + f'<small>{escape(refs)}</small></div>'
    )


def _render_byok_result(result: AnalysisResult, language: str) -> None:
    st.markdown(
        _summary_grid_html(result, language),
        unsafe_allow_html=True,
    )
    _render_analysis_workspace(
        result,
        language,
        preserve_claim=True,
        ai_assisted=True,
    )
    st.markdown("#### " + _tr(language, "AI audit exports", "AI 审计导出"))
    download_columns = st.columns(3)
    download_columns[0].download_button(
        "Markdown",
        data=analysis_to_markdown(result),
        file_name="voc_ai_evidence_audit.md",
        mime="text/markdown",
        key="voc_ai_download_markdown",
        **download_button_options(),
    )
    download_columns[1].download_button(
        "CSV",
        data=analysis_to_csv(result),
        file_name="voc_ai_evidence_ledger.csv",
        mime="text/csv",
        key="voc_ai_download_csv",
        **download_button_options(),
    )
    download_columns[2].download_button(
        "JSON",
        data=analysis_to_json(result),
        file_name="voc_ai_analysis.json",
        mime="application/json",
        key="voc_ai_download_json",
        **download_button_options(),
    )


def _replace_cached_result(
    state: MutableMapping[str, Any],
    key: str,
    build_result: Callable[[], AnalysisResult],
) -> AnalysisResult:
    """Replace a cached analysis without exposing a stale result on failure."""

    state.pop(key, None)
    result = build_result()
    state[key] = result
    return result


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
                _replace_cached_result(
                    st.session_state,
                    result_key,
                    lambda: extract_analysis_result(
                        result.reviews,
                        api_key=api_key,
                        base_url=base_url,
                        model=model,
                    ),
                )
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
    header_slot = st.empty()
    with st.sidebar:
        st.divider()
        source = _review_source_control(language)
    provenance_slot = st.empty()
    provenance_slot.markdown(
        _provenance_html(source, language),
        unsafe_allow_html=True,
    )

    uploaded = None
    if source == "upload":
        uploaded = st.file_uploader(
            _tr(language, "Upload review CSV", "上传评论 CSV"),
            type=["csv"],
            help="review_id, product_id, rating, review_text, review_date, source_type",
        )
        if uploaded is None:
            header_slot.markdown(
                _workspace_header_html(None, language),
                unsafe_allow_html=True,
            )
            st.markdown(
                '<div class="voc-empty-state">'
                + escape(
                    _tr(
                        language,
                        "Upload a CSV to continue.",
                        "请上传 CSV 后继续。",
                    )
                )
                + '</div>',
                unsafe_allow_html=True,
            )
            return

    try:
        validation = read_review_csv(
            uploaded.getvalue() if uploaded is not None else SAMPLE_REVIEWS
        )
    except ReviewValidationError as exc:
        header_slot.markdown(
            _workspace_header_html(None, language),
            unsafe_allow_html=True,
        )
        st.error(str(exc))
        return

    result = analyze_reviews(validation)
    report = validation.report
    if report.valid_rows == 0:
        header_slot.markdown(
            _workspace_header_html(result, language),
            unsafe_allow_html=True,
        )
        st.error(_tr(language, "No valid review rows remain.", "没有可用评论记录。"))
        return

    header_slot.markdown(
        _workspace_header_html(result, language),
        unsafe_allow_html=True,
    )
    st.markdown(
        _summary_grid_html(
            result,
            language,
            input_rows=report.input_rows,
            rejected_rows=report.rejected_rows,
        ),
        unsafe_allow_html=True,
    )

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
        _render_analysis_workspace(result, language)

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
            st.markdown(
                _recommendation_card_html(recommendation, language),
                unsafe_allow_html=True,
            )

        st.markdown("#### " + _tr(language, "Audit exports", "审计导出"))
        download_columns = st.columns(3)
        download_columns[0].download_button(
            "Markdown",
            data=analysis_to_markdown(result),
            file_name="voc_evidence_audit.md",
            mime="text/markdown",
            **download_button_options(),
        )
        download_columns[1].download_button(
            "CSV",
            data=analysis_to_csv(result),
            file_name="voc_evidence_ledger.csv",
            mime="text/csv",
            **download_button_options(),
        )
        download_columns[2].download_button(
            "JSON",
            data=analysis_to_json(result),
            file_name="voc_analysis.json",
            mime="application/json",
            **download_button_options(),
        )
        _render_byok(result, language)

    with tab_data:
        search_column, product_column = st.columns([2, 1])
        with search_column:
            query = st.text_input(_tr(language, "Search source reviews", "搜索评论原文或编号"))
        with product_column:
            product = st.selectbox(
                _tr(language, "Product", "商品"),
                [None] + sorted({review.product_id for review in result.reviews}),
                format_func=lambda value: value if value is not None else _tr(language, "All products", "全部商品"),
            )
        visible_reviews = _filter_reviews(result.reviews, query, product)
        st.caption(_tr(language, f"{len(visible_reviews)} / {len(result.reviews)} reviews", f"显示 {len(visible_reviews)} / {len(result.reviews)} 条评论"))
        visible_frame = pd.DataFrame(
            [review.as_dict() for review in visible_reviews],
            columns=_review_frame(result).columns,
        )
        st.dataframe(
            visible_frame,
            hide_index=True,
            height=440,
            **_stretch_kwargs(st.dataframe),
        )
        st.download_button(
            _tr(language, "Export selected reviews", "导出筛选后的评论"),
            data=visible_frame.to_csv(index=False).encode("utf-8-sig"),
            file_name="voc_filtered_reviews.csv",
            mime="text/csv",
            **download_button_options(),
            disabled=not visible_reviews,
        )
        st.caption(
            _tr(
                language,
                "Changing or removing a source row and uploading the CSV recomputes every count and recommendation.",
                "修改或删除源评论后重新上传，所有计数与建议都会重新计算。",
            )
        )
    st.markdown(
        '<footer class="voc-footer"><span>Evidence Ledger / Amazon VOC Copilot</span>'
        f'<span>{escape(_tr(language, "Rule-based analysis · Human review required", "规则分析 · 需人工复核"))}</span></footer>',
        unsafe_allow_html=True,
    )
