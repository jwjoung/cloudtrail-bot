# CloudTrail Security Bot - CloudFormation 배포

이 디렉토리에는 CloudTrail Security Bot을 AWS에 배포하기 위한 CloudFormation 템플릿이 포함되어 있습니다.

## 아키텍처

```
┌─────────────────────────────────────────────────────────────┐
│                        AWS Cloud                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │                    Your VPC                          │   │
│  │  ┌─────────────────────────────────────────────┐   │   │
│  │  │              Your Subnet                     │   │   │
│  │  │  ┌───────────────────────────────────────┐ │   │   │
│  │  │  │         EC2 Instance                   │ │   │   │
│  │  │  │  ┌─────────────────────────────────┐ │ │   │   │
│  │  │  │  │   CloudTrail Security Bot       │ │ │   │   │
│  │  │  │  │   - Slack Bot (Socket Mode)     │ │ │   │   │
│  │  │  │  │   - Strands Agent               │ │ │   │   │
│  │  │  │  └─────────────────────────────────┘ │ │   │   │
│  │  │  └───────────────────────────────────────┘ │   │   │
│  │  └─────────────────────────────────────────────┘   │   │
│  └─────────────────────────────────────────────────────┘   │
│                            │                                │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐    │
│  │ SSM Param   │    │  Bedrock    │    │ CloudTrail  │    │
│  │ Store       │    │  (Claude)   │    │   API       │    │
│  └─────────────┘    └─────────────┘    └─────────────┘    │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
                    ┌─────────────┐
                    │  Slack API  │
                    │ (WebSocket) │
                    └─────────────┘
```

## 생성되는 리소스

| 리소스 | 설명 |
|--------|------|
| EC2 Instance | Slack Bot 실행 (Amazon Linux 2023) |
| Security Group | 인바운드: SSH(22), 아웃바운드: All |
| IAM Role | SSM, STS, Bedrock, CloudWatch 권한 |
| SSM Parameters | Slack 토큰 저장 |
| CloudWatch Log Group | 애플리케이션 로그 |

## 사전 요구 사항

1. **AWS CLI** 설치 및 설정
2. **Slack App** 생성 완료 (Bot Token, App Token)
3. **VPC 및 Subnet** - 인터넷 접근 가능한 서브넷
4. **EC2 Key Pair** (선택사항 - SSH 접속용)

## 빠른 시작

### 1. 스크립트로 배포

```bash
# 실행 권한 부여
chmod +x deploy-stack.sh

# 배포 실행
./deploy-stack.sh \
    --vpc-id vpc-xxxxxxxxx \
    --subnet-id subnet-xxxxxxxxx \
    --bot-token "xoxb-your-bot-token" \
    --app-token "xapp-your-app-token" \
    --key-pair your-key-pair
```

### 2. AWS CLI로 직접 배포

```bash
aws cloudformation create-stack \
    --stack-name cloudtrail-bot \
    --template-body file://cloudtrail-bot-stack.yaml \
    --parameters file://parameters.json \
    --capabilities CAPABILITY_NAMED_IAM \
    --region ap-northeast-2
```

### 3. AWS Console에서 배포

1. AWS CloudFormation 콘솔 접속
2. "Create stack" → "With new resources"
3. "Upload a template file" 선택 후 `cloudtrail-bot-stack.yaml` 업로드
4. 파라미터 입력
5. "Create stack" 클릭

## 파라미터 설명

| 파라미터 | 필수 | 기본값 | 설명 |
|----------|------|--------|------|
| VpcId | ✅ | - | EC2를 배치할 VPC ID |
| SubnetId | ✅ | - | EC2를 배치할 Subnet ID |
| InstanceType | | t3.small | EC2 인스턴스 타입 |
| KeyPairName | | - | SSH 접속용 Key Pair |
| SlackBotToken | ✅ | - | Slack Bot Token (xoxb-...) |
| SlackAppToken | ✅ | - | Slack App Token (xapp-...) |
| EnvironmentType | | dev | 환경 타입 (dev/stg/prd) |
| UseAgentCoreRemote | | false | AgentCore 원격 호출 사용 |
| AgentCoreEndpoint | | - | AgentCore 엔드포인트 URL |
| GitRepoUrl | | - | 소스 코드 Git 저장소 URL |
| S3BucketName | | - | 소스 코드 S3 버킷 |

## 소스 코드 배포 옵션

### 옵션 1: Git 저장소

```bash
./deploy-stack.sh \
    --vpc-id vpc-xxx \
    --subnet-id subnet-xxx \
    --bot-token "xoxb-..." \
    --app-token "xapp-..." \
    --git-repo "https://github.com/your-org/cloudtrail-bot.git"
```

### 옵션 2: S3 버킷

```bash
# 먼저 소스 코드를 S3에 업로드
aws s3 sync . s3://your-bucket/cloudtrail-bot/ --exclude ".git/*" --exclude ".venv/*"

# 배포
./deploy-stack.sh \
    --vpc-id vpc-xxx \
    --subnet-id subnet-xxx \
    --bot-token "xoxb-..." \
    --app-token "xapp-..." \
    --s3-bucket your-bucket
```

### 옵션 3: 수동 배포

스택 생성 후 직접 소스 코드 복사:

```bash
# 로컬에서 EC2로 복사
scp -i your-key.pem -r src/ requirements.txt ec2-user@<instance-ip>:/opt/cloudtrail-bot/

# EC2에서 서비스 재시작
ssh -i your-key.pem ec2-user@<instance-ip> 'sudo systemctl restart cloudtrail-bot'
```

## 배포 후 확인

### 서비스 상태 확인

```bash
ssh -i your-key.pem ec2-user@<instance-ip>

# 서비스 상태
sudo systemctl status cloudtrail-bot

# 로그 확인
sudo journalctl -u cloudtrail-bot -f
```

### Slack에서 테스트

채널에 Bot을 추가하고 멘션:
```
@CloudTrail Bot 안녕하세요
```

## 스택 삭제

```bash
./delete-stack.sh --stack-name cloudtrail-bot --yes
```

또는:

```bash
aws cloudformation delete-stack \
    --stack-name cloudtrail-bot \
    --region ap-northeast-2
```

## 문제 해결

### Bot이 시작되지 않음

```bash
# UserData 스크립트 로그 확인
sudo cat /var/log/user-data.log

# 서비스 로그 확인
sudo journalctl -u cloudtrail-bot --no-pager -n 100
```

### Slack 연결 실패

1. Security Group 아웃바운드 규칙 확인 (모든 트래픽 허용 필요)
2. Subnet이 인터넷 접근 가능한지 확인 (NAT Gateway 또는 IGW)
3. SSM Parameter Store에서 토큰 값 확인

### AWS API 호출 실패

1. IAM Role 권한 확인
2. VPC Endpoint 설정 확인 (Private Subnet인 경우)

## 비용 예상

| 리소스 | 예상 월 비용 (ap-northeast-2) |
|--------|------------------------------|
| t3.small EC2 (24/7) | ~$15-20 |
| EBS (20GB gp3) | ~$2 |
| CloudWatch Logs | ~$1 |
| **Total** | **~$18-23/month** |

> 참고: 실제 비용은 사용량에 따라 다를 수 있습니다.

