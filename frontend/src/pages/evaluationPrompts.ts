import { getHeaders, postJson } from '../api';
import type {
    EvaluationPrompt,
    EvaluationPromptListResponse,
    EvaluationPromptSaveResponse
} from '../types';
import { formatDateTime } from './table';

interface EvaluationPromptsPage {
    prompts: EvaluationPrompt[];
    documentTypes: readonly string[];
    isLoading: boolean;
    error: string | null;
    successMessage: string | null;
    init(): Promise<void>;
    checkQueryParams(): void;
    loadPrompts(): Promise<void>;
    getPrompt(docType: string): EvaluationPrompt | undefined;
    hasPrompt(docType: string): boolean;
    getPromptPreview(docType: string): string;
    getUpdatedAt(docType: string): string;
    deletePrompt(docType: string): Promise<void>;
}

interface EvaluationPromptEditPage {
    documentType: string;
    content: string;
    isSaving: boolean;
    error: string | null;
    init(): Promise<void>;
    loadPrompt(): Promise<void>;
    savePrompt(): Promise<void>;
}

// 一覧に表示するプロンプト内容の最大文字数
const PREVIEW_LENGTH = 50;

// 評価プロンプト管理ページ（文書タイプごとに1件）
export function evaluationPromptsPage(): EvaluationPromptsPage {
    return {
        prompts: [],
        documentTypes: window.DOCUMENT_TYPES,
        isLoading: false,
        error: null,
        successMessage: null,

        async init() {
            this.checkQueryParams();
            await this.loadPrompts();
        },

        checkQueryParams() {
            // 保存・削除後のリダイレクトで付くクエリパラメータと、表示する成功メッセージ
            const successMessages: Record<string, string> = {
                saved: window.MESSAGES.SUCCESS.PROMPT_SAVED,
                deleted: window.MESSAGES.SUCCESS.PROMPT_DELETED
            };
            const params = new URLSearchParams(window.location.search);
            const action = Object.keys(successMessages).find(key => params.get(key) === '1');
            if (action) {
                this.successMessage = successMessages[action];
                // 再読み込みで同じメッセージが出ないようクエリパラメータを消す
                window.history.replaceState({}, document.title, window.location.pathname);
            }
        },

        async loadPrompts() {
            this.isLoading = true;
            this.error = null;
            try {
                const response = await fetch('/api/evaluation/prompts');
                const data = await response.json() as EvaluationPromptListResponse;
                this.prompts = data.prompts || [];
            } catch (e) {
                this.error = window.MESSAGES.ERROR.PROMPT_LOAD_FAILED;
            } finally {
                this.isLoading = false;
            }
        },

        getPrompt(docType: string) {
            return this.prompts.find(p => p.document_type === docType);
        },

        hasPrompt(docType: string) {
            return !!this.getPrompt(docType);
        },

        getPromptPreview(docType: string) {
            const content = this.getPrompt(docType)?.content;
            if (!content) return '未設定';
            return content.length > PREVIEW_LENGTH ? content.substring(0, PREVIEW_LENGTH) + '...' : content;
        },

        getUpdatedAt(docType: string) {
            return formatDateTime(this.getPrompt(docType)?.updated_at);
        },

        async deletePrompt(docType: string) {
            const confirmMessage = window.MESSAGES.CONFIRM.DELETE_EVALUATION_PROMPT.replace('{document_type}', docType);
            if (!confirm(confirmMessage)) return;

            try {
                const response = await fetch(`/api/evaluation/prompts/${encodeURIComponent(docType)}`, {
                    method: 'DELETE',
                    headers: getHeaders()
                });
                const data = await response.json() as EvaluationPromptSaveResponse;
                if (data.success) {
                    this.successMessage = data.message;
                    await this.loadPrompts();
                } else {
                    this.error = data.message || window.MESSAGES.ERROR.EVALUATION_PROMPT_DELETE_FAILED;
                }
            } catch (e) {
                this.error = window.MESSAGES.ERROR.API_ERROR;
            }
        }
    };
}

// 評価プロンプト編集ページ
export function evaluationPromptEditPage(documentType: string): EvaluationPromptEditPage {
    return {
        documentType: documentType,
        content: '',
        isSaving: false,
        error: null,

        async init() {
            await this.loadPrompt();
        },

        async loadPrompt() {
            try {
                const response = await fetch(`/api/evaluation/prompts/${encodeURIComponent(this.documentType)}`);
                const data = await response.json() as EvaluationPrompt;
                if (data.content) {
                    this.content = data.content;
                }
            } catch (e) {
                this.error = window.MESSAGES.ERROR.EVALUATION_PROMPT_LOAD_FAILED;
            }
        },

        async savePrompt() {
            if (!this.content.trim()) {
                this.error = window.MESSAGES.VALIDATION.PROMPT_CONTENT_REQUIRED;
                return;
            }

            this.isSaving = true;
            this.error = null;

            try {
                const response = await fetch('/api/evaluation/prompts', postJson({
                    document_type: this.documentType,
                    content: this.content
                }));

                const data = await response.json() as EvaluationPromptSaveResponse;
                if (data.success) {
                    window.location.href = '/evaluation-prompts?saved=1';
                } else {
                    this.error = data.message || window.MESSAGES.ERROR.EVALUATION_PROMPT_SAVE_FAILED;
                }
            } catch (e) {
                this.error = window.MESSAGES.ERROR.API_ERROR;
            } finally {
                this.isSaving = false;
            }
        }
    };
}
