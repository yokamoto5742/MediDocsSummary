"""統合テスト: 評価フロー（API層→Service層→DB）"""

from unittest.mock import patch

from app.core.constants import MESSAGES
from app.models.evaluation_prompt import EvaluationPrompt
from tests.integration.conftest import (
    make_test_settings,
    mock_ai_client,
    parse_sse_events,
    post_sse,
)

EVALUATE_URL = "/api/evaluation/evaluate-stream"

VALID_OUTPUT_SUMMARY = (
    "現病歴: 2型糖尿病にて加療中。\n"
    "入院経過: 血糖コントロール良好となり退院。\n"
    "退院時状況: 全身状態良好。"
)


def _payload(**overrides) -> dict:
    payload = {
        "document_type": "退院時サマリ",
        "input_text": "患者情報テキスト",
        "current_prescription": "",
        "additional_info": "",
        "output_summary": VALID_OUTPUT_SUMMARY,
    }
    return {**payload, **overrides}


def _add_evaluation_prompt(db_session, content: str = "以下の退院時サマリを評価してください。"):
    db_session.add(
        EvaluationPrompt(document_type="退院時サマリ", content=content, is_active=True)
    )
    db_session.commit()


class TestEvaluation:
    def test_success_emits_progress_and_complete_events(
        self, integration_client, db_session, csrf_headers
    ):
        """正常系: 評価プロンプトあり状態でprogress→completeのSSEイベントが返る"""
        _add_evaluation_prompt(db_session)

        with mock_ai_client("評価結果: 適切な要約です。", 500, 200) as calls:
            response = integration_client.post(
                EVALUATE_URL,
                json=_payload(
                    input_text="患者は67歳男性。糖尿病にて加療中。",
                    current_prescription="メトホルミン500mg",
                ),
                headers=csrf_headers,
            )

        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]

        events = parse_sse_events(response.text)
        assert [e["type"] for e in events] == ["progress", "progress", "complete"]

        data = events[-1]["data"]
        assert data["success"] is True
        assert data["evaluation_result"] == "評価結果: 適切な要約です。"
        assert data["input_tokens"] == 500
        assert data["output_tokens"] == 200

        # EVALUATION_MODEL(Gemini)のモデルで、DBの評価プロンプトと入力一式がAIに渡る
        assert len(calls) == 1
        assert calls[0]["model"] == "Gemini"
        assert calls[0]["model_name"] == "gemini-test-model"
        assert "以下の退院時サマリを評価してください。" in calls[0]["system_prompt"]
        assert "患者は67歳男性。糖尿病にて加療中。" in calls[0]["user_message"]
        assert "メトホルミン500mg" in calls[0]["user_message"]
        assert VALID_OUTPUT_SUMMARY in calls[0]["user_message"]

    def test_claude_evaluation_model(self, integration_client, db_session, csrf_headers):
        """EVALUATION_MODEL=Claude の場合はClaudeのモデルで評価する"""
        _add_evaluation_prompt(db_session)
        claude_settings = make_test_settings().model_copy(
            update={"evaluation_model": "Claude"}
        )

        with (
            patch("app.services.evaluation_service.settings", claude_settings),
            mock_ai_client() as calls,
        ):
            event = post_sse(integration_client, EVALUATE_URL, _payload(), csrf_headers)

        assert event["type"] == "complete"
        assert calls[0]["model"] == "Claude"
        assert calls[0]["model_name"] == "claude-test-model"

    def test_no_evaluation_prompt_emits_error_event(
        self, integration_client, db_session, csrf_headers
    ):
        """評価プロンプトが未設定の場合はerrorイベントを返し、AIを呼ばない"""
        with mock_ai_client() as calls:
            event = post_sse(integration_client, EVALUATE_URL, _payload(), csrf_headers)

        assert event["type"] == "error"
        assert event["data"] == {
            "success": False,
            "error_message": MESSAGES["VALIDATION"]["EVALUATION_PROMPT_NOT_SET"].format(
                document_type="退院時サマリ"
            ),
        }
        assert calls == []

    def test_empty_output_summary_emits_validation_error(
        self, integration_client, db_session, csrf_headers
    ):
        """評価対象の出力が空の場合はバリデーションエラーを返す"""
        _add_evaluation_prompt(db_session)

        event = post_sse(
            integration_client, EVALUATE_URL, _payload(output_summary=""), csrf_headers
        )

        assert event["type"] == "error"
        assert event["data"]["error_message"] == MESSAGES["VALIDATION"]["EVALUATION_NO_OUTPUT"]

    def test_evaluation_model_not_configured_emits_error_event(
        self, integration_client, db_session, csrf_headers
    ):
        """EVALUATION_MODEL が未設定の場合は設定エラーを返す"""
        _add_evaluation_prompt(db_session)
        no_model_settings = make_test_settings().model_copy(
            update={"evaluation_model": None}
        )

        with patch("app.services.evaluation_service.settings", no_model_settings):
            event = post_sse(integration_client, EVALUATE_URL, _payload(), csrf_headers)

        assert event["type"] == "error"
        assert event["data"]["error_message"] == MESSAGES["CONFIG"]["EVALUATION_MODEL_MISSING"]

    def test_evaluation_prompt_crud_then_evaluate(
        self, integration_client, db_session, csrf_headers
    ):
        """評価プロンプトをAPI経由で登録してから評価を実行できる"""
        integration_client.post(
            "/api/evaluation/prompts",
            json={
                "document_type": "現病歴",
                "content": "以下の現病歴を詳細に評価してください。",
            },
            headers=csrf_headers,
        )

        with mock_ai_client("詳細な評価結果です。") as calls:
            event = post_sse(
                integration_client,
                EVALUATE_URL,
                _payload(document_type="現病歴"),
                csrf_headers,
            )

        assert event["type"] == "complete"
        assert event["data"]["evaluation_result"] == "詳細な評価結果です。"
        assert "以下の現病歴を詳細に評価してください。" in calls[0]["system_prompt"]
