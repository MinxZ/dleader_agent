"""
Example: Minimal Agent Configuration for Image Analysis Only

This example shows how to configure the dleader_agent agent to use only 
image analysis tools without default data lake and packages.
"""

import time

from dleader_agent.agent.a1 import A1


def create_minimal_image_agent():
    """Create an agent configured only for image analysis tasks."""
    
    # Initialize agent without downloading default data lake
    agent = A1(
        use_tool_retriever=True,
        download_data_lake=False, 
        llm='claude-sonnet-4-5-20250929'
    )
    
    # Clear default data lake to avoid distractions
    agent.data_lake_dict = {}
    
    # Keep only essential packages for image processing
    essential_packages = {
        'requests': 'HTTP library for downloading images from URLs',
        'base64': 'Encoding/decoding binary data',
        'PIL': 'Python Imaging Library for image processing',
        'cv2': 'OpenCV for computer vision tasks'
    }
    agent.library_content_dict = essential_packages
    
    # Filter module2api to keep only support tools (contains image function)
    image_modules = {
        'dleader_agent.tool.support_tools': agent.module2api.get('dleader_agent.tool.support_tools', []),
        'dleader_agent.tool.literature': agent.module2api.get('dleader_agent.tool.literature', [])
    }
    agent.module2api = image_modules
    
    print("✅ Configured minimal agent with:")
    print(f"   📦 {len(essential_packages)} essential packages")
    print(f"   🔧 {len(image_modules.get('dleader_agent.tool.support_tools', []))} support tools (including image analysis)")
    print(f"   📊 {len(agent.data_lake_dict)} data lake items (empty)")
    
    return agent



def example_url_image_analysis():
    """Example using image URL analysis with different modes."""
    
    print("🚀 URL Image Analysis Example")
    print("="*50)
    
    # Create minimal agent
    agent = create_minimal_image_agent()
    
#     for i in range(1, 2):
#         file_path = f'extracted_examples/example_{i}.txt'
#         log, result = agent.go(f"""summarize the {file_path} if there are image url in it, use image analysis tools to transform the url into text first. You can find the crossponding url of image in /home/ubuntu/work/dleader_agent/data/dleader_agent_data/patent_raw/US20220340900A1_images.json.
# For each Modification types(Name, identity, Modification types classification (backbone, sugar, terminal, and conjugates or others))
# We need sequence(identity, and extact AUCG or ATCG sequence from image or text before <---> after pairwise) and <---> Collect all related information about the sequence and Modification types <----> summarize Effect (Properties data)  with original text. 
# for example, we have Toxicity, Binding affinity, Enzyme stability, Delivery, Reduce immune stimulation, Aqueous solubility, you need to think about the property related to them, for example, stability is tm shift, …
# """)
    for i in range(1, 2):
        file_path = f'extracted_examples/example_{i}.txt'
        log, result = agent.go(f"""summarize the {file_path} if there are image url in it, use image analysis tools to transform the url into text first. You can find the crossponding url of image in /home/ubuntu/work/dleader_agent/data/dleader_agent_data/patent_raw/US20220340900A1_images.json.
For each Modification types(Name, identity, Modification types classification (backbone, sugar, terminal, and conjugates or others))
We need sequence(identity, and extact AUCG or ATCG sequence from image or text before <---> after pairwise) and <---> Collect all related information about the sequence and Modification types <----> summarize Effect (Properties data)  with original text. 
for example, we have Toxicity, Binding affinity, Enzyme stability, Delivery, Reduce immune stimulation, Aqueous solubility, you need to think about the property related to them, for example, stability is tm shift, …
""")
    
        print("📋 Agent Response:")
        print(log, result)
        time.sleep(60)
        with open(f'analysis_results/analysis_log_{i}.txt', 'w') as f:
            f.write(str(log))
        with open(f'analysis_results/analysis_result_{i}.txt', 'w') as f:
            f.write(str(result))
        
    return log, result

if __name__ == "__main__":
    print("🧬 Minimal dleader_agent Agent - Image Analysis Only")
    print("="*60)
    example_url_image_analysis()
    
    # # Run examples
    # examples = [
    #     # ("Local Image Analysis", example_local_image_analysis),
    #     ("URL Image Analysis", example_url_image_analysis), 
    #     # ("Text Extraction (OCR)", example_text_extraction),
    # ]
    
    # results = {}
    
    # for name, example_func in examples:
    #     try:
    #         print(f"\n🔄 Running: {name}")
    #         log, result = example_func()
    #         if log and result:
    #             results[name] = {"status": "success"}
    #             print(f"✅ Completed: {name}")
    #         else:
    #             results[name] = {"status": "skipped"}
    #             print(f"⏭️ Skipped: {name}")
    #     except Exception as e:
    #         print(f"❌ Error in {name}: {str(e)}")
    #         results[name] = {"status": "failed", "error": str(e)}
    
    # # Summary
    # print("\n" + "="*60)
    # print("📊 EXECUTION SUMMARY")
    # print("="*60)
    
    # for name, result in results.items():
    #     status_icons = {"success": "✅", "failed": "❌", "skipped": "⏭️"}
    #     icon = status_icons.get(result["status"], "❓")
    #     print(f"{icon} {name}")
    #     if "error" in result:
    #         print(f"   └─ Error: {result['error']}")
    
    # print("\n🔧 Image Function Usage:")
    # print("   • read_and_summarize_image(image_source, mode, prompt, model)")
    # print("   • Modes: 'general', 'scientific', 'medical', 'data_viz', 'text_extraction', 'custom'")
    # print("   • Supports both local paths and URLs")
    # print("   • Uses get_llm() for flexible model selection")
    # print("   • Custom prompts override mode-based analysis")
    
    # print("\n💡 Usage Pattern:")
    # print("   ```python")
    # print("   from dleader_agent.tool.support_tools import read_and_summarize_image")
    # print("   ")
    # print("   # Local file")
    # print("   result = read_and_summarize_image('./image.jpg', mode='scientific')")
    # print("   ")
    # print("   # URL with custom model")
    # print("   result = read_and_summarize_image('https://...', mode='medical', model='gpt-4o')")
    # print("   ")
    # print("   # Custom prompt")
    # print("   result = read_and_summarize_image(url, prompt='Identify all species in this image')")
    # print("   ```")