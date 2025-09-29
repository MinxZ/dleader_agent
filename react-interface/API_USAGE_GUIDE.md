# React Interface API Usage Guide

## Overview
This document details all API endpoints used by the React interface, their expected inputs, outputs, and usage patterns for the dleader_agent biomedical AI system.

## API Base URL
- Default: `http://52.192.211.135:8001`
- Configurable via `REACT_APP_API_URL` environment variable

## Core API Endpoints Used

### 1. Start New Session - `/chat-queue`
**Method:** POST
**Purpose:** Initialize a new chat session with the AI agent

**Input (FormData):**
```javascript
{
  message: string,        // User's query/message (required)
  language: string,       // Language code: 'en' or 'jp' (default: 'en')
  user_id: string,        // Unique user identifier (required)
  files: File[]          // Optional file uploads
}
```

**Expected Output:**
```json
{
  "session_id": "session_xyz123",
  "status": "queued",
  "position": 1,
  "message": "Request queued successfully"
}
```

**React Usage:**
```javascript
const sessionId = await apiClient.submitRequest(message, 'en', userId, files);
```

---

### 2. Continue Multi-Turn Session - `/continue-session`
**Method:** POST
**Purpose:** Continue an existing conversation with a new message

**Input (FormData):**
```javascript
{
  session_id: string,     // Original session ID (required)
  message: string,        // Follow-up message (required)
  language: string,       // Language code (default: 'en')
  user_id: string,        // User identifier (required)
  files: File[]          // Optional file uploads
}
```

**Expected Output:**
```json
{
  "session_id": "session_xyz123",
  "turn_session_id": "session_xyz123_turn_2",
  "turn_number": 2,
  "status": "queued",
  "position": 1,
  "uploaded_files": 0,
  "message": "Turn 2 added to queue. Use /status/session_xyz123_turn_2 to check progress."
}
```

**Important:** Use `turn_session_id` to check the status of this specific turn!

**React Usage:**
```javascript
const result = await apiClient.continueSession(sessionId, message, 'en', userId, files);
// Use result.turn_session_id for status checking
```

---

### 3. Check Session Status - `/status/{session_id}`
**Method:** GET
**Purpose:** Check processing status of a session (polled every 5 seconds)

**Input (Query Params):**
```javascript
{
  user_id: string        // User identifier (required)
}
```

**Expected Output:**
```json
{
  "session_id": "session_xyz123",
  "status": "queued|processing|completed|failed|error|cancelled",
  "is_complete": false,  // TRUE when task finishes (success or failure)
  "created_at": "2024-01-01T10:00:00Z",
  "response": "Final response text (when complete)",
  "partial_response": "Partial response during processing",
  "error": "Error message if failed",
  "queue_position": 1,
  "progress": {
    "percentage": 45,
    "step": "Processing data..."
  }
}
```

**Key Fields:**
- `is_complete`: Boolean flag indicating if processing is finished
- `status`: Current state of the task
- `response`: Final agent response (only when complete)
- `partial_response`: Incremental updates during processing

**React Usage:**
```javascript
const status = await apiClient.getStatus(sessionId, userId);
if (status.is_complete && status.status === 'completed') {
  // Task successfully completed
}
```

---

### 4. Get Structured Results - `/results/{session_id}`
**Method:** GET
**Purpose:** Retrieve structured JSON results for completed sessions

**Input (Query Params):**
```javascript
{
  user_id: string        // User identifier (required)
}
```

**Expected Output:**
```json
{
  "session_id": "session_xyz123",
  "status": "completed",
  "timestamp": "2024-01-01T10:00:00Z",
  "language": "en",
  "query": "User's original query",
  "content": {
    "final_report": "## Clean Markdown Report\n\nFormatted final report...",
    "thinking_content": "Agent's thinking process and steps...",
    "raw_result": "Raw unformatted agent output"
  },
  "files": {
    "report_md": "/path/to/report.md",
    "thinking_process": "/path/to/thinking.txt",
    "session_zip": "/path/to/session.zip",
    "images": ["/path/to/plot1.png", "/path/to/plot2.png"]
  },
  "error": null,
  "session_path": "/chat_sessions/session_xyz123"
}
```

**React Usage:**
```javascript
const results = await apiClient.getResults(sessionId, userId);
const finalReport = results.content.final_report;
```

---

### 5. Get Snapshots - `/snapshots/{session_id}`
**Method:** GET
**Purpose:** Get thinking process snapshots (polled every 5 seconds during processing)

**Input (Query Params):**
```javascript
{
  user_id: string        // User identifier (required)
}
```

**Expected Output:**
```json
{
  "snapshots": [
    {
      "timestamp": "2024-01-01T10:00:00Z",
      "content": {
        "thinking_content": "Step 1: Analyzing the query...\nStep 2: Searching databases..."
      },
      "type": "periodic",
      "sequence": 1
    }
  ]
}
```

**React Usage:**
```javascript
const snapshots = await apiClient.getSnapshots(sessionId, userId);
// Display snapshots.snapshots array
```

---

### 6. Stop Running Task - `/stop/{session_id}`
**Method:** POST
**Purpose:** Cancel a running or queued task

**Input (Query Params):**
```javascript
{
  user_id: string        // User identifier (required)
}
```

**Expected Output:**
```json
{
  "success": true,
  "message": "Task stopped successfully"
}
```

