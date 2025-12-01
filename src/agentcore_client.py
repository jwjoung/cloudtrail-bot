"""
AgentCore Runtime 클라이언트

Slack Bot에서 AgentCore에 배포된 Agent를 호출합니다.
"""

import os
import json
from typing import Optional

import boto3
from loguru import logger


class AgentCoreClient:
    """AgentCore Runtime 클라이언트"""
    
    def __init__(self, runtime_arn: Optional[str] = None, region: Optional[str] = None):
        """
        Args:
            runtime_arn: AgentCore Runtime ARN (환경변수 AGENTCORE_RUNTIME_ARN에서도 읽음)
            region: AWS 리전 (환경변수 AWS_REGION에서도 읽음)
        """
        self.runtime_arn = runtime_arn or os.environ.get("AGENTCORE_RUNTIME_ARN")
        self.region = region or os.environ.get("AWS_REGION", "us-west-2")
        
        if not self.runtime_arn:
            raise ValueError(
                "AGENTCORE_RUNTIME_ARN 환경변수가 설정되지 않았습니다. "
                "AgentCore 배포 후 생성된 ARN을 설정해주세요."
            )
        
        # Bedrock Agent Runtime 클라이언트
        self._client = boto3.client(
            "bedrock-agent-runtime",
            region_name=self.region
        )
        
        logger.info(f"AgentCore 클라이언트 초기화: {self.runtime_arn}")
    
    def invoke(self, prompt: str) -> str:
        """
        AgentCore에 배포된 Agent를 호출합니다.
        
        Args:
            prompt: 사용자 메시지
        
        Returns:
            Agent 응답 텍스트
        """
        try:
            logger.info(f"AgentCore 호출: {prompt[:50]}...")
            
            # AgentCore Runtime 호출
            response = self._client.invoke_agent(
                agentId=self._extract_agent_id(),
                agentAliasId=self._extract_alias_id(),
                sessionId=self._generate_session_id(),
                inputText=prompt
            )
            
            # 스트리밍 응답 처리
            result_text = ""
            for event in response.get("completion", []):
                if "chunk" in event:
                    chunk_data = event["chunk"]
                    if "bytes" in chunk_data:
                        result_text += chunk_data["bytes"].decode("utf-8")
            
            logger.info(f"AgentCore 응답 수신 (길이: {len(result_text)})")
            return result_text
            
        except Exception as e:
            logger.error(f"AgentCore 호출 오류: {e}")
            raise
    
    def invoke_simple(self, prompt: str) -> str:
        """
        간단한 HTTP 방식으로 AgentCore를 호출합니다.
        (bedrock-agentcore SDK의 invoke 사용)
        
        Args:
            prompt: 사용자 메시지
        
        Returns:
            Agent 응답 텍스트
        """
        try:
            import requests
            
            # AgentCore Runtime endpoint
            endpoint = os.environ.get("AGENTCORE_ENDPOINT")
            if not endpoint:
                raise ValueError("AGENTCORE_ENDPOINT 환경변수가 설정되지 않았습니다.")
            
            logger.info(f"AgentCore HTTP 호출: {prompt[:50]}...")
            
            response = requests.post(
                f"{endpoint}/invocations",
                json={"prompt": prompt},
                headers={"Content-Type": "application/json"},
                timeout=120
            )
            response.raise_for_status()
            
            result = response.json()
            return result.get("result", str(result))
            
        except Exception as e:
            logger.error(f"AgentCore HTTP 호출 오류: {e}")
            raise
    
    def _extract_agent_id(self) -> str:
        """ARN에서 Agent ID 추출"""
        # arn:aws:bedrock:region:account:agent/agent-id
        parts = self.runtime_arn.split("/")
        return parts[-1] if parts else ""
    
    def _extract_alias_id(self) -> str:
        """기본 Alias ID 반환"""
        return os.environ.get("AGENTCORE_ALIAS_ID", "TSTALIASID")
    
    def _generate_session_id(self) -> str:
        """세션 ID 생성"""
        import uuid
        return str(uuid.uuid4())


# 싱글톤 인스턴스
_client: Optional[AgentCoreClient] = None


def get_agentcore_client() -> AgentCoreClient:
    """AgentCore 클라이언트 인스턴스 반환 (싱글톤)"""
    global _client
    if _client is None:
        _client = AgentCoreClient()
    return _client


def invoke_agentcore(prompt: str) -> str:
    """
    AgentCore Agent를 호출하는 헬퍼 함수
    
    Args:
        prompt: 사용자 메시지
    
    Returns:
        Agent 응답
    """
    client = get_agentcore_client()
    return client.invoke_simple(prompt)

