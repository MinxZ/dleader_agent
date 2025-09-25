#!/usr/bin/env python3
"""
Quick test script for multi-turn file persistence

A simpler version for quick testing and debugging.
"""

import asyncio
import json
import os
import time
from datetime import datetime
from pathlib import Path

import aiohttp
import pandas as pd


async def quick_multiturn_test():
    """Quick test of multi-turn functionality"""

    server_url = "http://localhost:8001"
    user_id = f"quick_test_{datetime.now().strftime('%H%M%S')}"

    print("="*60)
    print("QUICK MULTI-TURN TEST")
    print(f"Server: {server_url}")
    print(f"User: {user_id}")
    print("="*60)

    async with aiohttp.ClientSession() as session:
        # === TURN 1: Upload data and create plot ===
        print("\n📤 Turn 1: Uploading data and requesting plot...")

        # Create test data
        df = pd.DataFrame({
            'x': [1, 2, 3, 4, 5],
            'y': [2, 4, 6, 8, 10],
            'label': ['A', 'B', 'C', 'D', 'E']
        })
        test_file = Path("/tmp/test_data.csv")
        df.to_csv(test_file, index=False)

        # Create metadata with secret
        metadata = {
            "secret": "HIDDEN-VALUE-123",
            "plot_config": {
                "title": "Test Plot",
                "color": "blue"
            }
        }
        meta_file = Path("/tmp/metadata.json")
        with open(meta_file, 'w') as f:
            json.dump(metadata, f)

        # Submit first turn
        data = aiohttp.FormData()
        data.add_field('message', """
            Read test_data.csv and metadata.json:
            1. Create a line plot of x vs y
            2. Save plot as 'analysis.png'
            3. Extract and report the 'secret' value from metadata
            4. Save a summary as 'turn1_summary.txt'
        """)
        data.add_field('user_id', user_id)
        data.add_field('language', 'en')
        data.add_field('files', open(test_file, 'rb'),
                      filename='test_data.csv',
                      content_type='text/csv')
        data.add_field('files', open(meta_file, 'rb'),
                      filename='metadata.json',
                      content_type='application/json')

        async with session.post(f"{server_url}/chat-queue", data=data) as resp:
            result = await resp.json()
            session_id = result['session_id']
            print(f"✓ Session started: {session_id}")

        # Wait for completion
        print("⏳ Waiting for Turn 1 to complete...")
        start = time.time()
        while time.time() - start < 60:
            async with session.get(f"{server_url}/status/{session_id}",
                                  params={'user_id': user_id}) as resp:
                status = await resp.json()
                if status.get('is_complete'):
                    print(f"✓ Turn 1 completed in {time.time()-start:.1f}s")
                    break
            await asyncio.sleep(2)

        # === DELETE LOCAL FILES ===
        print("\n🗑️  Deleting local files...")
        local_paths = [
            f"session_storage/{session_id}",
            f"chat_sessions/{session_id}",
            f"temp_uploads/{session_id}"
        ]
        for path in local_paths:
            if Path(path).exists():
                print(f"  Deleting: {path}")
                import shutil
                shutil.rmtree(path, ignore_errors=True)

        # === TURN 2: Try to access deleted files ===
        print("\n📥 Turn 2: Attempting to access files from Turn 1...")

        data = aiohttp.FormData()
        data.add_field('session_id', session_id)
        data.add_field('message', """
            Please access the files from Turn 1:
            1. Load 'analysis.png' and describe what you see
            2. Read 'turn1_summary.txt' if it exists
            3. Report the 'secret' value from the original metadata
            4. List all available files from Turn 1

            Explicitly state whether you found each file.
        """)
        data.add_field('user_id', user_id)
        data.add_field('language', 'en')

        async with session.post(f"{server_url}/continue-session", data=data) as resp:
            result = await resp.json()
            turn2_id = result.get('turn_session_id')
            print(f"✓ Turn 2 started: {turn2_id}")

        # Wait for Turn 2
        print("⏳ Waiting for Turn 2 to complete...")
        start = time.time()
        while time.time() - start < 60:
            async with session.get(f"{server_url}/status/{turn2_id}",
                                  params={'user_id': user_id}) as resp:
                status = await resp.json()
                if status.get('is_complete'):
                    print(f"✓ Turn 2 completed in {time.time()-start:.1f}s")

                    # Check results
                    if status.get('json_result'):
                        content = str(status['json_result'].get('content', {}))

                        # Verify secret was found
                        secret_found = 'HIDDEN-VALUE-123' in content
                        files_listed = 'analysis.png' in content or 'test_data.csv' in content

                        print("\n📋 Verification:")
                        print(f"  Secret recovered: {'✓' if secret_found else '✗'}")
                        print(f"  Files accessed: {'✓' if files_listed else '✗'}")

                        if secret_found and files_listed:
                            print("\n✅ SUCCESS: Files were recovered from S3!")
                        else:
                            print("\n⚠️  WARNING: Some files may not have been recovered")
                    break
            await asyncio.sleep(2)

        # Get session metadata
        print("\n📊 Session Metadata:")
        async with session.get(f"{server_url}/multiturn-session/{session_id}",
                              params={'user_id': user_id}) as resp:
            if resp.status == 200:
                metadata = await resp.json()
                print(f"  Total turns: {metadata.get('total_turns', 0)}")
                for turn in metadata.get('turns', []):
                    files = turn.get('files', {})
                    if files:
                        print(f"  Turn {turn['turn_number']} files: {list(files.keys())}")

    print("\n" + "="*60)
    print("Test completed!")
    print("="*60)


if __name__ == "__main__":
    # Check server
    import requests
    try:
        resp = requests.get("http://localhost:8001/health")
        if resp.status_code == 200:
            print("✓ Server is running\n")
            asyncio.run(quick_multiturn_test())
        else:
            print("❌ Server health check failed")
    except requests.ConnectionError:
        print("❌ Cannot connect to server. Start it with:")
        print("  python agent_fastapi_server_multiturn.py")