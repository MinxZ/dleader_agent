# Agent FastAPI Server with Multi-User Queue Support

This FastAPI implementation provides a REST API server that can handle multiple concurrent users with a queue management system, supporting both English and Japanese languages.

## Features

- **Multi-User Concurrent Support**: Handle multiple users simultaneously with a queue system
- **Language Support**: Full support for English ("en") and Japanese ("jp") interfaces
- **Queue Management**: Automatic queue processing with position tracking and wait time estimation
- **Real-time Updates**: WebSocket support for live progress monitoring
- **Session Management**: Persistent session handling with file storage
- **File Upload Support**: Handle multiple file uploads per session
- **Thread-Safe**: Safe concurrent operation with proper locking mechanisms

## Architecture

### Core Components

1. **QueueManager**: Manages the user request queue and processing
2. **UserRequest**: Represents individual user requests with progress tracking
3. **SessionManager**: Handles file and session storage
4. **StreamingCapture**: Captures agent output for real-time streaming
5. **FastAPI Endpoints**: REST API endpoints for client interaction

### Queue System

The queue system ensures that only one user's request is processed at a time while others wait in queue:

- **Position Tracking**: Users can check their position in the queue
- **Wait Time Estimation**: Estimated wait time based on queue position (2 minutes per request)
- **Progress Updates**: Real-time progress updates via WebSocket or polling
- **Thread-Safe Processing**: Proper locking to ensure thread safety

## API Endpoints

### POST `/chat`
Start a new chat session.

**Request Body:**
```json
{
  "message": "Your request message",
  "language": "en",  // "en" or "jp"
  "session_id": "optional-existing-session-id"
}
```

**Response:**
```json
{
  "session_id": "unique-session-id",
  "status": "queued",
  "is_complete": false
}
```

### GET `/chat/{session_id}/status`
Get current status of a chat session.

**Response:**
```json
{
  "session_id": "session-id",
  "status": "processing",  // "queued", "processing", "completed", "error"
  "is_complete": false,
  "error": null,
  "result": null,
  "progress_updates": [...],
  "created_at": "2024-01-01T12:00:00"
}
```

### GET `/chat/{session_id}/queue`
Get queue position for a session.

**Response:**
```json
{
  "position": 2,
  "estimated_wait_time": 240,  // seconds
  "total_users_in_queue": 3
}
```

### POST `/upload/{session_id}`
Upload files for a session.

**Request:** Multipart form with files
**Response:**
```json
{
  "message": "Uploaded 2 files",
  "file_paths": ["/path/to/file1", "/path/to/file2"]
}
```

### WebSocket `/ws/{session_id}`
Real-time progress updates via WebSocket.

### GET `/sessions`
List all active sessions.

### GET `/health`
Health check endpoint.

## Installation and Setup

### Prerequisites

```bash
pip install fastapi uvicorn websockets aiohttp pandas
```

### Running the Server

```bash
# Basic startup
python agent_fastapi_server.py

# Custom port and host
python agent_fastapi_server.py --host 0.0.0.0 --port 8001

# With auto-reload for development
python agent_fastapi_server.py --reload
```

### Running the Client Examples

```bash
# Make sure server is running first
python agent_client_example.py
```

## Usage Examples

### 1. Single User Interaction

```python
import asyncio
from agent_client_example import AgentClient

async def single_user_example():
    client = AgentClient("http://localhost:8001")
    
    # Start chat
    session_id = await client.start_chat(
        "Analyze data and create visualizations", 
        language="en"
    )
    
    # Monitor progress
    await client.monitor_progress()
```

### 2. Multiple Users with Queue

```python
async def multiple_users_example():
    # User 1 - English
    client1 = AgentClient()
    await client1.start_chat("Create a bar chart", "en")
    
    # User 2 - Japanese  
    client2 = AgentClient()
    await client2.start_chat("データを分析してください", "jp")
    
    # Both will be processed in queue order
    await asyncio.gather(
        client1.monitor_progress(),
        client2.monitor_progress()
    )
```

### 3. File Upload

```python
async def file_upload_example():
    client = AgentClient()
    
    # Start session
    await client.start_chat("Analyze the uploaded CSV file", "en")
    
    # Upload files
    await client.upload_files(["data.csv", "report.xlsx"])
    
    # Monitor processing
    await client.monitor_progress()
```

## Language Support

### English (`"en"`)
- Standard English interface
- Enhanced message includes file path information
- English error messages and status updates

### Japanese (`"jp"`)
- Full Japanese language support
- Japanese timezone (JST) handling
- Japanese font configuration for matplotlib plots
- Japanese comments and reports

## Queue Management Details

### Queue Processing
1. Requests are added to a FIFO queue upon submission
2. A background thread processes one request at a time
3. Progress updates are pushed to the request's progress queue
4. Clients can poll or use WebSocket for real-time updates

### Status Flow
```
queued → processing → completed/error
```

### Position Tracking
- Queue position is calculated dynamically
- Estimated wait time: `position * 120 seconds`
- Real-time position updates as queue progresses

## Error Handling

The server handles various error scenarios:

- **Session Not Found**: Returns 404 for invalid session IDs
- **File Upload Errors**: Proper error responses for file upload issues
- **Agent Processing Errors**: Captured and returned to client
- **Queue Processing Errors**: Logged and marked as error status

## Session Storage

Each session creates a unique folder under `chat_sessions/` containing:

- **Report files** (`report_*.md`): Final agent reports
- **Thinking process** (`thinking_process_*.txt`): Agent's thinking process
- **Query files** (`query_*.txt`): Original user requests
- **Uploaded files**: User-uploaded files
- **Generated files**: Any files created during processing

## Security Considerations

- **File Upload**: Files are stored in temporary directories and session folders
- **CORS**: Currently allows all origins (configure for production)
- **Input Validation**: Basic validation on request models
- **Session Isolation**: Each session has isolated file storage

## Development and Debugging

### Health Check
```bash
curl http://localhost:8001/health
```

### View Queue Status
```bash
curl http://localhost:8001/sessions
```

### Logs
The server logs queue processing, file operations, and errors to stdout.

## Comparison with Original Gradio Interface

| Feature | Gradio Interface | FastAPI Server |
|---------|-----------------|----------------|
| **Concurrency** | Single user | Multi-user with queue |
| **API** | Web UI only | REST API + WebSocket |
| **Language** | Separate files | Single server with language parameter |
| **Queue** | No queue | Built-in queue management |
| **Real-time** | Live updates in UI | WebSocket + polling |
| **Integration** | Standalone | API for integration |

## Future Enhancements

Potential improvements for production use:

1. **Authentication**: Add user authentication and authorization
2. **Rate Limiting**: Implement rate limiting per user/IP
3. **Database**: Store session data in a database instead of files
4. **Scaling**: Add support for multiple worker processes
5. **Monitoring**: Add metrics and monitoring endpoints
6. **Configuration**: External configuration file support
7. **Persistence**: Queue persistence across server restarts

## Troubleshooting

### Common Issues

1. **Server won't start**
   - Check if port is already in use
   - Verify all dependencies are installed

2. **Queue not processing**
   - Check server logs for errors
   - Verify agent initialization is working

3. **WebSocket connection fails**
   - Ensure session exists before connecting
   - Check firewall settings

4. **File upload fails**
   - Check file permissions
   - Verify available disk space

### Debug Mode

Run with debug logging:
```bash
python agent_fastapi_server.py --reload
```

The server includes comprehensive error handling and logging to help with debugging issues.