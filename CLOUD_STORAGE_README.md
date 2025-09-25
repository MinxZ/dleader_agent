# Unified Session Management with Cloud Storage

This implementation provides a **transparent hybrid storage solution** where the API interface remains simple and doesn't need to know whether sessions are stored locally or in the cloud. The system intelligently routes requests based on session state.

## Architecture Overview

### Unified API Design
- **Transparent Access**: Same API endpoints work for local and cloud sessions
- **Intelligent Routing**: System automatically determines where to find session data
- **State-Aware**: Different handling for ongoing, pending, and completed tasks

### Storage Strategy
- **Amazon S3**: Stores large files (ZIPs, reports, thinking processes, snapshots)
- **MongoDB**: Stores session metadata, progress summaries, and search indexes
- **Local Processing**: Active sessions stay local during processing
- **Smart Cleanup**: Local files cleaned after successful cloud upload

### Task State Handling
- **ONGOING**: Active sessions being processed - Always local
- **PENDING**: Queued sessions waiting to start - Always local
- **COMPLETED**: Finished sessions - Can be local or cloud (intelligently handled)

### Benefits
- ✅ **API Simplicity**: Interface doesn't change, works transparently
- ✅ **Cost Effective**: S3 for bulk storage, MongoDB for fast queries
- ✅ **State Intelligent**: Proper handling of different task states
- ✅ **Scalable**: Handles large session volumes and file sizes
- ✅ **Fast Search**: Unified view of all sessions regardless of location
- ✅ **Automatic**: Sessions upload to cloud when completed

## Setup Instructions

### 1. Environment Variables
Copy `.env.example` to `.env` and configure:

```bash
# AWS S3 Configuration
AWS_ACCESS_KEY_ID_SELF=your_aws_access_key
AWS_SECRET_ACCESS_KEY_SELF=your_aws_secret_key
AWS_REGION_SELF=us-east-1
SESSION_STORAGE_BUCKET=your-bucket-name

# MongoDB Configuration
MONGODB_URI=mongodb://your_connection_string
SESSION_DB_NAME=dleader_agent
```

### 2. Required Dependencies
```bash
pip install boto3 pymongo python-dotenv
```

### 3. S3 Bucket Setup
- Create an S3 bucket for session storage
- Configure appropriate IAM permissions for read/write access
- The system will auto-create the bucket if it doesn't exist

### 4. MongoDB Setup
- Set up MongoDB instance (Atlas, local, or cloud)
- Collections will be auto-created:
  - `sessions`: Individual session metadata
  - `multiturn_sessions`: Multi-turn conversation data

## How It Works

### Automatic Upload Process

1. **During Session Processing**: Files are created locally in `chat_sessions/` directory
2. **On Session Completion**: Automatically triggers cloud upload
3. **S3 Upload**: All session files uploaded with organized structure:
   ```
   sessions/{session_id}/
   ├── report_md/report_20240922_123456.md
   ├── thinking_process/thinking_20240922_123456.txt
   ├── snapshots/snapshot_latest_20240922_123456.json
   ├── session_zip/session_20240922_123456.zip
   └── additional/other_files.txt
   ```
4. **MongoDB Record**: Metadata saved with S3 URLs and search indexes
5. **Local Cleanup**: Local files deleted after successful upload

### Session Metadata Structure (S3 Key-Based)

**MongoDB Document Example:**
```json
{
  "_id": "session_uuid",
  "session_id": "session_uuid",
  "status": "completed",
  "is_complete": true,
  "created_at": "2024-09-22T09:45:00",
  "query": "Analyze the uploaded data",
  "language": "en",
  "uploaded_to_cloud_at": "2024-09-22T09:50:00",
  "s3_files": {
    "report_md": {
      "filename": "report_20240922_094500.md",
      "s3_key": "sessions/uuid/report_md/report_20240922_094500.md",
      "file_size": 15420,
      "uploaded_at": "2024-09-22T09:50:00"
    },
    "session_zip": {
      "filename": "session_20240922_094500.zip",
      "s3_key": "sessions/uuid/session_zip/session_20240922_094500.zip",
      "file_size": 1048576,
      "uploaded_at": "2024-09-22T09:50:00"
    },
    "snapshots": [
      {
        "filename": "snapshot_latest_20240922_094500.json",
        "s3_key": "sessions/uuid/snapshots/snapshot_latest_20240922_094500.json",
        "file_size": 2048,
        "uploaded_at": "2024-09-22T09:50:00"
      }
    ]
  },
  "progress_summary": {
    "total_updates": 15,
    "snapshot_count": 3,
    "final_status": "completed"
  }
}
```

