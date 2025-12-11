# PostgreSQL to Cosmos DB Migration Tool

[![한국어](https://img.shields.io/badge/Language-한국어-blue)](README.ko.md) [![English](https://img.shields.io/badge/Language-English-red)](README.md)

Azure PostgreSQL에서 Cosmos DB for NoSQL로 사용자 인증 데이터를 안전하게 마이그레이션하는 Python 도구입니다.

## 주요 특징

🔐 **Entra ID 인증**: Microsoft Entra ID 기반 인증으로 Key 노출 없이 안전한 접근  
⚡ **빠른 실행**: uv 패키지 관리자를 사용한 빠른 의존성 설치  
🔄 **멱등성 보장**: Upsert 방식으로 중복 실행 가능  
📝 **자동 변환**: snake_case → camelCase, 타임스탬프 ISO 변환  
📊 **상세 로깅**: 콘솔 및 파일 로그로 전체 프로세스 추적 가능  
🗂️ **배치 처리**: 사용자를 배치 단위로 읽고 마이그레이션 (배치 크기 `.env`에서 설정)

## 프로젝트 구조

```
postgresql2cosmosdb/
├── src/
│   └── postgresql2cosmosdb/
│       ├── __init__.py
│       ├── config.py      # 환경 변수 로드 및 설정 관리
│       ├── migrate.py     # 마이그레이션 스크립트
│       └── validate.py    # 데이터 정합성 검증 스크립트
├── pyproject.toml         # 프로젝트 설정 및 의존성
├── uv.lock                # uv 잠금 파일
├── .env.example           # 환경 변수 템플릿
├── .env                   # 실제 환경 변수 (생성 필요)
├── .gitignore
└── README.md
```

## 설치 및 설정

### 1. uv 설치 (아직 설치하지 않은 경우)

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### 2. 의존성 패키지 설치

```bash
uv sync
```

이 명령은 가상 환경을 생성하고 모든 의존성을 설치합니다.

### 3. Azure CLI 로그인 (필수)

Cosmos DB는 Microsoft Entra ID 인증을 사용하므로 Azure CLI 로그인이 필수입니다.

**로그인 방법** (WSL/Linux/headless 환경):
```bash
az login --use-device-code
```

브라우저가 있는 환경:
```bash
az login
```

**로그인 확인:**
```bash
az account show
```

정상 출력 예시:
```json
{
  "id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
  "name": "Your Subscription Name",
  "state": "Enabled",
  "user": {
    "name": "your-email@example.com",
    "type": "user"
  }
}
```

### 4. Cosmos DB 권한 설정

Cosmos DB에 접근하려면 **두 가지 RBAC 권한**이 필요합니다:

#### 📋 필요한 권한

| 권한 종류 | 역할 | 용도 | 설정 위치 |
|---------|-----|------|---------|
| **Data Plane RBAC** | Cosmos DB Built-in Data Contributor | 데이터 읽기/쓰기 | Cosmos DB 내부 |
| **Control Plane IAM** | DocumentDB Account Contributor 또는 Cosmos DB Account Reader Role | 메타데이터 읽기 | Azure 구독/리소스 그룹 |

#### 🔧 권한 설정 방법

##### 1. Data Plane RBAC 설정 (필수 - 데이터 읽기/쓰기)

Azure CLI로 설정:
```bash
# 환경 변수 설정
RESOURCE_GROUP="<your-resource-group>"
COSMOS_ACCOUNT="<your-cosmos-account-name>"
PRINCIPAL_ID=$(az ad signed-in-user show --query id -o tsv)

# Cosmos DB Built-in Data Contributor 역할 할당
az cosmosdb sql role assignment create \
  --account-name "$COSMOS_ACCOUNT" \
  --resource-group "$RESOURCE_GROUP" \
  --role-definition-id "00000000-0000-0000-0000-000000000002" \
  --principal-id "$PRINCIPAL_ID" \
  --scope "/"
```

**역할 정의 ID:**
- `00000000-0000-0000-0000-000000000002`: Cosmos DB Built-in Data Contributor

##### 2. Control Plane IAM 설정 (선택 - 메타데이터 읽기, Portal 접근)

Azure Portal에서 설정:
1. Cosmos DB 계정 → **Access Control (IAM)**
2. **+ Add** → **Add role assignment**
3. **Role** 탭에서 다음 중 하나 선택:
   - `DocumentDB Account Contributor` (읽기/쓰기)
   - `Cosmos DB Account Reader Role` (읽기 전용)
4. **Members** 탭에서 현재 사용자 추가
5. **Review + assign**

또는 Azure CLI:
```bash
# 사용자 Object ID 확인
USER_ID=$(az ad signed-in-user show --query id -o tsv)

# Cosmos DB Account Reader Role 할당
az role assignment create \
  --role "Cosmos DB Account Reader Role" \
  --assignee "$USER_ID" \
  --scope "/subscriptions/<subscription-id>/resourceGroups/<resource-group>/providers/Microsoft.DocumentDB/databaseAccounts/<cosmos-account>"
```

#### ⏳ 권한 적용 시간

RBAC 권한은 전파되는데 **1-5분** 정도 걸릴 수 있습니다. 역할 할당 후 잠시 기다렸다가 테스트하세요.

### 5. 환경 변수 설정

`.env.example` 파일을 복사하여 `.env` 파일을 생성하고, 실제 값으로 수정합니다:

```bash
cp .env.example .env
```

`.env` 파일 예시 (자세한 옵션은 `.env.example` 참고):

```env
# Azure PostgreSQL Configuration
POSTGRES_HOST=your-postgresql-server.postgres.database.azure.com
POSTGRES_PORT=5432
POSTGRES_DATABASE=your_database_name
POSTGRES_USER=your_username
POSTGRES_PASSWORD=your_password
POSTGRES_SSLMODE=require

# Azure Cosmos DB Configuration (Entra ID 인증)
COSMOS_ENDPOINT=https://your-cosmosdb-account.documents.azure.com:443/
COSMOS_DATABASE_ID=authdb
COSMOS_CONTAINER_ID=auth-users

# Migration Configuration
MIGRATION_BATCH_SIZE=1000
```

**참고**: Cosmos DB는 Entra ID 인증을 사용하므로 `COSMOS_KEY`가 필요하지 않습니다.

**배치 크기**: `MIGRATION_BATCH_SIZE`로 한 번에 처리할 사용자 수를 조절할 수 있습니다 (기본값: 1000). 대용량 데이터나 메모리 상황에 맞게 조정하세요.

## 데이터베이스 스키마

### PostgreSQL (소스)

```sql
CREATE TABLE auth_user (
    user_id              VARCHAR(50) PRIMARY KEY,
    email                TEXT        NOT NULL UNIQUE,
    password_hash        TEXT        NOT NULL,
    status               VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_login_at        TIMESTAMPTZ,
    last_login_ip        INET,
    failed_login_count   INT         NOT NULL DEFAULT 0,
    locked_until         TIMESTAMPTZ
);
```

### Cosmos DB (타겟)

- Database ID: `authdb`
- Container ID: `auth-users`
- Partition Key: `/userId`

문서 구조:
```json
{
  "id": "u001",
  "userId": "u001",
  "email": "alice@example.com",
  "passwordHash": "HASHED_pw_alice",
  "status": "ACTIVE",
  "createdAt": "2025-01-01T00:00:00+00:00",
  "lastLoginAt": "2025-01-15T10:30:00+00:00",
  "lastLoginIp": "192.168.0.10",
  "failedLoginCount": 0,
  "lockedUntil": null,
  "_migrated": true,
  "_migrationDate": "2025-12-10T12:00:00.000000"
}
```

## 실행 방법

### 1. 마이그레이션 실행 (배치 처리)

```bash
uv run migrate
```

### 2. 데이터 정합성 검증 (마이그레이션 후)

```bash
uv run validate
```

PostgreSQL은 배치로, Cosmos DB는 전체 쿼리로 데이터를 읽어 모든 필드를 비교합니다.

## 기능

- ✅ **Entra ID 인증**: Microsoft Entra ID를 통한 안전한 인증
- ✅ **배치 데이터 마이그레이션**: 사용자를 배치 단위로 읽고 마이그레이션 (설정 가능)
- ✅ **데이터 정합성 검증**: 마이그레이션 후 모든 필드를 비교 (PostgreSQL은 배치, Cosmos DB는 전체 쿼리)
- ✅ **자동 변환**: snake_case → camelCase, 타임스탬프 ISO 형식 변환
- ✅ **안전한 실행**: Upsert 방식으로 중복 실행 가능
- ✅ **상세한 로깅**: 콘솔 + 파일 로그 (`migration.log`, `validation.log`)
- ✅ **에러 핸들링**: 실패 통계 및 상세한 불일치 정보 제공

## 마이그레이션 로그 예시

마이그레이션 실행 시 다음과 같이 (배치 처리 기준) 로그가 출력됩니다:

```
2025-12-10 17:07:14 - INFO - ============================================================
2025-12-10 17:07:14 - INFO - PostgreSQL -> Cosmos DB 마이그레이션 시작
2025-12-10 17:07:14 - INFO - ============================================================
2025-12-10 17:07:14 - INFO - 환경 변수 검증 중...
2025-12-10 17:07:14 - INFO - ✓ 환경 변수 검증 완료
2025-12-10 17:07:17 - INFO - PostgreSQL 연결 성공
2025-12-10 17:07:17 - INFO - PostgreSQL에서 사용자 데이터 조회 중...
2025-12-10 17:07:17 - INFO - PostgreSQL에서 3명의 사용자 조회 완료
2025-12-10 17:07:17 - INFO - Microsoft Entra ID 인증을 사용하여 Cosmos DB 연결 중...
2025-12-10 17:07:19 - INFO - Cosmos DB 데이터베이스 'authdb' 연결 성공
2025-12-10 17:07:21 - INFO - Cosmos DB 컨테이너 'auth-users' 연결 성공
2025-12-10 17:07:21 - INFO - ============================================================
2025-12-10 17:07:21 - INFO - 데이터 마이그레이션 시작
2025-12-10 17:07:21 - INFO - ============================================================
2025-12-10 17:07:21 - INFO - ✓ 사용자 'u001' 마이그레이션 완료
2025-12-10 17:07:21 - INFO - ✓ 사용자 'u002' 마이그레이션 완료
2025-12-10 17:07:21 - INFO - ✓ 사용자 'u003' 마이그레이션 완료
2025-12-10 17:07:21 - INFO - ============================================================
2025-12-10 17:07:21 - INFO - 마이그레이션 완료
2025-12-10 17:07:21 - INFO - 총 사용자 수: 3
2025-12-10 17:07:21 - INFO - 성공: 3
2025-12-10 17:07:21 - INFO - 실패: 0
2025-12-10 17:07:21 - INFO - ============================================================
2025-12-10 17:07:21 - INFO - PostgreSQL 연결 종료
2025-12-10 17:07:21 - INFO - 모든 사용자 마이그레이션 성공!
```

로그는 콘솔 출력과 동시에 `migration.log` 파일에도 저장됩니다.

## 주의사항 및 특징

### 보안
- ✅ `.env` 파일은 버전 관리에서 제외됩니다 (`.gitignore`에 포함됨)
- ✅ Microsoft Entra ID 인증 사용으로 Key 노출 위험 없음
- ✅ PostgreSQL은 SSL 연결 사용 (`sslmode=require`)

### 안전성 & 배치 처리
- ✅ **Upsert 방식**: 동일한 `id`로 여러 번 실행해도 안전 (멱등성 보장)
- ✅ **배치 처리**: 사용자를 배치 단위로 읽고 마이그레이션 (기본 1000명, 설정 가능)
- ✅ **자동 컨테이너 생성**: Cosmos DB 컨테이너가 없으면 자동 생성
- ✅ **트랜잭션 로깅**: 모든 작업이 `migration.log`에 기록

### 데이터 변환 & 검증
- 📝 **필드명 변환**: PostgreSQL snake_case → Cosmos DB camelCase
  - `user_id` → `userId`
  - `password_hash` → `passwordHash`
  - `created_at` → `createdAt` 등
- 🕐 **타임스탬프**: PostgreSQL TIMESTAMPTZ → ISO 8601 문자열
- 🌐 **IP 주소**: PostgreSQL INET → 문자열
- 🔍 **검증**: 마이그레이션 후 모든 필드를 비교 (PostgreSQL은 배치, Cosmos DB는 전체 쿼리)

## 기술 스택

### 패키지 관리
- **[uv](https://github.com/astral-sh/uv)**: 빠른 Python 패키지 관리자
- Python 3.9 이상 지원

### 주요 의존성
- **psycopg2-binary**: PostgreSQL 데이터베이스 드라이버
- **azure-cosmos**: Azure Cosmos DB Python SDK
- **azure-identity**: Microsoft Entra ID 인증
- **python-dotenv**: 환경 변수 관리

### 개발 명령어

```bash
# 의존성 설치
uv sync

# 패키지 추가
uv add <package-name>

# 개발 의존성 추가
uv add --dev <package-name>

# 마이그레이션 실행
uv run migrate

# Python 버전 확인
uv python list

# 가상 환경 재생성
rm -rf .venv && uv sync
```

## 트러블슈팅

### PostgreSQL 연결 오류
- 방화벽 규칙에서 현재 IP 주소가 허용되었는지 확인
- SSL 연결 설정 확인 (`POSTGRES_SSLMODE=require`)

### Cosmos DB 연결 오류

#### "Unauthorized" 또는 "Forbidden" 오류

**원인**: RBAC 권한 미설정

**해결방법**:
1. Azure CLI 로그인 확인:
   ```bash
   az login --use-device-code  # WSL/headless 환경
   az account show
   ```

2. Data Plane RBAC 설정 (위 권한 설정 섹션 참조):
   ```bash
   az cosmosdb sql role assignment create \
     --account-name <cosmos-account-name> \
     --resource-group <resource-group> \
     --role-definition-id "00000000-0000-0000-0000-000000000002" \
     --principal-id $(az ad signed-in-user show --query id -o tsv) \
     --scope "/"
   ```

3. 1-5분 대기 후 재시도 (권한 전파 시간)

#### "Local Authorization is disabled" 오류

**원인**: Cosmos DB에서 Key 기반 인증이 비활성화되어 있음 (보안 정책)

**해결방법**: 
- 정상적인 상태입니다. Microsoft Entra ID 인증을 사용하도록 설계되었습니다.
- 위의 RBAC 권한 설정을 완료하면 Microsoft Entra ID 인증으로 정상 작동합니다.

#### "readMetadata" 권한 오류

**원인**: Control Plane IAM 권한 미설정

**해결방법**:
- Azure Portal > Cosmos DB 계정 > Access Control (IAM)
- `Cosmos DB Account Reader Role` 또는 `DocumentDB Account Contributor` 역할 할당
- 이 권한은 메타데이터 읽기 및 Portal Data Explorer 접근에 필요합니다.

#### 네트워크 연결 오류
- 방화벽 설정 확인: Azure Portal > Cosmos DB > Firewall and virtual networks
- 현재 IP 주소 추가 또는 'Allow access from Azure Portal' 활성화

### uv 관련 문제
- `uv sync` 실행 시 의존성이 설치되지 않으면 캐시를 삭제: `rm -rf .venv && uv sync`
- Python 버전 문제: `uv python install 3.9` 또는 더 높은 버전 설치
