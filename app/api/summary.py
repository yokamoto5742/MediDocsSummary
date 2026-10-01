from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.schemas.summary import SummaryRequest
from app.services import model_selector
from app.services.sse_helpers import sse_response
from app.services.summary_service import execute_summary_generation_stream
from app.utils.audit_logger import get_client_ip

# 公開ルーター(読み取り専用、CSRFトークン不要)
public_router = APIRouter(prefix="/summary", tags=["summary"])

# 保護ルーター(CSRFトークン検証あり)
protected_router = APIRouter(prefix="/summary", tags=["summary"])


@protected_router.post("/generate-stream")
async def generate_summary_stream(
    request: SummaryRequest, user_ip: str | None = Depends(get_client_ip)
) -> StreamingResponse:
    """SSEストリーミング文書生成API"""
    return sse_response(execute_summary_generation_stream(request, user_ip))


@public_router.get("/models")
def get_available_models():
    """利用可能なモデル一覧を取得"""
    models = model_selector.get_available_models()
    return {
        "available_models": models,
        "default_model": models[0] if models else None,
    }
