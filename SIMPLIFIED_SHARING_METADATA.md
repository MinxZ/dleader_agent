# Simplified Sharing Metadata

## Overview
Per user request, the sharing metadata has been simplified to only two fields:
- `is_shared` (boolean)
- `shared_at` (timestamp or null)

All other sharing fields (share_tags, share_title, share_description) have been removed.

## What Changed

### Removed Fields
❌ `share_tags` - Array of tags for categorization
❌ `share_title` - Public title for sharing
❌ `share_description` - Public description
❌ `share_visibility` - Visibility level (already removed earlier)

### Kept Fields
✅ `is_shared` - Boolean indicating if session is shared
✅ `shared_at` - ISO timestamp when shared, or null if not shared

## Simplified Sharing Metadata

```typescript
{
  is_shared: boolean;         // true = shared, false = private
  shared_at: string | null;   // "2024-01-01T13:00:00Z" or null
}
```

### Default Values
All sessions now have:
```json
{
  "is_shared": false,
  "shared_at": null
}
```

## Updated APIs

### Share Session
**Endpoint**: `POST /share-session`

**Request**:
```json
{
  "session_id": "abc123",
  "user_id": "user123"
}
```

**Response**:
```json
{
  "success": true,
  "session_id": "abc123",
  "shared_at": "2024-01-01T13:00:00Z",
  "message": "Session shared successfully"
}
```

**Updates**:
- Local: `is_shared: true`, `shared_at: <timestamp>`
- MongoDB `multiturn_sessions`: Same
- MongoDB `community_sessions`: Added to collection

### Unshare Session
**Endpoint**: `POST /unshare-session`

**Request**:
```json
{
  "session_id": "abc123",
  "user_id": "user123"
}
```

**Response**:
```json
{
  "success": true,
  "session_id": "abc123",
  "message": "Session unshared successfully"
}
```

**Updates**:
- Local: `is_shared: false`, `shared_at: null`
- MongoDB `multiturn_sessions`: Same
- MongoDB `community_sessions`: Removed from collection

### Get All Multi-Turn Sessions
**Endpoint**: `GET /multiturn-sessions`

**Response**:
```json
{
  "sessions": [
    {
      "session_id": "abc123",
      "session_name": "My Analysis",
      "is_shared": false,
      "shared_at": null,
      "total_turns": 3,
      "created_at": "2024-01-01T10:00:00Z",
      ...
    }
  ]
}
```

## MongoDB Migration

### Migration Script
**File**: `migrate_sharing_defaults.py`

**Purpose**:
1. Set `is_shared: false` for all existing sessions (default)
2. Set `shared_at: null` for all existing sessions
3. Remove old fields: `share_tags`, `share_title`, `share_description`, `share_visibility`

**Usage**:
```bash
python migrate_sharing_defaults.py
```

**What it does**:
1. Connects to MongoDB `multiturn_sessions` collection
2. Analyzes sessions needing migration
3. Prompts for confirmation
4. Updates all sessions with default values
5. Removes deprecated fields
6. Verifies migration success

**Example Output**:
```
======================================================================
MongoDB Multi-Turn Sessions Migration
Setting default is_shared: false for all sessions
======================================================================

Connecting to MongoDB...
Database: dleader_agent
Collection: multiturn_sessions
✅ Connected to MongoDB successfully

Total sessions in collection: 150

Analyzing sessions...
  Sessions missing 'is_shared': 100
  Sessions with 'share_tags': 50
  Sessions with 'share_title': 50
  Sessions with 'share_description': 50

======================================================================
Migration will perform the following operations:
1. Set is_shared: false for all sessions (if not set)
2. Set shared_at: null for all sessions (if not set)
3. Remove old fields: share_tags, share_title, share_description
======================================================================

Proceed with migration? (yes/no): yes

🔄 Starting migration...

1. Setting default is_shared: false and shared_at: null...
   ✅ Updated 100 sessions with default values

2. Removing deprecated fields...
   ✅ Cleaned up 50 sessions

3. Ensuring all sessions have is_shared field...
   ✅ Ensured 150 sessions have is_shared field

======================================================================
Verification
======================================================================
Sessions with 'is_shared' field: 150/150
  - is_shared: true: 10
  - is_shared: false: 140

Remaining deprecated fields:
  - share_tags: 0
  - share_title: 0
  - share_description: 0

✅ Migration completed successfully!
All sessions now have is_shared: false by default
```

## Files Modified

### 1. Model Definition
**File**: `agent_fastapi_server_multiturn.py`

**Lines 126-128**: Removed fields from `MultiTurnSession`
```python
# Before:
is_shared: bool = False
shared_at: Optional[str] = None
share_tags: List[str] = []
share_title: Optional[str] = None
share_description: Optional[str] = None

# After:
is_shared: bool = False
shared_at: Optional[str] = None
```

**Lines 168-170**: Removed fields from `ShareSessionRequest`
```python
# Before:
class ShareSessionRequest(BaseModel):
    session_id: str
    title: str
    description: Optional[str] = None
    tags: List[str] = []
    user_id: Optional[str] = None

# After:
class ShareSessionRequest(BaseModel):
    session_id: str
    user_id: Optional[str] = None
```

### 2. Share API
**File**: `agent_fastapi_server_multiturn.py:3117-3162`

