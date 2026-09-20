from __future__ import annotations

import hashlib
import os
from html import escape
from pathlib import Path

import pandas as pd
import streamlit as st

from src.analysis import brand_summary, price_band_summary, summarize_market
from src.connectors.export import (
    build_product_page_workbook,
    coverage_summary_frame,
    decision_summary_frame,
    gap_analysis_frame,
    product_pool_summary_frame,
    product_readiness_summary_frame,
    normalized_specs_frame,
    requirement_draft_frame,
    specification_matrix_frame,
    supplier_comparison_frame,
    supplier_follow_up_frame,
)
from src.connectors.product_page import collect_product_pages
from src.finance import ProfitAssumptions
from src.i18n import (
    LANGUAGE_DISPLAY_NAMES,
    SUPPORTED_LANGUAGES,
    column_label,
    normalize_language,
    t,
)
from src.importers.export import (
    build_normalized_workbook,
    prepare_export_result,
)
from src.importers.mapping import (
    STANDARD_FIELDS,
    FieldMappingError,
    apply_field_mapping,
    suggest_field_mappings,
    validate_field_mapping,
)
from src.importers.tabular import (
    TabularImportError,
    list_worksheets,
    read_tabular_file,
)
from src.importers.validation import validate_and_clean_import
from src.specs import list_spec_profiles
from src.templates import build_template_workbook, list_template_definitions
from src.voc_dashboard import inject_app_styles, render_voc_dashboard
from src.workspace import (
    build_project_workspace,
    export_workspace_json,
    import_workspace_json,
    product_card_rows,
    supplier_card_rows,
    task_rows,
)


st.set_page_config(
    page_title="Evidence-Backed Amazon VOC Copilot",
    layout="wide",
)
inject_app_styles()

sample_path = Path(__file__).parent / "data" / "sample_products.csv"

DISPLAY_TO_LANGUAGE = {
    LANGUAGE_DISPLAY_NAMES[code]: code for code in SUPPORTED_LANGUAGES
}


def _language_select(label: str, default: str = "en") -> str:
    default_code = normalize_language(default)
    options = [LANGUAGE_DISPLAY_NAMES[code] for code in SUPPORTED_LANGUAGES]
    selected = st.selectbox(
        label,
        options,
        index=list(SUPPORTED_LANGUAGES).index(default_code),
    )
    return DISPLAY_TO_LANGUAGE[selected]


with st.sidebar:
    sidebar_identity = st.empty()
    language = _language_select("Language / 语言", "zh-CN")

sidebar_identity.markdown(
    """
    <div class="voc-sidebar-brand">
      <span class="voc-sidebar-mark">V</span>
      <span>
        <strong>Evidence Ledger</strong>
        <small>Amazon VOC Copilot</small>
      </span>
    </div>
    """,
    unsafe_allow_html=True,
)


def _localized_frame(frame: pd.DataFrame, language: str) -> pd.DataFrame:
    return frame.rename(columns={column: column_label(str(column), language) for column in frame.columns})


def _parse_url_lines(value: str) -> list[str]:
    return [line.strip() for line in value.splitlines() if line.strip()]


