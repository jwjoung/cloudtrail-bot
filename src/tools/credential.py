"""
AWS 계정 Credential 획득 모듈

DB에서 계정 정보를 조회하고 Bridge Role Chaining을 통해
대상 계정의 임시 자격증명을 획득합니다.

DB 접속 정보는 다음 우선순위로 로드됩니다:
1. 환경변수 (DB_HOST, DB_USER, DB_PASSWORD, DB_NAME, DB_PORT)
2. SSM Parameter Store (/fitcloud/{env_type}/db/...)
"""

import os
from typing import Optional, Dict, Any

import boto3
import pymysqlpool
from loguru import logger

# SSM Parameter Store 경로 설정
CROSSACCOUNT_ACCESS_KEY = '/access-key/crossaccount'
CROSSACCOUNT_SECRET_KEY = '/secret-key/crossaccount'

CROSSACCOUNT_BRIDGE_ACCOUNDID = '/crossaccountRoleBridge/bridgeAccountId'
CROSSACCOUNT_BRIDGE_EXTERNALID = '/crossaccountRoleBridge/bridgeExternalId'
CROSSACCOUNT_BRIDGE_ROLENAME = '/crossaccountRoleBridge/bridgeRoleName'

# SSM 클라이언트 (전역)
_ssm_client = None
_db_pool_cache: Dict[str, pymysqlpool.ConnectionPool] = {}


def _get_env_or_ssm(env_key: str, ssm_path: str, decrypt: bool = True) -> str:
    """
    환경변수를 먼저 확인하고, 없으면 SSM Parameter Store에서 로드합니다.
    
    Args:
        env_key: 환경변수 키
        ssm_path: SSM Parameter Store 경로
        decrypt: SSM 파라미터 복호화 여부
    
    Returns:
        설정값
    """
    # 환경변수 우선
    env_value = os.environ.get(env_key)
    if env_value:
        return env_value
    
    # SSM에서 로드
    return load_parameter(ssm_path)


def _load_parameter_safe(param_name: str) -> Optional[str]:
    """SSM Parameter Store에서 파라미터를 안전하게 로드합니다 (없으면 None)."""
    try:
        return load_parameter(param_name)
    except Exception:
        return None


def _get_db_secret_title(env_type: str) -> str:
    """
    DB secret title을 가져옵니다.
    
    우선순위:
    1. 환경변수 DB_SECRET_TITLE
    2. SSM: /cloudtrail-bot/{env_type}/db/secret-title
    3. SSM: /fitcloud/{env_type}/db/secret_title
    """
    # 1. 환경변수 확인
    secret_title = os.environ.get("DB_SECRET_TITLE")
    if secret_title:
        return secret_title
    
    # 2. cloudtrail-bot SSM 경로 확인
    secret_title = _load_parameter_safe(f"/cloudtrail-bot/{env_type}/db/secret-title")
    if secret_title:
        return secret_title
    
    # 3. fitcloud SSM 경로 사용
    return load_parameter(f"/fitcloud/{env_type}/db/secret_title")


def _get_ssm_client():
    """SSM 클라이언트를 가져옵니다 (싱글톤)."""
    global _ssm_client
    if _ssm_client is None:
        _ssm_client = boto3.client("ssm")
    return _ssm_client


def load_parameter(param_name: str) -> str:
    """SSM Parameter Store에서 파라미터 값을 가져옵니다."""
    ssm = _get_ssm_client()
    return ssm.get_parameter(Name=param_name, WithDecryption=True)["Parameter"]["Value"]


