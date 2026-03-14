#!/bin/bash
set -e

echo "Setting up RDS automation for cost optimization..."

# 環境変数の設定
export AWS_DEFAULT_REGION=ap-northeast-1
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

echo "Account ID: $ACCOUNT_ID"
echo "Region: $AWS_DEFAULT_REGION"
echo "----------------------------------------"

# 一時ファイルを削除するための関数
cleanup() {
    echo "Cleaning up temporary JSON files..."
    rm -f trust-policy.json rds-control-policy.json rds-stop-document.json rds-start-document.json eventbridge-trust-policy.json eventbridge-ssm-policy.json stop-targets.json start-targets.json
    echo "Cleanup completed."
}

# 実行終了時（成功・失敗問わず）にクリーンアップを実行
trap cleanup EXIT

# ステップ1: IAMロールの作成
step1_create_iam_roles() {
    echo "[Step 1] Creating IAM Role for RDS Automation..."

    # 1-1. 信頼ポリシーファイルの作成
    cat > trust-policy.json << 'EOF'
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Principal": {
                "Service": "ssm.amazonaws.com"
            },
            "Action": "sts:AssumeRole"
        }
    ]
}
EOF

    # 1-2. RDS制御ポリシーファイルの作成
    cat > rds-control-policy.json << 'EOF'
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "rds:StopDBInstance",
                "rds:StartDBInstance",
                "rds:DescribeDBInstances"
            ],
            "Resource": [
                "arn:aws:rds:ap-northeast-1:*:db:medidocs-db"
            ]
        },
        {
            "Effect": "Allow",
            "Action": [
                "logs:CreateLogGroup",
                "logs:CreateLogStream",
                "logs:PutLogEvents"
            ],
            "Resource": "*"
        }
    ]
}
EOF

    # 1-3. IAMロールとポリシーの作成 (既存の場合はスキップ)
    aws iam create-role \
        --role-name RDS-Automation-Role \
        --assume-role-policy-document file://trust-policy.json \
        --description "Role for RDS automation via Systems Manager" > /dev/null 2>&1 || echo " - Role 'RDS-Automation-Role' already exists, skipping creation."

    aws iam create-policy \
        --policy-name RDS-Control-Policy \
        --policy-document file://rds-control-policy.json \
        --description "Policy for RDS start/stop operations" > /dev/null 2>&1 || echo " - Policy 'RDS-Control-Policy' already exists, skipping creation."

    aws iam attach-role-policy \
        --role-name RDS-Automation-Role \
        --policy-arn arn:aws:iam::${ACCOUNT_ID}:policy/RDS-Control-Policy > /dev/null 2>&1 || true

    aws iam attach-role-policy \
        --role-name RDS-Automation-Role \
        --policy-arn arn:aws:iam::aws:policy/service-role/AmazonSSMAutomationRole > /dev/null 2>&1 || true

    echo "IAM Role 'RDS-Automation-Role' setup completed."
    echo "Waiting for IAM propagation (10 seconds)..."
    sleep 10
}

