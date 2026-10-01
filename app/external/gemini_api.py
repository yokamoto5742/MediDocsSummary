import json
from typing import Any

from google import genai
from google.genai import interactions
from google.oauth2 import service_account

from app.core.config import get_settings
from app.core.constants import MESSAGES, get_message
from app.external.base_api import BaseAPIClient
from app.utils.exceptions import APIError


class GeminiAPIClient(BaseAPIClient):
    """Vertex AI 経由の Gemini API クライアント"""

    def __init__(self) -> None:
        self.settings = get_settings()
        if not self.settings.google_project_id:
            raise APIError(MESSAGES["CONFIG"]["VERTEX_AI_PROJECT_MISSING"])

        self.client = genai.Client(
            vertexai=True,
            project=self.settings.google_project_id,
            location=self.settings.google_location,
            credentials=self._load_credentials(),
        )

    def _load_credentials(self) -> service_account.Credentials | None:
        """サービスアカウントJSONから認証情報を生成（未設定ならNoneを返しSDKの既定の認証に任せる）"""
        google_credentials_json = self.settings.google_credentials_json
        if not google_credentials_json:
            return None

        try:
            return service_account.Credentials.from_service_account_info(
                json.loads(google_credentials_json),
                scopes=["https://www.googleapis.com/auth/cloud-platform"],
            )
        except json.JSONDecodeError as e:
            raise APIError(
                get_message("ERROR", "VERTEX_AI_CREDENTIALS_JSON_PARSE_ERROR", error=str(e))
            )
        except KeyError as e:
            raise APIError(
                get_message("ERROR", "VERTEX_AI_CREDENTIALS_FIELD_MISSING", error=str(e))
            )
        except Exception as e:
            raise APIError(
                get_message("ERROR", "VERTEX_AI_CREDENTIALS_ERROR", error=str(e))
            )

    def _thinking_level(self) -> str:
        return "low" if self.settings.gemini_thinking_level == "LOW" else "high"

    def _generate_content(
        self, prompt: str, model_name: str, system_prompt: str = ""
    ) -> tuple[str, int, int]:
        request: dict[str, Any] = {
            "model": model_name,
            "input": prompt,
            "generation_config": {"thinking_level": self._thinking_level()},
            # 患者情報を含むためサーバー側に保存しない
            "store": False,
            # 思考を伴う長時間の生成でも応答待ちでタイムアウトしないよう、
            # ストリーミングで受信してここで結合する（呼び出し側には全文だけを返す）
            "stream": True,
        }
        if system_prompt:
            request["system_instruction"] = system_prompt

        event_stream: Any = self.client.interactions.create(**request)

        chunks: list[str] = []
        input_tokens = 0
        output_tokens = 0
        for event in event_stream:
            if isinstance(event, interactions.StepDelta):
                if isinstance(event.delta, interactions.TextDelta) and event.delta.text:
                    chunks.append(event.delta.text)
            elif isinstance(event, interactions.InteractionCompletedEvent):
                input_tokens, output_tokens = _token_counts(event.interaction.usage)

        if not chunks:
            raise APIError(MESSAGES["ERROR"]["EMPTY_RESPONSE"])

        return "".join(chunks), input_tokens, output_tokens


def _token_counts(usage: interactions.Usage | None) -> tuple[int, int]:
    """(入力トークン数, 出力トークン数) を返す"""
    if usage is None:
        return 0, 0
    return usage.total_input_tokens or 0, usage.total_output_tokens or 0
