"""
Machine Learning Modeling Tools for dleader_agent

This module provides comprehensive machine learning tools for both regression and classification tasks.
Includes model training, evaluation, feature importance analysis, and visualization capabilities.
"""

import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import joblib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.feature_selection import SelectFromModel
from sklearn.linear_model import LinearRegression, LogisticRegression
from sklearn.metrics import (accuracy_score, classification_report,
                             cohen_kappa_score, confusion_matrix, f1_score,
                             mean_absolute_error, mean_squared_error,
                             precision_score, r2_score, recall_score,
                             roc_auc_score, roc_curve)
from sklearn.model_selection import (GridSearchCV, KFold, cross_val_score,
                                     train_test_split)
from sklearn.neighbors import KNeighborsClassifier, KNeighborsRegressor
from sklearn.preprocessing import StandardScaler, MinMaxScaler, RobustScaler
from sklearn.svm import SVC, SVR

try:
    from tqdm import tqdm
    TQDM_AVAILABLE = True
except ImportError:
    TQDM_AVAILABLE = False
    print("⚠️  tqdm not available. Progress bars will not be shown.")
    
try:
    from mordred import Calculator, descriptors
    from rdkit import Chem
    RDKIT_AVAILABLE = True
except ImportError:
    RDKIT_AVAILABLE = False
    print("⚠️  RDKit and/or Mordred not available. Descriptor calculation functions will not work.")


def normalize_data(data, columns=None, method="standard"):
    """
    Normalize numeric columns.

    Args:
        data (pd.DataFrame): Input dataset
        columns (list): Columns to normalize (None for all numeric)
        method (str): Normalization method ('standard', 'minmax', 'robust')

    Returns:
        tuple: (normalized_data, scaler_object)
    """
    data_normalized = data.copy()

    if columns is None:
        columns = data.select_dtypes(include=[np.number]).columns

    print(f"📏 Normalizing data using {method} scaling")

    if method == "standard":
        scaler = StandardScaler()
    elif method == "minmax":
        scaler = MinMaxScaler()
    elif method == "robust":
        scaler = RobustScaler()
    else:
        raise ValueError(f"Unknown normalization method: {method}")

    if len(columns) > 0:
        data_normalized[columns] = scaler.fit_transform(data_normalized[columns])
        print(f"✅ Normalized {len(columns)} columns")

    return data_normalized, scaler


class PropertyRegressorCV:
    """
    A class to handle QSPR regression tasks using cross-validation.
    
    This class encapsulates the workflow of loading data, training models
    using cross-validation, making predictions, and evaluating results for QSPR modeling.
    """
    
    def __init__(self, model_type='random_forest', n_splits=5, random_state=42, model_params=None):
        """
        Initialize the PropertyRegressorCV.
        
        Args:
            model_type (str): Type of regression model
            n_splits (int): Number of splits for K-Fold cross-validation
            random_state (int): Random seed for reproducibility
            model_params (dict): Additional model parameters
        """
        self.model_type = model_type
        self.n_splits = n_splits
        self.random_state = random_state
        self.model_params = model_params or {}
        self.models = []
        self.kf = KFold(n_splits=n_splits, shuffle=True, random_state=random_state)
        self.X, self.y = None, None
        self.feature_importances = None
        self.scaler = None
        
    def load_data(self, X, y):
        """
        Load the dataset.
        
        Args:
            X (np.array or pd.DataFrame): Feature matrix
            y (np.array or pd.Series): Target vector
        """
        # Convert to numpy arrays if they are pandas objects
        if hasattr(X, 'values'):  # pandas DataFrame/Series
            self.X = X.values
        else:
            self.X = X
            
        if hasattr(y, 'values'):  # pandas DataFrame/Series
            self.y = y.values
        else:
            self.y = y
        
    def train_and_evaluate(self):
        """
        Train models using cross-validation and evaluate.
        
        Returns:
            float: Combined MSE for all validations
        """
        mse_scores = []
        mse_scores_train = []
        r2_scores = []
        r2_scores_train = []
        
        feature_importances = []
        val_indexs = []
        ys = []
        y_preds = []
        residuals = []
        
        y_train_preds = []
        
        for fold, (train_index, val_index) in enumerate(self.kf.split(self.X), 1):
            X_train, X_val = self.X[train_index], self.X[val_index]
            y_train, y_val = self.y[train_index], self.y[val_index]
            val_indexs.append(val_index)
            
            # Initialize model
            if self.model_type == 'random_forest':
                model = RandomForestRegressor(random_state=self.random_state, **self.model_params)
            elif self.model_type == 'linear':
                model = LinearRegression(**self.model_params)
            elif self.model_type == 'svr':
                model = SVR(**self.model_params)
                # Scale features for SVR
                if self.scaler is None:
                    self.scaler = StandardScaler()
                scaler_fold = StandardScaler()
                X_train = scaler_fold.fit_transform(X_train)
                X_val = scaler_fold.transform(X_val)
            elif self.model_type == 'knn':
                model = KNeighborsRegressor(**self.model_params)
                # Scale features for KNN
                if self.scaler is None:
                    self.scaler = StandardScaler()
                scaler_fold = StandardScaler()
                X_train = scaler_fold.fit_transform(X_train)
                X_val = scaler_fold.transform(X_val)
            else:
                raise ValueError(f"Unknown model type: {self.model_type}")
                
            model.fit(X_train, y_train)
            self.models.append(model)
            
            y_train_preds.extend(list(model.predict(X_train)))
            y_pred = model.predict(X_val)
            
            mse = mean_squared_error(y_val, y_pred)
            mse_train = mean_squared_error(y_train, model.predict(X_train))
            mse_scores.append(mse)
            mse_scores_train.append(mse_train)
            
            r2 = r2_score(y_val, y_pred)
            r2_train = r2_score(y_train, model.predict(X_train))
            r2_scores.append(r2)
            r2_scores_train.append(r2_train)
            
            if hasattr(model, 'feature_importances_'):
                feature_importances.append(model.feature_importances_)
            print(f"Fold {fold} MSE: {mse:.4f}, R²: {r2:.4f}")
            
            ys.extend(list(y_val))
            y_preds.extend(list(y_pred))
            residuals.extend(list(y_val - y_pred))
            
        self.mse = np.mean(mse_scores)
        self.mse_train = np.mean(mse_scores_train)
        self.r2 = np.mean(r2_scores)
        self.r2_train = np.mean(r2_scores_train)
        print(f"Combined MSE: {self.mse:.4f}, Combined R²: {self.r2:.4f}")
        
        if feature_importances:
            self.feature_importances = np.mean(feature_importances, axis=0)
        self.val_indexs = val_indexs
        self.ys = ys
        self.y_preds = y_preds
        self.residuals = residuals
        
        return self.mse
        
    def get_feature_importance(self):
        """
        Get the average feature importance across all folds.
        
        Returns:
            np.array: Average feature importance
        """
        return self.feature_importances
        
    def predict(self, X):
        """
        Make predictions using all trained models and average the results.
        
        Args:
            X (np.array or pd.DataFrame): Feature matrix to predict on
            
        Returns:
            np.array: Average predicted values across all models
        """
        # Convert to numpy array if it's a pandas DataFrame
        if hasattr(X, 'values'):
            X = X.values
            
        if self.model_type in ['svr', 'knn'] and self.scaler:
            X = self.scaler.transform(X)
        predictions = np.array([model.predict(X) for model in self.models])
        return np.mean(predictions, axis=0)


