#!/usr/bin/env python3
"""
Simple Patent Analysis Program
Analyzes patent examples for modification types and their effects on target properties.
"""

import os
import json
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
import re

@dataclass
class AnalysisResult:
    example_name: str
    modification_types: List[str]
    sequences_before_after: List[Dict[str, str]]
    property_effects: Dict[str, str]
    classification: str

class SimplePatentAnalyzer:
    def __init__(self, examples_dir: str, output_dir: str):
        self.examples_dir = Path(examples_dir)
        self.output_dir = Path(output_dir)
        self.target_properties = [
            "Toxicity",
            "Binding affinity", 
            "Enzyme stability",
            "Delivery",
            "Reduce immune stimulation",
            "Aqueous solubility"
        ]
        self.modification_types = ["backbone", "sugar", "terminal", "conjugates", "others"]
        
        # Create output directory if it doesn't exist
        self.output_dir.mkdir(exist_ok=True)
    
    def load_example_content(self) -> Dict[str, str]:
        """Load all example content from the examples directory."""
        examples_data = {}
        
        if not self.examples_dir.exists():
            print(f"❌ Examples directory not found: {self.examples_dir}")
            return examples_data
        
        for file_path in self.examples_dir.glob("*.txt"):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    examples_data[file_path.stem] = content
            except Exception as e:
                print(f"⚠️ Error reading {file_path}: {e}")
        
        return examples_data
    
    def analyze_modification_types(self, content: str) -> List[str]:
        """
        Classify modification types using simple keyword matching.
        Categories: backbone, sugar, terminal, conjugates, others
        """
        found_types = []
        content_lower = content.lower()
        
        # Backbone modifications
        backbone_keywords = ["backbone", "phosphodiester", "phosphorothioate", "boranophosphate", "methylphosphonate"]
        if any(keyword in content_lower for keyword in backbone_keywords):
            found_types.append("backbone")
        
        # Sugar modifications
        sugar_keywords = ["sugar", "ribose", "2'-o-methyl", "2'-fluoro", "locked nucleic acid", "lna"]
        if any(keyword in content_lower for keyword in sugar_keywords):
            found_types.append("sugar")
        
        # Terminal modifications
        terminal_keywords = ["terminal", "3' end", "5' end", "cap", "terminal modification"]
        if any(keyword in content_lower for keyword in terminal_keywords):
            found_types.append("terminal")
        
        # Conjugates
        conjugate_keywords = ["conjugate", "ligand", "cholesterol", "galnac", "aptamer", "antibody"]
        if any(keyword in content_lower for keyword in conjugate_keywords):
            found_types.append("conjugates")
        
        # If no specific type found, classify as others
        if not found_types:
            found_types.append("others")
        
        return found_types
    
    def extract_sequences(self, content: str) -> List[Dict[str, str]]:
        """Extract before/after sequence pairs from content."""
        sequences = []
        
        # Look for sequence patterns
        seq_patterns = [
            r"before[:\s]+([ATCGU\s]+)[\s\n]+after[:\s]+([ATCGU\s]+)",
            r"original[:\s]+([ATCGU\s]+)[\s\n]+modified[:\s]+([ATCGU\s]+)",
            r"([ATCGU]{10,})[\s\n]+(?:modified to|changed to)[:\s]+([ATCGU]{10,})"
        ]
        
        for pattern in seq_patterns:
            matches = re.finditer(pattern, content, re.IGNORECASE | re.MULTILINE)
            for match in matches:
                before_seq = re.sub(r'[^ATCGU]', '', match.group(1).upper())
                after_seq = re.sub(r'[^ATCGU]', '', match.group(2).upper())
                
                if len(before_seq) >= 5 and len(after_seq) >= 5:
                    sequences.append({
                        "before": before_seq,
                        "after": after_seq
                    })
        
        return sequences
    
    def analyze_property_effects(self, content: str) -> Dict[str, str]:
        """Analyze effects on target properties using simple text analysis."""
        effects = {}
        content_lower = content.lower()
        
        for prop in self.target_properties:
            prop_lower = prop.lower()
            
            # Look for mentions of the property
            if prop_lower in content_lower:
                # Look for effect indicators around the property mention
                context_words = []
                sentences = content_lower.split('.')
                
                for sentence in sentences:
                    if prop_lower in sentence:
                        # Check for improvement indicators
                        if any(word in sentence for word in ["improve", "increase", "enhance", "better", "reduce toxicity", "lower toxicity"]):
                            effects[prop] = "improved"
                        elif any(word in sentence for word in ["reduce", "decrease", "lower", "worse", "impair"]):
                            effects[prop] = "reduced" if prop != "Toxicity" else "improved"
                        elif any(word in sentence for word in ["maintain", "preserve", "stable"]):
                            effects[prop] = "maintained"
                        else:
                            effects[prop] = "mentioned"
                        break
            else:
                effects[prop] = "not mentioned"
        
        return effects
    
    def analyze_example(self, example_name: str, content: str) -> AnalysisResult:
        """Analyze a single example with simple prompt-like approach."""
        
        print(f"🔍 Analyzing {example_name}...")
        
        # 1. Modification types classification
        modification_types = self.analyze_modification_types(content)
        
        # 2. Sequence analysis
        sequences = self.extract_sequences(content)
        
        # 3. Property effects analysis
        property_effects = self.analyze_property_effects(content)
        
        # 4. Overall classification based on dominant modification type
        if len(modification_types) == 1:
            classification = modification_types[0]
        elif "backbone" in modification_types:
            classification = "backbone"
        elif "conjugates" in modification_types:
            classification = "conjugates"
        else:
            classification = "mixed"
        
        return AnalysisResult(
            example_name=example_name,
            modification_types=modification_types,
            sequences_before_after=sequences,
            property_effects=property_effects,
            classification=classification
        )
    
    def run_analysis(self):
        """Run the complete analysis pipeline."""
        print("🚀 Starting Simple Patent Analysis")
        print(f"📁 Examples directory: {self.examples_dir}")
        print(f"📁 Output directory: {self.output_dir}")
        
        # Load example content
        examples_data = self.load_example_content()
        if not examples_data:
            print("❌ No examples found to analyze")
            return
        
        print(f"\n📋 Found {len(examples_data)} examples to analyze")
        print(f"🎯 Target properties: {', '.join(self.target_properties)}")
        print(f"🔧 Modification types: {', '.join(self.modification_types)}")
        
        # Analyze each example
        results = []
        for example_name, content in examples_data.items():
            result = self.analyze_example(example_name, content)
            results.append(result)
        
        # Save results
        self.save_results(results)
        
        # Print summary
        self.print_summary(results)
    
    def save_results(self, results: List[AnalysisResult]):
        """Save analysis results to JSON file."""
        output_data = []
        
        for result in results:
            output_data.append({
                "example_name": result.example_name,
                "modification_types": result.modification_types,
                "sequences_before_after": result.sequences_before_after,
                "property_effects": result.property_effects,
                "classification": result.classification
            })
        
        output_file = self.output_dir / "simple_analysis_results.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)
        
        print(f"\n💾 Results saved to: {output_file}")
    
    def print_summary(self, results: List[AnalysisResult]):
        """Print analysis summary."""
        print(f"\n📊 Analysis Summary")
        print("=" * 50)
        
        # Modification type distribution
        mod_type_counts = {}
        for result in results:
            for mod_type in result.modification_types:
                mod_type_counts[mod_type] = mod_type_counts.get(mod_type, 0) + 1
        
        print(f"\n🔧 Modification Type Distribution:")
        for mod_type, count in sorted(mod_type_counts.items()):
            print(f"  {mod_type}: {count}")
        
        # Property effects summary
        property_effects_summary = {}
        for prop in self.target_properties:
            property_effects_summary[prop] = {"improved": 0, "reduced": 0, "maintained": 0, "mentioned": 0, "not mentioned": 0}
        
        for result in results:
            for prop, effect in result.property_effects.items():
                if prop in property_effects_summary:
                    property_effects_summary[prop][effect] = property_effects_summary[prop].get(effect, 0) + 1
        
        print(f"\n🎯 Property Effects Summary:")
        for prop, effects in property_effects_summary.items():
            print(f"  {prop}:")
            for effect, count in effects.items():
                if count > 0:
                    print(f"    {effect}: {count}")
        
        # Sequence analysis summary
        total_sequences = sum(len(result.sequences_before_after) for result in results)
        print(f"\n🧬 Sequence Analysis: Found {total_sequences} before/after sequence pairs")

def main():
    """Main function to run the simple patent analyzer."""
    examples_dir = "/home/ubuntu/work/dleader_agent/extracted_examples"
    output_dir = "/home/ubuntu/work/dleader_agent/analysis_results"
    
    analyzer = SimplePatentAnalyzer(examples_dir, output_dir)
    analyzer.run_analysis()

if __name__ == "__main__":
    main()