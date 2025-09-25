"""
Focused integration test for multi-turn chat workflow
Tests complete process: submit task -> check status -> continue session -> verify security
"""
import pytest
import io
from unittest.mock import Mock, patch, AsyncMock
from fastapi.testclient import TestClient

from agent_fastapi_server_multiturn import app


class TestWorkflowIntegration:
    """Integration test for complete workflow"""

    @pytest.fixture
    def client(self):
        return TestClient(app)

    @patch('agent_fastapi_server_multiturn.queue_manager')
    def test_complete_multiturn_workflow(self, mock_qm, client):
        """Test: Submit initial task -> Continue session -> Check security"""
        print("\n🎯 Complete Multi-Turn Workflow Test")

        # === STEP 1: Setup mocks ===
        mock_session = Mock()
        mock_session.user_id = "alice"
        mock_session.total_turns = 0
        mock_session.accumulated_context = ""

        mock_qm.create_or_get_multiturn_session.return_value = mock_session
        mock_qm.add_turn_to_session.side_effect = [1, 2]
        mock_qm.add_request.return_value = 1
        mock_qm.multiturn_sessions = {}

        # === STEP 2: Submit initial task with file ===
        print("1️⃣ Submitting initial task with test.txt...")

        test_file = io.BytesIO(b"Name,Age,City\nAlice,25,NYC\nBob,30,LA")
        test_file.name = "data.csv"

        form_data = {
            "message": "Analyze this CSV file and create a summary",
            "language": "en",
            "user_id": "alice"
        }
        files = {"files": ("data.csv", test_file, "text/csv")}

        response = client.post("/chat-queue", data=form_data, files=files)
        assert response.status_code == 200

        data = response.json()
        session_id = data["session_id"]
        assert data["turn_number"] == 1
        assert data["uploaded_files"] == 1
        assert data["status"] == "queued"

        print(f"   ✅ Task submitted: {session_id}")
        print(f"   ✅ Turn 1 with 1 file uploaded")

        # === STEP 3: Check status ===
        print("2️⃣ Checking task status...")

        mock_progress = {
            "session_id": session_id,
            "status": "processing",
            "is_complete": False,
            "user_id": "alice",
            "progress_updates": [
                {"type": "status", "message": "Processing file..."},
                {"type": "thinking_update", "content": "Analyzing CSV data..."}
            ]
        }
        mock_qm.get_session_progress.return_value = mock_progress

        with patch('agent_fastapi_server_multiturn.get_unified_session_manager') as mock_manager:
            unified_mock = Mock()
            unified_mock.get_session_status = AsyncMock(return_value=mock_progress)
            mock_manager.return_value = unified_mock

            status_response = client.get(f"/status/{session_id}?user_id=alice")
            assert status_response.status_code == 200

            status_data = status_response.json()
            assert status_data["status"] == "processing"
            assert len(status_data["progress_updates"]) == 2

        print("   ✅ Status retrieved successfully")

        # === STEP 4: Get snapshots ===
        print("3️⃣ Getting task snapshots...")

        mock_progress["periodic_snapshots"] = [
            {
                "timestamp": "2024-01-01T10:00:00",
                "status": "processing",
                "content": {"thinking_content": "Reading CSV file with 3 rows..."}
            }
        ]

        snapshots_response = client.get(f"/snapshots/{session_id}?user_id=alice")
        assert snapshots_response.status_code == 200

        snapshots_data = snapshots_response.json()
        assert "snapshots" in snapshots_data
        assert len(snapshots_data["snapshots"]) == 1

        print("   ✅ Snapshots retrieved")

        # === STEP 5: Continue session with new file ===
        print("4️⃣ Continuing session with additional file...")

        # Setup for continuation
        mock_session.total_turns = 1
        mock_qm.multiturn_sessions = {session_id: mock_session}

        new_file = io.BytesIO(b"Additional context: Budget analysis data\nQ1: $10000\nQ2: $15000")
        new_file.name = "budget.txt"

        continue_form = {
            "session_id": session_id,
            "message": "Now combine this budget data with the previous CSV analysis",
            "language": "en",
            "user_id": "alice"
        }
        continue_files = {"files": ("budget.txt", new_file, "text/plain")}

        continue_response = client.post("/continue-session", data=continue_form, files=continue_files)
        assert continue_response.status_code == 200

        continue_data = continue_response.json()
        assert continue_data["session_id"] == session_id
        assert continue_data["turn_number"] == 2
        assert continue_data["uploaded_files"] == 1

        print("   ✅ Turn 2 submitted with budget.txt")

        # === STEP 6: Simulate completion and download ===
        print("5️⃣ Testing download access...")

        with patch('agent_fastapi_server_multiturn.get_unified_session_manager') as mock_manager:
            unified_mock = Mock()
            unified_mock.get_session_by_id = AsyncMock(return_value={"user_id": "alice"})
            unified_mock.get_session_files = AsyncMock(return_value={
                "download_method": "local_zip",
                "zip_path": "/fake/nonexistent/path.zip"
            })
            mock_manager.return_value = unified_mock

            # Should get 404 for missing file (but not 403 for auth)
            download_response = client.get(f"/download/{session_id}?user_id=alice")
            assert download_response.status_code == 404  # File not found (good)

        print("   ✅ Download endpoint accessible (auth passed)")

        print("✅ Complete workflow successful!")

    @patch('agent_fastapi_server_multiturn.queue_manager')
    def test_security_isolation(self, mock_qm, client):
        """Test: User isolation across all endpoints"""
        print("\n🔐 Security Isolation Test")

        # Setup: Alice owns session, Bob tries to access
        alice_session = Mock()
        alice_session.user_id = "alice"
        alice_session.total_turns = 1
        alice_session.accumulated_context = "Alice's private data"

        mock_qm.multiturn_sessions = {"alice-session": alice_session}
        mock_qm.active_sessions = {"alice-session": Mock(user_id="alice")}

        print("1️⃣ Bob trying to continue Alice's session...")

        # Bob tries to continue Alice's session
        bob_form = {
            "session_id": "alice-session",
            "message": "Bob trying to access Alice's data",
            "language": "en",
            "user_id": "bob"
        }

        response = client.post("/continue-session", data=bob_form)
        assert response.status_code == 403
        assert "Access denied" in response.json()["detail"]

        print("   ✅ Cross-user session access blocked")

        print("2️⃣ Bob trying to check Alice's status...")

        with patch('agent_fastapi_server_multiturn.get_unified_session_manager') as mock_manager:
            unified_mock = Mock()
            unified_mock.get_session_status = AsyncMock(return_value={
                "user_id": "alice",
                "session_id": "alice-session"
            })
            mock_manager.return_value = unified_mock

            status_response = client.get("/status/alice-session?user_id=bob")
            assert status_response.status_code == 403

        print("   ✅ Cross-user status access blocked")

        print("3️⃣ Bob trying to get Alice's snapshots...")

        mock_qm.get_session_progress.return_value = {"user_id": "alice"}

        snapshots_response = client.get("/snapshots/alice-session?user_id=bob")
        assert snapshots_response.status_code == 403

        print("   ✅ Cross-user snapshots access blocked")

        print("4️⃣ Bob trying to stop Alice's task...")

        stop_response = client.post("/stop/alice-session?user_id=bob")
        assert stop_response.status_code == 403

        print("   ✅ Cross-user stop access blocked")

        print("✅ Security isolation working correctly!")

    def test_api_validation(self, client):
        """Test: Required parameters and validation"""
        print("\n✅ API Validation Test")

        print("1️⃣ Testing missing user_id validation...")

        # Endpoints that require user_id should return 422
        validation_tests = [
            ("GET", "/status/test-session"),
            ("GET", "/snapshots/test-session"),
            ("POST", "/stop/test-session"),
            ("GET", "/download/test-session"),
        ]

        for method, endpoint in validation_tests:
            if method == "GET":
                response = client.get(endpoint)
            else:
                response = client.post(endpoint)

            assert response.status_code == 422
            print(f"   ✅ {method} {endpoint} requires user_id")

        print("2️⃣ Testing form validation...")

        # Form endpoints without required fields
        response = client.post("/chat-queue", data={"message": "test"})  # Missing user_id
        assert response.status_code == 422

        response = client.post("/continue-session", data={"session_id": "test"})  # Missing user_id, message
        assert response.status_code == 422

        print("   ✅ Form validation working")
        print("✅ API validation test passed!")

    @patch('agent_fastapi_server_multiturn.queue_manager')
    def test_file_upload_types(self, mock_qm, client):
        """Test: Different file upload scenarios"""
        print("\n📎 File Upload Test")

        # Setup
        mock_session = Mock()
        mock_session.user_id = "alice"
        mock_session.total_turns = 0
        mock_qm.create_or_get_multiturn_session.return_value = mock_session
        mock_qm.add_turn_to_session.return_value = 1
        mock_qm.add_request.return_value = 1

        form_data = {
            "message": "Process these files",
            "language": "en",
            "user_id": "alice"
        }

        print("1️⃣ Testing CSV file upload...")

        csv_file = io.BytesIO(b"name,age\nAlice,25\nBob,30")
        csv_file.name = "data.csv"

        response = client.post("/chat-queue",
                              data=form_data,
                              files={"files": ("data.csv", csv_file, "text/csv")})
        assert response.status_code == 200
        assert response.json()["uploaded_files"] == 1

        print("   ✅ CSV upload successful")

        print("2️⃣ Testing multiple files...")

        file1 = io.BytesIO(b"File 1 content")
        file1.name = "file1.txt"
        file2 = io.BytesIO(b"File 2 content")
        file2.name = "file2.txt"

        response = client.post("/chat-queue",
                              data=form_data,
                              files=[
                                  ("files", ("file1.txt", file1, "text/plain")),
                                  ("files", ("file2.txt", file2, "text/plain"))
                              ])
        assert response.status_code == 200
        assert response.json()["uploaded_files"] == 2

        print("   ✅ Multiple file upload successful")

        print("3️⃣ Testing no files...")

        response = client.post("/chat-queue", data=form_data)
        assert response.status_code == 200
        assert response.json()["uploaded_files"] == 0

        print("   ✅ No files upload successful")

        print("✅ File upload test passed!")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])