import { displayMessage, fetchDoctors } from './api';
import { requestSSE } from './sse';
import type {
    Settings,
    SummaryForm,
    GenerationResult,
    EvaluationResult,
    SelectedModelResponse,
    SSECompleteEvent,
    SSEEvaluationCompleteEvent
} from './types';

type ScreenType = 'input' | 'output' | 'evaluation';

interface AppState {
    settings: Settings;
    doctors: string[];
    form: SummaryForm;
    result: GenerationResult;
    isGenerating: boolean;
    elapsedTime: number;
    timerInterval: ReturnType<typeof setInterval> | null;
    showCopySuccess: boolean;
    error: string | null;
    activeTab: number;
    tabs: readonly string[];
    currentScreen: ScreenType;
    evaluationResult: EvaluationResult;
    isEvaluating: boolean;
    init(): Promise<void>;
    updateDoctors(): Promise<void>;
    updateSelectedModel(): Promise<void>;
    startTimer(): void;
    stopTimer(): void;
    generateSummary(): Promise<void>;
    refineSummary(): Promise<void>;
    runGeneration(extraBody: Record<string, string>): Promise<void>;
    clearForm(): void;
    backToInput(): void;
    backToOutput(): void;
    showEvaluation(): void;
    evaluateOutput(): Promise<void>;
    copyToClipboard(text: string): Promise<void>;
    getCurrentTabContent(): string;
    copyCurrentTab(): void;
    getTabClass(index: number): string;
}

function emptyResult(): GenerationResult {
    return {
        outputSummary: '',
        parsedSummary: {},
        processingTime: null,
        modelUsed: '',
        modelSwitched: false
    };
}

function emptyEvaluation(): EvaluationResult {
    return { result: '', processingTime: null };
}

