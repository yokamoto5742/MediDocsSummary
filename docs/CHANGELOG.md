# Changelog

このプロジェクトのすべての変更は、このファイルに記録されます。

フォーマットは [Keep a Changelog](https://keepachangelog.com/ja/1.0.0/) に基づき、
このプロジェクトは [Semantic Versioning](https://semver.org/lang/ja/) に準拠しています。

## [Unreleased]

## [1.0.1] - 2026-03-09

### 追加

- **日次利用制限機能**: ユーザーごとの日次 API 利用回数に上限を設定する機能を実装
- **テストカバレッジ拡充**: CSRF トークンの期限切れ・無効・欠落ケースのテスト、セキュリティヘッダーテストを追加
- **評価プロンプトテスト強化**: セクション順序・複数行コンテンツの検証テストを実装
- **バリデーション・エラーハンドリングテスト**: `_validate_and_get_prompt` の各種エラー条件テスト、サマリサービスの入力検証テスト（最小文字数・プロンプトインジェクション検出）を追加
- **モデルセレクタテスト**: DB 障害時フォールバックテスト、Claude/Gemini モデル設定不足時のテストを実装

### 変更

- **UI テンプレート**: 成功ボタンの表示条件を改善し、条件付き表示に対応

### 削除

- **不要なテストコード**: `execute_evaluation`、`execute_evaluation_stream`、`execute_summary_generation` の不要なテストを削除

### 修正

- **依存関係**: grpcio を 1.78.0 に更新

## [1.0.0] - 2026-03-01

### 追加

- **AI プロバイダー対応**: Claude（AWS Bedrock）と Gemini（Google Vertex AI）の両プロバイダーをサポート。入力文字数に応じた自動モデル選択機能を実装
- **階層的プロンプト解決**: 診療科・医師・文書タイプ別のプロンプト管理システムを導入。フォールバックロジックで柔軟に対応
- **SSE ストリーミング**: Server-Sent Events による AI 出力のリアルタイムストリーミング返却機能
- **セクション分割機能**: AI 出力を自動的に複数セクションに分割し、構造化されたサマリを生成
- **セキュリティ機能**: CSRF 保護、入力サニタイゼーション、セキュリティヘッダー、監査ログ機能を実装
- **使用統計追跡**: トークン数・処理時間・コスト計算を記録し、`usage` テーブルで管理
- **データベースマイグレーション**: Alembic を使用した段階的なスキーマ管理に対応
- **テスト体制**: 各レイヤーの単体テストと統合テストをカバレッジ管理で実装

### 変更

- **API ファクトリーパターン**: `app/external/api_factory.py` で AI クライアントを動的生成し、プロバイダー切り替えを容易化
- **設定管理の統一**: Pydantic Settings で`.env` ファイル、OS 環境変数、AWS Secrets Manager を統一的に管理
- **定数管理の一元化**: UI メッセージを `app/core/constants.py` で一元管理し、ハードコード化を排除
- **アーキテクチャ層の分離**: API 層・Service 層・External 層・Model 層の責任を明確に分離
- **テストモック体制**: Claude API テストで`get_prompt` と`get_db_session` のモック元を修正し、テスト信頼性を向上

### 削除

- **Cloudflare Gemini API**: サポート対象を Google Vertex AI のみに統一し、Cloudflare 実装を削除
- **セットアップドキュメント**: 旧プロジェクト（MediDocsReferral）関連の`MediDocsReferral_setup.md` と`MediDocsSummary_setup.md` を削除

### 修正

- **テストフィクスチャ**: `test_summary_service.py` の`app_type` を "dischargesummary" に修正し、テスト連携を正常化
- **README ドキュメント**: 不要な設定項目を削除し、ドキュメント品質を改善
- **依存関係**: requirements.txt を更新し、最新のライブラリバージョンに対応

[Unreleased]: https://github.com/yourusername/MediDocsSummary/compare/v1.0.1...HEAD
[1.0.1]: https://github.com/yourusername/MediDocsSummary/compare/v1.0.0...v1.0.1
[1.0.0]: https://github.com/yourusername/MediDocsSummary/releases/tag/v1.0.0
