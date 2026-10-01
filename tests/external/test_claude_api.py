"""ClaudeAPIClient のテスト"""

from unittest.mock import MagicMock, patch

import pytest
from anthropic import omit  # type: ignore[attr-defined]
from anthropic.types import TextBlock

from app.core.constants import CLAUDE_GENERATION_TEMPERATURE, MESSAGES
from app.external.claude_api import ClaudeAPIClient
from app.schemas.summary import SummaryRequest
from app.utils.exceptions import APIError


def create_mock_response(text_blocks, input_tokens=100, output_tokens=50, stop_reason="end_turn"):
    """テスト用のAPIレスポンスモックを作成"""
    mock_response = MagicMock()
    mock_response.content = text_blocks
    mock_response.stop_reason = stop_reason
    mock_response.usage.input_tokens = input_tokens
    mock_response.usage.output_tokens = output_tokens
    return mock_response


def text_block(text: str) -> TextBlock:
    return TextBlock(type="text", text=text)


@pytest.fixture
def mock_bedrock():
    """AnthropicBedrock を差し替え、コンストラクタのモックを返す"""
    with (
        patch("app.external.claude_api.get_settings") as mock_get_settings,
        patch("app.external.claude_api.AnthropicBedrock") as mock_bedrock_class,
    ):
        mock_get_settings.return_value.aws_region = "ap-northeast-1"
        yield mock_bedrock_class


@pytest.fixture
def messages_create(mock_bedrock):
    """messages.create のモック（既定では正常なレスポンスを返す）"""
    create = mock_bedrock.return_value.messages.create
    create.return_value = create_mock_response([text_block("生成された要約")])
    return create


class TestClaudeAPIClientInit:
    """ClaudeAPIClient 生成時のテスト"""

    def test_init_creates_bedrock_client_with_region(self, mock_bedrock):
        """生成時に設定のリージョンでBedrockクライアントを作る"""
        client = ClaudeAPIClient()

        mock_bedrock.assert_called_once_with(aws_region="ap-northeast-1")
        assert client.client is mock_bedrock.return_value

    def test_init_error_propagates(self, mock_bedrock):
        """Bedrockクライアントの生成失敗はそのまま送出する（呼び出し側が一括で処理する）"""
        mock_bedrock.side_effect = Exception("Bedrock接続エラー")

        with pytest.raises(Exception, match="Bedrock接続エラー"):
            ClaudeAPIClient()


