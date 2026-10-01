import json
from unittest.mock import MagicMock, patch

import pytest
from google.genai import interactions

from app.core.constants import MESSAGES
from app.external.gemini_api import GeminiAPIClient
from app.schemas.summary import SummaryRequest
from app.utils.exceptions import APIError


def create_mock_settings(**kwargs):
    """テスト用の設定モックを作成"""
    mock = MagicMock()
    mock.google_project_id = kwargs.get("google_project_id", "test-project")
    mock.google_location = kwargs.get("google_location", "global")
    mock.google_credentials_json = kwargs.get("google_credentials_json", None)
    mock.gemini_thinking_level = kwargs.get("gemini_thinking_level", "HIGH")
    return mock


def create_mock_text_event(text):
    """テスト用のテキスト差分イベントモックを作成"""
    mock = MagicMock(spec=interactions.StepDelta)
    mock.delta = MagicMock(spec=interactions.TextDelta)
    mock.delta.text = text
    return mock


def create_mock_completed_event(input_tokens=None, output_tokens=None, has_usage=True):
    """テスト用の完了イベントモックを作成"""
    mock = MagicMock(spec=interactions.InteractionCompletedEvent)
    mock.interaction = MagicMock()
    mock.interaction.usage = (
        MagicMock(total_input_tokens=input_tokens, total_output_tokens=output_tokens)
        if has_usage
        else None
    )
    return mock


def make_client(events=None, **settings_kwargs):
    """genai.Client を差し替えた GeminiAPIClient と interactions.create のモックを返す"""
    with (
        patch("app.external.gemini_api.get_settings") as mock_get_settings,
        patch("app.external.gemini_api.genai.Client") as mock_genai_client,
    ):
        mock_get_settings.return_value = create_mock_settings(**settings_kwargs)
        client = GeminiAPIClient()

    create = mock_genai_client.return_value.interactions.create
    if events is not None:
        create.return_value = iter(events)
    return client, create


