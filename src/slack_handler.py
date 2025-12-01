"""
Slack Bolt 이벤트 핸들러

Slack App Mention 이벤트를 처리하고 스레드에 응답합니다.
"""

import os
import re
from typing import Optional

from loguru import logger
from slack_bolt.async_app import AsyncApp
from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler
from slack_sdk.web.async_client import AsyncWebClient

from src.agent import process_message

# Slack App 인스턴스
_slack_app: Optional[AsyncApp] = None
_socket_handler: Optional[AsyncSocketModeHandler] = None


def create_slack_app() -> AsyncApp:
    """Slack Bolt App 인스턴스를 생성합니다."""
    bot_token = os.environ.get("SLACK_BOT_TOKEN")
    
    if not bot_token:
        raise ValueError("SLACK_BOT_TOKEN 환경 변수가 설정되지 않았습니다.")
    
    app = AsyncApp(token=bot_token)
    
    # 이벤트 핸들러 등록
    register_event_handlers(app)
    
    return app


def register_event_handlers(app: AsyncApp):
    """이벤트 핸들러를 등록합니다."""
    
    @app.event("app_mention")
    async def handle_app_mention(event: dict, say, client: AsyncWebClient, logger):
        """
        Bot이 멘션되었을 때 처리합니다.
        멘션된 메시지의 스레드에서 대화를 진행합니다.
        """
        try:
            # 메시지 정보 추출
            channel = event.get("channel")
            user = event.get("user")
            text = event.get("text", "")
            ts = event.get("ts")
            thread_ts = event.get("thread_ts") or ts  # 스레드가 없으면 현재 메시지가 스레드 시작점
            
            logger.info(f"멘션 수신: channel={channel}, user={user}, text={text[:50]}...")
            
            # Bot 멘션 제거 (예: <@U123456789>)
            clean_text = re.sub(r'<@[A-Z0-9]+>', '', text).strip()
            
            if not clean_text:
                await say(
                    text="안녕하세요! 👋 무엇을 도와드릴까요?\n\n"
                         "예시:\n"
                         "• `계정 123456789012의 최근 활동을 조회해줘`\n"
                         "• `보안 분석을 해줘`\n"
                         "• `어제 콘솔 로그인 기록을 확인해줘`",
                    thread_ts=thread_ts
                )
                return
            
            # 처리 중 메시지 전송
            thinking_msg = await say(
                text="🔍 요청을 처리하고 있습니다...",
                thread_ts=thread_ts
            )
            
            # Agent로 메시지 처리
            response = process_message(clean_text)
            
            # 응답이 길면 분할
            max_length = 3900  # Slack 메시지 제한 (4000자)에 여유 둠
            
            if len(response) <= max_length:
                # 기존 "처리 중" 메시지 업데이트
                await client.chat_update(
                    channel=channel,
                    ts=thinking_msg["ts"],
                    text=response
                )
            else:
                # 긴 응답은 분할하여 전송
                await client.chat_update(
                    channel=channel,
                    ts=thinking_msg["ts"],
                    text=response[:max_length]
                )
                
                # 나머지 부분 전송
                remaining = response[max_length:]
                while remaining:
                    chunk = remaining[:max_length]
                    remaining = remaining[max_length:]
                    await say(text=chunk, thread_ts=thread_ts)
            
            logger.info(f"응답 완료: channel={channel}, thread_ts={thread_ts}")
            
        except Exception as e:
            logger.error(f"멘션 처리 오류: {e}")
            await say(
                text=f"❌ 요청을 처리하는 중 오류가 발생했습니다.\n```{str(e)}```",
                thread_ts=thread_ts
            )
    
    @app.event("message")
    async def handle_message(event: dict, say, client: AsyncWebClient, logger):
        """
        스레드 내 메시지를 처리합니다.
        Bot이 참여 중인 스레드에서 추가 메시지가 오면 응답합니다.
        """
        # Bot 자신의 메시지는 무시
        if event.get("bot_id"):
            return
        
        # 서브타입이 있는 메시지 (편집, 삭제 등) 무시
        if event.get("subtype"):
            return
        
        # 스레드 메시지만 처리 (app_mention과 중복 방지)
        thread_ts = event.get("thread_ts")
        if not thread_ts:
            return
        
        # 멘션이 포함된 메시지는 app_mention 핸들러가 처리함
        text = event.get("text", "")
        if re.search(r'<@[A-Z0-9]+>', text):
            return
        
        channel = event.get("channel")
        ts = event.get("ts")
        
        try:
            # 스레드의 기존 메시지 조회하여 Bot이 참여 중인지 확인
            result = await client.conversations_replies(
                channel=channel,
                ts=thread_ts,
                limit=10
            )
            
            messages = result.get("messages", [])
            bot_participated = any(msg.get("bot_id") for msg in messages)
            
            if not bot_participated:
                # Bot이 참여하지 않은 스레드는 무시
                return
            
            logger.info(f"스레드 메시지 수신: channel={channel}, thread_ts={thread_ts}")
            
            # 처리 중 표시
            thinking_msg = await say(
                text="🔍 요청을 처리하고 있습니다...",
                thread_ts=thread_ts
            )
            
            # Agent로 처리
            response = process_message(text)
            
            # 응답 업데이트
            await client.chat_update(
                channel=channel,
                ts=thinking_msg["ts"],
                text=response
            )
            
        except Exception as e:
            logger.error(f"스레드 메시지 처리 오류: {e}")
    
    @app.event("app_home_opened")
    async def handle_app_home_opened(event: dict, client: AsyncWebClient, logger):
        """App Home 탭이 열렸을 때 처리합니다."""
        user_id = event.get("user")
        
        try:
            await client.views_publish(
                user_id=user_id,
                view={
                    "type": "home",
                    "blocks": [
                        {
                            "type": "header",
                            "text": {
                                "type": "plain_text",
                                "text": "🛡️ CloudTrail Security Bot"
                            }
                        },
                        {
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": "AWS CloudTrail 이벤트를 자연어로 조회하고 보안 상태를 분석합니다."
                            }
                        },
                        {
                            "type": "divider"
                        },
                        {
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": "*사용 방법*\n\n"
                                        "채널에서 Bot을 멘션하여 질문하세요:\n\n"
                                        "```@CloudTrail Bot 계정 123456789012의 최근 활동을 조회해줘```\n\n"
                                        "```@CloudTrail Bot 어제 콘솔 로그인 기록을 확인해줘```\n\n"
                                        "```@CloudTrail Bot 보안 분석을 해줘```"
                            }
                        },
                        {
                            "type": "divider"
                        },
                        {
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": "*주요 기능*\n\n"
                                        "• 📊 CloudTrail 이벤트 조회\n"
                                        "• 🔐 콘솔 로그인 기록 조회\n"
                                        "• ⚠️ 에러 이벤트 조회\n"
                                        "• 🛡️ 종합 보안 분석\n"
                                        "• 🔍 계정 검색"
                            }
                        }
                    ]
                }
            )
        except Exception as e:
            logger.error(f"App Home 업데이트 오류: {e}")


def get_slack_app() -> AsyncApp:
    """Slack App 인스턴스를 반환합니다 (싱글톤)."""
    global _slack_app
    
    if _slack_app is None:
        _slack_app = create_slack_app()
    
    return _slack_app


async def start_socket_mode():
    """Socket Mode로 Slack App을 시작합니다."""
    global _socket_handler
    
    app_token = os.environ.get("SLACK_APP_TOKEN")
    
    if not app_token:
        raise ValueError("SLACK_APP_TOKEN 환경 변수가 설정되지 않았습니다.")
    
    app = get_slack_app()
    _socket_handler = AsyncSocketModeHandler(app, app_token)
    
    logger.info("Slack Bot 시작 중 (Socket Mode)...")
    await _socket_handler.start_async()


async def stop_socket_mode():
    """Socket Mode 연결을 종료합니다."""
    global _socket_handler
    
    if _socket_handler:
        await _socket_handler.close_async()
        logger.info("Slack Bot 종료됨")

