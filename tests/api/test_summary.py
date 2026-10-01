from unittest.mock import patch

from fastapi import status

from app.core.constants import MESSAGES


def test_generate_endpoint_removed(client, test_db, csrf_headers):
    """非ストリーミングの文書生成APIは廃止済み（generate-stream に一本化）"""
    response = client.post(
        "/api/summary/generate",
        json={"medical_text": "患者は40歳女性。"},
        headers=csrf_headers,
    )

    assert response.status_code == status.HTTP_404_NOT_FOUND


def test_generate_summary_missing_required_field(client, test_db, csrf_headers):
    """文書生成API - 必須フィールド不足"""
    payload = {
        "additional_info": "追加情報",
        # medical_text が欠落
    }

    response = client.post(
        "/api/summary/generate-stream", json=payload, headers=csrf_headers
    )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    # 検証エラーの詳細はクライアントに返さず定型メッセージを返す
    assert response.json()["error_message"] == MESSAGES["ERROR"]["INPUT_ERROR"]


def test_get_available_models_claude_only(client, test_db):
    """利用可能モデル取得 - Claude のみ"""
    with patch("app.services.model_selector.settings") as mock_settings:
        mock_settings.anthropic_model = "claude-3-5-sonnet-20241022"
        mock_settings.gemini_model = None

        response = client.get("/api/summary/models")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["available_models"] == ["Claude"]
        assert data["default_model"] == "Claude"


def test_get_available_models_gemini_only(client, test_db):
    """利用可能モデル取得 - Gemini のみ"""
    with patch("app.services.model_selector.settings") as mock_settings:
        mock_settings.anthropic_model = None
        mock_settings.gemini_model = "gemini-1.5-pro-002"

        response = client.get("/api/summary/models")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["available_models"] == ["Gemini"]
        assert data["default_model"] == "Gemini"


def test_get_available_models_both(client, test_db):
    """利用可能モデル取得 - 両方"""
    with patch("app.services.model_selector.settings") as mock_settings:
        mock_settings.anthropic_model = "claude-3-5-sonnet-20241022"
        mock_settings.gemini_model = "gemini-1.5-pro-002"

        response = client.get("/api/summary/models")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["available_models"] == ["Claude", "Gemini"]
        assert data["default_model"] == "Claude"


def test_get_available_models_none(client, test_db):
    """利用可能モデル取得 - なし"""
    with patch("app.services.model_selector.settings") as mock_settings:
        mock_settings.anthropic_model = None
        mock_settings.gemini_model = None

        response = client.get("/api/summary/models")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["available_models"] == []
        assert data["default_model"] is None