class TestGeminiAPIClientInit:
    """GeminiAPIClient 生成時のテスト"""

    @patch("app.external.gemini_api.genai.Client")
    @patch(
        "app.external.gemini_api.service_account.Credentials.from_service_account_info"
    )
    @patch("app.external.gemini_api.get_settings")
    def test_init_with_credentials_json(
        self, mock_get_settings, mock_from_service_account_info, mock_genai_client
    ):
        """GOOGLE_CREDENTIALS_JSON からサービスアカウント認証情報を作ってクライアントを生成"""
        credentials_dict = {
            "type": "service_account",
            "project_id": "test-project-123",
            "private_key": "-----BEGIN PRIVATE KEY-----\ntest\n-----END PRIVATE KEY-----\n",
            "client_email": "test@test-project.iam.gserviceaccount.com",
        }
        mock_get_settings.return_value = create_mock_settings(
            google_project_id="test-project-123",
            google_location="us-central1",
            google_credentials_json=json.dumps(credentials_dict),
        )

        client = GeminiAPIClient()

        assert client.client is mock_genai_client.return_value
        mock_from_service_account_info.assert_called_once_with(
            credentials_dict,
            scopes=["https://www.googleapis.com/auth/cloud-platform"],
        )
        mock_genai_client.assert_called_once_with(
            vertexai=True,
            project="test-project-123",
            location="us-central1",
            credentials=mock_from_service_account_info.return_value,
        )

    @pytest.mark.parametrize("credentials_json", [None, ""])
    @patch("app.external.gemini_api.genai.Client")
    @patch("app.external.gemini_api.get_settings")
    def test_init_without_credentials_json(
        self, mock_get_settings, mock_genai_client, credentials_json
    ):
        """認証情報JSONが未設定なら credentials=None でSDKの既定の認証に任せる"""
        mock_get_settings.return_value = create_mock_settings(
            google_project_id="test-project-456",
            google_location="asia-northeast1",
            google_credentials_json=credentials_json,
        )

        GeminiAPIClient()

        mock_genai_client.assert_called_once_with(
            vertexai=True,
            project="test-project-456",
            location="asia-northeast1",
            credentials=None,
        )

    @pytest.mark.parametrize("project_id", [None, ""])
    @patch("app.external.gemini_api.get_settings")
    def test_init_missing_project_id(self, mock_get_settings, project_id):
        """GOOGLE_PROJECT_ID が未設定ならAPIError"""
        mock_get_settings.return_value = create_mock_settings(google_project_id=project_id)

        with pytest.raises(APIError, match="GOOGLE_PROJECT_ID"):
            GeminiAPIClient()

    @patch("app.external.gemini_api.get_settings")
    def test_init_invalid_json_format(self, mock_get_settings):
        """認証情報JSONが不正な形式ならAPIError"""
        mock_get_settings.return_value = create_mock_settings(
            google_credentials_json="{ invalid json }"
        )

        with pytest.raises(APIError, match="認証情報JSONのパースに失敗しました"):
            GeminiAPIClient()

    @patch(
        "app.external.gemini_api.service_account.Credentials.from_service_account_info"
    )
    @patch("app.external.gemini_api.get_settings")
    def test_init_missing_credential_fields(
        self, mock_get_settings, mock_from_service_account_info
    ):
        """認証情報に必須フィールドがなければAPIError"""
        mock_get_settings.return_value = create_mock_settings(
            google_credentials_json=json.dumps({"type": "service_account"})
        )
        mock_from_service_account_info.side_effect = KeyError("private_key")

        with pytest.raises(APIError, match="認証情報に必要なフィールドがありません"):
            GeminiAPIClient()

    @patch(
        "app.external.gemini_api.service_account.Credentials.from_service_account_info"
    )
    @patch("app.external.gemini_api.get_settings")
    def test_init_credentials_creation_error(
        self, mock_get_settings, mock_from_service_account_info
    ):
        """認証情報の生成に失敗したらAPIError"""
        mock_get_settings.return_value = create_mock_settings(
            google_credentials_json=json.dumps({"type": "service_account"})
        )
        mock_from_service_account_info.side_effect = ValueError("不正な鍵")

        with pytest.raises(APIError, match="認証情報の処理中にエラーが発生しました"):
            GeminiAPIClient()

    @patch("app.external.gemini_api.genai.Client")
    @patch("app.external.gemini_api.get_settings")
    def test_init_genai_client_error_propagates(self, mock_get_settings, mock_genai_client):
        """genai.Client の生成失敗はそのまま送出する（呼び出し側が一括で処理する）"""
        mock_get_settings.return_value = create_mock_settings()
        mock_genai_client.side_effect = Exception("Vertex AI接続エラー")

        with pytest.raises(Exception, match="Vertex AI接続エラー"):
            GeminiAPIClient()


