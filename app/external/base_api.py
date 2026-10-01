import json
from abc import ABC, abstractmethod

from app.core.constants import (
    DEFAULT_SUMMARY_PROMPT,
    GROUNDING_INSTRUCTION,
    KARTE_JSON_INSTRUCTION,
    REFINEMENT_INSTRUCTION,
    get_message,
)
from app.core.database import get_db_session
from app.schemas.summary import SummaryRequest
from app.services.prompt_service import get_prompt
from app.utils.exceptions import APIError


def _is_json_text(text: str) -> bool:
    """テキストがJSON(オブジェクトまたは配列)としてパース可能か判定"""
    try:
        parsed = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return False
    return isinstance(parsed, (dict, list))


class BaseAPIClient(ABC):
    @abstractmethod
    def _generate_content(
        self, prompt: str, model_name: str, system_prompt: str = ""
    ) -> tuple[str, int, int]:
        """
        プロバイダー固有のAPI呼び出し
        Args:
            prompt: ユーザーメッセージ（カルテ等のデータ）
            model_name: 使用モデル名
            system_prompt: system prompt（指示テンプレート）
        Returns:
            (生成されたテキスト, 入力トークン数, 出力トークン数)
        Raises:
            APIError: レスポンスが空の場合
        """
        pass

    def generate(
        self, system_prompt: str, user_prompt: str, model_name: str
    ) -> tuple[str, int, int]:
        """
        テキストを生成

        SDKの例外はここで一度だけAPIErrorに変換する。サブクラスでは変換しない
        """
        try:
            return self._generate_content(user_prompt, model_name, system_prompt)
        except APIError:
            raise
        except Exception as e:
            raise APIError(
                get_message(
                    "ERROR",
                    "API_CLIENT_ERROR",
                    client=type(self).__name__,
                    error=str(e),
                )
            ) from e

    def create_summary_prompt(self, request: SummaryRequest) -> tuple[str, str]:
        """指示をsystem promptに、カルテ等のデータをuserメッセージに分離して生成"""
        try:
            with get_db_session() as db:
                prompt_data = get_prompt(
                    db, request.department, request.document_type, request.doctor
                )
                if prompt_data:
                    prompt_template = prompt_data.content
                else:
                    prompt_template = DEFAULT_SUMMARY_PROMPT
        except Exception:
            prompt_template = DEFAULT_SUMMARY_PROMPT

        system_prompt = f"{prompt_template}\n{GROUNDING_INSTRUCTION}"
        if _is_json_text(request.medical_text):
            system_prompt += f"\n{KARTE_JSON_INSTRUCTION}"

        user_message = f"<カルテ情報>\n{request.medical_text}\n</カルテ情報>"

        if request.current_prescription.strip():
            user_message += (
                f"\n\n<現在の処方>\n{request.current_prescription}\n</現在の処方>"
            )

        if request.additional_info.strip():
            user_message += f"\n\n<追加情報>\n{request.additional_info}\n</追加情報>"

        # 前回の生成結果と評価結果が両方指定された場合のみ再生成モード
        if request.previous_summary.strip() and request.evaluation_feedback.strip():
            system_prompt += f"\n{REFINEMENT_INSTRUCTION}"
            user_message += (
                f"\n\n<前回の生成結果>\n{request.previous_summary}\n</前回の生成結果>"
                f"\n\n<評価結果>\n{request.evaluation_feedback}\n</評価結果>"
            )

        return system_prompt, user_message

    def generate_summary(
        self, request: SummaryRequest, model_name: str
    ) -> tuple[str, int, int]:
        """文書生成リクエストからプロンプトを組み立てて生成"""
        system_prompt, user_message = self.create_summary_prompt(request)
        return self.generate(system_prompt, user_message, model_name)
