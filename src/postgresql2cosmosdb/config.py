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


def validate_config():
    """필수 환경 변수가 설정되었는지 확인"""
    errors = []
    
    # PostgreSQL 필수 값 확인
    for key, value in POSTGRES_CONFIG.items():
        if not value and key != 'sslmode':
            errors.append(f"PostgreSQL {key} is not set")
    
    # Cosmos DB 필수 값 확인
    if not COSMOS_CONFIG['endpoint']:
        errors.append("Cosmos DB endpoint is not set")
    
    if errors:
        raise ValueError(f"Configuration errors:\n" + "\n".join(errors))
    
    return True
