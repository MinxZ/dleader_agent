"""
Tests for FastAPI server endpoints and queue management
"""
import pytest
import asyncio
from unittest.mock import Mock, patch, AsyncMock
from fastapi.testclient import TestClient
from datetime import datetime
import json
import os
import tempfile

from agent_fastapi_server_multiturn import (
    app, queue_manager, UserRequest, Language,
    MultiTurnSession, ConversationTurn, QueueManager
)


class TestFastAPIEndpoints:
    """Test FastAPI server endpoints"""

    @pytest.fixture
    def client(self):
        """Create test client"""
        return TestClient(app)

    @pytest.fixture
    def mock_queue_manager(self):
        """Mock queue manager for testing"""
        mock_qm = Mock(spec=QueueManager)
        mock_qm.active_sessions = {}
        mock_qm.multiturn_sessions = {}
        mock_qm.add_request = Mock(return_value=1)
        mock_qm.create_or_get_multiturn_session = Mock()
        mock_qm.add_turn_to_session = Mock(return_value=1)
        return mock_qm

    def test_health_endpoint(self, client):
        """Test health check endpoint"""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "timestamp" in data

    @patch('agent_fastapi_server_multiturn.queue_manager')
    def test_chat_queue_endpoint(self, mock_qm, client):
        """Test chat queue endpoint with Form data"""
        # Mock the queue manager
        mock_multiturn_session = Mock()
        mock_qm.create_or_get_multiturn_session.return_value = mock_multiturn_session
        mock_qm.add_turn_to_session.return_value = 1
        mock_qm.add_request.return_value = 1

        # Use form data instead of JSON for file upload endpoint
        form_data = {
            "message": "Test message",
            "language": "en",
            "user_id": "test-user"
        }

        response = client.post("/chat-queue", data=form_data)
        assert response.status_code == 200
        data = response.json()

        assert "session_id" in data
        assert data["status"] == "queued"
        assert data["turn_number"] == 1
        assert data["position"] == 1
        assert "uploaded_files" in data

    @patch('agent_fastapi_server_multiturn.queue_manager')
    def test_continue_session_endpoint(self, mock_qm, client):
        """Test continue session endpoint with Form data"""
        # Setup mock multiturn session
        mock_session = Mock()
        mock_session.accumulated_context = "Previous context"
        mock_session.user_id = "test-user"
        mock_session.total_turns = 1
        mock_qm.multiturn_sessions = {"test-session": mock_session}
        mock_qm.add_turn_to_session.return_value = 2
        mock_qm.add_request.return_value = 1

        # Use form data for file upload endpoint
        form_data = {
            "session_id": "test-session",
            "message": "Continue message",
            "language": "en",
            "user_id": "test-user"
        }

        response = client.post("/continue-session", data=form_data)
        assert response.status_code == 200
        data = response.json()

        assert data["session_id"] == "test-session"
        assert data["turn_number"] == 2
        assert data["status"] == "queued"
        assert "uploaded_files" in data

    def test_continue_session_not_found(self, client):
        """Test continue session with non-existent session"""
        form_data = {
            "session_id": "non-existent",
            "message": "Continue message",
            "language": "en",
            "user_id": "test-user"
        }

        response = client.post("/continue-session", data=form_data)
        assert response.status_code == 404
        assert "not found" in response.json()["detail"]

    @patch('agent_fastapi_server_multiturn.get_unified_session_manager')
    def test_status_endpoint(self, mock_get_manager, client):
        """Test status endpoint with user_id"""
        # Mock unified session manager
        mock_manager = Mock()
        mock_status = {
            "session_id": "test-session",
            "status": "completed",
            "is_complete": True,
            "is_cancelled": False,
            "created_at": "2024-01-01T10:00:00",
            "progress_updates": [],
            "user_id": "test-user"
        }
        mock_manager.get_session_status = AsyncMock(return_value=mock_status)
        mock_get_manager.return_value = mock_manager

        response = client.get("/status/test-session?user_id=test-user")
        assert response.status_code == 200
        data = response.json()

        assert data["session_id"] == "test-session"
        assert data["status"] == "completed"

    @patch('agent_fastapi_server_multiturn.get_unified_session_manager')
    def test_status_not_found(self, mock_get_manager, client):
        """Test status endpoint with non-existent session"""
        mock_manager = Mock()
        mock_manager.get_session_status = AsyncMock(return_value=None)
        mock_get_manager.return_value = mock_manager

        response = client.get("/status/non-existent?user_id=test-user")
        assert response.status_code == 404

    @patch('agent_fastapi_server_multiturn.get_unified_session_manager')
    def test_all_sessions_endpoint(self, mock_get_manager, client):
        """Test all sessions endpoint"""
        mock_manager = Mock()
        mock_sessions = [
            {
                "session_id": "session-1",
                "query": "Test query 1",
                "status": "completed",
                "user_id": "user-1"
            },
            {
                "session_id": "session-2",
                "query": "Test query 2",
                "status": "processing",
                "user_id": "user-2"
            }
        ]
        mock_manager.get_all_sessions = AsyncMock(return_value=mock_sessions)
        mock_get_manager.return_value = mock_manager

        response = client.get("/all-sessions")
        assert response.status_code == 200
        data = response.json()

        assert "sessions" in data
        assert len(data["sessions"]) == 2

    @patch('agent_fastapi_server_multiturn.get_unified_session_manager')
    def test_all_sessions_with_user_filter(self, mock_get_manager, client):
        """Test all sessions endpoint with user_id filter"""
        mock_manager = Mock()
        mock_sessions = [
            {
                "session_id": "session-1",
                "query": "Test query 1",
                "status": "completed",
                "user_id": "test-user"
            }
        ]
        mock_manager.get_all_sessions = AsyncMock(return_value=mock_sessions)
        mock_get_manager.return_value = mock_manager

        response = client.get("/all-sessions?user_id=test-user")
        assert response.status_code == 200

        # Verify the manager was called with user_id
        mock_manager.get_all_sessions.assert_called_once_with(include_cloud=True, user_id="test-user")

    @patch('agent_fastapi_server_multiturn.get_unified_session_manager')
    def test_multiturn_sessions_endpoint(self, mock_get_manager, client):
        """Test multi-turn sessions endpoint"""
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

        response = client.get("/multiturn-sessions")
        assert response.status_code == 200
        data = response.json()

        assert "sessions" in data
        assert len(data["sessions"]) == 1

    @patch('agent_fastapi_server_multiturn.queue_manager')
    def test_stop_session_endpoint(self, mock_qm, client):
        """Test stop session endpoint with user_id"""
        mock_user_request = Mock()
        mock_user_request.is_complete = False
        mock_user_request.is_cancelled = False
        mock_user_request.user_id = "test-user"
        mock_qm.active_sessions = {"test-session": mock_user_request}
        mock_qm.stop_session = Mock(return_value=True)

        response = client.post("/stop/test-session?user_id=test-user")
        assert response.status_code == 200
        data = response.json()

        assert data["session_id"] == "test-session"
        assert "cancelled" in data["message"]

    def test_stop_session_not_found(self, client):
        """Test stop session with non-existent session"""
        response = client.post("/stop/non-existent?user_id=test-user")
        assert response.status_code == 404

    @patch('agent_fastapi_server_multiturn.queue_manager')
    def test_chat_queue_with_file_upload(self, mock_qm, client):
        """Test chat queue endpoint with file upload"""
        import io

        # Mock the queue manager
        mock_multiturn_session = Mock()
        mock_qm.create_or_get_multiturn_session.return_value = mock_multiturn_session
        mock_qm.add_turn_to_session.return_value = 1
        mock_qm.add_request.return_value = 1

        # Create a test file
        test_file = io.BytesIO(b"test file content")
        test_file.name = "test.txt"

        files = {"files": ("test.txt", test_file, "text/plain")}
        data = {
            "message": "Test message with file",
            "language": "en",
            "user_id": "test-user"
        }

        response = client.post("/chat-queue", data=data, files=files)
        assert response.status_code == 200
        response_data = response.json()

        assert "session_id" in response_data
        assert response_data["status"] == "queued"
        assert "uploaded_files" in response_data

    @patch('agent_fastapi_server_multiturn.queue_manager')
    def test_continue_session_with_file_upload(self, mock_qm, client):
        """Test continue session endpoint with file upload"""
        import io

        # Setup mock multiturn session
        mock_session = Mock()
        mock_session.accumulated_context = "Previous context"
        mock_session.user_id = "test-user"
        mock_session.total_turns = 1
        mock_qm.multiturn_sessions = {"test-session": mock_session}
        mock_qm.add_turn_to_session.return_value = 2
        mock_qm.add_request.return_value = 1

        # Create a test file
        test_file = io.BytesIO(b"turn 2 file content")
        test_file.name = "turn2_data.csv"

        files = {"files": ("turn2_data.csv", test_file, "text/csv")}
        data = {
            "session_id": "test-session",
            "message": "Continue with uploaded file",
            "language": "en",
            "user_id": "test-user"
        }

        response = client.post("/continue-session", data=data, files=files)
        assert response.status_code == 200
        response_data = response.json()

        assert response_data["session_id"] == "test-session"
        assert response_data["turn_number"] == 2
        assert "uploaded_files" in response_data

    @patch('agent_fastapi_server_multiturn.queue_manager')
    def test_user_id_authorization_failure(self, mock_qm, client):
        """Test user_id authorization failure on continue-session"""
        # Setup mock multiturn session with different user_id
        mock_session = Mock()
        mock_session.user_id = "original-user"  # Different from requester
        mock_qm.multiturn_sessions = {"test-session": mock_session}

        form_data = {
            "session_id": "test-session",
            "message": "Unauthorized access attempt",
            "language": "en",
            "user_id": "different-user"
        }

        response = client.post("/continue-session", data=form_data)
        assert response.status_code == 403  # Access denied for different user

    def test_missing_user_id_validation(self, client):
        """Test that user_id is required for endpoints"""
        # Test status endpoint without user_id
        response = client.get("/status/test-session")
        assert response.status_code == 422  # Validation error

        # Test continue-session without user_id
        form_data = {
            "session_id": "test-session",
            "message": "Test message",
            "language": "en"
        }
        response = client.post("/continue-session", data=form_data)
        assert response.status_code == 422  # Validation error


