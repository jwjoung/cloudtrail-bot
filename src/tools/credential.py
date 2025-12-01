"""
AWS 계정 Credential 획득 모듈

DB에서 계정 정보를 조회하고 Bridge Role Chaining을 통해
대상 계정의 임시 자격증명을 획득합니다.
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
    """DB 연결 풀을 생성합니다 (캐싱)."""
    global _db_pool_cache
    
    if env_type in _db_pool_cache:
        return _db_pool_cache[env_type]
    
    aws_mysql_host = load_parameter(f"/fitcloud/{env_type}/db/host")
    aws_mysql_id = load_parameter(f"/fitcloud/{env_type}/db/user/admin/id")
    aws_mysql_password = load_parameter(f"/fitcloud/{env_type}/db/user/admin/pw")
    aws_mysql_db = load_parameter(f"/fitcloud/{env_type}/db/db")
    
    db_config = {
        "host": aws_mysql_host,
        "port": 3306,
        "user": aws_mysql_id,
        "password": aws_mysql_password,
        "database": aws_mysql_db,
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

        secret_title = load_parameter(f"/fitcloud/{env_type}/db/secret_title")
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

        secret_title = load_parameter(f"/fitcloud/{env_type}/db/secret_title")
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

