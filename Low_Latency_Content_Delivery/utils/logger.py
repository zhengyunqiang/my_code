# utils/logger.py
"""
Training utilities: checkpoint management, logging, and training stability.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import torch
import torch.nn as nn
import numpy as np


@dataclass
class TrainMetrics:
    """Training metrics for logging."""
    iteration: int
    loss_total: float
    loss_actor: float
    loss_critic: float
    entropy: float
    s_final_mean: float
    s_final_min: float
    data_transmitted: float
    episode_time: float


class CheckpointManager:
    """Manage model checkpoints with automatic cleanup."""

    def __init__(
        self,
        save_dir: str | Path,
        max_keep: int = 5,
        save_freq: int = 10,
    ) -> None:
        self.save_dir = Path(save_dir)
        self.save_dir.mkdir(parents=True, exist_ok=True)
        self.max_keep = max_keep
        self.save_freq = save_freq
        self.history: List[Path] = []

    def save(
        self,
        iteration: int,
        models: Dict[str, nn.Module],
        optimizers: Dict[str, torch.optim.Optimizer],
        metrics: Dict[str, float],
        is_best: bool = False,
    ) -> Path:
        """Save checkpoint."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        ckpt_name = f"ckpt_iter{iteration}_{timestamp}.pt"
        ckpt_path = self.save_dir / ckpt_name

        # Prepare checkpoint data
        ckpt_data = {
            "iteration": iteration,
            "timestamp": timestamp,
            "metrics": metrics,
            "model_states": {name: model.state_dict() for name, model in models.items()},
            "optimizer_states": {name: opt.state_dict() for name, opt in optimizers.items()},
        }

        # Save
        torch.save(ckpt_data, ckpt_path)
        self.history.append(ckpt_path)

        # Save best separately
        if is_best:
            best_path = self.save_dir / "best_model.pt"
            torch.save(ckpt_data, best_path)

        # Cleanup old checkpoints
        self._cleanup()

        return ckpt_path

    def load(self, ckpt_path: Optional[Path] = None) -> Dict:
        """Load checkpoint. If None, load the most recent."""
        if ckpt_path is None:
            if not self.history:
                # Try to find checkpoints in directory
                ckpts = list(self.save_dir.glob("ckpt_*.pt"))
                if not ckpts:
                    raise FileNotFoundError(f"No checkpoints found in {self.save_dir}")
                ckpt_path = max(ckpts, key=os.path.getctime)
            else:
                ckpt_path = self.history[-1]

        # PyTorch>=2.6 defaults to weights_only=True; explicit False keeps
        # backward compatibility for checkpoints that include metadata objects.
        ckpt_data = torch.load(ckpt_path, map_location="cpu", weights_only=False)
        return ckpt_data

    def _cleanup(self) -> None:
        """Remove old checkpoints beyond max_keep."""
        while len(self.history) > self.max_keep:
            oldest = self.history.pop(0)
            if oldest.exists():
                oldest.unlink()


