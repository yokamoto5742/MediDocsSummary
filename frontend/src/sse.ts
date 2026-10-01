import { ApiError, errorMessage, postJson } from './api';
import type { SSEErrorEvent } from './types';

// 1イベント分のテキストから event と data を取り出して通知
function dispatchEvent(eventText: string, onEvent: (event: string, data: unknown) => void): void {
    let event = '';
    let data = '';

    for (const line of eventText.split('\n')) {
        if (line.startsWith('event: ')) {
            event = line.slice(7).trim();
        } else if (line.startsWith('data: ')) {
            data = line.slice(6);
        }
    }

    if (event && data) {
        onEvent(event, JSON.parse(data));
    }
}

// SSEレスポンスを読み取り、イベントごとに onEvent を呼ぶ
export async function readSSE(
    response: Response,
    onEvent: (event: string, data: unknown) => void
): Promise<void> {
    if (!response.body) {
        throw new Error(window.MESSAGES.ERROR.RESPONSE_BODY_EMPTY);
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    try {
        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            // イベントは空行で区切られる。末尾の要素は受信途中なので次回に持ち越す
            const events = buffer.split('\n\n');
            buffer = events.pop() || '';
            events.forEach(eventText => dispatchEvent(eventText, onEvent));
        }

        dispatchEvent(buffer, onEvent);
    } finally {
        reader.releaseLock();
    }
}

// SSEエンドポイントにPOSTし、complete イベントのデータを返す
// progress イベントは接続維持用のハートビートなので読み捨てる
export async function requestSSE<T>(url: string, body: unknown): Promise<T> {
    const response = await fetch(url, postJson(body));
    if (!response.ok) {
        throw new ApiError(await errorMessage(response, window.MESSAGES.ERROR.API_ERROR));
    }

    let result: T | undefined;
    await readSSE(response, (event, data) => {
        if (event === 'complete') {
            result = data as T;
        } else if (event === 'error') {
            throw new ApiError((data as SSEErrorEvent).error_message || window.MESSAGES.ERROR.GENERIC_ERROR);
        }
    });

    // complete も error も届かずにストリームが閉じた場合
    if (result === undefined) {
        throw new Error('SSEストリームが完了イベントなしで終了しました');
    }
    return result;
}
