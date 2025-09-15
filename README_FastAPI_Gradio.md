# KumiChem AI Agent - FastAPI & Gradio Integration Guide

This document provides comprehensive instructions for using the FastAPI backend server with the Gradio frontend interface for the KumiChem AI Agent system.

## Overview

The system consists of two main components:
- **FastAPI Server** (`agent_fastapi_server.py`) - Backend API with queue management
- **Gradio Interface** (`agent_gradio_fastapi.py`) - Frontend web interface

## Architecture

```
┌─────────────────┐    HTTP/REST API    ┌──────────────────┐
│  Gradio Web UI  │ ────────────────── │  FastAPI Server  │
│  (Frontend)     │                     │  (Backend)       │
└─────────────────┘                     └──────────────────┘
         │                                       │
         │                                       │
    Users interact                          ┌─────────┐
    through web                              │  Queue  │
    browser                                  │ Manager │
                                            └─────────┘
                                                 │
                                            ┌─────────┐
                                            │   AI    │
                                            │ Agent   │
                                            └─────────┘
```

## Quick Start

### Prerequisites

```bash
# Required Python packages
pip install fastapi uvicorn gradio requests pandas pillow
```

### 1. Start the FastAPI Server

```bash
# Basic startup
python3 agent_fastapi_server.py

# With custom configuration (for AWS EC2)
python3 agent_fastapi_server.py --host 0.0.0.0 --port 8000 --reload
```

**Server will be available at:** `http://YOUR_EC2_PUBLIC_IP:8000` (or `http://localhost:8000` if running locally)

### 2. Start the Gradio Interface

```bash
# Basic startup
python3 agent_gradio_fastapi.py

# With custom configuration (connecting to AWS EC2)
python3 agent_gradio_fastapi.py --server_port 7861 --fastapi_url http://YOUR_EC2_PUBLIC_IP:8000
python3 agent_gradio_fastapi.py --server_port 7861 --fastapi_url http://153.177.51.237:8000

```

**Gradio interface will be available at:** `http://localhost:7861`

## AWS EC2 Configuration

### Security Group Settings

To run the FastAPI server on AWS EC2 with port 8000, configure your Security Group:

1. **Open AWS EC2 Console** → Security Groups
2. **Select your EC2 instance's security group**
3. **Edit Inbound rules** → Add rule:
   - **Type**: Custom TCP
   - **Port range**: 8000
   - **Source**:
     - `0.0.0.0/0` (public access - less secure)
     - Your specific IP address (more secure)
     - Specific IP range/CIDR block

### Start FastAPI on EC2
```bash
# On your EC2 instance
python3 agent_fastapi_server.py --host 0.0.0.0 --port 8000
```

### Connect Gradio to EC2
```bash
# From your local machine (replace with your EC2 public IP)
python3 agent_gradio_fastapi.py --fastapi_url http://YOUR_EC2_PUBLIC_IP:8000
```

### Find Your EC2 Public IP
```bash
# On EC2 instance
curl http://checkip.amazonaws.com

# Or check in AWS Console: EC2 → Instances → Your Instance → Public IPv4 address
```

## FastAPI Server Details

### API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/chat` | POST | Submit request and wait for completion |
| `/chat-queue` | POST | Submit request to queue |
| `/status/{session_id}` | GET | Get session status |
| `/upload/{session_id}` | POST | Upload files for session |
| `/sessions` | GET | List all sessions |

### Starting the Server

```bash
# Available options:
python3 agent_fastapi_server.py \
  --host 0.0.0.0 \        # Host address (default: 0.0.0.0)
  --port 8000 \           # Port number (default: 8001, use 8000 for AWS EC2)
  --reload                # Enable auto-reload for development
```

### Server Features

- **Multi-user Queue System**: Handles concurrent requests
- **Session Management**: Each request gets a unique session ID
- **File Upload Support**: Users can upload multiple files
- **Real-time Status Updates**: Track processing progress
- **Language Support**: English and Japanese processing
- **Automatic File Management**: Session folders for organized storage

### API Usage Examples

#### Health Check
```bash
curl http://YOUR_EC2_PUBLIC_IP:8000/health
```