def get_db_connection_pool(env_type: str) -> pymysqlpool.ConnectionPool:
    """
    DB 연결 풀을 생성합니다 (캐싱).
    
    설정 우선순위:
    1. 환경변수 (DB_HOST, DB_USER, DB_PASSWORD, DB_NAME, DB_PORT)
    2. SSM: /cloudtrail-bot/{env_type}/db/* (CloudFormation 배포 시 설정)
    3. SSM: /fitcloud/{env_type}/db/* (기존 인프라 호환)
    """
    global _db_pool_cache
    
    if env_type in _db_pool_cache:
        return _db_pool_cache[env_type]
    
    # 1. 환경변수 확인
    db_host = os.environ.get("DB_HOST")
    db_user = os.environ.get("DB_USER")
    db_password = os.environ.get("DB_PASSWORD")
    db_name = os.environ.get("DB_NAME")
    db_port = int(os.environ.get("DB_PORT", "3306"))
    
    # 2. cloudtrail-bot SSM 경로 확인 (환경변수가 없는 경우)
    if not db_host:
        fitcloud_ssm_prefix = f"/fitcloud/prd/db/ts"
        db_host = _load_parameter_safe(f"{fitcloud_ssm_prefix}/host")
        
        if db_host:
            logger.info(f"DB 설정을 {fitcloud_ssm_prefix}에서 로드합니다")
            db_user = _load_parameter_safe(f"{fitcloud_ssm_prefix}/id")
            db_password = _load_parameter_safe(f"{fitcloud_ssm_prefix}/pw")
            db_name = "edp"
            db_port = 3306
    
    # 3. fitcloud SSM 경로 확인 (기존 인프라 호환)
    if not db_host:
        logger.info(f"DB 설정을 /fitcloud/{env_type}/db에서 로드합니다")
        db_host = load_parameter(f"/fitcloud/{env_type}/db/host")
        db_user = load_parameter(f"/fitcloud/{env_type}/db/user/admin/id")
        db_password = load_parameter(f"/fitcloud/{env_type}/db/user/admin/pw")
        db_name = load_parameter(f"/fitcloud/{env_type}/db/db")
    
    logger.info(f"DB 연결 설정: host={db_host}, db={db_name}, user={db_user}")
    
    db_config = {
        "host": db_host,
        "port": db_port,
        "user": db_user,
        "password": db_password,
        "database": db_name,
        "charset": "utf8"
    }
    
    pool = pymysqlpool.ConnectionPool(
        size=2, 
        maxsize=3, 
        pre_create_num=2, 
        name=f"credential_pool_{env_type}", 
        **db_config
    )
    _db_pool_cache[env_type] = pool
    return pool


def get_account_info_from_db(account_id: str, env_type: str = "dev") -> Optional[Dict[str, Any]]:
    """
    DB에서 단일 AWS Account의 정보를 조회합니다.
    
    Args:
        account_id: 조회할 AWS Account ID
        env_type: 환경 타입 (dev, prd 등)
    
    Returns:
        계정 정보 딕셔너리 또는 None
    """
    pool = get_db_connection_pool(env_type)
    conn = None
    curs = None
    
    try:
        conn = pool.get_connection()
        curs = conn.cursor()
        
        sql = """
            SELECT
                c.corp_id
                , c.corp_name
                , a.account_id
                , AES_DECRYPT(UNHEX(cross_account_role_name), SHA2(%s, 512)) as cross_account_role_name
                , a.assume_role_type
                , a.external_id
            FROM
            (
                SELECT
                    corp_id
                    , corp_name
                FROM
                corporation
                WHERE delete_flag = 0
            ) c INNER JOIN corporation_add_info cai ON cai.corp_id = c.corp_id
                INNER JOIN account a ON a.corp_id = c.corp_id
                WHERE 
                    a.account_id = %s
                    AND AES_DECRYPT(UNHEX(cross_account_role_name), SHA2(%s, 512)) != ''
                    AND a.delete_flag = 0
            LIMIT 1;
        """

        secret_title = _get_db_secret_title(env_type)
        curs.execute(sql, (secret_title, account_id, secret_title))
        
        row = curs.fetchone()
        if row:
            role_name = row[3]
            if isinstance(role_name, bytes):
                role_name = role_name.decode('utf-8').replace('b', '')
            
            return {
                'corp_id': row[0],
                'corp_name': row[1],
                'account_id': row[2],
                'role_name': role_name,
                'assume_role_type': row[4],
                'external_id': row[5] if row[5] else ""
            }
        return None
        
    except Exception as e:
        logger.error(f"DB 조회 실패: {e}")
        return None
        
    finally:
        if curs:
            curs.close()
        if conn:
            conn.close()


