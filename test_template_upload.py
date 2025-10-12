#!/usr/bin/env python3
"""
Test script to upload workflow templates to the FastAPI server (MongoDB)
"""

import requests
import json

# Server URL (adjust if needed)
SERVER_URL = "http://localhost:8001"

# Load templates from JSON file
with open('/home/ubuntu/dleader_agent/templates/workflow_templates.json', 'r', encoding='utf-8') as f:
    template_data = json.load(f)

print("=" * 60)
print("Testing Template Upload API (MongoDB Cloud Storage)")
print("=" * 60)

# Test 1: Upload templates to MongoDB
print("\n1. Uploading templates to MongoDB...")
response = requests.post(
    f"{SERVER_URL}/upload-template",
    json=template_data,
    headers={"Content-Type": "application/json"}
)

print(f"Status Code: {response.status_code}")
print(f"Response: {json.dumps(response.json(), indent=2)}")

if response.status_code == 200:
    print("✅ Templates uploaded successfully to MongoDB!")
else:
    print("❌ Upload failed!")
    print(f"Error: {response.text}")
    exit(1)

# Test 2: Retrieve templates from MongoDB
print("\n2. Retrieving templates from MongoDB...")
response = requests.get(f"{SERVER_URL}/templates")

print(f"Status Code: {response.status_code}")
result = response.json()
print(f"Total templates: {result.get('total', 0)}")
print(f"Data source: {result.get('source', 'unknown')}")

if response.status_code == 200:
    if result.get('source') == 'mongodb':
        print("✅ Templates retrieved successfully from MongoDB!")
    elif result.get('source') == 'local_backup':
        print("⚠️  Templates retrieved from local backup (MongoDB unavailable)")
    else:
        print("⚠️  No templates found")

    print("\nTemplate Titles:")
    for i, template in enumerate(result.get('templates', []), 1):
        print(f"  {i}. {template['title']} - {template['running_time']} ({template['tools']} tools)")
else:
    print("❌ Retrieval failed!")
    print(f"Error: {response.text}")
    exit(1)

print("\n" + "=" * 60)
print("All tests passed! ✅")
print("=" * 60)
print("\nNote: Templates are stored in MongoDB (cloud) with local backup")
print("This ensures data persists across ECS container restarts")
