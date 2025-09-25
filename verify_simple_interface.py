#!/usr/bin/env python3
"""
Quick verification that the simplified interface can be imported and created
"""
import sys

try:
    from agent_gradio_simple import create_interface

    # Try to create the interface
    demo = create_interface("http://localhost:8001")

    if demo is None:
        print("❌ ERROR: create_interface() returned None")
        sys.exit(1)
    else:
        print("✅ SUCCESS: Interface created successfully")
        print(f"   Type: {type(demo)}")
        print(f"   Interface is ready to launch")
        sys.exit(0)

except Exception as e:
    print(f"❌ ERROR: {e}")
    sys.exit(1)