def search_account_by_name(corp_name: str, env_type: str = "dev") -> Optional[Dict[str, Any]]:
    """
    회사명으로 AWS Account 정보를 검색합니다.
    
    Args:
        corp_name: 검색할 회사명 (부분 일치)
        env_type: 환경 타입 (dev, prd 등)
    
    Returns:
        계정 정보 딕셔너리 또는 None
    """
    pool = get_db_connection_pool(env_type)
    conn = None
    curs = None
    
    try:
        conn = pool.get_connection()
        curs = conn.cursor()
        
        sql = """
            SELECT
                c.corp_id
                , c.corp_name
                , a.account_id
                , AES_DECRYPT(UNHEX(cross_account_role_name), SHA2(%s, 512)) as cross_account_role_name
                , a.assume_role_type
                , a.external_id
            FROM
            (
                SELECT
                    corp_id
                    , corp_name
                FROM
                corporation
                WHERE delete_flag = 0
                AND corp_name LIKE %s
            ) c INNER JOIN corporation_add_info cai ON cai.corp_id = c.corp_id
                INNER JOIN account a ON a.corp_id = c.corp_id
                WHERE 
                    AES_DECRYPT(UNHEX(cross_account_role_name), SHA2(%s, 512)) != ''
                    AND a.delete_flag = 0
            LIMIT 1;
        """

        secret_title = _get_db_secret_title(env_type)
        search_pattern = f"%{corp_name}%"
        curs.execute(sql, (secret_title, search_pattern, secret_title))
        
        row = curs.fetchone()
        if row:
            role_name = row[3]
            if isinstance(role_name, bytes):
                role_name = role_name.decode('utf-8').replace('b', '')
            
            return {
                'corp_id': row[0],
                'corp_name': row[1],
                'account_id': row[2],
                'role_name': role_name,
                'assume_role_type': row[4],
                'external_id': row[5] if row[5] else ""
            }
        return None
        
    except Exception as e:
        logger.error(f"DB 검색 실패: {e}")
        return None
        
    finally:
        if curs:
            curs.close()
        if conn:
            conn.close()


def get_assumed_role_credential(
    account_id: str, 
    role_name: str, 
    external_id: Optional[str] = None, 
    assume_role_type: str = "Role"
) -> Dict[str, str]:
    """
    단일 AWS Account에 대한 자격증명을 가져옵니다.
    
    Args:
        account_id: 대상 AWS Account ID
        role_name: Assume할 IAM Role 이름
        external_id: External ID (Role 타입일 경우 필요)
        assume_role_type: "User" 또는 "Role" (기본값: "Role")
    
    Returns:
        AWS 자격증명 딕셔너리 (accessKeyId, secretAccessKey, sessionToken)
    """
    role_arn = f"arn:aws:iam::{account_id}:role/{role_name}"
    
    if assume_role_type == "User":
        # IAM User의 Access Key를 사용하여 직접 Assume Role
        aws_access_key_id = load_parameter(CROSSACCOUNT_ACCESS_KEY)
        aws_secret_access_key = load_parameter(CROSSACCOUNT_SECRET_KEY)

        sts = boto3.client(
            'sts',
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key
        )

        assumed_role = sts.assume_role(
            RoleArn=role_arn,
            RoleSessionName='cloudtrail_bot_session'
        )

    else:
        # Bridge Account를 통한 Assume Role (Role Chaining)
        bridge_account_id = load_parameter(CROSSACCOUNT_BRIDGE_ACCOUNDID)
        bridge_external_id = load_parameter(CROSSACCOUNT_BRIDGE_EXTERNALID)
        bridge_role_name = load_parameter(CROSSACCOUNT_BRIDGE_ROLENAME)

        bridge_role_arn = f"arn:aws:iam::{bridge_account_id}:role/{bridge_role_name}"

        # 1단계: Bridge Role로 Assume
        sts = boto3.client('sts')
        bridge_assumed_role = sts.assume_role(
            RoleArn=bridge_role_arn,
            RoleSessionName='bridge_session',
            ExternalId=bridge_external_id
        )

        # 2단계: Bridge 자격증명으로 Target Role Assume
        sts = boto3.client(
            'sts',
            aws_access_key_id=bridge_assumed_role["Credentials"]["AccessKeyId"],
            aws_secret_access_key=bridge_assumed_role["Credentials"]["SecretAccessKey"],
            aws_session_token=bridge_assumed_role["Credentials"]["SessionToken"]
        )

        assume_params = {
            'RoleArn': role_arn,
            'RoleSessionName': 'cloudtrail_bot_session'
        }
        if external_id:
            assume_params['ExternalId'] = external_id

        assumed_role = sts.assume_role(**assume_params)

    return {
        'accessKeyId': assumed_role["Credentials"]["AccessKeyId"],
        'secretAccessKey': assumed_role["Credentials"]["SecretAccessKey"],
        'sessionToken': assumed_role["Credentials"]["SessionToken"]
    }


