"""
Integration tests for dleader_agent system
"""
import pytest
import asyncio
import tempfile
import os
from unittest.mock import Mock, patch, AsyncMock
from datetime import datetime

from agent_fastapi_server_multiturn import QueueManager, UserRequest, Language
from unified_session_manager import UnifiedSessionManager
from cloud_storage_manager import CloudStorageManager


class TestIntegration:
    """Integration tests for the complete system"""

    @pytest.fixture
    def queue_manager(self):
        """Create QueueManager for integration testing"""
        return QueueManager()

    @pytest.fixture
    def cloud_manager(self, mock_environment_vars):
        """Create mocked CloudStorageManager"""
        with patch('cloud_storage_manager.get_s3_client'), \
             patch('cloud_storage_manager.create_bucket_if_not_exists'):
            manager = CloudStorageManager()
            manager.s3_client = Mock()
            return manager

    @pytest.fixture
    def unified_manager(self, queue_manager, cloud_manager):
        """Create UnifiedSessionManager with real components"""
        manager = UnifiedSessionManager(queue_manager)
        manager.cloud_manager = cloud_manager
        return manager

    @pytest.mark.asyncio
    async def test_complete_session_workflow(self, unified_manager, queue_manager, cloud_manager):
        """Test complete workflow from session creation to cloud upload"""
        # 1. Create a user request
        user_request = UserRequest(
            session_id="integration-test-session",
            message="Integration test message",
            language=Language.EN,
            user_id="integration-test-user"
        )

        # 2. Add to queue manager
        queue_manager.active_sessions[user_request.session_id] = user_request

        # 3. Test session retrieval from unified manager
        session = await unified_manager.get_session_by_id("integration-test-session")
        assert session is not None
        assert session["session_id"] == "integration-test-session"
        assert session["user_id"] == "integration-test-user"
        assert session["_storage_location"] == "active"

        # 4. Test session listing with user filter
        sessions = await unified_manager.get_all_sessions(user_id="integration-test-user")
        session_ids = [s["session_id"] for s in sessions]
        assert "integration-test-session" in session_ids

        # 5. Simulate session completion
        user_request.is_complete = True
        user_request.status = "completed"
        user_request.session_path = "/tmp/test-session"

        # 6. Test session status
        status = await unified_manager.get_session_status("integration-test-session")
        assert status["status"] == "completed"
        assert status["is_complete"] is True

    @pytest.mark.asyncio
    async def test_multiturn_session_workflow(self, unified_manager, queue_manager):
        """Test multi-turn session workflow"""
        # Use a unique session ID to avoid conflicts with existing sessions
        import uuid
        unique_session_id = f"mt-integration-test-{uuid.uuid4().hex[:8]}"

        # 1. Create multi-turn session
        session = queue_manager.create_or_get_multiturn_session(
            unique_session_id,
            Language.EN,
            "integration-user"
        )

        assert session.session_id == unique_session_id
        assert session.user_id == "integration-user"

        # 2. Add turns to session
        turn1 = queue_manager.add_turn_to_session(unique_session_id, "First question")
        assert turn1 == 1

        turn2 = queue_manager.add_turn_to_session(unique_session_id, "Second question")
        assert turn2 == 2

        # 3. Test session properties
        assert session.first_query == "First question"
        assert session.latest_query == "Second question"

        # 4. Test multiturn session listing
        mt_sessions = await unified_manager.get_multiturn_sessions(user_id="integration-user")
        session_ids = [s["session_id"] for s in mt_sessions]
        assert unique_session_id in session_ids

    @pytest.mark.asyncio
    async def test_cloud_storage_workflow(self, cloud_manager, sample_session_data, temp_dir):
        """Test cloud storage workflow"""
        # 1. Create test session directory with files
        session_path = os.path.join(temp_dir, "test_session")
        os.makedirs(session_path)

        # Create test files
        test_files = {
            "report_test.md": "# Test Report\nThis is a test report.",
            "thinking_process_test.txt": "Test thinking process",
            "result_test.json": '{"result": "test"}',
            "session_test.zip": "dummy zip content"
        }

        for filename, content in test_files.items():
            with open(os.path.join(session_path, filename), 'w') as f:
                f.write(content)

        # 2. Prepare session data
        session_data = sample_session_data.copy()
        session_data["session_path"] = session_path

        # 3. Mock cloud operations
        cloud_manager.s3_client.upload_file = Mock()

        with patch('cloud_storage_manager.upsert_wrapper') as mock_upsert:
            mock_upsert.return_value = {"statusCode": 200}

            # 4. Test upload
            result = await cloud_manager.upload_session_to_cloud("cloud-test-session", session_data)

            assert result["status"] == "success"
            assert result["session_id"] == "cloud-test-session"
            assert "s3_files" in result

        # 5. Test retrieval
        with patch('cloud_storage_manager.get_mongodb_collection') as mock_get_collection:
            mock_collection = Mock()
            mock_collection.find_one.return_value = {
                "session_id": "cloud-test-session",
                "status": "completed",
                "user_id": "test-user"
            }
            mock_get_collection.return_value = mock_collection

            retrieved_session = await cloud_manager.retrieve_session_from_cloud("cloud-test-session")
            assert retrieved_session is not None
            assert retrieved_session["session_id"] == "cloud-test-session"

    @pytest.mark.asyncio
    async def test_user_isolation(self, unified_manager, queue_manager, cloud_manager):
        """Test that user isolation works correctly"""
        # 1. Create sessions for different users
        user1_request = UserRequest(
            session_id="user1-session",
            message="User 1 message",
            language=Language.EN,
            user_id="user1"
        )

        user2_request = UserRequest(
            session_id="user2-session",
            message="User 2 message",
            language=Language.EN,
            user_id="user2"
        )

        queue_manager.active_sessions["user1-session"] = user1_request
        queue_manager.active_sessions["user2-session"] = user2_request

        # 2. Mock cloud sessions for different users
        async def mock_list_cloud_sessions(limit=None, user_id=None, **kwargs):
            all_cloud_sessions = [
                {"session_id": "cloud-user1", "user_id": "user1"},
                {"session_id": "cloud-user2", "user_id": "user2"}
            ]
            if user_id:
                return [s for s in all_cloud_sessions if s.get("user_id") == user_id]
            return all_cloud_sessions

        cloud_manager.list_cloud_sessions = mock_list_cloud_sessions

        # 3. Test user1 sessions
        user1_sessions = await unified_manager.get_all_sessions(user_id="user1", include_cloud=True)
        user1_session_ids = [s["session_id"] for s in user1_sessions]

        assert "user1-session" in user1_session_ids
        assert "cloud-user1" in user1_session_ids
        assert "user2-session" not in user1_session_ids
        assert "cloud-user2" not in user1_session_ids

        # 4. Test user2 sessions
        user2_sessions = await unified_manager.get_all_sessions(user_id="user2", include_cloud=True)
        user2_session_ids = [s["session_id"] for s in user2_sessions]

        assert "user2-session" in user2_session_ids
        assert "cloud-user2" in user2_session_ids
        assert "user1-session" not in user2_session_ids
        assert "cloud-user1" not in user2_session_ids

    @pytest.mark.asyncio
    async def test_error_handling_integration(self, unified_manager, queue_manager, cloud_manager):
        """Test error handling across the system"""
        # 1. Test non-existent session
        session = await unified_manager.get_session_by_id("non-existent-session")
        assert session is None

        status = await unified_manager.get_session_status("non-existent-session")
        assert status is None

        # 2. Test cloud manager errors
        cloud_manager.list_cloud_sessions = AsyncMock(side_effect=Exception("Cloud error"))

        # Should handle error gracefully
        sessions = await unified_manager.get_all_sessions(include_cloud=True)
        # Should still return local sessions even if cloud fails
        assert isinstance(sessions, list)

        # 3. Test multiturn session errors
        with patch('s3_mongodb.func_mongodb.get_mongodb_collection') as mock_get_collection:
            mock_get_collection.side_effect = Exception("MongoDB error")

            # Should handle error gracefully
            mt_sessions = await unified_manager.get_multiturn_sessions(include_cloud=True)
            assert isinstance(mt_sessions, list)

    @pytest.mark.asyncio
    async def test_concurrent_operations(self, unified_manager, queue_manager):
        """Test concurrent operations on the system"""
        # 1. Create multiple sessions concurrently
        sessions = []
        for i in range(5):
            user_request = UserRequest(
                session_id=f"concurrent-session-{i}",
                message=f"Concurrent message {i}",
                language=Language.EN,
                user_id=f"user{i % 2}"  # Alternate between user0 and user1
            )
            queue_manager.active_sessions[user_request.session_id] = user_request
            sessions.append(user_request)

        # 2. Test concurrent retrieval
        tasks = []
        for session in sessions:
            task = unified_manager.get_session_by_id(session.session_id)
            tasks.append(task)

        results = await asyncio.gather(*tasks)

        # 3. Verify all sessions were retrieved correctly
        assert len(results) == 5
        for i, result in enumerate(results):
            assert result is not None
            assert result["session_id"] == f"concurrent-session-{i}"

        # 4. Test concurrent user filtering
        user0_task = unified_manager.get_all_sessions(user_id="user0")
        user1_task = unified_manager.get_all_sessions(user_id="user1")

        user0_sessions, user1_sessions = await asyncio.gather(user0_task, user1_task)

        # Verify user isolation
        for session in user0_sessions:
            assert session["user_id"] == "user0"

        for session in user1_sessions:
            assert session["user_id"] == "user1"


