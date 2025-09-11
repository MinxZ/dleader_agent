#!/usr/bin/env python3
"""
Patent Examples Extractor

This program extracts examples from the patent JSON file and saves them to separate files.
It focuses on the properties: Toxicity, Binding affinity, Enzyme stability, Delivery, 
Reduce immune stimulation, Aqueous solubility.

Based on minimal_image_agent_example.py structure for analyzing patent data.
"""

import json
import os
import re
from pathlib import Path

def load_patent_data(file_path):
    """Load patent JSON data from file."""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        print(f"✅ Loaded patent data from {file_path}")
        return data
    except Exception as e:
        print(f"❌ Error loading patent data: {e}")
        return None

def extract_examples(data):
    """Extract all keys that start with 'Example' and their content."""
    examples = {}
    
    for key, value in data.items():
        if key.startswith("Example"):
            examples[key] = value
            print(f"📝 Found: {key}")
    
    return examples

def analyze_for_properties(text, target_properties):
    """Analyze text for mentions of target properties."""
    found_properties = []
    text_lower = text.lower()
    
    for prop in target_properties:
        if prop.lower() in text_lower:
            found_properties.append(prop)
    
    return found_properties

def save_examples_to_files(examples, output_dir, target_properties):
    """Save each example to a separate file with analysis."""
    
    # Create output directory
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    
    summary_data = []
    
    for example_key, content in examples.items():
        # Extract example number for filename
        example_num_match = re.search(r'Example (\d+)', example_key)
        if example_num_match:
            example_num = example_num_match.group(1)
            filename = f"example_{example_num}.txt"
        else:
            # Fallback filename
            filename = re.sub(r'[^\w\s-]', '', example_key.replace(' ', '_').lower()) + '.txt'
        
        filepath = os.path.join(output_dir, filename)
        
        # Analyze content for target properties
        found_properties = analyze_for_properties(content, target_properties)
        
        # Prepare file content - only the raw content
        file_content = content
        
        # Save to file
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(file_content)
        
        print(f"📄 Saved: {filename} (Properties found: {len(found_properties)})")
        
        # Add to summary
        summary_data.append({
            'example': example_key,
            'filename': filename,
            'content_length': len(content),
            'properties_found': found_properties
        })
    
    return summary_data

def create_summary_report(summary_data, target_properties, output_dir):
    """Create a summary report of all examples."""
    
    summary_file = os.path.join(output_dir, "examples_summary.md")
    
    content = f"""# Patent Examples Analysis Summary

## Target Properties
- {chr(10).join(f"- {prop}" for prop in target_properties)}

## Examples Analysis

"""
    
    for item in summary_data:
        content += f"""### {item['example']}
- **File**: `{item['filename']}`
- **Content Length**: {item['content_length']} characters
- **Properties Found**: {', '.join(item['properties_found']) if item['properties_found'] else 'None'}

"""
    
    # Overall statistics
    total_examples = len(summary_data)
    examples_with_properties = sum(1 for item in summary_data if item['properties_found'])
    
    content += f"""## Summary Statistics
- **Total Examples**: {total_examples}
- **Examples with Target Properties**: {examples_with_properties}
- **Coverage Rate**: {examples_with_properties/total_examples*100:.1f}%

## Properties Distribution
"""
    
    # Count property occurrences
    property_counts = {}
    for item in summary_data:
        for prop in item['properties_found']:
            property_counts[prop] = property_counts.get(prop, 0) + 1
    
    for prop in target_properties:
        count = property_counts.get(prop, 0)
        content += f"- **{prop}**: {count} examples\n"
    
    with open(summary_file, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print(f"📊 Summary report saved: examples_summary.md")
    return summary_file

def main():
    """Main function to extract and analyze patent examples."""
    
    print("🧬 Patent Examples Extractor")
    print("=" * 50)
    
    # Configuration
    patent_file = "/home/ubuntu/work/dleader_agent/data/dleader_agent_data/patent_raw/US20220340900A1.sections.json"
    output_dir = "/home/ubuntu/work/dleader_agent/extracted_examples"
    
    # Target properties from user selection
    target_properties = [
        "Toxicity",
        "Binding affinity", 
        "Enzyme stability",
        "Delivery",
        "Reduce immune stimulation",
        "Aqueous solubility"
    ]
    
    # Load patent data
    data = load_patent_data(patent_file)
    if not data:
        return
    
    # Extract examples
    examples = extract_examples(data)
    if not examples:
        print("❌ No examples found in patent data")
        return
    
    print(f"📋 Found {len(examples)} examples")
    
    # Save examples to files
    summary_data = save_examples_to_files(examples, output_dir, target_properties)
    
    # Create summary report
    create_summary_report(summary_data, target_properties, output_dir)
    
    # Final summary
    print("\n" + "=" * 50)
    print("✅ EXTRACTION COMPLETE")
    print("=" * 50)
    print(f"📁 Output Directory: {output_dir}")
    print(f"📄 Examples Extracted: {len(examples)}")
    print(f"🎯 Target Properties: {len(target_properties)}")
    print("=" * 50)

if __name__ == "__main__":
    main()