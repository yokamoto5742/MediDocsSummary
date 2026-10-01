// 一覧テーブルで共通に使う並び替えと日時表示

export interface SortState {
    column: string;
    direction: 'asc' | 'desc';
}

// 同じ列を再度選ぶと昇順・降順を切り替え、別の列なら昇順から始める
export function toggleSort(sort: SortState, column: string): void {
    if (sort.column === column) {
        sort.direction = sort.direction === 'asc' ? 'desc' : 'asc';
    } else {
        sort.column = column;
        sort.direction = 'asc';
    }
}

// 比較用の値に変換（日時はタイムスタンプ、文字列は大文字小文字を無視、未設定は空文字）
function sortKey(value: unknown, isDate: boolean): number | string {
    if (isDate) {
        return new Date(value as string).getTime();
    }
    if (typeof value === 'number') {
        return value;
    }
    return String(value ?? '').toLowerCase();
}

// 行を sort の列と向きで並び替える（配列を直接書き換える）
export function sortRows<T>(rows: T[], sort: SortState, dateColumn?: string): void {
    const column = sort.column as keyof T;
    const isDate = sort.column === dateColumn;
    const order = sort.direction === 'asc' ? 1 : -1;

    rows.sort((a, b) => {
        const aKey = sortKey(a[column], isDate);
        const bKey = sortKey(b[column], isDate);
        if (aKey < bKey) return -order;
        if (aKey > bKey) return order;
        return 0;
    });
}

export function sortIcon(sort: SortState, column: string): string {
    if (sort.column !== column) return '⇅';
    return sort.direction === 'asc' ? '↑' : '↓';
}

export function formatDateTime(dateStr: string | null | undefined): string {
    if (!dateStr) return '-';
    return new Date(dateStr).toLocaleString('ja-JP', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit'
    });
}
