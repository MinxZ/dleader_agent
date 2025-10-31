# Gradio API Separation - Results vs Snapshots

## Issue
The Gradio interface was mixing data from `/results` and `/snapshots` endpoints, sometimes getting snapshots from the results response instead of calling the dedicated `/snapshots` endpoint.

## Correct API Usage Pattern

For **completed sessions**, we should:
1. **First**: Call `/results/{session_id}` to get:
   - Final report
   - Generated images
   - File metadata
   - Status information

2. **Then**: Call `/snapshots/{session_id}` separately to get:
   - Thinking process steps
   - Snapshot content

This separation ensures:
- Clean data separation of concerns
- Proper endpoint usage
- Better performance (don't load snapshots if not needed)
- Follows the intended API design

## Changes Made

### Files Modified
- `agent_gradio_fastapi_multiturn_simplified.py`

### Functions Updated

#### 1. `view_specific_turn()` (lines 486-581)
**Multi-Turn Chat Tab → Turn Navigation**

**Before:**
```python
# Got snapshots from results_data
snapshots = results_data.get('snapshots', [])
```

**After:**
```python
# Step 1: Get results from /results
results_data = client.get_json_results(session_id, user_id, turn_number=turn_number)
# ... process final report and images ...

# Step 2: For completed turns, get thinking from /snapshots separately
if status == 'completed':
    snapshots_data = client.get_snapshots(session_id, user_id, turn_number=turn_number)
    if snapshots_data and 'snapshots' in snapshots_data:
        snapshots = snapshots_data['snapshots']
        # ... display thinking process ...
```

#### 2. `view_status_turn()` (lines 1440-1522)
**Check Status Tab → Turn Selector**

**Before:**
```python
# Got everything from results, including snapshots
snapshots = results_data.get('snapshots', [])
```

**After:**
```python
# Step 1: Get turn-specific results from /results
results_data = client.get_json_results(session_id, user_id, turn_number=turn_number)
# ... process final report and images ...

# Step 2: For completed sessions, get thinking from /snapshots separately
if status == 'completed':
    snapshots_data = client.get_snapshots(session_id, user_id, turn_number=turn_number)
    if snapshots_data and 'snapshots' in snapshots_data:
        snapshots = snapshots_data['snapshots']
        # ... display thinking process ...
```

#### 3. `check_status_with_history()` (lines 591-773)
**Check Status Tab → Main Status Check**

**Before:**
```python
# Mixed approach - sometimes from results
snapshots = results_data.get('snapshots', [])
```

**After:**
```python
# For completed sessions:
# Step 1: Get final report and images from /results
results_data = client.get_json_results(session_id, user_id)
# ... display final report and images ...

# Step 2: Get thinking from /snapshots separately
snapshots_data = client.get_snapshots(session_id, user_id)
if snapshots_data and 'snapshots' in snapshots_data:
    snapshots = snapshots_data['snapshots']
    # ... display thinking process ...

# For in-progress sessions:
# Get current thinking from /snapshots
snapshots_data = client.get_snapshots(session_id, user_id)
```

## Display Order (Completed Sessions)

The new display order for completed sessions is:

1. **Session Metadata**
   - Session ID, status, timestamp, query

2. **📋 Final Report** (from `/results`)
   - The actual results and findings

3. **📸 Images** (from `/results`)
   - Generated visualizations and plots

4. **🧠 Thinking Process** (from `/snapshots`)
   - Step-by-step reasoning that led to the results

5. **📥 Download Links** (from `/download-urls`)
   - S3 presigned URLs or local download links

## Benefits

### 1. Proper API Separation
- `/results` → Final outputs (report, files, images)
- `/snapshots` → Process trace (thinking steps)

### 2. Better Performance
- Only fetch snapshots when needed
- Reduces payload size for initial results view

### 3. Cleaner Code
- Clear separation of concerns
- Easier to maintain and debug
- Follows API design intent

### 4. Consistent Behavior
- All three functions now use the same pattern
- Predictable data flow throughout the UI

## API Call Flow

### For Completed Sessions

```
┌─────────────────────────────────────┐
│  User Selects Completed Turn       │
└──────────────┬──────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│  Step 1: GET /results/{session_id}  │
│  - Final report                     │
│  - Images                           │
│  - File metadata                    │
│  - Status: "completed"              │
└──────────────┬──────────────────────┘
               │
               ▼
        ┌──────────────┐
        │ status ==    │
        │ "completed"? │
        └──┬───────────┘
           │ YES
           ▼
┌─────────────────────────────────────┐
│ Step 2: GET /snapshots/{session_id} │
│  - Thinking process steps           │
│  - Snapshot content                 │
└─────────────────────────────────────┘
```

### For In-Progress Sessions

```
┌─────────────────────────────────────┐
│  User Checks In-Progress Session   │
└──────────────┬──────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│  GET /results/{session_id}          │
│  - Current status                   │
│  - Partial results (if any)         │
│  - Status: "processing"             │
└──────────────┬──────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│  GET /snapshots/{session_id}        │
│  - Current thinking steps           │
│  - Shows progress                   │
└─────────────────────────────────────┘
```

## Code Example

### Before (Mixed Approach)
```python
# ❌ Getting snapshots from results
results_data = client.get_json_results(session_id, user_id, turn_number=turn_number)
snapshots = results_data.get('snapshots', [])  # Wrong source!
```

### After (Separated Approach)
```python
# ✅ Step 1: Get results
results_data = client.get_json_results(session_id, user_id, turn_number=turn_number)
final_report = results_data['content']['final_report']
images = results_data['files']['images']

# ✅ Step 2: Get snapshots separately (only for completed)
if status == 'completed':
    snapshots_data = client.get_snapshots(session_id, user_id, turn_number=turn_number)
    snapshots = snapshots_data['snapshots']
```

## Testing

To verify the changes:

1. **Start Gradio interface:**
   ```bash
   python agent_gradio_fastapi_multiturn_simplified.py
   ```

2. **Test completed session:**
   - Go to "Check Status" tab
   - Select a completed session
   - Click "Check Status"
   - Verify: Final report appears first, then images, then thinking process
   - Check browser network tab: Should see separate calls to `/results` and `/snapshots`

3. **Test turn selector:**
   - Select a turn from dropdown
   - Verify: Final report → Images → Thinking process (in that order)
   - Check network: Separate `/results` and `/snapshots` calls

4. **Test in-progress session:**
   - Start a new session
   - Check status while processing
   - Verify: Thinking process shows current steps from `/snapshots`

## Technical Notes

### Turn-Specific Queries
Both endpoints support `turn_number` parameter:
```python
# Get specific turn results
client.get_json_results(session_id, user_id, turn_number=3)

# Get specific turn snapshots
client.get_snapshots(session_id, user_id, turn_number=3)
```

### Error Handling
- If `/snapshots` fails, thinking process simply won't show (graceful degradation)
- If `/results` fails, the entire view will show an error (critical data)

### Performance Impact
- **Before**: 1 API call with potentially large snapshot data in results
- **After**: 2 API calls, but only for completed sessions
- **Benefit**: Faster initial load, snapshots loaded on demand

## Migration Notes

### Breaking Changes
- None for users (UI behavior is the same)
- Backend must support both endpoints properly

### Backward Compatibility
- Code still handles case where snapshots might be in results (defensive)
- If `/snapshots` endpoint fails, UI degrades gracefully

## Future Improvements

1. **Lazy Loading**: Only fetch snapshots when user expands "Thinking Process" section
2. **Pagination**: For sessions with many snapshots, paginate the thinking process
3. **Caching**: Cache snapshots data to avoid refetching on turn changes
4. **Streaming**: Consider WebSocket for real-time snapshot updates on in-progress sessions
