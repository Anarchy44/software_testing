"""Donut trainer with M-ELBO loss and missing data injection.

Implements the training pipeline from Donut paper:
- Batch training with Adam optimizer
- Missing data injection for augmentation
- M-ELBO loss computation
- Learning rate scheduling
- Early stopping
"""

import torch
from torch.utils.data import DataLoader, TensorDataset
from tqdm import tqdm

from .vae import DonutVAE
from .melbo import melbo_loss, MissingDataInjector


class DonutTrainer:
    """Training manager for Donut VAE model.

    Args:
        model: DonutVAE instance
        lr: Learning rate (default: 1e-3)
        weight_decay: L2 regularization (default: 1e-5)
        missing_rate: Rate of missing data injection (default: 0.1)
        beta: KL divergence weight in M-ELBO (default: 1.0)
        device: Training device ('cpu' or 'cuda')
    """

    def __init__(
        self,
        model: DonutVAE,
        lr: float = 1e-3,
        weight_decay: float = 1e-5,
        missing_rate: float = 0.1,
        beta: float = 1.0,
        device: str = "auto",
    ):
        self.model = model

        # Auto-detect device
        if device == "auto":
            self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        else:
            self.device = torch.device(device)

        self.model.to(self.device)

        # Optimizer
        self.optimizer = torch.optim.Adam(
            model.parameters(), lr=lr, weight_decay=weight_decay
        )

        # M-ELBO parameters
        self.beta = beta
        self.missing_injector = MissingDataInjector(missing_rate=missing_rate)

        # Training history
        self.history = {
            "epoch": [],
            "train_loss": [],
            "recon_loss": [],
            "kl_loss": [],
        }

    def train_epoch(self, dataloader: DataLoader) -> dict[str, float]:
        """Train for one epoch.

        Args:
            dataloader: DataLoader containing training batches

        Returns:
            Dictionary of average losses for this epoch
        """
        self.model.train()
        total_losses = []
        recon_losses = []
        kl_losses = []

        for batch in tqdm(dataloader, desc="Training", leave=False):
            # DataLoader returns list of tensors from TensorDataset
            batch_x = batch[0] if isinstance(batch, (list, tuple)) else batch
            batch_x = batch_x.to(self.device)

            # Inject missing data
            x_missing, mask = self.missing_injector.inject(batch_x)

            # Forward pass
            x_recon, mu, logvar = self.model(x_missing)

            # Compute M-ELBO loss
            loss, metrics = melbo_loss(
                x=batch_x,
                x_recon=x_recon,
                mu=mu,
                logvar=logvar,
                mask=mask,
                beta=self.beta,
            )

            # Backward pass with gradient clipping
            self.optimizer.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(self.model.parameters(), max_norm=1.0)
            self.optimizer.step()

            total_losses.append(metrics["total_loss"])
            recon_losses.append(metrics["recon_loss"])
            kl_losses.append(metrics["kl_loss"])

        n = len(total_losses) or 1
        return {
            "train_loss": sum(total_losses) / n,
            "recon_loss": sum(recon_losses) / n,
            "kl_loss": sum(kl_losses) / n,
        }

    def validate(self, dataloader: DataLoader) -> dict[str, float]:
        """Validate model on validation set.

        Args:
            dataloader: DataLoader containing validation batches

        Returns:
            Dictionary of average validation losses
        """
        self.model.eval()
        total_losses = []
        recon_losses = []
        kl_losses = []

        with torch.no_grad():
            for batch in dataloader:
                # DataLoader returns list of tensors from TensorDataset
                batch_x = batch[0] if isinstance(batch, (list, tuple)) else batch
                batch_x = batch_x.to(self.device)

                # Forward pass (no missing injection during validation)
                x_recon, mu, logvar = self.model(batch_x)

                # Compute standard ELBO loss
                loss, metrics = melbo_loss(
                    x=batch_x,
                    x_recon=x_recon,
                    mu=mu,
                    logvar=logvar,
                    mask=None,
                    beta=self.beta,
                )

                total_losses.append(metrics["total_loss"])
                recon_losses.append(metrics["recon_loss"])
                kl_losses.append(metrics["kl_loss"])

        return {
            "val_loss": sum(total_losses) / len(total_losses),
            "val_recon_loss": sum(recon_losses) / len(recon_losses),
            "val_kl_loss": sum(kl_losses) / len(kl_losses),
        }

    def fit(
        self,
        X_train: torch.Tensor,
        X_val: torch.Tensor | None = None,
        batch_size: int = 64,
        epochs: int = 100,
        patience: int = 10,
        verbose: bool = True,
    ) -> dict:
        """Train the model.

        Args:
            X_train: Training data tensor (n_samples, input_dim)
            X_val: Optional validation data tensor
            batch_size: Mini-batch size
            epochs: Maximum number of epochs
            patience: Early stopping patience
            verbose: Whether to print progress

        Returns:
            Training history dictionary
        """
        # Create data loaders
        train_dataset = TensorDataset(X_train)
        # Only drop_last when we have enough samples; otherwise we get 0 batches
        drop = len(X_train) > batch_size
        train_loader = DataLoader(
            train_dataset, batch_size=min(batch_size, len(X_train)),
            shuffle=True, drop_last=drop,
        )

        if X_val is not None:
            val_dataset = TensorDataset(X_val)
            val_loader = DataLoader(val_dataset, batch_size=batch_size, shuffle=False)
        else:
            val_loader = None

        best_val_loss = float("inf")
        patience_counter = 0

        if verbose:
            print(f"Training Donut VAE on {self.device}")
            print(f"Training samples: {len(X_train)}, Epochs: {epochs}")

        for epoch in range(epochs):
            # Train one epoch
            train_metrics = self.train_epoch(train_loader)

            # Validate
            if val_loader is not None:
                val_metrics = self.validate(val_loader)
                current_val_loss = val_metrics["val_loss"]
            else:
                val_metrics = {}
                current_val_loss = train_metrics["train_loss"]

            # Update history
            self.history["epoch"].append(epoch + 1)
            self.history["train_loss"].append(train_metrics["train_loss"])
            self.history["recon_loss"].append(train_metrics["recon_loss"])
            self.history["kl_loss"].append(train_metrics["kl_loss"])

            if verbose and (epoch + 1) % 10 == 0:
                msg = f"Epoch {epoch+1}/{epochs} - Loss: {train_metrics['train_loss']:.4f}"
                if val_loader is not None:
                    msg += f" - Val Loss: {val_metrics['val_loss']:.4f}"
                print(msg)

            # Early stopping check
            if current_val_loss < best_val_loss:
                best_val_loss = current_val_loss
                patience_counter = 0
                # Save best model
                self.best_state_dict = self.model.state_dict().copy()
            else:
                patience_counter += 1
                if patience_counter >= patience:
                    if verbose:
                        print(f"Early stopping at epoch {epoch+1}")
                    break

        # Restore best model
        if hasattr(self, "best_state_dict"):
            self.model.load_state_dict(self.best_state_dict)

        return self.history
