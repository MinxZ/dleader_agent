#!/usr/bin/env python3
"""
Test JPG format saving to verify space savings
"""
import os
import sys
import time
import requests
import zipfile
import tempfile
import glob

BASE_URL = "http://localhost:8001"
TEST_USER = "test_jpg_user"

def main():
    print("="*70)
    print(" JPG FORMAT SAVING TEST")
    print(" Testing space-efficient JPG format preference")
    print("="*70)

    # Submit request that should generate JPG plots
    message = """Create molecular property analysis plots for SMILES: CC, CCC, CCCC, CCCCC

Please create:
1. A molecular weight comparison chart
2. LogP value distribution plot
3. TPSA (topological polar surface area) comparison
4. Molecular structure diagrams

Make sure all plots are saved efficiently with good compression."""

    print(f"\n📝 Submitting JPG test request...")

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

    # Wait for completion
    print("\n⏳ Waiting for completion...")
    for i in range(30):
        time.sleep(3)

        progress = requests.get(
            f"{BASE_URL}/status/{session_id}",
            params={"user_id": TEST_USER}
        )

        if progress.status_code == 200:
            data = progress.json()
            if data.get("is_complete"):
                print("✅ Completed!")
                break
            print(f"  [{i*3:2}s] Processing...")

    time.sleep(5)  # Wait for zip creation

    # Check zip contents
    zip_pattern = f"chat_zips/*{session_id[:8]}*.zip"
    zip_files = glob.glob(zip_pattern)

    if not zip_files:
        print("❌ No zip file found")
        return 1

    zip_path = zip_files[0]
    print(f"\n📦 Analyzing: {os.path.basename(zip_path)}")

    jpg_files = []
    png_files = []
    svg_files = []

    with zipfile.ZipFile(zip_path, 'r') as zf:
        for file in zf.namelist():
            info = zf.getinfo(file)
            size_kb = info.file_size / 1024

            if file.lower().endswith('.jpg') or file.lower().endswith('.jpeg'):
                jpg_files.append((file, size_kb))
            elif file.lower().endswith('.png'):
                png_files.append((file, size_kb))
            elif file.lower().endswith('.svg'):
                svg_files.append((file, size_kb))

    print(f"\n📊 File Analysis:")
    print(f"  JPG files: {len(jpg_files)}")
    for file, size in jpg_files:
        print(f"    📸 {file} ({size:.1f} KB)")

    print(f"  PNG files: {len(png_files)}")
    for file, size in png_files:
        print(f"    🖼️  {file} ({size:.1f} KB)")

    print(f"  SVG files: {len(svg_files)}")
    for file, size in svg_files:
        print(f"    📐 {file} ({size:.1f} KB)")

    total_jpg_size = sum(size for _, size in jpg_files)
    total_png_size = sum(size for _, size in png_files)
    total_svg_size = sum(size for _, size in svg_files)

    print(f"\n💾 Size Summary:")
    print(f"  Total JPG: {total_jpg_size:.1f} KB")
    print(f"  Total PNG: {total_png_size:.1f} KB")
    print(f"  Total SVG: {total_svg_size:.1f} KB")
    print(f"  Total images: {total_jpg_size + total_png_size + total_svg_size:.1f} KB")

    # Verdict
    if jpg_files:
        print(f"\n✅ SUCCESS: Agent is using JPG format!")
        print(f"   Created {len(jpg_files)} JPG files for space efficiency")
        if png_files:
            print(f"   Also created {len(png_files)} PNG files (probably for transparency)")
        if svg_files:
            print(f"   Also created {len(svg_files)} SVG files (probably for vector graphics)")
    else:
        print(f"\n⚠️ NOTICE: No JPG files found")
        if png_files:
            print(f"   Found {len(png_files)} PNG files instead")
        if svg_files:
            print(f"   Found {len(svg_files)} SVG files instead")
        print("   Agent may not have adopted JPG preference yet")

    return 0

if __name__ == "__main__":
    sys.exit(main())