class TestClaudeAPIClientGenerateContent:
    """ClaudeAPIClient _generate_content メソッドのテスト"""

    def test_success(self, messages_create):
        """正常系 - テキストとトークン数を返す"""
        messages_create.return_value = create_mock_response(
            [text_block("生成された要約")], input_tokens=1000, output_tokens=500
        )

        result = ClaudeAPIClient()._generate_content(
            prompt="テストプロンプト", model_name="claude-3-5-sonnet-20241022"
        )

        assert result == ("生成された要約", 1000, 500)

    def test_request_parameters(self, messages_create):
        """モデル名・max_tokens・temperature・メッセージ形式を指定して呼び出す"""
        ClaudeAPIClient()._generate_content(
            prompt="テストプロンプト", model_name="custom-model-name"
        )

        call_kwargs = messages_create.call_args[1]
        assert call_kwargs["model"] == "custom-model-name"
        assert call_kwargs["max_tokens"] == 6000
        assert call_kwargs["extra_body"] == {"temperature": CLAUDE_GENERATION_TEMPERATURE}
        assert call_kwargs["messages"] == [{"role": "user", "content": "テストプロンプト"}]

    def test_with_system_prompt(self, messages_create):
        """system promptが指定された場合はsystemパラメータに渡す"""
        ClaudeAPIClient()._generate_content(
            prompt="プロンプト", model_name="model", system_prompt="システム指示"
        )

        assert messages_create.call_args[1]["system"] == "システム指示"

    def test_without_system_prompt(self, messages_create):
        """system promptが空の場合はsystemパラメータを省略する"""
        ClaudeAPIClient()._generate_content(prompt="プロンプト", model_name="model")

        assert messages_create.call_args[1]["system"] is omit

    def test_uses_first_text_block(self, messages_create):
        """テキスト以外のブロックを飛ばし、最初のテキストブロックを使う"""
        messages_create.return_value = create_mock_response(
            [MagicMock(spec=[]), text_block("最初のテキスト"), text_block("2番目")]
        )

        text, _, _ = ClaudeAPIClient()._generate_content(prompt="プロンプト", model_name="model")

        assert text == "最初のテキスト"

    @pytest.mark.parametrize("content", [[], [MagicMock(spec=[])]])
    def test_empty_response_raises_api_error(self, messages_create, content):
        """テキストブロックがないレスポンスは生成結果として扱わずAPIErrorにする"""
        messages_create.return_value = create_mock_response(content)

        with pytest.raises(APIError, match=MESSAGES["ERROR"]["EMPTY_RESPONSE"]):
            ClaudeAPIClient()._generate_content(prompt="プロンプト", model_name="model")

    def test_truncated_output_warning(self, messages_create):
        """max_tokens到達で打ち切られた場合は警告を付加する"""
        messages_create.return_value = create_mock_response(
            [text_block("途中まで")], stop_reason="max_tokens"
        )

        text, _, _ = ClaudeAPIClient()._generate_content(prompt="プロンプト", model_name="model")

        assert text.startswith("途中まで")
        assert MESSAGES["WARNING"]["OUTPUT_TRUNCATED"] in text

    def test_normal_stop_no_warning(self, messages_create):
        """通常終了では警告を付加しない"""
        text, _, _ = ClaudeAPIClient()._generate_content(prompt="プロンプト", model_name="model")

        assert MESSAGES["WARNING"]["OUTPUT_TRUNCATED"] not in text

    def test_special_characters_in_prompt(self, messages_create):
        """特殊文字を含むプロンプトをそのまま送る"""
        special_prompt = "患者: <test>, \"引用\", '単一引用符', \n改行, \tタブ"

        ClaudeAPIClient()._generate_content(prompt=special_prompt, model_name="model")

        assert messages_create.call_args[1]["messages"][0]["content"] == special_prompt


class TestClaudeAPIClientGenerate:
    """ClaudeAPIClient の公開メソッド経由のテスト"""

    @pytest.mark.parametrize(
        "error",
        [
            TimeoutError("接続タイムアウト"),
            ConnectionResetError("接続がリセットされました"),
            Exception("429 Too Many Requests"),
        ],
    )
    def test_sdk_error_is_wrapped_as_api_error(self, messages_create, error):
        """SDKの例外は generate でAPIErrorに変換される"""
        messages_create.side_effect = error

        with pytest.raises(APIError) as exc_info:
            ClaudeAPIClient().generate("システム指示", "プロンプト", "model")

        assert "ClaudeAPIClientでエラーが発生しました" in str(exc_info.value)
        assert str(error) in str(exc_info.value)

    def test_full_generate_summary_flow(self, messages_create):
        """generate_summary - プロンプト生成からAPI呼び出しまで"""
        messages_create.return_value = create_mock_response(
            [text_block("生成された文書")], input_tokens=2000, output_tokens=1000
        )

        with (
            patch("app.external.base_api.get_db_session") as mock_db_session,
            patch("app.external.base_api.get_prompt", return_value=None),
        ):
            mock_db_session.return_value.__enter__.return_value = MagicMock()
            result = ClaudeAPIClient().generate_summary(
                SummaryRequest(medical_text="テストカルテ", additional_info="追加情報"),
                "claude-3-5-sonnet-20241022",
            )

        assert result == ("生成された文書", 2000, 1000)
        call_kwargs = messages_create.call_args[1]
        assert call_kwargs["model"] == "claude-3-5-sonnet-20241022"
        assert "テストカルテ" in call_kwargs["messages"][0]["content"]
