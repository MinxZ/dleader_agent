# Snapshot Persistence and Per-Turn ZIP Implementation Plan

## Overview
Implement three key features for improved multi-turn session management:
1. **Snapshot Persistence to S3** - Keep snapshots accessible after session completion
2. **Per-Turn ZIP Files** - Separate ZIP files for each turn (turn_1.zip, turn_2.zip, etc.)
3. **Previous Turn File Download** - Automatically download previous turn files when starting new turn

## Current State

### Snapshots
- **During Processing**: Saved locally to `chat_sessions/<session_id>/snapshot_latest_*.json`
- **After Completion**: Local files deleted, only `thinking_process.txt` preserved
- **Problem**: No way to retrieve individual snapshots after completion

### ZIP Files
- **Current**: Single ZIP per session (`multiturn_<timestamp>_<session_id>.zip`)
- **Problem**: All turns bundled together, can't download individual turn results

### Turn Context
- **Current**: Each turn starts with empty working directory
- **Problem**: Agent doesn't have access to previous turn outputs (images, CSVs, etc.)

## Implementation Plan

### Feature 1: Snapshot Persistence to S3

#### Changes Required

**1. Modify Snapshot Saving (agent_fastapi_server_multiturn.py:~1639)**
```python
# After saving snapshot locally, also track for S3 upload
snapshot_path = os.path.join(session_path, snapshot_filename)
with open(snapshot_path, 'w', encoding='utf-8') as f:
    json.dump(snapshot, f, indent=2, ensure_ascii=False)

# Track snapshot file for later S3 upload
if not hasattr(user_request, 'snapshot_files'):
    user_request.snapshot_files = []
user_request.snapshot_files.append({
    'path': snapshot_path,
    'filename': snapshot_filename,
    'timestamp': datetime.now().isoformat()
})
```

**2. Upload Snapshots After Completion (unified_session_manager.py)**

Add method to upload snapshot files:
```python
async def upload_session_snapshots(self, session_id: str, snapshot_files: List[dict]):
    """Upload snapshot files to S3"""
    uploaded_snapshots = []

    for snapshot_file in snapshot_files:
        try:
            s3_key = f"sessions/{session_id}/snapshots/{snapshot_file['filename']}"

            # Upload to S3
            with open(snapshot_file['path'], 'rb') as f:
                await self.cloud_storage.upload_fileobj(
                    f,
                    s3_key,
                    metadata={
                        'session_id': session_id,
                        'timestamp': snapshot_file['timestamp']
                    }
                )

            uploaded_snapshots.append({
                'filename': snapshot_file['filename'],
                's3_key': s3_key,
                'timestamp': snapshot_file['timestamp']
            })

        except Exception as e:
            print(f"Failed to upload snapshot {snapshot_file['filename']}: {e}")

    return uploaded_snapshots
```

**3. Update Session Completion to Upload Snapshots**

In `_process_user_request` after session completes:
```python
# Upload snapshots to S3
if hasattr(user_request, 'snapshot_files') and user_request.snapshot_files:
    uploaded_snapshots = await unified_manager.upload_session_snapshots(
        session_id,
        user_request.snapshot_files
    )

    # Update MongoDB with snapshot metadata
    await unified_manager.update_session_snapshots(session_id, uploaded_snapshots)
```

**4. Modify /snapshots Endpoint to Retrieve from S3**

Update `/snapshots/{session_id}` endpoint:
```python
@app.get("/snapshots/{session_id}")
async def get_session_snapshots(...):
    # ... existing code ...

    # If storage_location is "turn_specific" or "cloud", fetch from S3
    if storage_location in ["turn_specific", "cloud"]:
        # Get snapshot metadata from MongoDB
        session_data = await unified_manager.get_session_by_id(base_session_id)
        snapshot_metadata = session_data.get('snapshots', [])

        # Download and parse snapshot files from S3
        snapshots_list = []
        for snapshot_meta in snapshot_metadata:
            try:
                content = await cloud_storage.download_file_content(snapshot_meta['s3_key'])
                snapshot = json.loads(content)
                snapshots_list.append(snapshot)
            except Exception as e:
                print(f"Failed to retrieve snapshot {snapshot_meta['filename']}: {e}")

        return {
            "session_id": session_id,
            "snapshots": snapshots_list,
            "storage_location": storage_location
        }
```

