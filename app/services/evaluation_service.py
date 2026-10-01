import asyncio
import logging
import time
from typing import AsyncGenerator

from app.core.config import get_settings
from app.core.constants import EVALUATION_GROUNDING_INSTRUCTION, MESSAGES, get_message
from app.core.database import get_db_session
from app.external.api_factory import create_client
from app.schemas.evaluation import EvaluationRequest
from app.services.evaluation_prompt_service import get_evaluation_prompt
from app.services.model_selector import resolve_model_name
from app.services.sse_helpers import heartbeat_until_done, sse_error_event, sse_event
from app.services.usage_service import check_daily_limit
from app.utils.audit_logger import log_audit_event
from app.utils.input_sanitizer import sanitize_medical_text, validate_medical_input

logger = logging.getLogger(__name__)
settings = get_settings()

# サニタイズ対象の自由入力フィールド
_FREE_TEXT_FIELDS = (
    "input_text",
    "current_prescription",
    "additional_info",
    "output_summary",
)


def _sanitize_request(request: EvaluationRequest) -> EvaluationRequest:
    """自由入力フィールドをサニタイズしたコピーを返す"""
    return request.model_copy(
        update={
            field: sanitize_medical_text(getattr(request, field))
            for field in _FREE_TEXT_FIELDS
        }
    )


def _validate_request(request: EvaluationRequest) -> None:
    """評価対象の有無とプロンプトインジェクションを検証。問題があればValueError"""
    if not request.output_summary:
        raise ValueError(MESSAGES["VALIDATION"]["EVALUATION_NO_OUTPUT"])

    error_msg = validate_medical_input(request.output_summary) or validate_medical_input(
        request.input_text
    )
    if error_msg:
        raise ValueError(error_msg)


def _resolve_evaluation_model() -> tuple[str, str]:
    """EVALUATION_MODELから(モデル種別, モデル名)を解決。設定不備はValueError"""
    model = settings.evaluation_model
    if not model:
        raise ValueError(MESSAGES["CONFIG"]["EVALUATION_MODEL_MISSING"])
    return model, resolve_model_name(model)


def _get_prompt_template(document_type: str) -> str:
    """文書タイプの評価プロンプトを取得。未設定ならValueError"""
    with get_db_session() as db:
        prompt = get_evaluation_prompt(db, document_type)
        # セッションを閉じる前に値を取り出す
        content = prompt.content if prompt else None

    if content is None:
        raise ValueError(
            get_message("VALIDATION", "EVALUATION_PROMPT_NOT_SET", document_type=document_type)
        )
    return content


def build_evaluation_prompt(
    prompt_template: str, request: EvaluationRequest
) -> tuple[str, str]:
    """評価用のsystem promptとuserメッセージを構築"""
    system_prompt = f"{prompt_template}\n{EVALUATION_GROUNDING_INSTRUCTION}"

    user_message = f"""<カルテ記載>
{request.input_text}
</カルテ記載>

<現在の処方>
{request.current_prescription}
</現在の処方>

<追加情報>
{request.additional_info}
</追加情報>

<生成された出力>
{request.output_summary}
</生成された出力>"""

    return system_prompt, user_message


def _failure_event(
    request: EvaluationRequest,
    user_ip: str | None,
    audit_message: str,
    client_message: str,
) -> str:
    """失敗を監査ログに記録し、クライアントへ返すerrorイベントを生成"""
    log_audit_event(
        event_type=MESSAGES["AUDIT"]["EVALUATION_FAILURE"],
        user_ip=user_ip,
        document_type=request.document_type,
        success=False,
        error_message=audit_message,
    )
    return sse_error_event(client_message)


def _run_sync_evaluation(
    request: EvaluationRequest, prompt_template: str, model: str, model_name: str
) -> tuple[str, int, int]:
    """外部APIを同期呼び出しして評価を実行（スレッドプール上で実行する）"""
    system_prompt, user_message = build_evaluation_prompt(prompt_template, request)
    return create_client(model).generate(system_prompt, user_message, model_name)


async def execute_evaluation_stream(
    request: EvaluationRequest,
    user_ip: str | None = None,
) -> AsyncGenerator[str, None]:
    """SSEストリーミングで評価を実行"""
    log_audit_event(
        event_type=MESSAGES["AUDIT"]["EVALUATION_START"],
        user_ip=user_ip,
        document_type=request.document_type,
    )

    limit_error = check_daily_limit()
    if limit_error:
        yield sse_error_event(limit_error)
        return

    request = _sanitize_request(request)

    try:
        _validate_request(request)
        model, model_name = _resolve_evaluation_model()
        prompt_template = _get_prompt_template(request.document_type)
    except ValueError as e:
        yield _failure_event(request, user_ip, str(e), str(e))
        return

    start_time = time.time()
    task = asyncio.create_task(
        asyncio.to_thread(
            _run_sync_evaluation, request, prompt_template, model, model_name
        )
    )
    async for progress_event in heartbeat_until_done(
        task,
        start_message=MESSAGES["STATUS"]["EVALUATION_START"],
        running_status="evaluating",
        running_message=MESSAGES["STATUS"]["EVALUATING"],
        elapsed_message_template=MESSAGES["STATUS"]["EVALUATING_ELAPSED"],
    ):
        yield progress_event

    try:
        evaluation_text, input_tokens, output_tokens = await task
    except Exception as e:
        # 例外詳細はサーバーログのみに記録（外部APIの例外文字列に入力断片が含まれる可能性があるため）
        logger.error("評価API呼び出しエラー", exc_info=True)
        yield _failure_event(
            request, user_ip, type(e).__name__, MESSAGES["ERROR"]["EVALUATION_ERROR"]
        )
        return

    processing_time = time.time() - start_time

    log_audit_event(
        event_type=MESSAGES["AUDIT"]["EVALUATION_SUCCESS"],
        user_ip=user_ip,
        document_type=request.document_type,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        processing_time=processing_time,
    )

    yield sse_event(
        "complete",
        {
            "success": True,
            "evaluation_result": evaluation_text,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "processing_time": processing_time,
        },
    )
