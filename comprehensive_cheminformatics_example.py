"""
Comprehensive Cheminformatics Example: Descriptor Calculation to Modeling

This example demonstrates a complete workflow for cheminformatics modeling:
1. Calculate molecular descriptors from SMILES
2. Detect need for log transformation 
3. Comprehensive preprocessing pipeline
4. Feature selection (correlation and importance filtering)
5. Model training and evaluation (regression and classification)
6. Results visualization and model saving

Dataset: ChEMBL34 fraction unbound in plasma (fup) data
File: data/data/20240610_chembl34_extraxt_fup_human_1c1d.csv
SMILES Column: canonical_smiles
Target Property: fup_converted
"""

import os

from dleader_agent.agent.a1 import A1


def create_cheminformatics_agent():
    """Create an agent configured for cheminformatics workflow."""
    
    # Initialize agent with preprocessing and modeling tools
    agent = A1(
        use_tool_retriever=True,
        download_data_lake=False,
        llm='claude-sonnet-4-20250514'
    )
    
    # Clear default data lake
    agent.data_lake_dict = {}
    
    # Essential packages for cheminformatics
    essential_packages = {
        'pandas': 'Data manipulation and analysis library',
        'numpy': 'Numerical computing library',
        'scikit-learn': 'Machine learning library',
        'scipy': 'Scientific computing library',
        'matplotlib': 'Plotting library',
        'seaborn': 'Statistical data visualization',
        'rdkit': 'Chemical informatics and descriptor calculation library',
        'joblib': 'Model persistence library'
    }
    agent.library_content_dict = essential_packages
    
    # Keep preprocessing and modeling tools
    relevant_modules = {
        'dleader_agent.tool.preprocessing': agent.module2api.get('dleader_agent.tool.preprocessing', []),
        'dleader_agent.tool.modeling': agent.module2api.get('dleader_agent.tool.modeling', [])
    }
    agent.module2api = relevant_modules
    
    # Add the ChEMBL dataset
    agent.data_lake_dict = {
        '20240610_chembl34_extraxt_fup_human_1c1d.csv': 
        'ChEMBL34 fraction unbound in plasma data with SMILES strings and fup_converted values (molecular dataset for QSAR modeling)'
    }
    
    # Reconfigure agent
    # agent.configure()
    
    print("✅ Configured cheminformatics agent with:")
    print(f"   📦 {len(essential_packages)} essential packages")
    print(f"   🔧 {sum(len(tools) for tools in relevant_modules.values())} tools available")
    print(f"   📊 {len(agent.data_lake_dict)} dataset loaded")
    

    return agent


def example_complete_cheminformatics_workflow():
    """Complete cheminformatics workflow example."""
    
    print("🧪 Complete Cheminformatics Workflow Example")
    print("="*60)
    
    # Create agent
    agent = create_cheminformatics_agent()
    
    log, result = agent.go("""
    I need to perform a complete cheminformatics modeling workflow on the ChEMBL dataset. 
    The data file is 'data/data/20240610_chembl34_extraxt_fup_human_1c1d.csv' with:
    - SMILES column: 'canonical_smiles' 
    - Target property: 'fup_converted' (fraction unbound in plasma)
    
    Please execute this comprehensive workflow using the enhanced RDKit descriptor calculation functions:
    
    ## Phase 1: Data Loading and Initial Analysis
    1. Load the dataset and inspect its structure using load_and_inspect_data()
    2. Check the SMILES column and target property distribution
    3. Detect any missing values or data quality issues
    
    ## Phase 2: Enhanced Molecular Descriptor Calculation
    4. Use smiles_to_descriptors() function to calculate RDKit descriptors with parallel processing
    5. Apply analyze_descriptor_quality() to assess descriptor quality and identify issues
    6. Use filter_descriptors_by_quality() to remove problematic descriptors
    7. Save the dataset with quality-filtered descriptors for future use
    8. Report on descriptor calculation success rates and quality metrics
    
    ## Phase 3: Target Property Analysis
    7. Analyze the fup_converted distribution for skewness and normality
    8. Use detect_log_transformation_need() to determine if log transformation is needed
    9. Apply the recommended transformation if suggested
    
    ## Phase 4: Enhanced Preprocessing Pipeline
    10. Use clean_error_objects() to clean any error objects from descriptor calculations
    11. Apply detect_infinity_and_large_values() to identify problematic values
    12. Use remove_problematic_columns() to clean the dataset
    13. Generate a comprehensive preprocessing report
    
    ## Phase 5: Feature Selection
    14. Remove highly correlated descriptors (threshold 0.95)
    15. Remove low importance descriptors using Random Forest (threshold 0.001)
    16. Use select_best_features_comprehensive() for the complete pipeline
    17. Visualize feature selection results
    
    ## Phase 6: Regression Modeling
    18. Train a Random Forest regression model on the processed data
    19. Evaluate model performance with cross-validation
    20. Analyze feature importance for the final model
    21. Create regression diagnostic plots
    22. Save the trained regression model
    
    ## Phase 7: Classification Modeling  
    23. Convert the target to binary classification using threshold 0.05
    24. Train a Random Forest classification model
    25. Evaluate classification performance with detailed metrics
    26. Create classification diagnostic plots including confusion matrix and ROC curve
    27. Save the trained classification model
    
    ## Phase 8: Results Summary
    28. Provide a comprehensive summary of:
        - Dataset statistics (before/after preprocessing)
        - Feature selection results (original vs final feature count)
        - Model performance metrics (regression R², classification accuracy)
        - Recommendations for model usage and interpretation
    
    Use the complete preprocessing and modeling toolkit. Create visualizations where appropriate.
    Save models with descriptive names including date/performance metrics.
    """)
    
    print("📋 Agent Response:")
    print(result)
    return log, result


