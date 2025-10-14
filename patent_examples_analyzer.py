#!/usr/bin/env python3
"""
Patent Examples Analyzer

This program analyzes extracted patent examples using the dleader_agent agent,
referencing the structure from minimal_image_agent_example.py.
It focuses on the properties: Toxicity, Binding affinity, Enzyme stability, 
Delivery, Reduce immune stimulation, Aqueous solubility.

Based on example_url_image_analysis function from minimal_image_agent_example.py
"""

import os
import re
from pathlib import Path

from dleader_agent.agent.a1 import A1


def create_minimal_image_agent():
    """Create an agent configured for analysis tasks - from minimal_image_agent_example.py"""
    
    # Initialize agent without downloading default data lake
    agent = A1(
        use_tool_retriever=True,
        download_data_lake=False, 
        llm='claude-sonnet-4-5-20250929'
    )
    
    # Clear default data lake to avoid distractions
    agent.data_lake_dict = {}
    
    # Keep only essential packages for processing
    essential_packages = {
        'requests': 'HTTP library for downloading images from URLs',
        'base64': 'Encoding/decoding binary data',
        'PIL': 'Python Imaging Library for image processing',
        'cv2': 'OpenCV for computer vision tasks'
    }
    agent.library_content_dict = essential_packages
    
    # Filter module2api to keep only support tools (contains image function)
    image_modules = {
        'dleader_agent.tool.support_tools': agent.module2api.get('dleader_agent.tool.support_tools', [])
    }
    agent.module2api = image_modules
    
    print("✅ Configured minimal agent with:")
    print(f"   📦 {len(essential_packages)} essential packages")
    print(f"   🔧 {len(image_modules.get('dleader_agent.tool.support_tools', []))} support tools (including image analysis)")
    print(f"   📊 {len(agent.data_lake_dict)} data lake items (empty)")
    
    return agent


def load_example_content(examples_dir):
    """Load content from all example files."""
    examples_data = {}
    
    if not os.path.exists(examples_dir):
        print(f"❌ Examples directory not found: {examples_dir}")
        return examples_data
    
    for filename in os.listdir(examples_dir):
        if filename.startswith('example_') and filename.endswith('.txt'):
            filepath = os.path.join(examples_dir, filename)
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read()
                examples_data[filename] = content
                print(f"📄 Loaded: {filename} ({len(content)} characters)")
            except Exception as e:
                print(f"❌ Error loading {filename}: {e}")
    
    return examples_data


def extract_image_urls(content):
    """Extract image URLs from content."""
    # Look for patterns like [Image](url) or direct URLs to images
    url_patterns = [
        r'\[Image\]\(([^)]+)\)',  # Markdown image format
        r'https?://[^\s<>"]+\.(?:png|jpg|jpeg|gif|svg)',  # Direct image URLs
        r'patentimages\.storage\.googleapis\.com[^\s<>"]*'  # Patent image URLs
    ]
    
    urls = []
    for pattern in url_patterns:
        matches = re.findall(pattern, content, re.IGNORECASE)
        urls.extend(matches)
    
    return list(set(urls))  # Remove duplicates


def analyze_modification_types(agent, content, example_name):
    """Analyze modification types (Name, identity)"""
    
    prompt = f"""Analyze this patent example content to identify and extract modification types with their names and identities.

CONTENT TO ANALYZE:
{content}

INSTRUCTIONS:
1. Identify all modification types mentioned (e.g., substitutions, deletions, insertions, chemical modifications)
2. For each modification type, extract:
   - Name of the modification
   - Identity/description of what is being modified
   - Position information if available
   - Type of modification (amino acid, nucleotide, chemical group, etc.)
3. Present results in a structured format:
   MODIFICATION_TYPE: [type]
   NAME: [specific name]
   IDENTITY: [what is being modified]
   POSITION: [if available]
   DESCRIPTION: [additional details]

Please be thorough in identifying all modification types and their characteristics."""
    
    try:
        log, result = agent.go(prompt)
        return {'modification_analysis': result, 'log': log}
    except Exception as e:
        return {'modification_analysis': f"Error: {str(e)}", 'log': None}


