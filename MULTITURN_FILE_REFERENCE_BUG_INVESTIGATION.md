# Multi-Turn Session File Reference Bug - Investigation Summary

## Date: 2025-11-24

## Problem Statement
Multi-turn sessions were saving incorrect file references to MongoDB. All turns were referencing Turn 1's files instead of their own unique files.

## Investigation Timeline

### Issue 1: Race Condition (FIXED)
**Location:** `agent_fastapi_server_multiturn.py` lines 1260-1325
**Problem:** Redundant async save in background thread could overwrite correct data with stale snapshot
**Fix:** Removed the entire async upload block (lines 1260-1325)
**Status:** ✅ Fixed but didn't solve main issue

### Issue 2: Missing Filename Field (FIXED)
**Location:** `agent_fastapi_server_multiturn.py` line 1255
**Problem:** File metadata dict had 'path' but no 'filename' field
**Fix:** Added filename extraction: `filename = os.path.basename(file_path)`
**Code:**
```python
filename = os.path.basename(file_path) if '/' in file_path or '\\' in file_path else file_path
file_metadata = {
    'path': file_path,
    'filename': filename,  # ← ADDED THIS
    'turn': turn_number,
    'created_at': datetime.now().isoformat()
}
```
**Status:** ✅ Fixed

### Issue 3: Session Reload Overwriting Correct Data (ACTIVE)
**Status:** 🔍 Currently Investigating

**Evidence from Debug Logs:**
1. `complete_turn()` receives CORRECT file paths for each turn:
   - Turn 1: `thinking_process_20251124_125527.txt`
   - Turn 2: `thinking_process_20251124_125623.txt`
   - Turn 3: `thinking_process_20251124_125702.txt`

2. Data is serialized CORRECTLY and saved to MongoDB:
   ```
   [DEBUG] Serialized data for MongoDB:
   [DEBUG]   Turn 1: TP file = thinking_process_20251124_125527.txt
   [DEBUG]   Turn 2: TP file = thinking_process_20251124_125623.txt
   [DEBUG]   Turn 3: TP file = thinking_process_20251124_125702.txt
   item f0412bfc-...837 has been successfully updated in MongoDB.
   ```

3. But querying MongoDB returns all turns with Turn 1's file

**Hypothesis:**
The session is being reloaded from MongoDB AFTER the correct save, and the reload is using stale/cached data. Possible causes:

1. **Memory cleanup** (lines 1296-1317 - already removed with async block)
2. **Session restoration from cloud** in `/continue-session` endpoint (lines 4260-4320)
3. **MongoDB caching** or eventual consistency issue
4. **Another save happening** from the individual turn upload to S3

**Key Observation:**
```
item f0412bfc-55fc-4cef-8077-eb039704a837_turn_2 has been successfully inserted in MongoDB.
Successfully uploaded session f0412bfc-55fc-4cef-8077-eb039704a837_turn_2 to S3
```

Individual turn sessions are being saved separately to MongoDB. This might be interfering.

## Next Steps

1. Check `/continue-session` endpoint (line 4240) - does it reload session from MongoDB?
2. Check if session is being removed from memory cache and reloaded
3. Check if there's another `_save_multiturn_session` call happening after the correct one
4. Add MORE debug logging to track when session is loaded/reloaded from MongoDB
5. Check MongoDB directly to see what's actually stored

## Files Modified

1. **agent_fastapi_server_multiturn.py**
   - Removed lines 1260-1325 (async upload block)
   - Added filename extraction at line 1254
   - Added debug logging to `_save_multiturn_session()` (lines 1088-1120)
   - Added debug logging to `complete_turn()` (lines 1220-1232, 1275-1281)

2. **cloud_storage_manager.py**
   - Modified line 206 to sort files by modification time (attempted fix, not the root cause)

## Test Session IDs
- `352fbb2d-1518-4a33-8206-53647b806b0b` - Test before fixes
- `bf32bbea-fc63-41d5-b4ad-82d46d6bbe7e` - Debug test 1
- `f0412bfc-55fc-4cef-8077-eb039704a837` - Final fix test

## Debug Log Locations
- `/tmp/fastapi_debug.log` - First debug run
- `/tmp/fastapi_debug2.log` - After filename fix

## Key Code Locations
- `complete_turn()`: Line 1206
- `_save_multiturn_session()`: Line 1083
- `/continue-session` endpoint: Line 4240
- Session restoration logic: Lines 4260-4320

## Resolution - BUG FIXED! ✅

### Final Test Results (2025-11-24 13:28)
After server restart, session loaded from MongoDB with CORRECT unique file references:
- Turn 1: `thinking_process_20251124_131144.txt` ✓
- Turn 2: `thinking_process_20251124_131208.txt` ✓
- Turn 3: `thinking_process_20251124_131237.txt` ✓

### Root Cause Identified
The bug was NOT in the session reload logic. The bug was FIXED by the two previous changes:

1. **Race Condition** - Redundant async save was overwriting correct data
2. **Missing Filename Field** - File metadata needed explicit filename extraction

### Debug Logging Added
Comprehensive debug logging added to trace session loads:
- `unified_session_manager.py`: Lines 705-712, 755-763 - Logs session loads from memory/MongoDB
- `agent_fastapi_server_multiturn.py`: Lines 1155-1170 - Logs QueueManager MongoDB loads
- `agent_fastapi_server_multiturn.py`: Lines 4342-4356 - Logs /continue-session cloud restoration
- `agent_fastapi_server_multiturn.py`: Lines 3777-3781 - Logs /results file extraction

### Verification
MongoDB query returns correct data:
```
[DEBUG LOAD FROM MONGODB] Session 2509a817-... has 3 turns:
[DEBUG LOAD FROM MONGODB]   Turn 1: TP=thinking_process_20251124_131144.txt
[DEBUG LOAD FROM MONGODB]   Turn 2: TP=thinking_process_20251124_131208.txt
[DEBUG LOAD FROM MONGODB]   Turn 3: TP=thinking_process_20251124_131237.txt
```

## Conclusion
**BUG IS FIXED!** The previous fixes (removing async save race condition + adding filename field) successfully resolved the issue. MongoDB now correctly stores and retrieves unique file references for each turn.
