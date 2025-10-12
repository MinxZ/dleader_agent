# Multi-Turn File Persistence Testing Guide

## Overview

This guide explains how to test the multi-turn file persistence functionality that ensures files are available across conversation turns even when deleted locally.

## Test Scripts

### 1. `test_full_multiturn_workflow.py` - Comprehensive Test
Full workflow test that simulates a complete multi-turn conversation with file uploads, deletions, and recovery from S3.

**What it tests:**
- First turn: Upload CSV data and JSON metadata, agent creates plots
- File tracking across turns with metadata
- Local file deletion to simulate cloud-only storage
- Second turn: Recovery of files from S3
- Verification that agent can read recovered files
- ZIP download of all session results
- Extraction of specific values to prove file access

**Key features:**
- Creates test data with specific "secret" values to verify
- Uploads multiple files (CSV and JSON)
- Requests agent to create visualizations
- Deletes local files between turns
- Verifies files are recovered from S3
- Downloads final ZIP with all results

### 2. `test_multiturn_quick.py` - Quick Verification
Simplified test for quick verification of basic functionality.

**What it tests:**
- Basic file upload and processing
- File deletion and recovery
- Multi-turn context preservation
- Quick pass/fail verification

### 3. `test_multiturn_file_persistence.py` - Unit Tests
Unit tests for the enhanced multi-turn handler components.

**What it tests:**
- Context building with file information
- File type categorization
- File availability checking
- Metadata enrichment

## Running the Tests

### Prerequisites

1. **Start the FastAPI server:**
```bash
python agent_fastapi_server_multiturn.py
```

2. **Ensure environment variables are set:**
```bash
# S3 Configuration
export AWS_ACCESS_KEY_ID_SELF=your_key
export AWS_SECRET_ACCESS_KEY_SELF=your_secret
export AWS_REGION_SELF=us-east-1

# MongoDB Configuration
export MONGODB_URI=your_mongodb_uri
```

3. **Install required packages:**
```bash
pip install pandas aiohttp requests
```

### Running Full Workflow Test

```bash
python test_full_multiturn_workflow.py
```

**Expected output:**
```
======================================================================
MULTI-TURN WORKFLOW TEST WITH FILE PERSISTENCE
======================================================================

============================================================
TURN 1: Starting first turn with data upload
============================================================
Created test data file: /tmp/multiturn_test_xxx/test_sales_data.csv
Created metadata file: /tmp/multiturn_test_xxx/metadata.json
First turn started:
  Session ID: session_xxx
  Status: queued

Waiting for session session_xxx to complete...
  Status: processing
  Status: completed
  Session completed in 15.2 seconds

Deleting local files for session session_xxx...
  Deleting: session_storage/session_xxx
  Deleted 1 local items

============================================================
TURN 2: Starting second turn (files should be recovered from S3)
============================================================
Second turn started:
  Session ID: session_xxx
  Turn Session ID: session_xxx_turn_2
  Turn Number: 2

Waiting for session session_xxx_turn_2 to complete...
  Status: processing
  Restored 4 files from previous turns
  Status: completed

VERIFICATION: Checking results
============================================================

Verification Results:
  ✓ PASS: Turn 1 completed
  ✓ PASS: Turn 2 completed
  ✓ PASS: Files tracked across turns
  ✓ PASS: Secret key found
  ✓ PASS: Special codes extracted
  ✓ PASS: Plots created

🎉 SUCCESS: Multi-turn workflow test PASSED!
```

### Running Quick Test

```bash
python test_multiturn_quick.py
```

**Expected output:**
```
✓ Server is running

============================================================
QUICK MULTI-TURN TEST
Server: http://localhost:8001
User: quick_test_123456
============================================================

📤 Turn 1: Uploading data and requesting plot...
✓ Session started: session_xxx
⏳ Waiting for Turn 1 to complete...
✓ Turn 1 completed in 8.5s

🗑️  Deleting local files...
  Deleting: session_storage/session_xxx

📥 Turn 2: Attempting to access files from Turn 1...
✓ Turn 2 started: session_xxx_turn_2
⏳ Waiting for Turn 2 to complete...
✓ Turn 2 completed in 6.3s

📋 Verification:
  Secret recovered: ✓
  Files accessed: ✓

✅ SUCCESS: Files were recovered from S3!
```

## Test Data Structure

### Turn 1 Upload Files

**test_sales_data.csv:**
```csv
product,sales,profit,region,special_code
Product A,1200,300,North,TEST-001
Product B,1500,450,South,TEST-002
Product C,900,200,East,TEST-003
```

**metadata.json:**
```json
{
  "experiment_id": "EXP-2024-001",
  "secret_key": "MULTITURN-TEST-KEY-42",
  "parameters": {
    "plot_title": "Sales and Profit Analysis Q4 2024",
    "color_scheme": "viridis"
  }
}
```

### Verification Points

The test verifies that:

1. **Files are tracked** - Each turn's files are recorded with metadata
2. **Files are uploaded to S3** - After turn completion
3. **Local deletion works** - Files are removed from local storage
4. **S3 recovery works** - Files are downloaded when needed
5. **Agent can access recovered files** - Can read content and extract values
6. **Context is preserved** - Previous turn information is available

### Expected Agent Behavior

**Turn 1:**
- Reads uploaded CSV and JSON files
- Creates visualization plots
- Extracts secret key: `MULTITURN-TEST-KEY-42`
- Lists special codes: `TEST-001`, `TEST-002`, etc.
- Saves plots as PNG files

**Turn 2 (after deletion):**
- Recognizes missing local files
- Triggers S3 download via enhanced handler
- Successfully reads recovered files
- Reports found secret key and codes
- Can describe plot contents
- Creates new visualizations using recovered data

## Troubleshooting

### Test Failures

**"Server health check failed"**
- Ensure FastAPI server is running
- Check server is on correct port (8001)

**"Secret key not found"**
- Agent may not have read the metadata file
- Check agent logs for file reading errors

**"Files not recovered from S3"**
- Verify AWS credentials are set
- Check S3 bucket exists and is accessible
- Verify MongoDB is running and connected

**"Timeout waiting for completion"**
- Agent may be taking longer than expected
- Increase timeout in test script
- Check agent logs for errors

### Debug Mode

For detailed debugging, modify the server to enable verbose logging:

```python
# In agent_fastapi_server_multiturn.py
import logging
logging.basicConfig(level=logging.DEBUG)
```

### Manual Verification

Check S3 bucket contents:
```bash
aws s3 ls s3://dleader-agent-sessions/sessions/
```

Check MongoDB records:
```javascript
// In MongoDB shell
db.sessions.find({"session_id": "session_xxx"})
```

## Performance Metrics

Typical test execution times:
- Turn 1 completion: 10-20 seconds
- File deletion: < 1 second
- Turn 2 with recovery: 8-15 seconds
- Total test time: 30-45 seconds

## Summary

These tests ensure that the multi-turn file persistence system works correctly:
- Files are properly tracked across turns
- S3 backup happens automatically
- Files can be recovered when missing locally
- Agent maintains context across turns
- Users have seamless experience even with cloud-only storage