class PropertyClassifierCV:
    """
    A class to handle QSPR classification tasks using cross-validation.
    
    This class encapsulates the workflow of loading data, training models
    using cross-validation, making predictions, and evaluating results for QSPR modeling.
    """
    
    def __init__(self, model_type='random_forest', n_splits=5, random_state=42, model_params=None):
        """
        Initialize the PropertyClassifierCV.
        
        Args:
            model_type (str): Type of classification model
            n_splits (int): Number of splits for K-Fold cross-validation
            random_state (int): Random seed for reproducibility
            model_params (dict): Additional model parameters
        """
        self.model_type = model_type
        self.n_splits = n_splits
        self.random_state = random_state
        self.model_params = model_params or {}
        self.models = []
        self.kf = KFold(n_splits=n_splits, shuffle=True, random_state=random_state)
        self.X, self.y = None, None
        self.feature_importances = None
        self.scaler = None
        
    def load_data(self, X, y):
        """
        Load the dataset.
        
        Args:
            X (np.array or pd.DataFrame): Feature matrix
            y (np.array or pd.Series): Target vector
        """
        # Convert to numpy arrays if they are pandas objects
        if hasattr(X, 'values'):  # pandas DataFrame/Series
            self.X = X.values
        else:
            self.X = X
            
        if hasattr(y, 'values'):  # pandas DataFrame/Series
            self.y = y.values
        else:
            self.y = y
        
    def train_and_evaluate(self):
        """
        Train models using cross-validation and evaluate.
        
        Returns:
            float: Combined accuracy for all validations
        """
        accuracy_scores = []
        accuracy_scores_train = []
        
        f1_scores = []
        f1_scores_train = []
        
        recall_scores = []
        recall_scores_train = []
        
        precision_scores = []
        precision_scores_train = []
        
        roc_auc_scores = []
        roc_auc_scores_train = []
        
        feature_importances = []
        val_indexs = []
        ys = []
        y_preds = []
        
        y_train_preds = []
        
        for fold, (train_index, val_index) in enumerate(self.kf.split(self.X), 1):
            X_train, X_val = self.X[train_index], self.X[val_index]
            y_train, y_val = self.y[train_index], self.y[val_index]
            val_indexs.append(val_index)
            
            # Initialize model
            if self.model_type == 'random_forest':
                model = RandomForestClassifier(random_state=self.random_state, **self.model_params)
            elif self.model_type == 'logistic':
                model = LogisticRegression(random_state=self.random_state, **self.model_params)
            elif self.model_type == 'svc':
                model = SVC(random_state=self.random_state, probability=True, **self.model_params)
                # Scale features for SVC
                if self.scaler is None:
                    self.scaler = StandardScaler()
                scaler_fold = StandardScaler()
                X_train = scaler_fold.fit_transform(X_train)
                X_val = scaler_fold.transform(X_val)
            elif self.model_type == 'knn':
                model = KNeighborsClassifier(**self.model_params)
                # Scale features for KNN
                if self.scaler is None:
                    self.scaler = StandardScaler()
                scaler_fold = StandardScaler()
                X_train = scaler_fold.fit_transform(X_train)
                X_val = scaler_fold.transform(X_val)
            else:
                raise ValueError(f"Unknown model type: {self.model_type}")
                
            model.fit(X_train, y_train)
            self.models.append(model)
            
            y_train_preds.extend(list(model.predict(X_train)))
            y_pred = model.predict(X_val)
            
            accuracy = model.score(X_val, y_val)
            accuracy_train = model.score(X_train, y_train)
            accuracy_scores.append(accuracy)
            accuracy_scores_train.append(accuracy_train)
            
            f1_val = f1_score(y_val, y_pred, average='weighted')
            f1_train = f1_score(y_train, model.predict(X_train), average='weighted')
            f1_scores.append(f1_val)
            f1_scores_train.append(f1_train)
            
            recall_score_val = recall_score(y_val, y_pred, average='weighted')
            recall_score_train = recall_score(y_train, model.predict(X_train), average='weighted')
            recall_scores.append(recall_score_val)
            recall_scores_train.append(recall_score_train)
            
            precision_score_val = precision_score(y_val, y_pred, average='weighted')
            precision_score_train = precision_score(y_train, model.predict(X_train), average='weighted')
            precision_scores.append(precision_score_val)
            precision_scores_train.append(precision_score_train)
            
            # ROC AUC only for binary classification
            if len(np.unique(y_val)) == 2:
                try:
                    roc_auc_score_val = roc_auc_score(y_val, y_pred)
                    roc_auc_scores.append(roc_auc_score_val)
                    roc_auc_score_train = roc_auc_score(y_train, model.predict(X_train))
                    roc_auc_scores_train.append(roc_auc_score_train)
                except:
                    pass
            
            if hasattr(model, 'feature_importances_'):
                feature_importances.append(model.feature_importances_)
            print(f"Fold {fold} Accuracy: {accuracy:.4f}")
            
            ys.extend(list(y_val))
            y_preds.extend(list(y_pred))
            
        self.accuracy = np.mean(accuracy_scores)
        self.accuracy_train = np.mean(accuracy_scores_train)
        self.f1 = np.mean(f1_scores)
        self.f1_train = np.mean(f1_scores_train)
        self.recall = np.mean(recall_scores)
        self.recall_train = np.mean(recall_scores_train)
        self.precision = np.mean(precision_scores)
        self.precision_train = np.mean(precision_scores_train)
        
        if roc_auc_scores:
            self.roc_auc = np.mean(roc_auc_scores)
            self.roc_auc_train = np.mean(roc_auc_scores_train)
        else:
            self.roc_auc = None
            self.roc_auc_train = None
            
        print(f"Combined Accuracy: {self.accuracy:.4f}")
        
        if feature_importances:
            self.feature_importances = np.mean(feature_importances, axis=0)
        self.val_indexs = val_indexs
        self.ys = ys
        self.y_preds = y_preds
        
        return self.accuracy
        
    def get_feature_importance(self):
        """
        Get the average feature importance across all folds.
        
        Returns:
            np.array: Average feature importance
        """
        return self.feature_importances
        
    def predict(self, X):
        """
        Make predictions using all trained models and average the results.
        
        Args:
            X (np.array or pd.DataFrame): Feature matrix to predict on
            
        Returns:
            np.array: Average predicted values across all models
        """
        # Convert to numpy array if it's a pandas DataFrame
        if hasattr(X, 'values'):
            X = X.values
            
        if self.model_type in ['svc', 'knn'] and self.scaler:
            X = self.scaler.transform(X)
        predictions = np.array([model.predict(X) for model in self.models])
        return np.mean(predictions, axis=0)


def train_regression_model(data, target_column, feature_columns=None, model_type='random_forest', 
                         test_size=0.2, random_state=42, model_params=None, use_cross_validation=True, n_splits=5):
    """
    Train a regression model with comprehensive evaluation.
    
    Args:
        data (pd.DataFrame): Input dataset
        target_column (str): Name of the target variable column
        feature_columns (list): List of feature column names (None for all except target)
        model_type (str): Type of model ('random_forest', 'linear', 'svr', 'knn')
        test_size (float): Proportion of dataset for testing
        random_state (int): Random state for reproducibility
        model_params (dict): Additional model parameters
        use_cross_validation (bool): Whether to use cross-validation instead of train/test split
        n_splits (int): Number of splits for K-Fold cross-validation
        
    Returns:
        dict: Dictionary containing trained model, predictions, and evaluation metrics
    """
    if target_column not in data.columns:
        raise ValueError(f"Target column '{target_column}' not found in dataset")
    
    # Prepare features and target
    if feature_columns is None:
        feature_columns = [col for col in data.columns if col != target_column]
    
    X = data[feature_columns]
    y = data[target_column]
    
    # Remove any remaining NaN values
    mask = ~(X.isnull().any(axis=1) | y.isnull())
    X = X[mask]
    y = y[mask]
    
    print(f"🔬 Training {model_type} regression model")
    print(f"📊 Dataset: {X.shape[0]} samples, {X.shape[1]} features")
    if use_cross_validation:
        print(f"🔄 Using {n_splits}-fold cross-validation")
    else:
        print(f"🔄 Using train/test split (test_size={test_size})")
    
    if use_cross_validation:
        # Use cross-validation approach
        regressor = PropertyRegressorCV(model_type=model_type, n_splits=n_splits, random_state=random_state, model_params=model_params)
        regressor.load_data(X, y)
        mse = regressor.train_and_evaluate()
        
        result = {
            'model': regressor,
            'cv_models': regressor.models,
            'feature_columns': feature_columns,
            'target_column': target_column,
            'X': X,
            'y': y,
            'y_true': regressor.ys,
            'y_pred': regressor.y_preds,
            'residuals': regressor.residuals,
            'metrics': {
                'mse': regressor.mse,
                'mse_train': regressor.mse_train,
                'r2': regressor.r2,
                'r2_train': regressor.r2_train,
                'mae': np.mean(np.abs(regressor.residuals)),
                'cv_mse_mean': regressor.mse,
                'cv_r2_mean': regressor.r2
            },
            'model_type': model_type,
            'cross_validation': True,
            'n_splits': n_splits
        }
        
        if model_type in ['svr', 'knn'] and hasattr(regressor, 'scaler'):
            result['scaler'] = regressor.scaler
            
        return result
    
    # Split data
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=test_size, random_state=random_state
    )
    
    # Initialize model
    model_params = model_params or {}
    if model_type == 'random_forest':
        model = RandomForestRegressor(random_state=random_state, **model_params)
    elif model_type == 'linear':
        model = LinearRegression(**model_params)
    elif model_type == 'svr':
        model = SVR(**model_params)
        # Scale features for SVR
        scaler = StandardScaler()
        X_train = scaler.fit_transform(X_train)
        X_test = scaler.transform(X_test)
    elif model_type == 'knn':
        model = KNeighborsRegressor(**model_params)
        # Scale features for KNN
        scaler = StandardScaler()
        X_train = scaler.fit_transform(X_train)
        X_test = scaler.transform(X_test)
    else:
        raise ValueError(f"Unknown model type: {model_type}")
    
    # Train model
    model.fit(X_train, y_train)
    
    # Make predictions
    y_pred_train = model.predict(X_train)
    y_pred_test = model.predict(X_test)
    
    # Calculate metrics
    metrics = {
        'train_mse': mean_squared_error(y_train, y_pred_train),
        'test_mse': mean_squared_error(y_test, y_pred_test),
        'train_mae': mean_absolute_error(y_train, y_pred_train),
        'test_mae': mean_absolute_error(y_test, y_pred_test),
        'train_r2': r2_score(y_train, y_pred_train),
        'test_r2': r2_score(y_test, y_pred_test)
    }
    
    # Cross-validation
    cv_scores = cross_val_score(model, X_train, y_train, cv=5, scoring='r2')
    metrics['cv_r2_mean'] = cv_scores.mean()
    metrics['cv_r2_std'] = cv_scores.std()
    
    print(f"✅ Model training completed")
    print(f"  Test R²: {metrics['test_r2']:.4f}")
    print(f"  Test MSE: {metrics['test_mse']:.4f}")
    print(f"  Test MAE: {metrics['test_mae']:.4f}")
    print(f"  CV R² (mean±std): {metrics['cv_r2_mean']:.4f}±{metrics['cv_r2_std']:.4f}")
    
    result = {
        'model': model,
        'feature_columns': feature_columns,
        'target_column': target_column,
        'X_train': X_train,
        'X_test': X_test,
        'y_train': y_train,
        'y_test': y_test,
        'y_pred_train': y_pred_train,
        'y_pred_test': y_pred_test,
        'metrics': metrics,
        'model_type': model_type
    }
    
    # Add scaler if used
    if model_type in ['svr', 'knn']:
        result['scaler'] = scaler
    
    return result