export function appState(): AppState {
    return {
        // Settings
        settings: {
            department: 'default',
            doctor: 'default',
            documentType: window.DOCUMENT_TYPES[0],
            model: 'Claude'
        },
        doctors: ['default'],

        // Form
        form: {
            currentPrescription: '',
            medicalText: '',
            additionalInfo: ''
        },

        // Result
        result: emptyResult(),

        // UI state
        isGenerating: false,
        // 生成と評価は同時に走らないため、経過時間のタイマーは共用する
        elapsedTime: 0,
        timerInterval: null,
        showCopySuccess: false,
        error: null,
        activeTab: 0,
        tabs: window.TAB_NAMES,
        currentScreen: 'input',

        // Evaluation state
        evaluationResult: emptyEvaluation(),
        isEvaluating: false,

        async init() {
            await this.updateDoctors();
            await this.updateSelectedModel();
        },

        async updateDoctors() {
            try {
                this.doctors = await fetchDoctors(this.settings.department);
                if (!this.doctors.includes(this.settings.doctor)) {
                    this.settings.doctor = this.doctors[0];
                }
            } catch (error) {
                console.error('医師リストの取得中にエラーが発生しました:', error);
            }
        },

        async updateSelectedModel() {
            try {
                const params = new URLSearchParams({
                    department: this.settings.department,
                    document_type: this.settings.documentType,
                    doctor: this.settings.doctor
                });
                const response = await fetch(`/api/settings/selected-model?${params}`);
                if (!response.ok) {
                    console.error('選択モデルの取得に失敗しました:', response.status, response.statusText);
                    return;
                }
                const data = await response.json() as SelectedModelResponse;
                if (data.selected_model) {
                    this.settings.model = data.selected_model;
                }
            } catch (error) {
                console.error('選択モデルの取得中にエラーが発生しました:', error);
            }
        },

        startTimer() {
            this.elapsedTime = 0;
            this.timerInterval = setInterval(() => {
                this.elapsedTime++;
            }, 1000);
        },

        stopTimer() {
            if (this.timerInterval !== null) {
                clearInterval(this.timerInterval);
                this.timerInterval = null;
            }
        },

        async generateSummary() {
            if (!this.form.medicalText.trim()) {
                this.error = window.MESSAGES.VALIDATION.NO_INPUT;
                return;
            }

            await this.runGeneration({});
        },

        // 評価の指摘を反映して再生成
        async refineSummary() {
            if (!this.result.outputSummary || !this.evaluationResult.result) {
                this.error = window.MESSAGES.VALIDATION.EVALUATION_NO_OUTPUT;
                return;
            }

            await this.runGeneration({
                previous_summary: this.result.outputSummary,
                evaluation_feedback: this.evaluationResult.result
            });
        },

        async runGeneration(extraBody: Record<string, string>) {
            this.isGenerating = true;
            this.error = null;
            this.startTimer();

            try {
                const data = await requestSSE<SSECompleteEvent>('/api/summary/generate-stream', {
                    current_prescription: this.form.currentPrescription,
                    medical_text: this.form.medicalText,
                    additional_info: this.form.additionalInfo,
                    department: this.settings.department,
                    doctor: this.settings.doctor,
                    document_type: this.settings.documentType,
                    model: this.settings.model,
                    model_explicitly_selected: true,
                    ...extraBody
                });

                this.result = {
                    outputSummary: data.output_summary || '',
                    parsedSummary: data.parsed_summary || {},
                    processingTime: data.processing_time || null,
                    modelUsed: data.model_used || '',
                    modelSwitched: data.model_switched || false
                };
                // 文書が変わったので前回の評価は破棄する
                this.evaluationResult = emptyEvaluation();
                this.activeTab = 0;
                this.currentScreen = 'output';
            } catch (e) {
                this.error = displayMessage(e, window.MESSAGES.ERROR.API_ERROR);
            } finally {
                this.stopTimer();
                this.isGenerating = false;
            }
        },

        clearForm() {
            this.form = {
                currentPrescription: '',
                medicalText: '',
                additionalInfo: ''
            };
            this.result = emptyResult();
            this.evaluationResult = emptyEvaluation();
            this.error = null;
        },

        backToInput() {
            this.clearForm();
            this.currentScreen = 'input';
            this.error = null;
        },

        backToOutput() {
            this.currentScreen = 'output';
        },

        showEvaluation() {
            this.currentScreen = 'evaluation';
        },

        async evaluateOutput() {
            if (!this.result.outputSummary) {
                this.error = window.MESSAGES.VALIDATION.EVALUATION_NO_OUTPUT;
                return;
            }

            // 既に評価結果がある場合は確認ダイアログを表示
            if (this.evaluationResult.result) {
                if (!confirm(window.MESSAGES.CONFIRM.RE_EVALUATE)) {
                    return;
                }
            }

            this.isEvaluating = true;
            this.error = null;
            this.startTimer();

            try {
                const data = await requestSSE<SSEEvaluationCompleteEvent>('/api/evaluation/evaluate-stream', {
                    document_type: this.settings.documentType,
                    input_text: this.form.medicalText,
                    current_prescription: this.form.currentPrescription,
                    additional_info: this.form.additionalInfo,
                    output_summary: this.result.outputSummary
                });

                this.evaluationResult = {
                    result: data.evaluation_result || '',
                    processingTime: data.processing_time || null
                };
                this.currentScreen = 'evaluation';
            } catch (e) {
                this.error = displayMessage(e, window.MESSAGES.ERROR.EVALUATION_ERROR);
            } finally {
                this.stopTimer();
                this.isEvaluating = false;
            }
        },

        async copyToClipboard(text: string) {
            try {
                await navigator.clipboard.writeText(text);
                this.showCopySuccess = true;
                setTimeout(() => {
                    this.showCopySuccess = false;
                }, 2000);
            } catch (e) {
                this.error = window.MESSAGES.ERROR.COPY_FAILED;
            }
        },

        // ヘルパー関数
        getCurrentTabContent(): string {
            if (this.activeTab === 0) {
                return this.result.outputSummary;
            }
            return this.result.parsedSummary[this.tabs[this.activeTab]] || '';
        },

        copyCurrentTab() {
            this.copyToClipboard(this.getCurrentTabContent());
        },

        getTabClass(index: number): string {
            return this.activeTab === index
                ? 'border-blue-500 text-blue-600 dark:border-blue-400 dark:text-blue-400'
                : 'border-transparent text-white hover:text-gray-700 dark:hover:text-gray-300';
        }
    };
}
