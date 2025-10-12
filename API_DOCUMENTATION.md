# FastAPI Agent Server API Documentation

## Base URL
```
http://localhost:8001
```

## Authentication
All endpoints require a `user_id` parameter to identify the user and ensure proper access control.

---

## Core Endpoints

### 1. Health Check
Check if the server is running and get system status.

**Endpoint:** `GET /health`

**Response:**
```json
{
  "status": "healthy",
  "timestamp": "2025-09-25T02:15:00.000000",
  "queue_size": 0,
  "is_processing": false,
  "current_session": null,
  "multiturn_sessions": 14
}
```

---

### 2. Submit Chat Request
Queue a new chat/code execution request.

**Endpoint:** `POST /chat-queue`

**Request (Form Data):**
```
message: string (required) - The code or query to execute
user_id: string (required) - User identifier
language: string (required) - "en" or "jp"
session_id: string (optional) - For continuing existing session
files: File[] (optional) - Upload files to include
```

**Example cURL:**
```bash
curl -X POST http://localhost:8001/chat-queue \
  -F "message=print('Hello World')" \
  -F "user_id=john_doe" \
  -F "language=en"
```

**Response:**
```json
{
  "session_id": "17ac712c-656a-4ff3-bc08-84cba984ead1",
  "status": "queued",
  "message": "Request queued for processing",
  "position": 1
}
```

---

### 3. Get Session Status
Check the status of a session.

**Endpoint:** `GET /status/{session_id}`

**Parameters:**
- `user_id` (query): User identifier

**Example:**
```bash
curl "http://localhost:8001/status/17ac712c-656a-4ff3-bc08-84cba984ead1?user_id=john_doe"
```

**Response:**
```json
{
  "session_id": "17ac712c-656a-4ff3-bc08-84cba984ead1",
  "status": "completed",
  "result": "Output from execution",
  "created_at": "2025-09-25T02:00:00",
  "completed_at": "2025-09-25T02:00:30"
}
```

---

### 4. Stop Session
Stop a running session.

**Endpoint:** `POST /stop/{session_id}`

**Parameters:**
- `user_id` (query): User identifier

**Example:**
```bash
curl -X POST "http://localhost:8001/stop/17ac712c-656a-4ff3-bc08-84cba984ead1?user_id=john_doe"
```

**Response:**
```json
{
  "status": "success",
  "message": "Session stopped",
  "session_id": "17ac712c-656a-4ff3-bc08-84cba984ead1"
}
```

---

### 5. Get Session Results
Retrieve the results of a completed session.

**Endpoint:** `GET /results/{session_id}`

**Parameters:**
- `user_id` (query): User identifier

**Response:**
```json
{
  "session_id": "17ac712c-656a-4ff3-bc08-84cba984ead1",
  "status": "completed",
  "outputs": [
    {
      "type": "text",
      "content": "Hello World"
    },
    {
      "type": "plot",
      "path": "/path/to/plot.png"
    }
  ],
  "execution_time": 2.5
}
```

---

### 6. Get Snapshots
Get intermediate snapshots from a session.

**Endpoint:** `GET /snapshots/{session_id}`

**Parameters:**
- `user_id` (query): User identifier

**Response:**
```json
{
  "session_id": "17ac712c-656a-4ff3-bc08-84cba984ead1",
  "snapshots": [
    {
      "timestamp": "2025-09-25T02:00:10",
      "type": "plot",
      "url": "https://s3.amazonaws.com/bucket/snapshot1.png"
    }
  ]
}
```

---

### 7. Download Session Files
Download all files from a session as a ZIP.

**Endpoint:** `GET /download/{session_id}`

**Parameters:**
- `user_id` (query): User identifier

**Response:** Binary ZIP file or redirect to S3 URL

---

## Multi-turn Session Endpoints

### 8. Continue Session
Continue a multi-turn conversation.

**Endpoint:** `POST /continue-session`

**Request (JSON):**
```json
{
  "session_id": "17ac712c-656a-4ff3-bc08-84cba984ead1",
  "message": "Now create a bar chart",
  "user_id": "john_doe",
  "turn_number": 2
}
```

