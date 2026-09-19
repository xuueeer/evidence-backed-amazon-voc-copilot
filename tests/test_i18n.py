from src.i18n import (
    column_label,
    language_display_name,
    normalize_language,
    sheet_label,
    t,
)


def test_normalize_language_supports_aliases():
    assert normalize_language("zh") == "zh-CN"
    assert normalize_language("简体中文") == "zh-CN"
    assert normalize_language("english") == "en"


def test_normalize_language_falls_back_to_english():
    assert normalize_language(None) == "en"
    assert normalize_language("de") == "en"


def test_translates_known_keys():
    assert t("data_source", "en") == "Data source"
    assert t("data_source", "zh-CN") == "数据来源"
    assert t("voc_evidence_ledger", "zh-CN") == "VOC 证据账本"


def test_unknown_key_returns_key():
    assert t("not_a_real_key", "zh-CN") == "not_a_real_key"


def test_translation_formatting():
    assert t("fetch_http_error", "en", status_code=404) == "HTTP 404 returned for URL."
    assert t("fetch_http_error", "zh-CN", status_code=404) == "该 URL 返回 HTTP 404。"


def test_formatting_failure_returns_template():
    assert t("fetch_http_error", "en") == "HTTP {status_code} returned for URL."


def test_sheet_labels_are_localized():
    assert sheet_label("products", "en") == "Products"
    assert sheet_label("products", "zh-CN") == "产品数据"
    assert sheet_label("unknown_sheet", "zh-CN") == "unknown_sheet"


def test_column_labels_are_localized():
    assert column_label("source_url", "zh-CN") == "来源链接"
    assert column_label("source_url", "en") == "source_url"


def test_language_display_names():
    assert language_display_name("en") == "English"
    assert language_display_name("zh-CN") == "简体中文"
