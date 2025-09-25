#!/usr/bin/env python3
"""
Test the simplified interface fix
"""
import subprocess
import sys
import time

def test_interface_startup():
    """Test that the interface can start with different URL formats"""

    test_cases = [
        ("http://localhost:8001", 7861),
        ("localhost:8001", 7862),
        ("54.250.164.102:8001", 7863),
        ("http://54.250.164.102:8001", 7864),
    ]

    for url, port in test_cases:
        print(f"\nTesting with URL: {url} on port {port}")

        # Start the interface
        process = subprocess.Popen(
            ["python", "agent_gradio_simple.py", "--server_port", str(port), "--fastapi_url", url],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )

        # Wait a bit for startup
        time.sleep(3)

        # Check if process is still running
        poll = process.poll()

        if poll is None:
            # Process is running
            print(f"✅ Interface started successfully with {url}")
            process.terminate()
            time.sleep(1)
            process.kill()
        else:
            # Process exited
            stdout, stderr = process.communicate()
            print(f"❌ Interface failed to start with {url}")
            if stderr:
                print(f"   Error: {stderr[:200]}")
            return False

    return True

if __name__ == "__main__":
    print("Testing Simplified Interface Startup")
    print("="*50)

    success = test_interface_startup()

    if success:
        print("\n✅ All tests passed! The interface works with all URL formats.")
        sys.exit(0)
    else:
        print("\n❌ Some tests failed.")
        sys.exit(1)