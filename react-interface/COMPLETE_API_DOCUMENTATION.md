# Complete API Documentation for dleader_agent FastAPI Server

## Base URL
- Default: `http://52.192.211.135:8001`
- Local: `http://localhost:8001`

## All Available Endpoints (from agent_fastapi_server_multiturn.py)

### 1. Health Check
**Endpoint:** `GET /health`
**Purpose:** Check server availability
**Response:**
```json
{
  "status": "healthy",
  "timestamp": "2024-01-01T10:00:00Z"
}
```

---

### 2. Create New Chat Session
**Endpoint:** `POST /chat-queue`
**Purpose:** Start a new AI agent session
**Input (FormData):**
- `message` (string, required): User's query
- `language` (string): "en" or "jp" (default: "en")
- `user_id` (string, required): User identifier
- `files` (array): Optional file uploads

**Response:**
```json
{
  "session_id": "abc123",
  "status": "queued",
  "position": 1,
  "message": "Request queued successfully"
}
```

---

### 3. Get Session Progress (Deprecated)
**Endpoint:** `GET /progress/{session_id}`
**Note:** Use `/status/{session_id}` instead
**Query Params:**
- `user_id` (string, required)

---

### 4. Get Session Status ⭐ (Polled every 5 seconds)
**Endpoint:** `GET /status/{session_id}`
**Purpose:** Check processing status
**Query Params:**
- `user_id` (string, required)

**Response:**
```json
{
  "session_id": "abc123",
  "status": "queued|processing|completed|failed|error|cancelled",
  "is_complete": false,
  "created_at": "2024-01-01T10:00:00Z",
  "response": "Final response when complete",
  "partial_response": "Incremental updates",
  "error": "Error message if failed",
  "queue_position": 1,
  "progress": {
    "percentage": 45,
    "step": "Processing data..."
  }
}
```

---

### 5. Download Session ZIP
**Endpoint:** `GET /download/{session_id}`
**Purpose:** Download session ZIP file
**Query Params:**
- `user_id` (string, required)

**Response:** Binary ZIP file download

---

### 6. Get Session Results ⭐
**Endpoint:** `GET /results/{session_id}`
**Purpose:** Get structured JSON results for completed sessions
**Query Params:**
- `user_id` (string, required)

**Response:**
```json
{
  "session_id": "abc123",
  "status": "completed",
  "timestamp": "2024-01-01T10:00:00Z",
  "language": "en",
  "query": "User's query",
  "content": {
    "final_report": "## Markdown formatted report",
    "thinking_content": "Agent's thinking process",
    "raw_result": "Raw output"
  },
  "files": {
    "report_md": "/path/to/report.md",
    "thinking_process": "/path/to/thinking.txt",
    "session_zip": "/path/to/session.zip",
    "images": []
  }
}
```

---

### 7. Stop Running Task ⭐
**Endpoint:** `POST /stop/{session_id}`
**Purpose:** Cancel a queued or running task
**Query Params:**
- `user_id` (string, required)

**Response:**
```json
{
  "success": true,
  "message": "Task stopped"
}
```

---

### 8. Get Snapshots ⭐ (Polled every 5 seconds)
**Endpoint:** `GET /snapshots/{session_id}`
**Purpose:** Get thinking process snapshots
**Query Params:**
- `user_id` (string, required)

**Response:**
```json
{
  "snapshots": [
    {
      "timestamp": "2024-01-01T10:00:00Z",
      "content": {
        "thinking_content": "Step 1: Analyzing..."
      },
      "type": "periodic",
      "sequence": 1
    }
  ]
}
```

---

### 9. Get All Sessions ⭐
**Endpoint:** `GET /all-sessions`
**Purpose:** Get all sessions for a user
**Query Params:**
- `user_id` (string, optional): Filter by user

**Response:**
```json
{
  "sessions": [
    {
      "session_id": "abc123",
      "first_message": "Analyze this gene",
      "created_at": "2024-01-01T10:00:00Z",
      "status": "completed",
      "is_multi_turn": true,
      "total_turns": 2
    }
  ]
}
```

---

