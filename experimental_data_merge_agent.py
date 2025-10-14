"""
Experimental Data Merger Agent

This agent processes and merges experimental datasets from multiple researchers
with different naming conventions, missing data, and recording styles.
The agent must intelligently analyze and merge the data without prior knowledge
of the specific data structures.
"""

from dleader_agent.agent.a1 import A1


def create_data_merge_agent():
    """Create an agent configured for experimental data merging tasks."""
    
    # Initialize agent
    agent = A1(
        use_tool_retriever=True,
        download_data_lake=False, 
        llm='claude-sonnet-4-5-20250929'
    )
    
    # Clear default data lake to avoid distractions
    agent.data_lake_dict = {}
    
    # Keep essential packages for data processing and merging
    essential_packages = {
        'pandas': 'Data manipulation and analysis library with powerful merging capabilities',
        'numpy': 'Numerical computing library for handling arrays and missing data', 
        'scikit-learn': 'Machine learning library with preprocessing and data transformation tools',
        'scipy': 'Scientific computing library for statistical analysis',
        'matplotlib': 'Plotting library for data visualization',
        'seaborn': 'Statistical data visualization library',
        'fuzzywuzzy': 'Fuzzy string matching for column name standardization',
        'regex': 'Advanced regular expression operations for data parsing'
    }
    agent.library_content_dict = essential_packages
    
    # Filter module2api to keep only preprocessing and analysis tools
    preprocessing_modules = {
        # 'dleader_agent.tool.preprocessing': agent.module2api.get('dleader_agent.tool.preprocessing', [])
    }
    agent.module2api = preprocessing_modules
    agent.data_lake_dict = {}

    # Reconfigure agent with setup
    # agent.configure()s
    
    print("✅ Configured data merge agent with:")
    print(f"   📦 {len(essential_packages)} essential packages")
    print(f"   📊 {len(agent.data_lake_dict)} data lake items (empty - will be populated)")
    
    return agent


def experimental_data_merger_example():
    """Example using data merge agent to process and merge experimental datasets."""
    
    print("🧪 Experimental Data Merger Agent")
    print("="*60)
    
    # Create data merge agent
    agent = create_data_merge_agent()
    
    # Add the three experimental datasets without revealing their structure
    agent.data_lake_dict = {
        # 'researcher_a_2019_data.csv': 'Experimental data from Researcher A (2019) - contains chemical properties with some missing values and range notations',
        # 'researcher_b_2022_data.csv': 'Experimental data from Researcher B (2022) - uses different naming conventions and contains some non-English terms',
        # 'junior_researcher_data.csv': 'Experimental data from Junior Researcher - recorded with personal conventions and some incomplete entries'
        'data/researcher_a_2019_data.csv': 'Experimental data from Researcher A (2019) - contains chemical properties with some missing values and range notations',
        'data/researcher_b_2022_data.csv': 'Experimental data from Researcher B (2022) - uses different naming conventions and contains some non-English terms',
        'data/junior_researcher_data.csv': 'Experimental data from Junior Researcher - recorded with personal conventions and some incomplete entries'
    }
    
    # Reconfigure after adding datasets
    agent.configure()
    
    log, result = agent.go("""
    You have been given three experimental datasets from different researchers collected at different times.
    These datasets contain chemical/biological experimental data but were recorded by different people
    with different conventions, naming styles, and data recording practices.
    
    IMPORTANT: MEMORY MANAGEMENT FOR LARGE DATASETS
    - DO NOT load entire datasets into memory at once
    - Use pandas.read_csv() with chunksize parameter to read data in chunks
    - Process datasets in manageable portions (e.g., chunksize=1000 or 5000 rows)
    - Use iterator-based processing to handle large files efficiently
    - Only load the full dataset if you confirm it's small enough (<10MB or <50k rows)
    - For initial exploration, use pd.read_csv(nrows=100) to examine structure first
    
    YOUR MISSION:
    Intelligently analyze, process, and merge these three datasets into a single, unified, analysis-ready dataset.
    
    EXPECTED CHALLENGES (you need to discover and solve):
    - Different column naming conventions across datasets
    - Missing or incomplete data entries
    - Range values (like ">=10" or "<100") instead of exact measurements
    - Mixed languages/terms in column names
    - Different units or measurement scales
    - Inconsistent compound identification systems
    - Data quality issues from different recording practices
    - Large dataset sizes that require chunked processing
    
    REQUIREMENTS:
    1. **Data Discovery**: Load and thoroughly examine all three datasets using chunked reading
    2. **Structure Analysis**: Identify what each dataset contains and how they relate
    3. **Column Mapping**: Intelligently map similar columns across datasets (e.g., LogP vs logp vs lipophilicity_log)
    4. **Data Standardization**: 
       - Standardize column names to consistent naming convention
       - Handle range values and convert to usable numeric data where possible
       - Deal with missing data appropriately
       - Standardize units where needed
    5. **Intelligent Merging**: Merge the datasets using appropriate join strategies with chunked processing
    6. **Quality Assessment**: Provide comprehensive data quality metrics
    7. **Final Dataset**: Create a clean, analysis-ready merged dataset
    
    SUCCESS METRICS (KPIs):
    - Successfully merge all three datasets into one unified dataset
    - Achieve >95% compound coverage (minimize data loss during merge)
    - Standardize at least 80% of overlapping property columns
    - Handle all range values and missing data with documented strategies
    - Provide clear before/after statistics showing data improvement
    - Generate a comprehensive data quality and merging report
    - Save the final merged dataset as 'merged_experimental_data.csv'
    
    DELIVERABLES:
    1. Final merged dataset saved to file
    2. Data quality assessment report
    3. Column mapping and standardization documentation
    4. Before/after comparison statistics
    5. Recommendations for further data analysis
    
    You must figure out the optimal merging strategy based on the actual data content.
    Do not make assumptions - examine the data first to understand its structure and quality.
    """)
    
    print("📋 Agent Response:")
    print(result)
    return log, result


if __name__ == "__main__":
    print("🧬 Experimental Data Merger Agent")
    print("="*60)
    
    # Run the data merging example
    examples = [
        ("Experimental Data Merger", experimental_data_merger_example),
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
    
    print("\n🎯 SUCCESS CRITERIA:")
    print("   • >95% compound coverage in merged dataset")
    print("   • >80% column standardization rate") 
    print("   • All range values handled appropriately")
    print("   • Comprehensive data quality report generated")
    print("   • Final merged dataset saved and ready for analysis")
    
    print("\n💡 AGENT OBJECTIVES:")
    print("   • Intelligent discovery of data structure and relationships")
    print("   • Automated column mapping and standardization")
    print("   • Robust handling of messy real-world experimental data")
    print("   • Generation of analysis-ready unified dataset")