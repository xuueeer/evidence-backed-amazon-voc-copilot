from pathlib import Path
import tomllib


def test_streamlit_upload_limit_matches_project_limit():
    config_path = Path(".streamlit/config.toml")
    config = tomllib.loads(config_path.read_text(encoding="utf-8"))
    assert config["server"]["maxUploadSize"] == 20


def test_streamlit_theme_matches_evidence_workspace_palette():
    config_path = Path(".streamlit/config.toml")
    config = tomllib.loads(config_path.read_text(encoding="utf-8"))

    assert config["theme"] == {
        "primaryColor": "#117A63",
        "backgroundColor": "#F1F6F3",
        "secondaryBackgroundColor": "#FFFFFF",
        "textColor": "#17352D",
        "font": "sans serif",
    }