### 10. Continue Multi-Turn Session ⭐
**Endpoint:** `POST /continue-session`
**Purpose:** Add a new turn to existing session
**Input (FormData):**
- `session_id` (string, required): Original session ID
- `message` (string, required): Follow-up message
- `language` (string): Language code
- `user_id` (string, required): User identifier
- `files` (array): Optional file uploads

**Response:**
```json
{
  "session_id": "abc123",
  "turn_session_id": "abc123_turn_2",
  "turn_number": 2,
  "status": "queued",
  "position": 1,
  "uploaded_files": 0,
  "message": "Turn 2 added to queue"
}
```

**IMPORTANT:** Use `turn_session_id` for status checking!

---

### 11. Get Multi-Turn Session Details ⭐
**Endpoint:** `GET /multiturn-session/{session_id}`
**Purpose:** Get complete session history (replaces non-existent /session-history)
**Query Params:**
- `user_id` (string, required)

**Response:**
```json
{
  "session_id": "abc123",
  "user_id": "test_user_dleader",
  "created_at": "2024-01-01T10:00:00Z",
  "total_turns": 2,
  "is_complete": true,
  "turns": [
    {
      "turn_number": 1,
      "turn_id": "abc123_turn_1",
      "user_message": "First question",
      "agent_response": "First answer",
      "timestamp": "2024-01-01T10:00:00Z",
      "status": "completed"
    },
    {
      "turn_number": 2,
      "turn_id": "abc123_turn_2",
      "user_message": "Follow-up",
      "agent_response": "Second answer",
      "timestamp": "2024-01-01T10:05:00Z",
      "status": "completed"
    }
  ]
}
```

---

### 12. Get All Multi-Turn Sessions
**Endpoint:** `GET /multiturn-sessions`
**Purpose:** Get all multi-turn sessions
**Query Params:**
- `user_id` (string, optional): Filter by user

**Response:**
```json
{
  "sessions": [
    {
      "session_id": "abc123",
      "user_id": "test_user_dleader",
      "total_turns": 3,
      "created_at": "2024-01-01T10:00:00Z"
    }
  ]
}
```

---

### 13. Get Turn Report
**Endpoint:** `GET /turn-report/{session_id}/{turn_number}`
**Purpose:** Get specific turn details
**Query Params:**
- `user_id` (string, required)

**Response:** Turn-specific data

---

### 14. Get Session Context
**Endpoint:** `GET /session-context/{session_id}`
**Purpose:** Get accumulated context for multi-turn session
**Query Params:**
- `user_id` (string, required)

**Response:** Context data with all turns

---

### 15. Share Session
**Endpoint:** `POST /share-session`
**Purpose:** Share session publicly
**Input (JSON):**
```json
{
  "session_id": "abc123",
  "user_id": "test_user_dleader",
  "tags": ["genomics", "analysis"]
}
```

---

### 16. Unshare Session
**Endpoint:** `POST /unshare-session`
**Purpose:** Remove public sharing
**Input (JSON):**
```json
{
  "session_id": "abc123",
  "user_id": "test_user_dleader"
}
```

---

### 17. Search Shared Sessions
**Endpoint:** `POST /search-shared-sessions`
**Purpose:** Find publicly shared sessions
**Input (JSON):**
```json
{
  "query": "cancer",
  "tags": ["genomics"],
  "limit": 20
}
```

---

### 18. Get Shared Session
**Endpoint:** `GET /shared-session/{session_id}`
**Purpose:** Access publicly shared session

---

### 19. Get Popular Tags
**Endpoint:** `GET /popular-tags`
**Purpose:** Get trending tags
**Query Params:**
- `limit` (int): Max tags to return

---

### 20. Move to Trash
**Endpoint:** `POST /trash/{session_id}`
**Purpose:** Move session to trash
**Query Params:**
- `user_id` (string, required)

---

### 21. Restore from Trash
**Endpoint:** `POST /restore/{session_id}`
**Purpose:** Restore trashed session
**Query Params:**
- `user_id` (string, required)

---

### 22. Permanent Delete from Trash
**Endpoint:** `DELETE /permanent-delete/{session_id}`
**Purpose:** Permanently delete from trash
**Query Params:**
- `user_id` (string, required)

