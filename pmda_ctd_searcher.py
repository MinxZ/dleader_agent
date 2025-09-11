#!/usr/bin/env python3
"""
PMDA CTD Searcher - Search PMDA databases using Japanese drug names from KEGG data
"""

import pandas as pd
import requests
import time
import logging
from urllib.parse import quote
from bs4 import BeautifulSoup
import re
import json
from typing import Dict, List, Optional, Tuple

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class PMDASearcher:
    """Class to search PMDA databases for Japanese drug names"""
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        self.base_url = "https://www.pmda.go.jp"
        self.search_delay = 2  # Delay between requests in seconds
        
    def load_kegg_data(self, filepath: str) -> pd.DataFrame:
        """Load KEGG small molecules data"""
        try:
            df = pd.read_csv(filepath)
            logger.info(f"Loaded {len(df)} records from {filepath}")
            return df
        except Exception as e:
            logger.error(f"Error loading KEGG data: {e}")
            return pd.DataFrame()
    
    def search_pmda_by_japanese_name(self, japanese_name: str) -> Dict:
        """
        Search PMDA for drug information using Japanese name
        Since PMDA doesn't have a public API, this attempts web scraping
        """
        result = {
            'japanese_name': japanese_name,
            'found': False,
            'pmda_url': None,
            'approval_info': None,
            'error': None
        }
        
        try:
            # PMDA search URLs (these are approximations based on common patterns)
            search_urls = [
                f"https://www.pmda.go.jp/PmdaSearch/iyakuSearch/",
                f"https://www.pmda.go.jp/search/?q={quote(japanese_name)}"
            ]
            
            for search_url in search_urls:
                try:
                    logger.info(f"Searching PMDA for: {japanese_name}")
                    response = self.session.get(search_url, timeout=10)
                    
                    if response.status_code == 200:
                        soup = BeautifulSoup(response.content, 'html.parser')
                        
                        # Look for drug-related content
                        drug_links = soup.find_all('a', href=re.compile(r'/drugs|/review|/approved'))
                        
                        if drug_links:
                            result['found'] = True
                            result['pmda_url'] = search_url
                            result['approval_info'] = f"Found {len(drug_links)} potential matches"
                            break
                            
                except requests.RequestException as e:
                    logger.warning(f"Request failed for {search_url}: {e}")
                    continue
                    
                time.sleep(self.search_delay)
                
        except Exception as e:
            result['error'] = str(e)
            logger.error(f"Error searching for {japanese_name}: {e}")
        
        return result
    
    def search_alternative_databases(self, japanese_name: str, generic_name: str = None) -> Dict:
        """
        Search alternative databases that might have PMDA-related information
        """
        result = {
            'japanese_name': japanese_name,
            'generic_name': generic_name,
            'kegg_match': False,
            'alternative_sources': []
        }
        
        # KEGG DRUG database search
        try:
            kegg_url = f"https://www.genome.jp/dbget-bin/www_bfind_sub?mode=bfind&max_hit=1000&dbkey=drug&keywords={quote(japanese_name)}"
            response = self.session.get(kegg_url, timeout=10)
            
            if response.status_code == 200 and japanese_name in response.text:
                result['kegg_match'] = True
                result['alternative_sources'].append({
                    'source': 'KEGG DRUG',
                    'url': kegg_url,
                    'status': 'found'
                })
                
        except Exception as e:
            logger.warning(f"KEGG search failed for {japanese_name}: {e}")
        
        time.sleep(self.search_delay)
        return result
    
    def process_kegg_dataset(self, df: pd.DataFrame, max_records: int = None) -> List[Dict]:
        """Process KEGG dataset and search for PMDA information"""
        results = []
        
        if max_records:
            df = df.head(max_records)
        
        for idx, row in df.iterrows():
            japanese_name = row.get('Japanese_Name', '')
            generic_name = row.get('Generic_Name', '')
            
            if pd.isna(japanese_name) or japanese_name.strip() == '':
                continue
            
            logger.info(f"Processing {idx + 1}/{len(df)}: {japanese_name}")
            
            # Search PMDA
            pmda_result = self.search_pmda_by_japanese_name(japanese_name)
            
            # Search alternative databases
            alt_result = self.search_alternative_databases(japanese_name, generic_name)
            
            # Combine results
            combined_result = {
                'index': idx,
                'kegg_data': {
                    'date': row.get('Date', ''),
                    'drug_id': row.get('Drug_ID', ''),
                    'generic_name': generic_name,
                    'japanese_name': japanese_name,
                    'brand_name': row.get('Brand_Name', ''),
                    'company': row.get('Company', '')
                },
                'pmda_search': pmda_result,
                'alternative_search': alt_result
            }
            
            results.append(combined_result)
            
            # Progress logging
            if (idx + 1) % 10 == 0:
                logger.info(f"Processed {idx + 1} records")
        
        return results
    
    def save_results(self, results: List[Dict], output_file: str):
        """Save search results to JSON file"""
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(results, f, ensure_ascii=False, indent=2)
            logger.info(f"Results saved to {output_file}")
        except Exception as e:
            logger.error(f"Error saving results: {e}")
    
    def generate_summary_report(self, results: List[Dict]) -> Dict:
        """Generate a summary report of the search results"""
        summary = {
            'total_processed': len(results),
            'pmda_found': 0,
            'kegg_matches': 0,
            'errors': 0,
            'sample_findings': []
        }
        
        for result in results:
            if result['pmda_search']['found']:
                summary['pmda_found'] += 1
            
            if result['alternative_search']['kegg_match']:
                summary['kegg_matches'] += 1
            
            if result['pmda_search']['error'] or result['alternative_search']:
                summary['errors'] += 1
            
            # Collect sample findings
            if len(summary['sample_findings']) < 5 and result['pmda_search']['found']:
                summary['sample_findings'].append({
                    'japanese_name': result['kegg_data']['japanese_name'],
                    'generic_name': result['kegg_data']['generic_name'],
                    'pmda_info': result['pmda_search']['approval_info']
                })
        
        return summary


