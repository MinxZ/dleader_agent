#!/usr/bin/env python3
"""
Test to verify plots are being saved correctly with the new prompt instructions
This test will submit a plotting request and verify:
1. Agent uses plt.savefig() to save plots
2. Plot files are created in the working directory
3. Plot files are moved to the session folder
4. Plot files are included in the zip
"""
import os
import sys
import time
import json
import requests
import zipfile
import tempfile
import glob
import shutil
from datetime import datetime

BASE_URL = "http://localhost:8001"
TEST_USER = "test_plot_save_user"

def cleanup_old_test_files():
    """Clean up any old test files from previous runs"""
    patterns = ['molecule_*.png', 'molecular_*.png', 'structure_*.png', '*.svg']
    for pattern in patterns:
        for file in glob.glob(pattern):
            try:
                os.remove(file)
                print(f"Cleaned up old file: {file}")
            except:
                pass

def verify_plot_in_response(response_text):
    """Check if the response shows use of plt.savefig()"""
    savefig_indicators = [
        'plt.savefig',
        'savefig(',
        'fig.savefig',
        '.to_file(',  # for RDKit
        'saved to',
        'saved as',
        'saving plot',
        'plot saved'
    ]

    found_indicators = []
    for indicator in savefig_indicators:
        if indicator.lower() in response_text.lower():
            found_indicators.append(indicator)

    return found_indicators