# ステップ2: Automation Documentの作成
step2_create_ssm_documents() {
    echo "[Step 2] Creating SSM Automation Documents..."

    # 2-1. RDS停止用Documentの作成
    cat > rds-stop-document.json << 'EOF'
{
    "schemaVersion": "0.3",
    "description": "Stop RDS instance for cost optimization",
    "assumeRole": "{{ AutomationAssumeRole }}",
    "parameters": {
        "InstanceId": {
            "type": "String",
            "description": "RDS Instance Identifier",
            "default": "medidocs-db"
        },
        "AutomationAssumeRole": {
            "type": "String",
            "description": "IAM role for automation",
            "default": "arn:aws:iam::{{ global:ACCOUNT_ID }}:role/RDS-Automation-Role"
        }
    },
    "mainSteps": [
        {
            "name": "CheckInstanceStatus",
            "action": "aws:executeAwsApi",
            "inputs": {
                "Service": "rds",
                "Api": "DescribeDBInstances",
                "DBInstanceIdentifier": "{{ InstanceId }}"
            },
            "outputs": [
                {
                    "Name": "InstanceStatus",
                    "Selector": "$.DBInstances[0].DBInstanceStatus",
                    "Type": "String"
                }
            ]
        },
        {
            "name": "BranchOnStatus",
            "action": "aws:branch",
            "inputs": {
                "Choices": [
                    {
                        "NextStep": "StopRDSInstance",
                        "Variable": "{{ CheckInstanceStatus.InstanceStatus }}",
                        "StringEquals": "available"
                    }
                ],
                "Default": "SkipStop"
            }
        },
        {
            "name": "StopRDSInstance",
            "action": "aws:executeAwsApi",
            "inputs": {
                "Service": "rds",
                "Api": "StopDBInstance",
                "DBInstanceIdentifier": "{{ InstanceId }}"
            },
            "isEnd": true
        },
        {
            "name": "SkipStop",
            "action": "aws:sleep",
            "inputs": {
                "Duration": "PT1S"
            },
            "isEnd": true
        }
    ]
}
EOF

    aws ssm create-document \
        --name "RDS-Stop-Automation" \
        --document-type "Automation" \
        --document-format JSON \
        --content file://rds-stop-document.json \
        --tags Key=Purpose,Value=CostOptimization Key=Resource,Value=medidocs-db > /dev/null 2>&1 || echo " - Document 'RDS-Stop-Automation' already exists, skipping."

    # 2-2. RDS開始用Documentの作成
    cat > rds-start-document.json << 'EOF'
{
    "schemaVersion": "0.3",
    "description": "Start RDS instance",
    "assumeRole": "{{ AutomationAssumeRole }}",
    "parameters": {
        "InstanceId": {
            "type": "String",
            "description": "RDS Instance Identifier",
            "default": "medidocs-db"
        },
        "AutomationAssumeRole": {
            "type": "String",
            "description": "IAM role for automation",
            "default": "arn:aws:iam::{{ global:ACCOUNT_ID }}:role/RDS-Automation-Role"
        }
    },
    "mainSteps": [
        {
            "name": "CheckInstanceStatus",
            "action": "aws:executeAwsApi",
            "inputs": {
                "Service": "rds",
                "Api": "DescribeDBInstances",
                "DBInstanceIdentifier": "{{ InstanceId }}"
            },
            "outputs": [
                {
                    "Name": "InstanceStatus",
                    "Selector": "$.DBInstances[0].DBInstanceStatus",
                    "Type": "String"
                }
            ]
        },
        {
            "name": "BranchOnStatus",
            "action": "aws:branch",
            "inputs": {
                "Choices": [
                    {
                        "NextStep": "StartRDSInstance",
                        "Variable": "{{ CheckInstanceStatus.InstanceStatus }}",
                        "StringEquals": "stopped"
                    }
                ],
                "Default": "SkipStart"
            }
        },
        {
            "name": "StartRDSInstance",
            "action": "aws:executeAwsApi",
            "inputs": {
                "Service": "rds",
                "Api": "StartDBInstance",
                "DBInstanceIdentifier": "{{ InstanceId }}"
            },
            "isEnd": true
        },
        {
            "name": "SkipStart",
            "action": "aws:sleep",
            "inputs": {
                "Duration": "PT1S"
            },
            "isEnd": true
        }
    ]
}
EOF

    aws ssm create-document \
        --name "RDS-Start-Automation" \
        --document-type "Automation" \
        --document-format JSON \
        --content file://rds-start-document.json \
        --tags Key=Purpose,Value=CostOptimization Key=Resource,Value=medidocs-db > /dev/null 2>&1 || echo " - Document 'RDS-Start-Automation' already exists, skipping."

    echo "SSM Documents setup completed."
}

