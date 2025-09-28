# Multi-Turn File Management System Documentation

## Overview
The multi-turn chat system handles files in three distinct categories, each with different storage and retrieval strategies:

## File Categories

### 1. User-Uploaded Files
**Examples:** Images (`.jpg`, `.png`), data files (`.csv`, `.xlsx`), documents (`.pdf`, `.txt`)

**Storage Strategy:**
- **S3 Upload:** Immediately upon upload via API (in `/continue-session` endpoint)
- **S3 Key Pattern:** `sessions/{session_id}/turn{n}_{filename}` or `sessions/{session_id}/{category}/{filename}`
- **MongoDB:** S3 metadata stored (key, bucket, size, upload time)
- **Local:** Saved to session folder (`chat_sessions/multiturn_xxx/`)

**Retrieval Strategy:**
- **Each Turn Start:** Download ALL user files from S3 to session folder
- **Availability:** Must be present in working folder for agent access
- **Persistence:** Files persist across all turns via S3

### 2. System-Generated Files (Per Turn)
**Files:**
- `query_{timestamp}.txt` - User's query for the turn
- `report_{timestamp}.md` - Agent's response/report
- `thinking_process_{timestamp}.txt` - Agent's reasoning
- `result_{timestamp}.json` - Structured result data
- `snapshot_{timestamp}.json` - Progress snapshots
- `{session_name}.zip` - Session archive

**Storage Strategy:**
- **S3 Upload:** Yes, for backup/archival purposes
- **MongoDB:** Content stored directly in metadata (thinking_process, final_report fields)
- **Local:** Created in session folder during processing

**Retrieval Strategy:**
- **NOT Downloaded from S3** - These files are turn-specific
- **Context Building:** Query and report content pulled from MongoDB metadata
- **Previous Turns:** Added to prompt via enhanced_context from MultiTurnSession object

### 3. Agent-Generated Analysis Files
**Examples:** Plots (`.png`), analysis outputs (`.csv`), generated code files

**Storage Strategy:**
- **S3 Upload:** At session completion with other files
- **Local:** Created by agent during analysis, moved to session folder

**Retrieval Strategy:**
- **Download from S3:** Yes, these are treated like user files
- **Availability:** Must be in working folder for subsequent analysis

## Implementation Details

### File Upload Flow (Turn N)
```python
1. User uploads file via API
2. Save to temp_uploads/{session_id}/
3. Upload to S3: sessions/{session_id}/turn{n}_{filename}
4. Store S3 metadata in _temp_s3_metadata
5. Copy file to session folder
6. Agent processes with file available
```

### File Download Flow (Turn N+1)
```python
1. download_turn_files_from_s3() called
2. Filter: Skip system files (query_*, report_*, etc.)
3. Download only user-uploaded and agent-generated files
4. Files available in session folder
5. Agent has access to all previous files
```

### Context Building for Multi-Turn
```python
# From enhanced_multiturn_handler.py
for turn in previous_turns:
    context_parts.append(f"User Query: {turn.query}")  # From MongoDB
    context_parts.append(f"Assistant Response: {turn.final_report}")  # From MongoDB
    context_parts.append(f"Files: {turn.files.keys()}")  # File list only

# Current turn includes file availability
if all_available_files:
    enhanced_message_parts.append("=== Available Files ===")
    for filename in all_available_files:
        enhanced_message_parts.append(f"- {filename}")
```

### S3 Structure
```
sessions/
├── {session_id}/
│   ├── turn1_{user_file}.jpg          # User uploaded in turn 1
│   ├── turn2_{user_file}.csv          # User uploaded in turn 2
│   ├── images/
│   │   └── generated_plot.png         # Agent generated
│   ├── data/
│   │   └── analysis_results.csv       # Agent generated
│   ├── report_md/
│   │   └── report_20250927.md         # System file (NOT downloaded)
│   ├── thinking_process/
│   │   └── thinking_20250927.txt      # System file (NOT downloaded)
│   ├── query_file/
│   │   └── query_20250927.txt         # System file (NOT downloaded)
│   └── snapshots/
│       └── snapshot_20250927.json     # System file (NOT downloaded)
```

## Key Functions

### cloud_storage_manager.py

#### `download_turn_files_from_s3()`
- **Purpose:** Download user files from S3 for multi-turn sessions
- **Excludes:** System files (query_*, report_*, thinking_*, result_*, snapshot_*, *.zip)
- **Includes:** User uploads and agent-generated analysis files

#### `upload_session_to_cloud()`
- **Uploads ALL files** for archival
- **Checks for duplicates** before uploading (prevents re-upload)
- **Stores metadata** in MongoDB

### agent_fastapi_server_multiturn.py

#### `/continue-session` endpoint
- Uploads new files to S3 immediately
- Stores S3 metadata for tracking
- Builds enhanced context with file references

#### `_process_user_request()`
- Downloads previous turn files from S3
- Verifies user file availability
- Loads files into agent's data lake

## Best Practices

1. **User Files:** Always upload to S3 immediately, download at turn start
2. **System Files:** Store content in MongoDB, don't download from S3
3. **File Naming:** Preserve original names (remove turn prefixes when downloading)
4. **Error Handling:** Log missing files but continue processing
5. **Context Building:** Use MongoDB for previous turn content, not S3 files

## Common Issues and Solutions

### Issue: "File X is still missing after S3 download"
**Cause:** System files (report_md, thinking_process, etc.) being expected locally
**Solution:** These files are excluded from download - content is in MongoDB

### Issue: Duplicate S3 uploads
**Cause:** Files being re-uploaded at session completion
**Solution:** Check for existing S3 keys before upload

### Issue: Agent can't access previous turn files
**Cause:** Files not downloaded from S3
**Solution:** Ensure download_turn_files_from_s3() runs at turn start

## Summary

The system maintains a clear separation between:
- **User/Agent files** that need S3 persistence and download
- **System files** that are archived but accessed via MongoDB
- **Context information** built from MongoDB metadata, not files

This approach ensures efficient storage, fast access, and proper context maintenance across multi-turn conversations.