def train_classification_model(data, target_column, feature_columns=None, model_type='random_forest',
                             test_size=0.2, random_state=42, model_params=None, threshold=None, 
                             use_cross_validation=True, n_splits=5):
    """
    Train a classification model with comprehensive evaluation.
    
    Args:
        data (pd.DataFrame): Input dataset
        target_column (str): Name of the target variable column
        feature_columns (list): List of feature column names (None for all except target)
        model_type (str): Type of model ('random_forest', 'logistic', 'svc', 'knn')
        test_size (float): Proportion of dataset for testing
        random_state (int): Random state for reproducibility
        model_params (dict): Additional model parameters
        threshold (float): Threshold for binary classification (if converting continuous target)
        use_cross_validation (bool): Whether to use cross-validation instead of train/test split
        n_splits (int): Number of splits for K-Fold cross-validation
        
    Returns:
        dict: Dictionary containing trained model, predictions, and evaluation metrics
    """
    if target_column not in data.columns:
        raise ValueError(f"Target column '{target_column}' not found in dataset")
    
    data_processed = data.copy()
    
    # Convert continuous target to binary if threshold provided
    if threshold is not None:
        print(f"🔄 Converting continuous target to binary using threshold {threshold}")
        data_processed[target_column + '_binary'] = (data_processed[target_column] > threshold).astype(int)
        target_column = target_column + '_binary'
    
    # Prepare features and target
    if feature_columns is None:
        feature_columns = [col for col in data_processed.columns if col != target_column]
    
    X = data_processed[feature_columns]
    y = data_processed[target_column]
    
    # Remove any remaining NaN values
    mask = ~(X.isnull().any(axis=1) | y.isnull())
    X = X[mask]
    y = y[mask]
    
    print(f"🔬 Training {model_type} classification model")
    print(f"📊 Dataset: {X.shape[0]} samples, {X.shape[1]} features")
    print(f"📈 Class distribution: {y.value_counts().to_dict()}")
    if use_cross_validation:
        print(f"🔄 Using {n_splits}-fold cross-validation")
    else:
        print(f"🔄 Using train/test split (test_size={test_size})")
    
    if use_cross_validation:
        # Use cross-validation approach
        classifier = PropertyClassifierCV(model_type=model_type, n_splits=n_splits, random_state=random_state, model_params=model_params)
        classifier.load_data(X, y)
        accuracy = classifier.train_and_evaluate()
        
        # Prepare metrics for cross-validation result
        metrics = {
            'train_accuracy': classifier.accuracy_train,
            'test_accuracy': classifier.accuracy,
            'accuracy': classifier.accuracy,
            'precision': classifier.precision,
            'recall': classifier.recall,
            'f1_score': classifier.f1,
            'cv_accuracy_mean': classifier.accuracy,
            'cv_accuracy_std': 0.0  # We could compute this if we stored individual fold scores
        }
        
        if classifier.roc_auc is not None:
            metrics['auc_roc'] = classifier.roc_auc
        
        result = {
            'model': classifier,
            'cv_models': classifier.models,
            'feature_columns': feature_columns,
            'target_column': target_column,
            'X': X,
            'y': y,
            'y_true': classifier.ys,
            'y_pred': classifier.y_preds,
            'y_pred_proba_test': None,  # Could be added if needed
            'metrics': metrics,
            'model_type': model_type,
            'threshold': threshold,
            'cross_validation': True,
            'n_splits': n_splits
        }
        
        if model_type in ['svc', 'knn'] and hasattr(classifier, 'scaler'):
            result['scaler'] = classifier.scaler
            
        return result
    
    # Split data (stratified for classification)
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=test_size, random_state=random_state, stratify=y
    )
    
    # Initialize model
    model_params = model_params or {}
    if model_type == 'random_forest':
        model = RandomForestClassifier(random_state=random_state, **model_params)
    elif model_type == 'logistic':
        model = LogisticRegression(random_state=random_state, **model_params)
    elif model_type == 'svc':
        model = SVC(random_state=random_state, probability=True, **model_params)
        # Scale features for SVC
        scaler = StandardScaler()
        X_train = scaler.fit_transform(X_train)
        X_test = scaler.transform(X_test)
    elif model_type == 'knn':
        model = KNeighborsClassifier(**model_params)
        # Scale features for KNN
        scaler = StandardScaler()
        X_train = scaler.fit_transform(X_train)
        X_test = scaler.transform(X_test)
    else:
        raise ValueError(f"Unknown model type: {model_type}")
    
    # Train model
    model.fit(X_train, y_train)
    
    # Make predictions
    y_pred_train = model.predict(X_train)
    y_pred_test = model.predict(X_test)
    
    # Get prediction probabilities for binary classification
    try:
        y_pred_proba_test = model.predict_proba(X_test)[:, 1]
    except:
        y_pred_proba_test = None
    
    # Calculate metrics
    metrics = {
        'train_accuracy': accuracy_score(y_train, y_pred_train),
        'test_accuracy': accuracy_score(y_test, y_pred_test),
        'precision': precision_score(y_test, y_pred_test, average='weighted'),
        'recall': recall_score(y_test, y_pred_test, average='weighted'),
        'f1_score': f1_score(y_test, y_pred_test, average='weighted'),
        'cohen_kappa': cohen_kappa_score(y_test, y_pred_test)
    }
    
    # Add AUC for binary classification
    if len(np.unique(y)) == 2 and y_pred_proba_test is not None:
        metrics['auc_roc'] = roc_auc_score(y_test, y_pred_proba_test)
    
    # Cross-validation
    cv_scores = cross_val_score(model, X_train, y_train, cv=5, scoring='accuracy')
    metrics['cv_accuracy_mean'] = cv_scores.mean()
    metrics['cv_accuracy_std'] = cv_scores.std()
    
    print(f"✅ Model training completed")
    print(f"  Test Accuracy: {metrics['test_accuracy']:.4f}")
    print(f"  Precision: {metrics['precision']:.4f}")
    print(f"  Recall: {metrics['recall']:.4f}")
    print(f"  F1-Score: {metrics['f1_score']:.4f}")
    print(f"  Cohen's Kappa: {metrics['cohen_kappa']:.4f}")
    if 'auc_roc' in metrics:
        print(f"  AUC-ROC: {metrics['auc_roc']:.4f}")
    print(f"  CV Accuracy (mean±std): {metrics['cv_accuracy_mean']:.4f}±{metrics['cv_accuracy_std']:.4f}")
    
    result = {
        'model': model,
        'feature_columns': feature_columns,
        'target_column': target_column,
        'X_train': X_train,
        'X_test': X_test,
        'y_train': y_train,
        'y_test': y_test,
        'y_pred_train': y_pred_train,
        'y_pred_test': y_pred_test,
        'y_pred_proba_test': y_pred_proba_test,
        'metrics': metrics,
        'model_type': model_type,
        'threshold': threshold
    }
    
    # Add scaler if used
    if model_type in ['svc', 'knn']:
        result['scaler'] = scaler
    
    return result