def analyze_modification_to_sequence_mapping(agent, content, example_name):
    """Analyze modification types to sequence identity mapping"""
    
    prompt = f"""Analyze this patent example content to map modification types to specific sequences and their identities.

CONTENT TO ANALYZE:
{content}

INSTRUCTIONS:
1. Identify all sequences mentioned (amino acid sequences, nucleotide sequences, etc.)
2. For each sequence, determine:
   - Sequence identity (name, ID, or designation)
   - Associated modification types
   - Original sequence if provided
   - Modified sequence if provided
3. Create mappings between modification types and sequence identities
4. Present results in structured format:
   SEQUENCE_ID: [identifier]
   SEQUENCE_TYPE: [protein, DNA, RNA, etc.]
   ORIGINAL_SEQUENCE: [if available]
   MODIFICATION_TYPE: [type of modification]
   MODIFIED_SEQUENCE: [if available]
   RELATIONSHIP: [how modification relates to sequence]

Please extract all sequence-modification relationships."""
    
    try:
        log, result = agent.go(prompt)
        return {'sequence_modification_mapping': result, 'log': log}
    except Exception as e:
        return {'sequence_modification_mapping': f"Error: {str(e)}", 'log': None}


def analyze_sequence_pairwise_comparison(agent, content, example_name):
    """Analyze sequence before/after pairwise identity comparisons"""
    
    prompt = f"""Analyze this patent example content to perform pairwise comparisons between original and modified sequences.

CONTENT TO ANALYZE:
{content}

INSTRUCTIONS:
1. Identify pairs of sequences (before and after modification)
2. For each sequence pair, analyze:
   - Original sequence (before modification)
   - Modified sequence (after modification)
   - Sequence identity percentage
   - Specific differences (position, original residue, new residue)
   - Length changes
   - Functional implications of changes
3. Present pairwise comparisons in structured format:
   PAIR_ID: [identifier]
   ORIGINAL_SEQUENCE: [before sequence]
   MODIFIED_SEQUENCE: [after sequence]
   IDENTITY_PERCENTAGE: [if calculable]
   DIFFERENCES: [list of specific changes]
   FUNCTIONAL_IMPACT: [predicted or stated effects]

Focus on extracting specific sequence pairs and their comparative analysis."""
    
    try:
        log, result = agent.go(prompt)
        return {'pairwise_analysis': result, 'log': log}
    except Exception as e:
        return {'pairwise_analysis': f"Error: {str(e)}", 'log': None}


def analyze_sequence_to_effects(agent, content, example_name):
    """Analyze sequence pairwise comparisons to effect properties"""
    
    prompt = f"""Analyze this patent example content to identify relationships between sequence changes and their effects on properties.

CONTENT TO ANALYZE:
{content}

INSTRUCTIONS:
1. Identify sequence modifications and their corresponding effects on properties
2. For each sequence change, determine:
   - Specific sequence alteration
   - Property affected (toxicity, binding affinity, stability, etc.)
   - Direction of effect (increase/decrease/improvement/reduction)
   - Quantitative data if available
   - Mechanism of action if described
3. Present sequence-to-effect relationships:
   SEQUENCE_CHANGE: [description of modification]
   AFFECTED_PROPERTY: [specific property]
   EFFECT_DIRECTION: [increase/decrease/improve/reduce]
   QUANTITATIVE_DATA: [numerical values if available]
   MECHANISM: [how the change causes the effect]
   EVIDENCE: [experimental data or reasoning provided]

Focus on establishing clear cause-and-effect relationships between sequence modifications and property changes."""
    
    try:
        log, result = agent.go(prompt)
        return {'sequence_effects_analysis': result, 'log': log}
    except Exception as e:
        return {'sequence_effects_analysis': f"Error: {str(e)}", 'log': None}


