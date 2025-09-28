#!/usr/bin/env python3
"""
Comprehensive test of all FastAPI endpoints with saved payloads
"""

import requests
import json
import os
import time
from datetime import datetime

# Configuration
BASE_URL = "http://52.192.211.135:8001"
TEST_USER_ID = "test_comprehensive"
OUTPUT_DIR = "api_test_results"

# Create output directories
os.makedirs(f"{OUTPUT_DIR}/inputs", exist_ok=True)
os.makedirs(f"{OUTPUT_DIR}/outputs", exist_ok=True)

def save_test_data(test_name, endpoint, method, request_data, response_data):
    """Save test input and output"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Save input
    input_file = f"{OUTPUT_DIR}/inputs/{test_name}_{timestamp}.json"
    with open(input_file, 'w') as f:
        json.dump({
            "test": test_name,
            "endpoint": endpoint,
            "method": method,
            "timestamp": timestamp,
            "request": request_data
        }, f, indent=2, default=str)

    # Save output
    output_file = f"{OUTPUT_DIR}/outputs/{test_name}_{timestamp}.json"
    with open(output_file, 'w') as f:
        json.dump({
            "test": test_name,
            "endpoint": endpoint,
            "status_code": response_data.get("status_code"),
            "timestamp": timestamp,
            "response": response_data.get("response")
        }, f, indent=2, default=str)

    return input_file, output_file

def run_test(test_name, method, endpoint, **kwargs):
    """Run a single test and save results"""
    print(f"\n[{test_name}]")
    print(f"  {method} {endpoint}")

    url = f"{BASE_URL}{endpoint}"

    try:
        if method == "GET":
            response = requests.get(url, **kwargs)
        elif method == "POST":
            response = requests.post(url, **kwargs)
        elif method == "DELETE":
            response = requests.delete(url, **kwargs)
        else:
            raise ValueError(f"Unsupported method: {method}")

        response_data = {
            "status_code": response.status_code,
            "response": response.json() if response.content else {}
        }

        # Save test data
        input_file, output_file = save_test_data(
            test_name, endpoint, method,
            kwargs, response_data
        )

        # Print result
        status_emoji = "✓" if response.status_code < 400 else "✗"
        print(f"  {status_emoji} Status: {response.status_code}")

        if response.status_code >= 400:
            print(f"  Error: {response_data['response']}")

        return response.status_code < 400, response_data

    except Exception as e:
        print(f"  ✗ Error: {str(e)}")
        save_test_data(
            test_name, endpoint, method,
            kwargs, {"status_code": 0, "response": {"error": str(e)}}
        )
        return False, None

def main():
    """Run all endpoint tests"""
    print("="*60)
    print("COMPREHENSIVE API ENDPOINT TESTS")
    print("="*60)
    print(f"Server: {BASE_URL}")
    print(f"User: {TEST_USER_ID}")
    print(f"Output: {OUTPUT_DIR}/")

    results = []
    session_id = None

    # 1. Health Check
    success, data = run_test(
        "01_health",
        "GET",
        "/health"
    )
    results.append(("Health Check", success))

    # 2. Submit Chat Request
    success, data = run_test(
        "02_chat_queue",
        "POST",
        "/chat-queue",
        data={
            "message": "x = 42\nprint(f'The answer is {x}')",
            "user_id": TEST_USER_ID,
            "language": "en"
        }
    )
    results.append(("Chat Queue", success))

    if success and data:
        session_id = data["response"].get("session_id")
        print(f"  Session ID: {session_id}")

        # Wait for processing
        print("\n  Waiting for processing...")
        time.sleep(15)  # Increased wait time

    # 3-10: Session-based endpoints
    if session_id:
        # Status check
        success, _ = run_test(
            "03_status",
            "GET",
            f"/status/{session_id}",
            params={"user_id": TEST_USER_ID}
        )
        results.append(("Status Check", success))

        # Progress check
        success, _ = run_test(
            "04_progress",
            "GET",
            f"/progress/{session_id}",
            params={"user_id": TEST_USER_ID}
        )
        results.append(("Progress Check", success))

        # Results
        success, _ = run_test(
            "05_results",
            "GET",
            f"/results/{session_id}",
            params={"user_id": TEST_USER_ID}
        )
        results.append(("Results", success))

        # Snapshots
        success, _ = run_test(
            "06_snapshots",
            "GET",
            f"/snapshots/{session_id}",
            params={"user_id": TEST_USER_ID}
        )
        results.append(("Snapshots", success))

        # Session info
        success, _ = run_test(
            "07_multiturn_session",
            "GET",
            f"/multiturn-session/{session_id}",
            params={"user_id": TEST_USER_ID}
        )
        results.append(("Multiturn Session Info", success))

        # Turn report
        success, _ = run_test(
            "08_turn_report",
            "GET",
            f"/turn-report/{session_id}/1",
            params={"user_id": TEST_USER_ID}
        )
        results.append(("Turn Report", success))

        # Session context
        success, _ = run_test(
            "09_session_context",
            "GET",
            f"/session-context/{session_id}",
            params={"user_id": TEST_USER_ID}
        )
        results.append(("Session Context", success))

        # Continue session
        success, _ = run_test(
            "10_continue_session",
            "POST",
            "/continue-session",
            data={
                "session_id": session_id,
                "message": "print('Turn 2')",
                "user_id": TEST_USER_ID,
                "turn_number": "2"
            }
        )
        results.append(("Continue Session", success))

        # Share session
        success, _ = run_test(
            "11_share_session",
            "POST",
            "/share-session",
            json={
                "session_id": session_id,
                "user_id": TEST_USER_ID,
                "title": "Test Session",
                "description": "Comprehensive API test",
                "tags": ["test", "api"]
            }
        )
        results.append(("Share Session", success))

        # Shared session info
        success, _ = run_test(
            "12_shared_session",
            "GET",
            f"/shared-session/{session_id}"
        )
        results.append(("Shared Session Info", success))

        # Unshare session
        success, _ = run_test(
            "13_unshare_session",
            "POST",
            "/unshare-session",
            params={
                "session_id": session_id,
                "user_id": TEST_USER_ID
            }
        )
        results.append(("Unshare Session", success))

        # Download
        print(f"\n[14_download]")
        print(f"  GET /download/{session_id}")
        response = requests.get(
            f"{BASE_URL}/download/{session_id}",
            params={"user_id": TEST_USER_ID}
        )
        save_test_data(
            "14_download",
            f"/download/{session_id}",
            "GET",
            {"params": {"user_id": TEST_USER_ID}},
            {
                "status_code": response.status_code,
                "response": {
                    "content_type": response.headers.get("content-type"),
                    "size": len(response.content) if response.content else 0
                }
            }
        )
        success = response.status_code < 400
        print(f"  {'✓' if success else '✗'} Status: {response.status_code}")
        results.append(("Download", success))

        # Stop session
        success, _ = run_test(
            "15_stop",
            "POST",
            f"/stop/{session_id}",
            params={"user_id": TEST_USER_ID}
        )
        results.append(("Stop Session", success))

        # Hard delete
        success, _ = run_test(
            "16_hard_delete",
            "DELETE",
            f"/hard-delete/{session_id}",
            params={
                "user_id": TEST_USER_ID,
                "confirm": "true"
            }
        )
        results.append(("Hard Delete", success))

    # 17-20: List endpoints
    success, _ = run_test(
        "17_all_sessions",
        "GET",
        "/all-sessions",
        params={"user_id": TEST_USER_ID}
    )
    results.append(("All Sessions", success))

    success, _ = run_test(
        "18_multiturn_sessions",
        "GET",
        "/multiturn-sessions",
        params={"user_id": TEST_USER_ID}
    )
    results.append(("Multiturn Sessions", success))

    success, _ = run_test(
        "19_search_shared",
        "POST",
        "/search-shared-sessions",
        json={"query": "test"}
    )
    results.append(("Search Shared", success))

    success, _ = run_test(
        "20_popular_tags",
        "GET",
        "/popular-tags"
    )
    results.append(("Popular Tags", success))

    # Generate summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)

    passed = sum(1 for _, success in results if success)
    failed = len(results) - passed

    print(f"Total: {len(results)}")
    print(f"Passed: {passed} ({passed*100//len(results)}%)")
    print(f"Failed: {failed} ({failed*100//len(results)}%)")

    if failed > 0:
        print("\nFailed tests:")
        for name, success in results:
            if not success:
                print(f"  - {name}")

    # Save summary
    summary_file = f"{OUTPUT_DIR}/test_summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(summary_file, 'w') as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "total": len(results),
            "passed": passed,
            "failed": failed,
            "results": [{"test": name, "passed": success} for name, success in results]
        }, f, indent=2)

    print(f"\n✓ Test complete!")
    print(f"✓ Input payloads: {OUTPUT_DIR}/inputs/")
    print(f"✓ Output payloads: {OUTPUT_DIR}/outputs/")
    print(f"✓ Summary: {summary_file}")

if __name__ == "__main__":
    main()