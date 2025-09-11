"""
Inference Script for ChEMBL fup Property Prediction

This script demonstrates how to use a trained model and preprocessing pipeline
to predict molecular properties for new molecules. It loads the saved preprocessing
pipeline and models, then applies the same transformations to new SMILES strings.

Usage:
    python inference_ml.py

Requirements:
    - preprocessing_pipeline.json (from training)
    - Model files (.pkl files from training)
    - dleader_agent package with inference functions
"""

import os
from datetime import datetime

# Import inference functions
from dleader_agent.tool.preprocessing import (load_preprocessing_pipeline,
                                       apply_inference_preprocessing)
from dleader_agent.tool.modeling import (predict_with_pipeline,
                                  create_prediction_summary)


def predict_molecular_properties(smiles_list, pipeline_path="preprocessing_pipeline.json", verbose=True):
    """
    Predict molecular properties for new SMILES strings using trained pipeline.
    
    Args:
        smiles_list (list): List of SMILES strings to predict
        pipeline_path (str): Path to the preprocessing pipeline JSON file
        verbose (bool): Whether to print detailed progress
        
    Returns:
        dict: Comprehensive prediction results
    """
    
    if verbose:
        print("🔮 Molecular Property Inference Pipeline")
        print("="*50)
        print(f"📊 Input: {len(smiles_list)} molecule(s)")
    
    # Step 1: Load preprocessing pipeline
    if verbose:
        print(f"\n📍 Step 1: Loading preprocessing pipeline")
    
    if not os.path.exists(pipeline_path):
        raise FileNotFoundError(f"Preprocessing pipeline not found: {pipeline_path}")
    
    pipeline_metadata = load_preprocessing_pipeline(pipeline_path)
    
    # Step 2: Apply preprocessing to new molecules
    if verbose:
        print(f"\n📍 Step 2: Preprocessing new molecules")
    
    processed_data = apply_inference_preprocessing(
        smiles_list=smiles_list,
        pipeline_metadata=pipeline_metadata,
        verbose=verbose
    )
    
    if processed_data is None:
        print("❌ Preprocessing failed - no valid molecules")
        return None
    
    # Step 3: Make predictions
    if verbose:
        print(f"\n📍 Step 3: Making predictions")
    
    predictions = predict_with_pipeline(
        processed_data=processed_data,
        pipeline_metadata=pipeline_metadata,
        verbose=verbose
    )
    
    # Step 4: Create comprehensive summary
    if verbose:
        print(f"\n📍 Step 4: Creating prediction summary")
    
    # Generate output filename with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = f"molecular_predictions_{timestamp}.csv"
    
    summary_df = create_prediction_summary(
        predictions=predictions,
        processed_data=processed_data,
        pipeline_metadata=pipeline_metadata,
        output_path=output_file
    )
    
    # Step 5: Results summary
    if verbose:
        print(f"\n📍 Step 5: Results Summary")
        print("="*50)
        
        preprocessing_stats = processed_data['preprocessing_summary']
        print(f"🧬 Preprocessing Results:")
        print(f"   Input molecules: {preprocessing_stats['original_molecules']}")
        print(f"   Valid molecules: {preprocessing_stats['valid_molecules']}")
        print(f"   Success rate: {preprocessing_stats['success_rate']:.1f}%")
        print(f"   Features used: {preprocessing_stats['features_available']}")
        
        print(f"\n🤖 Model Information:")
        print(f"   Pipeline version: {pipeline_metadata['pipeline_info']['pipeline_version']}")
        print(f"   Pipeline created: {pipeline_metadata['pipeline_info']['created_at']}")
        print(f"   Model type: {pipeline_metadata['model_info']['model_type']}")
        
        if 'regression' in predictions:
            r2 = pipeline_metadata['model_info']['performance']['regression_r2']
            print(f"   Regression R²: {r2:.4f}")
            
        if 'classification' in predictions:
            acc = pipeline_metadata['model_info']['performance']['classification_accuracy']
            if acc:
                print(f"   Classification accuracy: {acc:.4f}")
        
        print(f"\n📊 Predictions:")
        if 'regression' in predictions:
            reg_preds = predictions['regression']['predicted_values']
            print(f"   Regression predictions: min={min(reg_preds):.4f}, max={max(reg_preds):.4f}, mean={sum(reg_preds)/len(reg_preds):.4f}")
            
        if 'classification' in predictions:
            class_preds = predictions['classification']['predicted_classes']
            from collections import Counter
            class_dist = Counter(class_preds)
            print(f"   Classification predictions: {dict(class_dist)}")
        
        print(f"\n💾 Output saved to: {output_file}")
    
    return {
        'predictions': predictions,
        'processed_data': processed_data,
        'pipeline_metadata': pipeline_metadata,
        'summary_dataframe': summary_df,
        'output_file': output_file
    }


