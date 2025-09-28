#!/usr/bin/env python3
"""
Retest failed API endpoints with correct parameters
"""

import requests
import json
import os
import time
from datetime import datetime
from typing import Dict, Any, Optional

# Configuration
BASE_URL = "http://52.192.211.135:8001"
TEST_USER_ID = "test_user_api_retry"
OUTPUT_DIR = "test_api_payloads"

class FailedEndpointTester:
    def __init__(self):
        self.base_url = BASE_URL
        self.user_id = TEST_USER_ID
        self.session_id = None
        self.test_results = []

    def save_payload(self, endpoint: str, input_data: Any, output_data: Any, test_name: str):
        """Save request and response payloads to files"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_endpoint = endpoint.replace("/", "_").replace("{", "").replace("}", "")

        # Save input
        input_file = f"{OUTPUT_DIR}/inputs/{test_name}_{safe_endpoint}_{timestamp}_retry.json"
        with open(input_file, 'w') as f:
            json.dump({
                "endpoint": endpoint,
                "method": test_name.split("_")[0].upper() if "_" in test_name else "GET",
                "timestamp": timestamp,
                "data": input_data
            }, f, indent=2, default=str)

        # Save output
        output_file = f"{OUTPUT_DIR}/outputs/{test_name}_{safe_endpoint}_{timestamp}_retry.json"
        with open(output_file, 'w') as f:
            json.dump({
                "endpoint": endpoint,
                "status_code": output_data.get("status_code", 0),
                "timestamp": timestamp,
                "response": output_data.get("response", {})
            }, f, indent=2, default=str)

        print(f"  ✓ Saved payloads: {os.path.basename(input_file)}")

    def test_endpoint(self, test_name: str, method: str, endpoint: str,
                      data: Optional[Dict] = None, json_data: Optional[Dict] = None,
                      files: Optional[Dict] = None, params: Optional[Dict] = None):
        """Generic endpoint tester"""
        print(f"\nTesting: {test_name}")
        print(f"  Endpoint: {method} {endpoint}")

        url = f"{self.base_url}{endpoint}"

        try:
            if method == "GET":
                response = requests.get(url, params=params)
            elif method == "POST":
                if json_data:
                    response = requests.post(url, json=json_data, params=params)
                elif files:
                    response = requests.post(url, data=data, files=files, params=params)
                else:
                    response = requests.post(url, data=data, params=params)
            elif method == "DELETE":
                response = requests.delete(url, params=params)
            else:
                raise ValueError(f"Unsupported method: {method}")

            result = {
                "status_code": response.status_code,
                "response": response.json() if response.content else {}
            }

            # Save payloads
            input_payload = {
                "params": params,
                "data": data,
                "json": json_data,
                "files": str(files) if files else None
            }

            self.save_payload(endpoint, input_payload, result, test_name)

            # Record test result
            self.test_results.append({
                "test": test_name,
                "endpoint": f"{method} {endpoint}",
                "status": "PASS" if response.status_code < 400 else "FAIL",
                "status_code": response.status_code
            })

            print(f"  Status: {response.status_code}")
            if response.status_code >= 400:
                print(f"  Error: {result['response']}")
            else:
                print(f"  Response preview: {str(result['response'])[:200]}...")

            return result

        except Exception as e:
            print(f"  ERROR: {str(e)}")
            self.test_results.append({
                "test": test_name,
                "endpoint": f"{method} {endpoint}",
                "status": "ERROR",
                "error": str(e)
            })
            return None

    def run_retests(self):
        """Rerun failed tests with corrections"""
        print("="*60)
        print("Retesting Failed API Endpoints")
        print("="*60)

        # First, create a completed session for testing
        print("\n[SETUP] Creating a test session and waiting for completion...")

        result = self.test_endpoint(
            test_name="00_setup_session",
            method="POST",
            endpoint="/chat-queue",
            data={
                "message": "x = 1 + 1; print(f'Result: {x}')",
                "user_id": self.user_id,
                "language": "en"
            }
        )

        if result and result["status_code"] == 200:
            self.session_id = result["response"].get("session_id")
            print(f"  Created session: {self.session_id}")

            # Wait for completion
            print("  Waiting for session to complete (10 seconds)...")
            time.sleep(10)

            # Check if completed
            status_result = self.test_endpoint(
                test_name="00_check_completion",
                method="GET",
                endpoint=f"/status/{self.session_id}",
                params={"user_id": self.user_id}
            )

            if status_result:
                print(f"  Session status: {status_result['response'].get('status', 'unknown')}")

        print("\n" + "="*60)
        print("RETESTING FAILED ENDPOINTS")
        print("="*60)

        # 1. Retest /results (should work now that session is complete)
        if self.session_id:
            self.test_endpoint(
                test_name="01_results_retry",
                method="GET",
                endpoint=f"/results/{self.session_id}",
                params={"user_id": self.user_id}
            )

        # 2. Retest /continue-session with correct form data format
        if self.session_id:
            self.test_endpoint(
                test_name="02_continue_session_retry",
                method="POST",
                endpoint="/continue-session",
                data={  # Using form data instead of JSON
                    "session_id": self.session_id,
                    "message": "print('This is turn 2 retry')",
                    "user_id": self.user_id,
                    "turn_number": "2"
                }
            )

            # Wait for processing
            print("  Waiting for turn 2 to process...")
            time.sleep(5)

        # 3. Retest /unshare-session with correct query parameters
        if self.session_id:
            # First share it
            share_result = self.test_endpoint(
                test_name="03_share_for_unshare",
                method="POST",
                endpoint="/share-session",
                json_data={
                    "session_id": self.session_id,
                    "user_id": self.user_id,
                    "title": "Test for Unshare",
                    "description": "Testing unshare endpoint",
                    "tags": ["test", "retry"]
                }
            )

            # Then unshare with correct parameters
            self.test_endpoint(
                test_name="03_unshare_session_retry",
                method="POST",
                endpoint="/unshare-session",
                params={  # Using query parameters
                    "session_id": self.session_id,
                    "user_id": self.user_id
                }
            )

        # 4. Test /download-urls (checking if endpoint exists)
        if self.session_id:
            print("\n[INFO] Testing /download-urls endpoint (may not exist)...")
            self.test_endpoint(
                test_name="04_download_urls_retry",
                method="GET",
                endpoint=f"/download-urls/{self.session_id}",
                params={"user_id": self.user_id}
            )

        # 5. Retest /download (should work with completed session)
        if self.session_id:
            print("\n[INFO] Testing /download endpoint...")
            response = requests.get(
                f"{self.base_url}/download/{self.session_id}",
                params={"user_id": self.user_id},
                allow_redirects=True
            )

            result = {
                "status_code": response.status_code,
                "response": {
                    "content_type": response.headers.get("content-type", ""),
                    "content_length": len(response.content) if response.content else 0,
                    "is_redirect": len(response.history) > 0,
                    "final_url": str(response.url) if response.url else ""
                }
            }

            self.save_payload(
                f"/download/{self.session_id}",
                {"params": {"user_id": self.user_id}},
                result,
                "05_download_retry"
            )

            self.test_results.append({
                "test": "05_download_retry",
                "endpoint": f"GET /download/{self.session_id}",
                "status": "PASS" if response.status_code < 400 else "FAIL",
                "status_code": response.status_code
            })

            print(f"  Status: {response.status_code}")
            print(f"  Content type: {response.headers.get('content-type', 'unknown')}")
            print(f"  Content size: {len(response.content)} bytes")

        # 6. Retest /hard-delete with confirmation parameter
        if self.session_id:
            # First without confirmation (should fail)
            self.test_endpoint(
                test_name="06_hard_delete_no_confirm",
                method="DELETE",
                endpoint=f"/hard-delete/{self.session_id}",
                params={
                    "user_id": self.user_id
                }
            )

            # Then with confirmation (should succeed)
            self.test_endpoint(
                test_name="06_hard_delete_with_confirm",
                method="DELETE",
                endpoint=f"/hard-delete/{self.session_id}",
                params={
                    "user_id": self.user_id,
                    "confirm": "true"
                }
            )

        # Generate summary
        self.generate_summary()

    def generate_summary(self):
        """Generate retry test summary"""
        print("\n" + "="*60)
        print("RETRY TEST SUMMARY")
        print("="*60)

        passed = sum(1 for r in self.test_results if r["status"] == "PASS")
        failed = sum(1 for r in self.test_results if r["status"] == "FAIL")
        errors = sum(1 for r in self.test_results if r["status"] == "ERROR")

        print(f"Total Retry Tests: {len(self.test_results)}")
        print(f"Passed: {passed}")
        print(f"Failed: {failed}")
        print(f"Errors: {errors}")

        if failed > 0 or errors > 0:
            print("\nFailed/Error Tests:")
            for result in self.test_results:
                if result["status"] in ["FAIL", "ERROR"]:
                    print(f"  - {result['test']}: {result['endpoint']} (Status: {result.get('status_code', 'N/A')})")

        # Save retry summary
        summary_file = f"{OUTPUT_DIR}/retry_test_summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(summary_file, 'w') as f:
            json.dump({
                "timestamp": datetime.now().isoformat(),
                "summary": {
                    "total": len(self.test_results),
                    "passed": passed,
                    "failed": failed,
                    "errors": errors
                },
                "results": self.test_results
            }, f, indent=2)

        print(f"\n✓ Retry summary saved to: {summary_file}")

def main():
    """Main test runner for failed endpoints"""
    tester = FailedEndpointTester()

    try:
        # Check server health first
        response = requests.get(f"{BASE_URL}/health", timeout=5)
        if response.status_code != 200:
            print(f"Warning: Server health check returned {response.status_code}")

        # Run retests
        tester.run_retests()

    except requests.exceptions.ConnectionError:
        print(f"ERROR: Cannot connect to server at {BASE_URL}")
        print("Please ensure the FastAPI server is running.")
    except Exception as e:
        print(f"ERROR: {str(e)}")

if __name__ == "__main__":
    main()