def analyze_example_with_agent(agent, example_name, content, target_properties):
    """Analyze a single example using the agent - enhanced with new analysis types"""
    
    print(f"\n🔄 Analyzing: {example_name}")
    print("="*60)
    
    # Extract any image URLs
    image_urls = extract_image_urls(content)
    
    # Prepare analysis prompt for original properties
    properties_str = ", ".join(target_properties)
    
    if image_urls:
        image_info = "\n".join([f"- {url}" for url in image_urls])
        prompt = f"""Please analyze this patent example content focusing on these specific properties: {properties_str}

CONTENT TO ANALYZE:
{content}

IMAGE URLS FOUND:
{image_info}

INSTRUCTIONS:
1. If there are image URLs, use image analysis tools to transform them into text first
2. Focus specifically on these properties: {properties_str}
3. For each property, indicate:
   - Whether it's mentioned or discussed
   - What specific information is provided
   - Any quantitative data or results
4. Provide a structured summary of findings for each property
5. If images contain relevant data (tables, graphs, charts), extract and analyze that information
6. if there are sequesnce data in image, extract them, or if in text, extract them and show it in analysis
7. other than those properties, extract anything you think should be report 
8. compare the original sequence, and modified one if exist.
9. save the sequense in the final analysis

Please be thorough and specific in identifying any mentions or implications related to these properties."""
    else:
        prompt = f"""Please analyze this patent example content focusing on these specific properties: {properties_str}

CONTENT TO ANALYZE:
{content}

INSTRUCTIONS:
1. Focus specifically on these properties: {properties_str}
2. For each property, indicate:
   - Whether it's mentioned or discussed
   - What specific information is provided
   - Any quantitative data or results
3. Provide a structured summary of findings for each property
4. Look for indirect references or implications related to these properties

Please be thorough and specific in identifying any mentions or implications related to these properties."""
    
    try:
        # Original analysis
        log, result = agent.go(prompt)
        print("📋 Original Properties Analysis:")
        print(result)
        
        # New analysis types
        print("\n🔬 Performing additional analyses...")
        
        # 1. Modification types analysis
        modification_analysis = analyze_modification_types(agent, content, example_name)
        print("✅ Completed modification types analysis")
        
        # 2. Modification to sequence mapping
        sequence_mapping = analyze_modification_to_sequence_mapping(agent, content, example_name)
        print("✅ Completed modification-sequence mapping")
        
        # 3. Sequence pairwise comparison
        pairwise_analysis = analyze_sequence_pairwise_comparison(agent, content, example_name)
        print("✅ Completed pairwise sequence analysis")
        
        # 4. Sequence to effects analysis
        effects_analysis = analyze_sequence_to_effects(agent, content, example_name)
        print("✅ Completed sequence-effects analysis")
        
        return {
            'example_name': example_name,
            'content_length': len(content),
            'image_urls_found': len(image_urls),
            'image_urls': image_urls,
            'analysis_result': result,
            'modification_analysis': modification_analysis['modification_analysis'],
            'sequence_modification_mapping': sequence_mapping['sequence_modification_mapping'],
            'pairwise_analysis': pairwise_analysis['pairwise_analysis'],
            'sequence_effects_analysis': effects_analysis['sequence_effects_analysis'],
            'log': log
        }
        
    except Exception as e:
        print(f"❌ Error analyzing {example_name}: {e}")
        return {
            'example_name': example_name,
            'content_length': len(content),
            'image_urls_found': len(image_urls),
            'image_urls': image_urls,
            'analysis_result': f"Error: {str(e)}",
            'modification_analysis': f"Error: {str(e)}",
            'sequence_modification_mapping': f"Error: {str(e)}",
            'pairwise_analysis': f"Error: {str(e)}",
            'sequence_effects_analysis': f"Error: {str(e)}",
            'log': None
        }


