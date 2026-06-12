# セキュリティ改善ガイド: 例外メッセージの遮断と秘密鍵のフェイルファスト

FastAPI + 外部AI API（Bedrock / Vertex AI 等）+ 監査ログという構成のアプリケーションに適用できる、2つのセキュリティ改善の実装手順。MediDocsSummary での実装（2026-06）を一般化したもの。

## 対象となるリスク

### リスク1: 例外メッセージの素通し

外部APIの例外（boto3 / google-genai 等）の `str(e)` には、リクエスト内容の断片や内部構成情報（エンドポイント、認証情報のヒント、リージョン等）が含まれることがある。これをそのまま流すと:

- **クライアントへの返却** → 内部構成情報の漏えい
- **監査ログへの記録** → 「ログに医療情報（個人情報）を残さない」方針が例外経路で破られる

### リスク2: 秘密鍵のデフォルトフォールバック

```python
csrf_secret_key: str = "default-csrf-secret-key"  # NG
```

本番では Secrets Manager 等から注入していても、環境変数が欠けると**黙って既知の鍵で起動**し、トークンが誰でも偽造可能になる。

## 基本方針

| 出力先 | 記録する内容 |
|---|---|
| クライアントへのレスポンス | 定型メッセージのみ（`constants.py` の定数を参照） |
| 監査ログ | 例外クラス名のみ（`type(e).__name__`） |
| サーバー内アプリケーションログ | 例外詳細（`exc_info=True`）— ここだけ詳細を許可 |

秘密鍵は「デフォルト値で黙って起動」を禁止し、未設定なら**起動時に例外で落とす**。

---

## 改善1: 例外メッセージの遮断

### 手順1-1: グローバル例外ハンドラの修正

`str(exc)` をクライアントに返している箇所を定型メッセージに置き換え、詳細はサーバーログへ。

**Before:**

```python
async def api_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content={"success": False, "error_message": str(exc)},
    )
```

**After:**

```python
import logging

from app.core.constants import MESSAGES

logger = logging.getLogger(__name__)


async def api_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    # 例外詳細はサーバーログのみに記録し、クライアントには定型メッセージを返す
    logger.error("未処理の例外: %s", type(exc).__name__, exc_info=exc)
    return JSONResponse(
        status_code=500,
        content={"success": False, "error_message": MESSAGES["ERROR"]["GENERIC_ERROR"]},
    )


async def validation_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.warning("リクエスト検証エラー: %s", type(exc).__name__)
    return JSONResponse(
        status_code=422,
        content={"success": False, "error_message": MESSAGES["ERROR"]["INPUT_ERROR"]},
    )
```

注意: 422（`RequestValidationError`）の `str(exc)` には**検証に失敗した入力値そのもの**が含まれるため、フィールド名込みの詳細を返すのもやめて定型文にする。

### 手順1-2: サービス層の監査ログを例外クラス名に置換

`grep -rn "error_message=str(e)" app/` で全箇所を洗い出し、監査ログへの記録をすべて置換する。

**Before:**

```python
except Exception as e:
    log_audit_event(
        event_type=...,
        success=False,
        error_message=str(e),
    )
    return _error_response(str(e), ...)
```

**After:**

```python
except Exception as e:
    # 例外詳細はサーバーログのみに記録（外部APIの例外文字列に入力断片が含まれる可能性があるため）
    logger.error("文書生成API呼び出しエラー", exc_info=True)
    log_audit_event(
        event_type=...,
        success=False,
        error_message=type(e).__name__,
    )
    return _error_response(MESSAGES["ERROR"]["API_ERROR"], ...)
```

クライアント向けメッセージの判断基準:

- **外部APIの例外を拾う `except`**（`except Exception` / `except APIError`）→ 定型メッセージ（`API_ERROR` 等）に置換。外部例外の文字列が `APIError("... : {error}".format(error=str(e)))` のように内部でラップされている場合も、`str(e)` には外部由来の断片が残っているため同様に遮断する
- **内部の設定不備による `ValueError`**（メッセージが `constants.py` の定数由来）→ ユーザー向け文言として安全なので `str(e)` のまま返してよい

副次対応: ラップ用の `"... : {error}"` 形式の定数（例: `EVALUATION_API_ERROR`）が不要になったら削除する。

### 手順1-3: SSEストリーミング経路の修正

