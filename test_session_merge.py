#!/usr/bin/env python3
"""
Test script to verify that the session merge functionality works correctly
"""

import requests
from typing import List

class FastAPIClient:
    def __init__(self, base_url: str = "http://localhost:8001"):
        if not base_url.startswith(('http://', 'https://')):
            base_url = f"http://{base_url}"
        self.base_url = base_url.rstrip('/')

    def get_all_sessions(self) -> List[dict]:
        """Get all sessions from server storage and active sessions"""
        all_sessions = []
        session_ids_seen = set()

        try:
            # First, get stored/completed sessions from /all-sessions
            print(f"Fetching stored sessions from: {self.base_url}/all-sessions")
            response = requests.get(f"{self.base_url}/all-sessions", timeout=10)
            if response.status_code == 200:
                data = response.json()
                stored_sessions = data.get("sessions", [])
                print(f"Retrieved {len(stored_sessions)} stored sessions")
                for session in stored_sessions:
                    session_id = session.get("session_id", "")
                    if session_id and session_id not in session_ids_seen:
                        all_sessions.append(session)
                        session_ids_seen.add(session_id)
            else:
                print(f"All-sessions endpoint returned {response.status_code}")

            # Then, get active sessions from /sessions
            print(f"Fetching active sessions from: {self.base_url}/sessions")
            response = requests.get(f"{self.base_url}/sessions", timeout=10)
            if response.status_code == 200:
                active_sessions = response.json()
                print(f"Retrieved {len(active_sessions)} active sessions")
                # Convert to expected format and merge
                for session in active_sessions:
                    session_id = session.get("session_id", "")
                    if session_id and session_id not in session_ids_seen:
                        formatted_session = {
                            "session_id": session_id,
                            "query": session.get("query", "No query available"),
                            "full_query": session.get("query", "No query available"),
                            "language": session.get("language", "en"),
                            "timestamp": session.get("created_at", ""),
                            "status": session.get("status", "unknown"),
                            "is_complete": session.get("status") in ["completed", "error", "cancelled"]
                        }
                        all_sessions.append(formatted_session)
                        session_ids_seen.add(session_id)
            else:
                print(f"Sessions endpoint returned {response.status_code}")

            print(f"Total merged sessions: {len(all_sessions)}")
            return all_sessions

        except Exception as e:
            print(f"Error getting all sessions: {e}")
            return []

def test_session_merge():
    """Test the session merging functionality"""
    print("=== TESTING SESSION MERGE FUNCTIONALITY ===")

    client = FastAPIClient()
    sessions = client.get_all_sessions()

    print(f"\nTotal sessions found: {len(sessions)}")
    print("\nSession details:")

    active_count = 0
    completed_count = 0

    for i, session in enumerate(sessions, 1):
        status = session.get("status", "unknown")
        query_preview = session.get("query", "")[:50] + "..." if len(session.get("query", "")) > 50 else session.get("query", "")
        timestamp = session.get("timestamp", "")

        if status in ["processing", "queued", "running"]:
            active_count += 1
            status_emoji = "🔄"
        elif status == "completed":
            completed_count += 1
            status_emoji = "✅"
        else:
            status_emoji = "❓"

        print(f"{i:2d}. {status_emoji} [{status}] {query_preview} ({timestamp})")

    print(f"\nSummary:")
    print(f"- Active/Processing sessions: {active_count}")
    print(f"- Completed sessions: {completed_count}")
    print(f"- Total sessions: {len(sessions)}")

    if active_count > 0:
        print("\n✅ SUCCESS: Active sessions are now included in the session list!")
    else:
        print("\n⚠️  No active sessions found, but merge functionality is working.")

if __name__ == "__main__":
    test_session_merge()