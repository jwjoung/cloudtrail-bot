# CloudTrail Security Bot 🛡️

AWS CloudTrail 이벤트를 자연어로 조회하고 보안 상태를 분석하는 Slack 챗봇입니다.

## 주요 기능

- 📊 **CloudTrail 이벤트 조회**: 특정 AWS 계정의 API 활동을 자연어로 조회
- 🔐 **콘솔 로그인 모니터링**: 로그인 성공/실패, IP 주소, MFA 사용 여부 확인
- ⚠️ **에러 이벤트 분석**: 권한 거부, API 호출 실패 등 파악
- 🛡️ **종합 보안 분석**: IAM 변경, 보안 그룹 수정, 루트 활동 등 분석
- 💬 **스레드 기반 대화**: Bot 멘션 메시지의 스레드에서 연속 대화

## 아키텍처

```
Slack Channel → @Bot 멘션 (계정명 포함)
       ↓
Slack Bolt App (Socket Mode)
       ↓
Strands Agent (Bedrock Claude)
       ↓
┌─────────────────────────────────┐
│ 1. DB에서 계정 정보 조회         │
│ 2. Bridge Role Chaining         │
│ 3. 대상 계정 Credential 획득    │
└─────────────────────────────────┘
       ↓
CloudTrail API (대상 계정)
```

## 빠른 시작

### 1. 의존성 설치

```bash
# 가상환경 생성 (권장)
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# 의존성 설치
pip install -r requirements.txt
```

### 2. 환경 변수 설정

`.env.example`을 복사하여 `.env` 파일을 생성하고 값을 설정합니다:

```bash
cp .env.example .env
```

```env
# Slack Configuration
SLACK_BOT_TOKEN=xoxb-your-bot-token-here
SLACK_APP_TOKEN=xapp-your-app-token-here

# AWS Configuration
ENV_TYPE=dev
AWS_REGION=ap-northeast-2
```

### 3. Slack App 설정

[docs/SLACK_APP_SETUP.md](docs/SLACK_APP_SETUP.md)를 참고하여 Slack App을 생성하고 설정합니다.

### 4. 로컬 실행

```bash
# Linux/Mac
./scripts/run_local.sh

# Windows
scripts\run_local.bat

# 또는 직접 실행
python -m src.main
```

## 사용 방법

채널에서 Bot을 멘션하여 질문합니다:

```
@CloudTrail Bot 계정 123456789012의 최근 활동을 조회해줘
```

```
@CloudTrail Bot 어제 콘솔 로그인 기록을 확인해줘
```

```
@CloudTrail Bot 보안 분석을 해줘
```

```
@CloudTrail Bot ABC회사 계정을 검색해줘
```

## 배포

### 로컬 개발 모드

Slack Bot과 Agent를 모두 로컬에서 실행합니다:

```bash
python -m src.main
```

### 운영 배포 (권장)

Agent는 AgentCore에 배포하고, Slack Bot은 EC2/ECS에서 실행합니다.

1. **AgentCore에 Agent 배포**
```bash
agentcore configure --entrypoint src/main.py
agentcore deploy --env ENV_TYPE=dev --env USE_AGENTCORE=true
```

2. **Slack Bot 서버 실행** (AgentCore 호출 모드)
```bash
# .env 설정
USE_AGENTCORE_REMOTE=true
AGENTCORE_ENDPOINT=https://your-endpoint.amazonaws.com

# 실행
python -m src.main
```

자세한 내용은 [docs/DEPLOYMENT_GUIDE.md](docs/DEPLOYMENT_GUIDE.md)를 참고하세요.

## 프로젝트 구조

```
cloudtrail-bot/
├── src/
│   ├── __init__.py
│   ├── main.py              # 진입점
│   ├── agent.py             # Strands Agent 정의
│   ├── slack_handler.py     # Slack 이벤트 핸들러
│   └── tools/
│       ├── __init__.py
│       ├── credential.py    # AWS Credential 획득
│       └── cloudtrail.py    # CloudTrail 도구
├── docs/
│   └── SLACK_APP_SETUP.md   # Slack App 설정 가이드
├── scripts/
│   ├── deploy.sh            # AgentCore 배포 스크립트
│   ├── run_local.sh         # 로컬 실행 (Linux/Mac)
│   └── run_local.bat        # 로컬 실행 (Windows)
├── requirements.txt
├── Dockerfile
├── .env.example
└── README.md
```

## 환경 변수

| 변수명 | 필수 | 설명 |
|--------|------|------|
| `SLACK_BOT_TOKEN` | ✅ | Bot User OAuth Token (xoxb-...) |
| `SLACK_APP_TOKEN` | ✅ | App-Level Token (xapp-...) |
| `ENV_TYPE` | | 환경 타입 (기본값: dev) |
| `AWS_REGION` | | 기본 AWS 리전 (기본값: ap-northeast-2) |
| `BEDROCK_MODEL_ID` | | Bedrock 모델 ID |
| `LOG_LEVEL` | | 로그 레벨 (기본값: INFO) |

## 필요 권한

### AWS IAM 권한

- `ssm:GetParameter` (WithDecryption)
- `sts:AssumeRole`
- `cloudtrail:LookupEvents`

### Slack App 권한

- `app_mentions:read`
- `chat:write`
- `channels:history`

## 라이선스

이 프로젝트는 내부 사용 목적으로 개발되었습니다.

