from __future__ import annotations

from typing import Any


DEFAULT_LANGUAGE = "en"
SUPPORTED_LANGUAGES = ("en", "zh-CN")
LANGUAGE_DISPLAY_NAMES = {
    "en": "English",
    "zh-CN": "简体中文",
}


TEXT: dict[str, dict[str, str]] = {
    "en": {
        "app_title": "Evidence-Backed Amazon VOC Copilot",
        "app_caption": (
            "Trace product opportunities to supporting reviews, counter-evidence "
            "and explicit unknowns before making a decision."
        ),
        "language": "Language",
        "data_source": "Data source",
        "input_mode": "Input mode",
        "use_sample_data": "Use included sample data",
        "voc_evidence_ledger": "VOC evidence ledger",
        "upload_csv_excel": "Upload CSV or Excel",
        "import_from_product_urls": "Import from product URLs",
        "template_center": "Template Center",
        "profit_assumptions": "Profit assumptions",
        "product_cost_per_unit": "Product cost per unit ($)",
        "shipping_cost_per_unit": "Shipping cost per unit ($)",
        "platform_fee_rate": "Platform fee rate (%)",
        "advertising_cost_rate": "Advertising cost rate (%)",
        "return_rate": "Return rate (%)",
        "step_select_source": "Step 1 — Select source data",
        "step_preview_data": "Step 2 — Preview source data",
        "step_confirm_mapping": "Step 3 — Confirm field mapping",
        "step_import_validation": "Step 4 — Import validation",
        "step_market_profit": "Step 5 — Market and profit analysis",
        "worksheet": "Worksheet",
        "rows": "Rows",
        "columns": "Columns",
        "validate_and_import": "Validate and import",
        "download_normalized_workbook": "Download normalized workbook",
        "download_product_page_workbook": "Download product page import workbook",
        "original_rows": "Original rows",
        "valid_rows": "Valid rows",
        "rejected_rows": "Rejected rows",
        "warning_rows": "Warning rows",
        "duplicate_asins": "Duplicate ASINs",
        "no_import_issues": "No import issues were detected.",
        "product_page_connector": "Public product page connector",
        "product_page_connector_caption": (
            "Paste public supplier or brand product page URLs. The connector extracts "
            "JSON-LD Product data, HTML specification tables, document links and fetch logs."
        ),
        "connector_scope_warning": (
            "Scope: public static product pages only. This connector does not bypass logins, "
            "CAPTCHA, paywalls or site access restrictions. Amazon page scraping is out of scope."
        ),
        "product_page_urls": "Product page URLs, one per line",
        "fetch_product_pages": "Fetch product pages",
        "connector_results": "Connector results",
        "products": "Products",
        "raw_specifications": "Raw Specifications",
        "normalized_specifications": "Normalized Specifications",
        "specification_matrix": "Specification Matrix",
        "coverage_summary": "Coverage Summary",
        "gap_analysis": "Gap Analysis",
        "requirement_draft": "Requirement Draft",
        "supplier_follow_up": "Supplier Follow-up",
        "decision_summary": "Decision Summary",
        "product_readiness_summary": "Readiness Score",
        "supplier_comparison": "Supplier Comparison",
        "product_pool_summary": "Product Pool",
        "fetch_logs": "Fetch Logs",
        "issues": "Issues",
        "successful_fetches": "Successful fetches",
        "raw_specs": "Raw specs",
        "template_center_intro": (
            "Download structured templates for product research, supplier evaluation "
            "and hardware specification collection."
        ),
        "download_market_research_template": "Download market research template",
        "download_supplier_quote_template": "Download supplier quote template",
        "download_product_url_template": "Download product URL import template",
        "download_security_camera_template": "Download security camera specification template",
        "download_vehicle_camera_template": "Download vehicle camera specification template",
        "market_analysis": "Market and profit analysis",
        "highest_opportunity_products": "Highest opportunity products",
        "brand_revenue": "Brand revenue",
        "price_bands": "Price bands",
        "estimated_monthly_revenue": "Estimated monthly revenue",
        "estimated_monthly_net_profit": "Estimated monthly net profit",
        "weighted_net_margin": "Weighted net margin",
        "average_unit_net_profit": "Average unit net profit",
        "break_even_price": "Break-even price",
        "top_brand_share": "Top brand share",
        "average_price": "Average price",
        "median_reviews": "Median reviews",
        "category_filter": "Categories",
        "brand_filter": "Brands",
        "export_language": "Export language",
        "not_mapped": "— Not mapped —",
        "missing_required_fields": "Required fields are not mapped: {fields}",
        "duplicate_source_columns": "Each source column can only be assigned once: {columns}",
        "url_empty": "URL is empty.",
        "unsupported_url_scheme": "Unsupported URL scheme '{scheme}'. Only http and https are supported.",
        "localhost_not_supported": "Localhost URLs are not supported by this connector.",
        "duplicate_url_skipped": "Duplicate URL was skipped.",
        "fetch_timeout": "Request timed out after {seconds:g} seconds.",
        "fetch_not_html": (
            "The URL was fetched but did not return an HTML document "
            "(content-type: {content_type})."
        ),
        "fetch_http_error": "HTTP {status_code} returned for URL.",
        "no_product_data": "No product title or specification data was detected.",
        "missing_asin": "ASIN is required; the row will be rejected.",
        "duplicate_asin": "Duplicate ASIN; only the first row will be retained.",
        "invalid_numeric": "{field} could not be converted to a number.",
        "negative_value_normalized": "Negative {field} will be normalized to zero.",
        "rating_out_of_range": "Rating will be limited to the 0–5 range.",
        "blank_value_normalized": "Blank {field} will be replaced with '{replacement}'.",
    },
    "zh-CN": {
        "app_title": "Amazon VOC 证据决策台",
        "app_caption": "在做选品判断前，将每条机会结论追溯到支持评论、反向证据和明确未知项。",
        "language": "语言",
        "data_source": "数据来源",
        "input_mode": "输入方式",
        "use_sample_data": "使用示例数据",
        "voc_evidence_ledger": "VOC 证据账本",
        "upload_csv_excel": "上传 CSV 或 Excel",
        "import_from_product_urls": "从产品页面 URL 导入",
        "template_center": "模板中心",
        "profit_assumptions": "利润参数",
        "product_cost_per_unit": "单件产品成本（美元）",
        "shipping_cost_per_unit": "单件物流成本（美元）",
        "platform_fee_rate": "平台费率（%）",
        "advertising_cost_rate": "广告费率（%）",
        "return_rate": "退货损失率（%）",
        "step_select_source": "步骤 1 — 选择数据来源",
        "step_preview_data": "步骤 2 — 预览源数据",
        "step_confirm_mapping": "步骤 3 — 确认字段映射",
        "step_import_validation": "步骤 4 — 导入校验",
        "step_market_profit": "步骤 5 — 市场与利润分析",
        "worksheet": "工作表",
        "rows": "行数",
        "columns": "列数",
        "validate_and_import": "校验并导入",
        "download_normalized_workbook": "下载标准化工作簿",
        "download_product_page_workbook": "下载产品页面导入工作簿",
        "original_rows": "原始行数",
        "valid_rows": "有效行数",
        "rejected_rows": "拒绝行数",
        "warning_rows": "警告行数",
        "duplicate_asins": "重复 ASIN",
        "no_import_issues": "未发现导入问题。",
        "product_page_connector": "公开产品页面连接器",
        "product_page_connector_caption": "粘贴公开供应商或品牌产品页面 URL，提取 JSON-LD 产品数据、HTML 规格表、文档链接和抓取日志。",
        "connector_scope_warning": "范围：仅支持公开静态产品页面。本连接器不会绕过登录、验证码、付费墙或网站访问限制。Amazon 页面抓取不在范围内。",
        "product_page_urls": "产品页面 URL，每行一个",
        "fetch_product_pages": "抓取产品页面",
        "connector_results": "连接器结果",
        "products": "产品数据",
        "raw_specifications": "原始规格",
        "normalized_specifications": "标准化规格",
        "specification_matrix": "规格矩阵",
        "coverage_summary": "覆盖率汇总",
        "gap_analysis": "缺口分析",
        "requirement_draft": "需求草案",
        "supplier_follow_up": "供应商追问",
        "decision_summary": "决策摘要",
        "product_readiness_summary": "就绪度评分",
        "supplier_comparison": "供应商对比",
        "product_pool_summary": "产品池",
        "fetch_logs": "抓取日志",
        "issues": "问题记录",
        "successful_fetches": "成功抓取",
        "raw_specs": "原始规格数",
        "template_center_intro": "下载用于产品调研、供应商评估和硬件规格收集的标准化模板。",
        "download_market_research_template": "下载市场调研模板",
        "download_supplier_quote_template": "下载供应商报价模板",
        "download_product_url_template": "下载产品 URL 导入模板",
        "download_security_camera_template": "下载安防摄像头规格模板",
        "download_vehicle_camera_template": "下载车载影像规格模板",
        "market_analysis": "市场与利润分析",
        "highest_opportunity_products": "最高机会产品",
        "brand_revenue": "品牌销售额",
        "price_bands": "价格带",
        "estimated_monthly_revenue": "预估月销售额",
        "estimated_monthly_net_profit": "预估月净利润",
        "weighted_net_margin": "加权净利率",
        "average_unit_net_profit": "平均单件净利润",
        "break_even_price": "盈亏平衡售价",
        "top_brand_share": "头部品牌占比",
        "average_price": "平均价格",
        "median_reviews": "评论数中位数",
        "category_filter": "类目",
        "brand_filter": "品牌",
        "export_language": "导出语言",
        "not_mapped": "— 未映射 —",
        "missing_required_fields": "以下必需字段尚未映射：{fields}",
        "duplicate_source_columns": "同一个源字段只能映射一次：{columns}",
        "url_empty": "URL 不能为空。",
        "unsupported_url_scheme": "不支持的 URL 协议“{scheme}”。仅支持 http 和 https。",
        "localhost_not_supported": "当前连接器不支持 localhost 链接。",
        "duplicate_url_skipped": "重复 URL 已跳过。",
        "fetch_timeout": "请求在 {seconds:g} 秒后超时。",
        "fetch_not_html": "该 URL 已访问成功，但返回的不是 HTML 文档（content-type：{content_type}）。",
        "fetch_http_error": "该 URL 返回 HTTP {status_code}。",
        "no_product_data": "未检测到产品标题或规格数据。",
        "missing_asin": "ASIN 不能为空，该行将被排除。",
        "duplicate_asin": "ASIN 重复，仅保留第一条记录。",
        "invalid_numeric": "{field} 无法转换为数字。",
        "negative_value_normalized": "{field} 为负数，将被归零。",
        "rating_out_of_range": "评分将被限制在 0–5 范围内。",
        "blank_value_normalized": "{field} 为空，将替换为“{replacement}”。",
    },
}


