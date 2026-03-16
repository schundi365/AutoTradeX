"""
Feature Importance Analysis using SHAP values.

This module provides functionality to compute SHAP (SHapley Additive exPlanations) values
for tree-based models to explain feature importance and identify feature interactions.

Requirements: 15.1, 15.2, 15.3, 15.4
"""

import os
import logging
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import shap

logger = logging.getLogger(__name__)


@dataclass
class FeatureImportanceResult:
    """
    Results from SHAP feature importance analysis.
    
    Attributes:
        feature_rankings: List of (feature_name, mean_abs_shap_value) tuples, sorted by importance
        shap_values: SHAP values array for all samples
        feature_names: List of feature names
        interaction_values: SHAP interaction values (if computed)
        plots_dir: Directory where plots are saved
    """
    feature_rankings: List[Tuple[str, float]]
    shap_values: np.ndarray
    feature_names: List[str]
    interaction_values: Optional[np.ndarray] = None
    plots_dir: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage"""
        return {
            'feature_rankings': self.feature_rankings,
            'feature_names': self.feature_names,
            'plots_dir': self.plots_dir,
            'has_interaction_values': self.interaction_values is not None
        }


class FeatureImportanceAnalyzer:
    """
    Analyzes feature importance using SHAP values for tree-based models.
    
    Supports XGBoost and LightGBM models.
    """
    
    def __init__(self, model_dir: str = "models"):
        """
        Initialize the feature importance analyzer.
        
        Args:
            model_dir: Base directory for storing model artifacts
        """
        self.model_dir = model_dir
        os.makedirs(model_dir, exist_ok=True)
    
    def compute_shap_values(
        self,
        model: Any,
        X: pd.DataFrame,
        model_type: str = "xgboost",
        max_samples: int = 1000
    ) -> Tuple[np.ndarray, shap.Explainer]:
        """
        Compute SHAP values for a tree-based model.
        
        Requirements: 15.1
        
        Args:
            model: Trained XGBoost or LightGBM model
            X: Feature data (validation or test set)
            model_type: Type of model ("xgboost" or "lightgbm")
            max_samples: Maximum number of samples to use for SHAP computation
        
        Returns:
            Tuple of (shap_values array, explainer object)
        
        Raises:
            ValueError: If model_type is not supported
        """
        logger.info(f"Computing SHAP values for {model_type} model with {len(X)} samples")
        
        # Limit samples for computational efficiency
        if len(X) > max_samples:
            logger.info(f"Sampling {max_samples} from {len(X)} samples for SHAP computation")
            X_sample = X.sample(n=max_samples, random_state=42)
        else:
            X_sample = X
        
        # Create appropriate explainer based on model type
        if model_type.lower() in ["xgboost", "xgb"]:
            explainer = shap.TreeExplainer(model)
        elif model_type.lower() in ["lightgbm", "lgbm"]:
            explainer = shap.TreeExplainer(model)
        else:
            raise ValueError(f"Unsupported model type: {model_type}. Use 'xgboost' or 'lightgbm'")
        
        # Compute SHAP values
        shap_values = explainer.shap_values(X_sample)
        
        # For binary classification, shap_values might be a list
        # We want the SHAP values for the positive class
        if isinstance(shap_values, list):
            shap_values = shap_values[1]  # Positive class
        
        logger.info(f"SHAP values computed with shape: {shap_values.shape}")
        return shap_values, explainer
    
    def rank_features_by_shap(
        self,
        shap_values: np.ndarray,
        feature_names: List[str]
    ) -> List[Tuple[str, float]]:
        """
        Rank features by mean absolute SHAP value.
        
        Requirements: 15.2
        
        Args:
            shap_values: SHAP values array (n_samples, n_features)
            feature_names: List of feature names
        
        Returns:
            List of (feature_name, mean_abs_shap_value) tuples, sorted by importance (descending)
        """
        logger.info("Ranking features by mean absolute SHAP value")
        
        # Compute mean absolute SHAP value for each feature
        mean_abs_shap = np.abs(shap_values).mean(axis=0)
        
        # Create list of (feature_name, importance) tuples
        feature_importance = list(zip(feature_names, mean_abs_shap))
        
        # Sort by importance (descending)
        feature_importance.sort(key=lambda x: x[1], reverse=True)
        
        logger.info(f"Top 5 features: {feature_importance[:5]}")
        return feature_importance
    
    def compute_interaction_values(
        self,
        model: Any,
        X: pd.DataFrame,
        model_type: str = "xgboost",
        max_samples: int = 500
    ) -> np.ndarray:
        """
        Compute SHAP interaction values to identify feature interactions.
        
        Requirements: 15.3
        
        Args:
            model: Trained XGBoost or LightGBM model
            X: Feature data (validation or test set)
            model_type: Type of model ("xgboost" or "lightgbm")
            max_samples: Maximum number of samples (interaction computation is expensive)
        
        Returns:
            SHAP interaction values array (n_samples, n_features, n_features)
        
        Note:
            Interaction value computation is computationally expensive.
            Use a smaller max_samples value for large datasets.
        """
        logger.info(f"Computing SHAP interaction values for {model_type} model")
        
        # Limit samples for computational efficiency (interactions are expensive)
        if len(X) > max_samples:
            logger.info(f"Sampling {max_samples} from {len(X)} samples for interaction computation")
            X_sample = X.sample(n=max_samples, random_state=42)
        else:
            X_sample = X
        
        # Create explainer
        if model_type.lower() in ["xgboost", "xgb"]:
            explainer = shap.TreeExplainer(model)
        elif model_type.lower() in ["lightgbm", "lgbm"]:
            explainer = shap.TreeExplainer(model)
        else:
            raise ValueError(f"Unsupported model type: {model_type}")
        
        # Compute interaction values
        interaction_values = explainer.shap_interaction_values(X_sample)
        
        # For binary classification, interaction_values might be a list
        if isinstance(interaction_values, list):
            interaction_values = interaction_values[1]  # Positive class
        
        logger.info(f"Interaction values computed with shape: {interaction_values.shape}")
        return interaction_values
    
    def generate_feature_importance_plots(
        self,
        shap_values: np.ndarray,
        X: pd.DataFrame,
        feature_names: List[str],
        output_dir: str,
        top_n: int = 20
    ) -> Dict[str, str]:
        """
        Generate feature importance plots using SHAP values.
        
        Requirements: 15.4
        
        Args:
            shap_values: SHAP values array
            X: Feature data used for SHAP computation
            feature_names: List of feature names
            output_dir: Directory to save plots
            top_n: Number of top features to display (default: 20)
        
        Returns:
            Dictionary mapping plot type to file path
        """
        logger.info(f"Generating feature importance plots (top {top_n} features)")
        os.makedirs(output_dir, exist_ok=True)
        
        plot_paths = {}
        
        # 1. Bar plot of mean absolute SHAP values (top N features)
        try:
            plt.figure(figsize=(10, 8))
            shap.summary_plot(
                shap_values,
                X,
                feature_names=feature_names,
                plot_type="bar",
                max_display=top_n,
                show=False
            )
            bar_plot_path = os.path.join(output_dir, "feature_importance_bar.png")
            plt.tight_layout()
            plt.savefig(bar_plot_path, dpi=150, bbox_inches='tight')
            plt.close()
            plot_paths['bar_plot'] = bar_plot_path
            logger.info(f"Saved bar plot to {bar_plot_path}")
        except Exception as e:
            logger.error(f"Failed to generate bar plot: {e}")
        
        # 2. Summary plot (beeswarm) showing feature values and SHAP values
        try:
            plt.figure(figsize=(10, 8))
            shap.summary_plot(
                shap_values,
                X,
                feature_names=feature_names,
                max_display=top_n,
                show=False
            )
            summary_plot_path = os.path.join(output_dir, "feature_importance_summary.png")
            plt.tight_layout()
            plt.savefig(summary_plot_path, dpi=150, bbox_inches='tight')
            plt.close()
            plot_paths['summary_plot'] = summary_plot_path
            logger.info(f"Saved summary plot to {summary_plot_path}")
        except Exception as e:
            logger.error(f"Failed to generate summary plot: {e}")
        
        # 3. Waterfall plot for a single prediction (first sample)
        try:
            plt.figure(figsize=(10, 8))
            shap.waterfall_plot(
                shap.Explanation(
                    values=shap_values[0],
                    base_values=shap_values.mean(axis=0).mean(),
                    data=X.iloc[0].values,
                    feature_names=feature_names
                ),
                max_display=top_n,
                show=False
            )
            waterfall_plot_path = os.path.join(output_dir, "feature_importance_waterfall.png")
            plt.tight_layout()
            plt.savefig(waterfall_plot_path, dpi=150, bbox_inches='tight')
            plt.close()
            plot_paths['waterfall_plot'] = waterfall_plot_path
            logger.info(f"Saved waterfall plot to {waterfall_plot_path}")
        except Exception as e:
            logger.error(f"Failed to generate waterfall plot: {e}")
        
        return plot_paths
    
    def analyze_feature_importance(
        self,
        model: Any,
        X: pd.DataFrame,
        model_type: str = "xgboost",
        model_id: str = "model",
        compute_interactions: bool = False,
        max_samples: int = 1000,
        top_n_features: int = 20
    ) -> FeatureImportanceResult:
        """
        Complete feature importance analysis pipeline.
        
        This method:
        1. Computes SHAP values
        2. Ranks features by importance
        3. Optionally computes interaction values
        4. Generates visualization plots
        
        Requirements: 15.1, 15.2, 15.3, 15.4
        
        Args:
            model: Trained tree-based model
            X: Feature data (validation or test set)
            model_type: Type of model ("xgboost" or "lightgbm")
            model_id: Model identifier for organizing output files
            compute_interactions: Whether to compute SHAP interaction values
            max_samples: Maximum samples for SHAP computation
            top_n_features: Number of top features to display in plots
        
        Returns:
            FeatureImportanceResult containing rankings, values, and plot paths
        """
        logger.info(f"Starting feature importance analysis for model {model_id}")
        
        feature_names = list(X.columns)
        
        # 1. Compute SHAP values
        shap_values, explainer = self.compute_shap_values(
            model, X, model_type, max_samples
        )
        
        # 2. Rank features
        feature_rankings = self.rank_features_by_shap(shap_values, feature_names)
        
        # 3. Optionally compute interaction values
        interaction_values = None
        if compute_interactions:
            try:
                interaction_values = self.compute_interaction_values(
                    model, X, model_type, max_samples=min(max_samples, 500)
                )
            except Exception as e:
                logger.warning(f"Failed to compute interaction values: {e}")
        
        # 4. Generate plots
        output_dir = os.path.join(self.model_dir, model_id, "feature_importance")
        plot_paths = self.generate_feature_importance_plots(
            shap_values,
            X.iloc[:len(shap_values)],  # Match the sampled data
            feature_names,
            output_dir,
            top_n=top_n_features
        )
        
        result = FeatureImportanceResult(
            feature_rankings=feature_rankings,
            shap_values=shap_values,
            feature_names=feature_names,
            interaction_values=interaction_values,
            plots_dir=output_dir
        )
        
        logger.info(f"Feature importance analysis complete. Plots saved to {output_dir}")
        return result
    
    def save_feature_rankings(
        self,
        feature_rankings: List[Tuple[str, float]],
        output_path: str
    ):
        """
        Save feature rankings to a CSV file.
        
        Args:
            feature_rankings: List of (feature_name, importance) tuples
            output_path: Path to save CSV file
        """
        df = pd.DataFrame(feature_rankings, columns=['feature_name', 'mean_abs_shap_value'])
        df.to_csv(output_path, index=False)
        logger.info(f"Feature rankings saved to {output_path}")
    
    def get_top_feature_interactions(
        self,
        interaction_values: np.ndarray,
        feature_names: List[str],
        top_n: int = 10
    ) -> List[Tuple[str, str, float]]:
        """
        Identify top feature interactions from SHAP interaction values.
        
        Args:
            interaction_values: SHAP interaction values (n_samples, n_features, n_features)
            feature_names: List of feature names
            top_n: Number of top interactions to return
        
        Returns:
            List of (feature1, feature2, mean_abs_interaction) tuples
        """
        logger.info("Identifying top feature interactions")
        
        # Average interaction values across samples
        mean_interaction = np.abs(interaction_values).mean(axis=0)
        
        # Get upper triangle (avoid duplicates and diagonal)
        n_features = len(feature_names)
        interactions = []
        
        for i in range(n_features):
            for j in range(i + 1, n_features):
                interaction_strength = mean_interaction[i, j]
                interactions.append((feature_names[i], feature_names[j], interaction_strength))
        
        # Sort by interaction strength
        interactions.sort(key=lambda x: x[2], reverse=True)
        
        top_interactions = interactions[:top_n]
        logger.info(f"Top 3 interactions: {top_interactions[:3]}")
        
        return top_interactions