class TrainingLogger:
    """Training logger with console and file output."""

    def __init__(
        self,
        log_dir: str | Path,
        experiment_name: str = "train",
        use_tensorboard: bool = True,
    ) -> None:
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.experiment_name = experiment_name
        self.use_tensorboard = use_tensorboard

        # File logger
        self.log_file = self.log_dir / f"{experiment_name}.log"
        self.metrics_file = self.log_dir / f"{experiment_name}_metrics.jsonl"

        # TensorBoard writer
        self.writer = None
        if use_tensorboard:
            try:
                from torch.utils.tensorboard import SummaryWriter
                self.writer = SummaryWriter(log_dir / str(experiment_name))
            except ImportError:
                print("TensorBoard not available. Install with: pip install tensorboard")

        # Metrics history
        self.metrics_history: List[TrainMetrics] = []
        self.best_s_final = float("inf")

        # Training start time
        self.start_time = time.time()

    def log(self, metrics: TrainMetrics) -> None:
        """Log metrics."""
        self.metrics_history.append(metrics)

        # Update best
        if metrics.s_final_mean < self.best_s_final:
            self.best_s_final = metrics.s_final_mean

        # Console log
        elapsed = time.time() - self.start_time
        print(
            f"[Iter {metrics.iteration:04d}] "
            f"Loss={metrics.loss_total:.4f} "
            f"Actor={metrics.loss_actor:.4f} "
            f"Critic={metrics.loss_critic:.4f} "
            f"Ent={metrics.entropy:.4f} "
            f"S_final={metrics.s_final_mean:.4f} "
            f"Time={elapsed:.1f}s"
        )

        # File log
        with open(self.log_file, "a") as f:
            f.write(f"{json.dumps(asdict(metrics))}\n")

        # TensorBoard
        if self.writer is not None:
            for key, value in asdict(metrics).items():
                if isinstance(value, (int, float)):
                    self.writer.add_scalar(f"train/{key}", value, metrics.iteration)

    def log_episode(
        self,
        iteration: int,
        actions: Dict[str, torch.Tensor],
        remaining_data: torch.Tensor,
        data_rate: torch.Tensor,
    ) -> None:
        """Log detailed episode statistics."""
        if self.writer is not None:
            # Action distributions
            for key, value in actions.items():
                self.writer.add_histogram(f"actions/{key}", value.flatten(), iteration)

            # State distributions
            self.writer.add_histogram("state/remaining_data", remaining_data, iteration)
            self.writer.add_histogram("state/data_rate", data_rate, iteration)

    def close(self) -> None:
        """Close logger."""
        if self.writer is not None:
            self.writer.close()

        # Save metrics summary
        summary_file = self.log_dir / f"{self.experiment_name}_summary.json"
        with open(summary_file, "w") as f:
            json.dump({
                "best_s_final": self.best_s_final,
                "total_iterations": len(self.metrics_history),
                "total_time": time.time() - self.start_time,
                "metrics": [asdict(m) for m in self.metrics_history],
            }, f, indent=2)


class LearningRateScheduler:
    """Combined learning rate scheduler with warmup and decay."""

    def __init__(
        self,
        optimizer: torch.optim.Optimizer,
        warmup_steps: int = 1000,
        max_steps: int = 100000,
        peak_lr: float = 3e-4,
        final_lr: float = 3e-5,
        style: str = "cosine",
    ) -> None:
        self.optimizer = optimizer
        self.warmup_steps = warmup_steps
        self.max_steps = max_steps
        self.peak_lr = peak_lr
        self.final_lr = final_lr
        self.style = style
        self.current_step = 0

    def step(self) -> float:
        """Update learning rate and return current value."""
        self.current_step += 1
        lr = self._get_lr()

        for param_group in self.optimizer.param_groups:
            param_group["lr"] = lr

        return lr

    def _get_lr(self) -> float:
        """Calculate learning rate for current step."""
        if self.current_step < self.warmup_steps:
            # Warmup phase
            return self.peak_lr * (self.current_step / self.warmup_steps)
        else:
            # Decay phase
            progress = (self.current_step - self.warmup_steps) / (self.max_steps - self.warmup_steps)
            if self.style == "cosine":
                return self.final_lr + (self.peak_lr - self.final_lr) * 0.5 * (1 + np.cos(np.pi * progress))
            elif self.style == "linear":
                return self.peak_lr - (self.peak_lr - self.final_lr) * progress
            else:
                return self.peak_lr


class EarlyStopping:
    """Early stopping based on metric improvement."""

    def __init__(
        self,
        patience: int = 10,
        min_delta: float = 1e-4,
        mode: str = "min",  # 'min' or 'max'
    ) -> None:
        self.patience = patience
        self.min_delta = min_delta
        self.mode = mode
        self.counter = 0
        self.best_value = None
        self.early_stop = False

    def check(self, value: float) -> bool:
        """Check if should stop. Returns True if early stopping triggered."""
        if self.best_value is None:
            self.best_value = value
            return False

        if self.mode == "min":
            improved = value < self.best_value - self.min_delta
        else:
            improved = value > self.best_value + self.min_delta

        if improved:
            self.best_value = value
            self.counter = 0
        else:
            self.counter += 1

        if self.counter >= self.patience:
            self.early_stop = True

        return self.early_stop


class RollingStatistics:
    """Track rolling statistics for metrics."""

    def __init__(self, window: int = 100) -> None:
        self.window = window
        self.values: List[float] = []

    def update(self, value: float) -> Dict[str, float]:
        """Update with new value and return statistics."""
        self.values.append(value)
        if len(self.values) > self.window:
            self.values.pop(0)

        arr = np.array(self.values)
        return {
            "mean": float(arr.mean()),
            "std": float(arr.std()),
            "min": float(arr.min()),
            "max": float(arr.max()),
        }
