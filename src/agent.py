"""
CloudTrail 보안 모니터링 Agent

Strands Agent를 사용하여 CloudTrail 이벤트를 자연어로 조회하고 분석합니다.
"""

import os
from typing import Optional

from loguru import logger
from strands import Agent

from src.tools.cloudtrail import (
    lookup_cloudtrail_events,
    analyze_security_events,
    get_console_login_events,
    get_error_events,
    search_account,
)

# 시스템 프롬프트 정의
SYSTEM_PROMPT = """당신은 AWS 보안 전문가이자 CloudTrail 분석가입니다. 
사용자가 AWS 계정의 보안 상태를 모니터링하고 분석하는 것을 돕습니다.

## 핵심 역할
- AWS CloudTrail 이벤트 조회 및 분석
- 보안 위협 탐지 및 설명
- 침해 사고 조사 지원
- 보안 모범 사례 제안

## 사용 가능한 도구

1. **lookup_cloudtrail_events**: 특정 계정의 CloudTrail 이벤트를 조회합니다.
   - account_id: AWS 계정 ID (12자리)
   - start_time: 조회 시작 시간 (예: "1 day ago", "2024-01-15")
   - event_name: 특정 이벤트 필터링 (선택)
   - username: 특정 사용자 필터링 (선택)
   - region: AWS 리전 (기본값: ap-northeast-2)

2. **get_console_login_events**: 콘솔 로그인 기록을 조회합니다.
   - 로그인 성공/실패, IP 주소, MFA 사용 여부 확인
   - ConsoleLogin 이벤트는 주로 us-east-1에 기록됨

3. **get_error_events**: 에러 이벤트를 조회합니다.
   - 권한 거부, API 호출 실패 등 조회
   - 보안 문제나 설정 오류 파악에 유용

4. **analyze_security_events**: 종합적인 보안 분석을 수행합니다.
   - IAM 변경, 보안 그룹 수정, 루트 활동 등 분석
   - 카테고리별 위험도 분류

5. **search_account**: 회사명 또는 Account ID로 계정을 검색합니다.
   - 계정 정보 확인 시 사용

## 응답 가이드라인

1. **계정 식별**
   - 사용자가 계정명이나 Account ID를 언급하면 해당 계정에 대해 작업합니다.
   - Account ID는 12자리 숫자입니다.
   - 계정을 찾을 수 없으면 search_account 도구로 먼저 검색합니다.

2. **분석 결과 설명**
   - 조회 결과를 요약하여 설명합니다.
   - 보안 위험이 있는 이벤트는 명확하게 강조합니다.
   - 기술적 내용은 이해하기 쉽게 설명합니다.

3. **보안 권고사항**
   - 발견된 문제에 대한 대응 방안을 제안합니다.
   - AWS 보안 모범 사례를 안내합니다.

4. **주의사항**
   - 민감한 정보(Access Key 등)는 마스킹하여 표시합니다.
   - 확실하지 않은 정보는 추측하지 않습니다.
   - 추가 조사가 필요한 경우 명확히 안내합니다.

## 응답 형식
- 한국어로 응답합니다.
- Slack 메시지에 적합한 마크다운 형식을 사용합니다.
- 이모지를 적절히 활용하여 가독성을 높입니다.
- 긴 결과는 요약 후 상세 내용을 제공합니다.

## 자주 묻는 질문 유형

1. "계정 XXX의 최근 활동을 조회해줘"
   → lookup_cloudtrail_events 사용

2. "어제 콘솔 로그인 기록을 확인해줘"
   → get_console_login_events 사용 (region=us-east-1)

3. "보안 분석을 해줘"
   → analyze_security_events 사용

4. "에러가 발생한 API 호출을 찾아줘"
   → get_error_events 사용

5. "특정 사용자(XXX)의 활동을 조회해줘"
   → lookup_cloudtrail_events에 username 파라미터 사용
"""

# Agent 인스턴스 (글로벌)
_agent_instance: Optional[Agent] = None


def get_agent() -> Agent:
    """
    CloudTrail 보안 모니터링 Agent 인스턴스를 반환합니다 (싱글톤).
    """
    global _agent_instance
    
    if _agent_instance is None:
        logger.info("CloudTrail Security Agent 초기화 중...")
        
        # Bedrock 모델 설정
        model_id = os.environ.get(
            "BEDROCK_MODEL_ID", 
            "us.anthropic.claude-3-5-sonnet-20241022-v2:0"
        )
        
        # Agent 생성
        _agent_instance = Agent(
            system_prompt=SYSTEM_PROMPT,
            tools=[
                lookup_cloudtrail_events,
                analyze_security_events,
                get_console_login_events,
                get_error_events,
                search_account,
            ],
            # model_id=model_id,  # Strands가 자동으로 Bedrock 사용
        )
        
        logger.info("CloudTrail Security Agent 초기화 완료")
    
    return _agent_instance


def process_message(user_message: str, use_remote: bool = None) -> str:
    """
    사용자 메시지를 처리하고 Agent 응답을 반환합니다.
    
    Args:
        user_message: 사용자 메시지
        use_remote: True면 AgentCore 원격 호출, False면 로컬 실행.
                    None이면 환경변수 USE_AGENTCORE_REMOTE로 결정
    
    Returns:
        Agent 응답 텍스트
    """
    # 원격 호출 여부 결정
    if use_remote is None:
        use_remote = os.environ.get("USE_AGENTCORE_REMOTE", "false").lower() == "true"
    
    if use_remote:
        return _process_message_remote(user_message)
    else:
        return _process_message_local(user_message)


def _process_message_local(user_message: str) -> str:
    """로컬에서 Agent를 실행하여 메시지를 처리합니다."""
    try:
        agent = get_agent()
        logger.info(f"[로컬] 사용자 메시지 처리 중: {user_message[:100]}...")
        
        # Agent 호출
        result = agent(user_message)
        
        # 응답 추출
        if hasattr(result, 'message'):
            response = result.message
        elif isinstance(result, str):
            response = result
        else:
            response = str(result)
        
        logger.info(f"[로컬] Agent 응답 생성 완료 (길이: {len(response)})")
        return response
        
    except Exception as e:
        logger.error(f"[로컬] 메시지 처리 오류: {e}")
        return f"❌ 요청을 처리하는 중 오류가 발생했습니다: {str(e)}"


def _process_message_remote(user_message: str) -> str:
    """AgentCore에 배포된 Agent를 호출하여 메시지를 처리합니다."""
    try:
        from src.agentcore_client import invoke_agentcore
        
        logger.info(f"[원격] AgentCore 호출 중: {user_message[:100]}...")
        
        response = invoke_agentcore(user_message)
        
        logger.info(f"[원격] AgentCore 응답 수신 (길이: {len(response)})")
        return response
        
    except ImportError:
        logger.warning("AgentCore 클라이언트를 로드할 수 없어 로컬 모드로 전환합니다.")
        return _process_message_local(user_message)
        
    except Exception as e:
        logger.error(f"[원격] AgentCore 호출 오류: {e}")
        return f"❌ AgentCore 호출 중 오류가 발생했습니다: {str(e)}"


def reset_agent():
    """Agent 인스턴스를 리셋합니다 (대화 컨텍스트 초기화)."""
    global _agent_instance
    _agent_instance = None
    logger.info("Agent 인스턴스가 리셋되었습니다.")

