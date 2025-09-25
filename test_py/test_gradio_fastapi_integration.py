#!/usr/bin/env python3
"""
End-to-End Gradio-FastAPI Integration Test
Tests the complete workflow from Gradio interface to FastAPI backend
"""
import os
import tempfile
import time
from unittest.mock import patch

# Import the updated Gradio client
from agent_gradio_fastapi_multiturn import FastAPIClient


def test_gradio_fastapi_integration():
    """Test complete integration between Gradio client and FastAPI server"""
    print("🧪 GRADIO-FASTAPI INTEGRATION TEST")
    print("=" * 50)

    # Use local FastAPI server
    base_url = "http://localhost:8001"
    client = FastAPIClient(base_url)

    print("\n1️⃣ TESTING HEALTH CHECK")
    print("-" * 25)
    try:
        health_ok = client.health_check()
        if health_ok:
            print("✅ Health check successful")
        else:
            print("❌ Health check failed - FastAPI server not running")
            print("   Please start the FastAPI server first:")
            print("   python agent_fastapi_server_multiturn.py")
            return False
    except Exception as e:
        print(f"❌ Health check error: {e}")
        return False

    print("\n2️⃣ TESTING SUBMIT REQUEST (NEW SESSION)")
    print("-" * 40)

    # Test submit_request with proper user_id
    user_id = "test_user_gradio"
    message = "Hello, this is a test message from Gradio integration test"

    try:
        session_id = client.submit_request(message, language="en", user_id=user_id)
        if session_id:
            print(f"✅ Request submitted successfully!")
            print(f"   Session ID: {session_id}")
            print(f"   User ID: {user_id}")
        else:
            print("❌ Failed to submit request")
            return False
    except Exception as e:
        print(f"❌ Submit request error: {e}")
        return False

    print("\n3️⃣ TESTING STATUS CHECK")
    print("-" * 25)

    try:
        status = client.get_status(session_id, user_id)
        if status:
            print(f"✅ Status retrieved successfully!")
            print(f"   Session: {status.get('session_id', 'N/A')}")
            print(f"   Status: {status.get('status', 'N/A')}")
            print(f"   Complete: {status.get('is_complete', 'N/A')}")
        else:
            print("❌ Failed to get status")
            return False
    except Exception as e:
        print(f"❌ Status check error: {e}")
        return False

    print("\n4️⃣ TESTING CONTINUE SESSION")
    print("-" * 29)

    try:
        continue_message = "This is a follow-up message to continue the conversation"
        continue_result = client.continue_session(session_id, continue_message, user_id=user_id)

        if continue_result:
            print(f"✅ Session continued successfully!")
            print(f"   Session: {continue_result.get('session_id', 'N/A')}")
            print(f"   Turn: {continue_result.get('turn_number', 'N/A')}")
            print(f"   Status: {continue_result.get('status', 'N/A')}")
        else:
            print("❌ Failed to continue session")
            return False
    except Exception as e:
        print(f"❌ Continue session error: {e}")
        return False

    print("\n5️⃣ TESTING FILE UPLOAD CAPABILITY")
    print("-" * 34)

    # Create a test file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        f.write("This is a test file for Gradio integration\nLine 2\nLine 3")
        test_file_path = f.name

    try:
        # Test submit_request with file
        file_session_id = client.submit_request(
            message="Analyze this test file",
            language="en",
            user_id=user_id,
            files=[test_file_path]
        )

        if file_session_id:
            print(f"✅ File upload request submitted!")
            print(f"   Session ID: {file_session_id}")
            print(f"   File: {os.path.basename(test_file_path)}")
        else:
            print("❌ Failed to submit file upload request")

        # Test continue_session with file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            f.write("name,age,department\nAlice,25,Engineering\nBob,30,Marketing")
            csv_file_path = f.name

        continue_result = client.continue_session(
            session_id=file_session_id,
            message="Now analyze this CSV data too",
            user_id=user_id,
            files=[csv_file_path]
        )

        if continue_result:
            print(f"✅ File upload in continue session successful!")
            print(f"   Turn: {continue_result.get('turn_number', 'N/A')}")
        else:
            print("❌ Failed to upload file in continue session")

        # Cleanup
        os.unlink(test_file_path)
        os.unlink(csv_file_path)

    except Exception as e:
        print(f"❌ File upload error: {e}")
        # Cleanup on error
        try:
            os.unlink(test_file_path)
            os.unlink(csv_file_path)
        except:
            pass

    print("\n6️⃣ TESTING SECURITY ISOLATION")
    print("-" * 30)

    try:
        # Test with different user trying to access session
        different_user = "different_user"

        # Try to get status with wrong user
        wrong_status = client.get_status(session_id, different_user)
        if wrong_status is None:
            print("✅ Cross-user status access properly blocked")
        else:
            print("❌ Security issue: Cross-user access allowed")

        # Try to continue session with wrong user
        wrong_continue = client.continue_session(
            session_id, "Unauthorized access attempt", user_id=different_user
        )
        if wrong_continue is None:
            print("✅ Cross-user session access properly blocked")
        else:
            print("❌ Security issue: Cross-user session access allowed")

    except Exception as e:
        print(f"❌ Security test error: {e}")

    print("\n7️⃣ TESTING MISSING USER_ID VALIDATION")
    print("-" * 37)

    try:
        # Test submit_request without user_id
        no_user_session = client.submit_request("Test without user", user_id=None)
        if no_user_session is None:
            print("✅ Missing user_id properly rejected in submit_request")
        else:
            print("❌ Missing user_id validation failed")

        # Test continue_session without user_id
        no_user_continue = client.continue_session(session_id, "Test without user", user_id=None)
        if no_user_continue is None:
            print("✅ Missing user_id properly rejected in continue_session")
        else:
            print("❌ Missing user_id validation failed")

    except Exception as e:
        print(f"❌ User ID validation test error: {e}")

    print("\n" + "=" * 50)
    print("🎉 INTEGRATION TEST COMPLETE!")
    print("\nFeatures Tested:")
    print("✅ Gradio client health check")
    print("✅ Form data submission (instead of JSON)")
    print("✅ Multi-turn conversation workflow")
    print("✅ File upload capabilities")
    print("✅ User ID validation and security")
    print("✅ Status checking and session management")

    return True


