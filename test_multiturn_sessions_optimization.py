#!/usr/bin/env python3
"""
Test script to verify /multiturn-sessions endpoint returns only metadata
without heavy content like full reports and thinking processes.
"""

import requests
import json

def test_multiturn_sessions_metadata_only():
    """Test that /multiturn-sessions returns only metadata"""

    BASE_URL = "http://localhost:8001"
    USER_ID = "test_user_dleader"

    print("=" * 60)
    print("Testing /multiturn-sessions Metadata Optimization")
    print("=" * 60)

    # Get all sessions
    response = requests.get(
        f"{BASE_URL}/multiturn-sessions",
        params={"user_id": USER_ID}
    )

    if response.status_code != 200:
        print(f"❌ Error: {response.status_code}")
        print(response.text)
        return False

    data = response.json()
    sessions = data.get("sessions", [])

    print(f"\n✅ Found {len(sessions)} sessions")

    if not sessions:
        print("⚠️  No sessions found. Create a session first to test.")
        return True

    # Check first session
    first_session = sessions[0]
    print(f"\n📋 First session metadata:")
    print(f"   Session ID: {first_session.get('session_id')}")
    print(f"   Session Name: {first_session.get('session_name')}")
    print(f"   Total Turns: {first_session.get('total_turns')}")
    print(f"   Created: {first_session.get('created_at')}")
    print(f"   Status: {first_session.get('session_status')}")
    print(f"   First Query: {first_session.get('first_query', '')[:50]}...")

    # Verify metadata-only response
    print("\n🔍 Checking for heavy content exclusion:")

    has_heavy_content = False
    excluded_fields = []

    # Check if turns data is included (should NOT be)
    if "turns" in first_session:
        has_heavy_content = True
        excluded_fields.append("turns")
        print("   ❌ FAIL: 'turns' array found in response (should be excluded)")
    else:
        print("   ✅ PASS: 'turns' array not included")

    # Check if individual turn content is included
    for key in ["response_content", "final_report", "thinking_content", "thinking_process"]:
        if key in first_session:
            has_heavy_content = True
            excluded_fields.append(key)
            print(f"   ❌ FAIL: '{key}' found in response (should be excluded)")

    if not excluded_fields:
        print("   ✅ PASS: No heavy content fields found")

    # Verify expected metadata fields are present
    print("\n📊 Verifying expected metadata fields:")
    expected_fields = [
        "session_id", "session_name", "user_id", "total_turns",
        "created_at", "last_updated", "language", "session_status",
        "first_query", "latest_query", "is_shared"
    ]

    missing_fields = []
    for field in expected_fields:
        if field in first_session:
            print(f"   ✅ {field}")
        else:
            missing_fields.append(field)
            print(f"   ⚠️  {field} (missing)")

    # Calculate response size
    response_size = len(response.text)
    print(f"\n📦 Response size: {response_size:,} bytes")

    # Summary
    print("\n" + "=" * 60)
    if has_heavy_content:
        print("❌ TEST FAILED: Heavy content found in response")
        print(f"   Excluded fields found: {', '.join(excluded_fields)}")
        return False
    elif missing_fields:
        print("⚠️  TEST PASSED with warnings")
        print(f"   Missing expected fields: {', '.join(missing_fields)}")
        return True
    else:
        print("✅ TEST PASSED: Response contains only metadata")
        print("   All expected fields present")
        print("   No heavy content included")
        return True

if __name__ == "__main__":
    try:
        success = test_multiturn_sessions_metadata_only()
        exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ Test failed with exception: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
