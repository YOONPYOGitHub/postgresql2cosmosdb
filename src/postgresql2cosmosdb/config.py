"""
환경 변수 로드 및 설정 관리
"""
import os
from dotenv import load_dotenv

# .env 파일 로드
load_dotenv()

# Azure PostgreSQL 설정
POSTGRES_CONFIG = {
    'host': os.getenv('POSTGRES_HOST'),
    'port': os.getenv('POSTGRES_PORT', '5432'),
    'database': os.getenv('POSTGRES_DATABASE'),
    'user': os.getenv('POSTGRES_USER'),
    'password': os.getenv('POSTGRES_PASSWORD'),
    'sslmode': os.getenv('POSTGRES_SSLMODE', 'require')
}

# Azure Cosmos DB 설정 (Entra ID 인증 사용)
COSMOS_CONFIG = {
    'endpoint': os.getenv('COSMOS_ENDPOINT'),
    'database_id': os.getenv('COSMOS_DATABASE_ID', 'authdb'),
    'container_id': os.getenv('COSMOS_CONTAINER_ID', 'auth-users')
}

# 마이그레이션 설정
def _get_batch_size():
    """배치 크기를 가져오고 유효성 검증"""
    batch_size_str = os.getenv('MIGRATION_BATCH_SIZE', '1000')
    try:
        batch_size = int(batch_size_str)
    except ValueError:
        raise ValueError(f"Invalid MIGRATION_BATCH_SIZE: '{batch_size_str}' is not a valid integer")
    
    if batch_size <= 0:
        raise ValueError(f"Invalid MIGRATION_BATCH_SIZE: {batch_size} must be positive")
    if batch_size > 10000:
        raise ValueError(f"Invalid MIGRATION_BATCH_SIZE: {batch_size} exceeds maximum of 10000")
    return batch_size

# 지연 로딩: 실제 사용 시점에 배치 크기 검증
MIGRATION_CONFIG = {
    'batch_size': None  # validate_config()에서 설정됨
}


def validate_config():
    """필수 환경 변수가 설정되었는지 확인"""
    errors = []
    
    # PostgreSQL 필수 필드만 명시적으로 검증
    required_pg_fields = ['host', 'database', 'user', 'password']
    for field in required_pg_fields:
        if not POSTGRES_CONFIG.get(field):
            errors.append(f"PostgreSQL {field} is not set")
    
    # Cosmos DB 필수 값 확인
    if not COSMOS_CONFIG['endpoint']:
        errors.append("Cosmos DB endpoint is not set")
    
    # 배치 크기 설정 및 검증 (지연 로딩)
    if MIGRATION_CONFIG['batch_size'] is None:
        try:
            MIGRATION_CONFIG['batch_size'] = _get_batch_size()
        except ValueError as e:
            errors.append(str(e))
    
    if errors:
        raise ValueError(f"Configuration errors:\n" + "\n".join(errors))
    
    return True
    
    return True
