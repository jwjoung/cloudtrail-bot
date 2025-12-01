#!/bin/bash
# CloudTrail Security Bot - 로컬 실행 스크립트

set -e

echo "🚀 CloudTrail Security Bot 로컬 실행 시작..."

# .env 파일 로드
if [ -f .env ]; then
    echo "📋 .env 파일 로드 중..."
    export $(cat .env | grep -v '^#' | xargs)
fi

# 환경 변수 확인
if [ -z "$SLACK_BOT_TOKEN" ]; then
    echo "❌ SLACK_BOT_TOKEN 환경 변수가 설정되지 않았습니다."
    echo "💡 .env 파일을 생성하거나 환경 변수를 설정해주세요."
    exit 1
fi

if [ -z "$SLACK_APP_TOKEN" ]; then
    echo "❌ SLACK_APP_TOKEN 환경 변수가 설정되지 않았습니다."
    echo "💡 .env 파일을 생성하거나 환경 변수를 설정해주세요."
    exit 1
fi

# 기본값 설정
export ENV_TYPE=${ENV_TYPE:-dev}
export AWS_REGION=${AWS_REGION:-ap-northeast-2}
export USE_AGENTCORE=false

echo "📋 실행 설정:"
echo "  - 환경: $ENV_TYPE"
echo "  - 리전: $AWS_REGION"
echo "  - 모드: 독립 실행 (Socket Mode)"

# 가상환경 활성화 (있는 경우)
if [ -d ".venv" ]; then
    echo "📦 가상환경 활성화 중..."
    source .venv/bin/activate
elif [ -d "venv" ]; then
    echo "📦 가상환경 활성화 중..."
    source venv/bin/activate
fi

# 실행
echo "🤖 Bot 시작 중..."
python -m src.main