**React Usage:**
```javascript
const success = await apiClient.stopTask(sessionId, userId);
```

---

### 7. Get All Sessions - `/all-sessions`
**Method:** GET
**Purpose:** Retrieve all sessions for the sidebar

**Input (Query Params):**
```javascript
{
  user_id: string        // User identifier (optional)
}
```

**Expected Output:**
```json
{
  "sessions": [
    {
      "session_id": "session_xyz123",
      "first_message": "Analyze this protein structure",
      "created_at": "2024-01-01T10:00:00Z",
      "status": "completed",
      "is_multi_turn": true,
      "total_turns": 3
    }
  ]
}
```

**React Usage:**
```javascript
const sessions = await apiClient.getAllSessions(userId);
```

---

### 8. Get Session History - `/session-history/{session_id}`
**Method:** GET
**Purpose:** Load conversation history when selecting a session

**Input (Query Params):**
```javascript
{
  user_id: string        // User identifier (required)
}
```

**Expected Output:**
```json
{
  "session_id": "session_xyz123",
  "turns": [
    {
      "turn_number": 1,
      "message": "User's first message",
      "response": "Agent's first response",
      "timestamp": "2024-01-01T10:00:00Z"
    },
    {
      "turn_number": 2,
      "message": "Follow-up question",
      "response": "Agent's second response",
      "timestamp": "2024-01-01T10:05:00Z"
    }
  ],
  "total_turns": 2
}
```

**React Usage:**
```javascript
const history = await apiClient.getSessionHistory(sessionId, userId);
```

---

### 9. Get Download URLs - `/download-urls/{session_id}`
**Method:** GET
**Purpose:** Get S3 presigned URLs for downloading session files

**Input (Query Params):**
```javascript
{
  user_id: string        // User identifier (required)
}
```

**Expected Output:**
```json
{
  "files": {
    "session_zip": {
      "presigned_url": "https://s3.amazonaws.com/...",
      "size": "2.5 MB",
      "expires_at": "2024-01-01T11:00:00Z"
    },
    "report_md": {
      "presigned_url": "https://s3.amazonaws.com/...",
      "size": "15 KB"
    }
  },
  "expires_in": 60  // minutes
}
```

**React Usage:**
```javascript
const urls = await apiClient.getDownloadUrls(sessionId, userId);
```

---

### 10. Delete Session - `/session/{session_id}`
**Method:** DELETE
**Purpose:** Permanently delete a session and its data

**Input (Query Params):**
```javascript
{
  user_id: string        // User identifier (required)
}
```

**Expected Output:**
```json
{
  "success": true,
  "message": "Session deleted successfully"
}
```

**React Usage:**
```javascript
const success = await apiClient.deleteSession(sessionId, userId);
```

---

## Multi-Turn Conversation Flow

### How Multi-Turn Works:
1. **First Turn:** Use `/chat-queue` → Get `session_id`
2. **Subsequent Turns:** Use `/continue-session` with original `session_id` → Get `turn_session_id`
3. **Status Checking:** Use `turn_session_id` for each turn's status
4. **Session Management:** Keep original `session_id` for the conversation thread

### Example Flow:
```javascript
// Turn 1
const sessionId = await apiClient.submitRequest("Analyze this gene", 'en', userId);
// Check status using sessionId
await checkStatus(sessionId);

// Turn 2
const result = await apiClient.continueSession(sessionId, "What about mutations?", 'en', userId);
// Check status using result.turn_session_id (e.g., "sessionId_turn_2")
await checkStatus(result.turn_session_id);

// Turn 3
const result2 = await apiClient.continueSession(sessionId, "Show protein structure", 'en', userId);
// Check status using result2.turn_session_id (e.g., "sessionId_turn_3")
await checkStatus(result2.turn_session_id);
```

---

## Polling Strategy

The React interface implements the following polling strategy:

1. **Status & Snapshots:** Polled every 5 seconds while task is running
2. **Completion Check:**
   - Check `is_complete` flag first
   - If `is_complete === true` and `status === 'completed'`, fetch results
3. **Stop Polling:** When `is_complete === true` or user cancels

---

## Error Handling

### Common Error Responses:
```json
{
  "detail": "Session not found"  // 404
}

{
  "detail": "Access denied: Session belongs to different user"  // 403
}

{
  "detail": "Session is not yet complete"  // 400
}
```

### Error Handling in React:
- All API calls return `null` or `false` on error
- Errors are logged to console
- UI shows user-friendly error messages

---

## File Uploads

### Supported Upload Methods:
1. **With New Session:** Files attached to `/chat-queue`
2. **With Continuation:** Files attached to `/continue-session`

### File Handling:
```javascript
const formData = new FormData();
formData.append('message', userMessage);
formData.append('user_id', userId);

// Add multiple files
files.forEach(file => {
  formData.append('files', file);
});
```

---

## Authentication & Security

- **User ID:** Required for all endpoints to ensure session isolation
- **Session Ownership:** Users can only access their own sessions
- **File Access:** Files are stored in user-specific directories

---

## WebSocket Support (Future)

The backend supports WebSocket connections for real-time updates:
- Endpoint: `ws://server:port/ws/{session_id}`
- Events: `status`, `progress`, `partial_response`, `complete`

Currently, the React interface uses polling, but WebSocket support can be added for real-time updates.