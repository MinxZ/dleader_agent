# API Endpoints Reference

## Overview
The React interface communicates with the FastAPI backend server (default: `http://52.192.211.135:8001`).
Status and snapshots are checked every 5 seconds during active sessions.

## Endpoints Called by the React Interface

### 1. Health Check
- **Endpoint:** `GET /health`
- **Purpose:** Check if the FastAPI server is running
- **Called:** On initial load and connection attempts
- **Response:** Status 200 if healthy

### 2. Submit New Request
- **Endpoint:** `POST /chat-queue`
- **Purpose:** Start a new conversation/session
- **Called:** When sending the first message in a new chat
- **Payload:** FormData with:
  - `message`: User's message
  - `language`: Language code (e.g., 'en')
  - `user_id`: User identifier
  - `files`: Optional file uploads
- **Response:** `{ session_id: string }`

### 3. Continue Session
- **Endpoint:** `POST /continue-session`
- **Purpose:** Continue an existing multi-turn conversation
- **Called:** When sending follow-up messages in an existing chat
- **Payload:** FormData with:
  - `session_id`: Existing session ID
  - `message`: Follow-up message
  - `language`: Language code
  - `user_id`: User identifier
  - `files`: Optional file uploads
- **Response:** Session continuation data

### 4. Get Status (Called every 5 seconds)
- **Endpoint:** `GET /status/{sessionId}`
- **Purpose:** Check the processing status of a session
- **Called:** Every 5 seconds while a task is running
- **Query Params:** `user_id`
- **Response:**
  ```json
  {
    "status": "queued|running|completed|failed",
    "response": "...",
    "partial_response": "...",
    "error": "..."
  }
  ```

### 5. Get Snapshots (Called every 5 seconds)
- **Endpoint:** `GET /snapshots/{sessionId}`
- **Purpose:** Get thinking process snapshots
- **Called:** Every 5 seconds while a task is running
- **Query Params:** `user_id`
- **Response:**
  ```json
  {
    "snapshots": [
      {
        "timestamp": "...",
        "content": {
          "thinking_content": "..."
        }
      }
    ]
  }
  ```

### 6. Stop Task
- **Endpoint:** `POST /stop/{sessionId}`
- **Purpose:** Cancel a running or queued task
- **Called:** When user clicks the stop button
- **Query Params:** `user_id`
- **Response:** Status 200 if successful

### 7. Get All Sessions
- **Endpoint:** `GET /all-sessions`
- **Purpose:** Retrieve all user sessions for the sidebar
- **Called:** On app load and after completing tasks
- **Query Params:** `user_id`
- **Response:**
  ```json
  {
    "sessions": [
      {
        "session_id": "...",
        "first_message": "...",
        "status": "..."
      }
    ]
  }
  ```

### 8. Get Session History
- **Endpoint:** `GET /session-history/{sessionId}`
- **Purpose:** Get full conversation history for a session
- **Called:** When user selects a session from the sidebar
- **Query Params:** `user_id`
- **Response:**
  ```json
  {
    "turns": [
      {
        "message": "...",
        "response": "..."
      }
    ]
  }
  ```

### 9. Get Download URLs
- **Endpoint:** `GET /download-urls/{sessionId}`
- **Purpose:** Get S3 presigned URLs for downloading session files
- **Called:** When a task completes successfully
- **Query Params:** `user_id`
- **Response:**
  ```json
  {
    "files": {
      "session_zip": {
        "presigned_url": "...",
        "size": "..."
      }
    },
    "expires_in": 60
  }
  ```

### 10. Get Download URL (Fallback)
- **Endpoint:** `GET /download/{sessionId}`
- **Purpose:** Fallback download endpoint when S3 URLs not available
- **Called:** As a fallback for downloads
- **Query Params:** `user_id`
- **Response:** File download or redirect to S3

### 11. Delete Session
- **Endpoint:** `DELETE /session/{sessionId}`
- **Purpose:** Permanently delete a session
- **Called:** When user deletes a chat from sidebar
- **Query Params:** `user_id`
- **Response:** Status 200 if successful

### 12. Get Multi-turn Session
- **Endpoint:** `GET /multiturn-session/{sessionId}`
- **Purpose:** Get detailed multi-turn session data
- **Called:** When needed for multi-turn context
- **Query Params:** `user_id`
- **Response:** Complete multi-turn session data

### 13. Get Results (Important for Final Report)
- **Endpoint:** `GET /results/{sessionId}`
- **Purpose:** Get structured JSON results including clean final report
- **Called:** When `is_complete` is true and status is 'completed'
- **Query Params:** `user_id`
- **Response:**
  ```json
  {
    "session_id": "...",
    "status": "completed",
    "content": {
      "final_report": "Clean markdown report content",
      "thinking_content": "Thinking process",
      "raw_result": "Raw agent output"
    },
    "files": {
      "report_md": "path",
      "thinking_process": "path",
      "session_zip": "path"
    }
  }
  ```

## Polling Behavior

### Active Session Monitoring
When a session is active (processing), the following endpoints are called every **5 seconds**:
1. `/status/{sessionId}` - Check processing status
2. `/snapshots/{sessionId}` - Get latest snapshots

The polling stops when:
- Task completes successfully
- Task fails with an error
- User stops the task manually
- User navigates away from the session

## File Uploads
Files can be uploaded with both new requests (`/chat-queue`) and session continuations (`/continue-session`). Files are sent as FormData with the `files` field.

## Authentication
All endpoints require a `user_id` parameter to ensure users can only access their own sessions. The user_id is generated as a UUID when the app loads.

## Error Handling
All API calls include error handling with console logging. Failed requests return `null` or `false` depending on the endpoint, and the UI displays appropriate error messages to the user.