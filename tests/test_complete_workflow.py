"""
Comprehensive integration test for the complete multi-turn chat workflow
Tests the entire process: chat-queue -> status -> snapshots -> continue-session -> download
Includes file uploads and user isolation testing
"""
import pytest
import asyncio
import time
import tempfile
import os
from unittest.mock import Mock, patch, AsyncMock
from fastapi.testclient import TestClient
from datetime import datetime
import json
import io

from agent_fastapi_server_multiturn import app, queue_manager


class TestCompleteWorkflow:
    """Test complete multi-turn workflow with file uploads"""

    @pytest.fixture
    def client(self):
        """Create test client"""
        return TestClient(app)

    @pytest.fixture
    def test_files(self):
        """Create test files for upload"""
        files = {}

        # Create test.txt for turn 1
        files['turn1'] = io.BytesIO(b"This is test content for turn 1\nLine 2\nLine 3")
        files['turn1'].name = "test.txt"

        # Create data.csv for turn 2
        files['turn2'] = io.BytesIO(b"name,age,city\nAlice,25,NYC\nBob,30,LA\nCharlie,35,Chicago")
        files['turn2'].name = "data.csv"

        return files

    @patch('agent_fastapi_server_multiturn.queue_manager')
    def test_complete_workflow_with_files(self, mock_qm, client, test_files):
        """Test complete workflow: chat-queue -> status -> continue -> snapshots -> download"""
        print("\n🚀 Starting Complete Workflow Test")

        # Setup mocks with proper attribute access
        mock_multiturn_session = Mock()
        mock_multiturn_session.user_id = "test-user"
        mock_multiturn_session.total_turns = 0
        mock_multiturn_session.accumulated_context = ""

        mock_qm.create_or_get_multiturn_session.return_value = mock_multiturn_session
        mock_qm.add_turn_to_session.side_effect = [1, 2]  # Return turn numbers
        mock_qm.add_request.return_value = 1

        # Use a function to return the session to avoid serialization issues
        def get_multiturn_sessions():
            return {"test-session": mock_multiturn_session}
        mock_qm.multiturn_sessions = get_multiturn_sessions()

        # Mock session progress for status checks
        mock_progress = {
            "session_id": "test-session",
            "status": "completed",
            "is_complete": True,
            "is_cancelled": False,
            "created_at": "2024-01-01T10:00:00",
            "progress_updates": [],
            "user_id": "test-user"
        }
        mock_qm.get_session_progress.return_value = mock_progress

        # Mock snapshots
        mock_snapshots = [
            {
                "session_id": "test-session",
                "timestamp": "2024-01-01T10:00:00",
                "status": "processing",
                "content": {"thinking_content": "Processing..."}
            }
        ]
        mock_progress["periodic_snapshots"] = mock_snapshots

        print("1️⃣ Testing initial chat-queue with file upload...")

        # Step 1: Submit initial request with file
        files_data = {"files": ("test.txt", test_files['turn1'], "text/plain")}
        form_data = {
            "message": "Analyze this test file",
            "language": "en",
            "user_id": "test-user"
        }

        response = client.post("/chat-queue", data=form_data, files=files_data)
        assert response.status_code == 200

        initial_data = response.json()
        session_id = initial_data["session_id"]
        assert initial_data["status"] == "queued"
        assert initial_data["turn_number"] == 1
        assert initial_data["uploaded_files"] == 1

        print(f"   ✅ Session created: {session_id}")
        print(f"   ✅ Turn 1 queued with 1 uploaded file")

        print("2️⃣ Testing status endpoint...")

        # Step 2: Check status
        with patch('agent_fastapi_server_multiturn.get_unified_session_manager') as mock_get_manager:
            mock_manager = Mock()
            mock_manager.get_session_status = AsyncMock(return_value=mock_progress)
            mock_get_manager.return_value = mock_manager

            status_response = client.get(f"/status/{session_id}?user_id=test-user")
            assert status_response.status_code == 200

            status_data = status_response.json()
            assert status_data["session_id"] == session_id
            assert status_data["status"] == "completed"

        print("   ✅ Status retrieved successfully")

        print("3️⃣ Testing snapshots endpoint...")

        # Step 3: Get snapshots
        snapshots_response = client.get(f"/snapshots/{session_id}?user_id=test-user")
        assert snapshots_response.status_code == 200

        snapshots_data = snapshots_response.json()
        assert "snapshots" in snapshots_data
        assert len(snapshots_data["snapshots"]) == 1

        print("   ✅ Snapshots retrieved successfully")

        print("4️⃣ Testing continue-session with new file...")

        # Step 4: Continue session with new file - need to set up session properly
        # Update the mock to have session in multiturn_sessions
        mock_multiturn_session.total_turns = 1  # Update for turn 2
        mock_qm.multiturn_sessions = {session_id: mock_multiturn_session}

        files_data2 = {"files": ("data.csv", test_files['turn2'], "text/csv")}
        continue_form_data = {
            "session_id": session_id,
            "message": "Now analyze this CSV data with the previous results",
            "language": "en",
            "user_id": "test-user"
        }

        continue_response = client.post("/continue-session", data=continue_form_data, files=files_data2)
        assert continue_response.status_code == 200

        continue_data = continue_response.json()
        assert continue_data["session_id"] == session_id
        assert continue_data["turn_number"] == 2
        assert continue_data["uploaded_files"] == 1

        print("   ✅ Turn 2 queued with 1 uploaded file")

        print("5️⃣ Testing download endpoint...")

        # Step 5: Test download (mocked)
        with patch('agent_fastapi_server_multiturn.get_unified_session_manager') as mock_get_manager:
            mock_manager = Mock()
            mock_session_data = {"user_id": "test-user"}
            mock_manager.get_session_by_id = AsyncMock(return_value=mock_session_data)

            mock_files_info = {
                "download_method": "local_zip",
                "zip_path": "/fake/path/session.zip"
            }
            mock_manager.get_session_files = AsyncMock(return_value=mock_files_info)
            mock_get_manager.return_value = mock_manager

            # This will fail because file doesn't exist, but we verify authorization works
            download_response = client.get(f"/download/{session_id}?user_id=test-user")
            # Should get 404 for missing file, not 403 for auth (good!)
            assert download_response.status_code == 404

        print("   ✅ Download endpoint accessible (file not found as expected)")

        print("✅ Complete workflow test passed!")

    @patch('agent_fastapi_server_multiturn.queue_manager')
    def test_user_isolation(self, mock_qm, client):
        """Test that users cannot access each other's sessions"""
        print("\n🔒 Testing User Isolation")

        # Setup session owned by user1
        mock_session = Mock()
        mock_session.user_id = "user1"
        mock_qm.multiturn_sessions = {"user1-session": mock_session}

        # Setup active session for user1
        mock_user_request = Mock()
        mock_user_request.user_id = "user1"
        mock_qm.active_sessions = {"user1-session": mock_user_request}

        print("1️⃣ Testing continue-session cross-user access...")

        # Test 1: user2 tries to continue user1's session
        form_data = {
            "session_id": "user1-session",
            "message": "Trying to access another user's session",
            "language": "en",
            "user_id": "user2"
        }

        response = client.post("/continue-session", data=form_data)
        assert response.status_code == 403
        assert "Access denied" in response.json()["detail"]

        print("   ✅ Cross-user continue-session blocked (403)")

        print("2️⃣ Testing status endpoint cross-user access...")

        # Test 2: status endpoint with wrong user
        with patch('agent_fastapi_server_multiturn.get_unified_session_manager') as mock_get_manager:
            mock_manager = Mock()
            mock_status = {
                "session_id": "user1-session",
                "user_id": "user1",
                "status": "completed"
            }
            mock_manager.get_session_status = AsyncMock(return_value=mock_status)
            mock_get_manager.return_value = mock_manager

            status_response = client.get("/status/user1-session?user_id=user2")
            assert status_response.status_code == 403

        print("   ✅ Cross-user status access blocked (403)")

        print("3️⃣ Testing snapshots endpoint cross-user access...")

        # Test 3: snapshots with wrong user
        mock_progress = {
            "session_id": "user1-session",
            "user_id": "user1",
            "periodic_snapshots": []
        }
        mock_qm.get_session_progress.return_value = mock_progress

        snapshots_response = client.get("/snapshots/user1-session?user_id=user2")
        assert snapshots_response.status_code == 403

        print("   ✅ Cross-user snapshots access blocked (403)")

        print("4️⃣ Testing stop endpoint cross-user access...")

        # Test 4: stop with wrong user
        stop_response = client.post("/stop/user1-session?user_id=user2")
        assert stop_response.status_code == 403

        print("   ✅ Cross-user stop access blocked (403)")

        print("✅ User isolation test passed!")

    def test_missing_user_id_validation(self, client):
        """Test that user_id is required for all endpoints"""
        print("\n🛡️ Testing Missing user_id Validation")

        print("1️⃣ Testing endpoints without user_id...")

        # Test endpoints that require user_id
        test_cases = [
            ("GET", "/status/test-session", 422),
            ("GET", "/snapshots/test-session", 422),
            ("POST", "/stop/test-session", 422),
            ("GET", "/download/test-session", 422),
            ("GET", "/results/test-session", 422),
        ]

        for method, endpoint, expected_status in test_cases:
            if method == "GET":
                response = client.get(endpoint)
            else:
                response = client.post(endpoint)

            assert response.status_code == expected_status
            print(f"   ✅ {method} {endpoint} requires user_id (422)")

        print("2️⃣ Testing form endpoints without user_id...")

        # Test form endpoints
        form_data_no_user = {
            "message": "Test message",
            "language": "en"
        }

        # chat-queue without user_id
        response = client.post("/chat-queue", data=form_data_no_user)
        assert response.status_code == 422
        print("   ✅ POST /chat-queue requires user_id (422)")

        # continue-session without user_id
        continue_data_no_user = {
            "session_id": "test-session",
            "message": "Test message",
            "language": "en"
        }
        response = client.post("/continue-session", data=continue_data_no_user)
        assert response.status_code == 422
        print("   ✅ POST /continue-session requires user_id (422)")

        print("✅ Missing user_id validation test passed!")

    @patch('agent_fastapi_server_multiturn.queue_manager')
    def test_file_upload_scenarios(self, mock_qm, client):
        """Test various file upload scenarios"""
        print("\n📁 Testing File Upload Scenarios")

        # Setup mocks
        mock_multiturn_session = Mock()
        mock_multiturn_session.user_id = "test-user"
        mock_multiturn_session.total_turns = 0
        mock_qm.create_or_get_multiturn_session.return_value = mock_multiturn_session
        mock_qm.add_turn_to_session.return_value = 1
        mock_qm.add_request.return_value = 1

        print("1️⃣ Testing single file upload...")

        # Test 1: Single file upload
        test_file = io.BytesIO(b"Single file content")
        test_file.name = "single.txt"

        files_data = {"files": ("single.txt", test_file, "text/plain")}
        form_data = {
            "message": "Process this single file",
            "language": "en",
            "user_id": "test-user"
        }

        response = client.post("/chat-queue", data=form_data, files=files_data)
        assert response.status_code == 200
        assert response.json()["uploaded_files"] == 1

        print("   ✅ Single file upload successful")

        print("2️⃣ Testing multiple file upload...")

        # Test 2: Multiple file upload
        file1 = io.BytesIO(b"First file content")
        file1.name = "file1.txt"
        file2 = io.BytesIO(b"Second file content")
        file2.name = "file2.txt"

        files_data = [
            ("files", ("file1.txt", file1, "text/plain")),
            ("files", ("file2.txt", file2, "text/plain"))
        ]

        response = client.post("/chat-queue", data=form_data, files=files_data)
        assert response.status_code == 200
        assert response.json()["uploaded_files"] == 2

        print("   ✅ Multiple file upload successful")

        print("3️⃣ Testing no file upload...")

        # Test 3: No files (should work)
        response = client.post("/chat-queue", data=form_data)
        assert response.status_code == 200
        assert response.json()["uploaded_files"] == 0

        print("   ✅ No file upload successful")

        print("4️⃣ Testing different file types...")

        # Test 4: Different file types
        csv_file = io.BytesIO(b"name,value\ntest,123")
        csv_file.name = "data.csv"

        json_file = io.BytesIO(b'{"key": "value", "number": 42}')
        json_file.name = "config.json"

        files_data = [
            ("files", ("data.csv", csv_file, "text/csv")),
            ("files", ("config.json", json_file, "application/json"))
        ]

        response = client.post("/chat-queue", data=form_data, files=files_data)
        assert response.status_code == 200
        assert response.json()["uploaded_files"] == 2

        print("   ✅ Different file types upload successful")

        print("✅ File upload scenarios test passed!")

    def test_multiturn_session_endpoints(self, client):
        """Test multi-turn session specific endpoints"""
        print("\n🔄 Testing Multi-Turn Session Endpoints")

        print("1️⃣ Testing /multiturn-sessions endpoint...")

        # Test multiturn-sessions endpoint
        with patch('agent_fastapi_server_multiturn.get_unified_session_manager') as mock_get_manager:
            mock_manager = Mock()
            mock_sessions = [
                {
                    "session_id": "mt-session-1",
                    "total_turns": 3,
                    "session_status": "active",
                    "user_id": "test-user"
                }
            ]
            mock_manager.get_multiturn_sessions = AsyncMock(return_value=mock_sessions)
            mock_get_manager.return_value = mock_manager

            response = client.get("/multiturn-sessions?user_id=test-user")
            assert response.status_code == 200

            data = response.json()
            assert "sessions" in data
            assert len(data["sessions"]) == 1

        print("   ✅ Multiturn sessions endpoint working")

        print("2️⃣ Testing /multiturn-session/{id} endpoint...")

        # Test specific multiturn session
        with patch('agent_fastapi_server_multiturn.queue_manager') as mock_qm:
            from agent_fastapi_server_multiturn import MultiTurnSession, Language

            # Create a real MultiTurnSession object that can be serialized
            mock_session = MultiTurnSession(
                session_id="mt-session-1",
                created_at="2024-01-01T10:00:00",
                last_updated="2024-01-01T10:00:00",
                language=Language.EN,
                user_id="test-user",
                total_turns=2
            )

            mock_qm.multiturn_sessions = {"mt-session-1": mock_session}

            response = client.get("/multiturn-session/mt-session-1?user_id=test-user")
            assert response.status_code == 200

        print("   ✅ Specific multiturn session endpoint working")

        print("3️⃣ Testing /turn-report endpoint...")

        # Test turn report
        with patch('agent_fastapi_server_multiturn.queue_manager') as mock_qm:
            from agent_fastapi_server_multiturn import ConversationTurn

            turn = ConversationTurn(
                turn_number=1,
                query="Test query",
                response_content="Test response",
                final_report="Test report",
                files={"test.txt": "/path/to/test.txt"},
                timestamp="2024-01-01T10:00:00",
                status="completed"
            )

            mock_session = Mock()
            mock_session.user_id = "test-user"
            mock_session.turns = [turn]
            mock_qm.multiturn_sessions = {"mt-session-1": mock_session}

            response = client.get("/turn-report/mt-session-1/1?user_id=test-user")
            assert response.status_code == 200

            data = response.json()
            assert data["turn_number"] == 1
            assert data["query"] == "Test query"

        print("   ✅ Turn report endpoint working")

        print("✅ Multi-turn session endpoints test passed!")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])