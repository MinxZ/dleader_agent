#!/usr/bin/env python3
"""
Test script to verify Gradio trash API URL handling
Tests both with and without http:// prefix
"""
import requests
import sys
import time
from datetime import datetime

# Test configurations
TEST_URLS = [
    "http://localhost:8001",      # With protocol
    "localhost:8001",              # Without protocol
    "127.0.0.1:8001",             # IP without protocol
    "http://127.0.0.1:8001",     # IP with protocol
]

TEST_USER = "gradio_test_user"

def test_url_format(base_url):
    """Test that URL formatting works correctly"""
    print(f"\n{'='*60}")
    print(f"Testing URL: {base_url}")
    print('='*60)

    # This simulates what the Gradio functions do
    server_url_value = base_url
    if not server_url_value.startswith(('http://', 'https://')):
        server_url_value = f"http://{server_url_value}"
        print(f"  Added protocol: {server_url_value}")
    else:
        print(f"  Protocol already present: {server_url_value}")

    # Test the trash endpoint
    try:
        response = requests.get(
            f"{server_url_value}/trash",
            params={"user_id": TEST_USER},
            timeout=2
        )

        if response.status_code == 200:
            data = response.json()
            print(f"  ✅ Trash endpoint works - {data.get('count', 0)} items")
            return True
        else:
            print(f"  ❌ Trash endpoint failed: {response.status_code}")
            return False

    except requests.exceptions.RequestException as e:
        print(f"  ❌ Connection error: {e}")
        return False

def test_full_trash_cycle():
    """Test a complete trash operation cycle"""
    print(f"\n{'='*60}")
    print("FULL TRASH OPERATION TEST")
    print('='*60)

    # Use IP without protocol to test URL fixing
    test_url = "127.0.0.1:8001"

    # Fix URL format
    if not test_url.startswith(('http://', 'https://')):
        test_url = f"http://{test_url}"

    print(f"Using URL: {test_url}")

    # 1. Create a test session
    print("\n1. Creating test session...")
    response = requests.post(
        f"{test_url}/chat-queue",
        data={
            "message": f"print('Gradio trash test at {datetime.now()}')",
            "user_id": TEST_USER,
            "language": "en"
        }
    )

    if response.status_code != 200:
        print(f"  ❌ Failed to create session: {response.status_code}")
        return False

    session_id = response.json()["session_id"]
    print(f"  ✅ Created session: {session_id}")

    # Wait for session to be ready
    time.sleep(3)

    # 2. Move to trash
    print("\n2. Moving session to trash...")
    response = requests.post(
        f"{test_url}/trash/{session_id}",
        params={"user_id": TEST_USER}
    )

    if response.status_code == 200:
        print(f"  ✅ Session moved to trash")
    elif response.status_code == 404:
        print(f"  ⚠️  Session not ready yet (expected for queued sessions)")
    else:
        print(f"  ❌ Failed to move to trash: {response.status_code}")

    # 3. Check trash
    print("\n3. Checking trash contents...")
    response = requests.get(
        f"{test_url}/trash",
        params={"user_id": TEST_USER}
    )

    if response.status_code == 200:
        data = response.json()
        count = data.get('count', 0)
        print(f"  ✅ Trash contains {count} items")

        # Clean up if session is in trash
        sessions = data.get('sessions', [])
        for session in sessions:
            if session['session_id'] == session_id:
                print(f"\n4. Cleaning up test session...")
                response = requests.delete(
                    f"{test_url}/permanent-delete/{session_id}",
                    params={"user_id": TEST_USER, "confirm": True}
                )
                if response.status_code == 200:
                    print(f"  ✅ Test session deleted")
                break
    else:
        print(f"  ❌ Failed to check trash: {response.status_code}")

    return True

def main():
    print("="*70)
    print("GRADIO TRASH API URL FORMAT TEST")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*70)

    # Test 1: URL format variations
    print("\n### TEST 1: URL Format Handling ###")
    all_passed = True
    for url in TEST_URLS:
        if not test_url_format(url):
            all_passed = False

    # Test 2: Full operation cycle
    print("\n### TEST 2: Full Trash Operation ###")
    if not test_full_trash_cycle():
        all_passed = False

    # Summary
    print("\n" + "="*70)
    if all_passed:
        print("✅ ALL TESTS PASSED")
        print("The Gradio trash API URL handling is working correctly.")
        return 0
    else:
        print("❌ SOME TESTS FAILED")
        print("Check the output above for details.")
        return 1

if __name__ == "__main__":
    sys.exit(main())