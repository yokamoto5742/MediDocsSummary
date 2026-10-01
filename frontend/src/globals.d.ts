// base.html のインラインスクリプトがサーバー側の値を window に設定する
interface Window {
    CSRF_TOKEN: string;
    TAB_NAMES: readonly string[];
    MESSAGES: Record<string, Record<string, string>>;
    DOCUMENT_TYPES: readonly string[];
}
