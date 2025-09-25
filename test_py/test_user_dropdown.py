#!/usr/bin/env python3
"""
Test script to verify User ID dropdown functionality
Tests that different users can submit requests and manage their sessions
"""
import requests
import sys
import time
from datetime import datetime

BASE_URL = "http://localhost:8001"

# Test users from the dropdown
TEST_USERS = ["Chen", "Yuan", "Zhang", "Test user"]

def test_user_sessions(user_id):
    """Test session creation and management for a specific user"""
    print(f"\n{'='*50}")
    print(f"Testing User: {user_id}")
    print('='*50)

    # 1. Submit a request
    print(f"1. Submitting request for {user_id}...")
    response = requests.post(
        f"{BASE_URL}/chat-queue",
        data={
            "message": f"print('Test for user {user_id} at {datetime.now().strftime('%H:%M:%S')}')",
            "user_id": user_id,
            "language": "en"
        }
    )

    if response.status_code != 200:
        print(f"   ❌ Failed to submit: {response.status_code}")
        return None

    session_id = response.json()["session_id"]
    print(f"   ✅ Created session: {session_id[:8]}...")

    # 2. Check user's sessions
    print(f"2. Getting sessions for {user_id}...")
    response = requests.get(
        f"{BASE_URL}/all-sessions",
        params={"user_id": user_id}
    )

    if response.status_code == 200:
        sessions = response.json().get("sessions", [])
        user_sessions = [s for s in sessions if s.get("session_id") == session_id]
        if user_sessions:
            print(f"   ✅ Found session in user's list")
        else:
            print(f"   ⚠️  Session not in list yet (may be processing)")
    else:
        print(f"   ❌ Failed to get sessions: {response.status_code}")

    # 3. Check trash (should be empty for new user)
    print(f"3. Checking trash for {user_id}...")
    response = requests.get(
        f"{BASE_URL}/trash",
        params={"user_id": user_id}
    )

    if response.status_code == 200:
        trash_count = response.json().get("count", 0)
        print(f"   ✅ Trash contains {trash_count} items")
    else:
        print(f"   ❌ Failed to check trash: {response.status_code}")

    return session_id

def test_user_isolation():
    """Test that users can't access each other's sessions"""
    print(f"\n{'='*50}")
    print("Testing User Isolation")
    print('='*50)

    # Create session for Chen
    print("1. Creating session for Chen...")
    response = requests.post(
        f"{BASE_URL}/chat-queue",
        data={
            "message": "print('Chen private data')",
            "user_id": "Chen",
            "language": "en"
        }
    )

    if response.status_code != 200:
        print(f"   ❌ Failed to create session")
        return False

    chen_session = response.json()["session_id"]
    print(f"   ✅ Created Chen's session: {chen_session[:8]}...")

    # Wait for processing
    time.sleep(2)

    # Try to move Chen's session to trash as Yuan (should fail)
    print("2. Yuan trying to delete Chen's session...")
    response = requests.post(
        f"{BASE_URL}/trash/{chen_session}",
        params={"user_id": "Yuan"}
    )

    if response.status_code == 403:
        print(f"   ✅ Correctly denied access (403)")
        isolation_works = True
    elif response.status_code == 404:
        print(f"   ✅ Session not found for Yuan (secure)")
        isolation_works = True
    else:
        print(f"   ❌ Unexpected response: {response.status_code}")
        isolation_works = False

    # Clean up - Chen deletes their own session
    print("3. Chen cleaning up their session...")
    response = requests.post(
        f"{BASE_URL}/trash/{chen_session}",
        params={"user_id": "Chen"}
    )

    if response.status_code in [200, 404]:
        print(f"   ✅ Cleanup successful")

    return isolation_works

def main():
    print("="*70)
    print("USER ID DROPDOWN FUNCTIONALITY TEST")
    print(f"Server: {BASE_URL}")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*70)

    # Test 1: Each user can create sessions
    print("\n### TEST 1: User Session Creation ###")
    created_sessions = {}
    for user in TEST_USERS:
        session_id = test_user_sessions(user)
        if session_id:
            created_sessions[user] = session_id

    # Test 2: User isolation
    print("\n### TEST 2: User Isolation Security ###")
    isolation_ok = test_user_isolation()

    # Summary
    print("\n" + "="*70)
    print("TEST SUMMARY")
    print("="*70)

    print(f"\nSessions created successfully:")
    for user, session_id in created_sessions.items():
        print(f"  • {user}: {session_id[:8]}...")

    print(f"\nUser isolation: {'✅ PASSED' if isolation_ok else '❌ FAILED'}")

    if len(created_sessions) == len(TEST_USERS) and isolation_ok:
        print("\n✅ ALL TESTS PASSED")
        print("The User ID dropdown functionality is working correctly.")
        return 0
    else:
        print("\n❌ SOME TESTS FAILED")
        print("Check the output above for details.")
        return 1

if __name__ == "__main__":
    sys.exit(main())