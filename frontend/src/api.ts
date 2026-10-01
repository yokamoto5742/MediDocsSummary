import type { DoctorsResponse } from './types';

// サーバーが返したメッセージを持つエラー（そのまま画面に表示してよい）
export class ApiError extends Error {}

// 画面に表示するメッセージを決める
// 通信断などサーバー由来でないエラーは内容をコンソールに残し、画面には定型文を出す
export function displayMessage(error: unknown, fallback: string): string {
    if (error instanceof ApiError) {
        return error.message;
    }
    console.error(error);
    return fallback;
}

// CSRFトークン付きのリクエストヘッダーを取得
export function getHeaders(additionalHeaders: Record<string, string> = {}): Record<string, string> {
    return { 'X-CSRF-Token': window.CSRF_TOKEN, ...additionalHeaders };
}

// JSONボディを送るPOSTリクエストのオプション
export function postJson(body: unknown): RequestInit {
    return {
        method: 'POST',
        headers: getHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify(body)
    };
}

// エラーレスポンスからサーバーのメッセージを取り出す
// 例外ハンドラ(422/500)は error_message、HTTPException(401/403/404)は detail で返す
export async function errorMessage(response: Response, fallback: string): Promise<string> {
    try {
        const data = await response.json();
        const message = data.error_message ?? data.detail;
        return typeof message === 'string' && message ? message : fallback;
    } catch {
        return fallback;
    }
}

// 診療科に所属する医師リストを取得
export async function fetchDoctors(department: string): Promise<string[]> {
    const response = await fetch(`/api/settings/doctors/${encodeURIComponent(department)}`);
    if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
    }
    const data = await response.json() as DoctorsResponse;
    return data.doctors;
}
