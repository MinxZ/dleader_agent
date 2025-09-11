
# Example: Complete Preprocessing Pipeline Usage
# ============================================

from dleader_agent.tool.preprocessing import *
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score

# Initialize and run the pipeline
pipeline = MLPreprocessingPipeline()

# Load data
pipeline.load_data('your_dataset.csv')

# Assess quality
quality_issues = pipeline.assess_data_quality()
print("Data quality issues:", quality_issues)

# Preprocess
pipeline.preprocess(save_path='cleaned_data.csv')

# Get ML-ready data
ml_data = pipeline.get_ml_ready_data('target_column')

# Train a simple model
model = RandomForestClassifier(random_state=42)
model.fit(ml_data['X_train'], ml_data['y_train'])

# Evaluate
predictions = model.predict(ml_data['X_test'])
accuracy = accuracy_score(ml_data['y_test'], predictions)
print(f"Model accuracy: {accuracy:.4f}")

# Get summary
print(pipeline.get_summary())
