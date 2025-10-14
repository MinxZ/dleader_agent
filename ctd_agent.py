"""
Example: Minimal Agent Configuration for Image Analysis Only

This example shows how to configure the dleader_agent agent to use only 
image analysis tools without default data lake and packages.
"""

import glob
import json
import os
import sys
import time
from datetime import datetime

import pandas as pd
import tiktoken
from tqdm import tqdm

sys.path.insert(0, os.getcwd())

from dleader_agent.agent.a1 import A1

"""
Example: Minimal Agent Configuration for Image Analysis Only

This example shows how to configure the dleader_agent agent to use only 
image analysis tools without default data lake and packages.
"""
"""
Agent Interface with Live Thinking Display

This interface provides a clean layout with:
- Left side: User input and final report display
- Right side: Live executor showing planning and thinking process
- Download functionality for reports and thinking process
"""

import argparse
import os
import shutil
import sys
import tempfile
import threading
import time
import uuid
import zipfile
from contextlib import redirect_stdout
from datetime import datetime

import pandas as pd
from PIL import Image

# Add current directory to path for imports
sys.path.insert(0, os.getcwd())

from dleader_agent.agent.a1 import A1


def create_agent():
    """Create an agent configured only for image analysis tasks."""
    
    # Initialize agent without downloading default data lake
    agent = A1(
        use_tool_retriever=True,
        download_data_lake=False, 
        llm='claude-sonnet-4-5-20250929'
    )
    
    return agent


class TokenCostTracker:
    """Track tokens and costs for Claude Sonnet 4 interactions."""
    
    def __init__(self):
        self.encoding = tiktoken.encoding_for_model("gpt-4")  # Use GPT-4 encoding as approximation
        self.session_stats = {
            'files_processed': {},
            'total_input_tokens': 0,
            'total_output_tokens': 0,
            'total_cost': 0.0,
            'start_time': datetime.now().isoformat()
        }
        
        # Claude Sonnet 4 pricing (per MTok)
        self.pricing = {
            'input_under_200k': 3.0,    # $3/MTok for prompts ≤ 200K tokens
            'input_over_200k': 6.0,     # $6/MTok for prompts > 200K tokens
            'output_under_200k': 15.0,  # $15/MTok for outputs ≤ 200K tokens
            'output_over_200k': 22.5    # $22.50/MTok for outputs > 200K tokens
        }
    
    def count_tokens(self, text):
        """Count tokens in text using tiktoken."""
        if not text:
            return 0
        return len(self.encoding.encode(str(text)))
    
    def calculate_cost(self, input_tokens, output_tokens):
        """Calculate cost based on Claude Sonnet 4 pricing tiers."""
        input_cost = 0.0
        output_cost = 0.0
        
        # Input cost calculation
        if input_tokens <= 200000:
            input_cost = (input_tokens / 1000000) * self.pricing['input_under_200k']
        else:
            # First 200k at lower rate, rest at higher rate
            input_cost = (200000 / 1000000) * self.pricing['input_under_200k']
            input_cost += ((input_tokens - 200000) / 1000000) * self.pricing['input_over_200k']
        
        # Output cost calculation
        if output_tokens <= 200000:
            output_cost = (output_tokens / 1000000) * self.pricing['output_under_200k']
        else:
            # First 200k at lower rate, rest at higher rate
            output_cost = (200000 / 1000000) * self.pricing['output_under_200k']
            output_cost += ((output_tokens - 200000) / 1000000) * self.pricing['output_over_200k']
        
        return input_cost + output_cost
    
    def track_interaction(self, file_path, prompt, response):
        """Track tokens and cost for a single interaction."""
        input_tokens = self.count_tokens(prompt)
        output_tokens = self.count_tokens(response)
        cost = self.calculate_cost(input_tokens, output_tokens)
        
        # Initialize file stats if new
        if file_path not in self.session_stats['files_processed']:
            self.session_stats['files_processed'][file_path] = {
                'input_tokens': 0,
                'output_tokens': 0,
                'cost': 0.0,
                'interactions': 0
            }
        
        # Update file-specific stats
        file_stats = self.session_stats['files_processed'][file_path]
        file_stats['input_tokens'] += input_tokens
        file_stats['output_tokens'] += output_tokens
        file_stats['cost'] += cost
        file_stats['interactions'] += 1
        
        # Update session totals
        self.session_stats['total_input_tokens'] += input_tokens
        self.session_stats['total_output_tokens'] += output_tokens
        self.session_stats['total_cost'] += cost
        
        return {
            'input_tokens': input_tokens,
            'output_tokens': output_tokens,
            'cost': cost
        }
    
    def print_interaction_stats(self, file_path, interaction_stats):
        """Print stats for current interaction."""
        print(f"\n💰 Token Usage & Cost for {os.path.basename(file_path)}:")
        print(f"   📥 Input tokens: {interaction_stats['input_tokens']:,}")
        print(f"   📤 Output tokens: {interaction_stats['output_tokens']:,}")
        print(f"   💵 Interaction cost: ${interaction_stats['cost']:.6f}")
    
    def print_session_summary(self):
        """Print comprehensive session statistics."""
        print("\n" + "="*60)
        print("💰 SESSION COST SUMMARY")
        print("="*60)
        
        total_tokens = self.session_stats['total_input_tokens'] + self.session_stats['total_output_tokens']
        print(f"📊 Total tokens: {total_tokens:,}")
        print(f"📥 Total input tokens: {self.session_stats['total_input_tokens']:,}")
        print(f"📤 Total output tokens: {self.session_stats['total_output_tokens']:,}")
        print(f"💵 Total estimated cost: ${self.session_stats['total_cost']:.6f}")
        
        print(f"\n📁 Files processed ({len(self.session_stats['files_processed'])}):")
        for file_path, stats in self.session_stats['files_processed'].items():
            print(f"   {os.path.basename(file_path)}:")
            print(f"     📥 Input: {stats['input_tokens']:,} tokens")
            print(f"     📤 Output: {stats['output_tokens']:,} tokens") 
            print(f"     💵 Cost: ${stats['cost']:.6f}")
            print(f"     🔄 Interactions: {stats['interactions']}")
    
    def save_stats(self, filename="token_cost_stats.json"):
        """Save session stats to JSON file."""
        self.session_stats['end_time'] = datetime.now().isoformat()
        with open(filename, 'w') as f:
            json.dump(self.session_stats, f, indent=2)
        print(f"💾 Stats saved to {filename}")

