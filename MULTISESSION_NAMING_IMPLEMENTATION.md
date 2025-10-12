# Multi-Session Naming Implementation

## Overview
This document describes the implementation of multi-session naming functionality, where each multi-turn session can have a custom name.

## Changes Made

### 1. Model Changes (`agent_fastapi_server_multiturn.py`)

#### Added `session_name` field to `MultiTurnSession` model
```python
class MultiTurnSession(BaseModel):
    session_id: str
    session_name: str = ""  # Name for the multi-session (default: first 30 chars of first query)
    # ... other fields
```

#### Created new request model for rename API
```python
class RenameMultiSessionRequest(BaseModel):
    session_id: str
    new_name: str
    user_id: str
```

### 2. Session Creation Changes

#### Updated `create_or_get_multiturn_session` method
- Added `initial_query` parameter
- Automatically sets `session_name` to first 30 characters of the query when creating new sessions
- Location: `agent_fastapi_server_multiturn.py:882`

```python
def create_or_get_multiturn_session(self, session_id: str, language: Language, user_id: str = None, initial_query: str = None) -> MultiTurnSession:
    # ... existing code ...
    session_name = ""
    if initial_query:
        session_name = initial_query[:30]

    session = MultiTurnSession(
        session_id=session_id,
        session_name=session_name,
        # ... other fields
    )
```

#### Updated `/chat-queue` endpoint
- Now passes the initial query message when creating multi-turn sessions
- Location: `agent_fastapi_server_multiturn.py:2368`

### 3. New Rename API Endpoint

#### Endpoint: `POST /rename-multisession`
- **Location**: `agent_fastapi_server_multiturn.py:3194`
- **Request Body**: `RenameMultiSessionRequest`
  - `session_id`: ID of the multi-turn session to rename
  - `new_name`: New name for the session
  - `user_id`: User ID for authorization

#### Features:
1. **Authorization**: Verifies that the user owns the session before allowing rename
2. **Local Storage Update**: Updates the session in memory and saves to local storage
3. **Cloud Storage Update**: If the session exists in MongoDB, updates it there as well
4. **Error Handling**: Returns appropriate HTTP errors for missing sessions or unauthorized access

#### Response:
```json
{
  "success": true,
  "session_id": "session-uuid",
  "new_name": "New Session Name",
  "message": "Session renamed successfully"
}
```

### 4. Storage Updates

#### Local Storage (`_save_multiturn_session`)
- Already saves the complete session object including the new `session_name` field
- Location: `agent_fastapi_server_multiturn.py:872`

#### Cloud Storage (`upload_multiturn_session`)
- Updated to include `session_name` in MongoDB metadata
- Location: `cloud_storage_manager.py:652`

```python
metadata = {
    "_id": session_id,
    "session_id": session_id,
    "session_name": multiturn_session_data.get("session_name", ""),
    # ... other fields
}
```

### 5. Unified Session Manager Updates

#### Updated `get_multiturn_sessions` method
- Now includes `session_name` when retrieving local multi-turn sessions
- Cloud sessions automatically include `session_name` from MongoDB
- Location: `unified_session_manager.py:378`

## API Usage Examples

### Create a New Multi-Turn Session
When you create a new session via `/chat-queue`, the session name is automatically set to the first 30 characters of your query.

```bash
curl -X POST http://localhost:8000/chat-queue \
  -F "message=What are the latest treatments for diabetes?" \
  -F "user_id=user123" \
  -F "language=en"
```

This will create a session with `session_name = "What are the latest treatment"`

### Rename an Existing Multi-Turn Session
```bash
curl -X POST http://localhost:8000/rename-multisession \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "abc123-def456",
    "new_name": "Diabetes Research Project",
    "user_id": "user123"
  }'
```

### Get All Multi-Turn Sessions (with names)
```bash
curl -X GET "http://localhost:8000/get-all-multiturn-sessions?user_id=user123"
```

Response will include `session_name` field:
```json
[
  {
    "session_id": "abc123-def456",
    "session_name": "Diabetes Research Project",
    "created_at": "2025-10-07T10:30:00",
    "total_turns": 5,
    ...
  }
]
```

## Key Design Decisions

1. **Initial Name from Query**: Using the first 30 characters of the query provides a meaningful default name without requiring explicit user input.

2. **Separate Sessions vs Multi-Sessions**:
   - **Session**: A single turn/query in the conversation
   - **Multi-Session**: Container for all turns in a multi-turn conversation
   - The `session_name` applies to the multi-session, not individual turns

3. **Authorization**: The rename API checks user ownership to prevent unauthorized modifications.

4. **Dual Storage**: Changes are persisted to both local storage (JSON files) and MongoDB (if available), ensuring consistency across storage backends.

5. **Graceful Degradation**: If MongoDB update fails during rename, the operation still succeeds locally and logs a warning rather than failing completely.

## Testing

To test the implementation:

1. Start a new multi-turn session with a query
2. Verify the session appears with the first 30 characters as the name
3. Use the rename API to change the name
4. Verify the name is updated in both local storage and MongoDB
5. Retrieve the multi-turn sessions list and verify the new name appears

## Files Modified

1. `agent_fastapi_server_multiturn.py` - Model, session creation, and rename API
2. `cloud_storage_manager.py` - MongoDB upload with session_name
3. `unified_session_manager.py` - Include session_name in retrieval
