#!/usr/bin/env python3
"""
Test script to verify that the report display functionality works correctly
"""

import requests
from datetime import datetime

class FastAPIClient:
    def __init__(self, base_url: str = "http://localhost:8001"):
        if not base_url.startswith(('http://', 'https://')):
            base_url = f"http://{base_url}"
        self.base_url = base_url.rstrip('/')

    def get_json_results(self, session_id: str):
        """Get structured JSON results for a completed session"""
        try:
            response = requests.get(f"{self.base_url}/results/{session_id}", timeout=10)
            if response.status_code == 200:
                return response.json()
            return None
        except Exception as e:
            print(f"Error getting JSON results: {e}")
            return None

def test_report_display():
    """Test the report display functionality"""

    # Use a completed session for testing
    session_id = "2bb02b3a-93c6-4151-8d18-4dc4f4a7ed1b"

    print("=== TESTING REPORT DISPLAY FUNCTIONALITY ===")
    print(f"Testing session: {session_id}")

    client = FastAPIClient()

    # Test getting the results
    results_data = client.get_json_results(session_id)

    if results_data:
        print("✅ Successfully retrieved results data")
        print(f"Keys in results: {list(results_data.keys())}")

        if 'content' in results_data:
            content = results_data['content']
            print(f"Content keys: {list(content.keys())}")

            if 'final_report' in content:
                final_report = content['final_report']
                print(f"✅ Final report found!")
                print(f"Report length: {len(final_report)} characters")
                print("\n=== REPORT PREVIEW ===")
                print(final_report[:500] + "..." if len(final_report) > 500 else final_report)

                # Simulate the display format
                result_display = f"""
## 📋 Final Report

{final_report}

"""
                print(f"\n=== FORMATTED DISPLAY ===")
                print("Report will be displayed in markdown format below the Download Session Files button")
                print(f"Total display length: {len(result_display)} characters")

            else:
                print("❌ No final_report found in content")
        else:
            print("❌ No content field found in results")
    else:
        print("❌ Failed to retrieve results data")

if __name__ == "__main__":
    test_report_display()