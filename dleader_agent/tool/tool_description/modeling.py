"""
Tool descriptions for machine learning modeling functions.

This module contains the API descriptions for all modeling tools,
formatted for the dleader_agent agent system.
"""

description = [
    {
        "name": "train_regression_model",
        "description": "Train a regression model with comprehensive evaluation including multiple algorithms (Random Forest, Linear Regression, SVR, KNN), optional K-fold cross-validation, and detailed performance metrics. When using cross-validation, returns ensemble of models trained on different folds for robust predictions.",
        "module": "dleader_agent.tool.modeling",
        "required_parameters": [
            {"name": "data", "type": "pd.DataFrame", "description": "Input dataset containing features and target"},
            {"name": "target_column", "type": "str", "description": "Name of the target variable column for regression"}
        ],
        "optional_parameters": [
            {"name": "feature_columns", "type": "list", "description": "List of feature column names (None for all except target)", "default": None},
            {"name": "model_type", "type": "str", "description": "Type of regression model: 'random_forest', 'linear', 'svr', 'knn'", "default": "random_forest"},
            {"name": "test_size", "type": "float", "description": "Proportion of dataset for testing (ignored if use_cross_validation=True)", "default": 0.2},
            {"name": "random_state", "type": "int", "description": "Random state for reproducibility", "default": 42},
            {"name": "model_params", "type": "dict", "description": "Additional model-specific parameters", "default": None},
            {"name": "use_cross_validation", "type": "bool", "description": "Whether to use K-fold cross-validation instead of train/test split", "default": False},
            {"name": "n_splits", "type": "int", "description": "Number of splits for K-fold cross-validation", "default": 5}
        ],
        "return_type": "dict",
        "return_description": "Dictionary containing trained model(s), predictions, evaluation metrics, and dataset information. When using cross-validation, includes ensemble of models and cross-validated predictions."
    },
    {
        "name": "train_classification_model",
        "description": "Train a classification model with comprehensive evaluation including multiple algorithms (Random Forest, Logistic Regression, SVC, KNN), optional K-fold cross-validation, stratified sampling, and detailed performance metrics including confusion matrix and ROC analysis. When using cross-validation, returns ensemble of models trained on different folds for robust predictions.",
        "module": "dleader_agent.tool.modeling",
        "required_parameters": [
            {"name": "data", "type": "pd.DataFrame", "description": "Input dataset containing features and target"},
            {"name": "target_column", "type": "str", "description": "Name of the target variable column for classification"}
        ],
        "optional_parameters": [
            {"name": "feature_columns", "type": "list", "description": "List of feature column names (None for all except target)", "default": None},
            {"name": "model_type", "type": "str", "description": "Type of classification model: 'random_forest', 'logistic', 'svc', 'knn'", "default": "random_forest"},
            {"name": "test_size", "type": "float", "description": "Proportion of dataset for testing (ignored if use_cross_validation=True)", "default": 0.2},
            {"name": "random_state", "type": "int", "description": "Random state for reproducibility", "default": 42},
            {"name": "model_params", "type": "dict", "description": "Additional model-specific parameters", "default": None},
            {"name": "threshold", "type": "float", "description": "Threshold for converting continuous target to binary classification", "default": None},
            {"name": "use_cross_validation", "type": "bool", "description": "Whether to use K-fold cross-validation instead of train/test split", "default": False},
            {"name": "n_splits", "type": "int", "description": "Number of splits for K-fold cross-validation", "default": 5}
        ],
        "return_type": "dict",
        "return_description": "Dictionary containing trained model(s), predictions, evaluation metrics, and dataset information. When using cross-validation, includes ensemble of models and cross-validated predictions."
    },
    {
        "name": "analyze_feature_importance",
        "description": "Analyze and visualize feature importance for tree-based models, providing insights into which features contribute most to model predictions.",
        "module": "dleader_agent.tool.modeling",
        "required_parameters": [
            {"name": "model_result", "type": "dict", "description": "Result dictionary from train_regression_model or train_classification_model"}
        ],
        "optional_parameters": [
            {"name": "top_n", "type": "int", "description": "Number of top features to display and plot", "default": 10},
            {"name": "plot", "type": "bool", "description": "Whether to create feature importance visualization", "default": True}
        ],
        "return_type": "pd.DataFrame",
        "return_description": "Feature importance dataframe sorted by importance scores"
    },
    {
        "name": "create_regression_plots",
        "description": "Create comprehensive visualization plots for regression model evaluation including actual vs predicted scatter plot, residuals analysis, and performance metrics summary.",
        "module": "dleader_agent.tool.modeling",
        "required_parameters": [
            {"name": "model_result", "type": "dict", "description": "Result dictionary from train_regression_model"}
        ],
        "optional_parameters": [
            {"name": "save_path", "type": "str", "description": "Path to save plots (optional)", "default": None}
        ],
        "return_type": "None",
        "return_description": "Displays comprehensive regression evaluation plots"
    },
    {
        "name": "create_classification_plots",
        "description": "Create comprehensive visualization plots for classification model evaluation including confusion matrix, ROC curve, class distribution, and performance metrics summary.",
        "module": "dleader_agent.tool.modeling",
        "required_parameters": [
            {"name": "model_result", "type": "dict", "description": "Result dictionary from train_classification_model"}
        ],
        "optional_parameters": [
            {"name": "save_path", "type": "str", "description": "Path to save plots (optional)", "default": None}
        ],
        "return_type": "None",
        "return_description": "Displays comprehensive classification evaluation plots"
    },
    {
        "name": "save_model",
        "description": "Save trained model and all associated information to disk using joblib for later use and deployment.",
        "module": "dleader_agent.tool.modeling",
        "required_parameters": [
            {"name": "model_result", "type": "dict", "description": "Result dictionary from training function containing model and metadata"},
            {"name": "file_path", "type": "str", "description": "Path where the model should be saved"}
        ],
        "optional_parameters": [],
        "return_type": "None",
        "return_description": "Saves model to disk and prints confirmation message"
    },
    {
        "name": "load_model",
        "description": "Load previously saved trained model from disk for making predictions or further analysis.",
        "module": "dleader_agent.tool.modeling",
        "required_parameters": [
            {"name": "file_path", "type": "str", "description": "Path to the saved model file"}
        ],
        "optional_parameters": [],
        "return_type": "dict",
        "return_description": "Loaded model result dictionary containing model and all metadata"
    },
    {
        "name": "hyperparameter_tuning",
        "description": "Perform comprehensive hyperparameter optimization using GridSearchCV to find the best model configuration with cross-validation.",
        "module": "dleader_agent.tool.modeling",
        "required_parameters": [
            {"name": "data", "type": "pd.DataFrame", "description": "Input dataset containing features and target"},
            {"name": "target_column", "type": "str", "description": "Name of the target variable column"}
        ],
        "optional_parameters": [
            {"name": "feature_columns", "type": "list", "description": "List of feature column names", "default": None},
            {"name": "model_type", "type": "str", "description": "Type of model to tune", "default": "random_forest"},
            {"name": "task_type", "type": "str", "description": "Task type: 'regression' or 'classification'", "default": "regression"},
            {"name": "param_grid", "type": "dict", "description": "Parameter grid for tuning (uses defaults if None)", "default": None},
            {"name": "cv", "type": "int", "description": "Number of cross-validation folds", "default": 5},
            {"name": "scoring", "type": "str", "description": "Scoring metric for optimization", "default": None}
        ],
        "return_type": "dict",
        "return_description": "Dictionary containing best model, parameters, scores, and cross-validation results"
    },
    {
        "name": "remove_low_importance_features",
        "description": "Remove features with low importance based on tree-based model feature importance scores, helping to reduce dimensionality and improve model performance.",
        "module": "dleader_agent.tool.modeling",
        "required_parameters": [
            {"name": "data", "type": "pd.DataFrame", "description": "Input dataset"},
            {"name": "target_column", "type": "str", "description": "Name of the target variable"}
        ],
        "optional_parameters": [
            {"name": "feature_columns", "type": "list", "description": "List of feature columns (None for all except target)", "default": None},
            {"name": "model_type", "type": "str", "description": "Model for importance calculation: 'random_forest', 'extra_trees'", "default": "random_forest"},
            {"name": "importance_threshold", "type": "float", "description": "Minimum importance threshold to keep features", "default": 0.001},
            {"name": "random_state", "type": "int", "description": "Random state for reproducibility", "default": 42}
        ],
        "return_type": "dict",
        "return_description": "Dictionary containing filtered data, important features, removed features, and importance scores"
    },
    {
        "name": "remove_highly_correlated_features",
        "description": "Remove highly correlated features to reduce multicollinearity and improve model interpretability by keeping only one feature from each highly correlated pair.",
        "module": "dleader_agent.tool.modeling",
        "required_parameters": [
            {"name": "data", "type": "pd.DataFrame", "description": "Input dataset"}
        ],
        "optional_parameters": [
            {"name": "feature_columns", "type": "list", "description": "List of feature columns (None for all numeric)", "default": None},
            {"name": "target_column", "type": "str", "description": "Target column to preserve (optional)", "default": None},
            {"name": "correlation_threshold", "type": "float", "description": "Correlation threshold above which to remove features", "default": 0.95},
            {"name": "method", "type": "str", "description": "Correlation method: 'pearson', 'spearman', 'kendall'", "default": "pearson"}
        ],
        "return_type": "dict",
        "return_description": "Dictionary containing filtered data, correlation matrix, and information about removed features"
    },
    {
        "name": "select_best_features_comprehensive",
        "description": "Comprehensive feature selection pipeline that combines correlation filtering and importance-based filtering to systematically reduce feature dimensionality.",
        "module": "dleader_agent.tool.modeling",
        "required_parameters": [
            {"name": "data", "type": "pd.DataFrame", "description": "Input dataset"},
            {"name": "target_column", "type": "str", "description": "Name of the target variable"}
        ],
        "optional_parameters": [
            {"name": "feature_columns", "type": "list", "description": "List of feature columns (None for all except target)", "default": None},
            {"name": "correlation_threshold", "type": "float", "description": "Correlation threshold for removing correlated features", "default": 0.95},
            {"name": "importance_threshold", "type": "float", "description": "Importance threshold for removing low-importance features", "default": 0.001},
            {"name": "model_type", "type": "str", "description": "Model type for importance calculation", "default": "random_forest"},
            {"name": "random_state", "type": "int", "description": "Random state for reproducibility", "default": 42}
        ],
        "return_type": "dict",
        "return_description": "Dictionary containing final filtered data, selected features, and comprehensive filtering results"
    },
    {
        "name": "visualize_feature_selection_results",
        "description": "Create comprehensive visualizations for feature selection results including feature count progression, importance rankings, and correlation analysis.",
        "module": "dleader_agent.tool.modeling",
        "required_parameters": [
            {"name": "selection_result", "type": "dict", "description": "Result dictionary from select_best_features_comprehensive"}
        ],
        "optional_parameters": [
            {"name": "save_path", "type": "str", "description": "Path to save plots (optional)", "default": None}
        ],
        "return_type": "None",
        "return_description": "Displays comprehensive feature selection visualization plots"
    },
    {
        "name": "select_best_features_regression",
        "description": "Comprehensive feature selection pipeline optimized specifically for regression tasks. This function combines correlation-based filtering and regression model importance analysis to systematically reduce feature dimensionality while preserving predictive power for continuous targets.",
        "module": "dleader_agent.tool.modeling",
        "required_parameters": [
            {"name": "data", "type": "pd.DataFrame", "description": "Input dataset with features and continuous target"},
            {"name": "target_column", "type": "str", "description": "Name of the target variable (continuous for regression)"}
        ],
        "optional_parameters": [
            {"name": "feature_columns", "type": "list", "description": "List of feature columns (None for all except target)", "default": None},
            {"name": "correlation_threshold", "type": "float", "description": "Correlation threshold for removing highly correlated features", "default": 0.95},
            {"name": "importance_threshold", "type": "float", "description": "Importance threshold for removing low-importance features", "default": 0.001},
            {"name": "model_type", "type": "str", "description": "Regression model type for importance calculation: 'random_forest', 'extra_trees', 'gradient_boosting'", "default": "random_forest"},
            {"name": "random_state", "type": "int", "description": "Random state for reproducibility", "default": 42}
        ],
        "return_type": "dict",
        "return_description": "Dictionary containing final filtered data, selected features, correlation and importance analysis results, and feature reduction statistics"
    },
    {
        "name": "modeling_workflow",
        "description": "Comprehensive modeling workflow for both regression and classification tasks in cheminformatics. This workflow function handles the complete modeling pipeline including feature selection, model training, evaluation, diagnostics, and visualization. It can perform both regression and classification modeling with automatic feature importance analysis and diagnostic plot generation.",
        "module": "dleader_agent.tool.modeling",
        "required_parameters": [
            {"name": "data", "type": "pd.DataFrame", "description": "Input dataset with features and target (typically from preprocessing_pipeline_workflow)"},
            {"name": "target_column", "type": "str", "description": "Name of the target variable column"}
        ],
        "optional_parameters": [
            {"name": "feature_columns", "type": "list", "description": "List of feature columns (None for auto-detection)", "default": None},
            {"name": "correlation_threshold", "type": "float", "description": "Threshold for correlation-based feature filtering", "default": 0.95},
            {"name": "importance_threshold", "type": "float", "description": "Threshold for importance-based feature filtering", "default": 0.001},
            {"name": "model_type", "type": "str", "description": "Type of model: 'random_forest', 'linear', 'svr', 'knn'", "default": "random_forest"},
            {"name": "classification_threshold", "type": "float", "description": "Threshold for converting regression to classification (None for regression only)", "default": None},
            {"name": "random_state", "type": "int", "description": "Random state for reproducibility", "default": 42},
            {"name": "image_folder", "type": "str", "description": "Folder to save diagnostic plots", "default": "image"}
        ],
        "return_type": "dict",
        "return_description": "Comprehensive dictionary containing all modeling results including trained models, feature selection results, performance metrics, diagnostic plots, saved model files, and recommendations"
    },
    {
        "name": "normalize_data",
        "description": "Normalize numeric features using StandardScaler, MinMaxScaler, or RobustScaler to prepare data for machine learning algorithms. This function standardizes feature values to improve model performance and convergence.",
        "module": "dleader_agent.tool.modeling",
        "required_parameters": [{"name": "data", "type": "pd.DataFrame", "description": "Input dataset to normalize"}],
        "optional_parameters": [
            {
                "name": "columns",
                "type": "list",
                "description": "Columns to normalize (None for all numeric columns)",
                "default": None,
            },
            {
                "name": "method",
                "type": "str",
                "description": "Normalization method: 'standard', 'minmax', 'robust'",
                "default": "standard",
            },
        ],
        "return_type": "tuple",
        "return_description": "Tuple containing (normalized_data, scaler_object) for future transformations",
    }
]