#### Submit Request to Queue
```bash
curl -X POST "http://YOUR_EC2_PUBLIC_IP:8000/chat-queue" \
  -H "Content-Type: application/json" \
  -d '{"message": "Calculate 2+2", "language": "en"}'
```

#### Check Status
```bash
curl http://YOUR_EC2_PUBLIC_IP:8000/status/{session_id}
```

## Gradio Interface Details

### Starting the Interface

```bash
# Available options:
python3 agent_gradio_fastapi.py \
  --server_port 7861 \                    # Gradio server port
  --fastapi_url http://YOUR_EC2_PUBLIC_IP:8000     # FastAPI server URL
```

### Interface Features

- **Clean Web UI**: User-friendly interface for interacting with the AI agent
- **File Upload**: Support for multiple file types
- **Real-time Status**: Shows processing status without streaming
- **Download Results**: Get reports and thinking process files
- **Language Selection**: Choose between English and Japanese
- **Server Configuration**: Configurable FastAPI server URL

### Using the Interface

1. **Configure Server URL**: Set the FastAPI server URL in the interface
2. **Upload Files** (optional): Select files to upload for analysis
3. **Enter Request**: Type your request in the text area
4. **Select Language**: Choose English or Japanese processing
5. **Process**: Click the "Process" button to start
6. **View Results**: Results appear in the right panel
7. **Download**: Download reports and thinking process files

## Configuration

### Environment Variables

Create a `.env` file in the project root:

```env
# FastAPI Configuration
FASTAPI_HOST=0.0.0.0
FASTAPI_PORT=8000

# Gradio Configuration
GRADIO_PORT=7861
GRADIO_SHARE=True

# Agent Configuration
LLM_MODEL=claude-sonnet-4-20250514
USE_TOOL_RETRIEVER=True
DOWNLOAD_DATA_LAKE=False
```

### Server Configuration

#### FastAPI Server Settings
```python
# In agent_fastapi_server.py
app = FastAPI(
    title="Agent Chat API",
    description="Multi-user agent chat with queue management"
)

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

#### Gradio Interface Settings
```python
# In agent_gradio_fastapi.py
demo.launch(
    server_name="0.0.0.0",
    server_port=args.server_port,
    share=True,
    debug=True
)
```

## Usage Examples

### Example 1: Basic Text Analysis

1. Start both servers
2. Open Gradio interface in browser
3. Enter request: "Analyze this text and provide key insights"
4. Click "Process"
5. Wait for completion and view results

### Example 2: Data Analysis with File Upload

1. Prepare a CSV file with data
2. Upload the file in the Gradio interface
3. Enter request: "Analyze the uploaded data and create a summary report"
4. Select language preference
5. Process and download the generated report

### Example 3: Japanese Language Processing

1. Set language to "Japanese" in the interface
2. Enter request in Japanese: "このデータを分析して、レポートを作成してください"
3. Process and receive results in Japanese

## File Management

### Session Folders

Each request creates a unique session folder:
```
chat_sessions/
├── session_20231215_143022_abc123de/
│   ├── uploaded_file.csv
│   ├── report_20231215_143525.md
│   ├── thinking_process_20231215_143525.txt
│   └── query_20231215_143525.txt
```

### File Types Supported

- **Data Files**: CSV, Excel (.xlsx, .xls)
- **Documents**: PDF, TXT, MD
- **Images**: PNG, JPG, JPEG, GIF
- **Other**: Any file type (auto-detected)

## Monitoring and Debugging

### Server Logs

The FastAPI server provides detailed logs:
```
INFO:     Started server process [12345]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8003
INFO:     127.0.0.1:55806 - "POST /chat-queue HTTP/1.1" 200 OK
```

### Health Monitoring

```bash
# Check FastAPI server health
curl http://YOUR_EC2_PUBLIC_IP:8000/health

# Check active sessions
curl http://YOUR_EC2_PUBLIC_IP:8000/sessions
```

### Debug Mode

Enable debug mode for development:
```bash
# FastAPI with reload
python3 agent_fastapi_server.py --reload