def _mode_header_html(mode: str, language: str) -> str:
    copy = {
        "sample": {
            "en": (
                "PRODUCT RESEARCH · INCLUDED DATA",
                "Product research workspace",
                "Review the included dataset, confirm its fields, and compare market and profit signals.",
            ),
            "zh-CN": (
                "PRODUCT RESEARCH · INCLUDED DATA",
                "产品调研工作台",
                "使用内置示例数据校验字段，并对比市场与利润信号。",
            ),
        },
        "spreadsheet": {
            "en": (
                "PRODUCT RESEARCH · USER UPLOAD",
                "Spreadsheet import workspace",
                "Validate a CSV or Excel file before using it for market and profit analysis.",
            ),
            "zh-CN": (
                "PRODUCT RESEARCH · USER UPLOAD",
                "表格导入工作台",
                "先校验 CSV 或 Excel 的字段与数据质量，再进入市场与利润分析。",
            ),
        },
        "templates": {
            "en": (
                "DATA OPERATIONS · STANDARD INPUTS",
                "Template center",
                "Download structured inputs for product research, supplier evaluation, and specification collection.",
            ),
            "zh-CN": (
                "DATA OPERATIONS · STANDARD INPUTS",
                "标准模板中心",
                "下载用于产品调研、供应商评估和规格收集的结构化模板。",
            ),
        },
        "workspace": {
            "en": (
                "PROJECT OPERATIONS · DECISION TRACKING",
                "Project workspace",
                "Review product candidates, suppliers, and unresolved follow-up tasks in one operational view.",
            ),
            "zh-CN": (
                "PROJECT OPERATIONS · DECISION TRACKING",
                "项目工作台",
                "在同一工作视图中复核产品候选、供应商与待追问任务。",
            ),
        },
        "urls": {
            "en": (
                "PUBLIC SOURCES · SPECIFICATION INTAKE",
                "Public product page connector",
                "Collect auditable product and specification data from permitted public pages.",
            ),
            "zh-CN": (
                "PUBLIC SOURCES · SPECIFICATION INTAKE",
                "公开产品页面连接器",
                "从允许访问的公开页面收集可追溯的产品与规格数据。",
            ),
        },
    }
    kicker, title, description = copy[mode][language]
    return (
        '<header class="app-page-header">'
        f'<div class="app-page-kicker">{escape(kicker)}</div>'
        f'<h1>{escape(title)}</h1>'
        f'<p>{escape(description)}</p>'
        "</header>"
    )


def _show_template_center(language: str) -> None:
    button_keys = {
        "market_research": "download_market_research_template",
        "supplier_quote": "download_supplier_quote_template",
        "product_url_import": "download_product_url_template",
        "security_camera_specs": "download_security_camera_template",
        "vehicle_camera_specs": "download_vehicle_camera_template",
    }

    for definition in list_template_definitions():
        with st.container(border=True):
            st.markdown(f"### {definition.title(language)}")
            st.write(definition.description(language))
            st.download_button(
                t(button_keys[definition.template_id], language),
                data=build_template_workbook(definition.template_id, language),
                file_name=definition.file_name,
                mime=(
                    "application/vnd.openxmlformats-officedocument."
                    "spreadsheetml.sheet"
                ),
                key=f"template::{definition.template_id}::{language}",
            )


with st.sidebar:
    st.header(t("data_source", language))

    mode_labels = {
        "voc": t("voc_evidence_ledger", language),
        "sample": t("use_sample_data", language),
        "spreadsheet": t("upload_csv_excel", language),
        "templates": t("template_center", language),
        "workspace": "Workspace" if language == "en" else "项目工作台",
    }
    if os.environ.get("ENABLE_PUBLIC_URL_IMPORT", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }:
        mode_labels["urls"] = t("import_from_product_urls", language)
    selected_mode_label = st.radio(
        t("input_mode", language),
        list(mode_labels.values()),
        index=0,
    )
    data_source_mode = {
        value: key for key, value in mode_labels.items()
    }[selected_mode_label]

    export_language = language
    if data_source_mode != "voc":
        export_language = _language_select(t("export_language", language), language)

    uploaded_file = None
    if data_source_mode == "spreadsheet":
        uploaded_file = st.file_uploader(
            t("upload_csv_excel", language),
            type=["csv", "xlsx", "xls"],
            help="CSV, XLSX, XLS. 20MB per file.",
        )
    elif data_source_mode == "urls":
        st.caption(
            "Use public supplier or brand product pages. Do not use login-only, "
            "CAPTCHA-protected or restricted pages."
            if language == "en"
            else "请使用公开供应商或品牌产品页面。不要使用登录、验证码保护或受限页面。"
        )

    if data_source_mode in {"sample", "spreadsheet"}:
        st.header(t("profit_assumptions", language))
        product_cost = st.number_input(
            t("product_cost_per_unit", language),
            min_value=0.0,
            value=30.0,
            step=1.0,
        )
        shipping_cost = st.number_input(
            t("shipping_cost_per_unit", language),
            min_value=0.0,
            value=8.0,
            step=1.0,
        )
        platform_fee_rate = st.number_input(
            t("platform_fee_rate", language),
            min_value=0.0,
            max_value=100.0,
            value=15.0,
            step=0.5,
        )
        advertising_cost_rate = st.number_input(
            t("advertising_cost_rate", language),
            min_value=0.0,
            max_value=100.0,
            value=10.0,
            step=0.5,
        )
        return_rate = st.number_input(
            t("return_rate", language),
            min_value=0.0,
            max_value=100.0,
            value=5.0,
            step=0.5,
        )