# ステップ3: EventBridgeルールの作成
step3_create_eventbridge_rules() {
    echo "[Step 3] Creating EventBridge Rules..."

    # 3-1. EventBridge用IAMロールの作成
    cat > eventbridge-trust-policy.json << 'EOF'
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Principal": {
                "Service": "events.amazonaws.com"
            },
            "Action": "sts:AssumeRole"
        }
    ]
}
EOF

    cat > eventbridge-ssm-policy.json << 'EOF'
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "ssm:StartAutomationExecution"
            ],
            "Resource": [
                "arn:aws:ssm:ap-northeast-1:*:automation-definition/RDS-Stop-Automation:*",
                "arn:aws:ssm:ap-northeast-1:*:automation-definition/RDS-Start-Automation:*"
            ]
        },
        {
            "Effect": "Allow",
            "Action": [
                "iam:PassRole"
            ],
            "Resource": "arn:aws:iam::*:role/RDS-Automation-Role"
        }
    ]
}
EOF

    aws iam create-role \
        --role-name EventBridge-SSM-Role \
        --assume-role-policy-document file://eventbridge-trust-policy.json > /dev/null 2>&1 || echo " - Role 'EventBridge-SSM-Role' already exists, skipping creation."

    aws iam create-policy \
        --policy-name EventBridge-SSM-Policy \
        --policy-document file://eventbridge-ssm-policy.json > /dev/null 2>&1 || echo " - Policy 'EventBridge-SSM-Policy' already exists, skipping creation."

    aws iam attach-role-policy \
        --role-name EventBridge-SSM-Role \
        --policy-arn arn:aws:iam::${ACCOUNT_ID}:policy/EventBridge-SSM-Policy > /dev/null 2>&1 || true

    echo "Waiting for EventBridge IAM propagation (10 seconds)..."
    sleep 10

    # 3-2. EventBridgeルールの作成
    aws events put-rule \
        --name "RDS-Stop-Schedule" \
        --schedule-expression "cron(0 9 ? * MON-FRI *)" \
        --description "Stop RDS instance on weekdays at 6 PM JST" \
        --state ENABLED > /dev/null

    aws events put-rule \
        --name "RDS-Start-Schedule" \
        --schedule-expression "cron(0 0 ? * MON-FRI *)" \
        --description "Start RDS instance on weekdays at 9 AM JST" \
        --state ENABLED > /dev/null

    # --- ターゲット用JSONファイルの作成 (CLI解析エラー回避) ---
    # 変数を展開するため EOF はクォートで囲みません
    cat > stop-targets.json << EOF
[
    {
        "Id": "1",
        "Arn": "arn:aws:ssm:ap-northeast-1:${ACCOUNT_ID}:automation-definition/RDS-Stop-Automation",
        "RoleArn": "arn:aws:iam::${ACCOUNT_ID}:role/EventBridge-SSM-Role",
        "Input": "{\"InstanceId\":[\"medidocs-db\"],\"AutomationAssumeRole\":[\"arn:aws:iam::${ACCOUNT_ID}:role/RDS-Automation-Role\"]}"
    }
]
EOF

    cat > start-targets.json << EOF
[
    {
        "Id": "1",
        "Arn": "arn:aws:ssm:ap-northeast-1:${ACCOUNT_ID}:automation-definition/RDS-Start-Automation",
        "RoleArn": "arn:aws:iam::${ACCOUNT_ID}:role/EventBridge-SSM-Role",
        "Input": "{\"InstanceId\":[\"medidocs-db\"],\"AutomationAssumeRole\":[\"arn:aws:iam::${ACCOUNT_ID}:role/RDS-Automation-Role\"]}"
    }
]
EOF

    # JSONファイルを読み込んでターゲットを設定
    aws events put-targets \
        --rule "RDS-Stop-Schedule" \
        --targets file://stop-targets.json > /dev/null

    aws events put-targets \
        --rule "RDS-Start-Schedule" \
        --targets file://start-targets.json > /dev/null

    echo "EventBridge Rules and Targets setup completed."
}

# --- メイン実行処理 ---
step1_create_iam_roles
step2_create_ssm_documents
step3_create_eventbridge_rules

echo "----------------------------------------"
echo "RDS automation setup completed successfully!"