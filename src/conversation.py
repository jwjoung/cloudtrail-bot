"""
대화 컨텍스트 관리 모듈

스레드별 대화 히스토리를 저장하고 관리합니다.
"""

import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from loguru import logger


@dataclass
class Message:
    """대화 메시지"""
    role: str  # "user" or "assistant"
    content: str
    timestamp: float = field(default_factory=time.time)


@dataclass
class Conversation:
    """스레드별 대화 컨텍스트"""
    thread_ts: str
    channel: str
    messages: List[Message] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    last_activity: float = field(default_factory=time.time)
    account_id: Optional[str] = None  # 현재 대화에서 사용 중인 계정
    
    def add_user_message(self, content: str):
        """사용자 메시지 추가"""
        self.messages.append(Message(role="user", content=content))
        self.last_activity = time.time()
    
    def add_assistant_message(self, content: str):
        """어시스턴트 응답 추가"""
        self.messages.append(Message(role="assistant", content=content))
        self.last_activity = time.time()
    
    def get_context_string(self, max_messages: int = 10) -> str:
        """대화 컨텍스트를 문자열로 반환"""
        recent_messages = self.messages[-max_messages:]
        
        context_parts = []
        for msg in recent_messages:
            role_label = "사용자" if msg.role == "user" else "어시스턴트"
            context_parts.append(f"[{role_label}]: {msg.content}")
        
        return "\n".join(context_parts)
    
    def is_expired(self, ttl_seconds: int = 3600) -> bool:
        """대화가 만료되었는지 확인 (기본 1시간)"""
        return time.time() - self.last_activity > ttl_seconds


class ConversationManager:
    """대화 컨텍스트 관리자"""
    
    def __init__(self, max_conversations: int = 1000, ttl_seconds: int = 3600):
        """
        Args:
            max_conversations: 최대 저장할 대화 수
            ttl_seconds: 대화 만료 시간 (초)
        """
        self._conversations: OrderedDict[str, Conversation] = OrderedDict()
        self._max_conversations = max_conversations
        self._ttl_seconds = ttl_seconds
    
    def _make_key(self, channel: str, thread_ts: str) -> str:
        """대화 키 생성"""
        return f"{channel}:{thread_ts}"
    
    def get_or_create(self, channel: str, thread_ts: str) -> Conversation:
        """대화 컨텍스트를 가져오거나 생성"""
        key = self._make_key(channel, thread_ts)
        
        if key in self._conversations:
            conv = self._conversations[key]
            # LRU: 최근 사용한 항목을 끝으로 이동
            self._conversations.move_to_end(key)
            return conv
        
        # 새 대화 생성
        conv = Conversation(thread_ts=thread_ts, channel=channel)
        self._conversations[key] = conv
        
        # 용량 초과 시 오래된 대화 삭제
        self._cleanup()
        
        return conv
    
    def get(self, channel: str, thread_ts: str) -> Optional[Conversation]:
        """대화 컨텍스트 조회 (없으면 None)"""
        key = self._make_key(channel, thread_ts)
        return self._conversations.get(key)
    
    def delete(self, channel: str, thread_ts: str):
        """대화 컨텍스트 삭제"""
        key = self._make_key(channel, thread_ts)
        if key in self._conversations:
            del self._conversations[key]
    
    def _cleanup(self):
        """오래된 대화 및 초과 대화 정리"""
        # 만료된 대화 삭제
        expired_keys = [
            key for key, conv in self._conversations.items()
            if conv.is_expired(self._ttl_seconds)
        ]
        for key in expired_keys:
            del self._conversations[key]
        
        # 용량 초과 시 가장 오래된 대화 삭제
        while len(self._conversations) > self._max_conversations:
            self._conversations.popitem(last=False)
    
    def clear_all(self):
        """모든 대화 삭제"""
        self._conversations.clear()
    
    @property
    def count(self) -> int:
        """현재 저장된 대화 수"""
        return len(self._conversations)


# 전역 대화 관리자
_conversation_manager: Optional[ConversationManager] = None


def get_conversation_manager() -> ConversationManager:
    """대화 관리자 싱글톤 인스턴스"""
    global _conversation_manager
    if _conversation_manager is None:
        _conversation_manager = ConversationManager()
    return _conversation_manager


def build_contextual_prompt(
    user_message: str,
    conversation: Conversation,
    max_history: int = 5
) -> str:
    """
    대화 컨텍스트를 포함한 프롬프트 생성
    
    Args:
        user_message: 현재 사용자 메시지
        conversation: 대화 컨텍스트
        max_history: 포함할 최대 이전 메시지 수
    
    Returns:
        컨텍스트가 포함된 프롬프트
    """
    if not conversation.messages:
        return user_message
    
    # 이전 대화 요약
    recent_messages = conversation.messages[-(max_history * 2):]  # user+assistant 쌍
    
    if not recent_messages:
        return user_message
    
    context_parts = ["[이전 대화 내용]"]
    for msg in recent_messages:
        role = "사용자" if msg.role == "user" else "봇"
        # 긴 메시지는 요약
        content = msg.content[:500] + "..." if len(msg.content) > 500 else msg.content
        context_parts.append(f"{role}: {content}")
    
    context_parts.append("")
    context_parts.append("[현재 질문]")
    context_parts.append(user_message)
    
    # 계정 컨텍스트가 있으면 추가
    if conversation.account_id:
        context_parts.insert(1, f"(현재 작업 중인 계정: {conversation.account_id})")
    
    return "\n".join(context_parts)