SHEET_LABELS: dict[str, dict[str, str]] = {
    "en": {
        "products": "Products",
        "issues": "Issues",
        "import_report": "Import Report",
        "raw_specifications": "Raw Specifications",
        "normalized_specifications": "Normalized Specifications",
        "specification_matrix": "Specification Matrix",
        "coverage_summary": "Coverage Summary",
        "gap_analysis": "Gap Analysis",
        "requirement_draft": "Product Requirement Draft",
        "supplier_follow_up": "Supplier Follow-up Questions",
        "decision_summary": "Decision Summary",
        "product_readiness_summary": "Product Readiness Summary",
        "supplier_comparison": "Supplier Comparison",
        "product_pool_summary": "Product Pool Summary",
        "fetch_logs": "Fetch Logs",
        "data_dictionary": "Data Dictionary",
        "example": "Example",
        "supplier_quotes": "Supplier Quotes",
        "product_urls": "Product URLs",
        "security_camera_specs": "Security Camera Specs",
        "vehicle_camera_specs": "Vehicle Camera Specs",
    },
    "zh-CN": {
        "products": "产品数据",
        "issues": "问题记录",
        "import_report": "导入报告",
        "raw_specifications": "原始规格",
        "normalized_specifications": "标准化规格",
        "specification_matrix": "规格矩阵",
        "coverage_summary": "覆盖率汇总",
        "gap_analysis": "缺口分析",
        "requirement_draft": "产品需求草案",
        "supplier_follow_up": "供应商追问清单",
        "decision_summary": "决策摘要",
        "product_readiness_summary": "产品就绪度汇总",
        "supplier_comparison": "供应商对比",
        "product_pool_summary": "产品池汇总",
        "fetch_logs": "抓取日志",
        "data_dictionary": "数据字典",
        "example": "示例",
        "supplier_quotes": "供应商报价",
        "product_urls": "产品页面链接",
        "security_camera_specs": "安防摄像头规格",
        "vehicle_camera_specs": "车载影像规格",
    },
}