def create_minimal_image_agent():
    """Create an agent configured only for image analysis tasks."""
    
    # Initialize agent without downloading default data lake
    agent = create_agent()
    
    # Clear default data lake to avoid distractions
    agent.data_lake_dict = {}
    

    # Filter module2api to keep only support tools (contains image function)
    image_modules = {
        'dleader_agent.tool.support_tools': agent.module2api.get('dleader_agent.tool.support_tools', []),
        'dleader_agent.tool.literature': agent.module2api.get('dleader_agent.tool.literature', [])
    }
    agent.module2api = image_modules
    
    print("✅ Configured minimal agent with:")
    # print(f"   📦 {len(essential_packages)} essential packages")
    # print(f"   🔧 {len(image_modules.get('dleader_agent.tool.support_tools', []))} support tools (including image analysis)")
    # print(f"   📊 {len(agent.data_lake_dict)} data lake items (empty)")
    
    return agent



def example_url_image_analysis():
    """Example using image URL analysis with different modes."""
    
    print("🚀 URL Image Analysis Example")
    print("="*50)
    
    # Create minimal agent and token tracker
    agent = create_minimal_image_agent()
    
    list_path = glob.glob('/home/ubuntu/dleader_agent/pdf/*.pdf')
    for file_path in tqdm(list_path[:2]):
        # os.chdir('/home/ubuntu/work/dleader_agent_ctd') 
        # tracker = TokenCostTracker()
        prompt = '1+1'
#         prompt = f"""
# I would like to extract information on whether a drug is a substrate of transporters or not, and whether it inhibits transporters, from the summary of drug review documents (extracts of CTD)
# Can you also include the number data, and the original text of evidence(japanese) and description and source page, the file path is {file_path}. 
# focus on these and use the threashold guideline P-gp or BCRP IC50,u

# 0.1 × (Dose/250 mL) (i.e.,
# (Dose/250 mL)/ IC50,u < 10) for orally administered drugs
# OATP1B1 or OATP1B3 OAT1, OAT3, OCT2 MATE1/MATE2-K IC50,u > 10 × Cmax, inlet,u

# (i.e., Cmax,inlet,u / IC50,u < 0.1)
# IC50,u > 10 × Cmax,u (i.e., Cmax,u/ IC50,u < 0.1)
# IC50,u > 50 × Cmax,u (i.e., Cmax,u/ IC50,u < 0.02)
# Cmax,u is unbound maximal plasma concentration of an inhibitor at steady state after therapeutic dose.

