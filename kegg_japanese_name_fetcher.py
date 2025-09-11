import pandas as pd
import requests
import time
from typing import Optional
from tqdm import tqdm

def fetch_japanese_name_from_kegg(drug_id: str = "D04127") -> Optional[str]:
    """
    Fetch Japanese name for a given KEGG drug ID.
    
    Args:
        drug_id: KEGG drug ID (e.g., 'D04127')
        
    Returns:
        Japanese name if found, None otherwise
    """
    try:
        # KEGG API endpoint for drug information
        url = f"https://rest.kegg.jp/get/dr_ja:{drug_id}"
        response = requests.get(url, timeout=10)
        
        if response.status_code == 200:
            lines = response.text.split('\n')
            
            # Look for NAME field which contains Japanese names
            in_name_section = False
            japanese_names = []
            
            for line in lines:
                line = line.strip()
                
                # Look for lines containing (JAN); pattern
                if '(JAN);' in line:
                    # Extract the part before (JAN);
                    parts = line.split('(JAN);')[0].strip()
                    
                    # Split by whitespace and get the last part (the Japanese name)
                    words = parts.split()
                    if words:
                        japanese_name = words[-1]
                        
                        # Check if it contains Japanese characters
                        if any('\u3040' <= char <= '\u309F' or  # Hiragana
                               '\u30A0' <= char <= '\u30FF' or  # Katakana
                               '\u4E00' <= char <= '\u9FAF'     # Kanji
                               for char in japanese_name):
                            return japanese_name
                
        return None
        
    except Exception as e:
        tqdm.write(f"Error fetching Japanese name for {drug_id}: {e}")
        return None

def process_kegg_csv_with_japanese_names(csv_path: str, output_path: str = None, delay: float = 1):
    """
    Read KEGG CSV file, fetch Japanese names for each Drug_ID, and save updated CSV.
    
    Args:
        csv_path: Path to input CSV file
        output_path: Path to save output CSV (defaults to input path)
        delay: Delay between API calls in seconds
    """
    if output_path is None:
        output_path = csv_path
        
    # Read the CSV file
    df = pd.read_csv(csv_path)
    
    # Add Japanese_Name column if it doesn't exist
    if 'Japanese_Name' not in df.columns:
        df['Japanese_Name'] = ''
    
    print(f"Processing {len(df)} drugs...")
    
    # Iterate through each row and fetch Japanese names
    for idx, row in tqdm(df.iterrows(), total=len(df), desc="Fetching Japanese names"):
        drug_id = row['Drug_ID']
        
        # Skip if Japanese name already exists
        if pd.notna(row.get('Japanese_Name')) and row.get('Japanese_Name').strip():
            tqdm.write(f"Japanese name already exists for {drug_id}, skipping...")
            continue
            
        tqdm.write(f"Fetching Japanese name for {drug_id}...")
        
        japanese_name = fetch_japanese_name_from_kegg(drug_id)
        
        if japanese_name:
            df.at[idx, 'Japanese_Name'] = japanese_name
            tqdm.write(f"Found Japanese name for {drug_id}: {japanese_name}")
        else:
            tqdm.write(f"No Japanese name found for {drug_id}")
            
        # Add delay to be respectful to the API
        time.sleep(delay)
        
        # Save progress every 10 entries
        if (idx + 1) % 10 == 0:
            df.to_csv(output_path, index=False)
            tqdm.write(f"Progress saved after {idx + 1} entries")
    
    # Save final results
    df.to_csv(output_path, index=False)
    print(f"Processing complete! Results saved to {output_path}")
    
    # Print summary
    japanese_name_count = df['Japanese_Name'].notna().sum()
    total_count = len(df)
    print(f"Summary: {japanese_name_count}/{total_count} drugs have Japanese names")

if __name__ == "__main__":
    # Process the KEGG small molecules CSV
    csv_file = "kegg_small_molecules_2010-2025.csv"
    process_kegg_csv_with_japanese_names(csv_file)