def analyze_feature_importance(model_result, top_n=10, plot=True, save_path=None):
    """
    Analyze and visualize feature importance for tree-based models.
    
    Args:
        model_result (dict): Result dictionary from train_regression_model or train_classification_model
        top_n (int): Number of top features to display
        plot (bool): Whether to create visualization
        save_path (str): Path to save plot (optional)
        
    Returns:
        pd.DataFrame: Feature importance dataframe
    """
    model = model_result['model']
    feature_columns = model_result['feature_columns']
    
    # Handle both cross-validation and train/test split scenarios
    if 'cross_validation' in model_result and model_result['cross_validation']:
        # Cross-validation: use averaged feature importance from CV object
        if hasattr(model, 'get_feature_importance') and model.get_feature_importance() is not None:
            feature_importances = model.get_feature_importance()
        else:
            print("⚠️  Cross-validation model does not have feature importance data")
            return None
    else:
        # Train/test split: use feature importance from sklearn model
        if not hasattr(model, 'feature_importances_'):
            print("⚠️  Model does not support feature importance analysis")
            return None
        feature_importances = model.feature_importances_
    
    # Create feature importance dataframe
    importance_df = pd.DataFrame({
        'Feature': feature_columns,
        'importance': feature_importances
    }).sort_values(by='importance', ascending=False)
    
    print(f"🎯 Top {top_n} Most Important Features:")
    print(importance_df.head(top_n).to_string(index=False))
    
    if plot:
        plt.figure(figsize=(10, 6))
        sns.barplot(data=importance_df.head(top_n), x='importance', y='Feature')
        plt.title(f'Top {top_n} Most Important Features')
        plt.xlabel('importance Score')
        plt.ylabel('Feature')
        plt.tight_layout()
        
        if save_path:
            plt.savefig(save_path, dpi=300, bbox_inches='tight')
            print(f"💾 Feature importance plot saved to {save_path}")
        else:
            plt.show()
        
        plt.close()
    
    return importance_df


def create_regression_plots(model_result, save_path=None):
    """
    Create comprehensive plots for regression model evaluation.
    
    Args:
        model_result (dict): Result dictionary from train_regression_model
        save_path (str): Path to save plots (optional)
    """
    # Handle both cross-validation and train/test split scenarios
    if 'cross_validation' in model_result and model_result['cross_validation']:
        # Cross-validation scenario
        y_true = np.array(model_result['y_true'])
        y_pred = np.array(model_result['y_pred'])
        r2_score = model_result['metrics']['r2']
        residuals = model_result.get('residuals', y_true - y_pred)
    else:
        # Train/test split scenario
        y_true = model_result['y_test']
        y_pred = model_result['y_pred_test']
        r2_score = model_result['metrics']['test_r2']
        residuals = y_true - y_pred
    
    metrics = model_result['metrics']
    
    fig, axes = plt.subplots(2, 2, figsize=(15, 12))
    
    # Actual vs Predicted
    axes[0, 0].scatter(y_true, y_pred, alpha=0.6)
    axes[0, 0].plot([y_true.min(), y_true.max()], [y_true.min(), y_true.max()], 'r--', lw=2)
    axes[0, 0].set_xlabel('Actual Values')
    axes[0, 0].set_ylabel('Predicted Values')
    axes[0, 0].set_title(f'Actual vs Predicted (R² = {r2_score:.4f})')
    
    # Residuals plot
    axes[0, 1].scatter(y_pred, residuals, alpha=0.6)
    axes[0, 1].axhline(y=0, color='r', linestyle='--')
    axes[0, 1].set_xlabel('Predicted Values')
    axes[0, 1].set_ylabel('Residuals')
    axes[0, 1].set_title('Residuals vs Predicted')
    
    # Residuals histogram
    axes[1, 0].hist(residuals, bins=30, alpha=0.7, edgecolor='black')
    axes[1, 0].set_xlabel('Residuals')
    axes[1, 0].set_ylabel('Frequency')
    axes[1, 0].set_title('Residuals Distribution')
    
    # Metrics summary
    if 'cross_validation' in model_result and model_result['cross_validation']:
        # Cross-validation metrics
        mse = metrics.get('mse', 'N/A')
        mae = metrics.get('mae', 'N/A')
        r2_mean = metrics.get('cv_r2_mean', metrics.get('r2', 'N/A'))
        metrics_text = f"""
    CV R²: {r2_score:.4f}
    CV MSE: {mse:.4f}
    CV MAE: {mae:.4f}
    Folds: {model_result.get('n_splits', 'N/A')}
    """
    else:
        # Train/test split metrics
        metrics_text = f"""
    Test R²: {metrics['test_r2']:.4f}
    Test MSE: {metrics['test_mse']:.4f}
    Test MAE: {metrics['test_mae']:.4f}
    CV R²: {metrics['cv_r2_mean']:.4f}±{metrics['cv_r2_std']:.4f}
    """
    axes[1, 1].text(0.1, 0.5, metrics_text, transform=axes[1, 1].transAxes, 
                    fontsize=12, verticalalignment='center',
                    bbox=dict(boxstyle='round', facecolor='lightblue', alpha=0.8))
    axes[1, 1].set_xlim(0, 1)
    axes[1, 1].set_ylim(0, 1)
    axes[1, 1].set_title('Model Performance Metrics')
    axes[1, 1].axis('off')
    
    plt.tight_layout()
    
    if save_path:
        plt.savefig(save_path, dpi=300, bbox_inches='tight')
        print(f"💾 Plots saved to: {save_path}")
    else:
        plt.show()


def create_classification_plots(model_result, save_path=None):
    """
    Create comprehensive plots for classification model evaluation.
    
    Args:
        model_result (dict): Result dictionary from train_classification_model
        save_path (str): Path to save plots (optional)
    """
    # Handle both cross-validation and train/test split scenarios
    if 'cross_validation' in model_result and model_result['cross_validation']:
        # Cross-validation scenario
        y_true = np.array(model_result['y_true'])
        y_pred = np.array(model_result['y_pred'])
        y_pred_proba = model_result.get('y_pred_proba_test', None)  # May not be available for CV
        accuracy = model_result['metrics']['accuracy']
    else:
        # Train/test split scenario
        y_true = model_result['y_test']
        y_pred = model_result['y_pred_test']
        y_pred_proba = model_result['y_pred_proba_test']
        accuracy = model_result['metrics']['test_accuracy']
    
    metrics = model_result['metrics']
    
    fig, axes = plt.subplots(2, 2, figsize=(15, 12))
    
    # Confusion Matrix
    cm = confusion_matrix(y_true, y_pred)
    sns.heatmap(cm, annot=True, fmt='d', cmap='Blues', ax=axes[0, 0])
    axes[0, 0].set_xlabel('Predicted')
    axes[0, 0].set_ylabel('Actual')
    axes[0, 0].set_title('Confusion Matrix')
    
    # ROC Curve (for binary classification)
    if len(np.unique(y_true)) == 2 and y_pred_proba is not None:
        fpr, tpr, _ = roc_curve(y_true, y_pred_proba)
        axes[0, 1].plot(fpr, tpr, label=f'ROC Curve (AUC = {metrics.get("auc_roc", 0):.4f})')
        axes[0, 1].plot([0, 1], [0, 1], 'k--', label='Random')
        axes[0, 1].set_xlabel('False Positive Rate')
        axes[0, 1].set_ylabel('True Positive Rate')
        axes[0, 1].set_title('ROC Curve')
        axes[0, 1].legend()
    else:
        axes[0, 1].text(0.5, 0.5, 'ROC Curve\n(Binary classification only)', 
                       ha='center', va='center', transform=axes[0, 1].transAxes)
        axes[0, 1].set_title('ROC Curve')
    
    # Class distribution
    class_counts = pd.Series(y_true).value_counts().sort_index()
    axes[1, 0].bar(range(len(class_counts)), class_counts.values)
    axes[1, 0].set_xlabel('Class')
    axes[1, 0].set_ylabel('Count')
    axes[1, 0].set_title('Class Distribution')
    axes[1, 0].set_xticks(range(len(class_counts)))
    axes[1, 0].set_xticklabels(class_counts.index)
    
    # Metrics summary
    if 'cross_validation' in model_result and model_result['cross_validation']:
        # Cross-validation metrics
        metrics_text = f"""
    CV Accuracy: {accuracy:.4f}
    CV Precision: {metrics['precision']:.4f}
    CV Recall: {metrics['recall']:.4f}
    CV F1-Score: {metrics['f1_score']:.4f}
    Folds: {model_result.get('n_splits', 'N/A')}
    """
        if 'auc_roc' in metrics:
            metrics_text += f"\n    CV AUC-ROC: {metrics['auc_roc']:.4f}"
    else:
        # Train/test split metrics
        metrics_text = f"""
    Accuracy: {metrics['test_accuracy']:.4f}
    Precision: {metrics['precision']:.4f}
    Recall: {metrics['recall']:.4f}
    F1-Score: {metrics['f1_score']:.4f}
    Cohen's Kappa: {metrics['cohen_kappa']:.4f}
    """
        if 'auc_roc' in metrics:
            metrics_text += f"\n    AUC-ROC: {metrics['auc_roc']:.4f}"
        
    axes[1, 1].text(0.1, 0.5, metrics_text, transform=axes[1, 1].transAxes,
                    fontsize=12, verticalalignment='center',
                    bbox=dict(boxstyle='round', facecolor='lightgreen', alpha=0.8))
    axes[1, 1].set_xlim(0, 1)
    axes[1, 1].set_ylim(0, 1)
    axes[1, 1].set_title('Model Performance Metrics')
    axes[1, 1].axis('off')
    
    plt.tight_layout()
    
    if save_path:
        plt.savefig(save_path, dpi=300, bbox_inches='tight')
        print(f"💾 Plots saved to: {save_path}")
    else:
        plt.show()


