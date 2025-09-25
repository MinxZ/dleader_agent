#!/usr/bin/env python3
"""
Test TPSA pesticide plotting to verify plots are saved to files
"""
import os
import sys
import time
import requests
import zipfile
import tempfile
import glob

BASE_URL = "http://localhost:8001"
TEST_USER = "test_tpsa_user"

def main():
    print("="*70)
    print(" TPSA PESTICIDE PLOTTING TEST")
    print(" Testing that plots are SAVED to files, not just displayed")
    print("="*70)

    # Submit the exact query the user mentioned
    message = "plot tpsa for some pesticide"

    print(f"\n📝 Submitting query: '{message}'")

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
    print("\n⏳ Monitoring execution...")
    response_text = ""

    for i in range(40):  # Wait up to 120 seconds
        time.sleep(3)

        progress = requests.get(
            f"{BASE_URL}/status/{session_id}",
            params={"user_id": TEST_USER}
        )

        if progress.status_code == 200:
            data = progress.json()
            status = data.get("status", "unknown")
            is_complete = data.get("is_complete", False)
            response_text = data.get("response", "")

            print(f"  [{i*3:3}s] Status: {status}")

            if is_complete:
                print("✅ Task completed!")
                break
    else:
        print("⚠️ Task didn't complete in 120 seconds")

    time.sleep(5)  # Wait for zip creation

    # Check if savefig was used in the response
    print("\n" + "="*70)
    print("CHECKING FOR PLOT SAVING BEHAVIOR")
    print("="*70)

    savefig_indicators = [
        'plt.savefig',
        'fig.savefig',
        'savefig(',
        '.to_file(',
        'saved to',
        'saved as',
        'saving plot'
    ]

    show_indicators = [
        'plt.show',
        '.show()',
        'display(',
        'show the plot'
    ]

    found_save = []
    found_show = []

    for indicator in savefig_indicators:
        if indicator.lower() in response_text.lower():
            found_save.append(indicator)

    for indicator in show_indicators:
        if indicator.lower() in response_text.lower():
            found_show.append(indicator)

    print(f"\n📊 Plot Saving Analysis:")
    if found_save:
        print(f"✅ Found SAVE indicators:")
        for indicator in found_save:
            print(f"   - '{indicator}'")
    else:
        print("❌ No SAVE indicators found")

    if found_show:
        print(f"\n⚠️ Found DISPLAY indicators (should avoid):")
        for indicator in found_show:
            print(f"   - '{indicator}'")
    else:
        print(f"\n✅ No DISPLAY indicators found (good)")

    # Check zip contents
    zip_pattern = f"chat_zips/*{session_id[:8]}*.zip"
    zip_files = glob.glob(zip_pattern)

    plot_files = []
    if zip_files:
        zip_path = zip_files[0]
        print(f"\n📦 Checking zip: {os.path.basename(zip_path)}")

        with zipfile.ZipFile(zip_path, 'r') as zf:
            files = zf.namelist()
            for file in files:
                if any(ext in file.lower() for ext in ['.png', '.jpg', '.svg', '.jpeg']):
                    info = zf.getinfo(file)
                    size_kb = info.file_size / 1024
                    plot_files.append((file, size_kb))
                    print(f"   🖼️ {file} ({size_kb:.1f} KB)")

        if plot_files:
            print(f"\n✅ Found {len(plot_files)} plot files in zip!")
        else:
            print(f"\n❌ No plot files found in zip")
    else:
        print(f"\n❌ No zip file found")

    # Final verdict
    print("\n" + "="*70)
    print("TEST RESULTS")
    print("="*70)

    if found_save and plot_files and not found_show:
        print("🎉 PERFECT! Agent is saving plots correctly")
        print("   - Uses plt.savefig() commands")
        print("   - Plots are saved to files")
        print("   - No unwanted plt.show() usage")
    elif found_save and plot_files:
        print("✅ GOOD! Agent is saving plots")
        print("   - Uses plt.savefig() commands")
        print("   - Plots are saved to files")
        if found_show:
            print("   - Still using some display commands (minor issue)")
    elif plot_files:
        print("🤔 PARTIAL: Plots exist but unclear how")
        print("   - Plots are in the zip")
        if not found_save:
            print("   - No clear savefig usage detected")
    else:
        print("❌ FAILED: No plots were saved")
        print("   - Agent may still be using plt.show() only")
        print("   - Prompt needs further strengthening")

    return 0 if (found_save and plot_files) else 1

if __name__ == "__main__":
    sys.exit(main())