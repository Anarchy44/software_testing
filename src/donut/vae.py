"""Donut VAE model implementation.

Implements the Variational Auto-Encoder architecture from the Donut paper:
- Encoder: MLP with ReLU activation
- Decoder: MLP with ReLU activation
- Latent space: Gaussian distribution with reparameterization trick
"""

import torch
import torch.nn as nn
import torch.nn.functional as F


class DonutVAE(nn.Module):
    """Variational Auto-Encoder for KPI anomaly detection.

    Architecture follows Donut paper (WWW 2018):
    - Encoder: input -> h_enc1 -> h_enc2 -> [mu, logvar]
    - Decoder: z -> h_dec1 -> h_dec2 -> reconstruction

    Args:
        input_dim: Window size of KPI time series (default: 120)
        hidden_dim: Hidden layer dimension (default: 500)
        latent_dim: Latent space dimension (default: 5)
        dropout: Dropout rate for regularization (default: 0.1)
    """

    def __init__(
        self,
        input_dim: int = 120,
        hidden_dim: int = 500,
        latent_dim: int = 5,
        dropout: float = 0.1,
    ):
        super().__init__()

        self.input_dim = input_dim
        self.hidden_dim = hidden_dim
        self.latent_dim = latent_dim

        # Encoder network
        self.encoder = nn.Sequential(
            nn.Linear(input_dim, hidden_dim),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(hidden_dim, hidden_dim),
            nn.ReLU(),
            nn.Dropout(dropout),
        )

        # Latent space parameters
        self.fc_mu = nn.Linear(hidden_dim, latent_dim)
        self.fc_logvar = nn.Linear(hidden_dim, latent_dim)

        # Decoder network
        self.decoder = nn.Sequential(
            nn.Linear(latent_dim, hidden_dim),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(hidden_dim, hidden_dim),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(hidden_dim, input_dim),
        )

        # Weight initialization (Xavier uniform)
        self._init_weights()

    def _init_weights(self):
        """Initialize weights using Xavier uniform initialization."""
        for module in self.modules():
            if isinstance(module, nn.Linear):
                nn.init.xavier_uniform_(module.weight)
                if module.bias is not None:
                    nn.init.zeros_(module.bias)

    def encode(self, x: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        """Encode input to latent space parameters.

        Args:
            x: Input tensor of shape (batch_size, input_dim)

        Returns:
            Tuple of (mu, logvar) tensors, each of shape (batch_size, latent_dim)
        """
        h = self.encoder(x)
        mu = self.fc_mu(h)
        logvar = self.fc_logvar(h)
        # Clamp logvar for numerical stability
        logvar = torch.clamp(logvar, min=-10, max=10)
        return mu, logvar

    def reparameterize(
        self, mu: torch.Tensor, logvar: torch.Tensor
    ) -> torch.Tensor:
        """Reparameterization trick for sampling from latent space.

        Args:
            mu: Mean of latent distribution
            logvar: Log variance of latent distribution

        Returns:
            Sampled latent vector z
        """
        std = torch.exp(0.5 * logvar)
        eps = torch.randn_like(std)
        z = mu + eps * std
        return z

    def decode(self, z: torch.Tensor) -> torch.Tensor:
        """Decode latent vector to reconstruction.

        Args:
            z: Latent vector of shape (batch_size, latent_dim)

        Returns:
            Reconstructed input of shape (batch_size, input_dim)
        """
        return self.decoder(z)

    def forward(
        self, x: torch.Tensor
    ) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        """Forward pass through VAE.

        Args:
            x: Input tensor of shape (batch_size, input_dim)

        Returns:
            Tuple of (reconstruction, mu, logvar)
        """
        mu, logvar = self.encode(x)
        z = self.reparameterize(mu, logvar)
        x_recon = self.decode(z)
        return x_recon, mu, logvar

    def sample(
        self, n_samples: int, device: str = "cpu"
    ) -> torch.Tensor:
        """Sample from the learned latent distribution.

        Args:
            n_samples: Number of samples to generate
            device: Device to place samples on

        Returns:
            Generated samples of shape (n_samples, input_dim)
        """
        z = torch.randn(n_samples, self.latent_dim, device=device)
        return self.decode(z)