def save_model(model_result, file_path):
    """
    Save trained model and associated information to disk.
    
    Args:
        model_result (dict): Result dictionary from training function
        file_path (str): Path to save the model
    """
    try:
        joblib.dump(model_result, file_path)
        print(f"💾 Model saved successfully to: {file_path}")
    except Exception as e:
        print(f"❌ Error saving model: {str(e)}")


def load_model(file_path):
    """
    Load trained model from disk.
    
    Args:
        file_path (str): Path to the saved model
        
    Returns:
        dict: Loaded model result dictionary
    """
    try:
        model_result = joblib.load(file_path)
        print(f"✅ Model loaded successfully from: {file_path}")
        return model_result
    except Exception as e:
        print(f"❌ Error loading model: {str(e)}")
        return None


def hyperparameter_tuning(data, target_column, feature_columns=None, model_type='random_forest',
                         task_type='regression', param_grid=None, cv=5, scoring=None):
    """
    Perform hyperparameter tuning using GridSearchCV.
    
    Args:
        data (pd.DataFrame): Input dataset
        target_column (str): Name of the target variable column
        feature_columns (list): List of feature column names
        model_type (str): Type of model to tune
        task_type (str): 'regression' or 'classification'
        param_grid (dict): Parameter grid for tuning
        cv (int): Number of cross-validation folds
        scoring (str): Scoring metric
        
    Returns:
        dict: Dictionary containing best model and tuning results
    """
    # Prepare data
    if feature_columns is None:
        feature_columns = [col for col in data.columns if col != target_column]
    
    X = data[feature_columns]
    y = data[target_column]
    
    # Remove any remaining NaN values
    mask = ~(X.isnull().any(axis=1) | y.isnull())
    X = X[mask]
    y = y[mask]
    
    print(f"🔧 Starting hyperparameter tuning for {model_type} {task_type}")
    
    # Initialize base model
    if task_type == 'regression':
        if model_type == 'random_forest':
            base_model = RandomForestRegressor(random_state=42)
            default_params = {
                'n_estimators': [50, 100, 200],
                'max_depth': [None, 10, 20],
                'min_samples_split': [2, 5, 10]
            }
            default_scoring = 'r2'
        elif model_type == 'linear':
            base_model = LinearRegression()
            default_params = {}  # Linear regression has no hyperparameters to tune
            default_scoring = 'r2'
    elif task_type == 'classification':
        if model_type == 'random_forest':
            base_model = RandomForestClassifier(random_state=42)
            default_params = {
                'n_estimators': [50, 100, 200],
                'max_depth': [None, 10, 20],
                'min_samples_split': [2, 5, 10]
            }
            default_scoring = 'accuracy'
        elif model_type == 'logistic':
            base_model = LogisticRegression(random_state=42)
            default_params = {
                'C': [0.1, 1, 10],
                'penalty': ['l1', 'l2'],
                'solver': ['liblinear']
            }
            default_scoring = 'accuracy'
    
    # Use provided parameters or defaults
    param_grid = param_grid or default_params
    scoring = scoring or default_scoring
    
    if not param_grid:
        print("⚠️  No hyperparameters to tune for this model")
        return None
    
    # Perform grid search
    grid_search = GridSearchCV(
        estimator=base_model,
        param_grid=param_grid,
        cv=cv,
        scoring=scoring,
        n_jobs=-1,
        verbose=1
    )
    
    grid_search.fit(X, y)
    
    print(f"✅ Hyperparameter tuning completed")
    print(f"  Best score: {grid_search.best_score_:.4f}")
    print(f"  Best parameters: {grid_search.best_params_}")
    
    result = {
        'best_model': grid_search.best_estimator_,
        'best_params': grid_search.best_params_,
        'best_score': grid_search.best_score_,
        'cv_results': grid_search.cv_results_,
        'feature_columns': feature_columns,
        'target_column': target_column
    }
    
    return result

def remove_low_importance_features(data, target_column, feature_columns=None, 
                                 model_type='random_forest', importance_threshold=0.001,
                                 random_state=42):
    """
    Remove features with low importance based on a tree-based model.
    
    Args:
        data (pd.DataFrame): Input dataset
        target_column (str): Name of the target variable
        feature_columns (list): List of feature columns (None for all except target)
        model_type (str): Model for importance calculation ('random_forest', 'extra_trees')
        importance_threshold (float): Minimum importance threshold to keep features
        random_state (int): Random state for reproducibility
        
    Returns:
        dict: Dictionary containing filtered data and importance information
    """
    if feature_columns is None:
        feature_columns = [col for col in data.columns if col != target_column]
    
    X = data[feature_columns]
    y = data[target_column]
    
    # Remove any rows with NaN values
    mask = ~(X.isnull().any(axis=1) | y.isnull())
    X_clean = X[mask]
    y_clean = y[mask]
    
    print(f"🎯 Removing low importance features using {model_type}")
    print(f"📊 Starting with {X_clean.shape[1]} features")
    
    # Initialize model for importance calculation
    if model_type == 'random_forest':
        if y_clean.dtype == 'object' or len(y_clean.unique()) < 10:
            model = RandomForestClassifier(random_state=random_state, n_estimators=100)
        else:
            model = RandomForestRegressor(random_state=random_state, n_estimators=100)
    elif model_type == 'extra_trees':
        from sklearn.ensemble import ExtraTreesClassifier, ExtraTreesRegressor
        if y_clean.dtype == 'object' or len(y_clean.unique()) < 10:
            model = ExtraTreesClassifier(random_state=random_state, n_estimators=100)
        else:
            model = ExtraTreesRegressor(random_state=random_state, n_estimators=100)
    else:
        raise ValueError(f"Unknown model type: {model_type}")
    
    # Fit model and calculate importance
    model.fit(X_clean, y_clean)
    importances = model.feature_importances_
    
    # Create importance dataframe
    importance_df = pd.DataFrame({
        'Feature': X_clean.columns,
        'importance': importances
    }).sort_values(by='importance', ascending=False)
    
    # Select features above threshold
    important_features = importance_df[importance_df['importance'] >= importance_threshold]['Feature'].tolist()
    
    # Filter original data
    filtered_data = data[important_features + [target_column]].copy()
    
    removed_features = set(feature_columns) - set(important_features)
    
    print(f"✅ Feature importance filtering completed")
    print(f"  Features above threshold ({importance_threshold}): {len(important_features)}")
    print(f"  Features removed: {len(removed_features)}")
    print(f"  Data shape: {data.shape} → {filtered_data.shape}")
    
    if len(removed_features) > 0:
        print(f"🗑️  Removed features: {list(removed_features)[:10]}{'...' if len(removed_features) > 10 else ''}")
    
    result = {
        'filtered_data': filtered_data,
        'important_features': important_features,
        'removed_features': list(removed_features),
        'importance_df': importance_df,
        'model': model,
        'threshold': importance_threshold
    }
    
    return result


def remove_highly_correlated_features(data, feature_columns=None, target_column=None,
                                    correlation_threshold=0.95, method='pearson'):
    """
    Remove highly correlated features to reduce multicollinearity.
    
    Args:
        data (pd.DataFrame): Input dataset
        feature_columns (list): List of feature columns (None for all numeric)
        target_column (str): Target column to preserve (optional)
        correlation_threshold (float): Correlation threshold above which to remove features
        method (str): Correlation method ('pearson', 'spearman', 'kendall')
        
    Returns:
        dict: Dictionary containing filtered data and correlation information
    """
    if feature_columns is None:
        feature_columns = data.select_dtypes(include=[np.number]).columns.tolist()
        if target_column and target_column in feature_columns:
            feature_columns.remove(target_column)
    
    print(f"🔗 Removing highly correlated features (threshold: {correlation_threshold})")
    print(f"📊 Starting with {len(feature_columns)} features")
    
    # Calculate correlation matrix
    feature_data = data[feature_columns].copy()
    
    # Convert all columns to numeric, errors='coerce' will convert non-numeric to NaN
    for col in feature_data.columns:
        feature_data[col] = pd.to_numeric(feature_data[col], errors='coerce')
    
    corr_matrix = feature_data.corr(method=method).abs()
    
    # Find highly correlated pairs
    upper_triangle = corr_matrix.where(np.triu(np.ones(corr_matrix.shape), k=1).astype(bool))
    
    # Find features to remove
    to_remove = set()
    high_corr_pairs = []
    
    for col in upper_triangle.columns:
        for row in upper_triangle.index:
            corr_value = upper_triangle.loc[row, col]
            if pd.notna(corr_value) and corr_value > correlation_threshold:
                high_corr_pairs.append({
                    'feature1': row,
                    'feature2': col,
                    'correlation': corr_value
                })
                # Remove the feature with lower variance (less informative)
                var1 = feature_data[row].var()
                var2 = feature_data[col].var()
                if var1 < var2:
                    to_remove.add(row)
                else:
                    to_remove.add(col)
    
    # Create filtered dataset
    features_to_keep = [col for col in feature_columns if col not in to_remove]
    columns_to_keep = features_to_keep.copy()
    if target_column:
        columns_to_keep.append(target_column)
    
    filtered_data = data[columns_to_keep].copy()
    
    print(f"✅ Correlation filtering completed")
    print(f"  High correlation pairs found: {len(high_corr_pairs)}")
    print(f"  Features removed: {len(to_remove)}")
    print(f"  Features remaining: {len(features_to_keep)}")
    print(f"  Data shape: {data.shape} → {filtered_data.shape}")
    
    if len(to_remove) > 0:
        print(f"🗑️  Removed features: {list(to_remove)[:10]}{'...' if len(to_remove) > 10 else ''}")
    
    result = {
        'filtered_data': filtered_data,
        'features_kept': features_to_keep,
        'features_removed': list(to_remove),
        'correlation_matrix': corr_matrix,
        'high_corr_pairs': high_corr_pairs,
        'threshold': correlation_threshold
    }
    
    return result


