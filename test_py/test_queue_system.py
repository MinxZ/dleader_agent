#!/usr/bin/env python3
"""
Test script for the FastAPI queue system
Tests multiple concurrent requests to ensure queue works properly
"""

import asyncio
import aiohttp
import time
import json
from typing import List

# Server configuration
SERVER_URL = "http://localhost:8002"

async def send_chat_request(session: aiohttp.ClientSession, message: str, request_id: int) -> dict:
    """Send a chat request and wait for completion"""
    start_time = time.time()

    # Send request to queue
    async with session.post(f"{SERVER_URL}/chat-queue", json={
        "message": f"{message} (Request #{request_id})",
        "language": "en"
    }) as response:
        if response.status != 200:
            return {"error": f"Failed to queue request: {response.status}"}

        queue_response = await response.json()
        session_id = queue_response["session_id"]
        print(f"Request #{request_id}: Queued with session_id {session_id}, position {queue_response['position']}")

    # Poll for completion
    while True:
        async with session.get(f"{SERVER_URL}/status/{session_id}") as response:
            if response.status != 200:
                return {"error": f"Failed to get status: {response.status}"}

            status_response = await response.json()

            if status_response["is_complete"]:
                end_time = time.time()
                duration = end_time - start_time

                if status_response.get("error"):
                    print(f"Request #{request_id}: FAILED after {duration:.1f}s - {status_response['error']}")
                    return {"success": False, "duration": duration, "error": status_response["error"]}
                else:
                    print(f"Request #{request_id}: COMPLETED after {duration:.1f}s")
                    return {"success": True, "duration": duration, "session_id": session_id}

            # Print status updates
            if "queue_position" in status_response:
                print(f"Request #{request_id}: Position {status_response['queue_position']} in queue (ETA: {status_response['estimated_wait_time']}s)")
            elif status_response["status"] == "processing":
                print(f"Request #{request_id}: Processing...")

            await asyncio.sleep(2)  # Check every 2 seconds

async def test_queue_system():
    """Test the queue system with multiple concurrent requests"""
    print("=" * 60)
    print("Testing FastAPI Queue System")
    print("=" * 60)

    # Test messages
    test_messages = [
        "Calculate 2+2 and explain your reasoning",
        "Generate a simple Python function to find prime numbers",
        "Explain the concept of machine learning in simple terms",
        "Write a haiku about programming",
        "Calculate the fibonacci sequence up to 10 numbers"
    ]

    async with aiohttp.ClientSession() as session:
        # Check server health
        try:
            async with session.get(f"{SERVER_URL}/health") as response:
                if response.status == 200:
                    health = await response.json()
                    print(f"Server Status: {health['status']}")
                    print(f"Queue Size: {health['queue_size']}")
                    print(f"Currently Processing: {health['is_processing']}")
                    print("-" * 60)
                else:
                    print("❌ Server not responding correctly")
                    return
        except Exception as e:
            print(f"❌ Cannot connect to server: {e}")
            print("Make sure the server is running on http://localhost:8001")
            return

        # Send multiple concurrent requests
        print(f"Sending {len(test_messages)} concurrent requests...")
        start_time = time.time()

        tasks = []
        for i, message in enumerate(test_messages, 1):
            task = asyncio.create_task(send_chat_request(session, message, i))
            tasks.append(task)

        # Wait for all requests to complete
        results = await asyncio.gather(*tasks, return_exceptions=True)

        end_time = time.time()
        total_duration = end_time - start_time

        # Analyze results
        print("\n" + "=" * 60)
        print("RESULTS SUMMARY")
        print("=" * 60)

        successful = 0
        failed = 0
        total_processing_time = 0

        for i, result in enumerate(results, 1):
            if isinstance(result, Exception):
                print(f"Request #{i}: EXCEPTION - {result}")
                failed += 1
            elif result.get("success"):
                successful += 1
                total_processing_time += result["duration"]
                print(f"Request #{i}: ✅ SUCCESS - {result['duration']:.1f}s")
            else:
                failed += 1
                print(f"Request #{i}: ❌ FAILED - {result.get('error', 'Unknown error')}")

        print(f"\nOverall Statistics:")
        print(f"  • Successful: {successful}/{len(test_messages)}")
        print(f"  • Failed: {failed}/{len(test_messages)}")
        print(f"  • Total Wall Time: {total_duration:.1f}s")
        print(f"  • Average Processing Time: {total_processing_time/max(successful, 1):.1f}s")
        print(f"  • Queue Efficiency: {total_processing_time/total_duration:.1%}")

        if successful == len(test_messages):
            print("\n🎉 All requests completed successfully!")
            print("✅ Queue system is working correctly")
        else:
            print(f"\n⚠️  {failed} requests failed")

if __name__ == "__main__":
    asyncio.run(test_queue_system())