def get_boto3_client(service_name: str, credential: Dict[str, str], region_name: str = 'ap-northeast-2'):
    """
    자격증명을 사용하여 boto3 클라이언트를 생성합니다.
    
    Args:
        service_name: AWS 서비스 이름 (예: 's3', 'ec2', 'cloudtrail')
        credential: get_assumed_role_credential에서 반환된 자격증명
        region_name: AWS 리전 (기본값: 'ap-northeast-2')
    
    Returns:
        설정된 boto3 클라이언트
    """
    return boto3.client(
        service_name,
        region_name=region_name,
        aws_access_key_id=credential["accessKeyId"],
        aws_secret_access_key=credential["secretAccessKey"],
        aws_session_token=credential["sessionToken"]
    )


def get_credential_by_account_id(account_id: str, env_type: str = None) -> Optional[Dict[str, str]]:
    """
    Account ID로 DB에서 정보를 조회하고 자격증명을 가져옵니다.
    
    Args:
        account_id: 대상 AWS Account ID
        env_type: 환경 타입 (dev, prd 등). None이면 환경변수에서 읽음
    
    Returns:
        AWS 자격증명 딕셔너리 또는 None
    """
    if env_type is None:
        env_type = os.environ.get("ENV_TYPE", "dev")
    
    # DB에서 계정 정보 조회
    account_info = get_account_info_from_db(account_id, env_type)
    
    if not account_info:
        logger.warning(f"Account ID '{account_id}'에 대한 정보를 찾을 수 없습니다.")
        return None
    
    logger.info(f"DB 조회 성공: {account_info['corp_name']} ({account_id})")
    
    # 자격증명 획득
    credential = get_assumed_role_credential(
        account_id=account_info['account_id'],
        role_name=account_info['role_name'],
        external_id=account_info['external_id'],
        assume_role_type=account_info['assume_role_type']
    )
    
    return credential


def get_credential_by_corp_name(corp_name: str, env_type: str = None) -> Optional[Dict[str, Any]]:
    """
    회사명으로 계정을 검색하고 자격증명을 가져옵니다.
    
    Args:
        corp_name: 검색할 회사명
        env_type: 환경 타입 (dev, prd 등). None이면 환경변수에서 읽음
    
    Returns:
        계정 정보와 자격증명을 포함한 딕셔너리 또는 None
    """
    if env_type is None:
        env_type = os.environ.get("ENV_TYPE", "dev")
    
    # DB에서 계정 정보 검색
    account_info = search_account_by_name(corp_name, env_type)
    
    if not account_info:
        logger.warning(f"회사명 '{corp_name}'에 대한 계정을 찾을 수 없습니다.")
        return None
    
    logger.info(f"계정 검색 성공: {account_info['corp_name']} ({account_info['account_id']})")
    
    # 자격증명 획득
    credential = get_assumed_role_credential(
        account_id=account_info['account_id'],
        role_name=account_info['role_name'],
        external_id=account_info['external_id'],
        assume_role_type=account_info['assume_role_type']
    )
    
    return {
        'account_info': account_info,
        'credential': credential
    }