# Gradio with debug
python3 agent_gradio_fastapi.py  # debug=True is default
```

## Troubleshooting

### Common Issues

#### 1. Connection Refused
**Problem**: Cannot connect to FastAPI server
**Solution**:
- Ensure FastAPI server is running
- Check the server URL in Gradio interface
- Verify firewall settings

#### 2. Port Already in Use
**Problem**: `Address already in use` error
**Solution**:
```bash
# Find process using the port
lsof -i :8000

# Kill the process or use a different port
python3 agent_fastapi_server.py --port 8000
```

#### 3. File Upload Fails
**Problem**: Files cannot be uploaded
**Solution**:
- Check file size limits
- Ensure session exists before uploading
- Verify file permissions

#### 4. Request Timeout
**Problem**: Requests take too long to process
**Solution**:
- Increase timeout in client configuration
- Check server logs for errors
- Monitor server resources

### Error Messages

| Error | Cause | Solution |
|-------|-------|----------|
| "Server not responding" | FastAPI server down | Start the server |
| "Session not found" | Invalid session ID | Check session ID format |
| "Request timeout" | Processing too slow | Increase timeout or simplify request |
| "File upload failed" | File too large or corrupted | Check file size and format |

## Performance Optimization

### Server Tuning

```bash
# Run with multiple workers
uvicorn agent_fastapi_server:app --workers 4 --host 0.0.0.0 --port 8000
```

### Client Optimization

- Use appropriate timeout values
- Upload smaller files when possible
- Submit simpler requests for faster processing

## Security Considerations

### Production Deployment

1. **Disable CORS wildcard**:
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://yourdomain.com"],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)
```

2. **Add authentication**:
```python
from fastapi.security import HTTPBearer
security = HTTPBearer()
```

3. **File upload restrictions**:
```python
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
ALLOWED_EXTENSIONS = {'.csv', '.xlsx', '.txt', '.pdf'}
```

## Advanced Usage

### Custom Client Implementation

```python
from agent_gradio_fastapi import FastAPIClient

# Create custom client
client = FastAPIClient("http://YOUR_EC2_PUBLIC_IP:8000")

# Submit request
session_id = client.submit_request("Your request here", "en")

# Poll for results
result = client.submit_and_wait("Your request", timeout=300)
```

### Batch Processing

```python
# Process multiple requests
requests = [
    "Analyze dataset A",
    "Generate report for dataset B",
    "Create summary for dataset C"
]

for req in requests:
    session_id = client.submit_request(req, "en")
    print(f"Submitted: {session_id}")
```

## API Reference

### Request Models

```python
class ChatRequest(BaseModel):
    message: str
    language: Language = Language.EN  # "en" or "jp"
    session_id: Optional[str] = None

class Language(str, Enum):
    EN = "en"
    JP = "jp"
```

### Response Models

```python
class ChatResponse(BaseModel):
    session_id: str
    status: str
    thinking_content: Optional[str] = None
    final_report: Optional[str] = None
    progress_updates: List[Dict[str, Any]] = []
    session_path: Optional[str] = None
    error: Optional[str] = None
```

## Best Practices

1. **Always check server health** before submitting requests
2. **Use appropriate timeouts** based on request complexity
3. **Monitor queue position** for long-running requests
4. **Clean up session files** periodically
5. **Use language-specific requests** for better results
6. **Validate file uploads** before submission
7. **Handle errors gracefully** in client applications

## Support and Maintenance

### Logging

Both servers provide comprehensive logging:
- FastAPI: Request/response logs, error tracking
- Gradio: Interface interactions, client errors

### Backup

Important directories to backup:
- `chat_sessions/` - All session data
- Configuration files
- Custom modifications

### Updates

To update the system:
1. Stop both servers
2. Update code files
3. Restart servers
4. Test functionality

---

## Quick Reference Commands

```bash
# Start FastAPI server
python3 agent_fastapi_server.py --port 8000

# Start Gradio interface
python3 agent_gradio_fastapi.py --server_port 7861

# Health check
curl http://YOUR_EC2_PUBLIC_IP:8000/health

# View sessions
curl http://YOUR_EC2_PUBLIC_IP:8000/sessions

# Submit test request
curl -X POST "http://YOUR_EC2_PUBLIC_IP:8000/chat-queue" \
  -H "Content-Type: application/json" \
  -d '{"message": "Hello", "language": "en"}'
```

For additional support or questions, refer to the code documentation and comments in the source files.