def main():
    print("="*80)
    print(" PLOT SAVING VERIFICATION TEST")
    print(" Testing new prompt instructions for plt.savefig()")
    print("="*80)

    # Clean up old test files
    cleanup_old_test_files()

    # Record start time
    start_time = time.time()
    print(f"\n🕐 Start time: {datetime.now()}")

    # Step 1: Submit plotting request with explicit save instruction
    print("\n" + "="*60)
    print("STEP 1: SUBMITTING PLOTTING REQUEST")
    print("="*60)

    message = """Please create molecular structure plots for these SMILES:
1. CC (Ethane)
2. CCC (Propane)
3. CCCC (Butane)

Requirements:
- Create 2D molecular structure diagrams
- Label each molecule clearly with its name
- IMPORTANT: Save each plot as a PNG file with descriptive names
- Use high quality settings (dpi=300)
- Make sure all plots are saved to files, not just displayed"""

    print(f"\n📝 Message sent:\n{'-'*40}\n{message}\n{'-'*40}")

    response = requests.post(
        f"{BASE_URL}/chat-queue",
        data={
            "message": message,
            "language": "en",
            "user_id": TEST_USER
        }
    )

    if response.status_code != 200:
        print(f"❌ Failed to submit: {response.status_code}")
        print(f"Response: {response.text}")
        return 1

    result = response.json()
    session_id = result["session_id"]
    print(f"\n✅ Session created: {session_id}")

    # Step 2: Monitor execution and check for savefig usage
    print("\n" + "="*60)
    print("STEP 2: MONITORING EXECUTION")
    print("="*60)

    session_path = None
    response_text = ""
    plot_files_found = []

    for i in range(40):  # Wait up to 80 seconds
        time.sleep(2)

        # Check status
        progress = requests.get(
            f"{BASE_URL}/status/{session_id}",
            params={"user_id": TEST_USER}
        )

        if progress.status_code == 200:
            data = progress.json()
            status = data.get("status", "unknown")
            is_complete = data.get("is_complete", False)
            session_path = data.get("session_path")
            response_text = data.get("response", "")

            # Check for new plot files
            current_plots = []
            for pattern in ['*.png', '*.svg', '*.jpg']:
                for file in glob.glob(pattern):
                    if os.path.getmtime(file) > start_time:
                        current_plots.append(file)

            if current_plots and not plot_files_found:
                plot_files_found = current_plots
                print(f"\n🎨 Plot files detected in working directory:")
                for file in plot_files_found:
                    size = os.path.getsize(file) / 1024
                    print(f"   - {file} ({size:.1f} KB)")

            print(f"  [{i*2:3}s] Status: {status}, Complete: {is_complete}")

            if is_complete:
                print(f"\n✅ Task completed!")
                break
    else:
        print("\n⚠️ Task didn't complete in 80 seconds")

    # Step 3: Verify plt.savefig() was used
    print("\n" + "="*60)
    print("STEP 3: VERIFYING plt.savefig() USAGE")
    print("="*60)

    indicators = verify_plot_in_response(response_text)
    if indicators:
        print(f"✅ Found savefig indicators in response:")
        for indicator in indicators:
            print(f"   - '{indicator}'")
    else:
        print("❌ No savefig indicators found in response")
        print("   Agent may not have used plt.savefig()")

    # Step 4: Check session folder for plot files
    print("\n" + "="*60)
    print("STEP 4: CHECKING SESSION FOLDER")
    print("="*60)

    session_plots = []
    if session_path and os.path.exists(session_path):
        print(f"📁 Session folder: {session_path}")
        files = os.listdir(session_path)

        for file in files:
            if any(ext in file.lower() for ext in ['.png', '.jpg', '.svg']):
                filepath = os.path.join(session_path, file)
                size = os.path.getsize(filepath) / 1024
                session_plots.append(file)
                print(f"   🖼️ {file} ({size:.1f} KB)")

        if session_plots:
            print(f"\n✅ Found {len(session_plots)} plot files in session folder")
        else:
            print("\n❌ No plot files found in session folder")
    else:
        print(f"❌ Session folder not found: {session_path}")

    # Step 5: Wait for zip creation
    print("\n" + "="*60)
    print("STEP 5: WAITING FOR ZIP CREATION")
    print("="*60)
    time.sleep(5)

    # Step 6: Verify plots in zip file
    print("\n" + "="*60)
    print("STEP 6: VERIFYING PLOTS IN ZIP")
    print("="*60)

    zip_pattern = f"chat_zips/*{session_id[:8]}*.zip"
    zip_files = glob.glob(zip_pattern)

    zip_plots = []
    if zip_files:
        zip_path = zip_files[0]
        print(f"📦 Zip file: {zip_path}")

        with zipfile.ZipFile(zip_path, 'r') as zf:
            files = zf.namelist()

            for file in files:
                if any(ext in file.lower() for ext in ['.png', '.jpg', '.svg']):
                    info = zf.getinfo(file)
                    size = info.file_size / 1024
                    zip_plots.append(file)
                    print(f"   🖼️ {file} ({size:.1f} KB)")

            if zip_plots:
                print(f"\n✅ Found {len(zip_plots)} plot files in zip")
            else:
                print("\n❌ No plot files found in zip")
    else:
        print(f"❌ No zip file found: {zip_pattern}")

    # Step 7: Test download endpoint
    print("\n" + "="*60)
    print("STEP 7: TESTING DOWNLOAD")
    print("="*60)

    download_response = requests.get(
        f"{BASE_URL}/download/{session_id}",
        params={"user_id": TEST_USER},
        allow_redirects=True
    )

    download_plots = []
    if download_response.status_code == 200:
        print(f"✅ Download successful ({len(download_response.content)} bytes)")

        # Check downloaded zip
        with tempfile.NamedTemporaryFile(suffix='.zip', delete=False) as tmp:
            tmp.write(download_response.content)
            tmp_path = tmp.name

        with zipfile.ZipFile(tmp_path, 'r') as zf:
            files = zf.namelist()
            for file in files:
                if any(ext in file.lower() for ext in ['.png', '.jpg', '.svg']):
                    download_plots.append(file)

        print(f"   Found {len(download_plots)} plots in downloaded zip")
        os.unlink(tmp_path)
    else:
        print(f"❌ Download failed: {download_response.status_code}")

    # Final Summary
    print("\n" + "="*80)
    print(" TEST RESULTS SUMMARY")
    print("="*80)

    test_results = {
        "savefig_used": len(indicators) > 0,
        "plots_created": len(plot_files_found) > 0,
        "plots_in_session": len(session_plots) > 0,
        "plots_in_zip": len(zip_plots) > 0,
        "plots_downloadable": len(download_plots) > 0
    }

    print("\n📊 Test Results:")
    print(f"   1. plt.savefig() used: {'✅ YES' if test_results['savefig_used'] else '❌ NO'}")
    print(f"   2. Plots created locally: {'✅ YES' if test_results['plots_created'] else '❌ NO'} ({len(plot_files_found)} files)")
    print(f"   3. Plots in session folder: {'✅ YES' if test_results['plots_in_session'] else '❌ NO'} ({len(session_plots)} files)")
    print(f"   4. Plots in zip file: {'✅ YES' if test_results['plots_in_zip'] else '❌ NO'} ({len(zip_plots)} files)")
    print(f"   5. Plots downloadable: {'✅ YES' if test_results['plots_downloadable'] else '❌ NO'} ({len(download_plots)} files)")

    if all(test_results.values()):
        print("\n🎉 SUCCESS! All tests passed!")
        print("   The new prompt instructions are working correctly.")
        print("   Plots are being saved with plt.savefig() and included in zips.")
    else:
        print("\n⚠️ ISSUES DETECTED:")
        if not test_results['savefig_used']:
            print("   - Agent didn't use plt.savefig() explicitly")
        if not test_results['plots_created']:
            print("   - No plot files were created locally")
        if not test_results['plots_in_session']:
            print("   - Plot files weren't moved to session folder")
        if not test_results['plots_in_zip']:
            print("   - Plot files weren't included in zip")
        if not test_results['plots_downloadable']:
            print("   - Plot files weren't downloadable")

    # Show example of correct usage
    if not test_results['savefig_used']:
        print("\n📝 Expected usage in agent response:")
        print("   plt.savefig('molecule_ethane.png', dpi=300, bbox_inches='tight')")
        print("   plt.close()  # Free memory")

    return 0 if all(test_results.values()) else 1

if __name__ == "__main__":
    sys.exit(main())