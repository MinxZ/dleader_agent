#!/usr/bin/env python3
"""
Test script for the chat session sharing functionality

This script tests:
1. Sharing a session with tags
2. Searching for shared sessions
3. Viewing a shared session
4. Getting popular tags
"""

import requests
import json
import time
from typing import Optional, Dict, List

BASE_URL = "http://localhost:8001"

def test_share_session():
    """Test sharing a session"""
    print("\n=== Testing Share Session ===")

    # Sample session ID (you'll need to replace with an actual session ID)
    session_id = "test-session-123"

    share_data = {
        "session_id": session_id,
        "title": "Test Drug Discovery Analysis",
        "description": "Analysis of potential cancer drug compounds using AI",
        "tags": ["drug-discovery", "cancer-research", "AI-analysis"],
        "visibility": "community",
        "user_id": "test_user"
    }

    try:
        response = requests.post(f"{BASE_URL}/share-session", json=share_data)
        if response.status_code == 200:
            print("✅ Session shared successfully!")
            print(f"Response: {json.dumps(response.json(), indent=2)}")
            return True
        else:
            print(f"❌ Failed to share session: {response.status_code}")
            print(f"Error: {response.text}")
            return False
    except Exception as e:
        print(f"❌ Error sharing session: {e}")
        return False

def test_search_sessions():
    """Test searching for shared sessions"""
    print("\n=== Testing Search Sessions ===")

    search_data = {
        "search_query": "cancer",
        "tags": ["cancer-research"],
        "visibility": "community",
        "limit": 10,
        "offset": 0
    }

    try:
        response = requests.post(f"{BASE_URL}/search-shared-sessions", json=search_data)
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Search successful! Found {data.get('total', 0)} sessions")
            sessions = data.get('sessions', [])
            for session in sessions[:3]:  # Show first 3
                print(f"\n  Session: {session.get('title', 'Untitled')}")
                print(f"  ID: {session.get('session_id', '')[:8]}...")
                print(f"  Tags: {', '.join(session.get('tags', []))}")
            return True
        else:
            print(f"❌ Search failed: {response.status_code}")
            print(f"Error: {response.text}")
            return False
    except Exception as e:
        print(f"❌ Error searching sessions: {e}")
        return False

def test_get_popular_tags():
    """Test getting popular tags"""
    print("\n=== Testing Popular Tags ===")

    try:
        response = requests.get(f"{BASE_URL}/popular-tags?limit=10")
        if response.status_code == 200:
            data = response.json()
            tags = data.get('tags', [])
            if tags:
                print("✅ Popular tags retrieved:")
                for tag in tags:
                    print(f"  - {tag.get('tag', '')} ({tag.get('count', 0)} uses)")
            else:
                print("ℹ️ No tags found yet")
            return True
        else:
            print(f"❌ Failed to get tags: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Error getting popular tags: {e}")
        return False

def test_view_shared_session(session_id: str):
    """Test viewing a specific shared session"""
    print(f"\n=== Testing View Session: {session_id} ===")

    try:
        response = requests.get(f"{BASE_URL}/shared-session/{session_id}")
        if response.status_code == 200:
            session = response.json()
            print(f"✅ Session retrieved successfully!")
            print(f"  Title: {session.get('title', 'Untitled')}")
            print(f"  Shared by: {session.get('shared_by', 'Unknown')}")
            print(f"  Tags: {', '.join(session.get('tags', []))}")
            print(f"  Total turns: {session.get('total_turns', 0)}")
            return True
        else:
            print(f"❌ Failed to get session: {response.status_code}")
            print(f"Error: {response.text}")
            return False
    except Exception as e:
        print(f"❌ Error viewing session: {e}")
        return False

def test_unshare_session(session_id: str, user_id: str):
    """Test unsharing a session"""
    print(f"\n=== Testing Unshare Session: {session_id} ===")

    try:
        response = requests.post(
            f"{BASE_URL}/unshare-session",
            params={"session_id": session_id, "user_id": user_id}
        )
        if response.status_code == 200:
            print("✅ Session unshared successfully!")
            return True
        else:
            print(f"❌ Failed to unshare: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Error unsharing session: {e}")
        return False

def main():
    """Run all tests"""
    print("=" * 50)
    print("Chat Session Sharing Functionality Tests")
    print("=" * 50)

    # Check if server is running
    try:
        response = requests.get(f"{BASE_URL}/health", timeout=2)
        if response.status_code != 200:
            print("❌ Server is not healthy!")
            return
        print("✅ Server is healthy")
    except Exception as e:
        print(f"❌ Cannot connect to server at {BASE_URL}")
        print(f"   Error: {e}")
        print("\n   Please make sure the FastAPI server is running:")
        print("   python agent_fastapi_server_multiturn.py")
        return

    # Run tests
    results = {
        "Share Session": test_share_session(),
        "Search Sessions": test_search_sessions(),
        "Popular Tags": test_get_popular_tags(),
        "View Session": test_view_shared_session("test-session-123"),
    }

    # Print summary
    print("\n" + "=" * 50)
    print("Test Summary:")
    print("=" * 50)

    for test_name, passed in results.items():
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"{test_name}: {status}")

    total_tests = len(results)
    passed_tests = sum(results.values())
    print(f"\nTotal: {passed_tests}/{total_tests} tests passed")

    if passed_tests == total_tests:
        print("\n🎉 All tests passed!")
    else:
        print(f"\n⚠️ {total_tests - passed_tests} test(s) failed")

if __name__ == "__main__":
    main()