def example_step_by_step_workflow():
    """Step-by-step workflow with intermediate checks."""
    
    print("🔬 Step-by-Step Cheminformatics Workflow")
    print("="*60)
    
    agent = create_cheminformatics_agent()
    
    # Step 1: Data loading and descriptor calculation
    print("\n📍 Step 1: Data Loading and Descriptor Calculation")
    log1, result1 = agent.go("""
    Let's start with the first phase of our enhanced cheminformatics workflow:
    
    1. Use load_and_inspect_data() to load 'data/data/20240610_chembl34_extraxt_fup_human_1c1d.csv'
    2. Inspect the dataset structure and check data quality
    3. Use smiles_to_descriptors() to calculate molecular descriptors from 'canonical_smiles' column with parallel processing
    4. Apply analyze_descriptor_quality() to assess the quality of calculated descriptors
    5. Use filter_descriptors_by_quality() to remove problematic descriptors (constant, low variance, highly correlated)
    6. Show comprehensive statistics about the descriptor calculation and filtering process
    
    Focus on getting high-quality descriptors using the new enhanced functions and report detailed quality metrics.
    """)
    
    # Step 2: Preprocessing and transformation analysis
    print("\n📍 Step 2: Target Analysis and Preprocessing")
    log2, result2 = agent.go("""
    Now let's analyze the target property and perform enhanced preprocessing:
    
    1. Use detect_log_transformation_need() to analyze 'fup_converted' distribution 
    2. Apply apply_log_transformation() if recommended
    3. Use clean_error_objects() to clean any error objects from descriptors
    4. Apply detect_infinity_and_large_values() to find problematic descriptor columns
    5. Use remove_problematic_columns() to clean the dataset
    6. Generate comprehensive preprocessing report showing before/after statistics
    
    Use the enhanced preprocessing functions and preserve transformation information for later use.
    """)
    
    # Step 3: Feature selection and modeling
    print("\n📍 Step 3: Feature Selection and Modeling")
    log3, result3 = agent.go("""
    Finally, let's perform feature selection and build models:
    
    1. Apply comprehensive feature selection (correlation + importance filtering)
    2. Train Random Forest regression model on selected features
    3. Train Random Forest classification model (threshold 0.05)
    4. Evaluate both models with appropriate metrics and visualizations
    5. Save both models with descriptive names
    
    Provide final recommendations for model deployment and usage.
    """)
    
    return [(log1, result1), (log2, result2), (log3, result3)]