### Feature 2: Per-Turn ZIP Files

#### Changes Required

**1. Modify ZIP Creation Logic**

Update ZIP naming and creation:
```python
def create_turn_zip(session_id: str, turn_number: int, session_path: str):
    """Create a ZIP file for a specific turn"""
    # Name format: multiturn_<timestamp>_<session_id>_turn_<N>.zip
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    zip_filename = f"multiturn_{timestamp}_{session_id[:12]}_turn_{turn_number}.zip"
    zip_path = os.path.join("chat_zips", zip_filename)

    # Create ZIP with only turn-specific files
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        # Include turn-specific files
        for root, dirs, files in os.walk(session_path):
            for file in files:
                # Filter for turn-specific files
                if f"_turn_{turn_number}_" in file or f"turn{turn_number}" in file:
                    file_path = os.path.join(root, file)
                    arcname = os.path.relpath(file_path, session_path)
                    zipf.write(file_path, arcname)

    return zip_path, zip_filename
```

**2. Create Turn ZIP After Each Turn Completion**

In turn completion logic:
```python
# Create turn-specific ZIP
turn_zip_path, turn_zip_filename = create_turn_zip(
    base_session_id,
    turn_number,
    session_path
)

# Upload turn ZIP to S3
turn_zip_s3_key = f"sessions/{base_session_id}/zips/{turn_zip_filename}"
await cloud_storage.upload_file(turn_zip_path, turn_zip_s3_key)

# Update MongoDB with turn ZIP info
await unified_manager.update_turn_zip(
    base_session_id,
    turn_number,
    {
        'filename': turn_zip_filename,
        's3_key': turn_zip_s3_key,
        'local_path': turn_zip_path
    }
)
```

**3. Update /results Endpoint to Include Turn ZIPs**

Modify response to include per-turn ZIP links:
```python
# Add turn-specific ZIP if available
turn_zips = []
for turn in range(1, turn_number + 1):
    turn_zip_info = session_data.get(f'turn_{turn}_zip')
    if turn_zip_info:
        turn_zip_url = await cloud_storage.generate_presigned_url(
            turn_zip_info['s3_key'],
            expiration=7200
        )
        turn_zips.append({
            'turn': turn,
            'filename': turn_zip_info['filename'],
            'url': turn_zip_url
        })

result['turn_zips'] = turn_zips
```

### Feature 3: Download Previous Turn Files

#### Changes Required

**1. Create Function to Download Previous Turn Files**

```python
async def download_previous_turn_files(
    session_id: str,
    current_turn: int,
    working_dir: str,
    unified_manager
):
    """Download all files from previous turns to working directory"""

    print(f"[TURN CONTEXT] Downloading files from {current_turn - 1} previous turns...")

    for prev_turn in range(1, current_turn):
        try:
            # Get turn data from MongoDB
            turn_data = await unified_manager.get_turn_data(session_id, prev_turn)

            if not turn_data:
                print(f"[TURN CONTEXT] No data found for turn {prev_turn}")
                continue

            # Download images
            for image in turn_data.get('images', []):
                image_content = await cloud_storage.download_file_content(image['s3_key'])
                local_path = os.path.join(working_dir, image['filename'])

                with open(local_path, 'wb') as f:
                    f.write(image_content)

                print(f"[TURN CONTEXT] Downloaded image: {image['filename']}")

            # Download CSV/data files
            for file_info in turn_data.get('generated_files', []):
                if file_info['filename'].endswith(('.csv', '.json', '.txt')):
                    file_content = await cloud_storage.download_file_content(file_info['s3_key'])
                    local_path = os.path.join(working_dir, file_info['filename'])

                    with open(local_path, 'wb') as f:
                        f.write(file_content)

                    print(f"[TURN CONTEXT] Downloaded file: {file_info['filename']}")

            print(f"[TURN CONTEXT] Turn {prev_turn} files downloaded successfully")

        except Exception as e:
            print(f"[TURN CONTEXT] Error downloading turn {prev_turn} files: {e}")
```