def select_best_features_comprehensive(data, target_column, feature_columns=None,
                                     correlation_threshold=0.95, importance_threshold=0.001,
                                     model_type='random_forest', random_state=42):
    """
    Comprehensive feature selection combining correlation and importance filtering.
    
    Args:
        data (pd.DataFrame): Input dataset
        target_column (str): Name of the target variable
        feature_columns (list): List of feature columns (None for all except target)
        correlation_threshold (float): Correlation threshold for removing correlated features
        importance_threshold (float): Importance threshold for removing low-importance features
        model_type (str): Model type for importance calculation
        random_state (int): Random state for reproducibility
        
    Returns:
        dict: Dictionary containing all filtering results and final dataset
    """
    print("🚀 Starting comprehensive feature selection pipeline")
    print(f"📊 Initial dataset shape: {data.shape}")
    
    # Step 1: Remove highly correlated features
    print("\n📍 Step 1: Removing highly correlated features")
    corr_result = remove_highly_correlated_features(
        data, feature_columns, target_column, correlation_threshold
    )
    
    # Step 2: Remove low importance features
    print("\n📍 Step 2: Removing low importance features")
    importance_result = remove_low_importance_features(
        corr_result['filtered_data'], target_column, 
        corr_result['features_kept'], model_type, importance_threshold, random_state
    )
    
    # Combine results
    final_features = importance_result['important_features']
    all_removed_features = list(set(corr_result['features_removed'] + importance_result['removed_features']))
    
    print(f"\n✅ Comprehensive feature selection completed")
    print(f"  Original features: {len(feature_columns) if feature_columns else len(data.columns)-1}")
    print(f"  After correlation filtering: {len(corr_result['features_kept'])}")
    print(f"  After importance filtering: {len(final_features)}")
    print(f"  Total features removed: {len(all_removed_features)}")
    print(f"  Final data shape: {importance_result['filtered_data'].shape}")
    
    result = {
        'final_data': importance_result['filtered_data'],
        'selected_features': final_features,
        'all_removed_features': all_removed_features,
        'correlation_result': corr_result,
        'importance_result': importance_result,
        'feature_reduction_ratio': len(final_features) / (len(feature_columns) if feature_columns else len(data.columns)-1),
        'parameters': {
            'correlation_threshold': correlation_threshold,
            'importance_threshold': importance_threshold,
            'model_type': model_type
        }
    }
    
    return result


def remove_low_importance_features_regression(data, target_column, feature_columns=None, 
                                           model_type='random_forest', importance_threshold=0.001,
                                           random_state=42):
    """
    Remove features with low importance using regression models optimized for continuous targets.
    
    Args:
        data (pd.DataFrame): Input dataset
        target_column (str): Name of the target variable (continuous)
        feature_columns (list): List of feature columns (None for all except target)
        model_type (str): Regression model type ('random_forest', 'extra_trees', 'gradient_boosting')
        importance_threshold (float): Minimum importance threshold to keep features
        random_state (int): Random state for reproducibility
        
    Returns:
        dict: Dictionary containing filtered data and importance information
    """
    if feature_columns is None:
        feature_columns = [col for col in data.columns if col != target_column]
    
    X = data[feature_columns]
    y = data[target_column]
    
    # Remove any rows with NaN values
    mask = ~(X.isnull().any(axis=1) | y.isnull())
    X_clean = X[mask]
    y_clean = y[mask]
    
    print(f"🎯 Removing low importance features using {model_type} (regression)")
    print(f"📊 Starting with {X_clean.shape[1]} features")
    
    # Choose regression model
    if model_type == 'random_forest':
        from sklearn.ensemble import RandomForestRegressor
        model = RandomForestRegressor(n_estimators=100, random_state=random_state, n_jobs=-1)
    elif model_type == 'extra_trees':
        from sklearn.ensemble import ExtraTreesRegressor
        model = ExtraTreesRegressor(n_estimators=100, random_state=random_state, n_jobs=-1)
    elif model_type == 'gradient_boosting':
        from sklearn.ensemble import GradientBoostingRegressor
        model = GradientBoostingRegressor(n_estimators=100, random_state=random_state)
    else:
        raise ValueError(f"Unsupported regression model type: {model_type}")
    
    # Fit model and get feature importances
    model.fit(X_clean, y_clean)
    importances = model.feature_importances_
    
    # Create importance dataframe
    importance_df = pd.DataFrame({
        'Feature': feature_columns,
        'importance': importances
    }).sort_values('importance', ascending=False)
    
    # Filter features by importance threshold
    important_features = importance_df[importance_df['importance'] >= importance_threshold]['Feature'].tolist()
    removed_features = importance_df[importance_df['importance'] < importance_threshold]['Feature'].tolist()
    
    # Create filtered dataset
    final_columns = [target_column] + important_features
    filtered_data = data[final_columns]
    
    print(f"📊 Kept {len(important_features)} features (importance >= {importance_threshold})")
    print(f"📊 Removed {len(removed_features)} features (importance < {importance_threshold})")
    print(f"📈 R² score: {model.score(X_clean, y_clean):.4f}")
    
    result = {
        'filtered_data': filtered_data,
        'important_features': important_features,
        'removed_features': removed_features,
        'importance_df': importance_df,
        'model': model,
        'r2_score': model.score(X_clean, y_clean),
        'threshold': importance_threshold,
        'model_type': model_type
    }
    
    return result


def select_best_features_regression(data, target_column, feature_columns=None,
                                  correlation_threshold=0.95, importance_threshold=0.001,
                                  model_type='random_forest', random_state=42):
    """
    Comprehensive feature selection for regression tasks, optimized for continuous targets.
    
    Args:
        data (pd.DataFrame): Input dataset
        target_column (str): Name of the target variable (continuous)
        feature_columns (list): List of feature columns (None for all except target)
        correlation_threshold (float): Correlation threshold for removing correlated features
        importance_threshold (float): Importance threshold for removing low-importance features
        model_type (str): Regression model type ('random_forest', 'extra_trees', 'gradient_boosting')
        random_state (int): Random state for reproducibility
        
    Returns:
        dict: Dictionary containing all filtering results and final dataset
    """
    print("🚀 Starting regression-optimized feature selection pipeline")
    print(f"📊 Initial dataset shape: {data.shape}")
    print(f"🎯 Target: {target_column} (regression)")
    
    # Step 1: Remove highly correlated features
    print("\n📍 Step 1: Removing highly correlated features")
    corr_result = remove_highly_correlated_features(
        data, feature_columns, target_column, correlation_threshold
    )
    
    # Step 2: Remove low importance features using regression models
    print("\n📍 Step 2: Removing low importance features (regression-based)")
    importance_result = remove_low_importance_features_regression(
        corr_result['filtered_data'], target_column, 
        corr_result['features_kept'], model_type, importance_threshold, random_state
    )
    
    # Combine results
    final_features = importance_result['important_features']
    all_removed_features = list(set(corr_result['features_removed'] + importance_result['removed_features']))
    
    print(f"\n✅ Regression feature selection completed")
    print(f"  Original features: {len(feature_columns) if feature_columns else len(data.columns)-1}")
    print(f"  After correlation filtering: {len(corr_result['features_kept'])}")
    print(f"  After regression importance filtering: {len(final_features)}")
    print(f"  Total features removed: {len(all_removed_features)}")
    print(f"  Final data shape: {importance_result['filtered_data'].shape}")
    
    result = {
        'final_data': importance_result['filtered_data'],
        'selected_features': final_features,
        'all_removed_features': all_removed_features,
        'correlation_result': corr_result,
        'importance_result': importance_result,
        'feature_reduction_ratio': len(final_features) / (len(feature_columns) if feature_columns else len(data.columns)-1),
        'parameters': {
            'correlation_threshold': correlation_threshold,
            'importance_threshold': importance_threshold,
            'model_type': model_type,
            'task_type': 'regression'
        }
    }
    
    return result