**Response:**
```json
{
  "status": "processing",
  "session_id": "17ac712c-656a-4ff3-bc08-84cba984ead1_turn_2",
  "turn_number": 2,
  "message": "Processing turn 2"
}
```

---

### 9. Get Multi-turn Session Info
Get information about a multi-turn session.

**Endpoint:** `GET /multiturn-session/{session_id}`

**Parameters:**
- `user_id` (query): User identifier

**Response:**
```json
{
  "base_session_id": "17ac712c-656a-4ff3-bc08-84cba984ead1",
  "total_turns": 3,
  "turns": [
    {
      "turn_number": 1,
      "status": "completed",
      "query": "Create a plot"
    },
    {
      "turn_number": 2,
      "status": "completed",
      "query": "Now create a bar chart"
    }
  ]
}
```

---

### 10. Get All Sessions
List all sessions for a user.

**Endpoint:** `GET /all-sessions`

**Parameters:**
- `user_id` (query): User identifier

**Response:**
```json
{
  "sessions": [
    {
      "session_id": "17ac712c-656a-4ff3-bc08-84cba984ead1",
      "created_at": "2025-09-25T02:00:00",
      "status": "completed",
      "query": "Create a plot"
    }
  ],
  "total_count": 15
}
```

---

## Trash System Endpoints

### 11. Move to Trash
Soft delete - move a session to trash.

**Endpoint:** `POST /trash/{session_id}`

**Parameters:**
- `user_id` (query): User identifier (required)

**Example:**
```bash
curl -X POST "http://localhost:8001/trash/17ac712c-656a-4ff3-bc08-84cba984ead1?user_id=john_doe"
```

**Response:**
```json
{
  "status": "success",
  "message": "Session moved to trash",
  "session_id": "17ac712c-656a-4ff3-bc08-84cba984ead1",
  "trashed_at": "2025-09-25T02:15:00.000000"
}
```

**Error Responses:**
- `404`: Session not found
- `403`: Access denied (not owner)
- `400`: Session already in trash

---

### 12. List Trash Sessions
Get all sessions in trash for a user.

**Endpoint:** `GET /trash`

**Parameters:**
- `user_id` (query): User identifier (required)

**Example:**
```bash
curl "http://localhost:8001/trash?user_id=john_doe"
```

**Response:**
```json
{
  "status": "success",
  "count": 3,
  "sessions": [
    {
      "session_id": "17ac712c-656a-4ff3-bc08-84cba984ead1",
      "query": "Create a plot",
      "status": "completed",
      "created_at": "2025-09-25T01:00:00",
      "trashed_at": "2025-09-25T02:15:00",
      "trashed_by": "john_doe",
      "user_id": "john_doe"
    }
  ]
}
```

---

### 13. Restore from Trash
Restore a session from trash back to active.

**Endpoint:** `POST /restore/{session_id}`

**Parameters:**
- `user_id` (query): User identifier (required)

**Example:**
```bash
curl -X POST "http://localhost:8001/restore/17ac712c-656a-4ff3-bc08-84cba984ead1?user_id=john_doe"
```

**Response:**
```json
{
  "status": "success",
  "message": "Session restored from trash",
  "session_id": "17ac712c-656a-4ff3-bc08-84cba984ead1",
  "restored_at": "2025-09-25T02:20:00.000000"
}
```

**Error Responses:**
- `404`: Session not found
- `403`: Access denied (not owner)
- `400`: Session is not in trash

---

### 14. Permanently Delete Session
Permanently delete a session and all associated resources.

**Endpoint:** `DELETE /permanent-delete/{session_id}`

**Parameters:**
- `user_id` (query): User identifier (required)
- `confirm` (query): Boolean confirmation (required)

**Example:**
```bash
# Without confirmation (will fail)
curl -X DELETE "http://localhost:8001/permanent-delete/17ac712c-656a-4ff3-bc08-84cba984ead1?user_id=john_doe&confirm=false"

# With confirmation (will delete)
curl -X DELETE "http://localhost:8001/permanent-delete/17ac712c-656a-4ff3-bc08-84cba984ead1?user_id=john_doe&confirm=true"
```

