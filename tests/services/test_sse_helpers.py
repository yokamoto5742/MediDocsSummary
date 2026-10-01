import asyncio
import json
import time

import pytest

from app.services.sse_helpers import (
    heartbeat_until_done,
    sse_error_event,
    sse_event,
    sse_response,
)


class TestSseEvent:
    """sse_event 関数のテスト"""

    def test_sse_event_basic(self):
        """SSEイベント生成 - 基本"""
        result = sse_event("progress", {"status": "starting"})

        assert result.startswith("event: progress\n")
        assert "data: " in result
        assert result.endswith("\n\n")

        data_line = result.split("data: ")[1].strip()
        parsed = json.loads(data_line)
        assert parsed["status"] == "starting"

    def test_sse_event_japanese(self):
        """SSEイベント生成 - 日本語"""
        result = sse_event("error", {"message": "エラーが発生しました"})

        data_line = result.split("data: ")[1].strip()
        parsed = json.loads(data_line)
        assert parsed["message"] == "エラーが発生しました"

    def test_sse_event_complete(self):
        """SSEイベント生成 - 完了イベント"""
        data = {
            "success": True,
            "input_tokens": 1000,
            "output_tokens": 500,
        }
        result = sse_event("complete", data)

        assert "event: complete\n" in result
        data_line = result.split("data: ")[1].strip()
        parsed = json.loads(data_line)
        assert parsed["success"] is True
        assert parsed["input_tokens"] == 1000

    def test_sse_error_event(self):
        """errorイベント生成 - success=False とメッセージを含む"""
        result = sse_error_event("失敗しました")

        assert result.startswith("event: error\n")
        parsed = json.loads(result.split("data: ")[1].strip())
        assert parsed == {"success": False, "error_message": "失敗しました"}


class TestSseResponse:
    """sse_response 関数のテスト"""

    async def test_sse_response_headers(self):
        """SSE用のメディアタイプとバッファリング無効化ヘッダーを設定する"""

        async def events():
            yield sse_event("progress", {})

        response = sse_response(events())

        assert response.media_type == "text/event-stream"
        assert response.headers["Cache-Control"] == "no-cache"
        assert response.headers["X-Accel-Buffering"] == "no"


class TestHeartbeatUntilDone:
    """heartbeat_until_done 関数のテスト"""

    async def _collect(self, task: asyncio.Future, heartbeat_interval: float = 5) -> list[str]:
        return [
            event
            async for event in heartbeat_until_done(
                task,
                start_message="開始",
                running_status="processing",
                running_message="処理中",
                elapsed_message_template="処理中... {elapsed}秒",
                heartbeat_interval=heartbeat_interval,  # type: ignore[arg-type]
            )
        ]

    async def test_yields_start_and_running_then_stops(self):
        """開始・実行中の2イベントを出し、タスク完了で終了する"""
        task = asyncio.create_task(asyncio.to_thread(lambda: ("結果", 100, 50)))

        events = await self._collect(task)

        assert len(events) == 2
        assert all("event: progress" in event for event in events)
        assert "開始" in events[0]
        assert "処理中" in events[1]
        # 結果はイベントに含めず、呼び出し側がタスクから受け取る
        assert await task == ("結果", 100, 50)

    async def test_yields_elapsed_events_while_running(self):
        """タスク実行中はハートビート間隔ごとに経過イベントを出す"""
        task = asyncio.create_task(asyncio.to_thread(time.sleep, 0.2))

        events = await self._collect(task, heartbeat_interval=0.05)

        assert len(events) > 2
        assert "秒" in events[2]
        assert task.done()

    async def test_task_error_is_left_to_caller(self):
        """タスクの例外はここで送出せず、errorイベントも出さない"""

        def failing_task() -> None:
            raise ValueError("テストエラー")

        task = asyncio.create_task(asyncio.to_thread(failing_task))

        events = await self._collect(task)

        assert len(events) == 2
        assert not any("event: error" in event for event in events)
        with pytest.raises(ValueError, match="テストエラー"):
            await task
