# MediDocsSummaryセットアップガイド

## 前提条件

- AWSアカウント作成済み
- AWS CLIインストール済み・設定済み（`aws configure`）
- Dockerインストール済み
- MediDocsReferralのデプロイが完了していること（VPC、SG、RDS、ALB、IAMロールが作成済み）

---

## 既に準備済みのもの（コード変更不要）

| 項目 | ファイル | 状態 |
|---|---|---|
| Dockerイメージ定義 | `Dockerfile` | マルチステージビルド（Node.js + Python） |
| Dockerビルド除外設定 | `.dockerignore` | 設定済み |
| ECSタスク定義 | `ecs/task-definition.json` | `medidocs-summary` として設定済み |
| IAMポリシー定義 | `ecs/iam-policies.json` | Bedrock/Secrets Manager権限設定済み |
| デプロイスクリプト | `scripts/deploy.sh` | `medidocs-summary` 用に設定済み |
| ヘルスチェック | `app/main.py:157` | `GET /health` → `{"status": "healthy"}` |
| CORS設定 | `.env` | `https://summary.medidocslm.com/` 設定済み |

**Secrets Manager**: `medidocs/production` を Referral・Summary・Opinion で共有
**RDS DB**: `medidocs` を3アプリで共有（プロンプト情報・履歴も共有）

---

## STEP 0: AWSアカウントIDの確認

```bash
aws sts get-caller-identity --query Account --output text
```

出力された12桁の数字が `ACCOUNT_ID`。以降の手順では `149050210156` を使用。

---

## STEP 1: Referralをプライベートサブネットに移行

> Summaryデプロイ前に既存のReferralを移行して、全ECSサービスの構成を統一する

### 1-1. プライベートサブネットのルートテーブル確認

AWSコンソール → **VPC** → 「ルートテーブル」

プライベートサブネット用ルートテーブルに以下のルートが存在することを確認:

| 送信先 | ターゲット |
|---|---|
| `0.0.0.0/0` | NAT Gateway (`nat-xxxxxxxxx`) |

存在しない場合は「ルートを編集」で追加する。

### 1-2. Referral ECSサービスの更新

AWSコンソール → **ECS** → `medidocs-cluster` → `medidocs-referral-service` → 「更新」

**ネットワーキングを変更:**

| 項目 | 変更前 | 変更後 |
|---|---|---|
| サブネット | パブリックサブネット | **プライベートサブネット** (1a, 1c) |
| パブリックIP自動割り当て | ENABLED | **DISABLED** |

「更新」をクリック。タスクが新しいサブネットで起動するまで待機（3〜5分）。

### 1-3. Referral動作確認(院内ネットワークから)

```bash
curl https://referral.medidocslm.com/health
# {"status": "healthy"} が返ればOK
```

---

## STEP 2: Summary用のAWSリソース作成

### 2-1. ECRリポジトリの作成

AWSコンソール → **Elastic Container Registry** → 「リポジトリを作成」

| 項目 | 値 |
|---|---|
| 可視性設定 | **プライベート** |
| リポジトリ名 | `medidocs-summary` |
| タグのイミュータビリティ | 無効 |

「リポジトリを作成」をクリック。

次に、ライフサイクルポリシーを設定:

1. 作成したリポジトリ → 「ライフサイクルポリシー」 → 「ルールを作成」
2. 以下を設定:

| 項目 | 値 |
|---|---|
| ルールの優先順位 | `1` |
| ルールの説明 | 最新10件以外を削除 |
| イメージのステータス | タグ付き |
| タグパターン | `*` |
| 一致条件 | イメージ数が `10` を超えた場合 |
| アクション | 期限切れ |

### 2-2. CloudWatch Logsグループの作成

AWSコンソール → **CloudWatch** → 「ロググループ」 → 「ロググループを作成」

| 項目 | 値 |
|---|---|
| ロググループ名 | `/ecs/medidocs-summary` |
| 保持期間 | `30日` |

### 2-3. ターゲットグループの作成

AWSコンソール → **EC2** → 「ターゲットグループ」 → 「ターゲットグループを作成」

| 項目 | 値 |
|---|---|
| ターゲットタイプ | **IP アドレス** |
| ターゲットグループ名 | `medidocs-tg-summary` |
| プロトコル / ポート | HTTP / `8000` |
| VPC | `medidocs-vpc` |
| ヘルスチェックパス | `/health` |

「次へ」→ IPを登録せずに「ターゲットグループを作成」（ECSが自動登録）

### 2-4. ALBリスナールールの追加

AWSコンソール → **EC2** → 「ロードバランサー」 → `medidocs-alb` → 「リスナー」タブ → `HTTPS:443` → 「ルールの管理」

