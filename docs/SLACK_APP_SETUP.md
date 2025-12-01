# Slack App 설정 가이드

이 문서는 CloudTrail 보안 모니터링 챗봇을 위한 Slack App 설정 방법을 설명합니다.

## 1. Slack App 생성

1. [Slack API 포털](https://api.slack.com/apps)에 접속합니다.
2. **Create New App** 버튼을 클릭합니다.
3. **From scratch**를 선택합니다.
4. App 이름(예: `CloudTrail Security Bot`)과 워크스페이스를 선택합니다.

## 2. Socket Mode 활성화

Socket Mode를 사용하면 공개 URL 없이 WebSocket 연결을 통해 이벤트를 수신할 수 있습니다.

1. 좌측 메뉴에서 **Socket Mode**를 클릭합니다.
2. **Enable Socket Mode**를 활성화합니다.
3. Token 이름을 입력하고 **Generate**를 클릭합니다.
4. 생성된 **App-Level Token** (`xapp-...`)을 안전하게 저장합니다.

> ⚠️ 이 토큰은 `SLACK_APP_TOKEN` 환경변수로 사용됩니다.

## 3. Bot Token Scopes 설정

1. 좌측 메뉴에서 **OAuth & Permissions**를 클릭합니다.
2. **Scopes** 섹션에서 **Bot Token Scopes**에 다음 권한을 추가합니다:

| Scope | 설명 |
|-------|------|
| `app_mentions:read` | Bot이 멘션된 메시지를 읽을 수 있음 |
| `chat:write` | Bot이 메시지를 보낼 수 있음 |
| `channels:history` | 공개 채널의 메시지 기록을 읽을 수 있음 |
| `groups:history` | 비공개 채널의 메시지 기록을 읽을 수 있음 (선택) |
| `im:history` | DM 메시지 기록을 읽을 수 있음 (선택) |

## 4. Event Subscriptions 설정

1. 좌측 메뉴에서 **Event Subscriptions**를 클릭합니다.
2. **Enable Events**를 활성화합니다.
3. **Subscribe to bot events** 섹션에서 다음 이벤트를 추가합니다:

| Event | 필수 | 설명 |
|-------|------|------|
| `app_mention` | ✅ | Bot이 멘션되었을 때 트리거 |
| `message.channels` | ✅ | 공개 채널에서 스레드 대화 이어가기 |
| `message.groups` | 선택 | 비공개 채널에서 스레드 대화 이어가기 |

> ⚠️ **중요**: `message.channels` 이벤트가 없으면 스레드에서 멘션 없이 대화를 이어갈 수 없습니다!

## 5. App 설치

1. 좌측 메뉴에서 **Install App**을 클릭합니다.
2. **Install to Workspace** 버튼을 클릭합니다.
3. 권한을 확인하고 **허용**을 클릭합니다.
4. 생성된 **Bot User OAuth Token** (`xoxb-...`)을 안전하게 저장합니다.

> ⚠️ 이 토큰은 `SLACK_BOT_TOKEN` 환경변수로 사용됩니다.

## 6. 채널에 Bot 추가

1. Slack 워크스페이스에서 Bot을 사용할 채널로 이동합니다.
2. 채널 이름을 클릭하여 설정을 엽니다.
3. **Integrations** 탭에서 **Add apps**를 클릭합니다.
4. 생성한 App을 검색하여 추가합니다.

## 7. 환경 변수 설정

다음 환경 변수를 `.env` 파일에 설정합니다:

```bash
# Slack Tokens
SLACK_BOT_TOKEN=xoxb-your-bot-token
SLACK_APP_TOKEN=xapp-your-app-token

# AWS 설정
ENV_TYPE=dev
AWS_REGION=ap-northeast-2
```

## 8. 사용 방법

채널에서 Bot을 멘션하여 CloudTrail 이벤트를 조회할 수 있습니다:

```
@CloudTrail Security Bot 계정 123456789012의 최근 보안 이벤트를 조회해줘
```

```
@CloudTrail Security Bot 어제 발생한 ConsoleLogin 이벤트를 분석해줘
```

## 문제 해결

### Bot이 응답하지 않는 경우

1. Socket Mode가 활성화되어 있는지 확인합니다.
2. `SLACK_APP_TOKEN`과 `SLACK_BOT_TOKEN`이 올바른지 확인합니다.
3. Bot이 채널에 추가되어 있는지 확인합니다.
4. Event Subscriptions에서 `app_mention` 이벤트가 구독되어 있는지 확인합니다.

### 권한 오류가 발생하는 경우

1. Bot Token Scopes가 올바르게 설정되어 있는지 확인합니다.
2. App을 다시 설치하여 새 권한을 적용합니다.

