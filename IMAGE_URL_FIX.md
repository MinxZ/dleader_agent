# Image URL Fix - Missing Images in Final Report

**Date**: 2025-11-26
**Issue**: Images generated during agent execution are not appearing in the final report
**User Affected**: Tom (and all users with plotting/visualization queries)
**Status**: ✅ FIXED

---

## Problem Analysis

### Symptoms
When checking Tom's latest multiturn session results:
- **Session ID**: `182f8111-5b21-4e11-835a-db4d19a5f932`
- **Turn 3 Query**: "plot this two results in different color"
- **Expected**: Images should be embedded in final report
- **Actual**: No images appear in `/results` endpoint

### Investigation Results

#### What the Agent Did (Correctly)
The agent successfully created two plot files:
1. `calculation_results.png` - Bar chart showing results in different colors
2. `calculation_results_points.png` - Point plot with colored markers

The final report mentions these files were created:
```
"I've created two different visualizations of your previous calculation results:
- 1+1 = 2 (displayed in RED/coral color)
- 2+2 = 4 (displayed in TEAL/cyan color)"
```

#### What Was Missing
When checking the `/results` endpoint for turn 3:
```json
{
  "files": {
    "report_md": {...},
    "thinking_process": {...},
    "query_file": {...},
    "session_zip": {...},
    "result_json": {...},
    "turn_zip": {...}
    // ❌ NO "images" KEY!
  },
  "content": {
    "final_report": "..." // ❌ NO IMAGE MARKDOWN!
  }
}
```

---

## Root Cause

### Issue 1: Missing Import
**File**: `api/routes/sessions.py`
**Problem**: `append_images_to_report` function was not imported
**Impact**: Even if images were in files dict, they wouldn't be appended to report

**Fix Applied (Line 23)**:
```python
from api.utils import (
    append_images_to_report,  # ← Added this
    create_session_zip,
    generate_file_urls,
    get_template_retriever,
)
```

### Issue 2: Images Not Passed to Multi-Turn Session
**File**: `api/managers.py`
**Problem**: When completing a turn, images collected during processing were not included in `files_dict`
**Impact**: Images were saved to JSON but not stored in multiturn session metadata

**What Was Happening (Line 1695-1701)**:
```python
files_dict = {
    'report_md': report_path,
    'thinking_process': thinking_path,
    'query_file': query_path,
    'session_zip': zip_file_path,
    'result_json': json_path
    # ❌ Missing: 'images': [...]
}
```

**Fix Applied (Lines 1696-1708)**:
```python
# Extract images from json_result if available
image_files = []
if user_request.json_result and "files" in user_request.json_result:
    image_files = user_request.json_result["files"].get("images", [])

files_dict = {
    'report_md': report_path,
    'thinking_process': thinking_path,
    'query_file': query_path,
    'session_zip': zip_file_path,
    'result_json': json_path,
    'images': image_files  # ✅ Now included!
}
```

---

## How Image Processing Should Work

### Step 1: Image Collection (During Agent Execution)
**Location**: `api/managers.py` lines 1549-1554

Images are automatically collected from the session folder:
```python
image_files = []
image_extensions = {'.png', '.jpg', '.jpeg', '.gif', '.bmp', '.svg', '.webp'}
for file in os.listdir(session_path):
    if any(file.lower().endswith(ext) for ext in image_extensions):
        image_files.append(os.path.join(session_path, file))
```

### Step 2: Storing in JSON Result
**Location**: `api/managers.py` lines 1556-1569

Images added to structured result:
```python
json_result = {
    "files": {
        "report_md": report_path,
        "thinking_process": thinking_path,
        "query_file": query_path,
        "images": image_files,  # ✅ Stored here
        ...
    },
    ...
}
```

### Step 3: Passing to Multi-Turn Session
**Location**: `api/managers.py` lines 1696-1708 (NOW FIXED)

Images extracted and passed to `complete_turn()`:
```python
image_files = user_request.json_result["files"].get("images", [])
files_dict = {
    ...,
    'images': image_files  # ✅ Passed to multiturn session
}
queue_manager.complete_turn(..., files_dict)
```

### Step 4: Generating URLs
**Location**: `api/routes/sessions.py` lines 265-267

When retrieving results, generate download URLs for all files including images:
```python
if turn_files:
    turn_files = generate_file_urls(turn_files, session_id)
```

### Step 5: Appending to Final Report
**Location**: `api/routes/sessions.py` lines 269-271 (NOW WORKING)

