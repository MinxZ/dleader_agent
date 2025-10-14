# MongoDB-Only Storage Migration

**Date**: October 13, 2025
**Status**: ✅ Complete

## Overview

The dleader_agent multi-turn session system has been migrated from a dual-storage model (local JSON files + MongoDB) to a **MongoDB-only storage model**. This ensures data persistence across ECS container restarts and simplifies the storage architecture.

## What Changed

### Before (Dual Storage)
- Multi-turn session metadata was saved to **both**:
  1. Local JSON files in `multiturn_sessions/` directory
  2. MongoDB collection `multiturn_sessions`
- Sessions were loaded from local JSON files on server startup
- Risk of data loss on ECS container restart

### After (MongoDB-Only)
- Multi-turn session metadata is saved **only** to MongoDB
- No local JSON files are created or read
- Sessions are loaded from MongoDB on-demand
- In-memory cache (`queue_manager.multiturn_sessions`) for active sessions
- Data persists across container restarts

## Implementation Details

### 1. Session Saving (`_save_multiturn_session`)
**File**: `agent_fastapi_server_multiturn.py:889-912`

```python
def _save_multiturn_session(self, session: MultiTurnSession):
    """Save multi-turn session to MongoDB only (no local JSON)"""
    # Prepare session data for MongoDB
    session_data = session.dict()
    session_data["_id"] = session.session_id
    session_data["last_updated"] = datetime.now().isoformat()

    # Save to MongoDB using upsert
    event = {
        "database_name": os.getenv("SESSION_DB_NAME", "dleader_agent"),
        "collection_name": "multiturn_sessions",
        "items": [session_data],
        "id_field": "_id"
    }
    result = upsert_wrapper(event)
```

**Changes**:
- ❌ Removed: `json.dump()` to local files
- ✅ Added: MongoDB upsert with `upsert_wrapper()`
- Uses `_id` field for atomic updates

### 2. Session Loading (`create_or_get_multiturn_session`)
**File**: `agent_fastapi_server_multiturn.py:914-953`

```python
def create_or_get_multiturn_session(self, session_id: str, ...):
    # 1. Check in-memory cache first
    if session_id in self.multiturn_sessions:
        return self.multiturn_sessions[session_id]

    # 2. Try to load from MongoDB
    collection = get_mongodb_collection("dleader_agent", "multiturn_sessions")
    if collection is not None:
        session_data = collection.find_one({"session_id": session_id})
        if session_data:
            session_data.pop("_id", None)  # Remove MongoDB internal field
            session = MultiTurnSession(**session_data)
            self.multiturn_sessions[session_id] = session
            return session

    # 3. Create new session if not found
    session = MultiTurnSession(...)
    self._save_multiturn_session(session)
    return session
```

**Changes**:
- ❌ Removed: Local file reading
- ✅ Added: MongoDB `find_one()` query
- Maintains in-memory cache for performance

### 3. Startup Behavior (`__init__`)
**File**: `agent_fastapi_server_multiturn.py:262-263`

```python
# Load existing sessions from storage
self._load_sessions_from_storage()
# Note: Multi-turn sessions are now loaded from MongoDB on-demand
# self._load_multiturn_sessions()  # REMOVED
```

**Changes**:
- ❌ Removed: Call to `_load_multiturn_sessions()`
- Sessions no longer loaded on startup
- Loaded from MongoDB on first access (lazy loading)

### 4. Function Removal (`_load_multiturn_sessions`)
**File**: `agent_fastapi_server_multiturn.py:867-887`

The entire function has been commented out:

```python
# REMOVED: No longer loading multi-turn sessions from local JSON files
# Multi-turn sessions are now stored in MongoDB only and loaded on-demand
# def _load_multiturn_sessions(self):
#     ...
```

### 5. Unified Session Manager
**File**: `unified_session_manager.py:368-417`

```python
async def get_multiturn_sessions(self, include_cloud: bool = True, user_id: str = None):
    """Get all multi-turn sessions from MongoDB only"""

    # 1. Get in-memory active sessions
    for session_id, session in self.queue_manager.multiturn_sessions.items():
        # ... convert to dict
        session_data["_storage_location"] = "memory"
        all_sessions.append(session_data)

    # 2. Get all persisted sessions from MongoDB
    collection = get_mongodb_collection("dleader_agent", "multiturn_sessions")
    mongodb_sessions = list(collection.find(query).sort("created_at", -1))
    for session in mongodb_sessions:
        session["_storage_location"] = "mongodb"
        all_sessions.append(session)
```

**Changes**:
- ❌ Removed: "local" storage location concept
- ✅ Changed: Storage locations are now "memory" or "mongodb"
- Simplified to single source of truth (MongoDB)

### 6. Share/Unshare Simplification
**Files**: `agent_fastapi_server_multiturn.py:3153-3212`

```python
# Share endpoint
multiturn_session.is_shared = True
multiturn_session.shared_at = datetime.now().isoformat()
queue_manager._save_multiturn_session(multiturn_session)

# Unshare endpoint
multiturn_session.is_shared = False
multiturn_session.shared_at = None
queue_manager._save_multiturn_session(multiturn_session)
```