if data_source_mode == "voc":
    render_voc_dashboard(language=language)
    st.stop()


st.markdown(
    _mode_header_html(data_source_mode, language),
    unsafe_allow_html=True,
)

if data_source_mode == "workspace":
    uploaded_workspace = st.file_uploader(
        "Upload project JSON" if language == "en" else "上传项目 JSON",
        type=["json"],
    )

    workspace = None
    if uploaded_workspace is not None:
        try:
            workspace = import_workspace_json(uploaded_workspace.getvalue())
            st.success("Project loaded." if language == "en" else "项目已加载。")
        except ValueError as exc:
            st.error(str(exc))
            st.stop()
    else:
        connector_result = st.session_state.get("product_page_connector_result")
        if connector_result is not None:
            default_profile = "generic_hardware"
            readiness = product_readiness_summary_frame(connector_result, profile=default_profile, language=language)
            suppliers = supplier_comparison_frame(connector_result, profile=default_profile, language=language)
            pool = product_pool_summary_frame(connector_result, profile=default_profile, language=language)
            follow_up = supplier_follow_up_frame(connector_result, profile=default_profile, language=language)
            workspace = build_project_workspace(
                project_name="Current Connector Analysis" if language == "en" else "当前连接器分析",
                profile=default_profile,
                language=language,
                product_pool=pool,
                supplier_comparison=suppliers,
                supplier_follow_up=follow_up,
            )

    if workspace is None:
        st.info(
            "Run the Product URL Connector first, or upload a project JSON."
            if language == "en"
            else "请先运行产品 URL 连接器，或上传项目 JSON。"
        )
        st.stop()

    metrics = workspace.metrics
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Products" if language == "en" else "产品", f"{metrics.product_count:,}")
    c2.metric("Suppliers" if language == "en" else "供应商", f"{metrics.supplier_count:,}")
    c3.metric("Review candidates" if language == "en" else "评审候选", f"{metrics.review_candidate_count:,}")
    c4.metric("High risk" if language == "en" else "高风险", f"{metrics.high_risk_product_count:,}")
    c5.metric("Open questions" if language == "en" else "待追问", f"{metrics.open_follow_up_count:,}")

    st.download_button(
        "Download project JSON" if language == "en" else "下载项目 JSON",
        data=export_workspace_json(workspace),
        file_name="project_workspace.json",
        mime="application/json",
    )

    tab_products, tab_suppliers, tab_tasks = st.tabs(
        [
            "Product Pool" if language == "en" else "产品池",
            "Supplier Pool" if language == "en" else "供应商池",
            "Follow-up Tasks" if language == "en" else "追问任务",
        ]
    )
    with tab_products:
        st.dataframe(product_card_rows(workspace), use_container_width=True, hide_index=True)
    with tab_suppliers:
        st.dataframe(supplier_card_rows(workspace), use_container_width=True, hide_index=True)
    with tab_tasks:
        st.dataframe(task_rows(workspace), use_container_width=True, hide_index=True)

    st.stop()


if data_source_mode == "templates":
    _show_template_center(language)
    st.stop()


