#!/usr/bin/env python3
"""
Debug script to trace exactly where plot files go
"""
import os
import time
import glob

print("Current working directory:", os.getcwd())
print("\nCreating test plots...")

# Simulate what the agent would do - create plot files
from datetime import datetime
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

# Create test plot files like the agent would
test_files = [
    f"molecule_CC_ethane_{timestamp}.png",
    f"molecule_CCC_propane_{timestamp}.png",
    f"molecular_structures_{timestamp}.svg"
]

for filename in test_files:
    with open(filename, "wb") as f:
        f.write(b"TEST_PLOT_DATA")
    print(f"Created: {filename}")

print("\nFiles in current directory after creation:")
for f in glob.glob("*.png") + glob.glob("*.svg"):
    print(f"  - {f}")

print("\nChecking chat_sessions folders:")
for folder in glob.glob("chat_sessions/*"):
    if os.path.isdir(folder):
        contents = os.listdir(folder)
        if any(f.endswith(('.png', '.svg', '.jpg')) for f in contents):
            print(f"  {folder}: {len(contents)} files")
            for f in contents:
                if f.endswith(('.png', '.svg', '.jpg')):
                    print(f"    - {f}")

# Clean up
print("\nCleaning up test files...")
for filename in test_files:
    if os.path.exists(filename):
        os.remove(filename)
        print(f"Removed: {filename}")