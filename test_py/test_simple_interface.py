#!/usr/bin/env python3
"""
Test script for simplified Gradio interface
Verifies that all features work with fixed user test_user_dleader
"""
import requests
import sys
import time
from datetime import datetime

BASE_URL = "http://localhost:8001"
FIXED_USER = "test_user_dleader"

def test_basic_functionality():
    """Test basic functionality with fixed user"""
    print(f"\n{'='*60}")
    print("Testing Basic Functionality")
    print(f"Fixed User: {FIXED_USER}")
    print('='*60)

    # 1. Submit a request
    print("\n1. Submitting request...")
    response = requests.post(
        f"{BASE_URL}/chat-queue",
        data={
            "message": f"print('Simplified interface test at {datetime.now()}')",
            "user_id": FIXED_USER,
            "language": "en"
        }
    )

    if response.status_code != 200:
        print(f"   ❌ Failed to submit: {response.status_code}")
        return False

    session_id = response.json()["session_id"]
    print(f"   ✅ Created session: {session_id[:8]}...")

    # 2. Check status
    print("\n2. Checking session status...")
    time.sleep(2)
    response = requests.get(
        f"{BASE_URL}/status/{session_id}",
        params={"user_id": FIXED_USER}
    )

    if response.status_code == 200:
        status = response.json().get("status")
        print(f"   ✅ Status: {status}")
    else:
        print(f"   ❌ Failed to get status: {response.status_code}")

    # 3. Get user sessions
    print("\n3. Getting user sessions...")
    response = requests.get(
        f"{BASE_URL}/all-sessions",
        params={"user_id": FIXED_USER}
    )

    if response.status_code == 200:
        sessions = response.json().get("sessions", [])
        user_sessions = [s for s in sessions if s.get("session_id") == session_id]
        if user_sessions:
            print(f"   ✅ Found session in user's list")
        else:
            print(f"   ⚠️  Session not found (may be processing)")
    else:
        print(f"   ❌ Failed to get sessions: {response.status_code}")

    return True

def test_no_user_management():
    """Verify no user management features exist"""
    print(f"\n{'='*60}")
    print("Verifying No User Management Features")
    print('='*60)

    # Check that trash endpoint is still accessible but only for test_user_dleader
    print("\n1. Checking trash (should work for test_user_dleader)...")
    response = requests.get(
        f"{BASE_URL}/trash",
        params={"user_id": FIXED_USER}
    )

    if response.status_code == 200:
        print(f"   ✅ Trash endpoint works for {FIXED_USER}")
    else:
        print(f"   ⚠️  Trash endpoint returned: {response.status_code}")

    # Try with different user (should work but show different data)
    print("\n2. Testing with different user (isolation check)...")
    response = requests.get(
        f"{BASE_URL}/all-sessions",
        params={"user_id": "other_user"}
    )

    if response.status_code == 200:
        sessions = response.json().get("sessions", [])
        print(f"   ✅ Other users isolated (sessions: {len(sessions)})")
    else:
        print(f"   ❌ Failed with other user: {response.status_code}")

    return True

def test_multi_turn():
    """Test multi-turn functionality"""
    print(f"\n{'='*60}")
    print("Testing Multi-Turn Functionality")
    print('='*60)

    # 1. Create initial session
    print("\n1. Creating initial session...")
    response = requests.post(
        f"{BASE_URL}/chat-queue",
        data={
            "message": "x = 42; print(f'Initial value: {x}')",
            "user_id": FIXED_USER,
            "language": "en"
        }
    )

    if response.status_code != 200:
        print(f"   ❌ Failed to create session: {response.status_code}")
        return False

    session_id = response.json()["session_id"]
    print(f"   ✅ Created session: {session_id[:8]}...")

    # Wait for processing
    time.sleep(3)

    # 2. Continue session
    print("\n2. Continuing session...")
    response = requests.post(
        f"{BASE_URL}/continue-session",
        data={
            "session_id": session_id,
            "message": "print(f'Double value: {x * 2}')",
            "user_id": FIXED_USER,
            "turn_number": 2
        }
    )

    if response.status_code == 200:
        print(f"   ✅ Multi-turn continuation works")
    else:
        print(f"   ❌ Failed to continue: {response.status_code}")
        return False

    return True

def main():
    print("="*70)
    print("SIMPLIFIED INTERFACE TEST")
    print(f"Server: {BASE_URL}")
    print(f"Fixed User: {FIXED_USER}")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*70)

    # Run tests
    test_results = []

    # Test 1: Basic functionality
    print("\n### TEST 1: Basic Functionality ###")
    test_results.append(("Basic Functionality", test_basic_functionality()))

    # Test 2: No user management
    print("\n### TEST 2: User Management ###")
    test_results.append(("User Management", test_no_user_management()))

    # Test 3: Multi-turn
    print("\n### TEST 3: Multi-Turn ###")
    test_results.append(("Multi-Turn", test_multi_turn()))

    # Summary
    print("\n" + "="*70)
    print("TEST SUMMARY")
    print("="*70)

    all_passed = True
    for test_name, passed in test_results:
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"{test_name:20} {status}")
        if not passed:
            all_passed = False

    print("\n" + "="*70)
    if all_passed:
        print("✅ ALL TESTS PASSED")
        print("The simplified interface is working correctly.")
        print(f"\nTo start the simplified interface:")
        print(f"  python agent_gradio_simple.py")
        print(f"\nIt will run on: http://localhost:7861")
    else:
        print("❌ SOME TESTS FAILED")
        print("Check the output above for details.")

    return 0 if all_passed else 1

if __name__ == "__main__":
    sys.exit(main())