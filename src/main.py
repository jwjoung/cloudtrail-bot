"""
CloudTrail Security Bot - 메인 진입점

AgentCore Runtime과 Slack Bot을 통합하여 실행합니다.
"""

import asyncio
import os
import signal
import sys
from typing import Optional

from dotenv import load_dotenv
from loguru import logger

# 환경 변수 로드
load_dotenv()

# 로깅 설정
logger.remove()
logger.add(
    sys.stderr,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    level=os.environ.get("LOG_LEVEL", "INFO")
)

# AgentCore 사용 여부
USE_AGENTCORE = os.environ.get("USE_AGENTCORE", "false").lower() == "true"


async def run_standalone():
    """
    독립 실행 모드 (로컬 개발/테스트용)
    
    Socket Mode로 Slack Bot을 직접 실행합니다.
    """
    from src.slack_handler import start_socket_mode, stop_socket_mode
    
    # 종료 시그널 핸들러
    loop = asyncio.get_event_loop()
    
    def signal_handler():
        logger.info("종료 시그널 수신")
        asyncio.create_task(stop_socket_mode())
    
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, signal_handler)
        except NotImplementedError:
            # Windows에서는 지원되지 않음
            pass
    
    logger.info("CloudTrail Security Bot 시작 (독립 실행 모드)")
    logger.info(f"환경: {os.environ.get('ENV_TYPE', 'dev')}")
    logger.info(f"리전: {os.environ.get('AWS_REGION', 'ap-northeast-2')}")
    
    try:
        await start_socket_mode()
    except KeyboardInterrupt:
        logger.info("키보드 인터럽트로 종료")
    except Exception as e:
        logger.error(f"실행 오류: {e}")
        raise
    finally:
        await stop_socket_mode()


def run_agentcore():
    """
    AgentCore Runtime 모드
    
    AgentCore에서 호스팅될 때 사용됩니다.
    HTTP 엔드포인트를 통해 요청을 받습니다.
    """
    from bedrock_agentcore.runtime import BedrockAgentCoreApp
    from src.agent import process_message
    
    app = BedrockAgentCoreApp()
    
    @app.entrypoint
    def agent_invocation(payload: dict, context: dict) -> dict:
        """AgentCore 호출 엔드포인트"""
        logger.info(f"AgentCore 호출 수신: {payload}")
        
        prompt = payload.get("prompt", "")
        
        if not prompt:
            return {
                "error": "prompt 필드가 필요합니다.",
                "example": {"prompt": "계정 123456789012의 최근 활동을 조회해줘"}
            }
        
        try:
            result = process_message(prompt)
            return {"result": result}
        except Exception as e:
            logger.error(f"처리 오류: {e}")
            return {"error": str(e)}
    
    logger.info("CloudTrail Security Bot 시작 (AgentCore 모드)")
    app.run()


def main():
    """메인 함수"""
    if USE_AGENTCORE:
        run_agentcore()
    else:
        asyncio.run(run_standalone())


if __name__ == "__main__":
    main()