class TestGeminiAPIClientGenerateContent:
    """GeminiAPIClient _generate_content メソッドのテスト"""

    def test_joins_stream_chunks_and_returns_token_counts(self):
        """ストリームのテキスト差分を結合し、完了イベントのトークン数を返す"""
        client, _ = make_client(
            [
                create_mock_text_event("最初の"),
                create_mock_text_event("チャンク"),
                create_mock_completed_event(300, 120),
            ]
        )

        result = client._generate_content(prompt="テスト", model_name="test-model")

        assert result == ("最初のチャンク", 300, 120)

    def test_request_parameters(self):
        """モデル名・入力・ストリーミング・非保存を指定して呼び出す"""
        client, create = make_client([create_mock_text_event("テキスト")])

        client._generate_content(prompt="テストプロンプト", model_name="gemini-test")

        call_kwargs = create.call_args[1]
        assert call_kwargs["model"] == "gemini-test"
        assert call_kwargs["input"] == "テストプロンプト"
        assert call_kwargs["stream"] is True
        # 患者情報を含むためサーバー側に保存しない
        assert call_kwargs["store"] is False
        assert "system_instruction" not in call_kwargs

    @pytest.mark.parametrize(
        ("setting", "expected"), [("LOW", "low"), ("HIGH", "high"), ("OTHER", "high")]
    )
    def test_thinking_level(self, setting, expected):
        """GEMINI_THINKING_LEVEL が LOW のときだけ low、それ以外は high"""
        client, create = make_client(
            [create_mock_text_event("テキスト")], gemini_thinking_level=setting
        )

        client._generate_content(prompt="テスト", model_name="test-model")

        assert create.call_args[1]["generation_config"] == {"thinking_level": expected}

    def test_with_system_prompt(self):
        """system promptが指定された場合は system_instruction に渡す"""
        client, create = make_client([create_mock_text_event("テキスト")])

        client._generate_content(
            prompt="テスト", model_name="test-model", system_prompt="システム指示"
        )

        assert create.call_args[1]["system_instruction"] == "システム指示"

    def test_ignores_non_text_events(self):
        """テキスト差分以外のイベントは無視する"""
        thought_event = MagicMock(spec=interactions.StepDelta)
        thought_event.delta = MagicMock()  # TextDeltaではない差分
        client, _ = make_client(
            [thought_event, MagicMock(), create_mock_text_event("本文")]
        )

        text, _, _ = client._generate_content(prompt="テスト", model_name="test-model")

        assert text == "本文"

    def test_no_usage_returns_zero_tokens(self):
        """usage がない・トークン数が None の場合は 0 を返す"""
        for completed_event in (
            create_mock_completed_event(has_usage=False),
            create_mock_completed_event(None, None),
        ):
            client, _ = make_client([create_mock_text_event("テキスト"), completed_event])

            result = client._generate_content(prompt="テスト", model_name="test-model")

            assert result == ("テキスト", 0, 0)

    def test_empty_response_raises_api_error(self):
        """テキストを含まないレスポンスは生成結果として扱わずAPIErrorにする"""
        client, _ = make_client([create_mock_completed_event(300, 0)])

        with pytest.raises(APIError, match=MESSAGES["ERROR"]["EMPTY_RESPONSE"]):
            client._generate_content(prompt="テスト", model_name="test-model")


class TestGeminiAPIClientGenerate:
    """GeminiAPIClient の公開メソッド経由のテスト"""

    @pytest.mark.parametrize(
        "error",
        [
            TimeoutError("接続タイムアウト"),
            ConnectionResetError("接続がリセットされました"),
            Exception("503 Service Unavailable"),
        ],
    )
    def test_sdk_error_is_wrapped_as_api_error(self, error):
        """SDKの例外は generate でAPIErrorに変換される"""
        client, create = make_client()
        create.side_effect = error

        with pytest.raises(APIError) as exc_info:
            client.generate("システム指示", "プロンプト", "test-model")

        assert "GeminiAPIClientでエラーが発生しました" in str(exc_info.value)
        assert str(error) in str(exc_info.value)

    def test_error_mid_stream_is_wrapped_as_api_error(self):
        """ストリーム途中の切断もAPIErrorに変換される"""

        def error_generator():
            yield create_mock_text_event("最初のチャンク")
            raise ConnectionError("ストリーム途中で切断")

        client, create = make_client()
        create.return_value = error_generator()

        with pytest.raises(APIError, match="ストリーム途中で切断"):
            client.generate("システム指示", "プロンプト", "test-model")

    def test_full_generate_summary_flow(self):
        """generate_summary - プロンプト生成からAPI呼び出しまで"""
        client, create = make_client(
            [create_mock_text_event("生成された文書"), create_mock_completed_event(2500, 1200)]
        )

        with (
            patch("app.external.base_api.get_db_session") as mock_db_session,
            patch("app.external.base_api.get_prompt", return_value=None),
        ):
            mock_db_session.return_value.__enter__.return_value = MagicMock()
            result = client.generate_summary(
                SummaryRequest(medical_text="テストカルテ", additional_info="追加情報"),
                "gemini-1.5-pro-002",
            )

        assert result == ("生成された文書", 2500, 1200)
        call_kwargs = create.call_args[1]
        assert call_kwargs["model"] == "gemini-1.5-pro-002"
        assert "テストカルテ" in call_kwargs["input"]
        assert call_kwargs["system_instruction"]