COLUMN_LABELS: dict[str, dict[str, str]] = {
    "en": {},
    "zh-CN": {
        "source_url": "来源链接",
        "domain": "域名",
        "status": "状态",
        "status_code": "状态码",
        "title": "标题",
        "brand": "品牌",
        "model": "型号",
        "price": "价格",
        "image_url": "图片链接",
        "document_urls": "文档链接",
        "parser_names": "解析器",
        "fetched_at": "采集时间",
        "error_message": "错误信息",
        "spec_name": "规格名称",
        "spec_value": "规格值",
        "parser": "解析来源",
        "standard_field": "标准字段",
        "standard_label": "标准标签",
        "raw_spec_name": "原始规格名称",
        "raw_spec_value": "原始规格值",
        "normalized_value": "标准化值",
        "confidence": "置信度",
        "category": "类别",
        "severity": "严重程度",
        "error_code": "错误代码",
        "message": "说明",
        "row_number": "行号",
        "field": "字段",
        "raw_value": "原始值",
        "asin": "ASIN",
        "reviews": "评论数",
        "monthly_sales": "月销量",
        "estimated_monthly_revenue": "预估月销售额",
        "opportunity_score": "机会分数",
        "estimated_unit_gross_profit": "单件毛利润",
        "estimated_unit_net_profit": "单件净利润",
        "estimated_net_margin": "净利率",
        "break_even_price": "盈亏平衡售价",
        "estimated_monthly_net_profit": "预估月净利润",
        "products_with_value": "有值产品数",
        "total_products": "产品总数",
        "coverage_rate": "覆盖率",
        "profile": "规格配置模板",
        "profile_label": "配置模板名称",
        "missing_fields": "缺失字段",
        "missing_labels": "缺失字段名称",
        "missing_count": "缺失数量",
        "required_fields_count": "必需字段数",
        "completion_rate": "完整率",
        "risk_level": "风险等级",
        "requirement_field": "需求字段",
        "requirement_label": "需求名称",
        "current_value": "当前值",
        "evidence_source": "证据来源",
        "action": "动作",
        "notes": "备注",
        "missing_field": "缺失字段",
        "missing_label": "缺失字段名称",
        "question": "追问问题",
        "priority": "优先级",
        "owner": "负责人",
        "recommendation": "建议",
        "next_action": "下一步动作",
        "decision_owner": "决策负责人",
        "decision_status": "决策状态",
        "readiness_score": "就绪度评分",
        "readiness_status": "就绪状态",
        "product_pool_status": "产品池状态",
        "priority": "优先级",
        "metadata_completeness": "基础信息完整度",
        "follow_up_question_count": "追问问题数量",
        "requirement_candidate_count": "需求候选项数量",
        "supplier_key": "供应商键",
        "supplier_name": "供应商名称",
        "product_count": "产品数量",
        "average_readiness_score": "平均就绪度评分",
        "max_readiness_score": "最高就绪度评分",
        "average_completion_rate": "平均完整率",
        "ready_product_count": "可评审产品数",
        "follow_up_required_count": "需追问产品数",
        "high_risk_product_count": "高风险产品数",
        "not_ready_product_count": "暂缓产品数",
        "total_missing_fields": "缺失字段总数",
        "total_follow_up_questions": "追问问题总数",
        "best_product_title": "最佳候选产品",
        "best_product_url": "最佳候选链接",
        "overall_status": "综合状态",
        "supplier_average_readiness_score": "供应商平均就绪度评分",
        "supplier_overall_status": "供应商综合状态",
        "power_input": "供电输入",
        "operating_temperature": "工作温度",
        "storage_temperature": "存储温度",
        "waterproof_rating": "防水等级",
        "dimensions": "尺寸",
        "resolution": "分辨率",
        "camera_resolution": "摄像头分辨率",
        "monitor_size": "显示器尺寸",
        "monitor_resolution": "显示器分辨率",
        "battery_capacity_mah": "电池容量",
        "wireless_protocol": "无线协议",
        "transmission_range_m": "传输距离",
        "latency_ms": "延迟",
        "night_vision_type": "夜视类型",
        "ir_distance_m": "红外距离",
        "supports_rtsp": "支持RTSP",
        "supports_onvif": "支持ONVIF",
        "field_of_view": "视场角",
        "anti_vibration": "抗震",
        "power_consumption": "功耗",
    },
}


