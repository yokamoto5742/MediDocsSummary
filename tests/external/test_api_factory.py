from unittest.mock import patch

import pytest

from app.core.constants import ModelType
from app.external.api_factory import create_client
from app.external.claude_api import ClaudeAPIClient
from app.external.gemini_api import GeminiAPIClient
from app.utils.exceptions import APIError


@pytest.fixture(autouse=True)
def _mock_sdk_clients():
    """クライアント生成時に外部SDKへ接続しないよう差し替える"""
    with (
        patch("app.external.claude_api.AnthropicBedrock"),
        patch("app.external.gemini_api.genai.Client"),
        patch("app.external.gemini_api.get_settings") as mock_gemini_settings,
    ):
        mock_gemini_settings.return_value.google_project_id = "test-project"
        mock_gemini_settings.return_value.google_credentials_json = None
        yield


class TestCreateClient:
    """create_client 関数のテスト"""

    @pytest.mark.parametrize("model", [ModelType.CLAUDE, "Claude"])
    def test_create_client_claude(self, model):
        """Claude のモデル種別（Enum・文字列）から ClaudeAPIClient を生成"""
        assert isinstance(create_client(model), ClaudeAPIClient)

    @pytest.mark.parametrize("model", [ModelType.GEMINI_PRO, "Gemini"])
    def test_create_client_gemini(self, model):
        """Gemini のモデル種別（Enum・文字列）から GeminiAPIClient を生成"""
        assert isinstance(create_client(model), GeminiAPIClient)

    @pytest.mark.parametrize("model", ["openai", "claude", "", "12345"])
    def test_create_client_unsupported_model(self, model):
        """未対応のモデル種別はAPIError（ModelTypeの値と完全一致のみ受け付ける）"""
        with pytest.raises(APIError) as exc_info:
            create_client(model)

        assert "サポートされていないモデル" in str(exc_info.value)

    def test_create_client_returns_independent_instances(self):
        """呼び出しごとに新しいインスタンスを返す"""
        assert create_client("Claude") is not create_client("Claude")
