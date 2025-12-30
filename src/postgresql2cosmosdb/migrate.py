"""
Azure PostgreSQL에서 Cosmos DB로 로그인 정보 마이그레이션
"""
import sys
import logging
from datetime import datetime
import psycopg2
from psycopg2.extras import RealDictCursor
from azure.cosmos import CosmosClient, PartitionKey, exceptions
from azure.identity import DefaultAzureCredential
from .config import POSTGRES_CONFIG, COSMOS_CONFIG, MIGRATION_CONFIG, validate_config

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('migration.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


class PostgreSQLConnector:
    """PostgreSQL 연결 및 데이터 조회"""
    
    def __init__(self, config):
        self.config = config
        self.connection = None
    
    def __enter__(self):
        """Context manager 진입"""
        self.connect()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager 종료 - 자동으로 연결 해제"""
        self.close()
        return False
    
    def connect(self):
        """PostgreSQL 데이터베이스 연결"""
        try:
            self.connection = psycopg2.connect(
                host=self.config['host'],
                port=self.config['port'],
                database=self.config['database'],
                user=self.config['user'],
                password=self.config['password'],
                sslmode=self.config['sslmode']
            )
            logger.info("PostgreSQL 연결 성공")
            return True
        except psycopg2.Error as e:
            logger.error(f"PostgreSQL 연결 실패: {e}")
            return False
    
    def fetch_users_batch(self, last_user_id=None, batch_size=None):
        """auth_user 테이블에서 배치 단위로 사용자 데이터 조회 (Keyset Pagination)"""
        if batch_size is None:
            batch_size = MIGRATION_CONFIG['batch_size']
        
        if not self.connection:
            raise Exception("PostgreSQL 연결이 설정되지 않았습니다")
        
        try:
            with self.connection.cursor(cursor_factory=RealDictCursor) as cursor:
                if last_user_id:
                    query = """
                        SELECT 
                            user_id,
                            email,
                            password_hash,
                            status,
                            created_at,
                            last_login_at,
                            last_login_ip,
                            failed_login_count,
                            locked_until
                        FROM auth_user
                        WHERE user_id > %s
                        ORDER BY user_id
                        LIMIT %s
                    """
                    cursor.execute(query, (last_user_id, batch_size))
                else:
                    query = """
                        SELECT 
                            user_id,
                            email,
                            password_hash,
                            status,
                            created_at,
                            last_login_at,
                            last_login_ip,
                            failed_login_count,
                            locked_until
                        FROM auth_user
                        ORDER BY user_id
                        LIMIT %s
                    """
                    cursor.execute(query, (batch_size,))
                
                users = cursor.fetchall()
                return users
        except Exception as e:
            logger.error(f"사용자 데이터 조회 실패: {e}")
            raise
    
    def close(self):
        """연결 종료"""
        if self.connection:
            self.connection.close()
            logger.info("PostgreSQL 연결 종료")


class CosmosDBConnector:
    """Cosmos DB 연결 및 데이터 삽입"""
    
    # 클래스 레벨에서 credential 캐싱
    _credential = None
    
    def __init__(self, config):
        self.config = config
        self.client = None
        self.database = None
        self.container = None
    
    def connect(self):
        """Cosmos DB 연결 및 컨테이너 준비 (Microsoft Entra ID 인증)"""
        try:
            # DefaultAzureCredential을 사용하여 Microsoft Entra ID 인증
            # 로컬: Azure CLI (로그인 필요)
            # Azure: Managed Identity 자동 사용
            logger.info("Microsoft Entra ID 인증을 사용하여 Cosmos DB 연결 중...")
            
            # Credential 재사용 (토큰 캐싱 최적화)
            if CosmosDBConnector._credential is None:
                CosmosDBConnector._credential = DefaultAzureCredential()
            
            self.client = CosmosClient(
                self.config['endpoint'],
                CosmosDBConnector._credential
            )
            
            # 데이터베이스 가져오기 (없으면 생성)
            self.database = self.client.get_database_client(self.config['database_id'])
            logger.info(f"Cosmos DB 데이터베이스 '{self.config['database_id']}' 연결 성공")
            
            # 컨테이너 가져오기 (없으면 생성)
            try:
                self.container = self.database.get_container_client(self.config['container_id'])
                # 컨테이너 존재 확인
                self.container.read()
                logger.info(f"Cosmos DB 컨테이너 '{self.config['container_id']}' 연결 성공")
            except exceptions.CosmosResourceNotFoundError:
                logger.warning(f"컨테이너 '{self.config['container_id']}'가 존재하지 않습니다. 생성합니다...")
                self.container = self.database.create_container(
                    id=self.config['container_id'],
                    partition_key=PartitionKey(path="/userId")
                )
                logger.info(f"컨테이너 '{self.config['container_id']}' 생성 완료")
            
            return True
        except Exception as e:
            logger.error(f"Cosmos DB 연결 실패: {e}")
            return False
    
    def transform_user_data(self, pg_user):
        """PostgreSQL 데이터를 Cosmos DB 형식으로 변환"""
        # datetime 객체를 ISO 8601 문자열로 변환
        def to_iso_string(dt):
            return dt.isoformat() if dt else None
        
        # IP 주소를 문자열로 변환 (psycopg2가 이미 문자열로 변환하지만 안전성을 위해 확인)
        last_login_ip = pg_user['last_login_ip']
        if last_login_ip is not None and not isinstance(last_login_ip, str):
            last_login_ip = str(last_login_ip)
        
        cosmos_doc = {
            'id': pg_user['user_id'],  # Cosmos DB의 고유 id
            'userId': pg_user['user_id'],  # Partition key
            'email': pg_user['email'],
            'passwordHash': pg_user['password_hash'],
            'status': pg_user['status'],
            'createdAt': to_iso_string(pg_user['created_at']),
            'lastLoginAt': to_iso_string(pg_user['last_login_at']),
            'lastLoginIp': last_login_ip,
            'failedLoginCount': pg_user['failed_login_count'],
            'lockedUntil': to_iso_string(pg_user['locked_until'])
        }
        
        return cosmos_doc
    
    def upsert_user(self, user_doc):
        """사용자 문서를 Cosmos DB에 삽입 또는 업데이트"""
        try:
            self.container.upsert_item(user_doc)
            return True
        except exceptions.CosmosHttpResponseError as e:
            logger.error(f"사용자 '{user_doc['id']}' 삽입 실패 (HTTP {e.status_code}): {e.message}")
            return False
        except Exception as e:
            logger.error(f"사용자 '{user_doc['id']}' 삽입 실패 (예상치 못한 오류): {e}")
            return False
    
    def migrate_users(self, pg_users):
        """사용자 목록을 Cosmos DB로 마이그레이션"""
        success_count = 0
        fail_count = 0
        
        for pg_user in pg_users:
            try:
                cosmos_doc = self.transform_user_data(pg_user)
                if self.upsert_user(cosmos_doc):
                    success_count += 1
                    logger.debug(f"✓ 사용자 '{cosmos_doc['id']}' 마이그레이션 완료")
                else:
                    fail_count += 1
            except Exception as e:
                fail_count += 1
                logger.error(f"✗ 사용자 '{pg_user['user_id']}' 변환 실패: {e}")
        
        return success_count, fail_count


def main():
    """메인 마이그레이션 프로세스"""
    logger.info("=" * 60)
    logger.info("PostgreSQL -> Cosmos DB 마이그레이션 시작")
    logger.info("=" * 60)
    
    pg_connector = None
    exit_code = 1  # 기본값: 실패
    
    try:
        # 환경 변수 검증
        logger.info("환경 변수 검증 중...")
        validate_config()
        logger.info("✓ 환경 변수 검증 완료")
        
        # PostgreSQL 연결
        pg_connector = PostgreSQLConnector(POSTGRES_CONFIG)
        if not pg_connector.connect():
            logger.error("PostgreSQL 연결 실패로 마이그레이션 중단")
            sys.exit(1)
        
        # Cosmos DB 연결
        cosmos_connector = CosmosDBConnector(COSMOS_CONFIG)
        if not cosmos_connector.connect():
            logger.error("Cosmos DB 연결 실패로 마이그레이션 중단")
            sys.exit(1)
        
        logger.info("=" * 60)
        logger.info("데이터 마이그레이션 시작 (배치 처리)")
        logger.info(f"배치 크기: {MIGRATION_CONFIG['batch_size']}")
        logger.info("=" * 60)
        
        # 배치 단위로 마이그레이션
        batch_size = MIGRATION_CONFIG['batch_size']
        last_user_id = None
        total_success = 0
        total_fail = 0
        total_processed = 0
        batch_num = 0
        
        while True:
            batch_num += 1
            logger.info(f"배치 #{batch_num} 처리 중...")
            
            # 배치 데이터 조회
            users = pg_connector.fetch_users_batch(last_user_id, batch_size)
            
            if not users:
                logger.info("더 이상 마이그레이션할 사용자가 없습니다")
                break
            
            # 배치 마이그레이션
            success_count, fail_count = cosmos_connector.migrate_users(users)
            total_success += success_count
            total_fail += fail_count
            total_processed += len(users)
            
            logger.info(f"배치 #{batch_num} 완료: {len(users)}명 처리 (성공: {success_count}, 실패: {fail_count})")
            
            # 마지막 user_id 저장 (다음 배치의 시작점)
            last_user_id = users[-1]['user_id']
            
            # 배치 크기보다 작으면 마지막 배치
            if len(users) < batch_size:
                logger.info("마지막 배치 처리 완료")
                break
        
        # 결과 요약
        logger.info("=" * 60)
        logger.info("마이그레이션 완료")
        logger.info(f"총 처리: {total_processed}명")
        logger.info(f"성공: {total_success}명")
        logger.info(f"실패: {total_fail}명")
        logger.info(f"총 배치 수: {batch_num}")
        logger.info("=" * 60)
        
        # 결과에 따른 종료 코드 설정
        if total_fail > 0:
            logger.warning(f"일부 사용자 마이그레이션 실패 ({total_fail}명)")
            exit_code = 1
        else:
            logger.info("모든 사용자 마이그레이션 성공!")
            exit_code = 0
            
    except KeyboardInterrupt:
        logger.warning("사용자에 의해 마이그레이션이 중단되었습니다")
        exit_code = 130
    except Exception as e:
        logger.error(f"마이그레이션 중 오류 발생: {e}", exc_info=True)
        exit_code = 1
    finally:
        # PostgreSQL 연결 종료 보장
        if pg_connector and pg_connector.connection:
            pg_connector.close()
    
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
