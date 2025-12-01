#!/bin/bash
# CloudTrail Security Bot - AgentCore 배포 스크립트

set -e

echo "🚀 CloudTrail Security Bot 배포 시작..."

# 환경 변수 확인
if [ -z "$SLACK_BOT_TOKEN" ]; then
    echo "❌ SLACK_BOT_TOKEN 환경 변수가 설정되지 않았습니다."
    exit 1
fi

if [ -z "$SLACK_APP_TOKEN" ]; then
    echo "❌ SLACK_APP_TOKEN 환경 변수가 설정되지 않았습니다."
    exit 1
fi

# 기본값 설정
ENV_TYPE=${ENV_TYPE:-dev}
AWS_REGION=${AWS_REGION:-ap-northeast-2}

echo "📋 배포 설정:"
echo "  - 환경: $ENV_TYPE"
echo "  - 리전: $AWS_REGION"

# AgentCore CLI 확인
if ! command -v agentcore &> /dev/null; then
    echo "📦 AgentCore CLI 설치 중..."
    pip install bedrock-agentcore-starter-toolkit
fi

# AgentCore 설정
echo "⚙️ AgentCore 설정 중..."
agentcore configure \
    --entrypoint src/main.py \
    --non-interactive

# AgentCore 배포
echo "🚀 AgentCore에 배포 중..."
agentcore deploy \
    --env SLACK_BOT_TOKEN="$SLACK_BOT_TOKEN" \
    --env SLACK_APP_TOKEN="$SLACK_APP_TOKEN" \
    --env ENV_TYPE="$ENV_TYPE" \
    --env AWS_REGION="$AWS_REGION" \
    --env USE_AGENTCORE=true

echo "✅ 배포 완료!"
echo ""
echo "📝 테스트 명령어:"
echo '  agentcore invoke '\''{"prompt": "계정 검색 테스트"}'\'''

