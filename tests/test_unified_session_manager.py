"""
Tests for UnifiedSessionManager
"""
import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime

from unified_session_manager import UnifiedSessionManager, get_unified_session_manager
from agent_fastapi_server_multiturn import UserRequest, Language, MultiTurnSession


class TestUnifiedSessionManager:
    """Test UnifiedSessionManager functionality"""

    @pytest.fixture
    def unified_manager(self, mock_queue_manager, mock_cloud_manager):
        """Create UnifiedSessionManager instance for testing"""
        manager = UnifiedSessionManager(mock_queue_manager)
        manager.cloud_manager = mock_cloud_manager
        return manager

    @pytest.mark.asyncio
    async def test_get_all_sessions_no_filter(self, unified_manager, mock_queue_manager, mock_cloud_manager):
        """Test getting all sessions without user filter"""
        # Mock active sessions
        mock_user_request = Mock()
        mock_user_request.session_id = "active-session"
        mock_user_request.message = "Active message"
        mock_user_request.language = Language.EN
        mock_user_request.created_at = datetime.now()
        mock_user_request.is_complete = False
        mock_user_request.is_cancelled = False
        mock_user_request.error = None
        mock_user_request.user_id = "user1"

        mock_queue_manager.active_sessions = {"active-session": mock_user_request}
        mock_queue_manager.get_all_stored_sessions.return_value = []

        # Mock cloud sessions
        cloud_sessions = [
            {
                "session_id": "cloud-session",
                "status": "completed",
                "user_id": "user2",
                "created_at": datetime.now().isoformat()
            }
        ]
        mock_cloud_manager.list_cloud_sessions.return_value = cloud_sessions

        sessions = await unified_manager.get_all_sessions(include_cloud=True)

        assert len(sessions) == 2
        session_ids = [s["session_id"] for s in sessions]
        assert "active-session" in session_ids
        assert "cloud-session" in session_ids

    @pytest.mark.asyncio
    async def test_get_all_sessions_with_user_filter(self, unified_manager, mock_queue_manager, mock_cloud_manager):
        """Test getting sessions with user_id filter"""
        # Mock active sessions
        mock_user_request1 = Mock()
        mock_user_request1.session_id = "user1-session"
        mock_user_request1.message = "User1 message"
        mock_user_request1.language = Language.EN
        mock_user_request1.created_at = datetime.now()
        mock_user_request1.is_complete = False
        mock_user_request1.is_cancelled = False
        mock_user_request1.error = None
        mock_user_request1.user_id = "user1"

        mock_user_request2 = Mock()
        mock_user_request2.session_id = "user2-session"
        mock_user_request2.message = "User2 message"
        mock_user_request2.language = Language.EN
        mock_user_request2.created_at = datetime.now()
        mock_user_request2.is_complete = False
        mock_user_request2.is_cancelled = False
        mock_user_request2.error = None
        mock_user_request2.user_id = "user2"

        mock_queue_manager.active_sessions = {
            "user1-session": mock_user_request1,
            "user2-session": mock_user_request2
        }
        mock_queue_manager.get_all_stored_sessions.return_value = []

        # Mock cloud sessions - set up a side_effect to simulate filtering
        cloud_sessions_all = [
            {
                "session_id": "cloud-user1",
                "status": "completed",
                "user_id": "user1",
                "created_at": datetime.now().isoformat()
            },
            {
                "session_id": "cloud-user2",
                "status": "completed",
                "user_id": "user2",
                "created_at": datetime.now().isoformat()
            }
        ]

        def mock_list_cloud_sessions(limit=1000, user_id=None):
            if user_id:
                return [s for s in cloud_sessions_all if s.get("user_id") == user_id]
            return cloud_sessions_all

        mock_cloud_manager.list_cloud_sessions.side_effect = mock_list_cloud_sessions

        # Test filtering for user1
        sessions = await unified_manager.get_all_sessions(include_cloud=True, user_id="user1")

        assert len(sessions) == 2
        for session in sessions:
            assert session["user_id"] == "user1"

        # Verify cloud manager was called with user_id filter
        mock_cloud_manager.list_cloud_sessions.assert_called_with(limit=1000, user_id="user1")

    @pytest.mark.asyncio
    async def test_get_session_by_id_active(self, unified_manager, mock_queue_manager):
        """Test getting active session by ID"""
        mock_user_request = Mock()
        mock_user_request.session_id = "active-session"
        mock_user_request.message = "Active message"
        mock_user_request.language = Language.EN
        mock_user_request.created_at = datetime.now()
        mock_user_request.is_complete = False
        mock_user_request.user_id = "test-user"

        mock_queue_manager.active_sessions = {"active-session": mock_user_request}

        session = await unified_manager.get_session_by_id("active-session")

        assert session is not None
        assert session["session_id"] == "active-session"
        assert session["_storage_location"] == "active"

    @pytest.mark.asyncio
    async def test_get_session_by_id_local_storage(self, unified_manager, mock_queue_manager):
        """Test getting session from local storage"""
        mock_queue_manager.active_sessions = {}
        mock_session_data = {
            "session_id": "local-session",
            "status": "completed",
            "user_id": "test-user"
        }
        mock_queue_manager._load_session_from_storage.return_value = mock_session_data

        session = await unified_manager.get_session_by_id("local-session")

        assert session is not None
        assert session["session_id"] == "local-session"
        assert session["_storage_location"] == "local"

    @pytest.mark.asyncio
    async def test_get_session_by_id_cloud(self, unified_manager, mock_queue_manager, mock_cloud_manager):
        """Test getting session from cloud storage"""
        mock_queue_manager.active_sessions = {}
        mock_queue_manager._load_session_from_storage.return_value = None

        cloud_session_data = {
            "session_id": "cloud-session",
            "status": "completed",
            "user_id": "test-user",
            "created_at": datetime.now().isoformat()
        }
        mock_cloud_manager.retrieve_session_from_cloud.return_value = cloud_session_data

        session = await unified_manager.get_session_by_id("cloud-session")

        assert session is not None
        assert session["session_id"] == "cloud-session"
        assert session["_storage_location"] == "cloud"

    @pytest.mark.asyncio
    async def test_get_session_by_id_not_found(self, unified_manager, mock_queue_manager, mock_cloud_manager):
        """Test getting non-existent session"""
        mock_queue_manager.active_sessions = {}
        mock_queue_manager._load_session_from_storage.return_value = None
        mock_cloud_manager.retrieve_session_from_cloud.return_value = None

        session = await unified_manager.get_session_by_id("non-existent")

        assert session is None

    @pytest.mark.asyncio
    async def test_get_session_status_active(self, unified_manager, mock_queue_manager):
        """Test getting status for active session"""
        mock_progress = {
            "session_id": "active-session",
            "status": "processing",
            "progress_updates": []
        }
        mock_queue_manager.get_session_progress.return_value = mock_progress
        mock_queue_manager.active_sessions = {"active-session": Mock()}

        status = await unified_manager.get_session_status("active-session")

        assert status == mock_progress

    @pytest.mark.asyncio
    async def test_get_session_status_completed(self, unified_manager, mock_queue_manager):
        """Test getting status for completed session"""
        mock_queue_manager.active_sessions = {}

        # Mock the get_session_by_id method
        with patch.object(unified_manager, 'get_session_by_id') as mock_get_session:
            mock_session_data = {
                "session_id": "completed-session",
                "status": "completed",
                "is_complete": True,
                "created_at": datetime.now().isoformat(),
                "_storage_location": "local"
            }
            mock_get_session.return_value = mock_session_data

            status = await unified_manager.get_session_status("completed-session")

            assert status["session_id"] == "completed-session"
            assert status["status"] == "completed"
            assert status["is_complete"] is True
            assert status["storage_location"] == "local"

    @pytest.mark.asyncio
    async def test_get_session_files_local(self, unified_manager):
        """Test getting session files for local session"""
        with patch.object(unified_manager, 'get_session_by_id') as mock_get_session:
            mock_session_data = {
                "session_id": "local-session",
                "_storage_location": "local"
            }
            mock_get_session.return_value = mock_session_data

            with patch('os.path.exists', return_value=True), \
                 patch('agent_fastapi_server_multiturn.create_session_zip', return_value="/tmp/test.zip"):

                files_info = await unified_manager.get_session_files("local-session")

                assert files_info["session_id"] == "local-session"
                assert files_info["storage_type"] == "local"
                assert files_info["download_method"] == "local_zip"

    @pytest.mark.asyncio
    async def test_get_session_files_cloud(self, unified_manager):
        """Test getting session files for cloud session"""
        with patch.object(unified_manager, 'get_session_by_id') as mock_get_session:
            mock_session_data = {
                "session_id": "cloud-session",
                "_storage_location": "cloud",
                "s3_files": {
                    "report_md": {
                        "filename": "report.md",
                        "s3_key": "sessions/cloud-session/report_md/report.md"
                    }
                }
            }
            mock_get_session.return_value = mock_session_data

            files_info = await unified_manager.get_session_files("cloud-session")

            assert files_info["session_id"] == "cloud-session"
            assert files_info["storage_type"] == "cloud"
            assert files_info["download_method"] == "s3_keys"
            assert "s3_files" in files_info

    @pytest.mark.asyncio
    async def test_get_multiturn_sessions(self, unified_manager, mock_queue_manager):
        """Test getting multi-turn sessions"""
        # Mock local multiturn sessions
        mock_multiturn_session = Mock()
        mock_multiturn_session.session_id = "mt-session"
        mock_multiturn_session.created_at = datetime.now().isoformat()
        mock_multiturn_session.last_updated = datetime.now().isoformat()
        mock_multiturn_session.total_turns = 2
        mock_multiturn_session.language = Language.EN
        mock_multiturn_session.session_status = "active"
        mock_multiturn_session.first_query = "First question"
        mock_multiturn_session.latest_query = "Latest question"
        mock_multiturn_session.user_id = "test-user"

        mock_queue_manager.multiturn_sessions = {"mt-session": mock_multiturn_session}

        # Mock cloud multiturn sessions
        with patch('s3_mongodb.func_mongodb.get_mongodb_collection') as mock_get_collection:
            mock_collection = Mock()
            mock_collection.find.return_value.sort.return_value.limit.return_value = [
                {
                    "session_id": "cloud-mt-session",
                    "created_at": datetime.now().isoformat(),
                    "total_turns": 3,
                    "user_id": "test-user"
                }
            ]
            mock_get_collection.return_value = mock_collection

            sessions = await unified_manager.get_multiturn_sessions(include_cloud=True)

            assert len(sessions) == 2
            session_ids = [s["session_id"] for s in sessions]
            assert "mt-session" in session_ids
            assert "cloud-mt-session" in session_ids

    @pytest.mark.asyncio
    async def test_get_multiturn_sessions_with_user_filter(self, unified_manager, mock_queue_manager):
        """Test getting multi-turn sessions with user filter"""
        # Mock local sessions with different users
        mock_session1 = Mock()
        mock_session1.session_id = "mt-user1"
        mock_session1.created_at = datetime.now().isoformat()
        mock_session1.last_updated = datetime.now().isoformat()
        mock_session1.total_turns = 1
        mock_session1.language = Language.EN
        mock_session1.session_status = "active"
        mock_session1.first_query = "Question 1"
        mock_session1.latest_query = "Question 1"
        mock_session1.user_id = "user1"

        mock_session2 = Mock()
        mock_session2.session_id = "mt-user2"
        mock_session2.created_at = datetime.now().isoformat()
        mock_session2.last_updated = datetime.now().isoformat()
        mock_session2.total_turns = 1
        mock_session2.language = Language.EN
        mock_session2.session_status = "active"
        mock_session2.first_query = "Question 2"
        mock_session2.latest_query = "Question 2"
        mock_session2.user_id = "user2"

        mock_queue_manager.multiturn_sessions = {
            "mt-user1": mock_session1,
            "mt-user2": mock_session2
        }

        # Mock cloud sessions
        with patch('s3_mongodb.func_mongodb.get_mongodb_collection') as mock_get_collection:
            mock_collection = Mock()
            mock_collection.find.return_value.sort.return_value.limit.return_value = [
                {
                    "session_id": "cloud-mt-user1",
                    "created_at": datetime.now().isoformat(),
                    "user_id": "user1"
                }
            ]
            mock_get_collection.return_value = mock_collection

            sessions = await unified_manager.get_multiturn_sessions(include_cloud=True, user_id="user1")

            # Should only return sessions for user1
            assert len(sessions) == 2
            for session in sessions:
                assert session["user_id"] == "user1"

    def test_convert_active_session_to_unified(self, unified_manager):
        """Test converting active session to unified format"""
        mock_user_request = Mock()
        mock_user_request.session_id = "test-session"
        mock_user_request.is_complete = True
        mock_user_request.error = None
        mock_user_request.is_cancelled = False
        mock_user_request.message = "Test message"
        mock_user_request.language = Language.EN
        mock_user_request.created_at = datetime.now()
        mock_user_request.user_id = "test-user"
        mock_user_request.all_progress_updates = []
        mock_user_request.json_result = {}
        mock_user_request.periodic_snapshots = []

        unified_session = unified_manager._convert_active_session_to_unified(mock_user_request)

        assert unified_session["session_id"] == "test-session"
        assert unified_session["status"] == "completed"
        assert unified_session["query"] == "Test message"
        assert unified_session["user_id"] == "test-user"
        assert unified_session["_storage_location"] == "active"

    def test_convert_cloud_to_unified_format(self, unified_manager):
        """Test converting cloud session to unified format"""
        cloud_session = {
            "session_id": "cloud-session",
            "status": "completed",
            "is_complete": True,
            "query": "Cloud query",
            "language": "en",
            "created_at": datetime.now().isoformat(),
            "user_id": "test-user",
            "s3_files": {}
        }

        unified_session = unified_manager._convert_cloud_to_unified_format(cloud_session)

        assert unified_session["session_id"] == "cloud-session"
        assert unified_session["status"] == "completed"
        assert unified_session["query"] == "Cloud query"
        assert unified_session["user_id"] == "test-user"
        assert unified_session["_storage_location"] == "cloud"


class TestGetUnifiedSessionManager:
    """Test the get_unified_session_manager function"""

    def test_get_unified_session_manager_creates_instance(self, mock_queue_manager):
        """Test that get_unified_session_manager creates instance"""
        # Reset global variable
        import unified_session_manager
        unified_session_manager.unified_session_manager = None

        manager = get_unified_session_manager(mock_queue_manager)

        assert manager is not None
        assert isinstance(manager, UnifiedSessionManager)

    def test_get_unified_session_manager_returns_same_instance(self, mock_queue_manager):
        """Test that get_unified_session_manager returns same instance"""
        # Reset global variable
        import unified_session_manager
        unified_session_manager.unified_session_manager = None

        manager1 = get_unified_session_manager(mock_queue_manager)
        manager2 = get_unified_session_manager(mock_queue_manager)

        assert manager1 is manager2


if __name__ == "__main__":
    pytest.main([__file__])