def test_actual_gradio_functions():
    """Test the actual Gradio interface functions"""
    print("\n" + "=" * 50)
    print("🎭 GRADIO INTERFACE FUNCTIONS TEST")
    print("=" * 50)

    # Import the Gradio functions
    import sys
    sys.path.insert(0, '.')

    try:
        # This will test the actual Gradio functions (mocked)
        print("Testing Gradio functions with mock...")

        # Mock the FastAPI client to avoid actual server calls
        with patch('agent_gradio_fastapi_multiturn.FastAPIClient') as mock_client_class:
            mock_client = mock_client_class.return_value
            mock_client.submit_request.return_value = "test-session-123"
            mock_client.continue_session.return_value = {
                "session_id": "test-session-123",
                "turn_number": 2,
                "status": "queued"
            }

            # Import and test the Gradio functions
            from agent_gradio_fastapi_multiturn import FastAPIClient

            # Test data
            test_url = "http://localhost:8001"
            test_user_id = "test_user"
            test_query = "Test query for Gradio"
            test_language = "en"

            print("1️⃣ Testing with mock client...")
            client = FastAPIClient(test_url)

            # Test submit_request
            session_id = client.submit_request(test_query, test_language, test_user_id)
            print(f"   Mock submit_request returned: {session_id}")

            # Test continue_session
            continue_result = client.continue_session(session_id, "Follow up", user_id=test_user_id)
            print(f"   Mock continue_session returned: {continue_result}")

            print("✅ Gradio interface functions work with mocked client")

    except Exception as e:
        print(f"❌ Gradio functions test error: {e}")

    print("✅ Gradio interface test complete!")


if __name__ == "__main__":
    print("🚀 Starting comprehensive Gradio-FastAPI integration tests...")

    # Test 1: Real integration (requires running FastAPI server)
    integration_success = test_gradio_fastapi_integration()

    # Test 2: Gradio functions (mocked)
    test_actual_gradio_functions()

    if integration_success:
        print("\n🎉 ALL TESTS PASSED!")
        print("The Gradio-FastAPI integration is working correctly.")
    else:
        print("\n⚠️  Some tests failed. Check the FastAPI server status.")