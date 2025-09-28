# S3 File Upload Implementation for Multi-Turn Sessions

## Overview
This document describes the implementation of S3 file upload and retrieval functionality for the FastAPI multi-turn server, enabling persistent file storage across sessions and server restarts.

**File Size Limit**: Maximum 10MB per file (configurable)

## Problem Addressed
The original implementation stored uploaded files locally in the EC2 instance, leading to issues:
1. Files were lost when sessions expired or servers restarted
2. Files uploaded via external APIs (e.g., React app) couldn't be accessed in subsequent turns
3. File paths referenced in session metadata didn't exist when sessions were restored from cloud storage

## Solution Implementation

### File Size Validation
- **Maximum file size**: 10MB (configurable via `MAX_FILE_SIZE_MB` constant)
- Files exceeding the limit are rejected with detailed error messages
- Mixed uploads supported: some files accepted, others rejected
- HTTP 413 status code returned when all files are rejected

### 1. S3 Upload in `/chat-queue` Endpoint
```python
# agent_fastapi_server_multiturn.py - Line 2251-2349

@app.post("/chat-queue")
async def start_chat_queue(...):
    # Files are now uploaded to S3 immediately
    # S3 object naming: sessions/{session_id}/turn{turn_number}_{filename}
    # Metadata stored in session for retrieval
```

**Key Features:**
- Automatic S3 upload for all files received via API
- S3 metadata stored in `multiturn_session.s3_files_by_turn`
- Fallback to local storage if S3 fails
- Proper logging of upload status

### 2. S3 Upload in `/continue-session` Endpoint
```python
# agent_fastapi_server_multiturn.py - Line 2648-2775

@app.post("/continue-session")
async def continue_session(...):
    # Handles file uploads for continuation turns
    # Includes S3 metadata in enhanced context
    # Flags files for download with 'needs_download' attribute
```

**Key Features:**
- Maintains S3 file tracking across turns
- Enhanced context includes S3 file references
- Automatic metadata persistence

### 3. File Restoration from S3
```python
# agent_fastapi_server_multiturn.py - Line 1099-1146

# In _process_user_request method:
# Downloads files from S3 when processing turns
# Checks 'needs_download' flag in file metadata
# Uses cloud_storage_manager.s3_client for downloads
```

**Key Features:**
- Automatic detection of files needing S3 download
- Fallback to enhanced handler for complex scenarios
- Progress updates during file restoration

## File Metadata Structure

### S3 File Metadata Format
```json
{
  "filename.ext": {
    "s3_key": "sessions/session_id/turn1_filename.ext",
    "bucket": "dleader-agent-sessions",
    "local_path": "/temp/path/filename.ext",
    "turn_number": 1,
    "upload_time": "2025-09-26T10:30:00",
    "file_size": 1024
  }
}
```

### Enhanced Context All Files Format
```json
{
  "filename.ext": {
    "turn": 1,
    "s3_key": "sessions/session_id/turn1_filename.ext",
    "bucket": "dleader-agent-sessions",
    "type": "file",
    "needs_download": true
  }
}
```

## API Response Changes

### `/chat-queue` Response
```json
{
  "session_id": "uuid",
  "turn_number": 1,
  "status": "queued",
  "position": 1,
  "uploaded_files": 2,
  "s3_files": ["file1.csv", "file2.png"],
  "rejected_files": [
    {
      "filename": "huge_file.csv",
      "size_mb": 15.3,
      "reason": "File size 15.3MB exceeds maximum 10MB"
    }
  ],
  "message": "Request added to queue. 2 files uploaded, 1 rejected (>10MB)."
}
```

### `/continue-session` Response
```json
{
  "session_id": "uuid",
  "turn_session_id": "uuid_turn_2",
  "turn_number": 2,
  "status": "queued",
  "position": 1,
  "uploaded_files": 1,
  "s3_files": ["new_file.csv"],
  "rejected_files": [],
  "message": "Turn 2 added to queue with S3 storage..."
}
```

## Configuration Requirements

### Environment Variables
```bash
# Required for S3 functionality
AWS_ACCESS_KEY_ID_SELF=your_access_key
AWS_SECRET_ACCESS_KEY_SELF=your_secret_key
AWS_REGION_SELF=us-east-1
SESSION_STORAGE_BUCKET=dleader-agent-sessions

# Optional MongoDB for metadata
MONGODB_URI=mongodb://...
SESSION_DB_NAME=dleader_agent
```

### Dependencies
- boto3 (S3 client)
- cloud_storage_manager module
- enhanced_multiturn_handler module

## Testing

Use the provided test scripts to verify functionality:

```bash
# Test S3 upload and retrieval
python test_s3_file_upload.py

# Test file size validation
python test_file_size_validation.py

# Or test manually with curl
curl -X POST http://localhost:8001/chat-queue \
  -F "message=Test message" \
  -F "language=en" \
  -F "user_id=test_user" \
  -F "files=@small_file.csv" \
  -F "files=@large_file.pdf"

# Test with oversized file (should be rejected)
dd if=/dev/zero of=big_file.bin bs=1M count=15  # Create 15MB file
curl -X POST http://localhost:8001/chat-queue \
  -F "message=Test message" \
  -F "language=en" \
  -F "user_id=test_user" \
  -F "files=@big_file.bin"
```

### File Size Configuration

To change the maximum file size limit:

```python
# In agent_fastapi_server_multiturn.py
MAX_FILE_SIZE_MB = 10  # Change this value (in MB)
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024
```

## Migration Notes

### For Existing Sessions
- Old sessions without S3 metadata will continue to work with local files
- New uploads will automatically use S3
- Gradual migration as sessions are renewed

### Backward Compatibility
- Falls back to local storage if S3 is not configured
- Compatible with existing Gradio and React interfaces
- No changes required to client applications

## Benefits

1. **Persistence**: Files survive server restarts and session timeouts
2. **Scalability**: Supports multi-server deployments
3. **Reliability**: S3 provides 99.999999999% durability
4. **Cost-Effective**: Only stores active session files
5. **Cross-Platform**: Works with any client (React, Gradio, CLI)

## Future Enhancements

1. **Compression**: Compress files before S3 upload
2. **Encryption**: Add client-side encryption for sensitive files
3. **Lifecycle Policies**: Auto-delete old session files
4. **CDN Integration**: Use CloudFront for faster file delivery
5. **Batch Operations**: Upload multiple files in parallel

## Troubleshooting

### Common Issues

1. **S3 Access Denied**
   - Check AWS credentials in environment variables
   - Verify IAM permissions for S3 bucket

2. **Files Not Found**
   - Check S3 bucket exists and is accessible
   - Verify file was uploaded successfully (check logs)

3. **Download Failures**
   - Check network connectivity
   - Verify S3 object keys are correct
   - Check bucket region matches configuration

4. **File Size Rejection (413 Error)**
   - File exceeds 10MB limit
   - Check response for `rejected_files` array with details
   - Consider splitting large files or increasing limit

### Debug Logging

Enable debug logging:
```python
import logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)
```

Check logs for:
- "Uploaded {filename} to S3: {s3_key}"
- "Downloaded {filename} from S3: {s3_key}"
- "Failed to upload/download {filename}: {error}"