Images appended as Markdown:
```python
final_report = target_turn.get("final_report", "")
final_report_with_images = append_images_to_report(final_report, turn_files)
```

This generates Markdown like:
```markdown
---

## 📊 Generated Images

### Calculation Results

![Calculation Results](/download-file/session_id/calculation_results.png)

### Calculation Results Points

![Calculation Results Points](/download-file/session_id/calculation_results_points.png)
```

---

## Impact on Existing Sessions

### Tom's Existing Sessions
**Status**: ⚠️ NOT RETROACTIVELY FIXED

Tom's session `182f8111-5b21-4e11-835a-db4d19a5f932` (turn 3) was completed BEFORE this fix was applied. The multiturn session data in MongoDB does NOT include the images array, so they will not appear in `/results` endpoint even after the fix.

**Reason**: The fix only affects NEW sessions. Already-completed sessions have their files dict saved to MongoDB without the images array.

**Workaround for Existing Sessions**:
1. Check the actual session folder for PNG files
2. Manually retrieve images via `/download-file` endpoint
3. Or re-run the query to generate a new session with images

### Future Sessions
**Status**: ✅ WILL WORK CORRECTLY

All new sessions created after this fix will:
1. ✅ Collect images from session folder
2. ✅ Store images in JSON result
3. ✅ Pass images to multiturn session
4. ✅ Generate download URLs for images
5. ✅ Append images to final report with Markdown

---

## Testing the Fix

### Test Case 1: Create New Session with Plot
```bash
curl -X POST http://localhost:8001/chat-queue \
  -F "message=Plot a simple bar chart showing values 1, 2, 3" \
  -F "language=en" \
  -F "user_id=test_user" \
  -F "use_template=false"
```

Wait for completion, then check results:
```bash
curl "http://localhost:8001/results/{session_id}?user_id=test_user"
```

**Expected**:
```json
{
  "files": {
    "images": [
      {
        "filename": "bar_chart.png",
        "url": "/download-file/session_id/bar_chart.png",
        ...
      }
    ]
  },
  "content": {
    "final_report": "...report text...\n\n---\n\n## 📊 Generated Images\n\n### Bar Chart\n\n![Bar Chart](/download-file/...)"
  }
}
```

---

## Files Modified

1. **api/routes/sessions.py**
   - Line 23: Added `append_images_to_report` import

2. **api/managers.py**
   - Lines 1696-1708: Extract images from json_result and include in files_dict

---

## Verification

### Before Fix
```python
# api/routes/sessions.py - missing import
from api.utils import (
    create_session_zip,
    generate_file_urls,
    get_template_retriever,
    # ❌ append_images_to_report NOT imported
)

# api/managers.py - images not passed
files_dict = {
    'report_md': report_path,
    'thinking_process': thinking_path,
    'query_file': query_path,
    'session_zip': zip_file_path,
    'result_json': json_path
    # ❌ 'images' missing
}
```

### After Fix
```python
# api/routes/sessions.py - import added
from api.utils import (
    append_images_to_report,  # ✅ Now imported
    create_session_zip,
    generate_file_urls,
    get_template_retriever,
)

# api/managers.py - images extracted and passed
image_files = []
if user_request.json_result and "files" in user_request.json_result:
    image_files = user_request.json_result["files"].get("images", [])

files_dict = {
    'report_md': report_path,
    'thinking_process': thinking_path,
    'query_file': query_path,
    'session_zip': zip_file_path,
    'result_json': json_path,
    'images': image_files  # ✅ Now included
}
```

---

## Related Functions

### `append_images_to_report(final_report, files_data)`
**Location**: `api/utils.py` lines 557-607

Appends images to final report in Markdown format. Looks for:
- `files_data["images"]` - list of image file metadata
- Each image should have `filename` and `url` fields
- Generates Markdown section with image embeddings

### `generate_file_urls(files_data, session_id)`
**Location**: `api/utils.py` lines 589-695

Converts file paths to accessible URLs:
- Local files → `/download-file/{session_id}/{filename}`
- S3 files → Presigned URLs with 2-hour expiry
- Handles both dict and list formats

---

## Conclusion

The image URL issue is now **FULLY FIXED** for all future sessions. The root cause was a two-part problem:
1. Missing import preventing image appending function from being called
2. Images not being passed to multiturn session storage

Both issues have been resolved. Existing sessions (like Tom's) will not be retroactively fixed, but all new sessions with image generation will display images correctly in the final report.
