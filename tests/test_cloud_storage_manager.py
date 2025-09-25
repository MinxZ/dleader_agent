"""
Tests for CloudStorageManager
"""
import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from datetime import datetime
import tempfile
import os
from pathlib import Path

from cloud_storage_manager import CloudStorageManager


class TestCloudStorageManager:
    """Test CloudStorageManager functionality"""

    @pytest.fixture
    def cloud_manager(self, mock_environment_vars):
        """Create CloudStorageManager instance for testing"""
        with patch('cloud_storage_manager.get_s3_client'), \
             patch('cloud_storage_manager.create_bucket_if_not_exists'):
            manager = CloudStorageManager()
            manager.s3_client = Mock()
            return manager

    @pytest.fixture
    def sample_session_files(self, temp_dir):
        """Create sample session files for testing"""
        session_path = Path(temp_dir) / "test_session"
        session_path.mkdir()

        # Create sample files
        (session_path / "report_20240101_120000.md").write_text("Test report")
        (session_path / "thinking_process_20240101_120000.txt").write_text("Test thinking")
        (session_path / "query_20240101_120000.txt").write_text("Test query")
        (session_path / "result_20240101_120000.json").write_text('{"result": "test"}')
        (session_path / "session_20240101_120000.zip").write_bytes(b"test zip content")
        (session_path / "snapshot_20240101_120000.json").write_text('{"snapshot": "test"}')

        return str(session_path)

    def test_cloud_manager_initialization(self, mock_environment_vars):
        """Test CloudStorageManager initialization"""
        with patch('cloud_storage_manager.get_s3_client') as mock_s3, \
             patch('cloud_storage_manager.create_bucket_if_not_exists') as mock_create_bucket:

            mock_s3.return_value = Mock()

            manager = CloudStorageManager()

            assert manager.aws_access_key == "test-access-key"
            assert manager.aws_secret_key == "test-secret-key"
            assert manager.bucket_name == "test-bucket"
            assert manager.database_name == "test_dleader_agent"

            mock_s3.assert_called_once()
            mock_create_bucket.assert_called_once()

    @pytest.mark.asyncio
    async def test_upload_session_to_cloud_success(self, cloud_manager, sample_session_files, sample_session_data):
        """Test successful session upload to cloud"""
        session_data = sample_session_data.copy()
        session_data["session_path"] = sample_session_files

        # Mock S3 upload
        cloud_manager.s3_client.upload_file = Mock()

        # Mock MongoDB operations
        with patch('cloud_storage_manager.upsert_wrapper') as mock_upsert:
            mock_upsert.return_value = {"statusCode": 200}

            result = await cloud_manager.upload_session_to_cloud("test-session", session_data)

            assert result["status"] == "success"
            assert result["session_id"] == "test-session"
            assert "s3_files" in result

            # Verify S3 uploads were called
            assert cloud_manager.s3_client.upload_file.call_count > 0

            # Verify MongoDB upsert was called
            mock_upsert.assert_called_once()

    @pytest.mark.asyncio
    async def test_upload_session_to_cloud_missing_path(self, cloud_manager, sample_session_data):
        """Test session upload with missing session path"""
        session_data = sample_session_data.copy()
        session_data["session_path"] = "/non/existent/path"

        result = await cloud_manager.upload_session_to_cloud("test-session", session_data)

        assert result["status"] == "error"
        assert "not found" in result["error"]

    @pytest.mark.asyncio
    async def test_upload_session_files_to_s3(self, cloud_manager, sample_session_files):
        """Test uploading session files to S3"""
        cloud_manager.s3_client.upload_file = Mock()

        s3_files = await cloud_manager._upload_session_files_to_s3("test-session", sample_session_files)

        # Verify file types are present
        expected_types = ["report_md", "thinking_process", "query_file", "result_json", "session_zip", "snapshots"]
        for file_type in expected_types:
            assert file_type in s3_files

        # Verify S3 keys format
        for file_type, file_info in s3_files.items():
            if file_type == "snapshots":
                assert isinstance(file_info, list)
                for snapshot in file_info:
                    assert snapshot["s3_key"].startswith("sessions/test-session/snapshots/")
            else:
                assert file_info["s3_key"].startswith(f"sessions/test-session/{file_type}/")

    def test_prepare_session_metadata(self, cloud_manager, sample_session_data):
        """Test preparing session metadata for MongoDB"""
        s3_files = {
            "report_md": {
                "filename": "report.md",
                "s3_key": "sessions/test/report_md/report.md",
                "file_size": 1024
            }
        }

        metadata = cloud_manager._prepare_session_metadata("test-session", sample_session_data, s3_files)

        assert metadata["_id"] == "test-session"
        assert metadata["session_id"] == "test-session"
        assert metadata["status"] == sample_session_data["status"]
        assert metadata["user_id"] == sample_session_data["user_id"]
        assert metadata["s3_files"] == s3_files
        assert "uploaded_to_cloud_at" in metadata
        assert "progress_summary" in metadata
        assert "result_summary" in metadata

    @pytest.mark.asyncio
    async def test_save_session_metadata_success(self, cloud_manager):
        """Test successful metadata save to MongoDB"""
        metadata = {
            "_id": "test-session",
            "session_id": "test-session",
            "status": "completed"
        }

        with patch('cloud_storage_manager.upsert_wrapper') as mock_upsert:
            mock_upsert.return_value = {"statusCode": 200}

            result = await cloud_manager._save_session_metadata(metadata)

            assert result == metadata
            mock_upsert.assert_called_once()

    @pytest.mark.asyncio
    async def test_save_session_metadata_failure(self, cloud_manager):
        """Test metadata save failure"""
        metadata = {"_id": "test-session"}

        with patch('cloud_storage_manager.upsert_wrapper') as mock_upsert:
            mock_upsert.return_value = {"statusCode": 500}

            with pytest.raises(Exception):
                await cloud_manager._save_session_metadata(metadata)

    @pytest.mark.asyncio
    async def test_cleanup_local_files(self, cloud_manager, temp_dir):
        """Test cleanup of local files"""
        # Create test directory with files
        test_session_path = os.path.join(temp_dir, "test_session")
        os.makedirs(test_session_path)
        test_file = os.path.join(test_session_path, "test.txt")
        with open(test_file, 'w') as f:
            f.write("test content")

        assert os.path.exists(test_session_path)

        await cloud_manager._cleanup_local_files(test_session_path)

        assert not os.path.exists(test_session_path)

    @pytest.mark.asyncio
    async def test_retrieve_session_from_cloud(self, cloud_manager):
        """Test retrieving session from cloud"""
        mock_session_doc = {
            "session_id": "cloud-session",
            "status": "completed",
            "user_id": "test-user"
        }

        with patch('cloud_storage_manager.get_mongodb_collection') as mock_get_collection:
            mock_collection = Mock()
            mock_collection.find_one.return_value = mock_session_doc
            mock_get_collection.return_value = mock_collection

            session = await cloud_manager.retrieve_session_from_cloud("cloud-session")

            assert session == mock_session_doc
            mock_collection.find_one.assert_called_once_with({"_id": "cloud-session"})

    @pytest.mark.asyncio
    async def test_retrieve_session_from_cloud_not_found(self, cloud_manager):
        """Test retrieving non-existent session from cloud"""
        with patch('cloud_storage_manager.get_mongodb_collection') as mock_get_collection:
            mock_collection = Mock()
            mock_collection.find_one.return_value = None
            mock_get_collection.return_value = mock_collection

            session = await cloud_manager.retrieve_session_from_cloud("non-existent")

            assert session is None

    @pytest.mark.asyncio
    async def test_list_cloud_sessions(self, cloud_manager):
        """Test listing cloud sessions"""
        mock_sessions = [
            {"session_id": "session1", "status": "completed", "user_id": "user1"},
            {"session_id": "session2", "status": "completed", "user_id": "user2"}
        ]

        with patch('cloud_storage_manager.get_mongodb_collection') as mock_get_collection:
            mock_collection = Mock()
            mock_collection.find.return_value.sort.return_value.limit.return_value = mock_sessions
            mock_get_collection.return_value = mock_collection

            sessions = await cloud_manager.list_cloud_sessions(limit=10)

            assert sessions == mock_sessions
            mock_collection.find.assert_called_once_with({})

    @pytest.mark.asyncio
    async def test_list_cloud_sessions_with_filters(self, cloud_manager):
        """Test listing cloud sessions with filters"""
        with patch('cloud_storage_manager.get_mongodb_collection') as mock_get_collection:
            mock_collection = Mock()
            mock_collection.find.return_value.sort.return_value.limit.return_value = []
            mock_get_collection.return_value = mock_collection

            await cloud_manager.list_cloud_sessions(
                limit=50,
                status_filter="completed",
                user_id="test-user"
            )

            # Verify query with filters
            expected_query = {"status": "completed", "user_id": "test-user"}
            mock_collection.find.assert_called_once_with(expected_query)

    def test_generate_presigned_url(self, cloud_manager):
        """Test generating presigned URL"""
        mock_url = "https://test-bucket.s3.amazonaws.com/test-key?signed-params"

        with patch('s3_mongodb.s3_utils.get_s3_link') as mock_get_link:
            mock_get_link.return_value = mock_url

            url = cloud_manager.generate_presigned_url("test-s3-key", 3600)

            assert url == mock_url
            mock_get_link.assert_called_once_with(
                cloud_manager.s3_client,
                cloud_manager.bucket_name,
                "test-s3-key",
                3600
            )

    @pytest.mark.asyncio
    async def test_get_session_download_urls(self, cloud_manager):
        """Test getting session download URLs"""
        mock_session_data = {
            "session_id": "test-session",
            "s3_files": {
                "report_md": {
                    "filename": "report.md",
                    "s3_key": "sessions/test/report_md/report.md"
                },
                "snapshots": [
                    {
                        "filename": "snapshot1.json",
                        "s3_key": "sessions/test/snapshots/snapshot1.json"
                    }
                ]
            }
        }

        with patch.object(cloud_manager, 'retrieve_session_from_cloud') as mock_retrieve, \
             patch.object(cloud_manager, 'generate_presigned_url') as mock_generate_url:

            mock_retrieve.return_value = mock_session_data
            mock_generate_url.return_value = "https://presigned-url.com"

            result = await cloud_manager.get_session_download_urls("test-session")

            assert result is not None
            assert result["session_id"] == "test-session"
            assert "download_urls" in result
            assert "report_md" in result["download_urls"]
            assert "snapshots" in result["download_urls"]

            # Verify URLs were generated
            assert mock_generate_url.call_count >= 2

    @pytest.mark.asyncio
    async def test_get_session_download_urls_not_found(self, cloud_manager):
        """Test getting download URLs for non-existent session"""
        with patch.object(cloud_manager, 'retrieve_session_from_cloud') as mock_retrieve:
            mock_retrieve.return_value = None

            result = await cloud_manager.get_session_download_urls("non-existent")

            assert result is None

    @pytest.mark.asyncio
    async def test_upload_multiturn_session(self, cloud_manager):
        """Test uploading multi-turn session"""
        multiturn_data = {
            "session_id": "mt-session",
            "created_at": datetime.now().isoformat(),
            "last_updated": datetime.now().isoformat(),
            "total_turns": 2,
            "language": "en",
            "user_id": "test-user",
            "session_status": "active",
            "first_query": "First question",
            "latest_query": "Latest question",
            "turns": [
                {
                    "turn_number": 1,
                    "query": "First question",
                    "response_content": "First response"
                }
            ]
        }

        with patch('cloud_storage_manager.upsert_wrapper') as mock_upsert:
            mock_upsert.return_value = {"statusCode": 200}

            result = await cloud_manager.upload_multiturn_session(multiturn_data)

            assert result["status"] == "success"
            assert result["session_id"] == "mt-session"

            # Verify upsert was called with correct collection
            call_args = mock_upsert.call_args[0][0]
            assert call_args["collection_name"] == "multiturn_sessions"

    @pytest.mark.asyncio
    async def test_upload_multiturn_session_failure(self, cloud_manager):
        """Test multi-turn session upload failure"""
        multiturn_data = {"session_id": "mt-session"}

        with patch('cloud_storage_manager.upsert_wrapper') as mock_upsert:
            mock_upsert.return_value = {"statusCode": 500}

            result = await cloud_manager.upload_multiturn_session(multiturn_data)

            assert result["status"] == "error"
            assert "MongoDB upsert failed" in result["error"]


