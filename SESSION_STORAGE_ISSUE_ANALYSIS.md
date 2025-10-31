# Session Storage Issue Analysis

## Problem Statement

Sessions are being uploaded to S3 and MongoDB correctly, but they remain in memory (`queue_manager.multiturn_sessions`) after completion. This causes:

1. **Incorrect storage location reporting**: The `/multiturn-sessions` endpoint shows `_storage_location: "memory"` for completed sessions
2. **Missing S3 URLs**: Because sessions are treated as "in-memory", the API may not generate S3 presigned URLs for download
3. **Memory accumulation**: Completed sessions stay in memory indefinitely instead of being cleaned up

## Current Behavior

### What Works ✅

1. **S3 Upload**: Files are uploaded to S3 when sessions complete
   - Location: `agent_fastapi_server_multiturn.py:1738` - `_trigger_s3_upload_for_session()`
   - Method: `cloud_storage_manager.upload_session_to_cloud()`

2. **MongoDB Upload**: Session metadata is saved to MongoDB
   - Collection: `multiturn_sessions`
   - Includes: session data, turns, files, queries, etc.

3. **File Generation**: All required files are created
   - Reports, thinking process, query files, result JSON, snapshots
   - These files exist in local storage before S3 upload

### What Doesn't Work ❌

1. **Memory Cleanup**: Completed sessions are NOT removed from `queue_manager.multiturn_sessions`
   - Code at line 1893-1898 removes from `active_sessions` but NOT from `multiturn_sessions`

2. **Storage Location Detection**: `unified_session_manager.py:424` sets `_storage_location: "memory"` for any session in `queue_manager.multiturn_sessions`
   - This takes precedence over MongoDB/cloud storage
   - Results in incorrect storage location reporting

3. **URL Generation**: Sessions marked as "memory" may not get S3 presigned URLs
   - The `/results` endpoint checks storage location
   - "memory" sessions use local file paths instead of S3 URLs

## Code Locations

### Upload Process (WORKS)
```python
# agent_fastapi_server_multiturn.py:1738
queue_manager._trigger_s3_upload_for_session(user_request)

# agent_fastapi_server_multiturn.py:590-632
def _trigger_s3_upload_for_session(self, user_request: UserRequest):
    # Uploads files to S3 and metadata to MongoDB
    cloud_storage_manager.upload_session_to_cloud(...)
```

### Multi-turn Session Completion (PARTIAL)
```python
# agent_fastapi_server_multiturn.py:1050-1119
def complete_turn(self, session_id: str, turn_number: int, ...):
    # Updates turn data
    # Saves to local JSON: _save_multiturn_session(session)
    # Uploads to MongoDB (async thread)
    # BUT does NOT remove from queue_manager.multiturn_sessions
```

### Storage Location Detection (PROBLEM)
```python
# unified_session_manager.py:424
# Memory sessions take precedence
for session_id, session in self.queue_manager.multiturn_sessions.items():
    session_data = {
        "_storage_location": "memory",  # ⚠️ Always "memory"
        ...
    }
```

### Session Cleanup (INCOMPLETE)
```python
# agent_fastapi_server_multiturn.py:1893-1898
# Only removes from active_sessions, NOT multiturn_sessions
if user_request.session_id in self.active_sessions:
    del self.active_sessions[user_request.session_id]
```

## Solution Required

### Option 1: Remove Completed Sessions from Memory (Recommended)

After successful S3/MongoDB upload, remove the session from `queue_manager.multiturn_sessions`:

**Location**: `agent_fastapi_server_multiturn.py:1119` (after `complete_turn`)

```python
def complete_turn(self, session_id: str, turn_number: int, ...):
    # ... existing code ...

    # Upload to MongoDB (existing code)
    upload_thread.start()

    # NEW: Remove completed session from memory if all turns are done
    session = self.multiturn_sessions.get(session_id)
    if session and session.total_turns == turn_number:
        # All turns completed, upload finished, remove from memory
        def cleanup_after_upload():
            time.sleep(5)  # Wait for async upload to finish
            if session_id in self.multiturn_sessions:
                del self.multiturn_sessions[session_id]
                print(f"Removed completed session {session_id} from memory")

        cleanup_thread = threading.Thread(target=cleanup_after_upload, daemon=True)
        cleanup_thread.start()
```

### Option 2: Change Storage Location Logic

Modify `unified_session_manager.py` to check if session is complete and has been uploaded:

```python
# unified_session_manager.py:424
for session_id, session in self.queue_manager.multiturn_sessions.items():
    # Check if session is completed and uploaded
    is_complete = session.session_status == "completed"
    has_cloud_storage = await self._check_if_in_mongodb(session_id)

    storage_location = "cloud" if (is_complete and has_cloud_storage) else "memory"

    session_data = {
        "_storage_location": storage_location,
        ...
    }
```

### Option 3: Hybrid Approach (Best)

Combine both options:
1. Mark storage location correctly based on upload status
2. Clean up memory after successful verification
3. Keep recent sessions in memory for faster access (e.g., last hour)

## Impact Analysis

### Current Impact
- ✅ Files ARE available in S3
- ✅ Metadata IS in MongoDB
- ❌ API returns `_storage_location: "memory"`
- ❌ Download URLs may use local paths instead of S3 URLs
- ❌ Memory usage grows over time

### After Fix
- ✅ Files available in S3
- ✅ Metadata in MongoDB
- ✅ API returns `_storage_location: "mongodb"` or `"cloud"`
- ✅ Download URLs use S3 presigned URLs
- ✅ Memory cleaned up after upload

## Testing Verification

To verify the fix works:

```bash
# 1. Create a new session
curl -X POST https://API_URL/chat-queue -F "message=test" -F "user_id=Test user"

# 2. Wait for completion

# 3. Check sessions list
curl "https://API_URL/multiturn-sessions?user_id=Test%20user&limit=5"

# Expected: "_storage_location": "mongodb" (not "memory")

# 4. Get results
curl "https://API_URL/results/SESSION_ID?user_id=Test%20user"

# Expected: S3 URLs with presigned signatures (not local paths)
```

## Recommendation

Implement **Option 3 (Hybrid Approach)**:

1. **Immediate fix**: Update storage location detection logic to check MongoDB
2. **Memory optimization**: Clean up sessions from memory after successful cloud upload
3. **Performance**: Keep recent sessions (last 1 hour) in memory for fast access
4. **Reliability**: Always fall back to MongoDB if not in memory

This ensures:
- Correct storage location reporting
- S3 URLs always generated for download
- Memory doesn't grow indefinitely
- Fast access for recent sessions