「ルールを追加」:

| 項目 | 値 |
|---|---|
| 条件タイプ | **ホストヘッダー** |
| 値 | `summary.medidocslm.com` |
| アクション | **転送** → `medidocs-tg-summary` |
| 優先度 | `2`（Referralルールより後、デフォルトより前） |

---

## STEP 3: Dockerイメージのビルドとプッシュ

```bash
# ACCOUNT_IDを設定（未設定の場合）
export ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

# ECRにログイン + ビルド + プッシュ
chmod +x scripts/deploy.sh
./scripts/deploy.sh
```

> 初回はECSサービスがまだ存在しないため、スクリプト末尾の `update-service` でエラーになる。
> エラーは無視してよい（STEP 4でサービスを作成する）。

---

## STEP 4: ECSタスク定義の登録

```bash
aws ecs register-task-definition \
  --cli-input-json file://ecs/task-definition.json \
  --region ap-northeast-1
```

AWSコンソールで確認: ECS → 「タスク定義」 → `medidocs-summary` が表示されればOK

---

## STEP 5: ECSサービスの作成

AWSコンソール → **ECS** → `medidocs-cluster` → 「サービスを作成」

**環境:**

| 項目 | 値 |
|---|---|
| コンピューティングオプション | **起動タイプ** |
| 起動タイプ | **FARGATE** |

**デプロイ設定:**

| 項目 | 値 |
|---|---|
| サービスタイプ | **サービス** |
| タスク定義 | `medidocs-summary` |
| リビジョン | 最新（1） |
| サービス名 | `medidocs-summary-service` |
| 必要なタスク | `1` |

**ヘルスチェックの猶予期間:** `60` 秒

**ネットワーキング:**

| 項目 | 値 |
|---|---|
| VPC | `medidocs-vpc` |
| サブネット | **プライベートサブネット** (ap-northeast-1a と 1c) |
| セキュリティグループ | `medidocs-sg-ecs` |
| パブリックIP | **DISABLED** |

**ロードバランシング:**

| 項目 | 値 |
|---|---|
| ロードバランサーのタイプ | **Application Load Balancer** |
| ロードバランサー | `medidocs-alb`（既存を使用） |
| コンテナ | `medidocs-summary:8000:8000` |
| リスナー | 既存のリスナーを使用 → `HTTPS:443` |
| ターゲットグループ | `medidocs-tg-summary`（既存を使用） |

「サービスを作成」をクリック。タスク起動〜ヘルスチェック通過まで3〜5分かかる。

---

## STEP 6: Route 53 DNSレコードの作成

AWSコンソール → **Route 53** → 「ホストゾーン」 → `medidocslm.com`

「レコードを作成」:

| 項目 | 値 |
|---|---|
| レコード名 | `summary` |
| レコードタイプ | **A** |
| エイリアス | **オン** |
| トラフィックのルーティング先 | **Application Load Balancerと Classic Load Balancerへのエイリアス** |
| リージョン | `ap-northeast-1` |
| ロードバランサー | `medidocs-alb` を選択 |

「レコードを作成」をクリック。DNS伝播まで数分かかる。

---

## STEP 7: DBマイグレーションは不要

DBは `medidocs` を共有しているため、Referralデプロイ時に既存テーブルが作成済み。

## STEP 8: 動作確認チェックリスト

```bash
# ヘルスチェック
curl https://summary.medidocslm.com/health
# {"status": "healthy"} が返ればOK
```

- [ ] `https://summary.medidocslm.com/health` → `{"status": "healthy"}`
- [ ] メインページが表示される
- [ ] Claude (Amazon Bedrock) でサマリ生成が動作する
- [ ] Gemini (Vertex AI) でサマリ生成が動作する
- [ ] SSEストリーミングが途中で切断されない（ALBタイムアウト: 120秒）
- [ ] 院内固定IP以外からのアクセスが拒否される（403/接続拒否）
- [ ] Referralも引き続き正常動作する（プライベートサブネット移行後）

---

## 以降のデプロイ（2回目以降）

コード変更後のデプロイは deploy.sh を実行するだけ:

```bash
./scripts/deploy.sh
```

---

## 将来: MediDocsOpinionの追加

同じ手順で追加可能。差分は以下のみ:

| 項目 | 値 |
|---|---|
| ECRリポジトリ名 | `medidocs-opinion` |
| CloudWatch Logsグループ | `/ecs/medidocs-opinion` |
| ターゲットグループ名 | `medidocs-tg-opinion` |
| ALBルーティング条件 | `opinion.medidocslm.com` |
| ECSサービス名 | `medidocs-opinion-service` |
| Route 53レコード名 | `opinion` |