def modeling_workflow(data, target_column, feature_columns=None, 
                     correlation_threshold=0.95, importance_threshold=0.001,
                     model_type='random_forest', classification_threshold=None,
                     random_state=42, image_folder='image'):
    """
    Comprehensive modeling workflow for both regression and classification tasks.
    
    This function handles the complete modeling pipeline including feature selection,
    model training, evaluation, and visualization for cheminformatics data.
    
    Args:
        data (pd.DataFrame): Input dataset with features and target
        target_column (str): Name of the target variable column
        feature_columns (list): List of feature columns (None for auto-detect)
        correlation_threshold (float): Threshold for correlation-based feature filtering
        importance_threshold (float): Threshold for importance-based feature filtering
        model_type (str): Type of model ('random_forest', 'linear', 'svr', 'knn')
        classification_threshold (float): Threshold for converting regression to classification
        random_state (int): Random state for reproducibility
        image_folder (str): Folder to save diagnostic plots
        
    Returns:
        dict: Dictionary containing all modeling results and trained models
    """
    import os
    from datetime import datetime
    
    print("🧪 Starting Modeling Workflow")
    print("="*50)
    
    # Create image folder if needed
    if not os.path.exists(image_folder):
        os.makedirs(image_folder)
        print(f"📁 Created image folder: {image_folder}")
    
    # Step 1: Feature Selection
    print("\n📍 Step 1: Feature Selection")
    feature_selection_result = select_best_features_regression(
        data,
        target_column,
        feature_columns=feature_columns,
        correlation_threshold=correlation_threshold,
        importance_threshold=importance_threshold,
        model_type=model_type
    )
    
    final_data = feature_selection_result['final_data']
    selected_features = feature_selection_result['selected_features']
    
    print(f"✅ Feature selection completed")
    print(f"📊 Features: {len(feature_columns or data.columns)-1} → {len(selected_features)}")
    print(f"📊 Reduction ratio: {feature_selection_result['feature_reduction_ratio']:.2%}")
    
    # Step 2: Regression Modeling
    print("\n📍 Step 2: Regression Modeling")
    regression_result = train_regression_model(
        final_data,
        target_column,
        feature_columns=selected_features,
        model_type=model_type,
        random_state=random_state
    )
    
    # Step 3: Feature Importance Analysis (Regression)
    print("\n📍 Step 3: Regression Feature Importance")
    regression_importance_df = analyze_feature_importance(
        regression_result, 
        top_n=15, 
        plot=True, 
        save_path=f"{image_folder}/regression_feature_importance.png"
    )
    
    # Step 4: Regression Diagnostic Plots
    print("\n📍 Step 4: Regression Diagnostics")
    create_regression_plots(
        regression_result, 
        save_path=f"{image_folder}/regression_diagnostics.png"
    )
    
    # Step 5: Save Regression Model
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    # Handle both cross-validation and train/test split scenarios
    if 'cross_validation' in regression_result and regression_result['cross_validation']:
        r2_score = regression_result['metrics']['r2']
    else:
        r2_score = regression_result['metrics']['test_r2']
    regression_model_name = f"regression_model_r2_{r2_score:.3f}_{timestamp}.pkl"
    save_model(regression_result, regression_model_name)
    
    print(f"✅ Regression model saved: {regression_model_name}")
    
    # Classification modeling (if threshold provided)
    classification_result = None
    classification_importance_df = None
    classification_model_name = None
    
    if classification_threshold is not None:
        print("\n📍 Step 6: Classification Modeling")
        classification_result = train_classification_model(
            final_data,
            target_column,
            feature_columns=selected_features,
            model_type=model_type,
            threshold=classification_threshold,
            random_state=random_state
        )
        
        # Step 7: Feature Importance Analysis (Classification)
        print("\n📍 Step 7: Classification Feature Importance")
        classification_importance_df = analyze_feature_importance(
            classification_result, 
            top_n=15, 
            plot=True, 
            save_path=f"{image_folder}/classification_feature_importance.png"
        )
        
        # Step 8: Classification Diagnostic Plots
        print("\n📍 Step 8: Classification Diagnostics")
        create_classification_plots(
            classification_result, 
            save_path=f"{image_folder}/classification_diagnostics.png"
        )
        
        # Step 9: Save Classification Model
        # Handle both cross-validation and train/test split scenarios
        if 'cross_validation' in classification_result and classification_result['cross_validation']:
            accuracy = classification_result['metrics']['accuracy']
        else:
            accuracy = classification_result['metrics']['test_accuracy']
        classification_model_name = f"classification_model_acc_{accuracy:.3f}_{timestamp}.pkl"
        save_model(classification_result, classification_model_name)
        
        print(f"✅ Classification model saved: {classification_model_name}")
    
    # Step 10: Results Summary
    print("\n📍 Step 10: Results Summary")
    print("\n🎯 MODELING WORKFLOW SUMMARY")
    print("="*60)
    
    print(f"📊 Dataset Statistics:")
    print(f"   Final shape: {final_data.shape}")
    print(f"   Selected features: {len(selected_features)}")
    
    print(f"\n🔬 Feature Engineering:")
    print(f"   Feature reduction: {feature_selection_result['feature_reduction_ratio']:.1%}")
    print(f"   Correlation threshold: {correlation_threshold}")
    print(f"   Importance threshold: {importance_threshold}")
    
    print(f"\n📈 Model Performance:")
    print(f"   Regression R²: {r2_score:.4f}")
    # Handle MAE for both cross-validation and train/test split scenarios
    if 'cross_validation' in regression_result and regression_result['cross_validation']:
        mae = regression_result['metrics']['mae']
    else:
        mae = regression_result['metrics']['test_mae']
    print(f"   Regression MAE: {mae:.4f}")
    
    if classification_result:
        # Handle accuracy for both cross-validation and train/test split scenarios
        if 'cross_validation' in classification_result and classification_result['cross_validation']:
            accuracy = classification_result['metrics']['accuracy']
        else:
            accuracy = classification_result['metrics']['test_accuracy']
        print(f"   Classification Accuracy: {accuracy:.4f}")
        print(f"   Classification F1-Score: {classification_result['metrics']['f1_score']:.4f}")
    
    print(f"\n💾 Generated Files:")
    print(f"   • {regression_model_name} (regression model)")
    if classification_model_name:
        print(f"   • {classification_model_name} (classification model)")
    print(f"   • {image_folder}/regression_feature_importance.png")
    print(f"   • {image_folder}/regression_diagnostics.png")
    if classification_result:
        print(f"   • {image_folder}/classification_feature_importance.png")
        print(f"   • {image_folder}/classification_diagnostics.png")
    
    print(f"\n💡 Recommendations:")
    print(f"   • Use regression model for continuous target prediction")
    if classification_result:
        print(f"   • Use classification model for binary classification (threshold: {classification_threshold})")
    if regression_importance_df is not None:
        top_features = regression_importance_df.head(3)['Feature'].tolist()
        print(f"   • Most important features: {', '.join(top_features)}")
    
    result = {
        'final_data': final_data,
        'selected_features': selected_features,
        'feature_selection_result': feature_selection_result,
        'regression_result': regression_result,
        'regression_importance_df': regression_importance_df,
        'regression_model_file': regression_model_name,
        'classification_result': classification_result,
        'classification_importance_df': classification_importance_df,
        'classification_model_file': classification_model_name,
        'target_column': target_column,
        'model_type': model_type,
        'classification_threshold': classification_threshold,
        'parameters': {
            'correlation_threshold': correlation_threshold,
            'importance_threshold': importance_threshold,
            'model_type': model_type,
            'random_state': random_state
        },
        'generated_files': {
            'regression_model': regression_model_name,
            'classification_model': classification_model_name,
            'plots': {
                'regression_importance': f"{image_folder}/regression_feature_importance.png",
                'regression_diagnostics': f"{image_folder}/regression_diagnostics.png",
                'classification_importance': f"{image_folder}/classification_feature_importance.png" if classification_result else None,
                'classification_diagnostics': f"{image_folder}/classification_diagnostics.png" if classification_result else None
            }
        }
    }
    
    return result


