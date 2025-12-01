# CloudTrail Security Bot 배포 가이드

이 문서는 CloudTrail Security Bot을 배포하고 Slack과 연동하는 방법을 설명합니다.

## 배포 아키텍처

### 권장 아키텍처: 하이브리드 방식

```
┌─────────────────────────────────────────────────────────────────┐
│                         AWS Cloud                                │
│  ┌──────────────────┐      ┌──────────────────────────────┐    │
│  │   Slack Bot      │      │    AgentCore Runtime         │    │
│  │   (EC2/ECS)      │─────►│    (Agent 로직)              │    │
│  │   Socket Mode    │      │    - CloudTrail 도구         │    │
│  └──────────────────┘      │    - Credential 획득         │    │
│           │                └──────────────────────────────┘    │
│           │                            │                        │
│           ▼                            ▼                        │
│  ┌──────────────────┐      ┌──────────────────────────────┐    │
│  │   Slack API      │      │    CloudTrail API            │    │
│  │   (WebSocket)    │      │    (대상 계정)               │    │
│  └──────────────────┘      └──────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
```

**장점:**
- Slack Bot은 안정적인 Socket Mode 사용
- Agent 로직은 AgentCore에서 관리형으로 실행
- 독립적인 스케일링 가능

---

## 1단계: AgentCore에 Agent 배포

### 1.1 사전 준비

```bash
# AgentCore CLI 설치
pip install bedrock-agentcore-starter-toolkit

# AWS CLI 설정 확인
aws sts get-caller-identity
```

### 1.2 AgentCore 배포

```bash
cd cloudtrail-bot

# AgentCore 설정
agentcore configure --entrypoint src/main.py --non-interactive

# 배포 (환경변수 포함)
agentcore deploy \
    --env ENV_TYPE=dev \
    --env AWS_REGION=ap-northeast-2 \
    --env USE_AGENTCORE=true
```

### 1.3 배포 확인

```bash
# 테스트 호출
agentcore invoke '{"prompt": "계정 검색 테스트"}'

# 엔드포인트 확인
agentcore status
```

배포 후 출력되는 **Runtime Endpoint URL**을 기록해두세요.

---

## 2단계: Slack Bot 서버 설정

AgentCore에 배포된 Agent를 호출하는 Slack Bot 서버를 설정합니다.

### 2.1 환경 변수 설정

`.env` 파일을 생성합니다:

```bash
# Slack 설정
SLACK_BOT_TOKEN=xoxb-your-bot-token
SLACK_APP_TOKEN=xapp-your-app-token

# AgentCore 연동 설정
USE_AGENTCORE_REMOTE=true
AGENTCORE_ENDPOINT=https://your-agentcore-endpoint.amazonaws.com

# AWS 설정
AWS_REGION=ap-northeast-2
ENV_TYPE=dev
```

### 2.2 로컬 테스트

```bash
# 의존성 설치
pip install -r requirements.txt

# Slack Bot 실행 (로컬)
python -m src.main
```

### 2.3 EC2/ECS 배포

#### EC2 배포 예시

```bash
# EC2 인스턴스에서
git clone <repository>
cd cloudtrail-bot

# 가상환경 설정
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 환경 변수 설정
cp .env.example .env
nano .env  # 값 입력

# systemd 서비스로 실행
sudo cp scripts/cloudtrail-bot.service /etc/systemd/system/
sudo systemctl enable cloudtrail-bot
sudo systemctl start cloudtrail-bot
```

#### Docker 배포 예시

```bash
# 이미지 빌드
docker build -t cloudtrail-bot:latest .

# 실행
docker run -d \
    --name cloudtrail-bot \
    --env-file .env \
    -e USE_AGENTCORE=false \
    -e USE_AGENTCORE_REMOTE=true \
    cloudtrail-bot:latest
```

---

## 3단계: Slack App 설정

[docs/SLACK_APP_SETUP.md](SLACK_APP_SETUP.md)를 참고하여 Slack App을 설정합니다.

### 핵심 설정 요약

1. **Socket Mode 활성화** - 외부 URL 없이 WebSocket 연결
2. **Event Subscriptions** - `app_mention` 이벤트 구독
3. **Bot Token Scopes** - `app_mentions:read`, `chat:write`, `channels:history`

---

## 4단계: 연동 테스트

### 4.1 Bot 상태 확인

```bash
# Slack Bot 로그 확인
tail -f /var/log/cloudtrail-bot.log

# 또는 Docker 로그
docker logs -f cloudtrail-bot
```

### 4.2 Slack에서 테스트

채널에 Bot을 추가하고 멘션합니다:

```
@CloudTrail Bot 안녕하세요
```

```
@CloudTrail Bot 계정 123456789012의 최근 활동을 조회해줘
```

---

## 배포 모드 비교

| 설정 | 설명 | 사용 시점 |
|------|------|----------|
| `USE_AGENTCORE=true` | AgentCore Runtime으로 실행 | AgentCore 배포 시 |
| `USE_AGENTCORE=false` + `USE_AGENTCORE_REMOTE=false` | 완전 로컬 실행 | 개발/테스트 |
| `USE_AGENTCORE=false` + `USE_AGENTCORE_REMOTE=true` | Slack Bot만 로컬, Agent는 AgentCore | 운영 권장 |

---

## 문제 해결

### AgentCore 연결 실패

```
❌ AgentCore 호출 중 오류가 발생했습니다
```

**해결:**
1. `AGENTCORE_ENDPOINT` 환경변수 확인
2. IAM 권한 확인 (bedrock-agent-runtime 호출 권한)
3. AgentCore 상태 확인: `agentcore status`

### Slack Bot 응답 없음

**해결:**
1. Socket Mode 활성화 확인
2. `SLACK_APP_TOKEN`, `SLACK_BOT_TOKEN` 확인
3. Bot이 채널에 추가되었는지 확인
4. Event Subscriptions에서 `app_mention` 구독 확인

### CloudTrail 조회 실패

```
❌ 계정 ID 'XXX'에 대한 자격증명을 획득할 수 없습니다
```

**해결:**
1. DB 연결 확인 (SSM Parameter Store 권한)
2. 계정 정보가 DB에 존재하는지 확인
3. Bridge Role 설정 확인

---

## IAM 권한 요약

### AgentCore 실행 역할

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "ssm:GetParameter"
            ],
            "Resource": "arn:aws:ssm:*:*:parameter/fitcloud/*"
        },
        {
            "Effect": "Allow",
            "Action": [
                "sts:AssumeRole"
            ],
            "Resource": "*"
        },
        {
            "Effect": "Allow",
            "Action": [
                "bedrock:InvokeModel"
            ],
            "Resource": "*"
        }
    ]
}
```

### Slack Bot 서버 역할 (원격 호출 시)

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "bedrock:InvokeAgent"
            ],
            "Resource": "arn:aws:bedrock:*:*:agent/*"
        }
    ]
}
```

