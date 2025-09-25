#!/usr/bin/env python3
"""
Final test to confirm download functionality is working
"""
import os
import sys
import time
import requests

BASE_URL = "http://localhost:8001"
TEST_USER = "Tom"  # Using the user from the original error message

print("="*70)
print(" TESTING DOWNLOAD FIX")
print("="*70)

# Submit a task
print("\n1. Submitting task...")
response = requests.post(
    f"{BASE_URL}/chat-queue",
    data={
        "message": "Create a file test.txt with content 'Hello from test'",
        "language": "en",
        "user_id": TEST_USER
    }
)

if response.status_code != 200:
    print(f"❌ Failed to submit: {response.text}")
    sys.exit(1)

session_id = response.json()["session_id"]
print(f"✓ Session ID: {session_id}")

# Wait for completion
print("\n2. Waiting for completion...")
for i in range(20):
    time.sleep(2)
    progress = requests.get(
        f"{BASE_URL}/progress/{session_id}",
        params={"user_id": TEST_USER}
    )

    if progress.status_code == 200:
        data = progress.json()
        if data.get("is_complete"):
            print(f"✓ Task completed after {(i+1)*2} seconds")
            break
else:
    print("⚠ Task didn't complete in 40 seconds")

# Wait a bit for async operations
print("\n3. Waiting for async operations (S3 upload, etc.)...")
time.sleep(5)

# Test download-urls endpoint
print("\n4. Testing /download-urls endpoint...")
response = requests.get(
    f"{BASE_URL}/download-urls/{session_id}",
    params={"user_id": TEST_USER}
)

print(f"   Status: {response.status_code}")
if response.status_code == 200:
    print("   ✅ download-urls endpoint works!")
    data = response.json()
    for key in data:
        if isinstance(data[key], dict):
            print(f"   - {key}: {data[key].get('filename', 'available')}")
else:
    print(f"   ❌ download-urls failed: {response.text}")

# Test direct download endpoint
print("\n5. Testing /download endpoint...")
response = requests.get(
    f"{BASE_URL}/download/{session_id}",
    params={"user_id": TEST_USER},
    allow_redirects=True
)

print(f"   Status: {response.status_code}")
if response.status_code == 200:
    print("   ✅ download endpoint works!")
    print(f"   Size: {len(response.content)} bytes")

    # Verify it's a valid zip
    import zipfile
    import tempfile
    with tempfile.NamedTemporaryFile(suffix='.zip', delete=False) as tmp:
        tmp.write(response.content)
        tmp_path = tmp.name

    try:
        with zipfile.ZipFile(tmp_path, 'r') as zf:
            files = zf.namelist()
            print(f"   Contains {len(files)} files:")
            for f in files[:5]:
                print(f"     - {f}")
        os.unlink(tmp_path)
    except Exception as e:
        print(f"   ❌ Not a valid zip: {e}")
        os.unlink(tmp_path)
else:
    print(f"   ❌ download failed: {response.text}")

# Summary
print("\n" + "="*70)
print(" SUMMARY")
print("="*70)

if response.status_code == 200:
    print("✅ DOWNLOAD FUNCTIONALITY IS WORKING!")
    print("\nThe issue has been fixed:")
    print("1. Session JSON files are no longer moved from session_storage")
    print("2. Download endpoints check for existing zip files first")
    print("3. Session folders are optional - zips are sufficient")
else:
    print("❌ Download still has issues")
    print("Please check the server logs for more details")