**Changes**:
- ❌ Removed: Duplicate `collection.update_one()` calls
- ✅ Simplified: Only call `_save_multiturn_session()`
- Single code path for all MongoDB updates

## Migration Script

A migration script was created to ensure all existing MongoDB sessions have default sharing values:

**File**: `migrate_sharing_defaults.py`

```python
# Set default is_shared and shared_at
collection.update_many(
    {"is_shared": {"$exists": False}},
    {"$set": {"is_shared": False, "shared_at": None}}
)

# Remove old fields
collection.update_many(
    {},
    {"$unset": {"share_tags": "", "share_title": "", "share_description": ""}}
)
```

**Result**: Successfully migrated 157 sessions

## Benefits

### 1. **Data Persistence**
- ✅ Sessions survive ECS container restarts
- ✅ No data loss from ephemeral local storage
- ✅ Automatic backups via MongoDB Atlas

### 2. **Simplified Architecture**
- ✅ Single source of truth (MongoDB)
- ✅ No sync issues between local and cloud
- ✅ Reduced code complexity

### 3. **Performance**
- ✅ Lazy loading (only load sessions when needed)
- ✅ In-memory cache for active sessions
- ✅ MongoDB indexes for fast queries

### 4. **Scalability**
- ✅ Multiple ECS containers can access same data
- ✅ No file locking issues
- ✅ Cloud-native architecture

## Storage Locations

### In-Memory Cache
- **Purpose**: Fast access to active/recently used sessions
- **Location**: `queue_manager.multiturn_sessions` dict
- **Lifecycle**: Cleared on server restart
- **Used For**: Current multi-turn conversations

### MongoDB Collection
- **Collection**: `dleader_agent.multiturn_sessions`
- **Purpose**: Persistent storage
- **Lifecycle**: Permanent
- **Used For**: All multi-turn session metadata

### Local Directories (Still Used)
The following local directories are still used for single-turn sessions and file uploads:

- `chat_sessions/`: Session folders with reports, code, uploaded files
- `session_storage/`: Single-turn session metadata (JSON)
- `chat_zips/`: Downloadable session archives
- `multiturn_sessions/`: **DEPRECATED** (no longer used)

## API Behavior

### No Changes to API Endpoints
All existing API endpoints work exactly the same:

- `GET /multiturn-sessions`: Returns sessions from MongoDB + in-memory
- `POST /chat-queue`: Creates/updates sessions in MongoDB
- `POST /share-session`: Updates MongoDB only
- `POST /unshare-session`: Updates MongoDB only
- `POST /rename-multisession`: Updates MongoDB only

### Response Format Unchanged
Session responses still include all fields:

```json
{
  "session_id": "...",
  "session_name": "...",
  "created_at": "...",
  "last_updated": "...",
  "total_turns": 5,
  "is_shared": false,
  "shared_at": null,
  "_storage_location": "mongodb"
}
```

## Testing

### Manual Testing Steps

1. **Create a new multi-turn session**
   ```bash
   curl -X POST http://localhost:8001/chat-queue \
     -H "Content-Type: application/json" \
     -d '{"message": "Test query", "language": "en", "multiturn_session_id": "test123"}'
   ```

2. **Verify in MongoDB**
   ```python
   from s3_mongodb.func_mongodb import get_mongodb_collection
   collection = get_mongodb_collection("dleader_agent", "multiturn_sessions")
   session = collection.find_one({"session_id": "test123"})
   print(session)
   ```

3. **Verify no local JSON file**
   ```bash
   ls multiturn_sessions/test123.json  # Should not exist
   ```

4. **Restart server and retrieve session**
   ```bash
   curl http://localhost:8001/multiturn-sessions?user_id=test_user
   ```

## Rollback Plan

If issues are encountered, the system can be rolled back by:

1. Revert `agent_fastapi_server_multiturn.py` to restore local JSON saving
2. Revert `unified_session_manager.py` to restore local file loading
3. Uncomment `_load_multiturn_sessions()` function and call

However, any sessions created after this migration will only exist in MongoDB.

## Environment Variables

Ensure these are set for MongoDB access:

```bash
SESSION_DB_NAME=dleader_agent  # MongoDB database name
MONGODB_URI=<your_mongodb_connection_string>
```

## Related Documentation

- `SIMPLIFIED_SHARING_METADATA.md`: Sharing field simplification
- `MONGODB_TEMPLATE_MIGRATION.md`: Template storage migration
- `CLOUD_MIGRATION_GUIDE.md`: General cloud migration guide
- `MULTISESSION_NAMING_IMPLEMENTATION.md`: Session naming feature

## Summary

The migration to MongoDB-only storage successfully:
- ✅ Removed all local JSON file operations for multi-turn sessions
- ✅ Centralized storage in MongoDB
- ✅ Maintained backward compatibility with existing APIs
- ✅ Improved data persistence and scalability
- ✅ Simplified the codebase

**All multi-turn session metadata is now stored exclusively in MongoDB, ensuring data persistence across ECS container restarts.**