class TestCloudStorageManagerErrorHandling:
    """Test error handling in CloudStorageManager"""

    @pytest.fixture
    def cloud_manager(self, mock_environment_vars):
        """Create CloudStorageManager for error testing"""
        with patch('cloud_storage_manager.get_s3_client'), \
             patch('cloud_storage_manager.create_bucket_if_not_exists'):
            manager = CloudStorageManager()
            manager.s3_client = Mock()
            return manager

    @pytest.fixture
    def sample_session_files(self, temp_dir):
        """Create sample session files for testing"""
        session_path = Path(temp_dir) / "test_session"
        session_path.mkdir()

        # Create sample files
        (session_path / "report_20240101_120000.md").write_text("Test report")
        (session_path / "thinking_process_20240101_120000.txt").write_text("Test thinking")
        (session_path / "query_20240101_120000.txt").write_text("Test query")
        (session_path / "result_20240101_120000.json").write_text('{"result": "test"}')
        (session_path / "session_20240101_120000.zip").write_bytes(b"test zip content")
        (session_path / "snapshot_20240101_120000.json").write_text('{"snapshot": "test"}')

        return str(session_path)

    @pytest.fixture
    def cloud_manager_no_init(self, mock_environment_vars):
        """Create CloudStorageManager without successful initialization"""
        with patch('cloud_storage_manager.get_s3_client') as mock_s3:
            mock_s3.side_effect = Exception("S3 connection failed")

            with pytest.raises(Exception):
                CloudStorageManager()

    @pytest.mark.asyncio
    async def test_upload_session_s3_failure(self, cloud_manager, sample_session_files, sample_session_data):
        """Test session upload with S3 failure"""
        session_data = sample_session_data.copy()
        session_data["session_path"] = sample_session_files

        # Mock S3 upload failure
        cloud_manager.s3_client.upload_file.side_effect = Exception("S3 upload failed")

        result = await cloud_manager.upload_session_to_cloud("test-session", session_data)

        assert result["status"] == "error"
        assert "S3 upload failed" in result["error"]

    @pytest.mark.asyncio
    async def test_retrieve_session_mongodb_failure(self, cloud_manager):
        """Test session retrieval with MongoDB failure"""
        with patch('cloud_storage_manager.get_mongodb_collection') as mock_get_collection:
            mock_get_collection.side_effect = Exception("MongoDB connection failed")

            session = await cloud_manager.retrieve_session_from_cloud("test-session")

            assert session is None

    @pytest.mark.asyncio
    async def test_list_sessions_mongodb_failure(self, cloud_manager):
        """Test session listing with MongoDB failure"""
        with patch('cloud_storage_manager.get_mongodb_collection') as mock_get_collection:
            mock_get_collection.side_effect = Exception("MongoDB connection failed")

            sessions = await cloud_manager.list_cloud_sessions()

            assert sessions == []


if __name__ == "__main__":
    pytest.main([__file__])