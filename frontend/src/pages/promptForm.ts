import { errorMessage, fetchDoctors, getHeaders, postJson } from '../api';
import type { PromptDetail } from '../types';

interface PromptForm {
    department: string;
    doctor: string;
    documentType: string;
    selectedModel: string;
    content: string;
}

interface PromptNewPage {
    form: PromptForm;
    doctors: string[];
    isSaving: boolean;
    error: string | null;
    init(): Promise<void>;
    updateDoctors(): Promise<void>;
    savePrompt(): Promise<void>;
}

interface PromptEditPage {
    promptId: number;
    form: PromptForm;
    isLoading: boolean;
    isSaving: boolean;
    error: string | null;
    loadError: string | null;
    init(): Promise<void>;
    loadPrompt(): Promise<void>;
    updatePrompt(): Promise<void>;
    deletePrompt(): Promise<void>;
}

// プロンプトを保存し、成功したら一覧へ遷移する。失敗時は表示用のエラーメッセージを返す
// 新規作成と更新で共通（診療科・医師・文書タイプが同じプロンプトがあればサーバー側で更新される）
async function savePromptAndRedirect(
    form: PromptForm,
    redirectTo: string,
    failureMessage: string
): Promise<string | null> {
    try {
        const response = await fetch('/api/prompts/', postJson({
            department: form.department,
            doctor: form.doctor,
            document_type: form.documentType,
            selected_model: form.selectedModel || null,
            content: form.content
        }));

        if (!response.ok) {
            return await errorMessage(response, failureMessage);
        }
        window.location.href = redirectTo;
        return null;
    } catch (e) {
        return window.MESSAGES.ERROR.API_ERROR;
    }
}

// プロンプト新規作成ページ
export function promptNewPage(): PromptNewPage {
    return {
        form: {
            department: 'default',
            doctor: 'default',
            documentType: window.DOCUMENT_TYPES[0],
            selectedModel: '',
            content: ''
        },
        doctors: ['default'],
        isSaving: false,
        error: null,

        async init() {
            await this.updateDoctors();
        },

        async updateDoctors() {
            try {
                this.doctors = await fetchDoctors(this.form.department);
                if (!this.doctors.includes(this.form.doctor)) {
                    this.form.doctor = this.doctors[0];
                }
            } catch (e) {
                this.doctors = ['default'];
            }
        },

        async savePrompt() {
            if (!this.form.department || !this.form.doctor || !this.form.documentType || !this.form.content.trim()) {
                this.error = window.MESSAGES.VALIDATION.ALL_REQUIRED_FIELDS;
                return;
            }

            this.isSaving = true;
            this.error = await savePromptAndRedirect(
                this.form, '/prompts?created=1', window.MESSAGES.ERROR.PROMPT_CREATE_FAILED
            );
            this.isSaving = false;
        }
    };
}

// プロンプト編集ページ
export function promptEditPage(promptId: number): PromptEditPage {
    return {
        promptId: promptId,
        form: {
            department: '',
            doctor: '',
            documentType: '',
            selectedModel: '',
            content: ''
        },
        isLoading: true,
        isSaving: false,
        error: null,
        loadError: null,

        async init() {
            await this.loadPrompt();
        },

        async loadPrompt() {
            this.isLoading = true;
            this.loadError = null;

            try {
                const response = await fetch(`/api/prompts/${this.promptId}`);
                if (response.ok) {
                    const data = await response.json() as PromptDetail;
                    this.form = {
                        department: data.department,
                        doctor: data.doctor,
                        documentType: data.document_type,
                        selectedModel: data.selected_model || '',
                        content: data.content
                    };
                } else if (response.status === 404) {
                    this.loadError = window.MESSAGES.ERROR.PROMPT_NOT_FOUND;
                } else {
                    this.loadError = window.MESSAGES.ERROR.PROMPT_LOAD_FAILED;
                }
            } catch (e) {
                this.loadError = window.MESSAGES.ERROR.API_ERROR;
            } finally {
                this.isLoading = false;
            }
        },

        async updatePrompt() {
            if (!this.form.content.trim()) {
                this.error = window.MESSAGES.VALIDATION.PROMPT_CONTENT_REQUIRED;
                return;
            }

            this.isSaving = true;
            this.error = await savePromptAndRedirect(
                this.form, '/prompts?updated=1', window.MESSAGES.ERROR.PROMPT_UPDATE_FAILED
            );
            this.isSaving = false;
        },

        async deletePrompt() {
            if (!confirm(window.MESSAGES.CONFIRM.DELETE_PROMPT)) return;

            this.isSaving = true;
            this.error = null;

            try {
                const response = await fetch(`/api/prompts/${this.promptId}`, {
                    method: 'DELETE',
                    headers: getHeaders()
                });

                if (response.ok) {
                    window.location.href = '/prompts?deleted=1';
                } else {
                    this.error = await errorMessage(response, window.MESSAGES.ERROR.PROMPT_DELETE_FAILED);
                }
            } catch (e) {
                this.error = window.MESSAGES.ERROR.API_ERROR;
            } finally {
                this.isSaving = false;
            }
        }
    };
}