def main():
    """Main function to run PMDA CTD search"""
    searcher = PMDASearcher()
    
    # Load KEGG data
    kegg_file = "/home/ubuntu/work/dleader_agent/kegg_small_molecules_complete.csv"
    df = searcher.load_kegg_data(kegg_file)
    
    if df.empty:
        logger.error("No data loaded. Exiting.")
        return
    
    print(f"Loaded {len(df)} KEGG records")
    print(f"Sample Japanese names: {df['Japanese_Name'].dropna().head().tolist()}")
    
    # Ask user for number of records to process
    while True:
        try:
            max_records = input(f"\nEnter number of records to process (max {len(df)}, or 'all'): ")
            if max_records.lower() == 'all':
                max_records = None
                break
            else:
                max_records = int(max_records)
                if 1 <= max_records <= len(df):
                    break
                else:
                    print(f"Please enter a number between 1 and {len(df)}")
        except ValueError:
            print("Please enter a valid number or 'all'")
    
    # Process the dataset
    print(f"\nStarting PMDA CTD search...")
    results = searcher.process_kegg_dataset(df, max_records)
    
    # Save results
    output_file = "pmda_ctd_search_results.json"
    searcher.save_results(results, output_file)
    
    # Generate and display summary
    summary = searcher.generate_summary_report(results)
    
    print(f"\n=== SEARCH SUMMARY ===")
    print(f"Total processed: {summary['total_processed']}")
    print(f"PMDA matches found: {summary['pmda_found']}")
    print(f"KEGG database matches: {summary['kegg_matches']}")
    print(f"Errors encountered: {summary['errors']}")
    
    if summary['sample_findings']:
        print(f"\n=== SAMPLE FINDINGS ===")
        for finding in summary['sample_findings']:
            print(f"Japanese: {finding['japanese_name']}")
            print(f"Generic: {finding['generic_name']}")
            print(f"PMDA Info: {finding['pmda_info']}")
            print("-" * 40)
    
    print(f"\nDetailed results saved to: {output_file}")


if __name__ == "__main__":
    main()