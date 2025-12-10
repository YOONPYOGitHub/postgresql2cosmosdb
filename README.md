# PostgreSQL to Cosmos DB Migration Tool

[![한국어](https://img.shields.io/badge/Language-한국어-blue)](README.ko.md) [![English](https://img.shields.io/badge/Language-English-red)](README.md)

A Python tool for securely migrating user authentication data from Azure PostgreSQL to Cosmos DB for NoSQL.

## Key Features

🔐 **Entra ID Authentication**: Secure access using Microsoft Entra ID-based authentication without exposing keys  
⚡ **Fast Execution**: Quick dependency installation using the uv package manager  
🔄 **Idempotency Guaranteed**: Repeatable execution using Upsert method  
📝 **Automatic Conversion**: snake_case → camelCase, timestamp ISO conversion  
📊 **Detailed Logging**: Full process tracking with console and file logs

## Project Structure

```
postgresql2cosmosdb/
├── src/
│   └── postgresql2cosmosdb/
│       ├── __init__.py
│       ├── config.py      # Environment variable loading and configuration management
│       ├── migrate.py     # Migration script
│       └── validate.py    # Data integrity validation script
├── pyproject.toml         # Project configuration and dependencies
├── uv.lock                # uv lock file
├── .env.example           # Environment variable template
├── .env                   # Actual environment variables (needs to be created)
├── .gitignore
└── README.md
```

## Installation and Setup

### 1. Install uv (if not already installed)

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### 2. Install Dependencies

```bash
uv sync
```

This command creates a virtual environment and installs all dependencies.

### 3. Azure CLI Login (Required)

Azure CLI login is required as Cosmos DB uses Microsoft Entra ID authentication.

**Login Method** (WSL/Linux/headless environment):
```bash
az login --use-device-code
```

Environment with browser:
```bash
az login
```

**Verify Login:**
```bash
az account show
```

Expected output:
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

### 4. Cosmos DB Permission Setup

Two types of **RBAC permissions** are required to access Cosmos DB:

#### 📋 Required Permissions

| Permission Type | Role | Purpose | Configuration Location |
|----------------|------|---------|------------------------|
| **Data Plane RBAC** | Cosmos DB Built-in Data Contributor | Data read/write | Within Cosmos DB |
| **Control Plane IAM** | DocumentDB Account Contributor or Cosmos DB Account Reader Role | Metadata read | Azure subscription/resource group |

#### 🔧 Permission Setup Methods

##### 1. Data Plane RBAC Setup (Required - Data Read/Write)

Setup via Azure CLI:
```bash
# Set environment variables
RESOURCE_GROUP="<your-resource-group>"
COSMOS_ACCOUNT="<your-cosmos-account-name>"
PRINCIPAL_ID=$(az ad signed-in-user show --query id -o tsv)

# Assign Cosmos DB Built-in Data Contributor role
az cosmosdb sql role assignment create \
  --account-name "$COSMOS_ACCOUNT" \
  --resource-group "$RESOURCE_GROUP" \
  --role-definition-id "00000000-0000-0000-0000-000000000002" \
  --principal-id "$PRINCIPAL_ID" \
  --scope "/"
```

**Role Definition ID:**
- `00000000-0000-0000-0000-000000000002`: Cosmos DB Built-in Data Contributor

##### 2. Control Plane IAM Setup (Optional - Metadata Read, Portal Access)

Setup via Azure Portal:
1. Cosmos DB Account → **Access Control (IAM)**
2. **+ Add** → **Add role assignment**
3. In **Role** tab, select one of:
   - `DocumentDB Account Contributor` (read/write)
   - `Cosmos DB Account Reader Role` (read-only)
4. Add current user in **Members** tab
5. **Review + assign**

Or via Azure CLI:
```bash
# Get user Object ID
USER_ID=$(az ad signed-in-user show --query id -o tsv)

# Assign Cosmos DB Account Reader Role
az role assignment create \
  --role "Cosmos DB Account Reader Role" \
  --assignee "$USER_ID" \
  --scope "/subscriptions/<subscription-id>/resourceGroups/<resource-group>/providers/Microsoft.DocumentDB/databaseAccounts/<cosmos-account>"
```

#### ⏳ Permission Propagation Time

RBAC permissions may take **1-5 minutes** to propagate. Wait a moment after role assignment before testing.

### 5. Environment Variable Setup

Copy the `.env.example` file to create a `.env` file and modify with actual values:

```bash
cp .env.example .env
```

`.env` file contents:

```env
# Azure PostgreSQL Configuration
POSTGRES_HOST=your-postgresql-server.postgres.database.azure.com
POSTGRES_PORT=5432
POSTGRES_DATABASE=your_database_name
POSTGRES_USER=your_username
POSTGRES_PASSWORD=your_password
POSTGRES_SSLMODE=require

# Azure Cosmos DB Configuration (Entra ID Authentication)
COSMOS_ENDPOINT=https://your-cosmosdb-account.documents.azure.com:443/
COSMOS_DATABASE_ID=authdb
COSMOS_CONTAINER_ID=auth-users
```

**Note**: `COSMOS_KEY` is not required as Cosmos DB uses Entra ID authentication.

## Database Schema

### PostgreSQL (Source)

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

### Cosmos DB (Target)

- Database ID: `authdb`
- Container ID: `auth-users`
- Partition Key: `/userId`

Document structure:
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

## Execution

### 1. Run Migration

```bash
uv run migrate
```

### 2. Validate Data Integrity (After Migration)

```bash
uv run validate
```

After migration completes, this validates that data in PostgreSQL and Cosmos DB match exactly.

## Features

- ✅ **Entra ID Authentication**: Secure authentication through Microsoft Entra ID
- ✅ **Data Migration**: Complete data transfer from PostgreSQL to Cosmos DB
- ✅ **Data Integrity Validation**: Check data consistency between both databases after migration
- ✅ **Automatic Conversion**: snake_case → camelCase, timestamp ISO format conversion
- ✅ **Safe Execution**: Repeatable execution using Upsert method
- ✅ **Metadata Addition**: Automatic addition of `_migrated`, `_migrationDate` fields
- ✅ **Detailed Logging**: Console + file logs (`migration.log`, `validation.log`)
- ✅ **Error Handling**: Failure statistics and detailed discrepancy information

## Migration Log Example

When running migration, logs are output as follows:

```
2025-12-10 17:07:14 - INFO - ============================================================
2025-12-10 17:07:14 - INFO - PostgreSQL -> Cosmos DB Migration Started
2025-12-10 17:07:14 - INFO - ============================================================
2025-12-10 17:07:14 - INFO - Validating environment variables...
2025-12-10 17:07:14 - INFO - ✓ Environment variable validation complete
2025-12-10 17:07:17 - INFO - PostgreSQL connection successful
2025-12-10 17:07:17 - INFO - Fetching user data from PostgreSQL...
2025-12-10 17:07:17 - INFO - Fetched 3 users from PostgreSQL
2025-12-10 17:07:17 - INFO - Connecting to Cosmos DB using Microsoft Entra ID authentication...
2025-12-10 17:07:19 - INFO - Cosmos DB database 'authdb' connection successful
2025-12-10 17:07:21 - INFO - Cosmos DB container 'auth-users' connection successful
2025-12-10 17:07:21 - INFO - ============================================================
2025-12-10 17:07:21 - INFO - Data migration started
2025-12-10 17:07:21 - INFO - ============================================================
2025-12-10 17:07:21 - INFO - ✓ User 'u001' migration complete
2025-12-10 17:07:21 - INFO - ✓ User 'u002' migration complete
2025-12-10 17:07:21 - INFO - ✓ User 'u003' migration complete
2025-12-10 17:07:21 - INFO - ============================================================
2025-12-10 17:07:21 - INFO - Migration complete
2025-12-10 17:07:21 - INFO - Total users: 3
2025-12-10 17:07:21 - INFO - Success: 3
2025-12-10 17:07:21 - INFO - Failed: 0
2025-12-10 17:07:21 - INFO - ============================================================
2025-12-10 17:07:21 - INFO - PostgreSQL connection closed
2025-12-10 17:07:21 - INFO - All users migrated successfully!
```

Logs are saved to `migration.log` file simultaneously with console output.

## Precautions and Characteristics

### Security
- ✅ `.env` file is excluded from version control (included in `.gitignore`)
- ✅ No risk of key exposure using Microsoft Entra ID authentication
- ✅ PostgreSQL uses SSL connection (`sslmode=require`)

### Safety
- ✅ **Upsert Method**: Safe to run multiple times with the same `id` (idempotency guaranteed)
- ✅ **Automatic Container Creation**: Automatically creates Cosmos DB container if it doesn't exist
- ✅ **Transaction Logging**: All operations recorded in `migration.log`

### Data Transformation
- 📝 **Field Name Conversion**: PostgreSQL snake_case → Cosmos DB camelCase
  - `user_id` → `userId`
  - `password_hash` → `passwordHash`
  - `created_at` → `createdAt`, etc.
- 🕐 **Timestamp**: PostgreSQL TIMESTAMPTZ → ISO 8601 string
- 🌐 **IP Address**: PostgreSQL INET → string
- 📌 **Metadata Addition**: Automatic addition of `_migrated`, `_migrationDate` fields

## Tech Stack

### Package Management
- **[uv](https://github.com/astral-sh/uv)**: Fast Python package manager
- Supports Python 3.9 and above

### Main Dependencies
- **psycopg2-binary**: PostgreSQL database driver
- **azure-cosmos**: Azure Cosmos DB Python SDK
- **azure-identity**: Microsoft Entra ID authentication
- **python-dotenv**: Environment variable management

### Development Commands

```bash
# Install dependencies
uv sync

# Add package
uv add <package-name>

# Add development dependency
uv add --dev <package-name>

# Run migration
uv run migrate

# Check Python version
uv python list

# Recreate virtual environment
rm -rf .venv && uv sync
```

## Troubleshooting

### PostgreSQL Connection Error
- Verify current IP address is allowed in firewall rules
- Check SSL connection settings (`POSTGRES_SSLMODE=require`)

### Cosmos DB Connection Errors

#### "Unauthorized" or "Forbidden" Error

**Cause**: RBAC permissions not set

**Solution**:
1. Verify Azure CLI login:
   ```bash
   az login --use-device-code  # WSL/headless environment
   az account show
   ```

2. Set Data Plane RBAC (refer to permission setup section above):
   ```bash
   az cosmosdb sql role assignment create \
     --account-name <cosmos-account-name> \
     --resource-group <resource-group> \
     --role-definition-id "00000000-0000-0000-0000-000000000002" \
     --principal-id $(az ad signed-in-user show --query id -o tsv) \
     --scope "/"
   ```

3. Wait 1-5 minutes and retry (permission propagation time)

#### "Local Authorization is disabled" Error

**Cause**: Key-based authentication is disabled in Cosmos DB (security policy)

**Solution**: 
- This is normal. The tool is designed to use Microsoft Entra ID authentication.
- Complete the RBAC permission setup above and it will work normally with Microsoft Entra ID authentication.

#### "readMetadata" Permission Error

**Cause**: Control Plane IAM permission not set

**Solution**:
- Azure Portal > Cosmos DB Account > Access Control (IAM)
- Assign `Cosmos DB Account Reader Role` or `DocumentDB Account Contributor` role
- This permission is required for metadata read and Portal Data Explorer access.

#### Network Connection Error
- Check firewall settings: Azure Portal > Cosmos DB > Firewall and virtual networks
- Add current IP address or enable 'Allow access from Azure Portal'

### uv Related Issues
- If dependencies don't install when running `uv sync`, clear cache: `rm -rf .venv && uv sync`
- Python version issue: `uv python install 3.9` or install higher version

## License

MIT License

## Contributing

Issues and Pull Requests are welcome!
