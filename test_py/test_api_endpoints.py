#!/usr/bin/env python3
"""
Unit tests for FastAPI Multiturn Server endpoints
Tests each API endpoint and saves request/response payloads
"""

import requests
import json
import os
import time
from datetime import datetime
from typing import Dict, Any, Optional
import sys

# Configuration
BASE_URL = "http://52.192.211.135:8001"  # Using the actual server
TEST_USER_ID = "test_user_api"
OUTPUT_DIR = "test_api_payloads"

# Create output directories
os.makedirs(f"{OUTPUT_DIR}/inputs", exist_ok=True)
os.makedirs(f"{OUTPUT_DIR}/outputs", exist_ok=True)

class APITester:
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
        input_file = f"{OUTPUT_DIR}/inputs/{test_name}_{safe_endpoint}_{timestamp}.json"
        with open(input_file, 'w') as f:
            json.dump({
                "endpoint": endpoint,
                "method": test_name.split("_")[0].upper() if "_" in test_name else "GET",
                "timestamp": timestamp,
                "data": input_data
            }, f, indent=2, default=str)

        # Save output
        output_file = f"{OUTPUT_DIR}/outputs/{test_name}_{safe_endpoint}_{timestamp}.json"
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
                print(f"  Response preview: {str(result['response'])[:100]}...")

            return result

        except Exception as e:
            print(f"  ERROR: {str(e)}")
            self.test_results.append({
                "test": test_name,
                "endpoint": f"{method} {endpoint}",
                "status": "ERROR",
                "error": str(e)
            })

            # Save error payload
            self.save_payload(endpoint,
                            {"params": params, "data": data, "json": json_data},
                            {"status_code": 0, "response": {"error": str(e)}},
                            test_name)
            return None

    def run_all_tests(self):
        """Run all API endpoint tests"""
        print("="*60)
        print("FastAPI Multiturn Server API Tests")
        print("="*60)

        # 1. Test Health Check
        self.test_endpoint(
            test_name="01_health_check",
            method="GET",
            endpoint="/health"
        )

        # 2. Test Chat Queue submission
        result = self.test_endpoint(
            test_name="02_chat_queue",
            method="POST",
            endpoint="/chat-queue",
            data={
                "message": "print('Hello from API test')",
                "user_id": self.user_id,
                "language": "en"
            }
        )

        if result and result["status_code"] == 200:
            self.session_id = result["response"].get("session_id")
            print(f"  Got session_id: {self.session_id}")

            # Wait a bit for processing
            print("  Waiting for processing...")
            time.sleep(3)

        # 3. Test Status Check
        if self.session_id:
            self.test_endpoint(
                test_name="03_status_check",
                method="GET",
                endpoint=f"/status/{self.session_id}",
                params={"user_id": self.user_id}
            )

        # 4. Test Progress Check
        if self.session_id:
            self.test_endpoint(
                test_name="04_progress_check",
                method="GET",
                endpoint=f"/progress/{self.session_id}",
                params={"user_id": self.user_id}
            )

        # 5. Test Results
        if self.session_id:
            self.test_endpoint(
                test_name="05_results",
                method="GET",
                endpoint=f"/results/{self.session_id}",
                params={"user_id": self.user_id}
            )

        # 6. Test Snapshots
        if self.session_id:
            self.test_endpoint(
                test_name="06_snapshots",
                method="GET",
                endpoint=f"/snapshots/{self.session_id}",
                params={"user_id": self.user_id}
            )

        # 7. Test All Sessions
        self.test_endpoint(
            test_name="07_all_sessions",
            method="GET",
            endpoint="/all-sessions",
            params={"user_id": self.user_id}
        )

        # 8. Test Multiturn Sessions List
        self.test_endpoint(
            test_name="08_multiturn_sessions",
            method="GET",
            endpoint="/multiturn-sessions",
            params={"user_id": self.user_id}
        )

        # 9. Test Continue Session
        if self.session_id:
            result = self.test_endpoint(
                test_name="09_continue_session",
                method="POST",
                endpoint="/continue-session",
                json_data={
                    "session_id": self.session_id,
                    "message": "print('This is turn 2')",
                    "user_id": self.user_id,
                    "turn_number": 2
                }
            )

            if result and result["status_code"] == 200:
                print("  Waiting for turn 2 processing...")
                time.sleep(3)

        # 10. Test Multiturn Session Info
        if self.session_id:
            self.test_endpoint(
                test_name="10_multiturn_session_info",
                method="GET",
                endpoint=f"/multiturn-session/{self.session_id}",
                params={"user_id": self.user_id}
            )

        # 11. Test Turn Report
        if self.session_id:
            self.test_endpoint(
                test_name="11_turn_report",
                method="GET",
                endpoint=f"/turn-report/{self.session_id}/1",
                params={"user_id": self.user_id}
            )

        # 12. Test Session Context
        if self.session_id:
            self.test_endpoint(
                test_name="12_session_context",
                method="GET",
                endpoint=f"/session-context/{self.session_id}",
                params={"user_id": self.user_id}
            )

        # 13. Test Share Session
        if self.session_id:
            self.test_endpoint(
                test_name="13_share_session",
                method="POST",
                endpoint="/share-session",
                json_data={
                    "session_id": self.session_id,
                    "user_id": self.user_id,
                    "title": "API Test Session",
                    "description": "Test session from API unit tests",
                    "tags": ["test", "api", "automated"]
                }
            )

        # 14. Test Search Shared Sessions
        self.test_endpoint(
            test_name="14_search_shared_sessions",
            method="POST",
            endpoint="/search-shared-sessions",
            json_data={
                "query": "test",
                "tags": ["test"]
            }
        )

        # 15. Test Shared Session
        if self.session_id:
            self.test_endpoint(
                test_name="15_shared_session",
                method="GET",
                endpoint=f"/shared-session/{self.session_id}"
            )

        # 16. Test Popular Tags
        self.test_endpoint(
            test_name="16_popular_tags",
            method="GET",
            endpoint="/popular-tags"
        )

        # 17. Test Unshare Session
        if self.session_id:
            self.test_endpoint(
                test_name="17_unshare_session",
                method="POST",
                endpoint="/unshare-session",
                json_data={
                    "session_id": self.session_id,
                    "user_id": self.user_id
                }
            )

        # 18. Test Download URLs
        if self.session_id:
            self.test_endpoint(
                test_name="18_download_urls",
                method="GET",
                endpoint=f"/download-urls/{self.session_id}",
                params={"user_id": self.user_id}
            )

        # 19. Test Download (Note: This returns a file, so we handle it differently)
        if self.session_id:
            print(f"\nTesting: 19_download")
            print(f"  Endpoint: GET /download/{self.session_id}")
            try:
                url = f"{self.base_url}/download/{self.session_id}"
                response = requests.get(url, params={"user_id": self.user_id})

                # Save the response metadata
                self.save_payload(
                    f"/download/{self.session_id}",
                    {"params": {"user_id": self.user_id}},
                    {
                        "status_code": response.status_code,
                        "response": {
                            "content_type": response.headers.get("content-type"),
                            "content_length": len(response.content) if response.content else 0,
                            "is_redirect": response.history != []
                        }
                    },
                    "19_download"
                )

                self.test_results.append({
                    "test": "19_download",
                    "endpoint": f"GET /download/{self.session_id}",
                    "status": "PASS" if response.status_code < 400 else "FAIL",
                    "status_code": response.status_code
                })

                print(f"  Status: {response.status_code}")

            except Exception as e:
                print(f"  ERROR: {str(e)}")
                self.test_results.append({
                    "test": "19_download",
                    "endpoint": f"GET /download/{self.session_id}",
                    "status": "ERROR",
                    "error": str(e)
                })

        # 20. Test Stop Session
        if self.session_id:
            self.test_endpoint(
                test_name="20_stop_session",
                method="POST",
                endpoint=f"/stop/{self.session_id}",
                params={"user_id": self.user_id}
            )

        # 21. Test Hard Delete
        if self.session_id:
            self.test_endpoint(
                test_name="21_hard_delete",
                method="DELETE",
                endpoint=f"/hard-delete/{self.session_id}",
                params={"user_id": self.user_id}
            )

        # Generate Summary Report
        self.generate_report()

    def generate_report(self):
        """Generate test summary report"""
        print("\n" + "="*60)
        print("TEST SUMMARY")
        print("="*60)

        passed = sum(1 for r in self.test_results if r["status"] == "PASS")
        failed = sum(1 for r in self.test_results if r["status"] == "FAIL")
        errors = sum(1 for r in self.test_results if r["status"] == "ERROR")

        print(f"Total Tests: {len(self.test_results)}")
        print(f"Passed: {passed}")
        print(f"Failed: {failed}")
        print(f"Errors: {errors}")

        if failed > 0 or errors > 0:
            print("\nFailed/Error Tests:")
            for result in self.test_results:
                if result["status"] in ["FAIL", "ERROR"]:
                    print(f"  - {result['test']}: {result['endpoint']} ({result['status']})")
                    if "error" in result:
                        print(f"    Error: {result['error']}")

        # Save summary to file
        summary_file = f"{OUTPUT_DIR}/test_summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
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

        print(f"\n✓ Summary saved to: {summary_file}")
        print(f"✓ Input payloads saved in: {OUTPUT_DIR}/inputs/")
        print(f"✓ Output payloads saved in: {OUTPUT_DIR}/outputs/")

def main():
    """Main test runner"""
    tester = APITester()

    try:
        # Check if server is running
        response = requests.get(f"{BASE_URL}/health", timeout=5)
        if response.status_code != 200:
            print(f"Warning: Server health check returned {response.status_code}")

        # Run all tests
        tester.run_all_tests()

    except requests.exceptions.ConnectionError:
        print(f"ERROR: Cannot connect to server at {BASE_URL}")
        print("Please ensure the FastAPI server is running.")
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()