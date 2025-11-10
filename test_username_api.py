"""
Test script for username management API endpoints

This script demonstrates how to:
1. Get a user's name (defaults to user_id if not set)
2. Update a user's name
3. Verify the update

Usage:
    python test_username_api.py
"""

import requests
import json

# Configuration
BASE_URL = "http://localhost:8001"  # Update this to match your server
TEST_USER_ID = "test_user_123"

def test_get_username(user_id):
    """Test GET /user/{user_id}/name endpoint"""
    print(f"\n{'='*60}")
    print(f"Testing GET /user/{user_id}/name")
    print('='*60)

    response = requests.get(f"{BASE_URL}/user/{user_id}/name")

    print(f"Status Code: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")

    return response.json()

def test_update_username(user_id, new_username):
    """Test PUT /user/{user_id}/name endpoint"""
    print(f"\n{'='*60}")
    print(f"Testing PUT /user/{user_id}/name")
    print('='*60)

    payload = {"username": new_username}
    response = requests.put(
        f"{BASE_URL}/user/{user_id}/name",
        json=payload
    )

    print(f"Status Code: {response.status_code}")
    print(f"Request Payload: {json.dumps(payload, indent=2)}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")

    return response.json()

def main():
    print("\n" + "="*60)
    print("USERNAME MANAGEMENT API TEST")
    print("="*60)

    # Test 1: Get default username (should return user_id)
    print("\n[Test 1] Get username before setting (should default to user_id)")
    result1 = test_get_username(TEST_USER_ID)
    assert result1["username"] == TEST_USER_ID or result1.get("source") == "mongodb", \
        f"Expected default username to be {TEST_USER_ID}"

    # Test 2: Update username
    print("\n[Test 2] Update username to 'Alice Johnson'")
    new_name = "Alice Johnson"
    result2 = test_update_username(TEST_USER_ID, new_name)
    assert result2["username"] == new_name, f"Expected username to be '{new_name}'"

    # Test 3: Get updated username
    print("\n[Test 3] Get username after update (should return 'Alice Johnson')")
    result3 = test_get_username(TEST_USER_ID)
    assert result3["username"] == new_name, f"Expected username to be '{new_name}'"
    assert result3.get("source") == "mongodb", "Expected source to be 'mongodb'"

    # Test 4: Update username again
    print("\n[Test 4] Update username to 'Dr. Alice'")
    new_name2 = "Dr. Alice"
    result4 = test_update_username(TEST_USER_ID, new_name2)
    assert result4["username"] == new_name2, f"Expected username to be '{new_name2}'"

    # Test 5: Verify final username
    print("\n[Test 5] Verify final username")
    result5 = test_get_username(TEST_USER_ID)
    assert result5["username"] == new_name2, f"Expected username to be '{new_name2}'"

    print("\n" + "="*60)
    print("ALL TESTS PASSED!")
    print("="*60)

    # Test with different user
    print("\n[Bonus] Test with a different user")
    another_user = "user_bob"
    test_get_username(another_user)
    test_update_username(another_user, "Bob Smith")
    test_get_username(another_user)

if __name__ == "__main__":
    try:
        main()
    except requests.exceptions.ConnectionError:
        print(f"\nERROR: Could not connect to server at {BASE_URL}")
        print("Please make sure the FastAPI server is running:")
        print("  python agent_fastapi_server_multiturn.py")
    except Exception as e:
        print(f"\nERROR: {e}")
        raise
