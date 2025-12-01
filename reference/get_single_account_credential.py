import boto3
import pymysqlpool

# SSM Parameter Store 경로 설정
CROSSACCOUNT_ACCESS_KEY = '/access-key/crossaccount'
CROSSACCOUNT_SECRET_KEY = '/secret-key/crossaccount'

CROSSACCOUNT_BRIDGE_ACCOUNDID = '/crossaccountRoleBridge/bridgeAccountId'
CROSSACCOUNT_BRIDGE_EXTERNALID = '/crossaccountRoleBridge/bridgeExternalId'
CROSSACCOUNT_BRIDGE_ROLENAME = '/crossaccountRoleBridge/bridgeRoleName'

ssm = boto3.client("ssm")


def load_parameter(param_name):
    """SSM Parameter Store에서 파라미터 값을 가져옵니다."""
    return ssm.get_parameter(Name=param_name, WithDecryption=True)["Parameter"]["Value"]


def get_db_connection_pool(env_type):
    """DB 연결 풀을 생성합니다."""
    aws_mysql_host = load_parameter("/fitcloud/" + env_type + "/db/host")
    aws_mysql_id = load_parameter("/fitcloud/" + env_type + "/db/user/admin/id")
    aws_mysql_password = load_parameter("/fitcloud/" + env_type + "/db/user/admin/pw")
    aws_mysql_db = load_parameter("/fitcloud/" + env_type + "/db/db")
    
    db_config = {
        "host": aws_mysql_host,
        "port": 3306,
        "user": aws_mysql_id,
        "password": aws_mysql_password,
        "database": aws_mysql_db,
        "charset": "utf8"
    }
    
    return pymysqlpool.ConnectionPool(size=2, maxsize=3, pre_create_num=2, name="single_account_pool", **db_config)


def get_account_info_from_db(account_id, env_type="dev"):
    """
    DB에서 단일 AWS Account의 정보를 조회합니다.
    
    Args:
        account_id (str): 조회할 AWS Account ID
        env_type (str): 환경 타입 (dev, prd 등)
    
    Returns:
        dict: 계정 정보 (corp_name, role_name, assume_role_type, external_id)
              계정이 없으면 None 반환
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

        secret_title = load_parameter("/fitcloud/" + env_type + "/db/secret_title")
        curs.execute(sql, (secret_title, account_id, secret_title))
        
        row = curs.fetchone()
        if row:
            return {
                'corp_id': row[0],
                'corp_name': row[1],
                'account_id': row[2],
                'role_name': row[3].decode('utf-8').replace('b', '') if row[3] else None,
                'assume_role_type': row[4],
                'external_id': row[5] if row[5] else ""
            }
        return None
        
    except Exception as e:
        print(f"@@ ERROR !! DB 조회 실패: {e}")
        return None
        
    finally:
        if curs:
            curs.close()
        if conn:
            conn.close()


def get_assumed_role_credential(account_id, role_name, external_id=None, assume_role_type="Role"):
    """
    단일 AWS Account에 대한 자격증명을 가져옵니다.
    
    Args:
        account_id (str): 대상 AWS Account ID
        role_name (str): Assume할 IAM Role 이름
        external_id (str, optional): External ID (Role 타입일 경우 필요)
        assume_role_type (str): "User" 또는 "Role" (기본값: "Role")
    
    Returns:
        dict: AWS 자격증명 (accessKeyId, secretAccessKey, sessionToken)
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
            RoleSessionName='single_account_session'
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
            'RoleSessionName': 'single_account_session'
        }
        if external_id:
            assume_params['ExternalId'] = external_id

        assumed_role = sts.assume_role(**assume_params)

    return {
        'accessKeyId': assumed_role["Credentials"]["AccessKeyId"],
        'secretAccessKey': assumed_role["Credentials"]["SecretAccessKey"],
        'sessionToken': assumed_role["Credentials"]["SessionToken"]
    }


def get_boto3_client(service_name, credential, region_name='ap-northeast-2'):
    """
    자격증명을 사용하여 boto3 클라이언트를 생성합니다.
    
    Args:
        service_name (str): AWS 서비스 이름 (예: 's3', 'ec2', 'health')
        credential (dict): get_assumed_role_credential에서 반환된 자격증명
        region_name (str): AWS 리전 (기본값: 'ap-northeast-2')
    
    Returns:
        boto3.client: 설정된 boto3 클라이언트
    """
    return boto3.client(
        service_name,
        region_name=region_name,
        aws_access_key_id=credential["accessKeyId"],
        aws_secret_access_key=credential["secretAccessKey"],
        aws_session_token=credential["sessionToken"]
    )


def get_credential_by_account_id(account_id, env_type="dev"):
    """
    Account ID로 DB에서 정보를 조회하고 자격증명을 가져옵니다.
    
    Args:
        account_id (str): 대상 AWS Account ID
        env_type (str): 환경 타입 (dev, prd 등)
    
    Returns:
        dict: AWS 자격증명 (accessKeyId, secretAccessKey, sessionToken)
              실패 시 None 반환
    """
    # DB에서 계정 정보 조회
    account_info = get_account_info_from_db(account_id, env_type)
    
    if not account_info:
        print(f"❌ Account ID '{account_id}'에 대한 정보를 찾을 수 없습니다.")
        return None
    
    print(f"✅ DB 조회 성공: {account_info['corp_name']} ({account_id})")
    
    # 자격증명 획득
    credential = get_assumed_role_credential(
        account_id=account_info['account_id'],
        role_name=account_info['role_name'],
        external_id=account_info['external_id'],
        assume_role_type=account_info['assume_role_type']
    )
    
    return credential


# 사용 예시
if __name__ == "__main__":
    # 설정
    TARGET_ACCOUNT_ID = "123456789012"  # 조회할 AWS Account ID
    ENV_TYPE = "dev"  # 환경 타입 (dev, prd)

    try:
        # 방법 1: Account ID로 DB 조회 후 자격증명 획득 (권장)
        credential = get_credential_by_account_id(TARGET_ACCOUNT_ID, ENV_TYPE)
        
        if credential:
            print("✅ 자격증명 획득 성공!")
            print(f"Access Key ID: {credential['accessKeyId'][:10]}...")
            
            # 예시: S3 클라이언트 생성 및 버킷 목록 조회
            s3_client = get_boto3_client('s3', credential)
            buckets = s3_client.list_buckets()
            print(f"\n📦 S3 버킷 목록:")
            for bucket in buckets['Buckets']:
                print(f"  - {bucket['Name']}")
        
        # 방법 2: DB 조회와 자격증명 획득을 분리하여 사용
        # account_info = get_account_info_from_db(TARGET_ACCOUNT_ID, ENV_TYPE)
        # if account_info:
        #     credential = get_assumed_role_credential(
        #         account_id=account_info['account_id'],
        #         role_name=account_info['role_name'],
        #         external_id=account_info['external_id'],
        #         assume_role_type=account_info['assume_role_type']
        #     )
            
    except Exception as e:
        print(f"❌ 오류 발생: {e}")