SSEヘルパーが例外をエラーイベントとしてクライアントに流している場合、ここも定型メッセージ化する。

**Before:**

```python
except Exception as e:
    logging.error(f"Task error: {e}", exc_info=True)
    await queue.put(("error", str(e)))
```

**After:**

```python
except Exception as e:
    # 例外詳細はサーバーログのみに記録し、クライアントには定型メッセージを返す
    logging.error(f"Task error: {e}", exc_info=True)
    await queue.put(("error", MESSAGES["ERROR"]["API_ERROR"]))
```

### 手順1-4: テストの更新

例外文字列の素通しを前提にしていたテストが落ちるので、「詳細が**含まれない**こと」の検証に反転させる。

```python
assert result.error_message == MESSAGES["ERROR"]["API_ERROR"]
# 例外詳細はクライアントに返さない
assert "API接続エラー" not in result.error_message
```

更新対象になりやすいテスト:

- 例外ハンドラの単体テスト（`error_message == str(exc)` を検証しているもの）
- サービス層のAPI例外テスト（モック例外のメッセージが応答に含まれることを検証しているもの）
- SSEエラーイベントのテスト
- 422レスポンスに欠落フィールド名が含まれることを検証しているAPIテスト

---

## 改善2: 秘密鍵のデフォルトフォールバック廃止

### 手順2-1: デフォルト値を空にする

```python
# CSRF認証（未設定の場合は起動時にエラー）
csrf_secret_key: str = ""
```

### 手順2-2: 起動時バリデーションを追加

`get_settings()`（`@lru_cache` 付きのファクトリ）でチェックする。アプリ本体のモジュールが import 時に `get_settings()` を呼ぶ構成なら、これだけで「未設定なら起動失敗」になる。

```python
@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    if not settings.csrf_secret_key:
        raise RuntimeError(
            "CSRF_SECRET_KEY環境変数が設定されていません。アプリケーションを起動できません。"
        )
    return settings
```

`Settings` の `field_validator` でなく `get_settings()` でチェックする理由: テストコードが `patch.dict(os.environ, {...}, clear=True)` で `Settings()` を直接構築している場合、モデル側のバリデーションだと無関係なテストが大量に落ちる。起動経路である `get_settings()` に置けば影響範囲を最小化できる。

### 手順2-3: 全実行環境への環境変数設定を確認

`get_settings()` を import 時に呼ぶすべての経路が対象になる。漏れがちな箇所:

- CI のテストステップ（例: GitHub Actions の `env:` に `CSRF_SECRET_KEY: test-secret-key`）
- テストの conftest（autouse fixture で `monkeypatch.setenv("CSRF_SECRET_KEY", ...)`）
- **DBマイグレーション**（`alembic/env.py` が設定経由でDB URLを取得している場合、マイグレーション実行環境にも必要）
- 本番（ECSタスク定義等で Secrets Manager から注入されていることを確認）

### 手順2-4: テストの追加

```python
@patch.dict(os.environ, {"CSRF_SECRET_KEY": ""}, clear=True)
def test_get_settings_missing_csrf_secret_key_raises(self):
    """CSRF_SECRET_KEY 未設定なら get_settings が RuntimeError"""
    with pytest.raises(RuntimeError, match="CSRF_SECRET_KEY"):
        get_settings()
```

ポイント: `clear=True` だけでは pydantic-settings が `.env` ファイルを読んでしまうため、`CSRF_SECRET_KEY: ""` を**明示的に空で上書き**する（環境変数は `.env` より優先される）。`lru_cache` のクリア（`get_settings.cache_clear()`）を fixture で行うことも忘れない。

---

## 適用チェックリスト

- [ ] グローバル例外ハンドラ（500 / 422）が `str(exc)` を返していないか
- [ ] `grep -rn "error_message=str(e)" app/` がゼロ件か（監査ログはクラス名のみ）
- [ ] 外部API例外がクライアント応答（同期レスポンス / SSEイベント）に漏れていないか
- [ ] 例外詳細がサーバーログ（`exc_info=True`）に残るか（調査可能性の維持）
- [ ] 秘密鍵にデフォルト値がないか、未設定で起動が失敗するか
- [ ] CI・テスト・マイグレーション・本番の全環境に秘密鍵が設定されているか
- [ ] テストが「詳細を含まないこと」を検証する形に更新されているか