def main():
    """Main inference demonstration."""
    
    print("🧬 ChEMBL fup Property Prediction - Inference Example")
    print("="*60)
    
    # Test molecules (including the requested "CCC")
    test_smiles = [
        "CCC",                    # Propane (simple alkane)
        "CCO",                    # Ethanol  
        "c1ccccc1",              # Benzene
        "CC(=O)Nc1ccc(O)cc1",    # Acetaminophen (paracetamol)
        "CCN(CC)CC",             # Triethylamine
        "INVALID_SMILES"         # Invalid SMILES to test error handling
    ]
    
    print(f"🧪 Test molecules:")
    for i, smiles in enumerate(test_smiles, 1):
        print(f"   {i}. {smiles}")
    
    try:
        # Run inference
        results = predict_molecular_properties(
            smiles_list=test_smiles,
            pipeline_path="preprocessing_pipeline.json",
            verbose=True
        )
        
        if results:
            print(f"\n{'='*60}")
            print("✅ INFERENCE COMPLETED SUCCESSFULLY!")
            print(f"{'='*60}")
            
            # Display individual predictions
            summary_df = results['summary_dataframe']
            print(f"\n📋 Individual Predictions:")
            print("-" * 60)
            
            for idx, row in summary_df.iterrows():
                smiles = row['SMILES']
                print(f"\n🧬 Molecule: {smiles}")
                
                # Show regression prediction if available
                target_col = results['pipeline_metadata']['preprocessing']['target_transformation']['target_column']
                if f'Predicted_{target_col}' in row:
                    pred_value = row[f'Predicted_{target_col}']
                    r2 = row.get('Model_R2', 'N/A')
                    print(f"   📈 Predicted {target_col}: {pred_value:.4f} (R²: {r2:.4f})")
                
                # Show classification prediction if available
                if 'Predicted_Class' in row:
                    pred_class = row['Predicted_Class']
                    threshold = row.get('Classification_Threshold', 'N/A')
                    accuracy = row.get('Classification_Accuracy', 'N/A')
                    print(f"   🎯 Predicted class: {pred_class} (threshold: {threshold}, accuracy: {accuracy:.4f})")
                    
                    if 'Predicted_Probability' in row:
                        prob = row['Predicted_Probability']
                        print(f"   📊 Probability: {prob:.4f}")
                
                features_used = row.get('Features_Used', 'N/A')
                print(f"   🔧 Features used: {features_used}")
            
            print(f"\n💡 Usage Notes:")
            print(f"   • Predictions are based on the trained model performance")
            print(f"   • Results saved to: {results['output_file']}")
            print(f"   • Pipeline can be reused for any new molecules")
            print(f"   • Invalid SMILES are automatically filtered out")
            
        else:
            print("\n❌ Inference failed - check error messages above")
            
    except FileNotFoundError as e:
        print(f"\n❌ Required files missing: {e}")
        print("   Make sure you have run the training script first to generate:")
        print("   • preprocessing_pipeline.json")
        print("   • Model files (.pkl)")
        
    except Exception as e:
        print(f"\n❌ Error during inference: {e}")
        import traceback
        traceback.print_exc()
    
    print(f"\n{'='*60}")
    print("🔍 INFERENCE PIPELINE COMPARISON:")
    print("   📊 Traditional approach: Manual feature engineering, separate preprocessing")
    print("   ⚡ New approach: Automated pipeline replication, consistent transformations")  
    print("   🛡️ Built-in validation and error handling")
    print("   📈 Preserves all training preprocessing steps")
    print("   💾 Comprehensive results and metadata")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()