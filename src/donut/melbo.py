"""M-ELBO (Modified Evidence Lower Bound) loss function.

Implements the modified ELBO from Donut paper that handles missing data:
- Masks anomalous points during training
- Uses alpha weights to control contribution of each point
- Supports missing data injection for data augmentation
"""

import torch
import torch.nn as nn


def melbo_loss(
    x: torch.Tensor,
    x_recon: torch.Tensor,
    mu: torch.Tensor,
    logvar: torch.Tensor,
    mask: torch.Tensor | None = None,
    beta: float = 1.0,
) -> tuple[torch.Tensor, dict[str, float]]:
    """Compute Modified Evidence Lower Bound loss.

    The M-ELBO extends standard VAE ELBO by:
    1. Applying mask to exclude anomalous/missing points from reconstruction loss
    2. Using weighted KL divergence term
    3. Supporting missing data injection

    Args:
        x: Original input tensor (batch_size, input_dim)
        x_recon: Reconstructed input tensor (batch_size, input_dim)
        mu: Latent mean (batch_size, latent_dim)
        logvar: Latent log variance (batch_size, latent_dim)
        mask: Binary mask indicating valid points (1=valid, 0=missing/anomaly).
              If None, all points are treated as valid.
        beta: Weight for KL divergence term (default: 1.0)

    Returns:
        Tuple of (total_loss, metrics_dict)
        where metrics_dict contains:
            - recon_loss: Reconstruction loss value
            - kl_loss: KL divergence loss value
            - total_loss: Combined loss
    """
    batch_size = x.size(0)

    # Apply mask if provided
    if mask is not None:
        # Only compute reconstruction loss on valid points
        recon_diff = (x - x_recon) ** 2 * mask
        n_valid = mask.sum(dim=1).clamp(min=1.0)  # Avoid division by zero
        recon_loss = (recon_diff.sum(dim=1) / n_valid).mean()
    else:
        # Standard MSE reconstruction loss
        recon_loss = F.mse_loss(x_recon, x, reduction="mean")

    # KL divergence with numerical stability: -0.5 * sum(1 + log(sigma^2) - mu^2 - sigma^2)
    # Clamp logvar to prevent overflow
    logvar_clamped = torch.clamp(logvar, min=-10, max=10)
    kl_loss = -0.5 * torch.mean(torch.sum(1 + logvar_clamped - mu.pow(2) - logvar_clamped.exp(), dim=1))

    # Total loss
    total_loss = recon_loss + beta * kl_loss

    metrics = {
        "recon_loss": recon_loss.item(),
        "kl_loss": kl_loss.item(),
        "total_loss": total_loss.item(),
    }

    return total_loss, metrics


class MissingDataInjector:
    """Inject missing values during training for data augmentation.

    Following Donut paper Section 3.2: randomly set normal points to 0
    to simulate missing data and enhance M-ELBO effectiveness.
    """

    def __init__(self, missing_rate: float = 0.1, seed: int | None = None):
        """Initialize missing data injector.

        Args:
            missing_rate: Probability of setting a point to missing (0.0-1.0)
            seed: Random seed for reproducibility
        """
        self.missing_rate = missing_rate
        self.rng = torch.Generator()
        if seed is not None:
            self.rng.manual_seed(seed)

    def inject(self, x: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        """Inject missing values into input tensor.

        Args:
            x: Input tensor (batch_size, input_dim)

        Returns:
            Tuple of (x_with_missing, mask)
            where mask indicates which points are valid (1) vs missing (0)
        """
        # Generate random mask (PyTorch 1.x compatible)
        try:
            mask = torch.rand_like(x, generator=self.rng) > self.missing_rate
        except TypeError:
            # Fallback for older PyTorch versions
            mask = torch.rand_like(x) > self.missing_rate
        
        mask = mask.float()

        # Set missing points to 0
        x_missing = x * mask

        return x_missing, mask