**Response:**
```json
{
  "status": "success",
  "message": "Session permanently deleted",
  "deleted_items": {
    "local_files": [
      "session_storage/17ac712c-656a-4ff3-bc08-84cba984ead1.json",
      "results/17ac712c-656a-4ff3-bc08-84cba984ead1.zip"
    ],
    "s3_files": [
      "sessions/17ac712c-656a-4ff3-bc08-84cba984ead1/output.txt",
      "sessions/17ac712c-656a-4ff3-bc08-84cba984ead1/plot.png"
    ],
    "mongodb_docs": [
      "session_17ac712c-656a-4ff3-bc08-84cba984ead1"
    ]
  }
}
```

**Error Responses:**
- `404`: Session not found
- `403`: Access denied (not owner)
- `400`: Confirmation required (when confirm=false)

---

### 15. Empty All Trash
Delete all sessions in trash for a user.

**Endpoint:** `POST /empty-trash`

**Parameters:**
- `user_id` (query): User identifier (required)
- `confirm` (query): Boolean confirmation (required)

**Example:**
```bash
# With confirmation
curl -X POST "http://localhost:8001/empty-trash?user_id=john_doe&confirm=true"
```

**Response:**
```json
{
  "status": "success",
  "message": "All trash sessions deleted",
  "deleted_count": 5,
  "deleted_sessions": [
    {
      "session_id": "17ac712c-656a-4ff3-bc08-84cba984ead1",
      "deleted_items": {
        "local_files": 2,
        "s3_files": 3,
        "mongodb_docs": 1
      }
    }
  ],
  "failed_deletions": []
}
```

**Error Responses:**
- `400`: Confirmation required (when confirm=false)
- `404`: No sessions in trash

---

## Error Response Format

All error responses follow this format:

```json
{
  "detail": "Error message describing what went wrong"
}
```

Common HTTP Status Codes:
- `200`: Success
- `400`: Bad Request (invalid parameters)
- `403`: Forbidden (access denied)
- `404`: Not Found
- `422`: Validation Error
- `500`: Internal Server Error

---

## Testing the API

### Quick Test Script
```python
import requests

BASE_URL = "http://localhost:8001"
USER_ID = "test_user"

# 1. Check health
response = requests.get(f"{BASE_URL}/health")
print("Health:", response.json())

# 2. Submit a chat request
response = requests.post(
    f"{BASE_URL}/chat-queue",
    data={
        "message": "print('Hello World')",
        "user_id": USER_ID,
        "language": "en"
    }
)
session_id = response.json().get("session_id")
print(f"Session created: {session_id}")

# 3. Check status
response = requests.get(f"{BASE_URL}/status/{session_id}?user_id={USER_ID}")
print("Status:", response.json().get("status"))

# 4. Move to trash
response = requests.post(f"{BASE_URL}/trash/{session_id}?user_id={USER_ID}")
print("Moved to trash:", response.json().get("status"))

# 5. List trash
response = requests.get(f"{BASE_URL}/trash?user_id={USER_ID}")
print("Trash count:", response.json().get("count"))

# 6. Permanently delete
response = requests.delete(
    f"{BASE_URL}/permanent-delete/{session_id}?user_id={USER_ID}&confirm=true"
)
print("Deleted:", response.json().get("status"))
```

---

## Rate Limits and Quotas

- Maximum file size per upload: 100MB
- Maximum files per request: 10
- Session timeout: 30 minutes
- Queue size limit: 100 requests

---

## WebSocket Support (Future)

The server is designed to support WebSocket connections for real-time updates. This feature is planned for future implementation.

---

## Notes for Developers

1. **Session IDs**: All session IDs are UUIDs. Multi-turn sessions append `_turn_N` to the base ID.

2. **File Storage**: Files are stored in:
   - Local: `session_storage/`, `results/`, `chat_zips/`
   - S3: `sessions/{session_id}/`
   - MongoDB: Collection `agent_sessions`

3. **Cleanup Policy**:
   - Sessions > 500MB are automatically flagged for cleanup
   - Trashed sessions are kept for 30 days before permanent deletion

4. **Security**:
   - All endpoints validate user ownership
   - Cross-user access is prevented
   - Sensitive operations require confirmation

5. **Auto-reload**: The server runs with auto-reload by default. Use `--no-reload` to disable.