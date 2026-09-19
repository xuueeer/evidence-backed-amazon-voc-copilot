from __future__ import annotations

from src.voc_dashboard import _display_rationale, _stretch_kwargs


def test_stretch_kwargs_supports_old_and_new_streamlit_apis() -> None:
    def legacy_component(*, use_container_width: bool = False) -> None:
        pass

    def current_component(*, width: str = "content") -> None:
        pass

    assert _stretch_kwargs(legacy_component) == {"use_container_width": True}
    assert _stretch_kwargs(current_component) == {"width": "stretch"}


def test_deterministic_rationale_is_localized_for_chinese_ui() -> None:
    rationale = (
        "5 of 30 valid reviews support the fit and comfort pain point "
        "across 4 product(s); 3 review(s) contradict it."
    )

    localized = _display_rationale(rationale, "zh-CN")

    assert "30 条有效评论" in localized
    assert "佩戴与舒适度" in localized
    assert "3 条评论提供反向证据" in localized
