import pandas as pd

def filter_complete_kegg_data(input_csv: str, output_csv: str = None):
    """
    Filter KEGG CSV to keep only rows with both Japanese names and SMILES.
    
    Args:
        input_csv: Path to input CSV file
        output_csv: Path to save filtered CSV (defaults to input_name_filtered.csv)
    """
    if output_csv is None:
        output_csv = input_csv.replace('.csv', '_filtered.csv')
    
    # Read the CSV file
    df = pd.read_csv(input_csv)
    
    print(f"Original dataset: {len(df)} drugs")
    
    # Filter for rows that have both Japanese_Name and SMILES
    filtered_df = df[
        df['Japanese_Name'].notna() & 
        (df['Japanese_Name'].str.strip() != '') &
        df['SMILES'].notna() & 
        (df['SMILES'].str.strip() != '')
    ].copy()
    
    print(f"Filtered dataset: {len(filtered_df)} drugs with both Japanese names and SMILES")
    print(f"Removed: {len(df) - len(filtered_df)} incomplete entries")
    
    # Save the filtered dataset
    filtered_df.to_csv(output_csv, index=False)
    print(f"Filtered data saved to: {output_csv}")
    
    # Show some statistics
    if len(filtered_df) > 0:
        print("\nSample of filtered data:")
        print(filtered_df[['Drug_ID', 'Generic_Name', 'Japanese_Name', 'SMILES']].head())
        
        print(f"\nYear distribution in filtered data:")
        # Handle inconsistent date formats by extracting year directly
        filtered_df['Year'] = filtered_df['Date'].str[:4].astype(int)
        year_counts = filtered_df['Year'].value_counts().sort_index()
        print(year_counts)

if __name__ == "__main__":
    # Filter the KEGG small molecules CSV
    input_file = "kegg_small_molecules_2010-2025.csv"
    output_file = "kegg_small_molecules_complete.csv"
    filter_complete_kegg_data(input_file, output_file)