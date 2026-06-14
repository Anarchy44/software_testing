"""Donut anomaly detector with MCMC imputation and KDE scoring.

Implements the detection pipeline from Donut paper:
1. MCMC iterative imputation for missing values
2. Reconstruction probability computation
3. KDE-based anomaly scoring
"""

import torch
import numpy as np
from scipy.stats import gaussian_kde
from typing import List, Tuple


class MCMCImputer:
    """MCMC-based missing value imputation.

    Following Donut paper Section 3.3: iteratively sample latent variables
    and reconstruct missing values to reduce bias in representation learning.

    Args:
        n_iterations: Number of MCMC iterations (default: 10)
    """

    def __init__(self, n_iterations: int = 10):
        self.n_iterations = n_iterations

    def impute(
        self, model, x: torch.Tensor, mask: torch.Tensor
    ) -> torch.Tensor:
        """Impute missing values using MCMC sampling.

        Algorithm:
        1. Initialize missing values with zeros
        2. For each iteration:
           a. Sample z from posterior q(z|x_observed, x_missing)
           b. Reconstruct x from z
           c. Update missing values with reconstruction

        Args:
            model: Trained DonutVAE model
            x: Input tensor with missing values set to 0 (batch_size, input_dim)
            mask: Binary mask indicating valid points (1=valid, 0=missing)

        Returns:
            Tensor with imputed missing values
        """
        x_imputed = x.clone()

        with torch.no_grad():
            for _ in range(self.n_iterations):
                # Encode current state
                mu, logvar = model.encode(x_imputed)

                # Sample from posterior
                std = torch.exp(0.5 * logvar)
                eps = torch.randn_like(std)
                z = mu + eps * std

                # Decode to get reconstruction
                x_recon = model.decode(z)

                # Update only missing values, keep observed values fixed
                x_imputed = x * mask + x_recon * (1 - mask)

        return x_imputed


class DonutDetector:
    """Anomaly detector using trained Donut VAE.

    Implements two scoring methods:
    1. Reconstruction Probability (RP): P(x|z) under Gaussian assumption
    2. KDE Score: Kernel density estimation of reconstruction errors

    Args:
        model: Trained DonutVAE model
        device: Device for computation ('cpu' or 'cuda')
        n_samples: Number of samples for Monte Carlo estimation (default: 100)
        use_kde: Whether to use KDE scoring (default: True)
    """

    def __init__(
        self,
        model,
        device: str = "auto",
        n_samples: int = 100,
        use_kde: bool = True,
    ):
        if device == "auto":
            self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        else:
            self.device = torch.device(device)

        self.model = model.to(self.device)
        self.model.eval()
        self.n_samples = n_samples
        self.use_kde = use_kde

        self.mcmc_imputer = MCMCImputer(n_iterations=10)

        # KDE model (fitted on training data)
        self.kde_model = None
        self.threshold = None

    def compute_reconstruction_probability(
        self, x: torch.Tensor, mask: torch.Tensor | None = None
    ) -> torch.Tensor:
        """Compute reconstruction probability for anomaly scoring.

        Lower probability indicates more anomalous.

        Args:
            x: Input tensor (batch_size, input_dim)
            mask: Optional mask for missing values

        Returns:
            Tensor of log probabilities (batch_size,)
        """
        batch_size = x.size(0)
        log_probs = []

        with torch.no_grad():
            # Impute missing values if needed
            if mask is not None:
                x_filled = self.mcmc_imputer.impute(self.model, x, mask)
            else:
                x_filled = x

            # Monte Carlo estimation of log p(x)
            for _ in range(self.n_samples):
                # Sample z from posterior
                mu, logvar = self.model.encode(x_filled)
                std = torch.exp(0.5 * logvar)
                eps = torch.randn_like(std)
                z = mu + eps * std

                # Compute log p(x|z) assuming Gaussian likelihood
                x_recon = self.model.decode(z)

                # Log likelihood under Gaussian: -0.5 * ||x - x_recon||^2 / sigma^2
                # Assuming unit variance for simplicity
                log_pxz = -0.5 * torch.sum((x - x_recon) ** 2, dim=1)
                log_probs.append(log_pxz)

        # Average over samples
        avg_log_prob = torch.stack(log_probs).mean(dim=0)

        return avg_log_prob

    def fit_kde(self, X_train: torch.Tensor, percentile: float = 95.0):
        """Fit KDE model on training data for threshold estimation.

        Args:
            X_train: Training data tensor (n_samples, input_dim)
            percentile: Threshold percentile (default: 95th)
        """
        # Compute reconstruction scores for training data
        scores = []
        batch_size = 64

        with torch.no_grad():
            for i in range(0, len(X_train), batch_size):
                batch = X_train[i : i + batch_size].to(self.device)
                log_probs = self.compute_reconstruction_probability(batch)
                scores.extend(-log_probs.cpu().numpy())  # Negative log prob as score

        scores = np.array(scores)

        # Fit KDE on scores
        if len(scores) > 1:
            self.kde_model = gaussian_kde(scores.reshape(1, -1))

        # Set threshold at given percentile
        self.threshold = np.percentile(scores, percentile)

    def detect(
        self, X: torch.Tensor, mask: torch.Tensor | None = None
    ) -> Tuple[np.ndarray, np.ndarray]:
        """Detect anomalies in input data.

        Args:
            X: Input tensor (n_samples, input_dim)
            mask: Optional mask for missing values

        Returns:
            Tuple of (scores, predictions)
            where scores are anomaly scores (higher = more anomalous)
            and predictions are binary (1=anomaly, 0=normal)
        """
        scores = []
        batch_size = 64

        with torch.no_grad():
            for i in range(0, len(X), batch_size):
                batch = X[i : i + batch_size].to(self.device)
                log_probs = self.compute_reconstruction_probability(batch, mask)
                batch_scores = -log_probs.cpu().numpy()  # Negative log prob
                scores.extend(batch_scores)

        scores = np.array(scores)

        # Apply threshold
        if self.threshold is not None:
            predictions = (scores > self.threshold).astype(int)
        else:
            # If no threshold set, use median as default
            predictions = (scores > np.median(scores)).astype(int)

        return scores, predictions

    def get_anomaly_windows(
        self, X: torch.Tensor, window_size: int = 120
    ) -> List[dict]:
        """Get anomalous time windows with details.

        Args:
            X: Input tensor (n_samples, input_dim)
            window_size: Size of sliding window

        Returns:
            List of dictionaries with anomaly details
        """
        scores, predictions = self.detect(X)

        anomalies = []
        for i, (score, pred) in enumerate(zip(scores, predictions)):
            if pred == 1:
                anomalies.append({
                    "window_idx": i,
                    "anomaly_score": float(score),
                    "is_anomaly": True,
                })

        return anomalies
