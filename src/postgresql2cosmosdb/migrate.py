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
from .config import POSTGRES_CONFIG, COSMOS_CONFIG, validate_config

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
    
    def fetch_users(self):
        """auth_user 테이블에서 모든 사용자 데이터 조회"""
        if not self.connection:
            raise Exception("PostgreSQL 연결이 설정되지 않았습니다")
        
        try:
            with self.connection.cursor(cursor_factory=RealDictCursor) as cursor:
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
                """
                cursor.execute(query)
                users = cursor.fetchall()
                logger.info(f"PostgreSQL에서 {len(users)}명의 사용자 조회 완료")
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
            credential = DefaultAzureCredential()
            
            self.client = CosmosClient(
                self.config['endpoint'],
                credential
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
        
        # IP 주소를 문자열로 변환
        last_login_ip = str(pg_user['last_login_ip']) if pg_user['last_login_ip'] else None
        
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
            'lockedUntil': to_iso_string(pg_user['locked_until']),
            '_migrated': True,
            '_migrationDate': datetime.utcnow().isoformat()
        }
        
        return cosmos_doc
    
    def upsert_user(self, user_doc):
        """사용자 문서를 Cosmos DB에 삽입 또는 업데이트"""
        try:
            self.container.upsert_item(user_doc)
            return True
        except Exception as e:
            logger.error(f"사용자 '{user_doc['id']}' 삽입 실패: {e}")
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
                    logger.info(f"✓ 사용자 '{cosmos_doc['id']}' 마이그레이션 완료")
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
    
    try:
        # 환경 변수 검증
        logger.info("환경 변수 검증 중...")
        validate_config()
        logger.info("✓ 환경 변수 검증 완료")
        
        # PostgreSQL 연결 및 데이터 조회
        pg_connector = PostgreSQLConnector(POSTGRES_CONFIG)
        if not pg_connector.connect():
            logger.error("PostgreSQL 연결 실패로 마이그레이션 중단")
            sys.exit(1)
        
        logger.info("PostgreSQL에서 사용자 데이터 조회 중...")
        users = pg_connector.fetch_users()
        
        if not users:
            logger.warning("마이그레이션할 사용자가 없습니다")
            pg_connector.close()
            sys.exit(0)
        
        # Cosmos DB 연결 및 마이그레이션
        cosmos_connector = CosmosDBConnector(COSMOS_CONFIG)
        if not cosmos_connector.connect():
            logger.error("Cosmos DB 연결 실패로 마이그레이션 중단")
            pg_connector.close()
            sys.exit(1)
        
        logger.info("=" * 60)
        logger.info("데이터 마이그레이션 시작")
        logger.info("=" * 60)
        
        success_count, fail_count = cosmos_connector.migrate_users(users)
        
        # 결과 요약
        logger.info("=" * 60)
        logger.info("마이그레이션 완료")
        logger.info(f"총 사용자 수: {len(users)}")
        logger.info(f"성공: {success_count}")
        logger.info(f"실패: {fail_count}")
        logger.info("=" * 60)
        
        # PostgreSQL 연결 종료
        pg_connector.close()
        
        # 종료 코드 반환
        if fail_count > 0:
            logger.warning("일부 사용자 마이그레이션 실패")
            sys.exit(1)
        else:
            logger.info("모든 사용자 마이그레이션 성공!")
            sys.exit(0)
            
    except Exception as e:
        logger.error(f"마이그레이션 중 오류 발생: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
