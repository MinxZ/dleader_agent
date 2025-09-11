import pandas as pd
import requests
import time
from typing import Optional
from tqdm import tqdm

def fetch_smiles_from_kegg(drug_id: str) -> Optional[str]:
    """
    Fetch SMILES string for a given KEGG drug ID.
    
    Args:
        drug_id: KEGG drug ID (e.g., 'D04127')
        
    Returns:
        SMILES string if found, None otherwise
    """
    try:
        # KEGG API endpoint for MOL file
        url = f"https://rest.kegg.jp/get/{drug_id}/mol"
        response = requests.get(url, timeout=10)
        
        if response.status_code == 200:
            mol_data = response.text
            
            # Convert MOL to SMILES using RDKit
            try:
                from rdkit import Chem
                mol = Chem.MolFromMolBlock(mol_data)
                if mol:
                    return Chem.MolToSmiles(mol)
                else:
                    tqdm.write(f"Failed to parse MOL data for {drug_id}")
                    return None
            except ImportError:
                tqdm.write("RDKit not available, cannot convert MOL to SMILES")
                return None
                
        return None
        
    except Exception as e:
        tqdm.write(f"Error fetching SMILES for {drug_id}: {e}")
        return None

def process_kegg_csv_with_smiles(csv_path: str, output_path: str = None, delay: float = 1):
    """
    Read KEGG CSV file, fetch SMILES for each Drug_ID, and save updated CSV.
    
    Args:
        csv_path: Path to input CSV file
        output_path: Path to save output CSV (defaults to input path)
        delay: Delay between API calls in seconds
    """
    if output_path is None:
        output_path = csv_path
        
    # Read the CSV file
    df = pd.read_csv(csv_path)
    
    # Add SMILES column if it doesn't exist
    if 'SMILES' not in df.columns:
        df['SMILES'] = ''
    
    print(f"Processing {len(df)} drugs...")
    
    # Iterate through each row and fetch SMILES with progress bar
    for idx, row in tqdm(df.iterrows(), total=len(df), desc="Fetching SMILES"):
        drug_id = row['Drug_ID']
        
        # Skip if SMILES already exists
        # if pd.notna(row.get('SMILES')) and row.get('SMILES').strip():
        #     tqdm.write(f"SMILES already exists for {drug_id}, skipping...")
        #     continue
            
        tqdm.write(f"Fetching SMILES for {drug_id}...")
        
        smiles = fetch_smiles_from_kegg(drug_id)
        
        if smiles:
            df.at[idx, 'SMILES'] = smiles
            tqdm.write(f"Found SMILES for {drug_id}: {smiles}")
        else:
            tqdm.write(f"No SMILES found for {drug_id}")
            
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
    smiles_count = df['SMILES'].notna().sum()
    total_count = len(df)
    print(f"Summary: {smiles_count}/{total_count} drugs have SMILES data")

if __name__ == "__main__":
    # Process the KEGG small molecules CSV
    csv_file = "kegg_small_molecules_2010-2025.csv"
    process_kegg_csv_with_smiles(csv_file)