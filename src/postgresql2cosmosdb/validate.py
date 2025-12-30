"""
PostgreSQL과 Cosmos DB 간 데이터 정합성 검증 스크립트
마이그레이션 후 두 데이터베이스의 데이터가 일치하는지 확인합니다.
"""
import sys
import logging
from datetime import datetime
import psycopg2
from psycopg2.extras import RealDictCursor
from azure.cosmos import CosmosClient
from azure.identity import DefaultAzureCredential
from .config import POSTGRES_CONFIG, COSMOS_CONFIG, MIGRATION_CONFIG, validate_config

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('validation.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


class DataValidator:
    """데이터 정합성 검증"""
    
    def __init__(self, pg_config, cosmos_config):
        self.pg_config = pg_config
        self.cosmos_config = cosmos_config
        self.pg_connection = None
        self.cosmos_client = None
        self.cosmos_container = None
        
    def connect_postgresql(self):
        """PostgreSQL 연결"""
        try:
            self.pg_connection = psycopg2.connect(
                host=self.pg_config['host'],
                port=self.pg_config['port'],
                database=self.pg_config['database'],
                user=self.pg_config['user'],
                password=self.pg_config['password'],
                sslmode=self.pg_config['sslmode']
            )
            logger.info("✓ PostgreSQL 연결 성공")
            return True
        except psycopg2.Error as e:
            logger.error(f"✗ PostgreSQL 연결 실패: {e}")
            return False
    
    def connect_cosmosdb(self):
        """Cosmos DB 연결"""
        try:
            credential = DefaultAzureCredential()
            self.cosmos_client = CosmosClient(
                self.cosmos_config['endpoint'],
                credential
            )
            database = self.cosmos_client.get_database_client(
                self.cosmos_config['database_id']
            )
            self.cosmos_container = database.get_container_client(
                self.cosmos_config['container_id']
            )
            logger.info("✓ Cosmos DB 연결 성공")
            return True
        except Exception as e:
            logger.error(f"✗ Cosmos DB 연결 실패: {e}")
            return False
    
    def fetch_postgresql_users(self):
        """PostgreSQL에서 모든 사용자 조회 (배치 처리)"""
        all_users = {}
        batch_size = MIGRATION_CONFIG['batch_size']
        
        # 배치 크기가 설정되지 않았으면 오류
        if batch_size is None:
            raise RuntimeError("MIGRATION_CONFIG['batch_size'] is not initialized. Call validate_config() first.")
        
        last_user_id = None
        total_count = 0
        
        try:
            while True:
                with self.pg_connection.cursor(cursor_factory=RealDictCursor) as cursor:
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
                    
                    if not users:
                        break
                    
                    for user in users:
                        all_users[user['user_id']] = dict(user)
                    
                    total_count += len(users)
                    last_user_id = users[-1]['user_id']
                    
                    if len(users) < batch_size:
                        break
            
            logger.info(f"PostgreSQL: {total_count}명 조회")
            return all_users
        except Exception as e:
            logger.error(f"PostgreSQL 데이터 조회 실패: {e}")
            raise
    
    def fetch_cosmosdb_users(self):
        """Cosmos DB에서 모든 사용자 조회 (배치 처리)"""
        all_users = {}
        try:
            query = "SELECT * FROM c"
            # 배치로 조회하여 메모리 효율성 향상
            items = self.cosmos_container.query_items(
                query=query,
                enable_cross_partition_query=True
            )
            
            count = 0
            for item in items:
                all_users[item['userId']] = item
                count += 1
                if count % 1000 == 0:
                    logger.debug(f"Cosmos DB 조회 진행 중: {count}명")
            
            logger.info(f"Cosmos DB: {count}명 조회")
            return all_users
        except Exception as e:
            logger.error(f"Cosmos DB 데이터 조회 실패: {e}")
            raise
    
    def normalize_timestamp(self, ts):
        """타임스탬프를 비교 가능한 형식으로 정규화"""
        if ts is None:
            return None
        if isinstance(ts, str):
            # ISO 형식 문자열을 datetime으로 변환
            return datetime.fromisoformat(ts.replace('Z', '+00:00'))
        return ts
    
    def compare_users(self, pg_user, cosmos_user):
        """개별 사용자 데이터 비교"""
        discrepancies = []
        
        # 필드 매핑 및 비교
        field_mappings = {
            'user_id': 'userId',
            'email': 'email',
            'password_hash': 'passwordHash',
            'status': 'status',
            'failed_login_count': 'failedLoginCount'
        }
        
        # 일반 필드 비교
        for pg_field, cosmos_field in field_mappings.items():
            pg_value = pg_user.get(pg_field)
            cosmos_value = cosmos_user.get(cosmos_field)
            
            if pg_value != cosmos_value:
                discrepancies.append({
                    'field': pg_field,
                    'postgresql': pg_value,
                    'cosmosdb': cosmos_value
                })
        
        # 타임스탬프 필드 비교 (초 단위까지만)
        timestamp_mappings = {
            'created_at': 'createdAt',
            'last_login_at': 'lastLoginAt',
            'locked_until': 'lockedUntil'
        }
        
        for pg_field, cosmos_field in timestamp_mappings.items():
            pg_ts = self.normalize_timestamp(pg_user.get(pg_field))
            cosmos_ts = self.normalize_timestamp(cosmos_user.get(cosmos_field))
            
            # None 값 처리
            if pg_ts is None and cosmos_ts is None:
                continue
            
            if pg_ts is None or cosmos_ts is None:
                discrepancies.append({
                    'field': pg_field,
                    'postgresql': str(pg_ts),
                    'cosmosdb': str(cosmos_ts)
                })
                continue
            
            # 초 단위까지만 비교 (밀리초 차이 무시)
            if abs((pg_ts - cosmos_ts).total_seconds()) > 1:
                discrepancies.append({
                    'field': pg_field,
                    'postgresql': pg_ts.isoformat(),
                    'cosmosdb': cosmos_ts.isoformat(),
                    'diff_seconds': abs((pg_ts - cosmos_ts).total_seconds())
                })
        
        # IP 주소 비교 (migrate.py와 동일한 로직 적용)
        pg_ip = pg_user.get('last_login_ip')
        if pg_ip is not None and not isinstance(pg_ip, str):
            pg_ip = str(pg_ip)
        cosmos_ip = cosmos_user.get('lastLoginIp')
        
        if pg_ip != cosmos_ip:
            discrepancies.append({
                'field': 'last_login_ip',
                'postgresql': pg_ip,
                'cosmosdb': cosmos_ip
            })
        
        return discrepancies
    
    def validate(self):
        """전체 데이터 정합성 검증"""
        logger.info("=" * 60)
        logger.info("데이터 정합성 검증 시작")
        logger.info("=" * 60)
        
        # PostgreSQL 데이터 조회
        pg_users = self.fetch_postgresql_users()
        
        # Cosmos DB 데이터 조회
        cosmos_users = self.fetch_cosmosdb_users()
        
        # 통계
        total_users = len(pg_users)
        matched_users = 0
        mismatched_users = 0
        missing_in_cosmos = []
        extra_in_cosmos = []
        detailed_mismatches = {}
        
        logger.info("=" * 60)
        logger.info("데이터 비교 중...")
        logger.info("=" * 60)
        
        # PostgreSQL 사용자가 Cosmos DB에 있는지 확인
        for user_id, pg_user in pg_users.items():
            if user_id not in cosmos_users:
                missing_in_cosmos.append(user_id)
                logger.warning(f"⚠ Cosmos DB에 누락: {user_id} ({pg_user['email']})")
            else:
                # 데이터 비교
                discrepancies = self.compare_users(pg_user, cosmos_users[user_id])
                
                if discrepancies:
                    mismatched_users += 1
                    detailed_mismatches[user_id] = discrepancies
                    logger.warning(f"⚠ 데이터 불일치: {user_id} ({pg_user['email']})")
                    for disc in discrepancies:
                        logger.warning(f"  - {disc['field']}: PG={disc['postgresql']} vs Cosmos={disc['cosmosdb']}")
                else:
                    matched_users += 1
                    logger.debug(f"✓ 일치: {user_id} ({pg_user['email']})")
                    # 주기적으로 진행 상황 출력
                    if matched_users % 100 == 0:
                        logger.info(f"진행 상황: {matched_users + mismatched_users}/{total_users} 검증 완료")
        
        # Cosmos DB에만 있는 사용자 확인
        for user_id in cosmos_users:
            if user_id not in pg_users:
                extra_in_cosmos.append(user_id)
                logger.warning(f"⚠ Cosmos DB에만 존재: {user_id}")
        
        # 결과 요약
        logger.info("=" * 60)
        logger.info("검증 결과 요약")
        logger.info("=" * 60)
        logger.info(f"총 사용자 수 (PostgreSQL): {total_users}")
        logger.info(f"총 사용자 수 (Cosmos DB): {len(cosmos_users)}")
        logger.info(f"완전 일치: {matched_users}")
        logger.info(f"데이터 불일치: {mismatched_users}")
        logger.info(f"Cosmos DB 누락: {len(missing_in_cosmos)}")
        logger.info(f"Cosmos DB 추가: {len(extra_in_cosmos)}")
        
        if missing_in_cosmos:
            logger.warning(f"\n누락된 사용자 ID: {', '.join(missing_in_cosmos)}")
        
        if extra_in_cosmos:
            logger.warning(f"\n추가된 사용자 ID: {', '.join(extra_in_cosmos)}")
        
        logger.info("=" * 60)
        
        # 검증 성공 여부
        is_valid = (
            len(missing_in_cosmos) == 0 and
            len(extra_in_cosmos) == 0 and
            mismatched_users == 0
        )
        
        if is_valid:
            logger.info("✅ 검증 성공: 모든 데이터가 정확하게 마이그레이션되었습니다!")
            return True
        else:
            logger.error("❌ 검증 실패: 데이터 불일치가 발견되었습니다.")
            return False
    
    def close(self):
        """연결 종료"""
        if self.pg_connection:
            self.pg_connection.close()
            logger.info("PostgreSQL 연결 종료")


def main():
    """메인 실행 함수"""
    validator = None
    exit_code = 1  # 기본값: 실패
    
    try:
        # 환경 변수 검증
        logger.info("환경 변수 검증 중...")
        validate_config()
        
        # 검증 실행
        validator = DataValidator(POSTGRES_CONFIG, COSMOS_CONFIG)
        
        if not validator.connect_postgresql():
            sys.exit(1)
        
        if not validator.connect_cosmosdb():
            sys.exit(1)
        
        is_valid = validator.validate()
        exit_code = 0 if is_valid else 1
        
    except KeyboardInterrupt:
        logger.warning("사용자에 의해 검증이 중단되었습니다")
        exit_code = 130
    except Exception as e:
        logger.error(f"검증 중 오류 발생: {e}", exc_info=True)
        exit_code = 1
    finally:
        # 연결 종료 보장
        if validator:
            validator.close()
    
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