def save_analysis_results(results, output_dir, target_properties):
    """Save analysis results to files with enhanced analysis types."""
    
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    
    # Save individual analysis results
    for result in results:
        filename = f"analysis_{result['example_name'].replace('.txt', '')}.md"
        filepath = os.path.join(output_dir, filename)
        
        content = f"""# Analysis: {result['example_name']}

## Target Properties
{chr(10).join(f"- {prop}" for prop in target_properties)}

## Content Summary
- **File**: {result['example_name']}
- **Content Length**: {result['content_length']} characters
- **Image URLs Found**: {result['image_urls_found']}

## Image URLs
{chr(10).join(f"- {url}" for url in result['image_urls']) if result['image_urls'] else "None found"}

## Original Properties Analysis

{result['analysis_result']}

## 1. Modification Types Analysis (Name, Identity)

{result.get('modification_analysis', 'No modification analysis available')}

## 2. Modification Types → Sequence Identity Mapping

{result.get('sequence_modification_mapping', 'No sequence-modification mapping available')}

## 3. Sequence Pairwise Analysis (Before → After Identity)

{result.get('pairwise_analysis', 'No pairwise analysis available')}

## 4. Sequence Pairwise → Effects (Properties)

{result.get('sequence_effects_analysis', 'No sequence-effects analysis available')}

---
*Analysis generated using enhanced dleader_agent agent with Claude Sonnet 4*
*Includes: Properties analysis, Modification types, Sequence mapping, Pairwise comparison, Effect analysis*
"""
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        
        print(f"💾 Saved enhanced analysis: {filename}")
    
    # Save comprehensive summary
    summary_file = os.path.join(output_dir, "comprehensive_analysis_summary.md")
    
    summary_content = f"""# Comprehensive Patent Examples Analysis

## Target Properties Analysis
{chr(10).join(f"- {prop}" for prop in target_properties)}

## Enhanced Analysis Types
1. **Modification Types (Name, Identity)**: Extraction and identification of modification types with names and identities
2. **Modification Types → Sequence Identity**: Mapping between modification types and specific sequences
3. **Sequence Pairwise Analysis (Before → After)**: Comparison of original vs modified sequences with identity analysis
4. **Sequence Pairwise → Effects (Properties)**: Relationship analysis between sequence changes and property effects

## Examples Analyzed
"""
    
    total_images = 0
    total_content = 0
    
    for result in results:
        summary_content += f"""
### {result['example_name']}
- **Content Length**: {result['content_length']} characters
- **Image URLs**: {result['image_urls_found']}
- **Analysis File**: `analysis_{result['example_name'].replace('.txt', '')}.md`
- **Enhanced Analysis**: ✅ Modification types, Sequence mapping, Pairwise comparison, Effect analysis

"""
        total_images += result['image_urls_found']
        total_content += result['content_length']
    
    summary_content += f"""
## Overall Statistics
- **Total Examples Analyzed**: {len(results)}
- **Total Content Analyzed**: {total_content:,} characters
- **Total Image URLs Found**: {total_images}
- **Analysis Method**: Enhanced dleader_agent agent with multiple analysis types
- **Analysis Types**: 5 (Original properties + 4 new analysis types)

## Analysis Structure
Each analysis file contains:
1. Original target properties analysis
2. Modification types identification
3. Modification-sequence mapping
4. Before/after sequence pairwise comparison
5. Sequence change to property effect relationships

## Key Findings Summary
Please refer to individual analysis files for detailed findings across all analysis types.

---
*Analysis generated using enhanced patent_examples_analyzer.py*
*Based on minimal_image_agent_example.py structure with additional analysis capabilities*
"""
    
    # Save additional specialized summaries
    modification_summary_file = os.path.join(output_dir, "modification_types_summary.md")
    sequence_summary_file = os.path.join(output_dir, "sequence_analysis_summary.md")
    effects_summary_file = os.path.join(output_dir, "effects_analysis_summary.md")
    
    # Create modification types summary
    mod_summary = """# Modification Types Summary

## Overview
This file contains a consolidated view of all modification types identified across patent examples.

## Modification Types Found
"""
    
    for result in results:
        if result.get('modification_analysis') and not result['modification_analysis'].startswith('Error'):
            mod_summary += f"""
### {result['example_name']}
{result['modification_analysis']}

---
"""
    
    with open(modification_summary_file, 'w', encoding='utf-8') as f:
        f.write(mod_summary)
    
    # Create sequence analysis summary
    seq_summary = """# Sequence Analysis Summary

## Overview
This file contains consolidated sequence mapping and pairwise comparison results.

## Sequence Mappings and Comparisons
"""
    
    for result in results:
        seq_summary += f"""
### {result['example_name']}

#### Modification-Sequence Mapping
{result.get('sequence_modification_mapping', 'No mapping data')}

#### Pairwise Analysis
{result.get('pairwise_analysis', 'No pairwise data')}

---
"""
    
    with open(sequence_summary_file, 'w', encoding='utf-8') as f:
        f.write(seq_summary)
    
    # Create effects analysis summary
    effects_summary = """# Effects Analysis Summary

## Overview
This file contains consolidated analysis of relationships between sequence changes and property effects.

## Sequence-to-Effects Relationships
"""
    
    for result in results:
        if result.get('sequence_effects_analysis') and not result['sequence_effects_analysis'].startswith('Error'):
            effects_summary += f"""
### {result['example_name']}
{result['sequence_effects_analysis']}

---
"""
    
    with open(effects_summary_file, 'w', encoding='utf-8') as f:
        f.write(effects_summary)
    
    with open(summary_file, 'w', encoding='utf-8') as f:
        f.write(summary_content)
    
    print(f"📊 Saved comprehensive summary: comprehensive_analysis_summary.md")
    print(f"🔬 Saved modification types summary: modification_types_summary.md")
    print(f"🧬 Saved sequence analysis summary: sequence_analysis_summary.md") 
    print(f"⚡ Saved effects analysis summary: effects_analysis_summary.md")


