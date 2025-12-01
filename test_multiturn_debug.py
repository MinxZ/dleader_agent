#!/usr/bin/env python3
"""Test multi-turn session to trace file reference bug with debug logging"""

import requests
import time
import json

BASE_URL = "http://localhost:8001"
USER_ID = "debug_test_user"

def start_session(query):
    """Start a new multi-turn session"""
    print(f"\n{'='*80}")
    print(f"STARTING NEW SESSION")
    print(f"{'='*80}")

    response = requests.post(
        f"{BASE_URL}/chat-queue",
        data={
            "message": query,
            "language": "en",
            "user_id": USER_ID,
            "use_template": "false"
        }
    )

    if response.status_code == 200:
        data = response.json()
        session_id = data.get("session_id")
        print(f"✓ Session started: {session_id}")
        return session_id
    else:
        print(f"✗ Failed to start session: {response.status_code}")
        print(response.text)
        return None

def continue_session(session_id, query, turn_num):
    """Continue an existing session"""
    print(f"\n{'='*80}")
    print(f"TURN {turn_num}: CONTINUING SESSION")
    print(f"{'='*80}")

    response = requests.post(
        f"{BASE_URL}/continue-session",
        data={
            "session_id": session_id,
            "message": query,
            "language": "en",
            "user_id": USER_ID,
            "use_template": "false"
        }
    )

    if response.status_code == 200:
        print(f"✓ Turn {turn_num} completed")
        return True
    else:
        print(f"✗ Turn {turn_num} failed: {response.status_code}")
        print(response.text)
        return False

def get_results(session_id, turn_num):
    """Get results for a specific turn"""
    print(f"\nFetching results for turn {turn_num}...")
    response = requests.get(
        f"{BASE_URL}/results/{session_id}",
        params={
            "user_id": USER_ID,
            "turn_number": turn_num
        }
    )

    if response.status_code == 200:
        data = response.json()
        print(f"✓ Results fetched for turn {turn_num}")

        # Show file references
        files = data.get("files", {})
        tp_file = files.get("thinking_process", {}).get("filename", "NONE") if isinstance(files.get("thinking_process"), dict) else "NONE"
        report_file = files.get("final_report", {}).get("filename", "NONE") if isinstance(files.get("final_report"), dict) else "NONE"

        print(f"  Files: TP={tp_file}, Report={report_file}")
        return data
    else:
        print(f"✗ Failed to get results: {response.status_code}")
        return None

def main():
    print("="*80)
    print("MULTI-TURN DEBUG TEST - Tracing Session Load Flow")
    print("="*80)
    print("\nThis test will:")
    print("1. Start a new session (Turn 1)")
    print("2. Continue with Turn 2")
    print("3. Continue with Turn 3")
    print("4. Fetch results for each turn to check file references")
    print("\nWatch /tmp/fastapi_debug3.log for debug output!")

    # Turn 1: Start session
    session_id = start_session("What is 2+2?")
    if not session_id:
        print("\n✗ Test failed - could not start session")
        return

    print("\nWaiting 2 seconds before Turn 2...")
    time.sleep(2)

    # Turn 2: Continue
    if not continue_session(session_id, "What is 3+3?", 2):
        print("\n✗ Test failed - Turn 2 failed")
        return

    print("\nWaiting 2 seconds before Turn 3...")
    time.sleep(2)

    # Turn 3: Continue
    if not continue_session(session_id, "What is 4+4?", 3):
        print("\n✗ Test failed - Turn 3 failed")
        return

    print("\nWaiting 2 seconds before fetching results...")
    time.sleep(2)

    # Fetch results for all turns
    print(f"\n{'='*80}")
    print("FETCHING RESULTS FOR ALL TURNS")
    print(f"{'='*80}")

    results = {}
    for turn in [1, 2, 3]:
        results[turn] = get_results(session_id, turn)

    # Summary
    print(f"\n{'='*80}")
    print("TEST SUMMARY")
    print(f"{'='*80}")
    print(f"Session ID: {session_id}")
    print("\nFile References by Turn:")

    for turn in [1, 2, 3]:
        if results[turn]:
            files = results[turn].get("files", {})
            tp_file = files.get("thinking_process", {}).get("filename", "NONE") if isinstance(files.get("thinking_process"), dict) else "NONE"
            report_file = files.get("final_report", {}).get("filename", "NONE") if isinstance(files.get("final_report"), dict) else "NONE"
            print(f"  Turn {turn}: TP={tp_file}, Report={report_file}")

    # Check for bug
    print(f"\n{'='*80}")
    print("BUG CHECK")
    print(f"{'='*80}")

    turn1_tp = None
    all_same = True

    for turn in [1, 2, 3]:
        if results[turn]:
            files = results[turn].get("files", {})
            tp_file = files.get("thinking_process", {}).get("filename", "NONE") if isinstance(files.get("thinking_process"), dict) else "NONE"

            if turn == 1:
                turn1_tp = tp_file
            elif tp_file != turn1_tp:
                all_same = False
                break

    if all_same and turn1_tp != "NONE":
        print("🐛 BUG DETECTED: All turns have the same file reference!")
        print(f"   All turns reference: {turn1_tp}")
        print("\n   Now check /tmp/fastapi_debug3.log to trace where stale data was loaded!")
    else:
        print("✓ No bug detected - each turn has unique file references")

    print(f"\n{'='*80}")
    print(f"Check debug logs: tail -100 /tmp/fastapi_debug3.log")
    print(f"{'='*80}\n")

if __name__ == "__main__":
    main()
