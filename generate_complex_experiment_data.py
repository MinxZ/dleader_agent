"""
Complex Experimental Data Generator

This script mimics a realistic scenario where multiple researchers over different time periods
recorded experimental data with different conventions, missing data, and various inconsistencies.

Scenario:
- Researcher A (5 years ago): Lost some data, used range notations like ">=10", "<100"
- Researcher B (2 years ago): Different naming conventions, mixed Japanese terms
- Junior researcher: Their own recording style, some data lost
"""

import json
import random
import re
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from dleader_agent.llm import get_llm


class ComplexExperimentDataGenerator:
    def __init__(self):
        self.llm = get_llm('claude-sonnet-4-5-20250929')
        self.compound_ids = []
        self.researcher_a_data = []
        self.researcher_b_data = []
        self.junior_researcher_data = []
        
        # Common chemical/biological properties that might be measured
        self.base_properties = [
            'LogP', 'MW', 'HBA', 'HBD', 'TPSA', 'RotBonds', 'AromaticRings',
            'IC50', 'EC50', 'Solubility', 'Permeability', 'Bioavailability'
        ]
        
        # Japanese property names for Researcher B
        self.japanese_properties = {
            'LogP': 'logp',  # lowercase variation
            'MW': '分子量',  # molecular weight in Japanese
            'Solubility': '溶解度',  # solubility in Japanese
            'IC50': 'ic_50_値',  # IC50 value in mixed Japanese
            'Permeability': '透過性',  # permeability in Japanese
        }
        
        # Junior researcher's creative naming
        self.junior_naming = {
            'LogP': 'lipophilicity_log',
            'MW': 'mol_wt_daltons',
            'IC50': 'inhibition_conc_50pct',
            'Solubility': 'aq_solub_mgml',
            'TPSA': 'polar_surf_area',
        }

    def generate_compound_ids(self, n_compounds=150):
        """Generate realistic compound IDs"""
        prefixes = ['COMP', 'MOL', 'CHEM', 'BIO', 'DRUG', 'EXP']
        self.compound_ids = []
        
        for i in range(n_compounds):
            prefix = random.choice(prefixes)
            number = random.randint(1000, 9999)
            suffix = random.choice(['', '-A', '-B', '-C', '_v1', '_v2'])
            self.compound_ids.append(f"{prefix}{number}{suffix}")
        
        return self.compound_ids

    def generate_researcher_a_data(self):
        """Generate Researcher A's data (5 years ago) with missing data and ranges"""
        print("Generating Researcher A data (5 years ago)...")
        
        # About 120 compounds with various issues
        available_compounds = random.sample(self.compound_ids, 120)
        
        for compound_id in available_compounds:
            record = {
                'compound_id': compound_id,
                'date_recorded': self._random_date_years_ago(5),
                'researcher': 'Dr. Smith (A)',
                'lab_notebook': f"NB-2019-{random.randint(10, 50)}"
            }
            
            # Generate properties with realistic research issues
            properties = {}
            
            # LogP - some exact values, some ranges, some missing
            logp_fate = random.choices(['exact', 'range', 'missing'], weights=[0.6, 0.3, 0.1])[0]
            if logp_fate == 'exact':
                properties['LogP'] = round(np.random.normal(2.5, 1.5), 2)
            elif logp_fate == 'range':
                if random.random() < 0.5:
                    properties['LogP'] = f">={random.randint(3, 8)}"
                else:
                    properties['LogP'] = f"<{random.randint(1, 5)}"
            else:
                properties['LogP'] = 'NaN'
            
            # MW - mostly available but some missing
            if random.random() < 0.85:
                properties['MW'] = round(np.random.normal(350, 100), 1)
            else:
                properties['MW'] = 'lost_data'
            
            # IC50 - often recorded as ranges due to assay limitations
            ic50_fate = random.choices(['exact', 'range', 'missing'], weights=[0.4, 0.4, 0.2])[0]
            if ic50_fate == 'exact':
                properties['IC50_uM'] = round(np.random.lognormal(1, 1.5), 3)
            elif ic50_fate == 'range':
                if random.random() < 0.7:
                    properties['IC50_uM'] = f">{random.randint(10, 100)}"
                else:
                    properties['IC50_uM'] = f"<{random.choice([0.1, 0.5, 1, 5])}"
            else:
                properties['IC50_uM'] = 'ND'  # Not determined
            
            # Solubility - often problematic measurements
            if random.random() < 0.7:
                sol_val = np.random.lognormal(-1, 1.5)
                if sol_val < 0.001:
                    properties['Solubility_mgmL'] = '<0.001'
                elif sol_val > 100:
                    properties['Solubility_mgmL'] = '>100'
                else:
                    properties['Solubility_mgmL'] = round(sol_val, 3)
            else:
                properties['Solubility_mgmL'] = 'insoluble'
            
            # Some additional properties with missing data
            if random.random() < 0.6:
                properties['TPSA'] = round(np.random.normal(80, 30), 1)
            
            if random.random() < 0.5:
                properties['HBD'] = random.randint(0, 8)
            
            record.update(properties)
            self.researcher_a_data.append(record)

    def generate_researcher_b_data(self):
        """Generate Researcher B's data (2 years ago) with different naming and Japanese"""
        print("Generating Researcher B data (2 years ago)...")
        
        # About 100 compounds, some overlap with A, some new
        overlap_compounds = random.sample(self.compound_ids[:80], 40)  # Some overlap
        new_compounds = random.sample(self.compound_ids[80:], 60)  # Some new
        available_compounds = overlap_compounds + new_compounds
        
        for compound_id in available_compounds:
            record = {
                'compound_id': compound_id,
                'date_recorded': self._random_date_years_ago(2),
                'researcher': 'Dr. Tanaka (B)',
                'experiment_series': f"EXP-{random.randint(200, 400)}",
                'notes': '実験ノート'  # "Experiment notes" in Japanese
            }
            
            # Use different property names and mix Japanese
            properties = {}
            
            # logp (lowercase) - Researcher B's style
            if random.random() < 0.8:
                properties['logp'] = round(np.random.normal(2.8, 1.2), 2)
            else:
                properties['logp'] = None
            
            # 分子量 (MW in Japanese)
            if random.random() < 0.75:
                properties['分子量'] = round(np.random.normal(380, 120), 1)
            
            # 溶解度 (Solubility in Japanese)
            if random.random() < 0.65:
                properties['溶解度_mg_per_ml'] = round(np.random.lognormal(0, 1.5), 3)
            else:
                properties['溶解度_mg_per_ml'] = '測定困難'  # "Difficult to measure"
            
            # ic_50_値 (IC50 value in mixed Japanese/English)
            if random.random() < 0.7:
                ic50_val = np.random.lognormal(0.5, 1.8)
                if ic50_val > 50:
                    properties['ic_50_値_μM'] = f'>{random.randint(50, 200)}'
                else:
                    properties['ic_50_値_μM'] = round(ic50_val, 2)
            else:
                properties['ic_50_値_μM'] = '未測定'  # "Not measured"
            
            # 透過性 (Permeability in Japanese)
            if random.random() < 0.5:
                properties['透過性_cm_per_s'] = f"{np.random.uniform(1e-7, 1e-4):.2e}"
            
            # Some English properties with B's naming style
            if random.random() < 0.6:
                properties['molecular_descriptors_tpsa'] = round(np.random.normal(85, 25), 1)
            
            if random.random() < 0.4:
                properties['h_bond_donors'] = random.randint(0, 6)
                properties['h_bond_acceptors'] = random.randint(0, 12)
            
            # Add some experimental conditions that B always recorded
            properties['temp_celsius'] = random.choice([25, 37, 40])
            properties['pH'] = round(random.uniform(6.5, 8.0), 1)
            
            record.update(properties)
            self.researcher_b_data.append(record)

    def generate_junior_researcher_data(self):
        """Generate Junior researcher's data with their own creative style"""
        print("Generating Junior researcher data...")
        
        # About 80 compounds, mix of existing and some new
        existing_compounds = random.sample(self.compound_ids[:100], 50)
        new_compounds = [f"JR{i:03d}" for i in range(1, 31)]  # Junior's own numbering
        available_compounds = existing_compounds + new_compounds
        
        for compound_id in available_compounds:
            record = {
                'compound_id': compound_id,
                'date_recorded': self._random_date_months_ago(random.randint(1, 18)),
                'researcher': 'Sarah Chen (Junior)',
                'project_code': f"PROJ-{random.randint(1, 20):02d}",
                'supervisor': random.choice(['Dr. Smith', 'Dr. Tanaka']),
                'data_quality': random.choice(['good', 'fair', 'needs_validation'])
            }
            
            # Junior researcher's creative naming conventions
            properties = {}
            
            # lipophilicity_log (Junior's name for LogP)
            if random.random() < 0.85:
                properties['lipophilicity_log'] = round(np.random.normal(2.3, 1.8), 2)
            else:
                properties['lipophilicity_log'] = 'LOST'  # Junior's note for missing data
            
            # mol_wt_daltons (Junior's name for MW)
            if random.random() < 0.9:
                properties['mol_wt_daltons'] = round(np.random.normal(340, 90), 1)
            
            # inhibition_conc_50pct (Junior's name for IC50)
            if random.random() < 0.8:
                ic50_val = np.random.lognormal(1.2, 1.3)
                if random.random() < 0.1:  # Junior sometimes uses different units
                    properties['inhibition_conc_50pct_nM'] = round(ic50_val * 1000, 1)
                else:
                    properties['inhibition_conc_50pct_uM'] = round(ic50_val, 3)
            else:
                properties['inhibition_conc_50pct_uM'] = 'TODO'  # Junior's todo note
            
            # aq_solub_mgml (Junior's name for aqueous solubility)
            if random.random() < 0.7:
                sol_val = np.random.lognormal(-0.5, 1.2)
                properties['aq_solub_mgml'] = round(sol_val, 4)
            else:
                properties['aq_solub_mgml'] = 'see_notebook_p47'  # Junior's reference style
            
            # polar_surf_area (Junior's name for TPSA)
            if random.random() < 0.6:
                properties['polar_surf_area'] = round(np.random.normal(75, 35), 1)
            
            # Junior also records some unique properties
            if random.random() < 0.7:
                properties['stability_days'] = random.randint(1, 30)
            
            if random.random() < 0.5:
                properties['color'] = random.choice(['white', 'yellow', 'brown', 'colorless', 'pink'])
            
            if random.random() < 0.3:
                properties['smell'] = random.choice(['odorless', 'sweet', 'pungent', 'fishy', 'none'])
            
            # Junior's experimental notes (sometimes incomplete)
            if random.random() < 0.4:
                properties['notes'] = random.choice([
                    'good_crystals', 'recrystallize_needed', 'check_purity',
                    'repeat_assay', 'sample_degraded?', 'verify_structure'
                ])
            
            record.update(properties)
            self.junior_researcher_data.append(record)

    def use_llm_for_realistic_variations(self):
        """Use LLM to generate some realistic property name variations and notes"""
        print("Using LLM to generate realistic variations...")
        
        messages = [
            {
                "role": "user", 
                "content": """Generate 10 realistic but slightly inconsistent ways that different researchers might name chemical/biological properties in their lab notebooks. Include some abbreviations, some full names, some with units embedded, some typos. Focus on properties like LogP, molecular weight, IC50, solubility, permeability, TPSA, etc.

Return as a JSON list of objects with 'standard_name' and 'researcher_variation' fields."""
            }
        ]
        
        try:
            response = self.llm.invoke(messages)
            variations_text = response.content if hasattr(response, 'content') else str(response)
            
            # Extract JSON from response
            json_match = re.search(r'\[.*\]', variations_text, re.DOTALL)
            if json_match:
                variations = json.loads(json_match.group())
                
                # Apply some of these variations to existing data
                self._apply_llm_variations_to_data(variations)
                
            return variations_text
        except Exception as e:
            print(f"LLM generation failed: {e}")
            return "Could not generate variations"

    def _apply_llm_variations_to_data(self, variations):
        """Apply LLM-generated variations to some existing data"""
        if not variations:
            return
            
        # Randomly apply variations to some records
        for dataset in [self.researcher_a_data, self.researcher_b_data, self.junior_researcher_data]:
            for record in random.sample(dataset, min(10, len(dataset))):
                variation = random.choice(variations)
                if 'standard_name' in variation and 'researcher_variation' in variation:
                    std_name = variation['standard_name']
                    var_name = variation['researcher_variation']
                    
                    # If the record has the standard name, sometimes rename it
                    if std_name in record and random.random() < 0.3:
                        record[var_name] = record.pop(std_name)

    def _random_date_years_ago(self, years):
        """Generate a random date from years ago"""
        start_date = datetime.now() - timedelta(days=years*365 + random.randint(-180, 180))
        return start_date.strftime("%Y-%m-%d")

    def _random_date_months_ago(self, months):
        """Generate a random date from months ago"""
        start_date = datetime.now() - timedelta(days=months*30 + random.randint(-30, 30))
        return start_date.strftime("%Y-%m-%d")

    def save_datasets(self, output_dir="data/"):
        """Save the generated datasets"""
        import os
        os.makedirs(output_dir, exist_ok=True)
        
        # Save each researcher's data
        researcher_a_df = pd.DataFrame(self.researcher_a_data)
        researcher_b_df = pd.DataFrame(self.researcher_b_data)
        junior_df = pd.DataFrame(self.junior_researcher_data)
        
        researcher_a_df.to_csv(f"{output_dir}researcher_a_2019_data.csv", index=False)
        researcher_b_df.to_csv(f"{output_dir}researcher_b_2022_data.csv", index=False)
        junior_df.to_csv(f"{output_dir}junior_researcher_data.csv", index=False)
        
        # Create a summary
        summary = {
            'generation_date': datetime.now().isoformat(),
            'total_compounds': len(self.compound_ids),
            'researcher_a_records': len(self.researcher_a_data),
            'researcher_b_records': len(self.researcher_b_data),
            'junior_researcher_records': len(self.junior_researcher_data),
            'data_quality_issues': {
                'range_values': 'Present in Researcher A data',
                'missing_data': 'Present in all datasets',
                'naming_inconsistencies': 'Different naming conventions across researchers',
                'language_mixing': 'Japanese terms in Researcher B data',
                'unit_inconsistencies': 'Different units used by different researchers'
            }
        }
        
        with open(f"{output_dir}dataset_summary.json", 'w', encoding='utf-8') as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)
        
        print(f"\n✅ Datasets saved to {output_dir}")
        print(f"   📊 Researcher A (2019): {len(self.researcher_a_data)} records")
        print(f"   📊 Researcher B (2022): {len(self.researcher_b_data)} records") 
        print(f"   📊 Junior Researcher: {len(self.junior_researcher_data)} records")
        
        return researcher_a_df, researcher_b_df, junior_df

    def generate_all_data(self):
        """Generate all experimental datasets"""
        print("🧪 Generating Complex Experimental Data Scenario")
        print("="*60)
        
        # Step 1: Generate compound IDs
        self.generate_compound_ids(150)
        print(f"✅ Generated {len(self.compound_ids)} compound IDs")
        
        # Step 2: Generate each researcher's data
        self.generate_researcher_a_data()
        print(f"✅ Generated Researcher A data: {len(self.researcher_a_data)} records")
        
        self.generate_researcher_b_data() 
        print(f"✅ Generated Researcher B data: {len(self.researcher_b_data)} records")
        
        self.generate_junior_researcher_data()
        print(f"✅ Generated Junior researcher data: {len(self.junior_researcher_data)} records")
        
        # Step 3: Use LLM for additional realism
        llm_variations = self.use_llm_for_realistic_variations()
        print("✅ Applied LLM-generated variations")
        
        return self.researcher_a_data, self.researcher_b_data, self.junior_researcher_data


def main():
    """Main function to generate and save complex experimental data"""
    generator = ComplexExperimentDataGenerator()
    
    # Generate all datasets
    researcher_a_data, researcher_b_data, junior_data = generator.generate_all_data()
    
    # Save datasets
    df_a, df_b, df_junior = generator.save_datasets()
    
    # Display sample data for verification
    print("\n📋 Sample Data Preview:")
    print("\n🔬 Researcher A (2019) - First 3 records:")
    print(df_a.head(3).to_string())
    
    print("\n🔬 Researcher B (2022) - First 3 records:")
    print(df_b.head(3).to_string())
    
    print("\n🔬 Junior Researcher - First 3 records:")
    print(df_junior.head(3).to_string())
    
    return generator


if __name__ == "__main__":
    generator = main()