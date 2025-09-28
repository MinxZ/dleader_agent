# Trash API Separation and S3 Metadata Fix

## Summary
This document describes the separation of trash management endpoints into a dedicated module and the fix for S3 metadata storage in multi-turn sessions.

## Changes Made

### 1. Trash API Separation

#### Created: `trash_api.py`
A new dedicated module containing all trash management endpoints:

- **POST** `/trash/move/{session_id}` - Move session to trash (soft delete)
- **POST** `/trash/restore/{session_id}` - Restore session from trash
- **DELETE** `/trash/permanent/{session_id}` - Permanently delete from trash
- **GET** `/trash/sessions` - Get all trashed sessions for a user
- **POST** `/trash/empty` - Empty all trash (permanent delete all)

**Backward Compatibility:**
- `/trash/{session_id}` → `/trash/move/{session_id}`
- `/restore/{session_id}` → `/trash/restore/{session_id}`
- `/permanent-delete/{session_id}` → `/trash/permanent/{session_id}`
- `/trash` → `/trash/sessions`
- `/empty-trash` → `/trash/empty`

#### Modified: `agent_fastapi_server_multiturn.py`
- Removed 285 lines of trash endpoint code
- Added import: `from trash_api import router as trash_router`
- Included router: `app.include_router(trash_router)`
- **Kept**: `/hard-delete/{session_id}` endpoint (as requested)

### 2. S3 Metadata Storage Fix

#### Problem
The `MultiTurnSession` Pydantic model doesn't allow dynamic attributes, causing:
```
ValueError: "MultiTurnSession" object has no field "s3_files_by_turn"
```

#### Solution
Instead of adding attributes to the Pydantic model, we now:

1. **Store S3 metadata temporarily in QueueManager:**
```python
queue_manager._temp_s3_metadata[f"{session_id}_turn_{turn_number}"] = s3_file_metadata
```

2. **Include S3 metadata when completing turns:**
- Enhanced `complete_turn` method to merge S3 metadata into turn files
- S3 metadata includes: `s3_key`, `bucket`, `file_size`

3. **Retrieve S3 metadata for file restoration:**
- Check `queue_manager._temp_s3_metadata` for previous turn files
- Mark files with `needs_download: true` flag for S3 retrieval

### 3. File Size Validation (Previous Implementation)
- Maximum file size: 10MB (configurable via `MAX_FILE_SIZE_MB`)
- Files exceeding limit are rejected with detailed error messages
- Mixed batch support (some accepted, some rejected)

## Benefits

### Code Organization
- **Modular design**: Trash functionality separated into dedicated module
- **Cleaner main file**: ~285 lines removed from main API
- **Easier maintenance**: All trash logic in one place
- **Better testability**: Can test trash operations independently

### S3 Integration
- **Proper metadata storage**: Works with Pydantic model constraints
- **Persistent file storage**: Files survive server restarts
- **Multi-turn support**: Files accessible across conversation turns
- **Cloud-native**: Ready for distributed deployments

## Testing

### Quick Tests
```bash
# Test S3 metadata fix
python test_s3_metadata_fix.py

# Test file size validation
python test_file_size_validation.py

# Test complete S3 flow
python test_s3_file_upload.py
```

### Manual Testing
```bash
# Start the server
python agent_fastapi_server_multiturn.py

# Test trash endpoints
curl -X POST http://localhost:8001/trash/move/{session_id}?user_id=test
curl -X GET http://localhost:8001/trash/sessions?user_id=test
curl -X POST http://localhost:8001/trash/restore/{session_id}?user_id=test

# Test file upload with S3
curl -X POST http://localhost:8001/chat-queue \
  -F "message=Test" \
  -F "language=en" \
  -F "user_id=test" \
  -F "files=@test.txt"
```

## Configuration

### Environment Variables
```bash
# S3 Configuration (Required for file persistence)
AWS_ACCESS_KEY_ID_SELF=your_key
AWS_SECRET_ACCESS_KEY_SELF=your_secret
AWS_REGION_SELF=us-east-1
SESSION_STORAGE_BUCKET=dleader-agent-sessions

# File Size Limit (Optional)
# Change in agent_fastapi_server_multiturn.py:
MAX_FILE_SIZE_MB = 10  # Default 10MB
```

## Migration Guide

### For API Clients
1. **Trash endpoints**: Update to use `/trash/` prefix or use backward compatibility URLs
2. **File uploads**: No changes needed - S3 integration is transparent
3. **File size**: Handle `rejected_files` array in responses

### For Developers
1. **Import trash router**: Already included via `app.include_router(trash_router)`
2. **S3 metadata**: Access via turn files or `queue_manager._temp_s3_metadata`
3. **File validation**: Adjust `MAX_FILE_SIZE_MB` constant as needed

## Troubleshooting

### Common Issues

1. **Import Error for trash_api**
   - Ensure `trash_api.py` is in the same directory
   - Check Python path includes current directory

2. **S3 Upload Failures**
   - Verify AWS credentials in environment
   - Check S3 bucket exists and has write permissions
   - Review logs for specific S3 errors

3. **File Size Rejections**
   - Check `rejected_files` in response
   - Increase `MAX_FILE_SIZE_MB` if needed
   - Consider chunking large files

4. **Trash Operations Fail**
   - Verify user owns the session
   - Check session exists in storage
   - Ensure proper permissions on directories

## Future Enhancements

1. **Trash Features**
   - Auto-empty trash after X days
   - Trash quota per user
   - Bulk restore operations

2. **S3 Optimization**
   - Multipart upload for large files
   - S3 Transfer Acceleration
   - Lifecycle policies for old files

3. **Performance**
   - Cache S3 metadata in Redis
   - Batch S3 operations
   - Async file uploads