"""統合テスト: エラーハンドリング（AI API障害・不正な設定）"""

import json
import logging

from app.core.constants import MESSAGES
from app.models.evaluation_prompt import EvaluationPrompt
from app.models.usage import SummaryUsage
from app.utils.exceptions import APIError
from tests.integration.conftest import mock_ai_client, post_sse

_VALID_MEDICAL_TEXT = (
    "患者は70歳女性。慢性心不全、2型糖尿病にて長期加療中。"
    "今回は心不全増悪にて入院し、治療後症状改善し退院となった。"
)

_VALID_OUTPUT_SUMMARY = (
    "現病歴: 慢性心不全、糖尿病にて加療中。\n"
    "入院経過: 心不全増悪後、治療により改善。\n"
    "退院時状況: 症状改善し退院。"
)

_EVALUATION_PAYLOAD = {
    "document_type": "退院時サマリ",
    "input_text": "患者情報テキスト",
    "current_prescription": "",
    "additional_info": "",
    "output_summary": _VALID_OUTPUT_SUMMARY,
}


def _audit_records(caplog) -> list[dict]:
    """監査ロガーに出力されたレコードをdictで取得"""
    return [json.loads(r.getMessage()) for r in caplog.records if r.name == "audit"]


class TestSummaryErrors:
    def test_ai_exception_emits_error_event_and_audit_failure(
        self, integration_client, db_session, csrf_headers, caplog
    ):
        """AI APIが例外を投げるとerrorイベントが返り、失敗が監査ログに記録される"""
        with (
            caplog.at_level(logging.INFO, logger="audit"),
            mock_ai_client(error=Exception("Bedrock接続エラー")),
        ):
            event = post_sse(
                integration_client,
                "/api/summary/generate-stream",
                {
                    "medical_text": _VALID_MEDICAL_TEXT,
                    "model": "Claude",
                    "model_explicitly_selected": True,
                },
                csrf_headers,
            )

        assert event["type"] == "error"
        assert event["data"]["success"] is False
        # 例外詳細はクライアントに返さず定型メッセージを返す
        assert event["data"]["error_message"] == MESSAGES["ERROR"]["API_ERROR"]

        failure = _audit_records(caplog)[-1]
        assert failure["event_type"] == MESSAGES["AUDIT"]["DOCUMENT_GENERATION_FAILURE"]
        assert failure["success"] is False
        # 監査ログには例外の型名だけを残す（外部APIの例外文字列に入力断片が含まれうるため）
        assert failure["error_message"] == "APIError"
        assert "Bedrock接続エラー" not in json.dumps(failure, ensure_ascii=False)

        # 失敗した生成は使用量に計上しない
        db_session.expire_all()
        assert db_session.query(SummaryUsage).count() == 0

    def test_empty_ai_response_emits_error_event(
        self, integration_client, db_session, csrf_headers
    ):
        """AI APIの応答が空の場合は生成結果として扱わずerrorイベントを返す"""
        with mock_ai_client(error=APIError(MESSAGES["ERROR"]["EMPTY_RESPONSE"])):
            event = post_sse(
                integration_client,
                "/api/summary/generate-stream",
                {
                    "medical_text": _VALID_MEDICAL_TEXT,
                    "model": "Claude",
                    "model_explicitly_selected": True,
                },
                csrf_headers,
            )

        assert event["type"] == "error"
        assert event["data"]["error_message"] == MESSAGES["ERROR"]["API_ERROR"]

        db_session.expire_all()
        assert db_session.query(SummaryUsage).count() == 0

    def test_unsupported_model_emits_error_event(
        self, integration_client, db_session, csrf_headers
    ):
        """サポートされていないモデル名はerrorイベントが返り、AIを呼ばない"""
        with mock_ai_client() as calls:
            event = post_sse(
                integration_client,
                "/api/summary/generate-stream",
                {
                    "medical_text": _VALID_MEDICAL_TEXT,
                    "model": "UnsupportedModel",
                    "model_explicitly_selected": True,
                },
                csrf_headers,
            )

        assert event["type"] == "error"
        assert event["data"]["error_message"] == MESSAGES["CONFIG"]["UNSUPPORTED_MODEL"].format(
            model="UnsupportedModel"
        )
        assert calls == []


class TestEvaluationErrors:
    def test_ai_exception_emits_error_event_and_audit_failure(
        self, integration_client, db_session, csrf_headers, caplog
    ):
        """評価でAI APIが例外を投げるとerrorイベントが返り、失敗が監査ログに記録される"""
        db_session.add(
            EvaluationPrompt(
                document_type="退院時サマリ",
                content="評価プロンプト",
                is_active=True,
            )
        )
        db_session.commit()

        with (
            caplog.at_level(logging.INFO, logger="audit"),
            mock_ai_client(error=Exception("Gemini API障害")),
        ):
            event = post_sse(
                integration_client,
                "/api/evaluation/evaluate-stream",
                _EVALUATION_PAYLOAD,
                csrf_headers,
            )

        assert event["type"] == "error"
        assert event["data"]["success"] is False
        assert event["data"]["error_message"] == MESSAGES["ERROR"]["EVALUATION_ERROR"]

        failure = _audit_records(caplog)[-1]
        assert failure["event_type"] == MESSAGES["AUDIT"]["EVALUATION_FAILURE"]
        assert failure["success"] is False
        assert failure["error_message"] == "APIError"
