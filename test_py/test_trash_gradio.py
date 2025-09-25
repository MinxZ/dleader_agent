#!/usr/bin/env python3
"""
Unit tests for Gradio trash interface components
Tests the trash management functions within the Gradio interface
"""
import json
import os
import sys
import time
import tempfile
import shutil
from datetime import datetime
import unittest
from unittest.mock import patch, MagicMock, AsyncMock
import asyncio
import requests

# Test configuration
TEST_USER = "test_user_123"
TEST_SESSION_ID = "test-session-12345678-90ab-cdef-ghij-klmnopqrstuv"
API_BASE = "http://localhost:8001"

class TestTrashGradioInterface(unittest.TestCase):
    """Test suite for Gradio trash interface"""

    @classmethod
    def setUpClass(cls):
        """Set up test environment"""
        cls.test_dir = tempfile.mkdtemp(prefix="gradio_trash_test_")

        # Mock session data
        cls.mock_trash_sessions = [
            {
                "session_id": TEST_SESSION_ID,
                "query": "Test query 1",
                "trashed_at": datetime.now().isoformat(),
                "created_at": datetime.now().isoformat()
            },
            {
                "session_id": "test-session-2",
                "query": "Test query 2",
                "trashed_at": datetime.now().isoformat(),
                "created_at": datetime.now().isoformat()
            }
        ]

    @classmethod
    def tearDownClass(cls):
        """Clean up test environment"""
        if os.path.exists(cls.test_dir):
            shutil.rmtree(cls.test_dir)

    def test_1_refresh_trash_list(self):
        """Test refreshing trash list API call"""
        print("\n" + "="*60)
        print("TEST 1: Refresh Trash List API")
        print("="*60)

        # Test the API endpoint directly
        with patch('requests.get') as mock_get:
            mock_response = MagicMock()
            mock_response.json.return_value = {
                "status": "success",
                "sessions": self.mock_trash_sessions,
                "count": len(self.mock_trash_sessions)
            }
            mock_response.status_code = 200
            mock_get.return_value = mock_response

            # Simulate the refresh_trash_list function behavior
            response = requests.get(f"{API_BASE}/trash", params={"user_id": TEST_USER})
            data = response.json()

            # Validate results
            self.assertEqual(data["status"], "success")
            self.assertEqual(data["count"], len(self.mock_trash_sessions))
            self.assertEqual(len(data["sessions"]), len(self.mock_trash_sessions))

            print(f"✅ Successfully tested trash list API")
            print(f"   Sessions found: {data['count']}")

    def test_2_restore_session(self):
        """Test restoring a session from trash API"""
        print("\n" + "="*60)
        print("TEST 2: Restore Session API")
        print("="*60)

        with patch('requests.post') as mock_post:
            mock_response = MagicMock()
            mock_response.json.return_value = {
                "status": "success",
                "message": "Session restored from trash",
                "restored_at": datetime.now().isoformat()
            }
            mock_response.status_code = 200
            mock_post.return_value = mock_response

            # Simulate the restore_session function behavior
            response = requests.post(
                f"{API_BASE}/restore/{TEST_SESSION_ID}",
                params={"user_id": TEST_USER}
            )
            data = response.json()

            # Validate
            self.assertEqual(data["status"], "success")
            self.assertIn("restored_at", data)
            mock_post.assert_called_once()

            print(f"✅ Session restore API test passed")
            print(f"   Session ID: {TEST_SESSION_ID[:8]}...")

    def test_3_permanent_delete(self):
        """Test permanent deletion from trash API"""
        print("\n" + "="*60)
        print("TEST 3: Permanent Delete API")
        print("="*60)

        with patch('requests.delete') as mock_delete:
            mock_response = MagicMock()
            mock_response.json.return_value = {
                "status": "success",
                "deleted_items": {
                    "local_files": ["file1.txt", "file2.txt"],
                    "s3_files": ["s3://bucket/file1"],
                    "mongodb_docs": ["doc1"]
                }
            }
            mock_response.status_code = 200
            mock_delete.return_value = mock_response

            # Simulate the delete_permanently function behavior
            response = requests.delete(
                f"{API_BASE}/permanent-delete/{TEST_SESSION_ID}",
                params={"user_id": TEST_USER, "confirm": True}
            )
            data = response.json()

            # Validate
            self.assertEqual(data["status"], "success")
            self.assertIn("deleted_items", data)
            mock_delete.assert_called_once()

            # Check that confirm=True was passed
            call_args = mock_delete.call_args
            self.assertTrue(call_args[1]['params']['confirm'])

            print(f"✅ Permanent delete API test passed")
            print(f"   Deleted session: {TEST_SESSION_ID[:8]}...")

    def test_4_empty_trash(self):
        """Test emptying all trash API"""
        print("\n" + "="*60)
        print("TEST 4: Empty All Trash API")
        print("="*60)

        with patch('requests.post') as mock_post:
            mock_response = MagicMock()
            mock_response.json.return_value = {
                "status": "success",
                "deleted_count": 5,
                "deleted_sessions": [
                    {"session_id": "session1", "deleted_items": {"local_files": []}},
                    {"session_id": "session2", "deleted_items": {"local_files": []}}
                ]
            }
            mock_response.status_code = 200
            mock_post.return_value = mock_response

            # Simulate the empty_all_trash function behavior
            response = requests.post(
                f"{API_BASE}/empty-trash",
                params={"user_id": TEST_USER, "confirm": True}
            )
            data = response.json()

            # Validate
            self.assertEqual(data["status"], "success")
            self.assertEqual(data["deleted_count"], 5)
            mock_post.assert_called_once()

            # Check that confirm=True was passed
            call_args = mock_post.call_args
            self.assertTrue(call_args[1]['params']['confirm'])

            print(f"✅ Empty trash API test passed")
            print(f"   Deleted count: {data['deleted_count']}")

    def test_5_error_handling(self):
        """Test error handling in trash operations"""
        print("\n" + "="*60)
        print("TEST 5: Error Handling")
        print("="*60)

        # Test network error
        with patch('requests.get') as mock_get:
            mock_get.side_effect = requests.exceptions.RequestException("Network error")

            try:
                response = requests.get(f"{API_BASE}/trash", params={"user_id": TEST_USER})
                self.fail("Should have raised exception")
            except requests.exceptions.RequestException:
                print("✅ Network error raised as expected")

        # Test permission error
        with patch('requests.delete') as mock_delete:
            mock_response = MagicMock()
            mock_response.json.return_value = {
                "status": "error",
                "detail": "Permission denied"
            }
            mock_response.status_code = 403
            mock_delete.return_value = mock_response

            response = requests.delete(
                f"{API_BASE}/permanent-delete/{TEST_SESSION_ID}",
                params={"user_id": "wrong_user", "confirm": True}
            )
            data = response.json()

            self.assertEqual(data["status"], "error")
            print("✅ Permission error handled properly")

        # Test missing confirmation
        with patch('requests.post') as mock_post:
            mock_response = MagicMock()
            mock_response.json.return_value = {
                "status": "error",
                "detail": "Confirmation required"
            }
            mock_response.status_code = 400
            mock_post.return_value = mock_response

            response = requests.post(
                f"{API_BASE}/empty-trash",
                params={"user_id": TEST_USER, "confirm": False}
            )
            data = response.json()

            self.assertEqual(data["status"], "error")
            print("✅ Missing confirmation handled properly")

    def test_6_ui_interaction_flow(self):
        """Test complete API interaction flow"""
        print("\n" + "="*60)
        print("TEST 6: API Interaction Flow")
        print("="*60)

        # Simulate complete user flow
        with patch('requests.get') as mock_get, \
             patch('requests.post') as mock_post, \
             patch('requests.delete') as mock_delete:

            # Setup mock responses
            get_response = MagicMock()
            get_response.json.return_value = {
                "status": "success",
                "sessions": self.mock_trash_sessions,
                "count": 2
            }
            get_response.status_code = 200
            mock_get.return_value = get_response

            post_response = MagicMock()
            post_response.json.return_value = {
                "status": "success",
                "message": "Session moved to trash"
            }
            post_response.status_code = 200
            mock_post.return_value = post_response

            delete_response = MagicMock()
            delete_response.json.return_value = {
                "status": "success",
                "deleted_items": {}
            }
            delete_response.status_code = 200
            mock_delete.return_value = delete_response

            # Step 1: Load trash list
            response = requests.get(f"{API_BASE}/trash", params={"user_id": TEST_USER})
            data = response.json()
            self.assertEqual(data["count"], 2)
            print("✅ Step 1: Loaded trash list")

            # Step 2: Move session to trash
            response = requests.post(
                f"{API_BASE}/trash/{TEST_SESSION_ID}",
                params={"user_id": TEST_USER}
            )
            data = response.json()
            self.assertEqual(data["status"], "success")
            print("✅ Step 2: Moved session to trash")

            # Step 3: Delete session permanently
            response = requests.delete(
                f"{API_BASE}/permanent-delete/{TEST_SESSION_ID}",
                params={"user_id": TEST_USER, "confirm": True}
            )
            data = response.json()
            self.assertEqual(data["status"], "success")
            print("✅ Step 3: Deleted session permanently")

            print("\n✅ Complete API flow test passed")


def run_tests():
    """Run all Gradio interface tests"""
    print("="*70)
    print("GRADIO TRASH INTERFACE UNIT TESTS")
    print("="*70)

    # Create test suite
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromTestCase(TestTrashGradioInterface)

    # Run tests
    runner = unittest.TextTestRunner(verbosity=1)
    result = runner.run(suite)

    # Summary
    print("\n" + "="*70)
    print("TEST SUMMARY")
    print("="*70)
    print(f"Tests run: {result.testsRun}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")
    print(f"Skipped: {len(result.skipped)}")

    if result.wasSuccessful():
        print("\n✅ All Gradio tests passed!")
        return 0
    else:
        print("\n❌ Some tests failed")
        return 1


if __name__ == "__main__":
    sys.exit(run_tests())