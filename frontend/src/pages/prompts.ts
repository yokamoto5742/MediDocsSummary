import { errorMessage, fetchDoctors, getHeaders } from '../api';
import type { PromptListItem } from '../types';
import { formatDateTime, sortIcon, sortRows, toggleSort } from './table';
import type { SortState } from './table';

interface PromptsPage {
    prompts: PromptListItem[];
    filteredPrompts: PromptListItem[];
    doctors: string[];
    filter: { department: string; doctor: string; documentType: string };
    isLoading: boolean;
    error: string | null;
    successMessage: string | null;
    sort: SortState;
    init(): Promise<void>;
    updateDoctors(): Promise<void>;
    checkQueryParams(): void;
    loadPrompts(): Promise<void>;
    applyFilters(): void;
    deletePrompt(promptId: number): Promise<void>;
    formatDate(dateStr: string | null): string;
    sortPrompts(column: string): void;
    getSortIcon(column: string): string;
}

// プロンプト管理ページ（一覧）
export function promptsPage(): PromptsPage {
    return {
        prompts: [],
        filteredPrompts: [],
        doctors: ['default'],
        filter: {
            department: 'default',
            doctor: 'default',
            documentType: window.DOCUMENT_TYPES[0]
        },
        isLoading: false,
        error: null,
        successMessage: null,
        sort: {
            column: '',
            direction: 'asc'
        },

        async init() {
            this.checkQueryParams();
            await this.updateDoctors();
            await this.loadPrompts();
        },

        async updateDoctors() {
            if (!this.filter.department) {
                this.doctors = ['default'];
                return;
            }
            try {
                this.doctors = await fetchDoctors(this.filter.department);
                if (this.filter.doctor && !this.doctors.includes(this.filter.doctor)) {
                    this.filter.doctor = '';
                }
            } catch (e) {
                this.doctors = ['default'];
            }
        },

        checkQueryParams() {
            // 作成・更新・削除後のリダイレクトで付くクエリパラメータと、表示する成功メッセージ
            const successMessages: Record<string, string> = {
                created: window.MESSAGES.SUCCESS.PROMPT_CREATED,
                updated: window.MESSAGES.SUCCESS.PROMPT_UPDATED,
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
                const response = await fetch('/api/prompts/');
                this.prompts = await response.json() as PromptListItem[];
                this.applyFilters();
            } catch (e) {
                this.error = window.MESSAGES.ERROR.PROMPT_LOAD_FAILED;
            } finally {
                this.isLoading = false;
            }
        },

        applyFilters() {
            this.filteredPrompts = this.prompts.filter(p => {
                if (this.filter.department && p.department !== this.filter.department) return false;
                if (this.filter.doctor && p.doctor !== this.filter.doctor) return false;
                if (this.filter.documentType && p.document_type !== this.filter.documentType) return false;
                return true;
            });
        },

        async deletePrompt(promptId: number) {
            if (!confirm(window.MESSAGES.CONFIRM.DELETE_PROMPT)) return;

            try {
                const response = await fetch(`/api/prompts/${promptId}`, {
                    method: 'DELETE',
                    headers: getHeaders()
                });
                if (response.ok) {
                    this.successMessage = window.MESSAGES.SUCCESS.PROMPT_DELETED;
                    await this.loadPrompts();
                } else {
                    this.error = await errorMessage(response, window.MESSAGES.ERROR.PROMPT_DELETE_FAILED);
                }
            } catch (e) {
                this.error = window.MESSAGES.ERROR.API_ERROR;
            }
        },

        formatDate(dateStr: string | null): string {
            return formatDateTime(dateStr);
        },

        sortPrompts(column: string) {
            toggleSort(this.sort, column);
            sortRows(this.filteredPrompts, this.sort, 'updated_at');
        },

        getSortIcon(column: string): string {
            return sortIcon(this.sort, column);
        }
    };
}
