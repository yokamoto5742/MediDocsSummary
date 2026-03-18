# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## House Rules:
- 文章ではなくパッチの差分を返す。
- コードの変更範囲は最小限に抑える。
- コードの修正は直接適用する。
- Pythonのコーディング規約はPEP8に従います。
- KISSの原則に従い、できるだけシンプルなコードにします。
- 可読性を優先します。一度読んだだけで理解できるコードが最高のコードです。
- Pythonのコードのimport文は以下の適切な順序に並べ替えてください。
標準ライブラリ
サードパーティライブラリ
カスタムモジュール 
それぞれアルファベット順に並べます。importが先でfromは後です。

## クリーンコードガイドライン
- 関数のサイズ：関数は50行以下に抑えることを目標にしてください。関数の処理が多すぎる場合は、より小さな関数に分割してください。
- 単一責任：各関数とモジュールには明確な目的が1つあるようにします。無関係なロジックをまとめないでください。
- 命名：説明的な名前を使用してください。`tmp` 、`data`、`handleStuff`のような一般的な名前は避けてください。例えば、`doCalc`よりも`calculateInvoiceTotal` の方が適しています。
- DRY原則：コードを重複させないでください。類似のロジックが2箇所に存在する場合は、共有関数にリファクタリングしてください。それぞれに独自の実装が必要な場合はその理由を明確にしてください。
- コメント:分かりにくいロジックについては説明を加えます。説明不要のコードには過剰なコメントはつけないでください。
- コメントとdocstringは必要最小限に日本語で記述します。
- このアプリのUI画面で表示するメッセージはすべて日本語にします。constants.pyで一元管理します。

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

## コーディング規約

- 型ヒント必須（パラメータと戻り値）
- コメントは複雑なロジックのみ日本語で記述
- 関数は50行以下を目標
- インポート順: 標準ライブラリ → サードパーティ → ローカル（各グループ内アルファベット順、`import` 先・`from` 後）

## コミットメッセージ形式

`✨ feat`, `🐛 fix`, `📝 docs`, `♻️ refactor`, `✅ test` プレフィックスを使用し、変更内容と理由を日本語で記述。
