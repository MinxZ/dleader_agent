#!/usr/bin/env python3
"""Test per-turn ZIP creation functionality"""
import requests
import time
import json

BASE_URL = "http://localhost:8001"
USER_ID = "test_turn_zip@test.com"

def create_multiturn_session(message, user_id):
    """Create a new multi-turn session"""
    response = requests.post(
        f"{BASE_URL}/multiturn-chat",
        json={
            "message": message,
            "user_id": user_id,
            "language": "en",
            "turn_type": "execution"
        }
    )
    return response.json()

def add_turn(session_id, message, user_id):
    """Add a new turn to existing session"""
    response = requests.post(
        f"{BASE_URL}/multiturn-chat",
        json={
            "message": message,
            "user_id": user_id,
            "session_id": session_id,
            "language": "en",
            "turn_type": "execution"
        }
    )
    return response.json()

def check_status(session_id, user_id):
    """Check session status"""
    response = requests.get(
        f"{BASE_URL}/check-status",
        params={"session_id": session_id, "user_id": user_id}
    )
    return response.json()

def get_results(session_id, user_id, turn_number=None):
    """Get session results"""
    params = {"user_id": user_id}
    if turn_number:
        params["turn_number"] = turn_number
    response = requests.get(
        f"{BASE_URL}/results/{session_id}",
        params=params
    )
    return response.json()

def wait_for_completion(session_id, user_id, timeout=600):
    """Wait for session to complete"""
    start_time = time.time()
    while time.time() - start_time < timeout:
        status = check_status(session_id, user_id)
        if status.get("status") == "completed":
            print(f"✓ Session completed!")
            return True
        elif status.get("status") == "error":
            print(f"✗ Session failed with error: {status.get('error')}")
            return False
        time.sleep(2)
    print(f"✗ Timeout waiting for completion")
    return False

def main():
    print("=" * 80)
    print("Testing Per-Turn ZIP Creation")
    print("=" * 80)

    # Turn 1: Simple calculation
    print("\n[Turn 1] Creating session with query: '1+1'")
    result = create_multiturn_session("1+1", USER_ID)
    session_id = result.get("session_id")
    print(f"Session ID: {session_id}")

    # Wait for Turn 1 to complete
    if not wait_for_completion(session_id, USER_ID):
        print("Turn 1 failed!")
        return

    # Check Turn 1 results
    print("\n[Turn 1] Checking results...")
    turn1_results = get_results(session_id, USER_ID, turn_number=1)
    turn1_files = turn1_results.get("files", {})

    print(f"Turn 1 files:")
    for key, value in turn1_files.items():
        if isinstance(value, dict):
            filename = value.get("filename", "N/A")
            url = value.get("url", "N/A")
            has_url = "✓" if url and url != "N/A" else "✗"
            print(f"  {has_url} {key}: {filename}")
            if key == "turn_zip":
                print(f"      → Turn ZIP found: {filename}")
        else:
            print(f"  - {key}: {value}")

    # Turn 2: Plot generation (creates images)
    print("\n[Turn 2] Adding query: 'plot tpsa for drugs'")
    result = add_turn(session_id, "plot tpsa for drugs", USER_ID)

    # Wait for Turn 2 to complete
    if not wait_for_completion(session_id, USER_ID):
        print("Turn 2 failed!")
        return

    # Check Turn 2 results
    print("\n[Turn 2] Checking results...")
    turn2_results = get_results(session_id, USER_ID, turn_number=2)
    turn2_files = turn2_results.get("files", {})

    print(f"Turn 2 files:")
    for key, value in turn2_files.items():
        if isinstance(value, dict):
            filename = value.get("filename", "N/A")
            url = value.get("url", "N/A")
            has_url = "✓" if url and url != "N/A" else "✗"
            print(f"  {has_url} {key}: {filename}")
            if key == "turn_zip":
                print(f"      → Turn ZIP found: {filename}")
        else:
            print(f"  - {key}: {value}")

    # Check local chat_zips directory for turn ZIPs
    print("\n[Local Files] Checking chat_zips directory...")
    import os
    chat_zips_dir = "/home/ubuntu/dleader_agent_demo/chat_zips"
    if os.path.exists(chat_zips_dir):
        base_session_id = session_id.split("_turn_")[0] if "_turn_" in session_id else session_id
        turn_zips = [f for f in os.listdir(chat_zips_dir) if base_session_id[:12] in f and "turn_" in f]
        if turn_zips:
            print(f"Found {len(turn_zips)} turn ZIP(s):")
            for zip_file in sorted(turn_zips):
                size_mb = os.path.getsize(os.path.join(chat_zips_dir, zip_file)) / 1024 / 1024
                print(f"  ✓ {zip_file} ({size_mb:.2f} MB)")
        else:
            print("  ✗ No turn ZIPs found")
    else:
        print("  ✗ chat_zips directory not found")

    print("\n" + "=" * 80)
    print("Test Summary:")
    print("=" * 80)

    turn1_has_zip = "turn_zip" in turn1_files
    turn2_has_zip = "turn_zip" in turn2_files

    print(f"{'✓' if turn1_has_zip else '✗'} Turn 1 has turn_zip in /results response")
    print(f"{'✓' if turn2_has_zip else '✗'} Turn 2 has turn_zip in /results response")

    if turn1_has_zip and turn2_has_zip:
        print("\n✓ Per-turn ZIP creation is working!")
    else:
        print("\n✗ Per-turn ZIP creation has issues")

    print(f"\nSession ID for manual inspection: {session_id}")

if __name__ == "__main__":
    main()