**2. Call Download Function When Starting New Turn**

In `_process_user_request` before agent execution:
```python
# If this is turn 2 or later, download previous turn files
if turn_number and turn_number > 1:
    await download_previous_turn_files(
        base_session_id,
        turn_number,
        session_path,  # working directory
        unified_manager
    )
```

**3. Update Agent Initialization Message**

```python
if turn_number and turn_number > 1:
    # Add context about available files
    available_files_msg = f"\n\nAvailable files from previous turns:\n"

    for file in os.listdir(session_path):
        if not file.startswith('snapshot_'):
            available_files_msg += f"- {file}\n"

    # Prepend to user message
    user_request.message = available_files_msg + "\n" + user_request.message
```

## Testing Plan

### Test 1: Snapshot Persistence
1. Start session with "plot tpsa for drugs"
2. During processing, verify snapshots via `/snapshots/<session_id>_turn_1`
3. After completion, verify snapshots still accessible
4. Verify snapshots contain correct content

### Test 2: Per-Turn ZIPs
1. Complete Turn 1 with "1+1"
2. Verify `turn_1.zip` created and uploaded
3. Complete Turn 2 with "plot tpsa for drugs"
4. Verify `turn_2.zip` created and uploaded
5. Verify both ZIPs downloadable with separate URLs

### Test 3: Previous Turn File Download
1. Complete Turn 1 generating images and CSV
2. Start Turn 2 with query "analyze the tpsa data"
3. Verify Turn 1 files downloaded to Turn 2 working directory
4. Verify agent can access previous turn files

## Database Schema Updates

### MongoDB Sessions Collection
```javascript
{
  session_id: "uuid",
  user_id: "email",
  // ... existing fields ...

  // NEW: Snapshot metadata
  snapshots: [
    {
      filename: "snapshot_latest_20251125_123456.json",
      s3_key: "sessions/{session_id}/snapshots/snapshot_latest_20251125_123456.json",
      timestamp: "2025-11-25T12:34:56"
    }
  ],

  // NEW: Per-turn ZIP files
  turn_1_zip: {
    filename: "multiturn_20251125_123456_uuid_turn_1.zip",
    s3_key: "sessions/{session_id}/zips/multiturn_20251125_123456_uuid_turn_1.zip",
    created_at: "2025-11-25T12:35:00"
  },
  turn_2_zip: {
    // ... same structure
  }
}
```

## Files to Modify

1. **agent_fastapi_server_multiturn.py**
   - Line ~1639: Add snapshot tracking
   - Line ~2000: Add snapshot upload after completion
   - Line ~4042: Update `/snapshots` endpoint for S3 retrieval
   - Line ~3682: Update `/results` to include turn ZIPs
   - Line ~1500: Add previous turn file download

2. **unified_session_manager.py**
   - Add `upload_session_snapshots()` method
   - Add `update_session_snapshots()` method
   - Add `get_turn_data()` method
   - Add `update_turn_zip()` method

3. **cloud_storage_manager.py**
   - Add `download_file_content()` method if not exists
   - Ensure `upload_fileobj()` supports metadata

## Estimated Implementation Time

- Feature 1 (Snapshot Persistence): 2-3 hours
- Feature 2 (Per-Turn ZIPs): 1-2 hours
- Feature 3 (Previous Turn Download): 2-3 hours
- Testing & Integration: 2-3 hours

**Total: 7-11 hours**

## Priority Order

1. **Feature 3** (Previous Turn Download) - Most impactful for agent functionality
2. **Feature 2** (Per-Turn ZIPs) - Better organization and download experience
3. **Feature 1** (Snapshot Persistence) - Nice to have, less critical

## Next Steps

1. Review this plan with user
2. Confirm priority order
3. Begin implementation starting with Feature 3
4. Test each feature independently before integration
5. Deploy to production after full testing