**Key Improvements:**
- ✅ **No Expiring URLs**: Only S3 keys stored, no time-limited URLs
- ✅ **Fresh URLs**: Generated on-demand with 2-hour expiry
- ✅ **File Metadata**: Size and upload timestamp for each file
- ✅ **Cost Effective**: No need to regenerate URLs during storage

## Unified API Endpoints

All existing endpoints now work seamlessly with both local and cloud sessions:

### List All Sessions (Local + Cloud)
```bash
GET /all-sessions
# Returns all sessions with automatic local/cloud merging
# Response includes _source field showing storage location
```

### Get Session Status (Universal)
```bash
GET /status/{session_id}
# Works for ongoing, pending, and completed sessions
# Automatically routes to correct storage location
# Returns appropriate data based on session state
```

### Download Session Files (Intelligent)
```bash
GET /download/{session_id}
# Local sessions: Direct file download
# Cloud sessions: Fresh S3 presigned URL (2 hours)
# Active sessions: Returns "not ready" message
```

### Get Fresh Download URLs (Cloud Sessions)
```bash
GET /download-urls/{session_id}
# Generates fresh 2-hour URLs for ALL files in a cloud session
# Returns: report, thinking process, snapshots, session zip, etc.
```

### Multi-Turn Sessions (Unified)
```bash
GET /multiturn-sessions
# Returns all multi-turn sessions from local and cloud
```

## File Organization

```
/home/ubuntu/dleader_agent/
├── cloud_storage_manager.py      # Main cloud storage logic
├── s3_mongodb/                   # Your existing S3/MongoDB utilities
│   ├── s3_utils.py
│   ├── func_mongodb.py
│   ├── mongodb_upsert.py
│   └── utiles.py
├── agent_fastapi_server_multiturn.py  # Modified with cloud integration
└── .env.example                  # Environment configuration template
```

## Usage Examples

### Automatic Operation
Sessions automatically upload to cloud when completed. No manual intervention needed.

### Manual Upload
```python
# Upload specific session to cloud
curl -X POST http://localhost:8001/manual-cloud-upload/session_uuid
```

### Query Cloud Sessions
```python
# List recent completed sessions
curl "http://localhost:8001/cloud-sessions?limit=50&status_filter=completed"

# Get specific session metadata
curl http://localhost:8001/cloud-session/session_uuid
```

### Access S3 Files (New Approach)
Generate fresh URLs for downloading files from cloud sessions:
```python
# Get fresh download URLs (valid for 2 hours)
download_data = requests.get("http://localhost:8001/download-urls/session_uuid").json()
report_url = download_data["download_urls"]["report_md"]["url"]
report_content = requests.get(report_url).text

# Or download session zip directly (auto-generates fresh URL)
zip_response = requests.get("http://localhost:8001/download/session_uuid")
# This redirects to fresh S3 URL automatically
```

## Monitoring and Maintenance

### Check Upload Status
Monitor server logs for cloud upload messages:
- `"Initiated cloud upload for session {session_id}"`
- `"Successfully uploaded session {session_id} to cloud"`

### Failed Uploads
If cloud upload fails, sessions remain stored locally and can be manually uploaded later.

### Local Storage Cleanup
Local files are automatically deleted after successful cloud upload. To disable:
```python
# In cloud_storage_manager.py, comment out:
# await self._cleanup_local_files(local_session_path)
```

## Troubleshooting

### Common Issues

1. **AWS Credentials**: Ensure AWS credentials are properly configured
2. **MongoDB Connection**: Verify MongoDB URI and network access
3. **S3 Permissions**: Check bucket permissions for read/write access
4. **Disk Space**: Monitor local disk usage during processing

### Error Logs
Check server logs for detailed error messages:
```bash
tail -f /path/to/your/logs/server.log | grep "cloud upload"
```

## Performance Considerations

- **Async Upload**: Cloud uploads happen asynchronously to not block session completion
- **Batch Operations**: Multiple files uploaded concurrently for efficiency
- **Presigned URLs**: S3 URLs expire after 30 days (configurable)
- **Local Cache**: Active sessions remain local during processing for performance

## Security

- **Presigned URLs**: Temporary access URLs for secure file sharing
- **IAM Permissions**: Use minimal required S3 permissions
- **Network Security**: Secure MongoDB connection with authentication
- **Data Encryption**: S3 server-side encryption enabled by default