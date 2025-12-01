#!/bin/bash
# CloudTrail Security Bot - CloudFormation 스택 삭제 스크립트

set -e

# 색상 정의
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# 기본값
STACK_NAME="cloudtrail-bot"
REGION="ap-northeast-2"

# 사용법
usage() {
    echo "Usage: $0 [options]"
    echo ""
    echo "Options:"
    echo "  -n, --stack-name    Stack name (default: cloudtrail-bot)"
    echo "  -r, --region        AWS Region (default: ap-northeast-2)"
    echo "  -y, --yes           Skip confirmation"
    echo "  -h, --help          Show this help message"
    exit 1
}

# 파라미터 파싱
SKIP_CONFIRM=false
while [[ $# -gt 0 ]]; do
    case $1 in
        -n|--stack-name)
            STACK_NAME="$2"
            shift 2
            ;;
        -r|--region)
            REGION="$2"
            shift 2
            ;;
        -y|--yes)
            SKIP_CONFIRM=true
            shift
            ;;
        -h|--help)
            usage
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            usage
            ;;
    esac
done

echo -e "${YELLOW}========================================${NC}"
echo -e "${YELLOW}CloudTrail Security Bot Stack Deletion${NC}"
echo -e "${YELLOW}========================================${NC}"
echo ""
echo -e "Stack Name: ${RED}${STACK_NAME}${NC}"
echo -e "Region:     ${RED}${REGION}${NC}"
echo ""

# 확인
if [ "$SKIP_CONFIRM" = false ]; then
    echo -e "${RED}WARNING: This will delete all resources in the stack!${NC}"
    read -p "Are you sure? (yes/no): " CONFIRM
    if [ "$CONFIRM" != "yes" ]; then
        echo "Cancelled."
        exit 0
    fi
fi

# 스택 삭제
echo -e "${YELLOW}Deleting CloudFormation stack...${NC}"

aws cloudformation delete-stack \
    --stack-name "${STACK_NAME}" \
    --region "${REGION}"

echo -e "${GREEN}Waiting for stack deletion to complete...${NC}"
aws cloudformation wait stack-delete-complete \
    --stack-name "${STACK_NAME}" \
    --region "${REGION}"

echo ""
echo -e "${GREEN}Stack deleted successfully!${NC}"