def example_quick_modeling_workflow():
    """Quick workflow focusing on key steps."""
    
    print("⚡ Quick Cheminformatics Modeling")
    print("="*60)
    
    agent = create_cheminformatics_agent()
    
    log, result = agent.go("""
    Perform a streamlined cheminformatics modeling workflow using enhanced functions:
    
    1. Use load_and_inspect_data() to load 'data/data/20240610_chembl34_extraxt_fup_human_1c1d.csv'
    2. Apply smiles_to_descriptors() to calculate descriptors from 'canonical_smiles' with quality filtering
    3. Use detect_log_transformation_need() for 'fup_converted' and apply transformation if recommended
    4. Apply enhanced preprocessing with clean_error_objects() and detect_infinity_and_large_values()
    5. Use comprehensive feature selection to reduce descriptor dimensionality
    6. Train and evaluate Random Forest models for both regression and classification
    7. Save best models with descriptive names and provide performance summary
    
    Focus on automation and efficiency using the new enhanced descriptor calculation and preprocessing functions.
    """)
    
    print("📋 Agent Response:")
    print(result)
    return log, result


if __name__ == "__main__":
    print("🧬 Comprehensive Cheminformatics Workflow Examples")
    print("="*80)
    
    # Check if data file exists
    data_file = "data/data/20240610_chembl34_extraxt_fup_human_1c1d.csv"
    if not os.path.exists(data_file):
        print(f"⚠️  Warning: Data file not found at {data_file}")
        print("   Please ensure the ChEMBL dataset is available at the specified path")
    
    # Available examples
    examples = [
        ("Complete Workflow", example_complete_cheminformatics_workflow),
        ("Step-by-Step Workflow", example_step_by_step_workflow),
        ("Quick Modeling", example_quick_modeling_workflow),
    ]
    
    print("\nAvailable examples:")
    for i, (name, _) in enumerate(examples, 1):
        print(f"  {i}. {name}")
    
    # Run examples
    choice = input("\nEnter example number to run (1-3, or 'all' for all): ").strip()
    
    results = {}
    
    if choice.lower() == 'all':
        selected_examples = examples
    else:
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(examples):
                selected_examples = [examples[idx]]
            else:
                print("Invalid choice. Running complete workflow.")
                selected_examples = [examples[0]]
        except ValueError:
            print("Invalid input. Running complete workflow.")
            selected_examples = [examples[0]]
    
    for name, example_func in selected_examples:
        try:
            print(f"\n🔄 Running: {name}")
            print("-" * 60)
            
            result = example_func()
            
            if result:
                results[name] = {"status": "success"}
                print(f"✅ Completed: {name}")
            else:
                results[name] = {"status": "skipped"}
                print(f"⏭️ Skipped: {name}")
                
        except Exception as e:
            print(f"❌ Error in {name}: {str(e)}")
            results[name] = {"status": "failed", "error": str(e)}
    
    # Summary
    print("\n" + "="*80)
    print("📊 EXECUTION SUMMARY")
    print("="*80)
    
    for name, result in results.items():
        status_icons = {"success": "✅", "failed": "❌", "skipped": "⏭️"}
        icon = status_icons.get(result["status"], "❓")
        print(f"{icon} {name}")
        if "error" in result:
            print(f"   └─ Error: {result['error']}")
    
    print("\n🔬 Workflow Components:")
    print("   • Molecular descriptor calculation (RDKit)")
    print("   • Log transformation detection and application")
    print("   • Comprehensive preprocessing pipeline")
    print("   • Feature selection (correlation + importance)")
    print("   • Regression and classification modeling")
    print("   • Model evaluation and visualization")
    print("   • Model persistence for deployment")
    
    print("\n💡 Key Features Demonstrated:")
    print("   ✓ Enhanced SMILES to molecular descriptors conversion with parallel processing")
    print("   ✓ Automated descriptor quality analysis and filtering") 
    print("   ✓ Statistical analysis for transformation detection")
    print("   ✓ Advanced data quality assessment with error object cleaning")
    print("   ✓ Intelligent feature selection with correlation and importance filtering")
    print("   ✓ Dual modeling (regression + classification)")
    print("   ✓ Comprehensive evaluation and visualization")
    print("   ✓ Production-ready model saving with quality metrics")
    
    print("\n📁 Expected Outputs:")
    print("   • descriptors_dataset.csv (data with calculated descriptors)")
    print("   • fup_regression_model_YYYYMMDD.pkl (trained regression model)")
    print("   • fup_classification_model_YYYYMMDD.pkl (trained classification model)")
    print("   • Feature selection and model evaluation plots")
    print("   • Comprehensive performance reports")