if data_source_mode == "urls":
    st.warning(t("connector_scope_warning", language), icon="⚠️")

    profile_options = {
        profile.label(language): profile.profile_id
        for profile in list_spec_profiles()
    }
    selected_profile_label = st.selectbox(
        "Spec profile" if language == "en" else "规格配置模板",
        list(profile_options.keys()),
        index=0,
    )
    selected_profile = profile_options[selected_profile_label]

    url_text = st.text_area(
        t("product_page_urls", language),
        height=150,
        placeholder=(
            "https://supplier.example.com/product/wireless-backup-camera\n"
            "https://brand.example.com/products/4g-solar-camera"
        ),
    )
    urls = _parse_url_lines(url_text)

    if st.button(t("fetch_product_pages", language), type="primary"):
        if not urls:
            st.error(
                "Paste at least one product page URL."
                if language == "en"
                else "请至少粘贴一个产品页面 URL。"
            )
        else:
            spinner_text = (
                f"Fetching {len(urls)} URL(s)..."
                if language == "en"
                else f"正在抓取 {len(urls)} 个 URL..."
            )
            with st.spinner(spinner_text):
                st.session_state["product_page_connector_result"] = collect_product_pages(urls)

    connector_result = st.session_state.get("product_page_connector_result")
    if connector_result is None:
        st.info(
            "Paste public supplier or brand product URLs above, then select “Fetch product pages”."
            if language == "en"
            else "在上方粘贴公开供应商或品牌产品页面 URL，然后点击“抓取产品页面”。"
        )
        st.stop()

    products_frame = connector_result.products_frame
    specs_frame = connector_result.raw_specs_frame
    normalized_frame = normalized_specs_frame(connector_result, language)
    matrix_frame = specification_matrix_frame(connector_result, language)
    coverage_frame = coverage_summary_frame(connector_result, language)
    gaps_frame = gap_analysis_frame(
        connector_result,
        profile=selected_profile,
        language=language,
    )
    requirement_frame = requirement_draft_frame(
        connector_result,
        profile=selected_profile,
        language=language,
    )
    supplier_follow_up = supplier_follow_up_frame(
        connector_result,
        profile=selected_profile,
        language=language,
    )
    decision_summary = decision_summary_frame(
        connector_result,
        profile=selected_profile,
        language=language,
    )
    product_readiness = product_readiness_summary_frame(
        connector_result,
        profile=selected_profile,
        language=language,
    )
    supplier_comparison = supplier_comparison_frame(
        connector_result,
        profile=selected_profile,
        language=language,
    )
    product_pool = product_pool_summary_frame(
        connector_result,
        profile=selected_profile,
        language=language,
    )
    logs_frame = connector_result.fetch_logs_frame
    issues_frame = connector_result.issues_frame

    def _ui_label(en: str, zh: str) -> str:
        return zh if language == "zh-CN" else en

    def _display_frame(
        frame: pd.DataFrame,
        *,
        percent_fields: list[str] | None = None,
        height: int | None = None,
    ) -> None:
        percent_fields = percent_fields or []
        display = _localized_frame(frame, language)
        column_config = {}
        for field in percent_fields:
            localized = column_label(field, language)
            if localized in display.columns:
                column_config[localized] = st.column_config.NumberColumn(
                    localized,
                    format="percent",
                )
        dataframe_kwargs = {
            "use_container_width": True,
            "hide_index": True,
            "column_config": column_config,
        }
        if height is not None:
            dataframe_kwargs["height"] = height
        st.dataframe(display, **dataframe_kwargs)

    def _preview_columns(frame: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
        selected = [column for column in columns if column in frame.columns]
        return frame[selected].copy() if selected else frame.copy()

    st.subheader(t("connector_results", language))

    # Decision-first KPI section. This replaces the previous long, tab-heavy
    # interface with a compact dashboard that emphasizes what users should do next.
    avg_readiness = 0 if product_readiness.empty else product_readiness["readiness_score"].mean()
    review_candidates = 0 if product_pool.empty else int((product_pool["priority"] == "P1").sum())
    supplier_count = len(supplier_comparison)
    follow_up_questions = 0 if supplier_follow_up.empty else len(supplier_follow_up)

    kpi_1, kpi_2, kpi_3, kpi_4 = st.columns(4)
    kpi_1.metric(_ui_label("Avg. readiness", "平均就绪度"), f"{avg_readiness:.1f}")
    kpi_2.metric(_ui_label("Review candidates", "评审候选"), f"{review_candidates:,}")
    kpi_3.metric(_ui_label("Suppliers", "供应商"), f"{supplier_count:,}")
    kpi_4.metric(_ui_label("Follow-up questions", "追问问题"), f"{follow_up_questions:,}")

    health_1, health_2, health_3, health_4 = st.columns(4)
    health_1.metric(t("products", language), f"{len(products_frame):,}")
    health_2.metric(
        t("successful_fetches", language),
        f"{int(logs_frame['success'].sum()) if not logs_frame.empty else 0:,}",
    )
    health_3.metric(t("raw_specs", language), f"{len(specs_frame):,}")
    health_4.metric(t("issues", language), f"{len(issues_frame):,}")

    if products_frame.empty:
        st.error(
            "No product records were produced. Check whether the URLs are public HTML product pages."
            if language == "en"
            else "未生成产品记录。请检查 URL 是否为公开 HTML 产品页面。"
        )
    elif specs_frame.empty:
        st.warning(
            "The page was fetched, but no technical specification table was detected. Use supplier or brand product detail pages with visible specification tables for better results."
            if language == "en"
            else "页面已抓取，但未识别到技术规格表。建议使用包含明确规格表的供应商或品牌产品详情页。"
        )

    st.download_button(
        t("download_product_page_workbook", language),
        data=build_product_page_workbook(
            connector_result,
            language=export_language,
            profile=selected_profile,
        ),
        file_name="product_page_import.xlsx",
        mime=(
            "application/vnd.openxmlformats-officedocument."
            "spreadsheetml.sheet"
        ),
    )

    (
        tab_overview,
        tab_decision,
        tab_specs,
        tab_requirements,
        tab_diagnostics,
    ) = st.tabs(
        [
            _ui_label("Overview", "总览"),
            _ui_label("Decision Board", "决策看板"),
            _ui_label("Specifications", "规格分析"),
            _ui_label("Requirements", "需求与追问"),
            _ui_label("Diagnostics", "诊断数据"),
        ]
    )

    with tab_overview:
        st.markdown(
            "#### " + _ui_label("Recommended working view", "推荐工作视图")
        )
        st.caption(
            _ui_label(
                "Start with Product Pool and Supplier Comparison. Use Diagnostics only when you need raw evidence or troubleshooting.",
                "优先查看产品池和供应商对比。只有需要原始证据或排查问题时，再进入诊断数据。",
            )
        )

        left, right = st.columns([1.4, 1])
        with left:
            st.markdown("##### " + _ui_label("Top product candidates", "优先产品候选"))
            product_preview = _preview_columns(
                product_pool,
                [
                    "priority",
                    "title",
                    "brand",
                    "model",
                    "readiness_score",
                    "product_pool_status",
                    "risk_level",
                    "follow_up_question_count",
                    "source_url",
                ],
            )
            _display_frame(product_preview, height=320)
        with right:
            st.markdown("##### " + _ui_label("Supplier snapshot", "供应商概览"))
            supplier_preview = _preview_columns(
                supplier_comparison,
                [
                    "supplier_name",
                    "product_count",
                    "average_readiness_score",
                    "overall_status",
                    "total_follow_up_questions",
                ],
            )
            _display_frame(supplier_preview, height=320)

    with tab_decision:
        decision_view_options = {
            _ui_label("Product Pool", "产品池"): "pool",
            _ui_label("Readiness Score", "就绪度评分"): "readiness",
            _ui_label("Supplier Comparison", "供应商对比"): "suppliers",
            _ui_label("Decision Summary", "决策摘要"): "decision",
        }
        selected_decision_view = st.selectbox(
            _ui_label("Decision view", "决策视图"),
            list(decision_view_options.keys()),
        )
        decision_view = decision_view_options[selected_decision_view]

        if decision_view == "pool":
            _display_frame(
                product_pool,
                percent_fields=["completion_rate", "metadata_completeness"],
            )
        elif decision_view == "readiness":
            _display_frame(
                product_readiness,
                percent_fields=["completion_rate", "metadata_completeness"],
            )
        elif decision_view == "suppliers":
            _display_frame(
                supplier_comparison,
                percent_fields=["average_completion_rate"],
            )
        else:
            _display_frame(decision_summary, percent_fields=["completion_rate"])

    with tab_specs:
        spec_view_options = {
            t("specification_matrix", language): "matrix",
            t("coverage_summary", language): "coverage",
            t("gap_analysis", language): "gaps",
            t("normalized_specifications", language): "normalized",
        }
        selected_spec_view = st.selectbox(
            _ui_label("Specification view", "规格视图"),
            list(spec_view_options.keys()),
        )
        spec_view = spec_view_options[selected_spec_view]

        if spec_view == "matrix":
            _display_frame(matrix_frame)
        elif spec_view == "coverage":
            _display_frame(coverage_frame, percent_fields=["coverage_rate"])
        elif spec_view == "gaps":
            _display_frame(gaps_frame, percent_fields=["completion_rate"])
        else:
            _display_frame(normalized_frame)

    with tab_requirements:
        requirement_view_options = {
            t("requirement_draft", language): "draft",
            t("supplier_follow_up", language): "follow_up",
        }
        selected_requirement_view = st.selectbox(
            _ui_label("Requirement view", "需求视图"),
            list(requirement_view_options.keys()),
        )
        requirement_view = requirement_view_options[selected_requirement_view]

        if requirement_view == "draft":
            _display_frame(requirement_frame)
        else:
            _display_frame(supplier_follow_up)

    with tab_diagnostics:
        diagnostics_view_options = {
            t("products", language): "products",
            t("raw_specifications", language): "raw_specs",
            t("fetch_logs", language): "logs",
            t("issues", language): "issues",
        }
        selected_diagnostics_view = st.selectbox(
            _ui_label("Diagnostics view", "诊断视图"),
            list(diagnostics_view_options.keys()),
        )
        diagnostics_view = diagnostics_view_options[selected_diagnostics_view]

        if diagnostics_view == "products":
            _display_frame(products_frame)
        elif diagnostics_view == "raw_specs":
            _display_frame(specs_frame)
        elif diagnostics_view == "logs":
            _display_frame(logs_frame)
        else:
            if issues_frame.empty:
                st.success(
                    "No connector issues were recorded."
                    if language == "en"
                    else "未记录连接器问题。"
                )
            else:
                _display_frame(issues_frame)

    st.stop()


if data_source_mode == "spreadsheet":
    if uploaded_file is None:
        st.info("Upload a spreadsheet to continue." if language == "en" else "请上传表格文件继续。")
        st.stop()
    file_name = uploaded_file.name
    file_content = uploaded_file.getvalue()
else:
    file_name = sample_path.name
    file_content = sample_path.read_bytes()

worksheet: str | None = None
st.subheader(t("step_select_source", language))
try:
    sheets = list_worksheets(file_name, file_content)
    if sheets:
        worksheet = st.selectbox(t("worksheet", language), sheets)
    else:
        st.caption(
            "CSV and sample files do not require worksheet selection."
            if language == "en"
            else "CSV 和示例文件不需要选择工作表。"
        )
    raw_data = read_tabular_file(file_name, file_content, worksheet)
except TabularImportError as exc:
    st.error(f"Unable to import file: {exc}" if language == "en" else f"无法导入文件：{exc}")
    st.stop()

st.subheader(t("step_preview_data", language))
preview_1, preview_2 = st.columns(2)
preview_1.metric(t("rows", language), f"{len(raw_data):,}")
preview_2.metric(t("columns", language), f"{len(raw_data.columns):,}")
st.dataframe(raw_data.head(20), use_container_width=True, hide_index=True)

st.subheader(t("step_confirm_mapping", language))
suggestions = suggest_field_mappings(raw_data.columns)
not_mapped = t("not_mapped", language)
options = [not_mapped, *[str(column) for column in raw_data.columns]]
mapping: dict[str, str | None] = {}

mapping_columns = st.columns(2)
for index, standard_field in enumerate(STANDARD_FIELDS):
    suggestion = suggestions.get(standard_field)
    default_index = options.index(suggestion) if suggestion in options else 0
    with mapping_columns[index % 2]:
        selected = st.selectbox(
            column_label(standard_field, language),
            options,
            index=default_index,
            key=f"mapping::{file_name}::{worksheet}::{standard_field}::{language}",
        )
    mapping[standard_field] = None if selected == not_mapped else selected

mapping_error: str | None = None
try:
    validate_field_mapping(mapping, raw_data.columns)
except FieldMappingError as exc:
    mapping_error = str(exc)
    st.warning(mapping_error)

signature_payload = repr(
    (file_name, worksheet, sorted(mapping.items()))
).encode("utf-8")
import_signature = hashlib.sha256(signature_payload).hexdigest()

if st.session_state.get("import_signature") != import_signature:
    st.session_state.pop("import_result", None)
    st.session_state["import_signature"] = import_signature

if st.button(
    t("validate_and_import", language),
    type="primary",
    disabled=mapping_error is not None,
):
    try:
        mapped_data = apply_field_mapping(raw_data, mapping)
        st.session_state["import_result"] = validate_and_clean_import(
            mapped_data,
            source_file=file_name,
            worksheet=worksheet,
            mapping={
                field: str(source)
                for field, source in mapping.items()
                if source is not None
            },
        )
    except (FieldMappingError, ValueError) as exc:
        st.error(f"Import validation failed: {exc}" if language == "en" else f"导入校验失败：{exc}")

result = st.session_state.get("import_result")
if result is None:
    st.info(
        "Confirm the mappings and select “Validate and import” to continue."
        if language == "en"
        else "确认字段映射后，点击“校验并导入”继续。"
    )
    st.stop()

st.subheader(t("step_import_validation", language))
report = result.report
report_columns = st.columns(5)
report_columns[0].metric(t("original_rows", language), f"{report.original_rows:,}")
report_columns[1].metric(t("valid_rows", language), f"{report.valid_rows:,}")
report_columns[2].metric(t("rejected_rows", language), f"{report.rejected_rows:,}")
report_columns[3].metric(t("warning_rows", language), f"{report.warning_rows:,}")
report_columns[4].metric(t("duplicate_asins", language), f"{report.duplicate_asins:,}")

if result.issues:
    st.dataframe(
        _localized_frame(result.issues_frame, language),
        use_container_width=True,
        hide_index=True,
    )
else:
    st.success(t("no_import_issues", language))

if result.products.empty:
    st.error("No valid product rows remain. Correct the source file and retry." if language == "en" else "没有可用产品行。请修正源文件后重试。")
    st.stop()

assumptions = ProfitAssumptions(
    product_cost=product_cost,
    shipping_cost=shipping_cost,
    platform_fee_rate=platform_fee_rate / 100,
    advertising_cost_rate=advertising_cost_rate / 100,
    return_rate=return_rate / 100,
)

try:
    export_result = prepare_export_result(result, assumptions)
except ValueError as exc:
    st.error(f"Invalid profit assumptions: {exc}" if language == "en" else f"利润参数无效：{exc}")
    st.stop()

workbook_bytes = build_normalized_workbook(export_result, language=export_language)
st.download_button(
    t("download_normalized_workbook", language),
    data=workbook_bytes,
    file_name="normalized_products.xlsx",
    mime=(
        "application/vnd.openxmlformats-officedocument."
        "spreadsheetml.sheet"
    ),
)

data = export_result.products.copy()
categories = sorted(data["category"].dropna().unique().tolist())
brands = sorted(data["brand"].dropna().unique().tolist())

with st.sidebar:
    selected_categories = st.multiselect(
        t("category_filter", language),
        categories,
        default=categories,
    )
    selected_brands = st.multiselect(
        t("brand_filter", language),
        brands,
        default=brands,
    )

filtered = data[
    data["category"].isin(selected_categories)
    & data["brand"].isin(selected_brands)
].copy()

st.subheader(t("step_market_profit", language))
summary = summarize_market(filtered)

metric_1, metric_2, metric_3, metric_4, metric_5 = st.columns(5)
metric_1.metric(t("products", language), f"{summary.product_count}")
metric_2.metric(t("average_price", language), f"${summary.average_price:,.2f}")
metric_3.metric(t("median_reviews", language), f"{summary.median_reviews:,.0f}")
metric_4.metric(
    t("estimated_monthly_revenue", language),
    f"${summary.estimated_monthly_revenue:,.0f}",
)
metric_5.metric(t("top_brand_share", language), f"{summary.top_brand_share:.1%}")

total_monthly_net_profit = float(
    filtered["estimated_monthly_net_profit"].sum()
)
total_revenue = float(filtered["estimated_monthly_revenue"].sum())
weighted_net_margin = (
    total_monthly_net_profit / total_revenue if total_revenue else 0.0
)
average_unit_net_profit = (
    float(filtered["estimated_unit_net_profit"].mean())
    if not filtered.empty
    else 0.0
)
break_even_price = (
    float(filtered["break_even_price"].iloc[0])
    if not filtered.empty
    else 0.0
)

profit_1, profit_2, profit_3, profit_4 = st.columns(4)
profit_1.metric(
    t("estimated_monthly_net_profit", language),
    f"${total_monthly_net_profit:,.0f}",
)
profit_2.metric(t("weighted_net_margin", language), f"{weighted_net_margin:.1%}")
profit_3.metric(
    t("average_unit_net_profit", language),
    f"${average_unit_net_profit:,.2f}",
)
profit_4.metric(t("break_even_price", language), f"${break_even_price:,.2f}")

st.subheader(t("highest_opportunity_products", language))
opportunities = filtered.sort_values(
    ["opportunity_score", "estimated_monthly_revenue"],
    ascending=False,
)
opportunity_columns = [
    "asin",
    "title",
    "brand",
    "price",
    "rating",
    "reviews",
    "monthly_sales",
    "estimated_monthly_revenue",
    "estimated_unit_net_profit",
    "estimated_net_margin",
    "estimated_monthly_net_profit",
    "opportunity_score",
]
opportunity_frame = opportunities[opportunity_columns].rename(
    columns={column: column_label(column, language) for column in opportunity_columns}
)
net_margin_label = column_label("estimated_net_margin", language)
st.dataframe(
    opportunity_frame,
    use_container_width=True,
    hide_index=True,
    column_config={
        net_margin_label: st.column_config.NumberColumn(
            net_margin_label,
            format="percent",
        ),
    },
)

left, right = st.columns(2)
with left:
    st.subheader(t("brand_revenue", language))
    brand_data = brand_summary(filtered)
    if not brand_data.empty:
        st.bar_chart(
            brand_data.set_index("brand")[
                "estimated_monthly_revenue"
            ]
        )
        st.dataframe(
            _localized_frame(brand_data, language),
            use_container_width=True,
            hide_index=True,
        )

with right:
    st.subheader(t("price_bands", language))
    price_data = price_band_summary(filtered)
    if not price_data.empty:
        st.bar_chart(
            price_data.set_index("price_band")["monthly_sales"]
        )
        st.dataframe(
            _localized_frame(price_data, language),
            use_container_width=True,
            hide_index=True,
        )
