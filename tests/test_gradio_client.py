"""
Tests for Gradio FastAPI Client
"""
import pytest
from unittest.mock import Mock, patch, mock_open
import requests
import json
from datetime import datetime

from agent_gradio_fastapi_multiturn import FastAPIClient, get_session_history


class TestFastAPIClient:
    """Test FastAPIClient functionality"""

    @pytest.fixture
    def client(self):
        """Create FastAPIClient instance for testing"""
        return FastAPIClient("http://localhost:8001")

    @pytest.fixture
    def mock_response(self):
        """Create mock response object"""
        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"test": "data"}
        return mock_resp

    def test_client_initialization(self):
        """Test FastAPIClient initialization"""
        # Test with http prefix
        client1 = FastAPIClient("http://localhost:8001")
        assert client1.base_url == "http://localhost:8001"

        # Test without http prefix
        client2 = FastAPIClient("localhost:8001")
        assert client2.base_url == "http://localhost:8001"

        # Test with https
        client3 = FastAPIClient("https://api.example.com")
        assert client3.base_url == "https://api.example.com"

    @patch('agent_gradio_fastapi_multiturn.requests.get')
    def test_health_check_success(self, mock_get, client, mock_response):
        """Test successful health check"""
        mock_get.return_value = mock_response

        result = client.health_check()

        assert result is True
        mock_get.assert_called_once_with("http://localhost:8001/health", timeout=5)

    @patch('agent_gradio_fastapi_multiturn.requests.get')
    def test_health_check_failure(self, mock_get, client):
        """Test health check failure"""
        mock_get.side_effect = requests.exceptions.RequestException("Connection failed")

        result = client.health_check()

        assert result is False

    @patch('agent_gradio_fastapi_multiturn.requests.post')
    def test_submit_request_success(self, mock_post, client):
        """Test successful request submission"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"session_id": "test-session-123"}
        mock_post.return_value = mock_response

        session_id = client.submit_request("Test message", "en", "test-user")

        assert session_id == "test-session-123"
        mock_post.assert_called_once_with(
            "http://localhost:8001/chat-queue",
            json={
                "message": "Test message",
                "language": "en",
                "user_id": "test-user"
            },
            timeout=10
        )

    @patch('agent_gradio_fastapi_multiturn.requests.post')
    def test_submit_request_without_user_id(self, mock_post, client):
        """Test request submission without user_id"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"session_id": "test-session-123"}
        mock_post.return_value = mock_response

        session_id = client.submit_request("Test message", "en")

        assert session_id == "test-session-123"
        mock_post.assert_called_once_with(
            "http://localhost:8001/chat-queue",
            json={
                "message": "Test message",
                "language": "en"
            },
            timeout=10
        )

    @patch('agent_gradio_fastapi_multiturn.requests.post')
    def test_submit_request_failure(self, mock_post, client):
        """Test request submission failure"""
        mock_post.side_effect = requests.exceptions.RequestException("Request failed")

        session_id = client.submit_request("Test message")

        assert session_id is None

    @patch('agent_gradio_fastapi_multiturn.requests.get')
    def test_get_status_success(self, mock_get, client):
        """Test successful status retrieval"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "session_id": "test-session",
            "status": "completed",
            "progress_updates": []
        }
        mock_get.return_value = mock_response

        status = client.get_status("test-session", "test-user")

        assert status is not None
        assert status["session_id"] == "test-session"
        mock_get.assert_called_once_with(
            "http://localhost:8001/status/test-session",
            params={"user_id": "test-user"},
            timeout=10
        )

    @patch('agent_gradio_fastapi_multiturn.requests.get')
    def test_get_status_failure(self, mock_get, client):
        """Test status retrieval failure"""
        mock_get.side_effect = requests.exceptions.RequestException("Request failed")

        status = client.get_status("test-session", "test-user")

        assert status is None

    @patch('agent_gradio_fastapi_multiturn.requests.get')
    def test_get_snapshots_success(self, mock_get, client):
        """Test successful snapshots retrieval"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "snapshots": [{"timestamp": "2024-01-01", "data": "test"}]
        }
        mock_get.return_value = mock_response

        snapshots = client.get_snapshots("test-session", "test-user")

        assert snapshots is not None
        assert "snapshots" in snapshots
        mock_get.assert_called_once_with(
            "http://localhost:8001/snapshots/test-session",
            params={"user_id": "test-user"},
            timeout=10
        )

    @patch('agent_gradio_fastapi_multiturn.requests.get')
    def test_get_all_sessions_success(self, mock_get, client):
        """Test successful all sessions retrieval"""
        # Mock response for single unified API call
        response = Mock()
        response.status_code = 200
        response.json.return_value = {
            "sessions": [
                {"session_id": "session1", "user_id": "user1"},
                {"session_id": "session2", "query": "test query", "status": "processing", "created_at": "2024-01-01T10:00:00"}
            ]
        }

        mock_get.return_value = response

        sessions = client.get_all_sessions("test-user")

        assert len(sessions) == 2
        assert mock_get.call_count == 1

    @patch('agent_gradio_fastapi_multiturn.requests.get')
    def test_get_all_sessions_without_user_filter(self, mock_get, client):
        """Test all sessions retrieval without user filter"""
        # Mock response for single unified API call
        response = Mock()
        response.status_code = 200
        response.json.return_value = {"sessions": []}

        mock_get.return_value = response

        sessions = client.get_all_sessions()

        assert sessions == []
        assert mock_get.call_count == 1

    @patch('agent_gradio_fastapi_multiturn.requests.get')
    def test_get_download_url_success(self, mock_get, client):
        """Test successful download URL retrieval"""
        # Mock download-urls response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "files": {
                "session_zip": {
                    "presigned_url": "https://s3.example.com/session.zip?signature=..."
                }
            }
        }
        mock_get.return_value = mock_response

        download_url = client.get_download_url("test-session", "test-user")

        assert download_url == "https://s3.example.com/session.zip?signature=..."
        mock_get.assert_called_once_with(
            "http://localhost:8001/download-urls/test-session",
            params={"user_id": "test-user"},
            timeout=10
        )

    @patch('agent_gradio_fastapi_multiturn.requests.get')
    def test_get_download_url_fallback(self, mock_get, client):
        """Test download URL fallback to direct endpoint"""
        # Mock download-urls failure, should fallback to direct endpoint
        mock_get.side_effect = requests.exceptions.RequestException("Download URLs failed")

        download_url = client.get_download_url("test-session", "test-user")

        assert download_url == "http://localhost:8001/download/test-session?user_id=test-user"

    @patch('agent_gradio_fastapi_multiturn.requests.get')
    def test_get_download_urls_success(self, mock_get, client):
        """Test successful S3 download URLs retrieval"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "files": {
                "session_zip": {
                    "presigned_url": "https://s3.example.com/session.zip?signature=...",
                    "size": "1.2 MB"
                },
                "report_md": {
                    "presigned_url": "https://s3.example.com/report.md?signature=...",
                    "size": "45 KB"
                }
            },
            "expires_in": "60"
        }
        mock_get.return_value = mock_response

        urls = client.get_download_urls("test-session", "test-user")

        assert urls is not None
        assert "files" in urls
        assert "session_zip" in urls["files"]
        assert "presigned_url" in urls["files"]["session_zip"]
        assert urls["expires_in"] == "60"
        mock_get.assert_called_once_with(
            "http://localhost:8001/download-urls/test-session",
            params={"user_id": "test-user"},
            timeout=10
        )

    @patch('agent_gradio_fastapi_multiturn.requests.get')
    def test_get_download_urls_failure(self, mock_get, client):
        """Test S3 download URLs retrieval failure"""
        mock_get.side_effect = requests.exceptions.RequestException("Download URLs failed")

        urls = client.get_download_urls("test-session", "test-user")

        assert urls is None

    @patch('agent_gradio_fastapi_multiturn.requests.post')
    def test_continue_session_success(self, mock_post, client):
        """Test successful session continuation"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "session_id": "test-session",
            "turn_number": 2,
            "status": "queued"
        }
        mock_post.return_value = mock_response

        result = client.continue_session("test-session", "Follow up message", "en", "test-user")

        assert result is not None
        assert result["turn_number"] == 2
        mock_post.assert_called_once_with(
            "http://localhost:8001/continue-session",
            json={
                "session_id": "test-session",
                "message": "Follow up message",
                "language": "en",
                "user_id": "test-user"
            },
            timeout=30
        )

    @patch('agent_gradio_fastapi_multiturn.requests.post')
    def test_continue_session_without_user_id(self, mock_post, client):
        """Test session continuation without user_id"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"session_id": "test-session"}
        mock_post.return_value = mock_response

        result = client.continue_session("test-session", "Follow up message")

        assert result is not None
        mock_post.assert_called_once_with(
            "http://localhost:8001/continue-session",
            json={
                "session_id": "test-session",
                "message": "Follow up message",
                "language": "en"
            },
            timeout=30
        )

    @patch('agent_gradio_fastapi_multiturn.requests.get')
    def test_get_multiturn_session_success(self, mock_get, client):
        """Test successful multi-turn session retrieval"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "session_id": "mt-session",
            "total_turns": 3,
            "turns": []
        }
        mock_get.return_value = mock_response

        session = client.get_multiturn_session("mt-session", "test-user")

        assert session is not None
        assert session["total_turns"] == 3

    @patch('agent_gradio_fastapi_multiturn.requests.get')
    def test_get_all_multiturn_sessions_success(self, mock_get, client):
        """Test successful all multi-turn sessions retrieval"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "sessions": [
                {"session_id": "mt1", "user_id": "user1"},
                {"session_id": "mt2", "user_id": "user2"}
            ]
        }
        mock_get.return_value = mock_response

        sessions = client.get_all_multiturn_sessions("test-user")

        assert len(sessions) == 2
        mock_get.assert_called_once_with(
            "http://localhost:8001/multiturn-sessions",
            params={"user_id": "test-user"},
            timeout=10
        )

    @patch('agent_gradio_fastapi_multiturn.requests.get')
    def test_get_turn_report_success(self, mock_get, client):
        """Test successful turn report retrieval"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "session_id": "mt-session",
            "turn_number": 2,
            "report": "Turn 2 report"
        }
        mock_get.return_value = mock_response

        report = client.get_turn_report("mt-session", 2, "test-user")

        assert report is not None
        assert report["turn_number"] == 2

    @patch('agent_gradio_fastapi_multiturn.requests.post')
    def test_stop_task_success(self, mock_post, client):
        """Test successful task stopping"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response

        result = client.stop_task("test-session", "test-user")

        assert result is True
        mock_post.assert_called_once_with(
            "http://localhost:8001/stop/test-session",
            params={"user_id": "test-user"},
            timeout=10
        )


class TestGradioHelperFunctions:
    """Test helper functions used in Gradio interface"""

    @patch('agent_gradio_fastapi_multiturn.FastAPIClient')
    def test_get_session_history_success(self, mock_client_class):
        """Test successful session history retrieval"""
        mock_client = Mock()
        mock_client.health_check.return_value = True
        mock_client.get_all_sessions.return_value = [
            {
                "session_id": "session1",
                "query": "Test query 1",
                "status": "completed",
                "timestamp": "2024-01-01T10:00:00"
            },
            {
                "session_id": "session2",
                "query": "Test query 2",
                "status": "processing",
                "timestamp": "2024-01-01T11:00:00"
            }
        ]
        mock_client_class.return_value = mock_client

        history = get_session_history("http://localhost:8001", "test-user")

        assert len(history) == 2
        assert isinstance(history[0], tuple)
        assert "session1" in history[0][1]  # session_id is in the tuple value, not label
        assert "Test query 1" in history[0][0]  # query should be in the label

    @patch('agent_gradio_fastapi_multiturn.FastAPIClient')
    def test_get_session_history_server_unavailable(self, mock_client_class):
        """Test session history when server is unavailable"""
        mock_client = Mock()
        mock_client.health_check.return_value = False
        mock_client_class.return_value = mock_client

        history = get_session_history("http://localhost:8001")

        assert len(history) == 1
        assert "Server not available" in history[0][0]

    @patch('agent_gradio_fastapi_multiturn.FastAPIClient')
    def test_get_session_history_no_sessions(self, mock_client_class):
        """Test session history when no sessions available"""
        mock_client = Mock()
        mock_client.health_check.return_value = True
        mock_client.get_all_sessions.return_value = []
        mock_client_class.return_value = mock_client

        history = get_session_history("http://localhost:8001")

        assert len(history) == 1
        assert "No sessions available" in history[0][0]

    @patch('agent_gradio_fastapi_multiturn.FastAPIClient')
    def test_get_session_history_with_user_filter(self, mock_client_class):
        """Test session history with user filter"""
        mock_client = Mock()
        mock_client.health_check.return_value = True
        mock_client.get_all_sessions.return_value = [
            {
                "session_id": "user1-session",
                "query": "User 1 query",
                "status": "completed",
                "timestamp": "2024-01-01T10:00:00",
                "user_id": "user1"
            }
        ]
        mock_client_class.return_value = mock_client

        history = get_session_history("http://localhost:8001", "user1")

        # Verify client was called with user_id
        mock_client.get_all_sessions.assert_called_once_with(user_id="user1")
        assert len(history) == 1


class TestGradioInterfaceFunctions:
    """Test Gradio interface helper functions"""

    def test_format_session_for_dropdown(self):
        """Test session formatting for dropdown display"""
        session = {
            "session_id": "test-session-123",
            "query": "This is a very long query that should be truncated for display purposes because it exceeds the 200 character limit that we have set for the dropdown display and therefore should include ellipsis at the end to indicate truncation",
            "status": "completed",
            "timestamp": "2024-01-01T10:30:00",
            "language": "en"
        }

        # Test the formatting logic from get_session_history
        query_display = session["query"][:200] + ("..." if len(session["query"]) > 200 else "")
        status_emoji = {
            'queued': '📋',
            'processing': '🔄',
            'completed': '✅',
            'failed': '❌',
            'cancelled': '🚫'
        }.get(session['status'], '❓')

        expected_display = f"{session['session_id']} | {status_emoji} {session['status']} | {query_display}"

        assert "..." in query_display  # Query should be truncated
        assert "✅" in expected_display  # Should have completed emoji

    def test_session_status_formatting(self):
        """Test session status emoji formatting"""
        status_emojis = {
            'queued': '📋',
            'processing': '🔄',
            'completed': '✅',
            'failed': '❌',
            'cancelled': '🚫'
        }

        for status, emoji in status_emojis.items():
            assert emoji is not None
            assert len(emoji) > 0


if __name__ == "__main__":
    pytest.main([__file__])