class TestUserRequest:
    """Test UserRequest class functionality"""

    def test_user_request_creation(self):
        """Test UserRequest object creation"""
        user_request = UserRequest(
            session_id="test-123",
            message="Test message",
            language=Language.EN,
            user_id="test-user"
        )

        assert user_request.session_id == "test-123"
        assert user_request.message == "Test message"
        assert user_request.language == Language.EN
        assert user_request.user_id == "test-user"
        assert user_request.status == "queued"
        assert user_request.is_complete is False
        assert user_request.is_cancelled is False

    def test_user_request_enhanced_message(self):
        """Test enhanced message building for multi-turn"""
        user_request = UserRequest(
            session_id="test-123",
            message="Follow up question",
            language=Language.EN,
            is_continuation=True,
            previous_context="Previous conversation context"
        )

        assert "Previous conversation context" in user_request.enhanced_message
        assert "Follow up question" in user_request.enhanced_message


class TestMultiTurnSession:
    """Test MultiTurnSession class functionality"""

    def test_multiturn_session_creation(self):
        """Test MultiTurnSession creation"""
        session = MultiTurnSession(
            session_id="mt-test-123",
            created_at=datetime.now().isoformat(),
            last_updated=datetime.now().isoformat(),
            language=Language.EN,
            user_id="test-user"
        )

        assert session.session_id == "mt-test-123"
        assert session.language == Language.EN
        assert session.user_id == "test-user"
        assert session.total_turns == 0
        assert session.session_status == "active"

    def test_multiturn_session_properties(self):
        """Test first_query and latest_query properties"""
        # Create session with turns
        turn1 = ConversationTurn(
            turn_number=1,
            query="First question",
            response_content="First response",
            final_report="First report",
            files=None,
            timestamp=datetime.now().isoformat(),
            status="completed"
        )

        turn2 = ConversationTurn(
            turn_number=2,
            query="Second question",
            response_content="Second response",
            final_report="Second report",
            files=None,
            timestamp=datetime.now().isoformat(),
            status="completed"
        )

        session = MultiTurnSession(
            session_id="mt-test-123",
            created_at=datetime.now().isoformat(),
            last_updated=datetime.now().isoformat(),
            language=Language.EN,
            turns=[turn1, turn2]
        )

        assert session.first_query == "First question"
        assert session.latest_query == "Second question"

    def test_multiturn_session_empty_properties(self):
        """Test properties with empty turns list"""
        session = MultiTurnSession(
            session_id="mt-test-123",
            created_at=datetime.now().isoformat(),
            last_updated=datetime.now().isoformat(),
            language=Language.EN
        )

        assert session.first_query == ""
        assert session.latest_query == ""


