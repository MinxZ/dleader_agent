# Template Matching Feature

## Overview

The template matching feature allows users to optionally disable automatic workflow template matching when submitting queries to the dleader_agent system.

**Default behavior**: Template matching is **ENABLED** by default.

## What is Template Matching?

Template matching automatically:
1. Analyzes your query to find relevant workflow templates
2. Augments your query with the template's detailed prompt
3. Provides structured guidance for complex biomedical workflows

When disabled, your query is sent directly to the agent without template augmentation.

## Changes Made

### API Endpoints

Both API endpoints now support a `use_template` parameter (default: `true`):

#### `/chat-queue` - Start new session
```bash
curl -X POST http://localhost:8001/chat-queue \
  -F "message=Your query here" \
  -F "language=en" \
  -F "user_id=your_user_id" \
  -F "use_template=false"  # Disable template matching
```

#### `/continue-session` - Continue existing session
```bash
curl -X POST http://localhost:8001/continue-session \
  -F "session_id=your_session_id" \
  -F "message=Follow-up query" \
  -F "user_id=your_user_id" \
  -F "use_template=false"  # Disable template matching
```

### Gradio Interface

The Gradio interface includes a checkbox labeled **"Use Template Matching"** in:
- **Start New Conversation** section
- **Continue Existing Session** section

Simply check or uncheck the box to enable/disable template matching for that specific request.

## Usage Scripts

### Start Services

```bash
# Make sure you're in the dleader_agent directory
cd /home/ubuntu/dleader_agent

# Activate the conda environment
conda activate dleader_agent_e1

# Start both FastAPI server and Gradio interface
./start_services.sh
```

The script will:
- Start FastAPI server on port 8001
- Start Gradio interface on port 7861
- Create log files: `fastapi_server.log` and `gradio_interface.log`

### Stop Services

```bash
./stop_services.sh
```

This will gracefully stop both services.

### View Logs

```bash
# FastAPI server logs
tail -f fastapi_server.log

# Gradio interface logs
tail -f gradio_interface.log
```

## Testing the Feature

1. Start the services: `./start_services.sh`
2. Open Gradio interface: http://localhost:7861
3. Go to "Multi-Turn Conversations" tab
4. Try a query with template matching **enabled** (checkbox checked)
5. Try the same query with template matching **disabled** (checkbox unchecked)
6. Compare the results to see the difference

## Example Queries to Test

With template matching:
- "Merge two datasets" → Should match "Data Merge" template
- "Design ASO for KRAS gene" → Should match "ASO Design" template
- "QSPR analysis for drug compounds" → Should match "QSPR Workflow" template

Without template matching:
- Same queries will be processed directly without template augmentation
- Faster processing but less structured workflow guidance

## Files Modified

1. `agent_fastapi_server_multiturn.py`
   - Added `use_template` parameter to UserRequest class
   - Added `use_template` parameter to `/chat-queue` and `/continue-session` endpoints
   - Updated `run_agent_in_process` function signature to accept `use_template` parameter
   - Pass `use_template` value when creating the agent process
   - Added conditional template matching logic based on `use_template` flag

2. `agent_gradio_fastapi_multiturn_simplified.py`
   - Added `use_template` parameter to FastAPIClient methods
   - Added "Use Template Matching" checkboxes to UI
   - Updated event handlers to pass checkbox value

3. `template_retriever.py` (no changes needed)
   - Existing template matching logic used when enabled

## Bug Fixes

**Fixed**: NameError when `user_request` was not accessible in `run_agent_in_process` function
- Solution: Added `use_template` as a parameter to `run_agent_in_process` function
- Passed the value from `user_request.use_template` when creating the process
