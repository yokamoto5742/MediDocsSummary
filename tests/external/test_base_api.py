from unittest.mock import MagicMock, patch

import pytest

from app.core.constants import (
    DEFAULT_DOCUMENT_TYPE,
    GROUNDING_INSTRUCTION,
    KARTE_JSON_INSTRUCTION,
    REFINEMENT_INSTRUCTION,
)
from app.external.base_api import BaseAPIClient, _is_json_text
from app.schemas.summary import SummaryRequest
from app.utils.exceptions import APIError


class MockAPIClient(BaseAPIClient):
    """テスト用のモックAPIクライアント（_generate_content の呼び出しを記録する）"""

    def __init__(self, error: Exception | None = None):
        self.error = error
        self.calls: list[tuple[str, str, str]] = []

    def _generate_content(
        self, prompt: str, model_name: str, system_prompt: str = ""
    ) -> tuple[str, int, int]:
        self.calls.append((prompt, model_name, system_prompt))
        if self.error:
            raise self.error
        return "生成されたテキスト", 1000, 500


@pytest.fixture
def mock_get_prompt():
    """DBアクセスを差し替え、get_prompt のモックを返す（既定ではプロンプト未登録）"""
    with (
        patch("app.external.base_api.get_db_session") as mock_db_session,
        patch("app.external.base_api.get_prompt", return_value=None) as mock,
    ):
        mock_db_session.return_value.__enter__.return_value = MagicMock()
        yield mock


class TestIsJsonText:
    """_is_json_text 関数のテスト"""

    def test_json_object(self):
        """JSON判定 - オブジェクト"""
        assert _is_json_text('{"記載日": "2026-07-01", "所見": "良好"}') is True

    def test_json_array(self):
        """JSON判定 - 配列"""
        assert _is_json_text('[{"記載日": "2026-07-01"}]') is True

    def test_plain_text(self):
        """JSON判定 - 通常のテキスト"""
        assert _is_json_text("患者は60歳男性。高血圧で入院。") is False

    def test_json_scalar_is_not_karte(self):
        """JSON判定 - スカラー値はカルテJSONとみなさない"""
        assert _is_json_text("123") is False
        assert _is_json_text("null") is False


class TestCreateSummaryPrompt:
    """create_summary_prompt メソッドのテスト"""

    def test_minimal(self, mock_get_prompt):
        """プロンプト生成 - カルテ情報のみ"""
        system_prompt, user_message = MockAPIClient().create_summary_prompt(
            SummaryRequest(medical_text="患者情報")
        )

        # プロンプト未登録ならDEFAULT_SUMMARY_PROMPTを使用
        assert "以下のカルテ情報を要約してください" in system_prompt
        assert GROUNDING_INSTRUCTION in system_prompt
        assert "<カルテ情報>" in user_message
        assert "患者情報" in user_message
        # 空のオプションフィールドはuserメッセージに含まれない
        assert "<現在の処方>" not in user_message
        assert "<追加情報>" not in user_message

    def test_all_fields(self, mock_get_prompt):
        """プロンプト生成 - 全フィールド指定"""
        system_prompt, user_message = MockAPIClient().create_summary_prompt(
            SummaryRequest(
                medical_text="カルテデータ",
                additional_info="追加データ",
                current_prescription="処方内容",
                department="眼科",
                document_type="他院への紹介",
                doctor="橋本義弘",
            )
        )

        assert "<カルテ情報>" in user_message
        assert "カルテデータ" in user_message
        assert "<現在の処方>" in user_message
        assert "処方内容" in user_message
        assert "<追加情報>" in user_message
        assert "追加データ" in user_message
        # データはsystem promptに含まれない
        assert "カルテデータ" not in system_prompt

    def test_whitespace_optional_fields(self, mock_get_prompt):
        """プロンプト生成 - 空白のみのオプションフィールドは追加しない"""
        _, user_message = MockAPIClient().create_summary_prompt(
            SummaryRequest(
                medical_text="データ", additional_info="   ", current_prescription="\t"
            )
        )

        assert "<現在の処方>" not in user_message
        assert "<追加情報>" not in user_message

    def test_custom_prompt(self, mock_get_prompt):
        """プロンプト生成 - DBのカスタムプロンプトを使用"""
        mock_get_prompt.return_value = MagicMock(content="カスタムプロンプトテンプレート")

        system_prompt, user_message = MockAPIClient().create_summary_prompt(
            SummaryRequest(
                medical_text="データ",
                department="眼科",
                document_type="他院への紹介",
                doctor="橋本義弘",
            )
        )

        assert "カスタムプロンプトテンプレート" in system_prompt
        assert "データ" in user_message
        # 第1引数はdbセッション、第2-4引数はdepartment, document_type, doctor
        assert mock_get_prompt.call_args[0][1:] == ("眼科", "他院への紹介", "橋本義弘")

    def test_default_lookup_keys(self, mock_get_prompt):
        """プロンプト生成 - 未指定時は default とデフォルト文書タイプで検索"""
        MockAPIClient().create_summary_prompt(SummaryRequest(medical_text="データ"))

        assert mock_get_prompt.call_args[0][1:] == (
            "default",
            DEFAULT_DOCUMENT_TYPE,
            "default",
        )

    def test_db_error_falls_back_to_default_prompt(self):
        """プロンプト生成 - DB取得に失敗してもデフォルトプロンプトで続行"""
        with patch(
            "app.external.base_api.get_db_session", side_effect=Exception("DB error")
        ):
            system_prompt, _ = MockAPIClient().create_summary_prompt(
                SummaryRequest(medical_text="データ")
            )

        assert "以下のカルテ情報を要約してください" in system_prompt

    def test_json_karte(self, mock_get_prompt):
        """プロンプト生成 - JSON形式カルテでJSON指示が付加される"""
        system_prompt, _ = MockAPIClient().create_summary_prompt(
            SummaryRequest(medical_text='{"記載日": "2026-07-01", "所見": "良好"}')
        )

        assert KARTE_JSON_INSTRUCTION in system_prompt

    def test_non_json_karte(self, mock_get_prompt):
        """プロンプト生成 - 通常テキストではJSON指示が付加されない"""
        system_prompt, _ = MockAPIClient().create_summary_prompt(
            SummaryRequest(medical_text="通常のカルテ記載")
        )

        assert KARTE_JSON_INSTRUCTION not in system_prompt

    def test_refinement(self, mock_get_prompt):
        """プロンプト生成 - 前回結果と評価結果の両方指定で再生成モード"""
        system_prompt, user_message = MockAPIClient().create_summary_prompt(
            SummaryRequest(
                medical_text="カルテ",
                previous_summary="前回のサマリ",
                evaluation_feedback="指摘事項",
            )
        )

        assert REFINEMENT_INSTRUCTION in system_prompt
        assert "<前回の生成結果>" in user_message
        assert "前回のサマリ" in user_message
        assert "<評価結果>" in user_message
        assert "指摘事項" in user_message

    def test_refinement_requires_both(self, mock_get_prompt):
        """プロンプト生成 - 片方のみ指定では再生成モードにならない"""
        system_prompt, user_message = MockAPIClient().create_summary_prompt(
            SummaryRequest(medical_text="カルテ", previous_summary="前回のサマリ")
        )

        assert REFINEMENT_INSTRUCTION not in system_prompt
        assert "<前回の生成結果>" not in user_message

    def test_special_characters(self, mock_get_prompt):
        """プロンプト生成 - 特殊文字をそのまま含める"""
        special_text = "患者: <test>, \"引用\", '単一引用符', \n改行, \tタブ"
        _, user_message = MockAPIClient().create_summary_prompt(
            SummaryRequest(medical_text=special_text)
        )

        assert special_text in user_message


