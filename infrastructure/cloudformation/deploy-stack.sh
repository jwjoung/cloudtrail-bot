#!/bin/bash
# CloudTrail Security Bot - CloudFormation 배포 스크립트

set -e

# 색상 정의
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 기본값
STACK_NAME="cloudtrail-bot"
REGION="ap-northeast-2"
ENV_TYPE="dev"
INSTANCE_TYPE="t3.small"

# 사용법 출력
usage() {
    echo "Usage: $0 [options]"
    echo ""
    echo "Options:"
    echo "  -n, --stack-name      Stack name (default: cloudtrail-bot)"
    echo "  -r, --region          AWS Region (default: ap-northeast-2)"
    echo "  -e, --env-type        Environment type: dev|stg|prd (default: dev)"
    echo "  -v, --vpc-id          VPC ID (required)"
    echo "  -s, --subnet-id       Subnet ID (required)"
    echo "  -k, --key-pair        EC2 Key Pair name (optional)"
    echo "  -i, --instance-type   EC2 Instance type (default: t3.small)"
    echo "  --bot-token           Slack Bot Token (or set SLACK_BOT_TOKEN env var)"
    echo "  --app-token           Slack App Token (or set SLACK_APP_TOKEN env var)"
    echo "  --git-repo            Git repository URL for source code"
    echo "  --s3-bucket           S3 bucket for source code"
    echo "  -h, --help            Show this help message"
    echo ""
    echo "Example:"
    echo "  $0 -v vpc-12345678 -s subnet-12345678 --bot-token xoxb-... --app-token xapp-..."
    exit 1
}

# 파라미터 파싱
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
        -e|--env-type)
            ENV_TYPE="$2"
            shift 2
            ;;
        -v|--vpc-id)
            VPC_ID="$2"
            shift 2
            ;;
        -s|--subnet-id)
            SUBNET_ID="$2"
            shift 2
            ;;
        -k|--key-pair)
            KEY_PAIR="$2"
            shift 2
            ;;
        -i|--instance-type)
            INSTANCE_TYPE="$2"
            shift 2
            ;;
        --bot-token)
            SLACK_BOT_TOKEN="$2"
            shift 2
            ;;
        --app-token)
            SLACK_APP_TOKEN="$2"
            shift 2
            ;;
        --git-repo)
            GIT_REPO="$2"
            shift 2
            ;;
        --s3-bucket)
            S3_BUCKET="$2"
            shift 2
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

# 필수 파라미터 확인
if [ -z "$VPC_ID" ]; then
    echo -e "${RED}Error: VPC ID is required${NC}"
    usage
fi

if [ -z "$SUBNET_ID" ]; then
    echo -e "${RED}Error: Subnet ID is required${NC}"
    usage
fi

if [ -z "$SLACK_BOT_TOKEN" ]; then
    echo -e "${RED}Error: Slack Bot Token is required${NC}"
    echo "Set with --bot-token or SLACK_BOT_TOKEN environment variable"
    exit 1
fi

if [ -z "$SLACK_APP_TOKEN" ]; then
    echo -e "${RED}Error: Slack App Token is required${NC}"
    echo "Set with --app-token or SLACK_APP_TOKEN environment variable"
    exit 1
fi

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}CloudTrail Security Bot Deployment${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "Stack Name:    ${YELLOW}${STACK_NAME}${NC}"
echo -e "Region:        ${YELLOW}${REGION}${NC}"
echo -e "Environment:   ${YELLOW}${ENV_TYPE}${NC}"
echo -e "VPC ID:        ${YELLOW}${VPC_ID}${NC}"
echo -e "Subnet ID:     ${YELLOW}${SUBNET_ID}${NC}"
echo -e "Instance Type: ${YELLOW}${INSTANCE_TYPE}${NC}"
echo ""

# CloudFormation 파라미터 구성
PARAMS="ParameterKey=VpcId,ParameterValue=${VPC_ID}"
PARAMS="${PARAMS} ParameterKey=SubnetId,ParameterValue=${SUBNET_ID}"
PARAMS="${PARAMS} ParameterKey=InstanceType,ParameterValue=${INSTANCE_TYPE}"
PARAMS="${PARAMS} ParameterKey=SlackBotToken,ParameterValue=${SLACK_BOT_TOKEN}"
PARAMS="${PARAMS} ParameterKey=SlackAppToken,ParameterValue=${SLACK_APP_TOKEN}"
PARAMS="${PARAMS} ParameterKey=EnvironmentType,ParameterValue=${ENV_TYPE}"

if [ -n "$KEY_PAIR" ]; then
    PARAMS="${PARAMS} ParameterKey=KeyPairName,ParameterValue=${KEY_PAIR}"
fi

if [ -n "$GIT_REPO" ]; then
    PARAMS="${PARAMS} ParameterKey=GitRepoUrl,ParameterValue=${GIT_REPO}"
fi

if [ -n "$S3_BUCKET" ]; then
    PARAMS="${PARAMS} ParameterKey=S3BucketName,ParameterValue=${S3_BUCKET}"
fi

# 스택 존재 여부 확인
STACK_EXISTS=$(aws cloudformation describe-stacks --stack-name "${STACK_NAME}" --region "${REGION}" 2>&1 || true)

if echo "${STACK_EXISTS}" | grep -q "does not exist"; then
    echo -e "${GREEN}Creating new stack...${NC}"
    ACTION="create-stack"
    WAIT_ACTION="stack-create-complete"
else
    echo -e "${YELLOW}Updating existing stack...${NC}"
    ACTION="update-stack"
    WAIT_ACTION="stack-update-complete"
fi

# 스택 배포
echo -e "${GREEN}Deploying CloudFormation stack...${NC}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

aws cloudformation ${ACTION} \
    --stack-name "${STACK_NAME}" \
    --template-body "file://${SCRIPT_DIR}/cloudtrail-bot-stack.yaml" \
    --parameters ${PARAMS} \
    --capabilities CAPABILITY_NAMED_IAM \
    --region "${REGION}" \
    --tags Key=Application,Value=cloudtrail-bot Key=Environment,Value=${ENV_TYPE}

echo -e "${GREEN}Waiting for stack to complete...${NC}"
aws cloudformation wait ${WAIT_ACTION} \
    --stack-name "${STACK_NAME}" \
    --region "${REGION}"

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Deployment Complete!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# 출력값 표시
echo -e "${YELLOW}Stack Outputs:${NC}"
aws cloudformation describe-stacks \
    --stack-name "${STACK_NAME}" \
    --region "${REGION}" \
    --query 'Stacks[0].Outputs[*].[OutputKey,OutputValue]' \
    --output table

echo ""
echo -e "${GREEN}Next Steps:${NC}"
echo "1. SSH into the instance to verify the bot is running"
echo "2. Check service status: sudo systemctl status cloudtrail-bot"
echo "3. View logs: sudo journalctl -u cloudtrail-bot -f"
echo ""
echo "If source code was not provided, deploy manually:"
echo "  scp -r src/ ec2-user@<instance-ip>:/opt/cloudtrail-bot/"
echo "  ssh ec2-user@<instance-ip> 'sudo systemctl restart cloudtrail-bot'"