# The Ki,u of an inhibitor approaches IC50,u when substrate concentration is much less than Km assuming
# competitive inhibition (8).
# Cmax,inlet,u is estimated unbound maximum plasma concentration of an inhibitor at liver inlet.
# Cmax,inlet,u=fu,p x (Cmax + (Fa×Fg×ka×Dose)/Qh/RB) (36). If unknown, Fa= 1, Fg = 1 and k= 0.1/min can
# be used as a worst-case estimate. The fu,p should be set to 1% if the reliability of fu,p measurements <1%
# cannot be demonstrated (also refer to Section 2.1.2.1). 
# Some of the term is in japanese, like P-gp is represented as hMDR1 or ヒトP糖たん白. You need to first to think about the japanese term or see in the pdf. 
# List any transporters not mentioned, because the drug may be a non-substrate of these transporters. write in both japanese and english version table. and write clearly is a substrate of transporters or not, and whether it inhibits transporters in the table, if not mentioned, say not mentioned
# If the experimental numerical data is not mentioned or not tested, also say not mentioned. always say not mentioned instead of not test
# Next to substrate(yes/no) add three additional columns alongside the Yes/No column. Label them IC50, Km/or.., Numerical Value, and Unit. also do it for transporters(yes/no), 
# write in 日本語 for the description and original text if the language is japanese, other wise using the language of the pdf for the description and original text and summarize in table
# separate substrate and transporters into 2 csv: {file_path.replace('.pdf', '_substrate.csv').replace('pdf/', 'csv/')}, {file_path.replace('.pdf', '_transporter.csv').replace('pdf/', 'csv/')}
# reference this as the format for pdf.
# Transporter (English),Transporter (Japanese),Inhibitor (Yes/No),IC50/Km/Other Parameter,STANDARD_RELATION,Numerical Value,Standard Deviation,Unit,Original Text,Source page
# P-gp,P糖蛋白,Yes,IC50,=,37.2,8.1,μM,ジゴキシン輸送（P-gp）37.2 ± 8.1,38
# BCRP,乳癌耐性蛋白,Yes,IC50,=,0.31,0.22,μM,BCRP 0.31 ± 0.22,38
# OATP1B1,有機アニオン輸送ポリペプチド1B1,Yes,IC50,=,6.1,1.0,μM,OATP1B1 6.1 ± 1.0,38
# OATP1B3,有機アニオン輸送ポリペプチド1B3,Yes,IC50,=,1.1,0.4,μM,OATP1B3 1.1 ± 0.4,38
# NTCP,タウロコール酸ナトリウム共輸送ポリペプチド,No,IC50,>,50,,μM,NTCP > 50,38
# BSEP,胆汁酸塩輸送ポンプ,Yes,IC50,=,17.0,2.1,μM,BSEP 17.0 ± 2.1,38
# MRP2,多剤耐性蛋白2,No,IC50,>,50,,μM,MRP2 > 50,38
# OAT1,有機アニオントランスポーター1,Yes,IC50,=,16.8,2.7,μM,OAT1 16.8 ± 2.7,38
# OAT3,有機アニオントランスポーター3,Yes,IC50,=,17.2,0.9,μM,OAT3 17.2 ± 0.9,38
# OCT1,有機カチオントランスポーター1,Yes,IC50,=,4.7,0.6,μM,OCT1 4.7 ± 0.6,38
# OCT2,有機カチオントランスポーター2,Yes,IC50,=,24.7,5.0,μM,OCT2 24.7 ± 5.0,38
# MATE1,多剤・毒性化合物排出蛋白1,Yes,IC50,=,6.7,1.6,μM,MATE1 6.7 ± 1.6,38
# MATE2-K,多剤・毒性化合物排出蛋白2-K,Yes,IC50,=,3.33,,μM,MATE2-K 3.33,38
# """
        
        log, result = agent.go(prompt)
        
        # Track tokens and cost for this interaction
        # interaction_stats = tracker.track_interaction(file_path, prompt, str(log))
        # tracker.print_interaction_stats(file_path, interaction_stats)
    
        print("📋 Agent Response:")
        print(log, result)
        time.sleep(60)
        with open(file_path.replace('.pdf', '_log.txt'), 'w') as f:
            f.write(str(log))
        with open(file_path.replace('.pdf', '_result.txt'), 'w') as f:
            f.write(str(result))
            
if __name__ == "__main__":
    print("🧬 Minimal dleader_agent Agent - Image Analysis Only")
    print("="*60)
    example_url_image_analysis()
    
