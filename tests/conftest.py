"""
Test configuration and fixtures for dleader_agent tests
"""
import asyncio
import os
import tempfile
import pytest
from unittest.mock import Mock, AsyncMock
from datetime import datetime
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent_fastapi_server_multiturn import UserRequest, QueueManager, Language, MultiTurnSession
from unified_session_manager import UnifiedSessionManager
from cloud_storage_manager import CloudStorageManager


@pytest.fixture
def temp_dir():
    """Create a temporary directory for test files"""
    with tempfile.TemporaryDirectory() as temp_dir:
        yield temp_dir


@pytest.fixture
def mock_user_request():
    """Create a mock UserRequest for testing"""
    user_request = UserRequest(
        session_id="test-session-123",
        message="Test message",
        language=Language.EN,
        user_id="test-user"
    )
    user_request.created_at = datetime.now()
    user_request.status = "completed"
    user_request.is_complete = True
    user_request.is_cancelled = False
    user_request.error = None
    user_request.result = "Test result"
    user_request.json_result = {"test": "data"}
    user_request.session_path = "/tmp/test-session"
    user_request.all_progress_updates = []
    user_request.periodic_snapshots = []
    return user_request


@pytest.fixture
def mock_queue_manager():
    """Create a mock QueueManager for testing"""
    queue_manager = Mock(spec=QueueManager)
    queue_manager.active_sessions = {}
    queue_manager.multiturn_sessions = {}
    queue_manager._load_session_from_storage = Mock(return_value=None)
    queue_manager.get_all_stored_sessions = Mock(return_value=[])
    return queue_manager


@pytest.fixture
def mock_cloud_manager():
    """Create a mock CloudStorageManager for testing"""
    cloud_manager = Mock(spec=CloudStorageManager)
    cloud_manager.upload_session_to_cloud = AsyncMock()
    cloud_manager.retrieve_session_from_cloud = AsyncMock(return_value=None)
    cloud_manager.list_cloud_sessions = AsyncMock(return_value=[])
    cloud_manager.upload_multiturn_session = AsyncMock()
    cloud_manager.get_session_download_urls = AsyncMock(return_value=None)
    return cloud_manager


@pytest.fixture
def mock_multiturn_session():
    """Create a mock MultiTurnSession for testing"""
    from agent_fastapi_server_multiturn import ConversationTurn

    turn1 = ConversationTurn(
        turn_number=1,
        query="First question",
        response_content="First response",
        final_report="First report",
        files=None,
        timestamp=datetime.now().isoformat(),
        status="completed"
    )

    session = MultiTurnSession(
        session_id="multiturn-test-123",
        created_at=datetime.now().isoformat(),
        last_updated=datetime.now().isoformat(),
        language=Language.EN,
        user_id="test-user",
        total_turns=1,
        current_turn=1,
        turns=[turn1],
        accumulated_context="Test context",
        session_status="active"
    )
    return session


@pytest.fixture
def sample_session_data():
    """Sample session data for testing"""
    return {
        "session_id": "test-session-123",
        "status": "completed",
        "is_complete": True,
        "is_cancelled": False,
        "error": None,
        "created_at": datetime.now().isoformat(),
        "query": "Test query",
        "language": "en",
        "user_id": "test-user",
        "session_path": "/tmp/test-session",
        "all_progress_updates": [],
        "periodic_snapshots": [],
        "result": "Test result",
        "json_result": {"test": "data"}
    }


@pytest.fixture
def sample_cloud_session():
    """Sample cloud session data for testing"""
    return {
        "_id": "cloud-session-123",
        "session_id": "cloud-session-123",
        "status": "completed",
        "is_complete": True,
        "is_cancelled": False,
        "error": None,
        "created_at": datetime.now().isoformat(),
        "query": "Cloud test query",
        "language": "en",
        "user_id": "test-user",
        "uploaded_to_cloud_at": datetime.now().isoformat(),
        "s3_files": {
            "report_md": {
                "filename": "report_test.md",
                "s3_key": "sessions/cloud-session-123/report_md/report_test.md",
                "file_size": 1024,
                "uploaded_at": datetime.now().isoformat()
            }
        },
        "progress_summary": {
            "total_updates": 5,
            "snapshot_count": 2,
            "final_status": "completed"
        },
        "result_summary": {
            "has_result": True,
            "json_result_keys": ["test"]
        }
    }


@pytest.fixture
def mock_environment_vars(monkeypatch):
    """Mock environment variables for testing"""
    monkeypatch.setenv("AWS_ACCESS_KEY_ID_SELF", "test-access-key")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY_SELF", "test-secret-key")
    monkeypatch.setenv("AWS_REGION_SELF", "us-east-1")
    monkeypatch.setenv("SESSION_STORAGE_BUCKET", "test-bucket")
    monkeypatch.setenv("MONGODB_URI", "mongodb://test:27017")
    monkeypatch.setenv("SESSION_DB_NAME", "test_dleader_agent")


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()