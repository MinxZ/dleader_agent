"""
Example: Minimal Agent Configuration for Preprocessing Only

This example shows how to configure the dleader_agent agent to use only 
preprocessing tools without default data lake and packages.
"""

from dleader_agent.agent.a1 import A1


def create_minimal_preprocessing_agent():
    """Create an agent configured only for preprocessing tasks."""
    
    # Initialize agent without downloading default data lake
    agent = A1(
        use_tool_retriever=True,
        download_data_lake=False, llm='claude-sonnet-4-5-20250929'
    )
    
    # Clear default data lake to avoid distractions
    agent.data_lake_dict = {}
    
    # Keep only essential packages for preprocessing
    essential_packages = {
        'pandas': 'Data manipulation and analysis library',
        'numpy': 'Numerical computing library', 
        'scikit-learn': 'Machine learning library with preprocessing tools',
        'scipy': 'Scientific computing library'
    }
    agent.library_content_dict = essential_packages
    
    # Filter module2api to keep only preprocessing tools
    preprocessing_modules = {
        'dleader_agent.tool.preprocessing': agent.module2api.get('dleader_agent.tool.preprocessing', [])
    }
    agent.module2api = preprocessing_modules
    
    agent.data_lake_dict = {}
    # Reconfigure agent with minimal setup
    # agent.configure()
    
    print("✅ Configured minimal agent with:")
    print(f"   📦 {len(essential_packages)} essential packages")
    # print(f"   🔧 {len(preprocessing_modules.get('dleader_agent.tool.preprocessing', []))} preprocessing tools")
    print(f"   📊 {len(agent.data_lake_dict)} data lake items (empty)")
    
    return agent

def example_minimal_preprocessing():
    """Example using minimal agent configuration with real data."""
    
    print("🚀 Minimal Preprocessing Agent Example")
    print("="*50)
    
    # Create minimal agent
    agent = create_minimal_preprocessing_agent()
    
    # Add real data descriptions (these files exist in data/)
    agent.data_lake_dict = {
        'my_dataset.csv': 'Patient demographics and outcomes with missing values and outliers (510 rows)',
        'experiment_data.csv': 'Laboratory experiment results with mixed data types (300 rows)',
        'survey_responses.json': 'Nested survey responses in JSON format (200 responses)'
    }
    
    # Reconfigure after adding custom data
    agent.configure()
    
    log, result = agent.go("""
    I have real datasets in the data/data/ directory that need preprocessing:
    
    1. my_dataset.csv contains:
       - patient_id: unique identifier
       - age: numeric (some missing values, outliers around 120-150)
       - gender: categorical (M/F/Other)
       - diagnosis: categorical (Hypertension, Diabetes, Heart Disease, etc.)
       - treatment_response: numeric score (0-100, has outliers 150-200)
       - follow_up_months: numeric
       - bmi: numeric (some missing values)
       - blood_pressure_systolic: numeric
       - blood_pressure_diastolic: numeric
       - Contains ~15% missing values and duplicate rows
    
    Please:
    1. Load and inspect the data from 'data/data/my_dataset.csv'
    2. Detect and report all data quality issues
    3. Handle missing values using appropriate strategies for each column type
    4. Remove outliers from treatment_response and age using IQR method
    5. Encode categorical variables (gender, diagnosis) for machine learning
    6. Normalize all numeric features using standard scaling
    7. Generate a comprehensive preprocessing report
    8. Show before/after statistics
    
    Use only preprocessing tools - load the actual file and process real data.
    """)
    
    print("📋 Agent Response:")
    print(result)
    return log, result


if __name__ == "__main__":
    print("🧬 Minimal dleader_agent Agent - Preprocessing Only")
    print("="*60)
    
    # Run examples
    examples = [
        ("Minimal Preprocessing Setup", example_minimal_preprocessing),
    ]
    
    results = {}
    
    for name, example_func in examples:
        try:
            print(f"\n🔄 Running: {name}")
            log, result = example_func()
            if log and result:
                results[name] = {"status": "success"}
                print(f"✅ Completed: {name}")
            else:
                results[name] = {"status": "skipped"}
                print(f"⏭️ Skipped: {name}")
        except Exception as e:
            print(f"❌ Error in {name}: {str(e)}")
            results[name] = {"status": "failed", "error": str(e)}
    
    # Summary
    print("\n" + "="*60)
    print("📊 EXECUTION SUMMARY")
    print("="*60)
    
    for name, result in results.items():
        status_icons = {"success": "✅", "failed": "❌", "skipped": "⏭️"}
        icon = status_icons.get(result["status"], "❓")
        print(f"{icon} {name}")
        if "error" in result:
            print(f"   └─ Error: {result['error']}")
    