from unittest.mock import patch

from fastapi import status

from app.schemas.summary import SummaryRequest


async def _mock_stream():
    yield 'event: progress\ndata: {"status": "generating", "message": "文書を生成中..."}\n\n'
    yield 'event: complete\ndata: {"success": true, "output_summary": "生成された文書", "parsed_summary": {}, "input_tokens": 100, "output_tokens": 200, "processing_time": 1.5, "model_used": "Claude", "model_switched": false}\n\n'


def test_generate_summary_stream_success(client, test_db, csrf_headers):
    """SSEストリーミング文書生成API - 正常系"""
    with patch(
        "app.api.summary.execute_summary_generation_stream",
        return_value=_mock_stream(),
    ):
        response = client.post(
            "/api/summary/generate-stream",
            json={
                "medical_text": "患者は60歳男性",
                "additional_info": "",
                "current_prescription": "",
                "department": "default",
                "doctor": "default",
                "document_type": "他院への紹介",
                "model": "Claude",
                "model_explicitly_selected": True,
            },
            headers=csrf_headers,
        )

    assert response.status_code == status.HTTP_200_OK
    assert response.headers["content-type"] == "text/event-stream; charset=utf-8"
    # プロキシでバッファリングされないようにする
    assert response.headers["x-accel-buffering"] == "no"
    assert "event: complete" in response.text
    assert "生成された文書" in response.text


def test_generate_summary_stream_passes_request_to_service(client, test_db, csrf_headers):
    """リクエストはSummaryRequestのまま、クライアントIPとともにサービス層へ渡す"""
    with patch(
        "app.api.summary.execute_summary_generation_stream",
        return_value=_mock_stream(),
    ) as mock_execute:
        client.post(
            "/api/summary/generate-stream",
            json={
                "medical_text": "患者データ",
                "model": "Gemini",
                "model_explicitly_selected": True,
            },
            headers=csrf_headers,
        )

    request, user_ip = mock_execute.call_args.args
    assert isinstance(request, SummaryRequest)
    assert request.medical_text == "患者データ"
    assert request.model == "Gemini"
    assert request.model_explicitly_selected is True
    # 省略したフィールドにはデフォルト値が入る
    assert request.additional_info == ""
    assert request.department == "default"
    assert request.doctor == "default"
    assert request.document_type == "退院時サマリ"
    assert user_ip == "testclient"


def test_generate_summary_stream_csrf_required(client, test_db):
    """SSEストリーミングAPI - CSRF認証必須"""
    response = client.post(
        "/api/summary/generate-stream",
        json={"medical_text": "患者は60歳男性", "model": "Claude"},
    )

    # CSRF認証がないため401が返る
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