def main():
    """Main function - based on example_url_image_analysis structure"""
    
    print("🧬 Patent Examples Analyzer")
    print("="*60)
    print("Based on minimal_image_agent_example.py")
    print("="*60)
    
    # Configuration
    examples_dir = "/home/ubuntu/work/dleader_agent/extracted_examples"
    output_dir = "/home/ubuntu/work/dleader_agent/analysis_results"
    
    # Target properties from user selection
    target_properties = [
        "Toxicity",
        "Binding affinity", 
        "Enzyme stability",
        "Delivery",
        "Reduce immune stimulation",
        "Aqueous solubility"
    ]
    
    # Create minimal agent - following minimal_image_agent_example.py
    agent = create_minimal_image_agent()
    
    # Load example content
    examples_data = load_example_content(examples_dir)
    if not examples_data:
        print("❌ No examples found to analyze")
        return
    
    print(f"\n📋 Found {len(examples_data)} examples to analyze")
    
    # Analyze each example
    results = []
    for example_name, content in examples_data.items():
        result = analyze_example_with_agent(agent, example_name, content, target_properties)
        results.append(result)
    
    # Save results
    save_analysis_results(results, output_dir, target_properties)
    
    # Final summary
    print("\n" + "="*60)
    print("✅ ANALYSIS COMPLETE")
    print("="*60)
    print(f"📁 Input Directory: {examples_dir}")
    print(f"📁 Output Directory: {output_dir}")
    print(f"📄 Examples Analyzed: {len(results)}")
    print(f"🎯 Target Properties: {len(target_properties)}")
    print(f"🔍 Total Image URLs Found: {sum(r['image_urls_found'] for r in results)}")
    print("="*60)


if __name__ == "__main__":
    main()