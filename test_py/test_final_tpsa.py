#!/usr/bin/env python3
"""
Final test for TPSA pesticide plotting with strongest prompt
"""
import os
import sys
import time
import requests
import zipfile

BASE_URL = "http://localhost:8001"
TEST_USER = "test_final_tpsa"

def main():
    print("="*70)
    print(" FINAL TPSA PLOTTING TEST")
    print(" Testing strongest prompt version")
    print("="*70)

    # Same query but expecting different behavior with new prompt
    message = "plot tpsa for some pesticide"

    print(f"\n📝 Query: '{message}'")

    response = requests.post(
        f"{BASE_URL}/chat-queue",
        data={
            "message": message,
            "language": "en",
            "user_id": TEST_USER
        }
    )

    if response.status_code != 200:
        print(f"❌ Failed: {response.status_code}")
        return 1

    result = response.json()
    session_id = result["session_id"]
    print(f"✅ Session: {session_id}")

    # Monitor execution
    print(f"\n⏳ Waiting for completion...")
    for i in range(40):
        time.sleep(3)

        progress = requests.get(
            f"{BASE_URL}/status/{session_id}",
            params={"user_id": TEST_USER}
        )

        if progress.status_code == 200:
            data = progress.json()
            if data.get("is_complete"):
                print(f"✅ Completed!")
                break
            print(f"  [{i*3:3}s] Processing...")

    time.sleep(5)  # Wait for zip

    # Check results
    import glob
    zip_pattern = f"chat_zips/*{session_id[:8]}*.zip"
    zip_files = glob.glob(zip_pattern)

    if not zip_files:
        print("❌ No zip file found")
        return 1

    zip_path = zip_files[0]
    print(f"\n📦 Checking: {os.path.basename(zip_path)}")

    plot_files = []
    with zipfile.ZipFile(zip_path, 'r') as zf:
        for file in zf.namelist():
            if any(ext in file.lower() for ext in ['.svg', '.png', '.jpg']):
                info = zf.getinfo(file)
                size_kb = info.file_size / 1024
                plot_files.append((file, size_kb))

    if plot_files:
        print(f"✅ SUCCESS! Found {len(plot_files)} plot files:")
        for file, size in plot_files:
            print(f"   🖼️ {file} ({size:.1f} KB)")
        print(f"\n🎉 The updated prompt works! Agent is now saving plots.")
        return 0
    else:
        print(f"❌ STILL NO PLOTS SAVED")
        print(f"   The prompt needs even more strengthening")
        return 1

if __name__ == "__main__":
    sys.exit(main())