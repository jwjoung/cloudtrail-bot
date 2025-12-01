"""
CloudTrail 조회 도구 모듈

Strands Agent에서 사용할 CloudTrail 관련 도구들을 정의합니다.
동적 credential을 사용하여 다양한 AWS 계정의 CloudTrail을 조회합니다.
"""

import json
import os
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

from dateutil import parser as date_parser
from loguru import logger
from strands import tool

from src.tools.credential import (
    get_credential_by_account_id,
    get_credential_by_corp_name,
    get_boto3_client,
    get_account_info_from_db,
    search_account_by_name,
)


def parse_time_input(time_str: str) -> datetime:
    """
    시간 문자열을 datetime으로 변환합니다.
    
    지원 형식:
    - ISO 형식: "2024-01-15T10:00:00"
    - 상대 시간: "1 day ago", "2 hours ago", "30 minutes ago"
    - 특수 키워드: "now", "today", "yesterday"
    """
    time_str = time_str.strip().lower()
    now = datetime.utcnow()
    
    if time_str == "now":
        return now
    elif time_str == "today":
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif time_str == "yesterday":
        return (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    elif "ago" in time_str:
        parts = time_str.replace(" ago", "").split()
        if len(parts) >= 2:
            amount = int(parts[0])
            unit = parts[1]
            
            if "minute" in unit:
                return now - timedelta(minutes=amount)
            elif "hour" in unit:
                return now - timedelta(hours=amount)
            elif "day" in unit:
                return now - timedelta(days=amount)
            elif "week" in unit:
                return now - timedelta(weeks=amount)
    
    # ISO 형식 파싱 시도
    try:
        return date_parser.parse(time_str)
    except Exception:
        # 기본값: 1일 전
        return now - timedelta(days=1)


def format_event(event: Dict[str, Any]) -> str:
    """CloudTrail 이벤트를 읽기 쉬운 형식으로 포맷합니다."""
    cloud_trail_event = event.get("CloudTrailEvent", "{}")
    if isinstance(cloud_trail_event, str):
        try:
            event_detail = json.loads(cloud_trail_event)
        except json.JSONDecodeError:
            event_detail = {}
    else:
        event_detail = cloud_trail_event
    
    event_time = event.get("EventTime", "N/A")
    if hasattr(event_time, 'isoformat'):
        event_time = event_time.isoformat()
    
    lines = [
        f"📅 시간: {event_time}",
        f"🔧 이벤트: {event.get('EventName', 'N/A')}",
        f"👤 사용자: {event.get('Username', 'N/A')}",
        f"🌐 소스: {event_detail.get('eventSource', 'N/A')}",
        f"📍 리전: {event_detail.get('awsRegion', 'N/A')}",
        f"🖥️ IP: {event_detail.get('sourceIPAddress', 'N/A')}",
    ]
    
    # 에러 정보가 있으면 추가
    error_code = event_detail.get("errorCode")
    error_message = event_detail.get("errorMessage")
    if error_code:
        lines.append(f"❌ 에러 코드: {error_code}")
    if error_message:
        lines.append(f"❌ 에러 메시지: {error_message}")
    
    # 리소스 정보
    resources = event.get("Resources", [])
    if resources:
        resource_strs = [f"{r.get('ResourceType', 'Unknown')}: {r.get('ResourceName', 'N/A')}" for r in resources[:3]]
        lines.append(f"📦 리소스: {', '.join(resource_strs)}")
    
    return "\n".join(lines)


@tool
def lookup_cloudtrail_events(
    account_id: str,
    start_time: str = "1 day ago",
    end_time: str = "now",
    event_name: Optional[str] = None,
    username: Optional[str] = None,
    resource_name: Optional[str] = None,
    event_source: Optional[str] = None,
    region: str = "ap-northeast-2",
    max_results: int = 20
) -> str:
    """
    특정 AWS 계정의 CloudTrail 이벤트를 조회합니다.
    
    Args:
        account_id: AWS Account ID (12자리 숫자)
        start_time: 조회 시작 시간 (예: "1 day ago", "2024-01-15", "3 hours ago")
        end_time: 조회 종료 시간 (예: "now", "2024-01-16")
        event_name: 특정 이벤트 이름으로 필터링 (예: "ConsoleLogin", "CreateUser")
        username: 특정 사용자로 필터링
        resource_name: 특정 리소스 이름으로 필터링
        event_source: 특정 서비스로 필터링 (예: "s3.amazonaws.com", "ec2.amazonaws.com")
        region: AWS 리전 (기본값: ap-northeast-2)
        max_results: 최대 결과 수 (기본값: 20, 최대: 50)
    
    Returns:
        조회된 CloudTrail 이벤트 목록을 텍스트로 반환
    """
    try:
        # Credential 획득
        credential = get_credential_by_account_id(account_id)
        if not credential:
            return f"❌ 계정 ID '{account_id}'에 대한 자격증명을 획득할 수 없습니다. 계정 ID가 올바른지 확인해주세요."
        
        # CloudTrail 클라이언트 생성
        ct_client = get_boto3_client('cloudtrail', credential, region)
        
        # 시간 파싱
        start_dt = parse_time_input(start_time)
        end_dt = parse_time_input(end_time)
        
        # 조회 파라미터 구성
        lookup_params = {
            'StartTime': start_dt,
            'EndTime': end_dt,
            'MaxResults': min(max_results, 50),
        }
        
        # 필터 조건 추가
        lookup_attributes = []
        if event_name:
            lookup_attributes.append({'AttributeKey': 'EventName', 'AttributeValue': event_name})
        if username:
            lookup_attributes.append({'AttributeKey': 'Username', 'AttributeValue': username})
        if resource_name:
            lookup_attributes.append({'AttributeKey': 'ResourceName', 'AttributeValue': resource_name})
        if event_source:
            lookup_attributes.append({'AttributeKey': 'EventSource', 'AttributeValue': event_source})
        
        # CloudTrail API는 하나의 LookupAttribute만 지원
        if lookup_attributes:
            lookup_params['LookupAttributes'] = [lookup_attributes[0]]
        
        logger.info(f"CloudTrail 조회: account={account_id}, region={region}, params={lookup_params}")
        
        # 이벤트 조회
        response = ct_client.lookup_events(**lookup_params)
        events = response.get('Events', [])
        
        if not events:
            return f"📭 계정 {account_id}에서 조건에 맞는 이벤트를 찾을 수 없습니다.\n조회 기간: {start_dt.isoformat()} ~ {end_dt.isoformat()}"
        
        # 결과 포맷팅
        account_info = get_account_info_from_db(account_id)
        corp_name = account_info.get('corp_name', 'Unknown') if account_info else 'Unknown'
        
        result_lines = [
            f"🔍 **CloudTrail 이벤트 조회 결과**",
            f"📋 계정: {corp_name} ({account_id})",
            f"📍 리전: {region}",
            f"⏰ 기간: {start_dt.strftime('%Y-%m-%d %H:%M')} ~ {end_dt.strftime('%Y-%m-%d %H:%M')} UTC",
            f"📊 조회된 이벤트 수: {len(events)}개",
            "",
            "---",
            ""
        ]
        
        for i, event in enumerate(events, 1):
            result_lines.append(f"**[{i}]**")
            result_lines.append(format_event(event))
            result_lines.append("")
        
        return "\n".join(result_lines)
        
    except Exception as e:
        logger.error(f"CloudTrail 조회 오류: {e}")
        return f"❌ CloudTrail 조회 중 오류가 발생했습니다: {str(e)}"


@tool
def get_console_login_events(
    account_id: str,
    start_time: str = "7 days ago",
    region: str = "us-east-1",
    max_results: int = 30
) -> str:
    """
    특정 AWS 계정의 콘솔 로그인 이벤트를 조회합니다.
    
    보안 모니터링에 유용한 콘솔 로그인 기록을 조회합니다.
    로그인 성공/실패, 소스 IP, MFA 사용 여부 등을 확인할 수 있습니다.
    
    Args:
        account_id: AWS Account ID (12자리 숫자)
        start_time: 조회 시작 시간 (기본값: 7일 전)
        region: AWS 리전 (ConsoleLogin은 주로 us-east-1에 기록됨)
        max_results: 최대 결과 수
    
    Returns:
        콘솔 로그인 이벤트 목록
    """
    try:
        credential = get_credential_by_account_id(account_id)
        if not credential:
            return f"❌ 계정 ID '{account_id}'에 대한 자격증명을 획득할 수 없습니다."
        
        ct_client = get_boto3_client('cloudtrail', credential, region)
        
        start_dt = parse_time_input(start_time)
        end_dt = datetime.utcnow()
        
        response = ct_client.lookup_events(
            LookupAttributes=[
                {'AttributeKey': 'EventName', 'AttributeValue': 'ConsoleLogin'}
            ],
            StartTime=start_dt,
            EndTime=end_dt,
            MaxResults=min(max_results, 50)
        )
        
        events = response.get('Events', [])
        
        if not events:
            return f"📭 계정 {account_id}에서 콘솔 로그인 이벤트를 찾을 수 없습니다."
        
        account_info = get_account_info_from_db(account_id)
        corp_name = account_info.get('corp_name', 'Unknown') if account_info else 'Unknown'
        
        result_lines = [
            f"🔐 **콘솔 로그인 이벤트 조회 결과**",
            f"📋 계정: {corp_name} ({account_id})",
            f"⏰ 기간: {start_dt.strftime('%Y-%m-%d')} ~ {end_dt.strftime('%Y-%m-%d')} UTC",
            f"📊 조회된 로그인 수: {len(events)}건",
            "",
            "---",
            ""
        ]
        
        for i, event in enumerate(events, 1):
            event_detail = json.loads(event.get("CloudTrailEvent", "{}"))
            event_time = event.get("EventTime", "N/A")
            if hasattr(event_time, 'strftime'):
                event_time = event_time.strftime('%Y-%m-%d %H:%M:%S')
            
            # 로그인 결과 확인
            response_elements = event_detail.get("responseElements", {})
            login_result = response_elements.get("ConsoleLogin", "Unknown")
            
            # MFA 사용 여부
            additional_data = event_detail.get("additionalEventData", {})
            mfa_used = additional_data.get("MFAUsed", "Unknown")
            
            lines = [
                f"**[{i}]** {event_time}",
                f"  👤 사용자: {event.get('Username', 'N/A')}",
                f"  🖥️ IP: {event_detail.get('sourceIPAddress', 'N/A')}",
                f"  ✅ 결과: {login_result}",
                f"  🔑 MFA: {mfa_used}",
            ]
            
            # 에러가 있으면 표시
            error_code = event_detail.get("errorCode")
            if error_code:
                lines.append(f"  ❌ 에러: {error_code}")
            
            result_lines.extend(lines)
            result_lines.append("")
        
        return "\n".join(result_lines)
        
    except Exception as e:
        logger.error(f"콘솔 로그인 이벤트 조회 오류: {e}")
        return f"❌ 콘솔 로그인 이벤트 조회 중 오류가 발생했습니다: {str(e)}"


@tool
def get_error_events(
    account_id: str,
    start_time: str = "1 day ago",
    region: str = "ap-northeast-2",
    max_results: int = 30
) -> str:
    """
    특정 AWS 계정에서 발생한 에러 이벤트를 조회합니다.
    
    API 호출 실패, 권한 거부 등의 에러 이벤트를 조회하여
    보안 문제나 설정 오류를 파악하는 데 도움을 줍니다.
    
    Args:
        account_id: AWS Account ID (12자리 숫자)
        start_time: 조회 시작 시간 (기본값: 1일 전)
        region: AWS 리전
        max_results: 최대 결과 수
    
    Returns:
        에러 이벤트 목록
    """
    try:
        credential = get_credential_by_account_id(account_id)
        if not credential:
            return f"❌ 계정 ID '{account_id}'에 대한 자격증명을 획득할 수 없습니다."
        
        ct_client = get_boto3_client('cloudtrail', credential, region)
        
        start_dt = parse_time_input(start_time)
        end_dt = datetime.utcnow()
        
        # 전체 이벤트 조회 후 에러만 필터링
        response = ct_client.lookup_events(
            StartTime=start_dt,
            EndTime=end_dt,
            MaxResults=50
        )
        
        all_events = response.get('Events', [])
        
        # 에러 이벤트만 필터링
        error_events = []
        for event in all_events:
            event_detail = json.loads(event.get("CloudTrailEvent", "{}"))
            if event_detail.get("errorCode") or event_detail.get("errorMessage"):
                error_events.append(event)
        
        error_events = error_events[:max_results]
        
        if not error_events:
            return f"✅ 계정 {account_id}에서 에러 이벤트를 찾을 수 없습니다. (조회 기간: {start_time} ~ now)"
        
        account_info = get_account_info_from_db(account_id)
        corp_name = account_info.get('corp_name', 'Unknown') if account_info else 'Unknown'
        
        result_lines = [
            f"⚠️ **에러 이벤트 조회 결과**",
            f"📋 계정: {corp_name} ({account_id})",
            f"📍 리전: {region}",
            f"⏰ 기간: {start_dt.strftime('%Y-%m-%d %H:%M')} ~ now",
            f"📊 발견된 에러 수: {len(error_events)}건",
            "",
            "---",
            ""
        ]
        
        for i, event in enumerate(error_events, 1):
            event_detail = json.loads(event.get("CloudTrailEvent", "{}"))
            event_time = event.get("EventTime", "N/A")
            if hasattr(event_time, 'strftime'):
                event_time = event_time.strftime('%Y-%m-%d %H:%M:%S')
            
            lines = [
                f"**[{i}]** {event_time}",
                f"  🔧 이벤트: {event.get('EventName', 'N/A')}",
                f"  👤 사용자: {event.get('Username', 'N/A')}",
                f"  🌐 서비스: {event_detail.get('eventSource', 'N/A')}",
                f"  ❌ 에러 코드: {event_detail.get('errorCode', 'N/A')}",
                f"  ❌ 에러 메시지: {event_detail.get('errorMessage', 'N/A')[:100]}...",
            ]
            
            result_lines.extend(lines)
            result_lines.append("")
        
        return "\n".join(result_lines)
        
    except Exception as e:
        logger.error(f"에러 이벤트 조회 오류: {e}")
        return f"❌ 에러 이벤트 조회 중 오류가 발생했습니다: {str(e)}"


@tool
def analyze_security_events(
    account_id: str,
    start_time: str = "7 days ago",
    region: str = "ap-northeast-2"
) -> str:
    """
    특정 AWS 계정의 보안 관련 이벤트를 분석합니다.
    
    IAM 변경, 보안 그룹 수정, 루트 계정 활동 등
    보안에 민감한 이벤트를 종합적으로 분석합니다.
    
    Args:
        account_id: AWS Account ID (12자리 숫자)
        start_time: 조회 시작 시간 (기본값: 7일 전)
        region: AWS 리전
    
    Returns:
        보안 이벤트 분석 결과
    """
    # 보안 관련 이벤트 패턴
    SECURITY_EVENTS = {
        'iam': [
            'CreateUser', 'DeleteUser', 'CreateAccessKey', 'DeleteAccessKey',
            'CreateRole', 'DeleteRole', 'AttachUserPolicy', 'DetachUserPolicy',
            'AttachRolePolicy', 'DetachRolePolicy', 'PutUserPolicy', 'PutRolePolicy',
            'CreateGroup', 'DeleteGroup', 'AddUserToGroup', 'RemoveUserFromGroup',
            'UpdateLoginProfile', 'CreateLoginProfile', 'DeleteLoginProfile',
            'DeactivateMFADevice', 'EnableMFADevice', 'CreateVirtualMFADevice'
        ],
        'security_group': [
            'AuthorizeSecurityGroupIngress', 'AuthorizeSecurityGroupEgress',
            'RevokeSecurityGroupIngress', 'RevokeSecurityGroupEgress',
            'CreateSecurityGroup', 'DeleteSecurityGroup'
        ],
        'network': [
            'CreateVpc', 'DeleteVpc', 'CreateSubnet', 'DeleteSubnet',
            'CreateInternetGateway', 'DeleteInternetGateway',
            'CreateNatGateway', 'DeleteNatGateway'
        ],
        'kms': [
            'CreateKey', 'ScheduleKeyDeletion', 'DisableKey',
            'PutKeyPolicy', 'CreateGrant', 'RevokeGrant'
        ],
        'cloudtrail': [
            'StopLogging', 'DeleteTrail', 'UpdateTrail'
        ],
        's3': [
            'PutBucketPolicy', 'DeleteBucketPolicy', 'PutBucketAcl',
            'PutBucketPublicAccessBlock', 'DeleteBucketPublicAccessBlock'
        ]
    }
    
    try:
        credential = get_credential_by_account_id(account_id)
        if not credential:
            return f"❌ 계정 ID '{account_id}'에 대한 자격증명을 획득할 수 없습니다."
        
        ct_client = get_boto3_client('cloudtrail', credential, region)
        
        start_dt = parse_time_input(start_time)
        end_dt = datetime.utcnow()
        
        # 전체 이벤트 조회
        all_events = []
        next_token = None
        
        for _ in range(3):  # 최대 3번 페이징
            params = {
                'StartTime': start_dt,
                'EndTime': end_dt,
                'MaxResults': 50
            }
            if next_token:
                params['NextToken'] = next_token
            
            response = ct_client.lookup_events(**params)
            all_events.extend(response.get('Events', []))
            
            next_token = response.get('NextToken')
            if not next_token:
                break
        
        # 보안 이벤트 분류
        security_findings = {category: [] for category in SECURITY_EVENTS.keys()}
        security_findings['root_activity'] = []
        security_findings['error_events'] = []
        
        for event in all_events:
            event_name = event.get('EventName', '')
            username = event.get('Username', '')
            event_detail = json.loads(event.get("CloudTrailEvent", "{}"))
            
            # 루트 계정 활동 체크
            user_identity = event_detail.get('userIdentity', {})
            if user_identity.get('type') == 'Root':
                security_findings['root_activity'].append(event)
            
            # 에러 이벤트 체크
            if event_detail.get('errorCode'):
                security_findings['error_events'].append(event)
            
            # 카테고리별 분류
            for category, event_names in SECURITY_EVENTS.items():
                if event_name in event_names:
                    security_findings[category].append(event)
                    break
        
        # 결과 포맷팅
        account_info = get_account_info_from_db(account_id)
        corp_name = account_info.get('corp_name', 'Unknown') if account_info else 'Unknown'
        
        result_lines = [
            f"🛡️ **보안 이벤트 분석 결과**",
            f"📋 계정: {corp_name} ({account_id})",
            f"📍 리전: {region}",
            f"⏰ 분석 기간: {start_dt.strftime('%Y-%m-%d')} ~ {end_dt.strftime('%Y-%m-%d')} UTC",
            f"📊 총 분석 이벤트: {len(all_events)}건",
            "",
            "---",
            "",
            "📊 **카테고리별 요약**",
            ""
        ]
        
        category_names = {
            'root_activity': '🚨 루트 계정 활동',
            'iam': '👤 IAM 변경',
            'security_group': '🔒 보안 그룹 변경',
            'network': '🌐 네트워크 변경',
            'kms': '🔑 KMS 변경',
            'cloudtrail': '📝 CloudTrail 변경',
            's3': '📦 S3 정책 변경',
            'error_events': '⚠️ 에러 이벤트'
        }
        
        for category, display_name in category_names.items():
            events = security_findings.get(category, [])
            count = len(events)
            
            if count > 0:
                result_lines.append(f"- {display_name}: **{count}건** {'🔴' if category in ['root_activity', 'cloudtrail'] else ''}")
            else:
                result_lines.append(f"- {display_name}: 0건")
        
        # 주요 발견 사항 상세
        result_lines.extend(["", "---", "", "📌 **주요 발견 사항**", ""])
        
        # 루트 계정 활동 상세
        if security_findings['root_activity']:
            result_lines.append("🚨 **루트 계정 활동 감지**")
            for event in security_findings['root_activity'][:5]:
                event_time = event.get("EventTime", "N/A")
                if hasattr(event_time, 'strftime'):
                    event_time = event_time.strftime('%Y-%m-%d %H:%M')
                result_lines.append(f"  - {event_time}: {event.get('EventName', 'N/A')}")
            result_lines.append("")
        
        # IAM 변경 상세
        if security_findings['iam']:
            result_lines.append("👤 **IAM 변경 이벤트**")
            for event in security_findings['iam'][:5]:
                event_time = event.get("EventTime", "N/A")
                if hasattr(event_time, 'strftime'):
                    event_time = event_time.strftime('%Y-%m-%d %H:%M')
                result_lines.append(f"  - {event_time}: {event.get('EventName', 'N/A')} (by {event.get('Username', 'N/A')})")
            result_lines.append("")
        
        # CloudTrail 변경 (심각)
        if security_findings['cloudtrail']:
            result_lines.append("🔴 **CloudTrail 로깅 변경 감지**")
            for event in security_findings['cloudtrail']:
                event_time = event.get("EventTime", "N/A")
                if hasattr(event_time, 'strftime'):
                    event_time = event_time.strftime('%Y-%m-%d %H:%M')
                result_lines.append(f"  - {event_time}: {event.get('EventName', 'N/A')} (by {event.get('Username', 'N/A')})")
            result_lines.append("")
        
        # 발견된 보안 이슈가 없는 경우
        total_security_events = sum(len(events) for events in security_findings.values())
        if total_security_events == 0:
            result_lines.append("✅ 분석 기간 동안 특이한 보안 이벤트가 발견되지 않았습니다.")
        
        return "\n".join(result_lines)
        
    except Exception as e:
        logger.error(f"보안 이벤트 분석 오류: {e}")
        return f"❌ 보안 이벤트 분석 중 오류가 발생했습니다: {str(e)}"


@tool
def search_account(
    search_term: str
) -> str:
    """
    회사명 또는 Account ID로 AWS 계정을 검색합니다.
    
    Args:
        search_term: 검색할 회사명 또는 Account ID
    
    Returns:
        검색된 계정 정보
    """
    env_type = os.environ.get("ENV_TYPE", "dev")
    
    # 숫자로만 이루어진 경우 Account ID로 검색
    if search_term.isdigit() and len(search_term) == 12:
        account_info = get_account_info_from_db(search_term, env_type)
        if account_info:
            return (
                f"✅ **계정 검색 결과**\n"
                f"- 회사명: {account_info['corp_name']}\n"
                f"- Account ID: {account_info['account_id']}\n"
                f"- 연결 타입: {account_info['assume_role_type']}"
            )
        else:
            return f"❌ Account ID '{search_term}'에 해당하는 계정을 찾을 수 없습니다."
    
    # 회사명으로 검색
    account_info = search_account_by_name(search_term, env_type)
    if account_info:
        return (
            f"✅ **계정 검색 결과**\n"
            f"- 회사명: {account_info['corp_name']}\n"
            f"- Account ID: {account_info['account_id']}\n"
            f"- 연결 타입: {account_info['assume_role_type']}"
        )
    else:
        return f"❌ '{search_term}'에 해당하는 계정을 찾을 수 없습니다."

