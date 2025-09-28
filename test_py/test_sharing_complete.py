#!/usr/bin/env python3
"""
Complete test for sharing functionality including session creation
"""

import requests
import json
import time
import uuid

BASE_URL = "http://localhost:8001"
TEST_USER = "test_user_share"

def create_test_session():
    """Create a test multi-turn session first"""
    print("\n=== Creating Test Session ===")

    # Create initial session
    session_data = {
        "message": "What are the key biomarkers for lung cancer?",
        "language": "en",
        "user_id": TEST_USER
    }

    try:
        response = requests.post(f"{BASE_URL}/chat-queue", data=session_data)
        if response.status_code == 200:
            result = response.json()
            session_id = result.get("session_id")
            print(f"✅ Session created: {session_id}")

            # Wait a bit for processing
            print("⏳ Waiting for session to process...")
            time.sleep(5)

            # Add a continuation to make it multi-turn
            continue_data = {
                "session_id": session_id,
                "message": "Can you provide more details about PD-L1 expression?",
                "language": "en",
                "user_id": TEST_USER
            }

            response = requests.post(f"{BASE_URL}/continue", json=continue_data)
            if response.status_code == 200:
                print(f"✅ Added turn 2 to session")
                time.sleep(3)

            return session_id
        else:
            print(f"❌ Failed to create session: {response.status_code}")
            print(f"Response: {response.text}")
            return None
    except Exception as e:
        print(f"❌ Error creating session: {e}")
        return None

def share_session(session_id):
    """Share the created session"""
    print(f"\n=== Sharing Session {session_id} ===")

    share_data = {
        "session_id": session_id,
        "title": "Lung Cancer Biomarkers Research",
        "description": "Analysis of key biomarkers for lung cancer diagnosis and treatment, including PD-L1 expression patterns",
        "tags": ["lung-cancer", "biomarkers", "PD-L1", "cancer-research", "immunotherapy"],
        "visibility": "community",
        "user_id": TEST_USER
    }

    try:
        response = requests.post(f"{BASE_URL}/share-session", json=share_data)
        if response.status_code == 200:
            print("✅ Session shared successfully!")
            result = response.json()
            print(f"   Shared at: {result.get('shared_at', 'Unknown')}")
            return True
        else:
            print(f"❌ Failed to share: {response.status_code}")
            print(f"Error: {response.text}")
            return False
    except Exception as e:
        print(f"❌ Error sharing: {e}")
        return False

def search_shared_sessions():
    """Search for the shared session"""
    print("\n=== Searching Shared Sessions ===")

    # Search by tag
    search_data = {
        "tags": ["lung-cancer"],
        "visibility": "community",
        "limit": 10
    }

    try:
        response = requests.post(f"{BASE_URL}/search-shared-sessions", json=search_data)
        if response.status_code == 200:
            data = response.json()
            total = data.get('total', 0)
            print(f"✅ Found {total} sessions with 'lung-cancer' tag")

            sessions = data.get('sessions', [])
            for session in sessions[:3]:
                print(f"\n  📄 {session.get('title', 'Untitled')}")
                print(f"     ID: {session.get('session_id', '')[:8]}...")
                print(f"     Shared by: {session.get('shared_by', 'Unknown')}")
                print(f"     Tags: {', '.join(session.get('tags', []))}")
            return True
        else:
            print(f"❌ Search failed: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Error searching: {e}")
        return False

def view_shared_session(session_id):
    """View the shared session details"""
    print(f"\n=== Viewing Shared Session ===")

    try:
        response = requests.get(f"{BASE_URL}/shared-session/{session_id}")
        if response.status_code == 200:
            session = response.json()
            print(f"✅ Session retrieved:")
            print(f"   Title: {session.get('title', 'Untitled')}")
            print(f"   Description: {session.get('description', 'No description')[:100]}...")
            print(f"   Total turns: {len(session.get('turns', []))}")

            # Show first turn
            turns = session.get('turns', [])
            if turns:
                print(f"\n   First turn query: {turns[0].get('query', '')[:100]}...")
            return True
        else:
            print(f"❌ Failed to view: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Error viewing: {e}")
        return False

def get_popular_tags():
    """Get popular tags"""
    print("\n=== Getting Popular Tags ===")

    try:
        response = requests.get(f"{BASE_URL}/popular-tags?limit=10")
        if response.status_code == 200:
            data = response.json()
            tags = data.get('tags', [])
            if tags:
                print("✅ Popular tags:")
                for tag in tags[:5]:
                    print(f"   #{tag.get('tag', '')} ({tag.get('count', 0)} uses)")
            else:
                print("ℹ️ No tags found yet")
            return True
        else:
            print(f"❌ Failed: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def unshare_session(session_id):
    """Unshare the session"""
    print(f"\n=== Unsharing Session ===")

    try:
        response = requests.post(
            f"{BASE_URL}/unshare-session",
            params={"session_id": session_id, "user_id": TEST_USER}
        )
        if response.status_code == 200:
            print("✅ Session unshared successfully")
            return True
        else:
            print(f"❌ Failed: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def main():
    """Run complete test flow"""
    print("=" * 60)
    print("Complete Chat Session Sharing Test")
    print("=" * 60)

    # Check server health
    try:
        response = requests.get(f"{BASE_URL}/health", timeout=2)
        if response.status_code != 200:
            print("❌ Server is not healthy!")
            return
        print("✅ Server is healthy")
    except Exception as e:
        print(f"❌ Cannot connect to server at {BASE_URL}")
        print(f"   Please ensure the server is running:")
        print(f"   python agent_fastapi_server_multiturn.py")
        return

    # Run complete test flow
    print("\n" + "=" * 60)
    print("Starting Test Flow")
    print("=" * 60)

    # Step 1: Create a test session
    session_id = create_test_session()
    if not session_id:
        print("\n❌ Failed to create test session. Aborting tests.")
        return

    # Step 2: Share the session
    share_success = share_session(session_id)

    # Step 3: Search for shared sessions
    search_success = search_shared_sessions()

    # Step 4: View the shared session
    view_success = view_shared_session(session_id)

    # Step 5: Get popular tags
    tags_success = get_popular_tags()

    # Step 6: Unshare the session (cleanup)
    # unshare_success = unshare_session(session_id)

    # Print summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)

    results = {
        "Create Session": session_id is not None,
        "Share Session": share_success,
        "Search Sessions": search_success,
        "View Session": view_success,
        "Popular Tags": tags_success,
        # "Unshare Session": unshare_success
    }

    for test_name, passed in results.items():
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"{test_name}: {status}")

    total = len(results)
    passed = sum(results.values())
    print(f"\nTotal: {passed}/{total} tests passed")

    if passed == total:
        print("\n🎉 All tests passed! Sharing functionality is working correctly.")
    else:
        print(f"\n⚠️ {total - passed} test(s) failed")

    if session_id:
        print(f"\n📝 Test session ID: {session_id}")
        print(f"   You can now test the UI with this session in the Gradio interface")

if __name__ == "__main__":
    main()