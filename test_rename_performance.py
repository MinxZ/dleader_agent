"""
Test script to measure rename operation performance

This script tests the /rename-multisession endpoint to see how long it takes
to rename a session.
"""

import requests
import time
import json

# Configuration
BASE_URL = "http://localhost:8001"  # Update if needed
TEST_USER_ID = "test_user_dleader"

def get_recent_sessions(user_id, limit=10):
    """Get recent sessions for a user"""
    print(f"\n{'='*60}")
    print(f"Fetching recent sessions for user: {user_id}")
    print('='*60)

    response = requests.get(
        f"{BASE_URL}/multiturn-sessions",
        params={"user_id": user_id, "limit": limit, "offset": 0}
    )

    if response.status_code == 200:
        data = response.json()
        sessions = data.get('sessions', [])
        print(f"Found {len(sessions)} sessions")
        return sessions
    else:
        print(f"Error: {response.status_code}")
        return []

def rename_session(session_id, new_name, user_id):
    """Rename a session and measure time"""
    print(f"\n{'='*60}")
    print(f"Testing RENAME operation")
    print('='*60)
    print(f"Session ID: {session_id}")
    print(f"New Name: {new_name}")
    print(f"User ID: {user_id}")

    payload = {
        "session_id": session_id,
        "new_name": new_name,
        "user_id": user_id
    }

    # Start timing
    start_time = time.time()

    response = requests.post(
        f"{BASE_URL}/rename-multisession",
        json=payload
    )

    # End timing
    end_time = time.time()
    elapsed_ms = (end_time - start_time) * 1000

    print(f"\n⏱️  Time taken: {elapsed_ms:.2f} ms ({elapsed_ms/1000:.3f} seconds)")
    print(f"Status Code: {response.status_code}")

    if response.status_code == 200:
        result = response.json()
        print(f"Response: {json.dumps(result, indent=2)}")
        print(f"\n✅ Rename successful!")
    else:
        print(f"Error: {response.text}")
        print(f"\n❌ Rename failed!")

    return elapsed_ms

def main():
    print("\n" + "="*60)
    print("RENAME PERFORMANCE TEST")
    print("="*60)

    # Step 1: Get recent sessions
    sessions = get_recent_sessions(TEST_USER_ID, limit=5)

    if not sessions:
        print("\n❌ No sessions found. Please create a session first.")
        return

    # Display sessions
    print(f"\n{'='*60}")
    print("Available Sessions:")
    print('='*60)
    for i, session in enumerate(sessions, 1):
        session_id = session.get('session_id', 'N/A')
        session_name = session.get('session_name', 'Unnamed')
        total_turns = session.get('total_turns', 0)
        print(f"{i}. {session_id[:16]}... | {total_turns} turns | '{session_name}'")

    # Test with first session
    test_session = sessions[0]
    session_id = test_session['session_id']
    original_name = test_session.get('session_name', 'Unnamed Session')

    print(f"\n{'='*60}")
    print(f"Testing with Session 1")
    print('='*60)
    print(f"Original name: '{original_name}'")

    # Test 1: Rename to new name
    test_name_1 = f"Performance Test - {time.strftime('%H:%M:%S')}"
    time1 = rename_session(session_id, test_name_1, TEST_USER_ID)

    time.sleep(1)  # Small delay

    # Test 2: Rename back to original (or another name)
    test_name_2 = f"Test Renamed Back - {time.strftime('%H:%M:%S')}"
    time2 = rename_session(session_id, test_name_2, TEST_USER_ID)

    time.sleep(1)  # Small delay

    # Test 3: One more rename
    test_name_3 = f"Final Test Name - {time.strftime('%H:%M:%S')}"
    time3 = rename_session(session_id, test_name_3, TEST_USER_ID)

    # Summary
    print(f"\n{'='*60}")
    print("PERFORMANCE SUMMARY")
    print('='*60)
    print(f"Test 1: {time1:.2f} ms")
    print(f"Test 2: {time2:.2f} ms")
    print(f"Test 3: {time3:.2f} ms")
    print(f"Average: {(time1 + time2 + time3) / 3:.2f} ms")
    print(f"Min: {min(time1, time2, time3):.2f} ms")
    print(f"Max: {max(time1, time2, time3):.2f} ms")

    print(f"\n{'='*60}")
    print("TEST COMPLETE")
    print('='*60)

    # Optional: Restore original name
    restore = input("\nRestore original session name? (y/n): ").strip().lower()
    if restore == 'y':
        rename_session(session_id, original_name, TEST_USER_ID)
        print(f"\n✅ Restored original name: '{original_name}'")

if __name__ == "__main__":
    try:
        main()
    except requests.exceptions.ConnectionError:
        print(f"\nERROR: Could not connect to server at {BASE_URL}")
        print("Please make sure the FastAPI server is running:")
        print("  python agent_fastapi_server_multiturn.py")
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