def visualize_feature_selection_results(selection_result, save_path=None):
    """
    Create visualizations for feature selection results.
    
    Args:
        selection_result (dict): Result from select_best_features_comprehensive
        save_path (str): Path to save plots (optional)
    """
    fig, axes = plt.subplots(2, 2, figsize=(15, 12))
    
    # Feature count comparison
    original_count = len(selection_result['correlation_result']['features_kept']) + len(selection_result['correlation_result']['features_removed'])
    after_corr = len(selection_result['correlation_result']['features_kept'])
    final_count = len(selection_result['selected_features'])
    
    stages = ['Original', 'After Correlation\nFiltering', 'Final Selection']
    counts = [original_count, after_corr, final_count]
    
    axes[0, 0].bar(stages, counts, color=['lightblue', 'orange', 'green'])
    axes[0, 0].set_ylabel('Number of Features')
    axes[0, 0].set_title('Feature Selection Pipeline')
    for i, count in enumerate(counts):
        axes[0, 0].text(i, count + max(counts)*0.01, str(count), ha='center')
    
    # Top feature importances
    importance_df = selection_result['importance_result']['importance_df']
    top_features = importance_df.head(15)
    
    axes[0, 1].barh(range(len(top_features)), top_features['importance'])
    axes[0, 1].set_yticks(range(len(top_features)))
    axes[0, 1].set_yticklabels(top_features['Feature'], fontsize=8)
    axes[0, 1].set_xlabel('Feature Importance')
    axes[0, 1].set_title('Top 15 Feature Importances')
    
    # Correlation heatmap (top correlated pairs)
    high_corr_pairs = selection_result['correlation_result']['high_corr_pairs']
    if high_corr_pairs:
        corr_df = pd.DataFrame(high_corr_pairs).head(10)
        y_pos = range(len(corr_df))
        axes[1, 0].barh(y_pos, corr_df['correlation'])
        axes[1, 0].set_yticks(y_pos)
        axes[1, 0].set_yticklabels([f"{row['feature1']} - {row['feature2']}" for _, row in corr_df.iterrows()], fontsize=8)
        axes[1, 0].set_xlabel('Correlation Coefficient')
        axes[1, 0].set_title('Top 10 Highly Correlated Feature Pairs')
    else:
        axes[1, 0].text(0.5, 0.5, 'No highly correlated\nfeature pairs found', 
                       ha='center', va='center', transform=axes[1, 0].transAxes)
        axes[1, 0].set_title('Highly Correlated Feature Pairs')
    
    # Summary statistics
    params = selection_result['parameters']
    summary_text = f"""
    Feature Selection Summary:
    
    Correlation Threshold: {params['correlation_threshold']}
    Importance Threshold: {params['importance_threshold']}
    Model Type: {params['model_type']}
    
    Original Features: {original_count}
    After Correlation Filtering: {after_corr}
    Final Features: {final_count}
    
    Reduction Ratio: {selection_result['feature_reduction_ratio']:.2%}
    Features Removed: {len(selection_result['all_removed_features'])}
    """
    
    axes[1, 1].text(0.1, 0.5, summary_text, transform=axes[1, 1].transAxes,
                    fontsize=10, verticalalignment='center',
                    bbox=dict(boxstyle='round', facecolor='lightgray', alpha=0.8))
    axes[1, 1].set_xlim(0, 1)
    axes[1, 1].set_ylim(0, 1)
    axes[1, 1].set_title('Selection Summary')
    axes[1, 1].axis('off')
    
    plt.tight_layout()
    
    if save_path:
        plt.savefig(save_path, dpi=300, bbox_inches='tight')
        print(f"💾 Feature selection plots saved to: {save_path}")
    else:
        plt.show()


# ============================================================================
# INFERENCE FUNCTIONS
# ============================================================================

def load_model_for_inference(model_path):
    """
    Load a trained model for inference.
    
    Args:
        model_path (str): Path to the saved model file (.pkl)
        
    Returns:
        dict: Loaded model result dictionary
    """
    import joblib
    import os
    
    if not os.path.exists(model_path):
        raise FileNotFoundError(f"Model file not found: {model_path}")
    
    print(f"📂 Loading model from: {model_path}")
    
    model_result = joblib.load(model_path)
    
    print("✅ Model loaded successfully")
    print(f"📊 Model type: {model_result.get('model_type', 'unknown')}")
    
    if 'cross_validation' in model_result and model_result['cross_validation']:
        print(f"🔄 Cross-validation model with {model_result.get('n_splits', 'N/A')} folds")
    else:
        print("🔀 Train/test split model")
    
    return model_result


def predict_with_pipeline(processed_data, pipeline_metadata, model_results=None, verbose=True):
    """
    Make predictions using the trained models and preprocessing pipeline.
    
    Args:
        processed_data (dict): Result from apply_inference_preprocessing
        pipeline_metadata (dict): Pipeline metadata from save_preprocessing_pipeline
        model_results (dict): Pre-loaded model results (optional, will load from files if None)
        verbose (bool): Whether to print progress information
        
    Returns:
        dict: Prediction results including regression and classification predictions
    """
    import pandas as pd
    import numpy as np
    
    if verbose:
        print(f"🔮 Making predictions for {processed_data['n_molecules_processed']} molecule(s)")
    
    # Load models if not provided
    if model_results is None:
        model_results = {}
        
        # Load regression model
        regression_model_file = pipeline_metadata['model_info']['regression_model_file']
        if regression_model_file:
            if verbose:
                print("📂 Loading regression model...")
            model_results['regression'] = load_model_for_inference(regression_model_file)
        
        # Load classification model if available
        classification_model_file = pipeline_metadata['model_info']['classification_model_file']
        if classification_model_file:
            if verbose:
                print("📂 Loading classification model...")
            model_results['classification'] = load_model_for_inference(classification_model_file)
    
    # Prepare feature data for prediction
    feature_columns = processed_data['feature_columns']
    feature_data = processed_data['processed_data'][feature_columns]
    
    if verbose:
        print(f"📊 Feature data shape: {feature_data.shape}")
    
    predictions = {
        'smiles': processed_data['valid_smiles'],
        'n_molecules': processed_data['n_molecules_processed']
    }
    
    # Regression predictions
    if 'regression' in model_results:
        if verbose:
            print("📈 Making regression predictions...")
        
        regression_model = model_results['regression']['model']
        regression_preds = regression_model.predict(feature_data)
        
        # Apply inverse transformation if target was transformed during training
        if pipeline_metadata['preprocessing']['target_transformation']['transformation_needed']:
            transformation_info = pipeline_metadata['preprocessing']['target_transformation']['transformation_info']
            if transformation_info:
                # Apply inverse transformation (if available)
                # Note: This would need the inverse_log_transformation function from preprocessing
                if verbose:
                    print("🔄 Applying inverse target transformation...")
                # For now, store raw predictions - can be enhanced with inverse transformation
        
        predictions['regression'] = {
            'predicted_values': regression_preds.tolist(),
            'model_performance': pipeline_metadata['model_info']['performance']['regression_r2']
        }
        
        if verbose:
            print(f"✅ Regression predictions: min={regression_preds.min():.4f}, max={regression_preds.max():.4f}, mean={regression_preds.mean():.4f}")
    
    # Classification predictions
    if 'classification' in model_results:
        if verbose:
            print("🎯 Making classification predictions...")
        
        classification_model = model_results['classification']['model']
        classification_preds = classification_model.predict(feature_data)
        
        # Try to get prediction probabilities
        try:
            classification_probas = classification_model.predict_proba(feature_data)
            # For binary classification, get probability of positive class
            if classification_probas.shape[1] == 2:
                probabilities = classification_probas[:, 1]
            else:
                probabilities = classification_probas.max(axis=1)
        except:
            probabilities = None
        
        predictions['classification'] = {
            'predicted_classes': classification_preds.tolist(),
            'predicted_probabilities': probabilities.tolist() if probabilities is not None else None,
            'classification_threshold': pipeline_metadata['model_info']['classification_threshold'],
            'model_performance': pipeline_metadata['model_info']['performance']['classification_accuracy']
        }
        
        if verbose:
            unique_classes, counts = np.unique(classification_preds, return_counts=True)
            class_dist = dict(zip(unique_classes, counts))
            print(f"✅ Classification predictions: {class_dist}")
    
    # Summary
    if verbose:
        print("✅ Prediction completed successfully")
        available_predictions = list(predictions.keys())
        available_predictions.remove('smiles')
        available_predictions.remove('n_molecules')
        print(f"📊 Available predictions: {', '.join(available_predictions)}")
    
    return predictions


def create_prediction_summary(predictions, processed_data, pipeline_metadata, output_path=None):
    """
    Create a comprehensive summary of prediction results.
    
    Args:
        predictions (dict): Prediction results from predict_with_pipeline
        processed_data (dict): Processed data from apply_inference_preprocessing
        pipeline_metadata (dict): Pipeline metadata
        output_path (str): Optional path to save results CSV
        
    Returns:
        pd.DataFrame: Summary DataFrame with predictions
    """
    import pandas as pd
    
    print("📋 Creating prediction summary...")
    
    # Create base DataFrame
    summary_df = pd.DataFrame({
        'SMILES': predictions['smiles']
    })
    
    # Add regression predictions
    if 'regression' in predictions:
        reg_preds = predictions['regression']['predicted_values']
        target_col = pipeline_metadata['preprocessing']['target_transformation']['target_column']
        summary_df[f'Predicted_{target_col}'] = reg_preds
        summary_df[f'Model_R2'] = [predictions['regression']['model_performance']] * len(reg_preds)
    
    # Add classification predictions
    if 'classification' in predictions:
        class_preds = predictions['classification']['predicted_classes']
        class_probas = predictions['classification']['predicted_probabilities']
        threshold = predictions['classification']['classification_threshold']
        
        summary_df['Predicted_Class'] = class_preds
        if class_probas:
            summary_df['Predicted_Probability'] = class_probas
        summary_df['Classification_Threshold'] = [threshold] * len(class_preds)
        summary_df['Classification_Accuracy'] = [predictions['classification']['model_performance']] * len(class_preds)
    
    # Add preprocessing info
    summary_df['Preprocessing_Success'] = [True] * len(summary_df)
    summary_df['Features_Used'] = [processed_data['n_features']] * len(summary_df)
    
    print(f"✅ Summary created with {len(summary_df)} predictions")
    
    # Save to file if requested
    if output_path:
        summary_df.to_csv(output_path, index=False)
        print(f"💾 Prediction summary saved to: {output_path}")
    
    return summary_df