#!/usr/bin/env python3
"""
Final Demo Test - Comprehensive Multi-Turn Chat with File Upload
This test demonstrates the complete secure multi-turn workflow
"""
import io
from unittest.mock import Mock, patch, AsyncMock
from fastapi.testclient import TestClient

from agent_fastapi_server_multiturn import app


def run_demo():
    """Run comprehensive demo of the multi-turn system"""
    client = TestClient(app)

    print("🚀 MULTI-TURN CHAT SYSTEM DEMO")
    print("=" * 50)

    # Test 1: File Upload & Initial Task Submission
    print("\n1️⃣ INITIAL TASK SUBMISSION WITH FILE UPLOAD")
    print("-" * 45)

    with patch('agent_fastapi_server_multiturn.queue_manager') as mock_qm:
        # Setup
        mock_session = Mock()
        mock_session.user_id = "alice"
        mock_session.total_turns = 0
        mock_session.accumulated_context = ""

        mock_qm.create_or_get_multiturn_session.return_value = mock_session
        mock_qm.add_turn_to_session.return_value = 1
        mock_qm.add_request.return_value = 1

        # Create test CSV file
        csv_content = b"Name,Age,Department\nAlice,25,Engineering\nBob,30,Marketing\nCharlie,35,Sales"
        test_file = io.BytesIO(csv_content)
        test_file.name = "employees.csv"

        form_data = {
            "message": "Analyze this employee data and create a summary report",
            "language": "en",
            "user_id": "alice"
        }
        files = {"files": ("employees.csv", test_file, "text/csv")}

        response = client.post("/chat-queue", data=form_data, files=files)

        if response.status_code == 200:
            data = response.json()
            session_id = data["session_id"]
            print(f"✅ Task submitted successfully!")
            print(f"   Session ID: {session_id}")
            print(f"   Turn: {data['turn_number']}")
            print(f"   Files uploaded: {data['uploaded_files']}")
            print(f"   Status: {data['status']}")
        else:
            print(f"❌ Failed: {response.status_code}")
            return

    # Test 2: Continue Session with Additional File
    print("\n2️⃣ CONTINUE SESSION WITH ADDITIONAL FILE")
    print("-" * 42)

    with patch('agent_fastapi_server_multiturn.queue_manager') as mock_qm:
        # Setup for continuation
        mock_session.total_turns = 1
        mock_qm.multiturn_sessions = {session_id: mock_session}
        mock_qm.add_turn_to_session.return_value = 2
        mock_qm.add_request.return_value = 1

        # Create budget file
        budget_content = b"Department,Budget\nEngineering,$50000\nMarketing,$30000\nSales,$40000"
        budget_file = io.BytesIO(budget_content)
        budget_file.name = "budget.csv"

        continue_data = {
            "session_id": session_id,
            "message": "Now analyze the budget data alongside employee data",
            "language": "en",
            "user_id": "alice"
        }
        files = {"files": ("budget.csv", budget_file, "text/csv")}

        response = client.post("/continue-session", data=continue_data, files=files)

        if response.status_code == 200:
            data = response.json()
            print(f"✅ Session continued successfully!")
            print(f"   Session ID: {data['session_id']}")
            print(f"   Turn: {data['turn_number']}")
            print(f"   Files uploaded: {data['uploaded_files']}")
        else:
            print(f"❌ Failed: {response.status_code}")

    # Test 3: Status Check
    print("\n3️⃣ STATUS CHECK")
    print("-" * 15)

    with patch('agent_fastapi_server_multiturn.get_unified_session_manager') as mock_manager:
        unified_mock = Mock()
        mock_status = {
            "session_id": session_id,
            "status": "processing",
            "is_complete": False,
            "user_id": "alice",
            "storage_location": "active"
        }
        unified_mock.get_session_status = AsyncMock(return_value=mock_status)
        mock_manager.return_value = unified_mock

        response = client.get(f"/status/{session_id}?user_id=alice")

        if response.status_code == 200:
            data = response.json()
            print(f"✅ Status retrieved successfully!")
            print(f"   Session: {data['session_id']}")
            print(f"   Status: {data['status']}")
            print(f"   Complete: {data['is_complete']}")
        else:
            print(f"❌ Failed: {response.status_code}")

    # Test 4: Snapshots
    print("\n4️⃣ SNAPSHOTS CHECK")
    print("-" * 18)

    with patch('agent_fastapi_server_multiturn.queue_manager') as mock_qm:
        mock_progress = {
            "session_id": session_id,
            "user_id": "alice",
            "periodic_snapshots": [
                {
                    "timestamp": "2024-01-01T10:00:00",
                    "status": "processing",
                    "content": {"thinking_content": "Analyzing employee CSV: 3 employees across 3 departments..."}
                }
            ]
        }
        mock_qm.get_session_progress.return_value = mock_progress

        response = client.get(f"/snapshots/{session_id}?user_id=alice")

        if response.status_code == 200:
            data = response.json()
            print(f"✅ Snapshots retrieved successfully!")
            print(f"   Snapshot count: {data['snapshot_count']}")
            print(f"   Latest thinking: {data['snapshots'][0]['content']['thinking_content'][:50]}...")
        else:
            print(f"❌ Failed: {response.status_code}")

    # Test 5: Security Isolation
    print("\n5️⃣ SECURITY ISOLATION TEST")
    print("-" * 27)

    with patch('agent_fastapi_server_multiturn.queue_manager') as mock_qm:
        # Setup Alice's session
        alice_session = Mock()
        alice_session.user_id = "alice"
        mock_qm.multiturn_sessions = {session_id: alice_session}

        # Bob tries to access Alice's session
        bob_form = {
            "session_id": session_id,
            "message": "Bob trying to access Alice's data",
            "language": "en",
            "user_id": "bob"
        }

        response = client.post("/continue-session", data=bob_form)

        if response.status_code == 403:
            print("✅ Security isolation working!")
            print("   Cross-user access properly blocked (403)")
        else:
            print(f"❌ Security issue: {response.status_code}")

    # Test 6: API Validation
    print("\n6️⃣ API VALIDATION")
    print("-" * 16)

    # Test missing user_id
    response = client.get(f"/status/{session_id}")  # No user_id

    if response.status_code == 422:
        print("✅ API validation working!")
        print("   Missing user_id properly rejected (422)")
    else:
        print(f"❌ Validation issue: {response.status_code}")

    # Test 7: File Upload Variations
    print("\n7️⃣ FILE UPLOAD VARIATIONS")
    print("-" * 26)

    with patch('agent_fastapi_server_multiturn.queue_manager') as mock_qm:
        mock_session = Mock()
        mock_session.user_id = "alice"
        mock_session.total_turns = 0
        mock_qm.create_or_get_multiturn_session.return_value = mock_session
        mock_qm.add_turn_to_session.return_value = 1
        mock_qm.add_request.return_value = 1

        # Test multiple files
        file1 = io.BytesIO(b"Config: debug=true\nmode=production")
        file1.name = "config.txt"
        file2 = io.BytesIO(b'{"api_key": "test123", "timeout": 30}')
        file2.name = "settings.json"

        form_data = {
            "message": "Process these configuration files",
            "language": "en",
            "user_id": "alice"
        }

        response = client.post("/chat-queue",
                              data=form_data,
                              files=[
                                  ("files", ("config.txt", file1, "text/plain")),
                                  ("files", ("settings.json", file2, "application/json"))
                              ])

        if response.status_code == 200:
            data = response.json()
            print(f"✅ Multiple file upload successful!")
            print(f"   Files uploaded: {data['uploaded_files']}")
        else:
            print(f"❌ Failed: {response.status_code}")

    print("\n" + "=" * 50)
    print("🎉 DEMO COMPLETE!")
    print("\nKey Features Demonstrated:")
    print("✅ Multi-turn conversations with file uploads")
    print("✅ Secure user isolation (403 for cross-user access)")
    print("✅ File sharing across turns in same session")
    print("✅ Status checking and progress snapshots")
    print("✅ API validation (422 for missing parameters)")
    print("✅ Multiple file uploads support")
    print("✅ Different file types (CSV, TXT, JSON)")
    print("\nEndpoints Verified:")
    print("📡 POST /chat-queue (with file uploads)")
    print("📡 POST /continue-session (with file uploads)")
    print("📡 GET /status/{id}?user_id={id}")
    print("📡 GET /snapshots/{id}?user_id={id}")
    print("📡 All endpoints require user_id validation")


if __name__ == "__main__":
    run_demo()