---

### 23. Get Trash Contents
**Endpoint:** `GET /trash`
**Purpose:** List all trashed sessions
**Query Params:**
- `user_id` (string, required)

**Response:**
```json
{
  "sessions": [],
  "total": 0
}
```

---

### 24. Empty Trash
**Endpoint:** `POST /empty-trash`
**Purpose:** Delete all trashed sessions
**Query Params:**
- `user_id` (string, required)

---

### 25. Hard Delete Session ⭐
**Endpoint:** `DELETE /hard-delete/{session_id}`
**Purpose:** Immediately delete session (bypasses trash)
**Query Params:**
- `user_id` (string, required)

**Response:**
```json
{
  "success": true,
  "message": "Session permanently deleted"
}
```

---

### 26. Get Download URLs
**Endpoint:** `GET /download-urls/{session_id}`
**Purpose:** Get S3 presigned URLs
**Query Params:**
- `user_id` (string, required)

**Response:**
```json
{
  "files": {
    "session_zip": {
      "presigned_url": "https://s3.amazonaws.com/...",
      "size": "2.5 MB",
      "expires_at": "2024-01-01T11:00:00Z"
    }
  },
  "expires_in": 60
}
```

---

## React Interface Usage

### Currently Used Endpoints ✅
1. `POST /chat-queue` - Start new session
2. `POST /continue-session` - Continue multi-turn
3. `GET /status/{session_id}` - Check status (5 sec polling)
4. `GET /snapshots/{session_id}` - Get snapshots (5 sec polling)
5. `GET /results/{session_id}` - Get final results
6. `POST /stop/{session_id}` - Stop task
7. `GET /all-sessions` - List sessions
8. `GET /multiturn-session/{session_id}` - Get session history
9. `GET /download-urls/{session_id}` - Get download links
10. `DELETE /hard-delete/{session_id}` - Delete session

### Fixed Issues 🔧
- ❌ `/session-history/{session_id}` → ✅ `/multiturn-session/{session_id}`
- ❌ `/session/{session_id}` DELETE → ✅ `/hard-delete/{session_id}` DELETE

---

## Multi-Turn Flow

### Correct Implementation:
1. **First Turn:**
   ```
   POST /chat-queue → session_id: "abc123"
   GET /status/abc123 (poll)
   ```

2. **Second Turn:**
   ```
   POST /continue-session → turn_session_id: "abc123_turn_2"
   GET /status/abc123_turn_2 (poll) ← Use turn_session_id!
   ```

3. **Third Turn:**
   ```
   POST /continue-session → turn_session_id: "abc123_turn_3"
   GET /status/abc123_turn_3 (poll) ← Use turn_session_id!
   ```

4. **View History:**
   ```
   GET /multiturn-session/abc123 → All turns
   ```

---

## Important Notes

### Session ID Management
- **Original Session:** `abc123` (conversation thread)
- **Turn Sessions:** `abc123_turn_2`, `abc123_turn_3` (individual turns)
- **Status Checking:** Always use turn_session_id for multi-turn status

### User Authentication
- All endpoints require `user_id` parameter
- Users can only access their own sessions
- 403 Forbidden for unauthorized access

### Polling Strategy
- Status: Every 5 seconds
- Snapshots: Every 5 seconds
- Stop when: `is_complete === true`

### Error Responses
- 404: Session not found
- 403: Access denied (wrong user)
- 422: Validation error
- 400: Bad request
- 500: Server error

---

## Testing with Default User

Default user: `test_user_dleader`

Example calls:
```bash
# Start new session
curl -X POST http://localhost:8001/chat-queue \
  -F "message=Analyze this gene" \
  -F "user_id=test_user_dleader"

# Check status
curl http://localhost:8001/status/abc123?user_id=test_user_dleader

# Continue session
curl -X POST http://localhost:8001/continue-session \
  -F "session_id=abc123" \
  -F "message=What about mutations?" \
  -F "user_id=test_user_dleader"

# Get history
curl http://localhost:8001/multiturn-session/abc123?user_id=test_user_dleader
```