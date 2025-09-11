#!/usr/bin/env python3
"""
Patent section classifier - Simple and persistent approach
"""

import yaml
import requests
import json
import os
import time
from typing import Dict, Any


def call_azure_openai(prompt: str) -> str | None:
    """Simple Azure OpenAI API call - keep trying until success"""
    while True:
        try:
            with open("config.yaml", "r") as f:
                config = yaml.safe_load(f)
            azure_config = config["azure_openai"]

            url = f"{azure_config['endpoint'].rstrip('/')}/openai/deployments/{azure_config['deployment']}/chat/completions"
            headers = {
                "Content-Type": "application/json",
                "api-key": azure_config["api_key"]
            }
            params = {"api-version": azure_config["api_version"]}
            payload = {
                "messages": [{"role": "user", "content": prompt}],
                "max_completion_tokens": 200
            }

            r = requests.post(url, headers=headers, params=params, json=payload, timeout=10)
            r.raise_for_status()
            data = r.json()
            
            if "choices" in data and data["choices"]:
                result = data["choices"][0]["message"]["content"]
                if result and result.strip():
                    return result.strip()
            
            print("    Empty response, retrying in 10s...")
            time.sleep(10)
            
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 429:
                print("    Rate limit hit, waiting 5 minutes...")
                time.sleep(300)  # 5 minutes
            else:
                print(f"    HTTP error {e.response.status_code}, retrying in 30s...")
                time.sleep(30)
        except Exception as e:
            print(f"    Error: {e}, retrying in 30s...")
            time.sleep(30)


def get_first_100_words(text: str) -> str:
    """Extract first 100 words from text"""
    if not text or not isinstance(text, str):
        return ""
    words = text.split()
    return " ".join(words[:100])


def create_classification_prompt(title: str, content_preview: str) -> str:
    """Create the classification prompt"""
    prompt_template = """You are a patent document section classifier. Given a title and the first 100 words of content from a JSON key-value pair, classify the section into one of the predefined Google Patents standardized labels.

**Instructions:**
1. Analyze the provided title: "{title}"
2. Examine the first 100 words of content: "{content_preview}"
3. Determine if this section matches any of the standardized Google Patents section labels listed below
4. Return ONLY the exact matching label if found, or ONLY "Others" if no match exists

**Standardized Google Patents Section Labels:**
[
   'Info',
   'Links',
   'Images',
   'Classifications',
   'Definitions',
   'Landscapes',
   'Abstract',
   'Description',
   'Technical Field',
   'Background',
   'Summary of the Invention',
   'Brief Description of the Drawings',
   'Detailed Description',
   'Examples',
   'Example',
   'Working Example',
   'Comparative Example',
   'Reference Example',
   'Synthesis Example',
   'Preparation Example',
   'Prophetic Example',
   'Control Example',
   'Test Example',
   'Experimental Example',
   'Embodiment',
   'Preferred Embodiment',
   'Alternative Embodiment',
   'Specific Embodiment',
   'First Embodiment',
   'Second Embodiment',
   'Detailed Description of Certain Embodiments',
   'Best Mode for Carrying Out the Invention',
   'Claims',
   'Applications Claiming Priority',
   'Publications',
   'Family',
   'Family Applications',
   'Country Status',
   'Cited By',
   'Families Citing This Family',
   'Citations',
   'Family Cites Families',
   'Patent Citations',
   'Also Published As',
   'Similar Documents',
   'Legal Events',
   'Field of the Invention',
   'Description of Related Art',
   'Industrial Applicability',
   'Advantageous Effects',
   'Technical Problem',
   'Technical Solution',
   'Sequence Listing',
   'Computer Program Listing'
]

**STRICT OUTPUT REQUIREMENTS:**
- Return ONLY one of the exact labels from the list above, or ONLY "Others"
- NO additional text, explanations, or formatting
- NO quotes around the answer
- NO periods, colons, or other punctuation
- NO "Label:" prefix or any other prefix
- Must be one single line response

**Classification Rules:**
- Match based on semantic meaning and context, not just exact string matching
- Consider variations in capitalization, pluralization, and phrasing
- If the content clearly belongs to a specific patent section type, return the corresponding standardized label
- If uncertain or if the content doesn't fit any category, return "Others"

**Expected Output Format Examples:**
- Abstract
- Technical Field  
- Claims
- Others"""

    return prompt_template.format(title=title, content_preview=content_preview)


