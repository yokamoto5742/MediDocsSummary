from fastapi import APIRouter, Depends

from app.api import evaluation, prompts, settings, statistics, summary
from app.core.security import require_csrf_token

# 公開ルーター(読み取り専用、CSRFトークン不要)
public_router = APIRouter()
public_router.include_router(settings.router)  # GET: departments, doctors, document_types
public_router.include_router(statistics.router)  # GET: summary, aggregated, records
public_router.include_router(prompts.public_router)  # GET: list_prompts, get_prompt
public_router.include_router(evaluation.public_router)  # GET: get_all_evaluation_prompts, get_evaluation_prompt
public_router.include_router(summary.public_router)  # GET: get_available_models

# 保護ルーター(生成・評価・変更操作。CSRFトークン検証でUI経由のリクエストに限定)
protected_router = APIRouter(dependencies=[Depends(require_csrf_token)])
protected_router.include_router(prompts.protected_router)  # POST/DELETE: create_prompt, delete_prompt
protected_router.include_router(evaluation.protected_router)  # POST/DELETE: evaluate-stream, save/delete_evaluation_prompt
protected_router.include_router(summary.protected_router)  # POST: generate-stream

# 統合ルーター
api_router = APIRouter()
api_router.include_router(public_router)
api_router.include_router(protected_router)
