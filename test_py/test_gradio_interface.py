"""
Test script for the Gradio preprocessing interface
"""

import sys
import os

# Add current directory to path
sys.path.insert(0, os.getcwd())

try:
    from gradio_preprocessing_interface import create_interface
    print("✅ Interface imports successful")
    
    # Create the interface
    demo = create_interface()
    print("✅ Interface created successfully")
    
    print("\n🚀 Gradio preprocessing interface is ready!")
    print("📝 Features available:")
    print("   • Data upload and inspection")
    print("   • Quality issue detection")
    print("   • Automated preprocessing pipeline")
    print("   • Agent-powered custom preprocessing")
    print("\n💡 To launch the interface, run:")
    print("   python gradio_preprocessing_interface.py")
    
except ImportError as e:
    print(f"❌ Import error: {e}")
    print("Make sure all dependencies are installed")
except Exception as e:
    print(f"❌ Error creating interface: {e}")