class TestGenerate:
    """generate メソッドのテスト"""

    def test_passes_prompts_and_model_to_subclass(self):
        """system prompt・userメッセージ・モデル名をサブクラスの実装に渡す"""
        client = MockAPIClient()

        result = client.generate("システム指示", "ユーザーデータ", "test-model")

        assert result == ("生成されたテキスト", 1000, 500)
        assert client.calls == [("ユーザーデータ", "test-model", "システム指示")]

    def test_sdk_exception_is_wrapped_once(self):
        """SDKの例外はクライアント名付きのAPIErrorに変換し、元の例外を原因として保持する"""
        original = ConnectionError("接続失敗")
        client = MockAPIClient(error=original)

        with pytest.raises(APIError) as exc_info:
            client.generate("システム指示", "ユーザーデータ", "test-model")

        assert "MockAPIClientでエラーが発生しました" in str(exc_info.value)
        assert "接続失敗" in str(exc_info.value)
        assert exc_info.value.__cause__ is original

    def test_api_error_propagates_unchanged(self):
        """サブクラスが送出したAPIErrorは再ラップしない"""
        original = APIError("レスポンスが空です")
        client = MockAPIClient(error=original)

        with pytest.raises(APIError) as exc_info:
            client.generate("システム指示", "ユーザーデータ", "test-model")

        assert exc_info.value is original


class TestGenerateSummary:
    """generate_summary メソッドのテスト"""

    def test_builds_prompt_and_generates(self, mock_get_prompt):
        """リクエストからプロンプトを組み立て、指定モデルで生成する"""
        client = MockAPIClient()

        result = client.generate_summary(
            SummaryRequest(medical_text="テストカルテ", additional_info="追加情報"),
            "custom-model",
        )

        assert result == ("生成されたテキスト", 1000, 500)
        user_message, model_name, system_prompt = client.calls[0]
        assert "テストカルテ" in user_message
        assert "追加情報" in user_message
        assert model_name == "custom-model"
        assert GROUNDING_INSTRUCTION in system_prompt

    def test_generation_failure_raises_api_error(self, mock_get_prompt):
        """生成に失敗した場合はAPIErrorになる"""
        client = MockAPIClient(error=Exception("API呼び出しエラー"))

        with pytest.raises(APIError):
            client.generate_summary(SummaryRequest(medical_text="データ"), "test-model")


class TestBaseAPIClientAbstractMethods:
    """BaseAPIClient の抽象メソッドのテスト"""

    def test_cannot_instantiate_base_class(self):
        """基底クラスは直接インスタンス化できない"""
        with pytest.raises(TypeError):
            BaseAPIClient()  # type: ignore

    def test_subclass_must_implement_generate_content(self):
        """サブクラスは _generate_content を実装する必要がある"""

        class IncompleteClient(BaseAPIClient):
            pass

        with pytest.raises(TypeError):
            IncompleteClient()  # type: ignore