```python
# Only sets is_shared and shared_at
multiturn_session.is_shared = True
multiturn_session.shared_at = datetime.now().isoformat()

# MongoDB update
collection.update_one(
    {"session_id": request.session_id},
    {"$set": {
        "is_shared": True,
        "shared_at": multiturn_session.shared_at,
        "last_updated": datetime.now().isoformat()
    }}
)
```

### 3. Unshare API
**File**: `agent_fastapi_server_multiturn.py:3190-3216`

```python
# Clears sharing metadata
multiturn_session.is_shared = False
multiturn_session.shared_at = None

# MongoDB update
collection.update_one(
    {"session_id": session_id},
    {"$set": {
        "is_shared": False,
        "shared_at": None,
        "last_updated": datetime.now().isoformat()
    }}
)
```

### 4. Unified Session Manager
**File**: `unified_session_manager.py:387-390`

```python
# Only includes is_shared and shared_at in response
"is_shared": getattr(session, 'is_shared', False),
"shared_at": getattr(session, 'shared_at', None),
```

### 5. Cloud Storage Manager
**File**: `cloud_storage_manager.py:662-665`

```python
# Only uploads is_shared and shared_at to MongoDB
"is_shared": multiturn_session_data.get("is_shared", False),
"shared_at": multiturn_session_data.get("shared_at"),
```

### 6. API Documentation
**File**: `COMPLETE_API_DOCUMENTATION.md`

- Section 12: Updated with simplified fields
- Section 15: Simplified share request (no tags/title/description)
- Section 16: Updated unshare behavior

## Usage Examples

### Check if Session is Shared
```javascript
// Simple check
if (session.is_shared) {
  console.log('Session is shared');
  console.log('Shared on:', session.shared_at);
} else {
  console.log('Session is private');
}
```

### Share a Session
```bash
curl -X POST http://localhost:8001/share-session \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "abc123",
    "user_id": "user123"
  }'
```

### Unshare a Session
```bash
curl -X POST http://localhost:8001/unshare-session \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "abc123",
    "user_id": "user123"
  }'
```

### Get Sessions with Sharing Status
```bash
curl "http://localhost:8001/multiturn-sessions?user_id=user123" \
  | jq '.sessions[] | {session_id, is_shared, shared_at}'
```

**Response**:
```json
{
  "session_id": "abc123",
  "is_shared": false,
  "shared_at": null
}
{
  "session_id": "def456",
  "is_shared": true,
  "shared_at": "2024-01-01T13:00:00Z"
}
```

## MongoDB Schema

### multiturn_sessions Collection
```json
{
  "_id": "session123",
  "session_id": "session123",
  "session_name": "My Analysis",
  "user_id": "user123",
  "created_at": "2024-01-01T10:00:00Z",
  "last_updated": "2024-01-01T12:00:00Z",
  "total_turns": 3,
  "language": "en",
  "session_status": "completed",
  "first_query": "Analyze this...",
  "latest_query": "Generate report...",
  "turns": [...],

  // Sharing metadata (simplified)
  "is_shared": false,
  "shared_at": null,

  "uploaded_to_cloud_at": "2024-01-01T12:00:00Z"
}
```

## Benefits of Simplification

✅ **Simpler API**: Only need to send `session_id` and `user_id` to share
✅ **Less Storage**: Fewer fields in MongoDB
✅ **Easier Logic**: Just check `is_shared` boolean
✅ **Cleaner Code**: Removed unused fields
✅ **Better Performance**: Less data to transfer and store
✅ **Clear Intent**: Binary shared/not-shared status

## Migration Checklist

- [x] Remove share_tags, share_title, share_description from model
- [x] Update ShareSessionRequest to remove fields
- [x] Update share API to only set is_shared and shared_at
- [x] Update unshare API to only clear is_shared and shared_at
- [x] Update unified_session_manager response
- [x] Update cloud_storage_manager upload
- [x] Create MongoDB migration script
- [x] Update API documentation
- [ ] **Run migration script on production MongoDB**
- [ ] Verify all sessions have is_shared: false by default

## Running the Migration

### Step 1: Backup MongoDB (Recommended)
```bash
# Create backup before migration
mongodump --uri="<your-mongodb-uri>" --db=dleader_agent --collection=multiturn_sessions
```

### Step 2: Run Migration Script
```bash
cd /home/ubuntu/dleader_agent
python migrate_sharing_defaults.py
```

### Step 3: Verify Migration
```bash
# Check via API
curl "http://localhost:8001/multiturn-sessions?user_id=test_user" | jq '.sessions[] | {is_shared, shared_at}'

# All should show:
# {
#   "is_shared": false,
#   "shared_at": null
# }
```

### Step 4: Test Share/Unshare
```bash
# Share a session
curl -X POST http://localhost:8001/share-session \
  -H "Content-Type: application/json" \
  -d '{"session_id": "abc123", "user_id": "user123"}'

# Verify it's shared
curl "http://localhost:8001/multiturn-sessions?user_id=user123" | jq '.sessions[0].is_shared'
# Should return: true

# Unshare it
curl -X POST http://localhost:8001/unshare-session \
  -H "Content-Type: application/json" \
  -d '{"session_id": "abc123", "user_id": "user123"}'

# Verify it's unshared
curl "http://localhost:8001/multiturn-sessions?user_id=user123" | jq '.sessions[0].is_shared'
# Should return: false
```

## Summary

The sharing metadata has been simplified to just two fields:
- **is_shared**: Boolean flag (default: false)
- **shared_at**: Timestamp or null

All deprecated fields have been removed, and a migration script is provided to update existing MongoDB data.