def classify_patent_sections(input_file_path: str, output_file_path: str):
    """
    Classify patent sections - keep going until ALL are done
    """
    
    # Load input file
    if not os.path.exists(input_file_path):
        print(f"Error: Input file {input_file_path} does not exist")
        return

    try:
        with open(input_file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        print(f"Error reading JSON file: {e}")
        return

    print(f"Loaded {len(data)} sections from {input_file_path}")
    
    # Check if we have partial results
    processed_data = {}
    if os.path.exists(output_file_path):
        try:
            with open(output_file_path, 'r', encoding='utf-8') as f:
                processed_data = json.load(f)
            print(f"Found {len(processed_data)} already processed sections")
        except:
            print("Could not load existing results, starting fresh")
    
    total_sections = len(data)
    sections_list = list(data.items())
    
    for i, (key, value) in enumerate(sections_list, 1):
        # Skip if already processed
        if key in processed_data:
            print(f"Skipping section {i}/{total_sections}: {key} (already done)")
            continue
            
        print(f"Processing section {i}/{total_sections}: {key}")
        
        # Get first 100 words
        content_preview = get_first_100_words(str(value))
        
        # Create prompt
        prompt = create_classification_prompt(key, content_preview)
        
        # Keep trying until we get a result
        print("  -> Calling API (will keep trying until success)...")
        label = call_azure_openai(prompt)
        print(f"  -> SUCCESS! Classified as: {label}")
        
        # Store result
        processed_data[key] = {
            "content": value,
            "label": label
        }
        
        # Save progress after each successful classification
        try:
            with open(output_file_path, 'w', encoding='utf-8') as f:
                json.dump(processed_data, f, indent=2, ensure_ascii=False)
            print(f"  -> Saved progress ({len(processed_data)}/{total_sections})")
        except Exception as e:
            print(f"  -> Warning: Could not save progress: {e}")
        
        # Small delay between successful calls
        print("  -> Waiting 10 seconds before next section...")
        time.sleep(10)
    
    # Final summary
    print(f"\n{'='*50}")
    print("ALL SECTIONS COMPLETED!")
    print(f"{'='*50}")
    
    label_counts = {}
    for section_data in processed_data.values():
        label = section_data["label"]
        label_counts[label] = label_counts.get(label, 0) + 1
    
    print(f"Total sections processed: {len(processed_data)}")
    print("\nLabel Distribution:")
    for label, count in sorted(label_counts.items(), key=lambda x: x[1], reverse=True):
        percentage = (count / len(processed_data)) * 100
        print(f"  {label}: {count} ({percentage:.1f}%)")


if __name__ == "__main__":
    input_file = "/home/ubuntu/work/dleader_agent/data/dleader_agent_data/patent_raw/US20220340900A1.sections.json"
    output_file = "/home/ubuntu/work/dleader_agent/data/dleader_agent_data/patent_raw/US20220340900A1.sections.labeled.json"
    
    print("="*60)
    print("PATENT SECTION CLASSIFIER - PERSISTENT MODE")
    print("="*60)
    print("Strategy: Keep trying until ALL sections are classified!")
    print("Will resume from where it left off if interrupted.")
    print("="*60)
    
    classify_patent_sections(input_file, output_file)
    
    print(f"\n{'='*60}")
    print("MISSION ACCOMPLISHED!")
    print(f"{'='*60}")