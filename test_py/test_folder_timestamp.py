#!/usr/bin/env python3
"""
Test to understand folder timestamp behavior
"""
import os
import time
from datetime import datetime

# Create a folder
folder_name = "test_timestamp_folder"
os.makedirs(folder_name, exist_ok=True)

# Record creation time
creation_time = os.path.getctime(folder_name)
modification_time = os.path.getmtime(folder_name)

print(f"Folder created: {folder_name}")
print(f"Creation time: {datetime.fromtimestamp(creation_time)}")
print(f"Modification time: {datetime.fromtimestamp(modification_time)}")

# Wait a bit
time.sleep(2)

# Create a file inside the folder
file_path = os.path.join(folder_name, "test_file.txt")
with open(file_path, 'w') as f:
    f.write("test content")

# Check times again
new_creation_time = os.path.getctime(folder_name)
new_modification_time = os.path.getmtime(folder_name)

print(f"\nAfter creating file inside:")
print(f"Creation time: {datetime.fromtimestamp(new_creation_time)}")
print(f"Modification time: {datetime.fromtimestamp(new_modification_time)}")
print(f"Modification time changed: {new_modification_time > modification_time}")

# Clean up
import shutil
shutil.rmtree(folder_name)