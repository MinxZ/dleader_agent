#!/usr/bin/env python3
"""
Test script to verify FastAPI connection
"""

import requests

def test_connection(url):
    """Test connection to FastAPI server"""
    print(f"Testing connection to: {url}")

    # Ensure URL has proper protocol
    if not url.startswith(('http://', 'https://')):
        url = f"http://{url}"

    try:
        response = requests.get(f"{url}/health", timeout=5)
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.json()}")
        return response.status_code == 200
    except Exception as e:
        print(f"Connection failed: {e}")
        return False

if __name__ == "__main__":
    # Test different URL formats
    test_urls = [
        "http://localhost:8001",
        "localhost:8001",
        "127.0.0.1:8001",
        "http://127.0.0.1:8001",
        "54.250.164.102:8001",
        "http://54.250.164.102:8001"
    ]

    for url in test_urls:
        print("=" * 50)
        success = test_connection(url)
        print(f"Success: {success}")
        print()