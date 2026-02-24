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

## Automatic Notifications (Hooks)
自動通知は`.claude/settings.local.json` で設定済：
- **Stop Hook**: ユーザーがClaude Codeを停止した時に「作業が完了しました」と通知
- **SessionEnd Hook**: セッション終了時に「Claude Code セッションが終了しました」と通知

## クリーンコードガイドライン
- 関数のサイズ：関数は50行以下に抑えることを目標にしてください。関数の処理が多すぎる場合は、より小さな関数に分割してください。
- 単一責任：各関数とモジュールには明確な目的が1つあるようにします。無関係なロジックをまとめないでください。
- 命名：説明的な名前を使用してください。`tmp` 、`data`、`handleStuff`のような一般的な名前は避けてください。例えば、`doCalc`よりも`calculateInvoiceTotal` の方が適しています。
- DRY原則：コードを重複させないでください。類似のロジックが2箇所に存在する場合は、共有関数にリファクタリングしてください。それぞれに独自の実装が必要な場合はその理由を明確にしてください。
- コメント:分かりにくいロジックについては説明を加えます。説明不要のコードには過剰なコメントはつけないでください。
- コメントとdocstringは必要最小限に日本語で記述します。文末に"。"や"."をつけないでください。
- このアプリのUI画面で表示するメッセージはすべて日本語にします。app/core/constants.pyで一元管理します。

## Commands

### Backend
```bash
# Dev server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Run all tests
python -m pytest tests/ -v --tb=short

# Run a single test file
python -m pytest tests/services/test_summary_service.py -v

# Run a single test
python -m pytest tests/services/test_summary_service.py::test_generate_summary -v

# Coverage
python -m pytest tests/ -v --tb=short --cov=app --cov-report=html

# Type checking (checks app/ only, excludes tests/ and scripts/)
pyright
```

### Database migrations (Alembic)
```bash
alembic revision --autogenerate -m "説明"
alembic upgrade head
alembic downgrade -1
```

### Frontend
```bash
cd frontend && npm install
npm run dev      # Vite dev server
npm run build    # Production build
npm run typecheck
```

## Architecture

This is a FastAPI application for generating Japanese medical summary documents (退院時サマリ) using Claude and Gemini AI models.

### Layer structure

```
Request → API router (app/api/) → Service layer (app/services/) → External API (app/external/)
                                         ↓
                               Database (app/models/)
```

- **`app/api/`** — FastAPI route handlers. All state-changing routes (POST/PUT/DELETE) require CSRF validation via `X-CSRF-Token` header.
- **`app/services/`** — Business logic separated from routes. `summary_service.py` orchestrates the full document generation pipeline.
- **`app/external/`** — AI API clients. `api_factory.py` is the entry point; use `create_client(APIProvider)` to get the right client.
- **`app/models/`** — SQLAlchemy ORM models backed by PostgreSQL.
- **`app/schemas/`** — Pydantic v2 request/response schemas.
- **`app/core/constants.py`** — Single source of truth for all constants and user-facing messages.

### Settings loading

`app/core/config.py::get_settings()` is `@lru_cache`-cached. On startup it tries to pull secrets from AWS Secrets Manager (`AWS_SECRET_NAME` env var, default `medidocs/prod`), then falls back to `.env`. Existing env vars are never overwritten by Secrets Manager.

### Database sessions

Two patterns are used:
- `get_db()` — FastAPI `Depends()` injection for route handlers
- `get_db_session()` — `contextmanager` for use inside service layer functions (commits on exit, rolls back on exception)

Tests override `get_db` via `app.dependency_overrides` and use SQLite in-memory.

### AI provider selection and auto-switching

`model_selector.py::determine_model()` handles model selection:
1. If `model_explicitly_selected=False`, queries DB for per-doctor/department model preference
2. If input exceeds `MAX_TOKEN_THRESHOLD` (default 100,000 chars) and Claude is selected, auto-switches to Gemini
3. `api_factory.create_client()` picks `CloudflareGeminiAPIClient` when all three Cloudflare env vars are set, otherwise uses direct `GeminiAPIClient`/`ClaudeAPIClient`

### Hierarchical prompt resolution

When building the AI prompt, `prompt_service.get_prompt()` resolves in priority order:
1. Doctor + document type specific prompt
2. Department + document type specific prompt
3. Document type default prompt
4. `DEFAULT_SUMMARY_PROMPT` constant

### Document generation (SSE streaming)

`/api/summary/stream` uses Server-Sent Events. `sse_helpers.stream_with_heartbeat()` runs the synchronous AI API call in a thread pool while sending periodic heartbeat events to keep the connection alive.

### Constants and messages

All strings shown to users or logged must come from `app/core/constants.py`. Use `get_message(category, key, **kwargs)` to retrieve with placeholder substitution. Categories: `ERROR`, `CONFIG`, `VALIDATION`, `SUCCESS`, `STATUS`, `INFO`, `CONFIRM`, `LOG`, `AUDIT`. `FRONTEND_MESSAGES` is a curated subset passed to Jinja2 templates.

## Testing

- Tests run with `asyncio_mode = auto` (pytest-asyncio).
- The `test_db` fixture (SQLite in-memory) is **function-scoped** and automatically overrides the `get_db` dependency.
- The `client` fixture depends on `test_db` and returns a `TestClient`.
- The `csrf_headers` fixture provides the `X-CSRF-Token` header required for mutating endpoints.
- External AI API calls must be mocked with `pytest-mock`; never call real APIs in tests.

## Code conventions

- All functions must have type hints (parameters and return type).
- Never use magic strings — reference `app/core/constants.py`.
- Comments written in Japanese only when logic is non-obvious; no trailing 句点（。）.
- Import order: stdlib → third-party → local, alphabetical within each group (`import` before `from`).
- Keep functions under 50 lines.
- Commit format: `✨ feat`, `🐛 fix`, `📝 docs`, `♻️ refactor`, `✅ test` with Japanese description.