class TestQueueManager:
    """Test QueueManager functionality"""

    def test_queue_manager_initialization(self):
        """Test QueueManager initialization"""
        qm = QueueManager()

        assert hasattr(qm, 'request_queue')
        assert hasattr(qm, 'active_sessions')
        assert hasattr(qm, 'multiturn_sessions')
        assert len(qm.active_sessions) == 0
        # Don't assert exact count for multiturn_sessions since it loads from storage
        assert isinstance(qm.multiturn_sessions, dict)

    def test_create_multiturn_session(self):
        """Test creating multi-turn session"""
        qm = QueueManager()

        session = qm.create_or_get_multiturn_session(
            "test-session",
            Language.EN,
            "test-user"
        )

        assert session.session_id == "test-session"
        assert session.language == Language.EN
        assert session.user_id == "test-user"
        assert "test-session" in qm.multiturn_sessions

    def test_get_existing_multiturn_session(self):
        """Test getting existing multi-turn session"""
        qm = QueueManager()

        # Create session
        session1 = qm.create_or_get_multiturn_session("test-session", Language.EN)

        # Get same session
        session2 = qm.create_or_get_multiturn_session("test-session", Language.EN)

        assert session1 is session2

    @patch('agent_fastapi_server_multiturn.os.makedirs')
    @patch('agent_fastapi_server_multiturn.os.path.exists')
    def test_session_storage_operations(self, mock_exists, mock_makedirs):
        """Test session storage operations"""
        mock_exists.return_value = True

        qm = QueueManager()
        user_request = UserRequest(
            session_id="test-storage",
            message="Test message",
            language=Language.EN
        )

        # Test save operation doesn't raise errors
        try:
            qm._save_session_to_storage(user_request)
        except Exception as e:
            pytest.fail(f"Session storage failed: {e}")


if __name__ == "__main__":
    pytest.main([__file__])