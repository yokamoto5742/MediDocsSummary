from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.constants import MESSAGES
from app.core.database import get_db
from app.schemas.prompt import PromptCreate, PromptListItem, PromptResponse
from app.services import prompt_service
from app.utils.audit_logger import get_client_ip, log_audit_event

# 公開ルーター(読み取り専用、CSRFトークン不要)
public_router = APIRouter(prefix="/prompts", tags=["prompts"])

# 保護ルーター(CSRFトークン検証あり)
protected_router = APIRouter(prefix="/prompts", tags=["prompts"])


@public_router.get("/", response_model=list[PromptListItem])
def list_prompts(db: Session = Depends(get_db)):
    """プロンプト一覧を取得"""
    prompts = prompt_service.get_all_prompts(db)
    return prompts


@public_router.get("/{prompt_id}", response_model=PromptResponse)
def get_prompt(prompt_id: int, db: Session = Depends(get_db)):
    """単一プロンプトを取得"""
    prompt = prompt_service.get_prompt_by_id(db, prompt_id)
    if not prompt:
        raise HTTPException(status_code=404, detail=MESSAGES["ERROR"]["PROMPT_NOT_FOUND"])
    return prompt


@protected_router.post("/", response_model=PromptResponse)
def create_prompt(
    prompt: PromptCreate,
    db: Session = Depends(get_db),
    user_ip: str | None = Depends(get_client_ip),
):
    """プロンプトを作成または更新"""
    existing = prompt_service.get_prompt(
        db, prompt.department, prompt.document_type, prompt.doctor
    )
    is_update = existing is not None

    result = prompt_service.create_or_update_prompt(
        db,
        department=prompt.department,
        document_type=prompt.document_type,
        doctor=prompt.doctor,
        content=prompt.content,
        selected_model=prompt.selected_model,
    )
    db.commit()
    db.refresh(result)

    log_audit_event(
        event_type=(
            MESSAGES["AUDIT"]["PROMPT_UPDATED"]
            if is_update
            else MESSAGES["AUDIT"]["PROMPT_CREATED"]
        ),
        user_ip=user_ip,
        document_type=prompt.document_type,
        department=prompt.department,
        doctor=prompt.doctor,
        prompt_id=result.id,
    )

    return result


@protected_router.delete("/{prompt_id}")
def delete_prompt(
    prompt_id: int,
    db: Session = Depends(get_db),
    user_ip: str | None = Depends(get_client_ip),
):
    """プロンプトを削除"""
    if not prompt_service.delete_prompt(db, prompt_id):
        raise HTTPException(status_code=404, detail=MESSAGES["ERROR"]["PROMPT_NOT_FOUND"])
    db.commit()

    log_audit_event(
        event_type=MESSAGES["AUDIT"]["PROMPT_DELETED"],
        user_ip=user_ip,
        prompt_id=prompt_id,
    )

    return {"status": "deleted"}