def normalize_language(language: str | None) -> str:
    """Return a supported language code, falling back to English."""

    if not language:
        return DEFAULT_LANGUAGE

    value = str(language).strip()
    aliases = {
        "zh": "zh-CN",
        "zh-cn": "zh-CN",
        "zh_CN": "zh-CN",
        "cn": "zh-CN",
        "chinese": "zh-CN",
        "中文": "zh-CN",
        "简体中文": "zh-CN",
        "en-us": "en",
        "en_US": "en",
        "english": "en",
    }
    normalized = aliases.get(value.lower(), value)
    return normalized if normalized in SUPPORTED_LANGUAGES else DEFAULT_LANGUAGE


def language_display_name(language: str | None) -> str:
    code = normalize_language(language)
    return LANGUAGE_DISPLAY_NAMES[code]


def t(key: str, language: str | None = DEFAULT_LANGUAGE, **kwargs: Any) -> str:
    """Translate a UI text key.

    Missing keys fall back to English; if the key is unknown in all languages,
    the key itself is returned. Keyword arguments are applied through
    ``str.format``.
    """

    code = normalize_language(language)
    template = TEXT.get(code, {}).get(key) or TEXT[DEFAULT_LANGUAGE].get(key) or key

    if kwargs:
        try:
            return template.format(**kwargs)
        except (KeyError, ValueError):
            return template

    return template


def sheet_label(key: str, language: str | None = DEFAULT_LANGUAGE) -> str:
    code = normalize_language(language)
    return SHEET_LABELS.get(code, {}).get(key) or SHEET_LABELS[DEFAULT_LANGUAGE].get(key) or key


def column_label(key: str, language: str | None = DEFAULT_LANGUAGE) -> str:
    code = normalize_language(language)
    return COLUMN_LABELS.get(code, {}).get(key) or COLUMN_LABELS[DEFAULT_LANGUAGE].get(key) or key
