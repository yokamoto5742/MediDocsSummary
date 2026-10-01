import asyncio
import json
import time
from typing import Any, AsyncGenerator

from fastapi.responses import StreamingResponse


def sse_response(events: AsyncGenerator[str, None]) -> StreamingResponse:
    """SSEイベントのジェネレータをストリーミングレスポンスに変換"""
    return StreamingResponse(
        events,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            # リバースプロキシのバッファリングを無効化し、イベントを即時に届ける
            "X-Accel-Buffering": "no",
        },
    )


def sse_event(event_type: str, data: dict[str, Any]) -> str:
    """SSEイベント文字列を生成"""
    return f"event: {event_type}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def sse_error_event(error_message: str) -> str:
    """errorイベント文字列を生成"""
    return sse_event("error", {"success": False, "error_message": error_message})


async def heartbeat_until_done(
    task: asyncio.Future[Any],
    start_message: str,
    running_status: str,
    running_message: str,
    elapsed_message_template: str,
    heartbeat_interval: int = 5,
) -> AsyncGenerator[str, None]:
    """
    タスクが完了するまでprogressイベントを送り続ける

    タスクの結果と例外はここでは扱わない。呼び出し側が await task で受け取る
    """
    yield sse_event("progress", {"status": "starting", "message": start_message})
    yield sse_event("progress", {"status": running_status, "message": running_message})

    start_time = time.time()
    while True:
        # asyncio.waitはタスクが例外で終了しても送出しない
        done, _ = await asyncio.wait({task}, timeout=heartbeat_interval)
        if done:
            return
        elapsed = int(time.time() - start_time)
        yield sse_event(
            "progress",
            {
                "status": running_status,
                "message": elapsed_message_template.format(elapsed=elapsed),
            },
        )