class TestSystemPerformance:
    """Performance tests for the system"""

    @pytest.fixture
    def queue_manager(self):
        """Create QueueManager for performance testing"""
        return QueueManager()

    @pytest.fixture
    def cloud_manager(self, mock_environment_vars):
        """Create mocked CloudStorageManager for performance testing"""
        # Use a completely mocked cloud manager to avoid network calls
        mock_manager = Mock()
        mock_manager.list_cloud_sessions = AsyncMock(return_value=[])
        return mock_manager

    @pytest.fixture
    def unified_manager(self, queue_manager, cloud_manager):
        """Create UnifiedSessionManager with mocked cloud manager"""
        manager = UnifiedSessionManager(queue_manager)
        manager.cloud_manager = cloud_manager
        return manager

    @pytest.mark.asyncio
    async def test_large_session_list_performance(self, unified_manager, queue_manager):
        """Test performance with large number of sessions"""
        # Clear any existing sessions to ensure clean test
        queue_manager.active_sessions.clear()

        # Create many sessions
        for i in range(100):
            user_request = UserRequest(
                session_id=f"perf-session-{i}",
                message=f"Performance test message {i}",
                language=Language.EN,
                user_id=f"perf-user-{i % 10}"  # 10 different users
            )
            queue_manager.active_sessions[user_request.session_id] = user_request

        # Test retrieval performance
        start_time = datetime.now()
        sessions = await unified_manager.get_all_sessions()
        end_time = datetime.now()

        retrieval_time = (end_time - start_time).total_seconds()

        # Should complete within reasonable time (adjust threshold as needed)
        assert retrieval_time < 5.0  # 5 seconds
        assert len(sessions) >= 100  # At least 100 sessions (may have pre-existing sessions)

        # Test user filtering performance
        start_time = datetime.now()
        user_sessions = await unified_manager.get_all_sessions(user_id="perf-user-0")
        end_time = datetime.now()

        filter_time = (end_time - start_time).total_seconds()

        assert filter_time < 2.0  # 2 seconds
        assert len(user_sessions) >= 10  # At least 10 sessions for this user

    @pytest.mark.asyncio
    async def test_memory_usage(self, unified_manager, queue_manager):
        """Test memory usage doesn't grow excessively"""
        import tracemalloc

        # Clear any existing sessions to ensure clean test
        queue_manager.active_sessions.clear()

        tracemalloc.start()

        # Create and process many sessions
        for i in range(50):
            user_request = UserRequest(
                session_id=f"memory-test-{i}",
                message=f"Memory test {i}",
                language=Language.EN,
                user_id="memory-user"
            )
            queue_manager.active_sessions[user_request.session_id] = user_request

            # Retrieve session
            await unified_manager.get_session_by_id(user_request.session_id)

        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        # Memory usage should be reasonable (adjust threshold as needed)
        peak_mb = peak / 1024 / 1024
        assert peak_mb < 100  # Less than 100MB peak memory usage

        print(f"Peak memory usage: {peak_mb:.2f} MB")


if __name__ == "__main__":
    pytest.main([__file__])