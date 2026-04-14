# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 概要

退院時サマリ作成アプリ。FastAPI + PostgreSQL バックエンド、Vite + TypeScript + Alpine.js フロントエンド。Claude（AWS Bedrock）と Gemini（Google Vertex AI）の両プロバイダーに対応。

## よく使うコマンド

### バックエンド

```bash
# 開発サーバー起動
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# テスト実行（全件）
python -m pytest tests/ -v --tb=short

# テスト実行（単一ファイル）
python -m pytest tests/services/test_summary_service.py -v

# テスト実行（単一テスト）
python -m pytest tests/services/test_summary_service.py::test_generate_summary -v

# カバレッジ付きテスト
python -m pytest tests/ -v --tb=short --cov=app --cov-report=html

# 型チェック
pyright
```

### フロントエンド

```bash
cd frontend
npm install
npm run dev        # 開発サーバー（ポート5173、/api を localhost:8000 にプロキシ）
npm run build      # 本番ビルド → ../app/static/dist/ に出力
npm run typecheck  # TypeScript 型チェック
```

### データベースマイグレーション

```bash
alembic revision --autogenerate -m "説明"
alembic upgrade head
alembic downgrade -1
```

## アーキテクチャ

### レイヤー構成

```
API層 (app/api/)       → HTTPルーティングのみ
Service層 (app/services/) → ビジネスロジック
External層 (app/external/) → AI API呼び出し
Model層 (app/models/)  → SQLAlchemy ORM
```

### AI プロバイダー

- `app/external/api_factory.py` の `create_client(APIProvider)` でクライアントを動的生成
- `ClaudeAPIClient`（AWS Bedrock）と `GeminiAPIClient`（Vertex AI）は `BaseAPIClient` を継承
- `app/services/model_selector.py` で入力文字数が `MAX_TOKEN_THRESHOLD` を超えた場合、Claude → Gemini に自動切り替え

### 階層的プロンプト解決

`prompt_service.get_prompt()` で以下の順序でDBを検索：
1. 診療科 + 医師 + 文書タイプ固有
2. 診療科 + デフォルト医師 + 文書タイプ
3. デフォルト診療科 + デフォルト医師 + 文書タイプ
4. フォールバック: `constants.py` の `DEFAULT_SUMMARY_PROMPT`

### 設定管理

- `app/core/config.py` の `Settings`（pydantic-settings）が `.env` ファイルを読み込み
- `get_settings()` は `@lru_cache` でシングルトン
- 優先順位: OS環境変数 → AWS Secrets Manager → `.env`

### 定数管理

`app/core/constants.py` で一元管理：
- `ModelType` Enum: `"Claude"`, `"Gemini_Pro"`
- `MESSAGES` dict: カテゴリ別の日本語メッセージ（`get_message(category, key, **kwargs)` で取得）
- `FRONTEND_MESSAGES`: テンプレートに渡す用のメッセージサブセット
- マジック文字列を使わず必ず定数を参照すること

### データフロー

1. フロントエンド（Alpine.js）→ POST `/api/summary`
2. `SummaryService` がプロンプト解決・モデル選択・API呼び出しを調整
3. `text_processor.py` がAI出力をセクション分割
4. 使用統計（トークン数・時間・コスト）を `usage` テーブルに保存
5. SSE（Server-Sent Events）でストリーミング返却

### セキュリティ

- CSRF トークン: 状態変更エンドポイント（POST/PUT/DELETE）で `X-CSRF-Token` ヘッダー必須
- 入力サニタイゼーション: `app/utils/input_sanitizer.py`（プロンプトインジェクション検出）
- セキュリティヘッダー: `SecurityHeadersMiddleware`（`app/core/security.py`）
- 監査ログ: `app/utils/audit_logger.py`（PHI は記録しない）
