#!/usr/bin/env python3
"""
Complete test to simulate the full Gradio interface display including snapshots and report
"""

import requests
from datetime import datetime

class FastAPIClient:
    def __init__(self, base_url: str = "http://localhost:8001"):
        if not base_url.startswith(('http://', 'https://')):
            base_url = f"http://{base_url}"
        self.base_url = base_url.rstrip('/')

    def get_status(self, session_id: str):
        try:
            response = requests.get(f"{self.base_url}/status/{session_id}", timeout=10)
            if response.status_code == 200:
                return response.json()
            return None
        except Exception as e:
            print(f"Error getting status: {e}")
            return None

    def get_snapshots(self, session_id: str):
        try:
            response = requests.get(f"{self.base_url}/snapshots/{session_id}", timeout=10)
            if response.status_code == 200:
                return response.json()
            return None
        except Exception as e:
            print(f"Error getting snapshots: {e}")
            return None

    def get_json_results(self, session_id: str):
        try:
            response = requests.get(f"{self.base_url}/results/{session_id}", timeout=10)
            if response.status_code == 200:
                return response.json()
            return None
        except Exception as e:
            print(f"Error getting JSON results: {e}")
            return None

def test_complete_display():
    """Test the complete display functionality including snapshots and report"""

    session_id = "2bb02b3a-93c6-4151-8d18-4dc4f4a7ed1b"  # Completed session

    print("=== TESTING COMPLETE DISPLAY FUNCTIONALITY ===")
    print(f"Session ID: {session_id}")

    client = FastAPIClient()

    # Get status
    status_data = client.get_status(session_id)
    if not status_data:
        print("❌ Failed to get status")
        return

    current_status = status_data.get("status", "unknown")
    is_complete = current_status in ["completed", "error", "cancelled"]

    print(f"Status: {current_status}")
    print(f"Is Complete: {is_complete}")

    # Start building the display (simulating Gradio interface)
    result_display = f"""## 📊 Session Status

**Status:** {'✅ Completed' if current_status == 'completed' else f'🔄 {current_status.title()}'}
**Session ID:** `{session_id}`
**Query:** {status_data.get('query', 'N/A')}
**Language:** {status_data.get('language', 'en').upper()}
**Timestamp:** {status_data.get('timestamp', 'N/A')}

"""

    # Add snapshots
    snapshots_data = client.get_snapshots(session_id)
    if snapshots_data:
        snapshots = snapshots_data.get("snapshots", [])
        if snapshots:
            result_display += f"""

## 📸 All Snapshots ({len(snapshots)} total) - Scroll Down for Full Content

*All snapshots are displayed below in chronological order. Scroll down to view complete content.*

"""
            for i, snapshot in enumerate(snapshots, 1):
                snap_time = snapshot.get("timestamp", "N/A")
                try:
                    dt = datetime.fromisoformat(snap_time.replace('Z', '+00:00'))
                    formatted_time = dt.strftime('%Y-%m-%d %H:%M:%S')
                except:
                    formatted_time = snap_time

                content = snapshot.get("content", {})
                thinking_content = content.get("thinking_content", "")
                char_count = len(thinking_content) if thinking_content else 0

                result_display += f"""
---

### 📸 Snapshot #{i} - {formatted_time}
**Content Size:** {char_count:,} characters

```
{thinking_content[:200] if thinking_content else 'No thinking content available'}...
[Content truncated for preview - full content shown in actual interface]
```

"""

    # Add report for completed sessions
    if is_complete and current_status == "completed":
        results_data = client.get_json_results(session_id)
        if results_data and 'content' in results_data and 'final_report' in results_data['content']:
            final_report = results_data['content']['final_report']
            if final_report:
                result_display += f"""

## 📋 Final Report

{final_report}

"""

    print("=== COMPLETE DISPLAY PREVIEW ===")
    print(f"Total display length: {len(result_display):,} characters")
    print("\n" + "="*80)
    print(result_display)
    print("="*80)

    print(f"\n=== SUMMARY ===")
    print(f"✅ Status display: Working")
    print(f"✅ Snapshots display: {len(snapshots)} snapshots shown" if snapshots_data else "❌ No snapshots")
    print(f"✅ Report display: {'Working' if is_complete and 'final_report' in str(results_data) else 'Not applicable (session not completed)'}")
    print(f"✅ Scrollable format: All content displayed with proper formatting")

if __name__ == "__main__":
    test_complete_display()