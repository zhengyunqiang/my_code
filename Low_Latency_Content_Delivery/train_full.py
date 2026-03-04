# train_full.py
"""
Complete training script with all improvements:
  - Model checkpointing
  - TensorBoard logging
  - Learning rate scheduling
  - Early stopping
  - Realistic channel models
  - Training stability features

Usage:
    python train_full.py --config config.yaml
    python train_full.py --epochs 1000 --lr 3e-4
"""
from __future__ import annotations

import argparse
import signal
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import torch
import torch.nn as nn
import numpy as np

from trainers.mixed_ppo_trainer import MixedPPOConfig, MixedPPOTrainer
from models.gat import SharedGATNetwork
from models.actor import TelecomHybridActor, SBSActor
from models.critic import SharedCriticLocal
from environments import TelecomEnvConfig, create_telecom_env
from utils import (
    CheckpointManager,
    TrainingLogger,
    TrainMetrics,
    LearningRateScheduler,
    EarlyStopping,
    RollingStatistics,
)


@dataclass
class TrainConfig:
    """Complete training configuration."""

    # Environment
    E: int = 8              # parallel envs
    T: int = 40             # episode length
    num_bases: int = 2
    num_cars: int = 2
    num_subchannels: int = 5
    num_fap: int = 10

    # Network
    D_obs: int = 32
    D_h: int = 64

    # Training
    num_iterations: int = 1000
    save_freq: int = 50
    log_freq: int = 10
    eval_freq: int = 100

    # PPO
    P_max: float = 100
    B_max: float = 10
    scale: float = 100
    gamma: float = 0.99
    lam: float = 0.95
    clip_eps: float = 0.2
    vf_coef: float = 0.5
    ent_coef: float = 0.01
    epochs: int = 4
    minibatch_size: int = 256
    max_grad_norm: float = 1.0
    evaluator_coef: float = 0.1
    use_slot_evaluator: bool = True

    # Optimizer
    lr: float = 3e-4
    weight_decay: float = 1e-5

    # Learning rate schedule
    warmup_steps: int = 500
    max_steps: int = 100000
    final_lr: float = 3e-5

    # Early stopping
    patience: int = 50
    min_delta: float = 1e-3

    # Checkpointing
    max_checkpoints: int = 5
    checkpoint_dir: str = "checkpoints"
    log_dir: str = "logs"
    experiment_name: str = "telecom_marl"

    # Channel model
    realistic_channel: bool = True
    fc: float = 2.1       # GHz
    speed_kmh: float = 300
    fading_model: str = "rician"

    # Device
    device: str = "cuda" if torch.cuda.is_available() else "cpu"

    # Resume
    resume_from: Optional[str] = None


class GracefulExit:
    """Handle graceful exit on interrupt."""

    def __init__(self):
        self.shutdown = False
        signal.signal(signal.SIGINT, self.exit_gracefully)
        signal.signal(signal.SIGTERM, self.exit_gracefully)

    def exit_gracefully(self, signum, frame):
        print(f"\nSignal {signum} received. Shutting down gracefully...")
        self.shutdown = True


class Trainer:
    """Complete trainer with all features."""

    def __init__(self, cfg: TrainConfig):
        self.cfg = cfg
        self.device = torch.device(cfg.device)

        # Create directories
        self.checkpoint_dir = Path(cfg.checkpoint_dir) / cfg.experiment_name
        self.log_dir = Path(cfg.log_dir) / cfg.experiment_name

        # Initialize components
        self._init_env()
        self._init_models()
        self._init_optimizers()
        self._init_schedulers()
        self._init_helpers()

        # Training state
        self.iteration = 0
        self.best_s_final = float("inf")

    def _init_env(self):
        """Initialize environment."""
        env_cfg = TelecomEnvConfig(
            E=self.cfg.E,
            T=self.cfg.T,
            num_bases=self.cfg.num_bases,
            num_cars=self.cfg.num_cars,
            users_per_car=10,
            num_subchannels=self.cfg.num_subchannels,
            num_fap=self.cfg.num_fap,
            D_obs=self.cfg.D_obs,
            max_power=self.cfg.P_max,
            max_bandwidth=self.cfg.B_max,
            use_realistic_channel=self.cfg.realistic_channel,
            channel_fc=self.cfg.fc,
            channel_speed_kmh=self.cfg.speed_kmh,
            channel_fading_model=self.cfg.fading_model,
        )
        self.env = create_telecom_env(env_cfg, self.device)
        self.env_cfg = env_cfg

    def _init_models(self):
        """Initialize neural networks."""
        N, M, K = self.cfg.num_bases, self.cfg.num_subchannels, self.cfg.num_fap
        D_obs, D_h = self.cfg.D_obs, self.cfg.D_h

        # GAT (shared encoder)
        self.gat = SharedGATNetwork(
            d_obs=D_obs,
            d_h=D_h,
            num_layers=2,
            num_heads=4,
            dropout_attn=0.0,
        ).to(self.device)

        # Critic (shared value head)
        self.critic = SharedCriticLocal(
            d_h=D_h,
            hidden_layers=(256, 256),
            activation="relu",
        ).to(self.device)

        # Standard actors (BaseStations)
        self.std_actors = nn.ModuleList([
            TelecomHybridActor(
                input_dim=D_h,
                num_subchannels=M,
                num_femtoCell=self.cfg.num_cars,
                max_power=self.cfg.P_max,
                trunk_layers=(256, 256),
            ).to(self.device)
            for _ in range(N)
        ])

        # SBS actor
        self.sbs_actor = SBSActor(
            input_dim=D_h,
            num_fap=K,
            max_bandwidth=self.cfg.B_max,
            trunk_layers=(256, 256),
        ).to(self.device)

    def _init_optimizers(self):
        """Initialize optimizers."""
        self.opt_gat = torch.optim.Adam(
            self.gat.parameters(),
            lr=self.cfg.lr,
            weight_decay=self.cfg.weight_decay,
        )
        self.opt_critic = torch.optim.Adam(
            self.critic.parameters(),
            lr=self.cfg.lr,
            weight_decay=self.cfg.weight_decay,
        )
        self.opt_std_actors = torch.optim.Adam(
            self.std_actors.parameters(),
            lr=self.cfg.lr,
            weight_decay=self.cfg.weight_decay,
        )
        self.opt_sbs_actor = torch.optim.Adam(
            self.sbs_actor.parameters(),
            lr=self.cfg.lr,
            weight_decay=self.cfg.weight_decay,
        )

    def _init_schedulers(self):
        """Initialize learning rate schedulers."""
        # One scheduler per optimizer
        self.lr_schedulers = [
            LearningRateScheduler(
                opt,
                warmup_steps=self.cfg.warmup_steps,
                max_steps=self.cfg.max_steps,
                peak_lr=self.cfg.lr,
                final_lr=self.cfg.final_lr,
            )
            for opt in [self.opt_gat, self.opt_critic, self.opt_std_actors, self.opt_sbs_actor]
        ]

    def _init_helpers(self):
        """Initialize training helpers."""
        self.checkpoint_manager = CheckpointManager(
            save_dir=self.checkpoint_dir,
            max_keep=self.cfg.max_checkpoints,
            save_freq=self.cfg.save_freq,
        )
        self.logger = TrainingLogger(
            log_dir=self.log_dir,
            experiment_name=self.cfg.experiment_name,
            use_tensorboard=True,
        )
        self.early_stopping = EarlyStopping(
            patience=self.cfg.patience,
            min_delta=self.cfg.min_delta,
            mode="min",
        )
        self.rolling_stats = RollingStatistics(window=100)

    def train(self):
        """Main training loop."""
        exit_handler = GracefulExit()

        # Setup PPO trainer
        ppo_cfg = MixedPPOConfig(
            T=self.cfg.T,
            E=self.cfg.E,
            N=self.cfg.num_bases,
            M=self.cfg.num_subchannels,
            K=self.cfg.num_fap,
            D_obs=self.cfg.D_obs,
            P_max=self.cfg.P_max,
            B_max=self.cfg.B_max,
            scale=self.cfg.scale,
            gamma=self.cfg.gamma,
            lam=self.cfg.lam,
            clip_eps=self.cfg.clip_eps,
            vf_coef=self.cfg.vf_coef,
            ent_coef=self.cfg.ent_coef,
            epochs=self.cfg.epochs,
            minibatch_size=self.cfg.minibatch_size,
            max_grad_norm=self.cfg.max_grad_norm,
            use_slot_evaluator=self.cfg.use_slot_evaluator,
            evaluator_coef=self.cfg.evaluator_coef,
        )
        trainer = MixedPPOTrainer(
            cfg=ppo_cfg,
            gat=self.gat,
            critic=self.critic,
            std_actors=self.std_actors,
            sbs_actor=self.sbs_actor,
            opt_gat=self.opt_gat,
            opt_critic=self.opt_critic,
            opt_std_actors=self.opt_std_actors,
            opt_sbs_actor=self.opt_sbs_actor,
            device=self.device,
        )

        # Resume from checkpoint if specified
        if self.cfg.resume_from:
            self._resume(self.cfg.resume_from)

        # Print header
        self._print_header()

        # Training loop
        for self.iteration in range(self.iteration + 1, self.cfg.num_iterations + 1):
            if exit_handler.shutdown:
                print("\nGraceful shutdown requested. Saving checkpoint...")
                self._save_checkpoint(is_best=False)
                break

            # Update learning rates
            current_lr = self.lr_schedulers[0].step()

            # Collect episode
            episode_start = time.time()
            buf = trainer.collect_episode(self.env)
            episode_time = time.time() - episode_start

            # Get S_final from buffer
            # (Extract from last step's info - for simplicity, compute here)
            S_final = self._compute_terminal_score()

            # PPO update
            logs = trainer.update(buf)

            # Update statistics
            stats = self.rolling_stats.update(S_final.mean().item())

            # Logging
            if self.iteration % self.cfg.log_freq == 0:
                metrics = TrainMetrics(
                    iteration=self.iteration,
                    loss_total=logs["loss_total"],
                    loss_actor=logs["loss_actor"],
                    loss_critic=logs["loss_critic"] + logs.get("loss_evaluator", 0.0),
                    entropy=logs["entropy"],
                    s_final_mean=S_final.mean().item(),
                    s_final_min=S_final.min().item(),
                    data_transmitted=0,  # TODO: compute from buffer
                    episode_time=episode_time,
                )
                self.logger.log(metrics)

            # Checkpointing
            if self.iteration % self.cfg.save_freq == 0:
                is_best = S_final.mean().item() < self.best_s_final
                if is_best:
                    self.best_s_final = S_final.mean().item()
                self._save_checkpoint(is_best)

            # Early stopping check
            if self.early_stopping.check(S_final.mean().item()):
                print(f"\nEarly stopping triggered at iteration {self.iteration}")
                break

        # Final save
        self._save_checkpoint(is_best=True)
        self.logger.close()

    def _compute_terminal_score(self) -> torch.Tensor:
        """Compute terminal score from environment state."""
        # Simplified: use remaining data
        if hasattr(self.env, 'remaining_data'):
            return self.env.remaining_data.sum(dim=1)
        return torch.zeros(self.cfg.E, device=self.device)

    def _save_checkpoint(self, is_best: bool = False):
        """Save training checkpoint."""
        models = {
            "gat": self.gat,
            "critic": self.critic,
            "std_actors": self.std_actors,
            "sbs_actor": self.sbs_actor,
        }
        optimizers = {
            "gat": self.opt_gat,
            "critic": self.opt_critic,
            "std_actors": self.opt_std_actors,
            "sbs_actor": self.opt_sbs_actor,
        }
        metrics = {
            "iteration": self.iteration,
            "best_s_final": self.best_s_final,
            "lr": self.lr_schedulers[0]._get_lr(),
        }

        path = self.checkpoint_manager.save(self.iteration, models, optimizers, metrics, is_best)
        if is_best or self.iteration % self.cfg.save_freq == 0:
            print(f"  Checkpoint saved: {path}")

    def _resume(self, ckpt_path: str):
        """Resume from checkpoint."""
        print(f"Resuming from {ckpt_path}")
        ckpt = self.checkpoint_manager.load(Path(ckpt_path))

        # Load model states
        self.gat.load_state_dict(ckpt["model_states"]["gat"])
        self.critic.load_state_dict(ckpt["model_states"]["critic"])
        if "std_actors" in ckpt["model_states"]:
            self.std_actors.load_state_dict(ckpt["model_states"]["std_actors"])
        self.sbs_actor.load_state_dict(ckpt["model_states"]["sbs_actor"])

        # Load optimizer states
        self.opt_gat.load_state_dict(ckpt["optimizer_states"]["gat"])
        self.opt_critic.load_state_dict(ckpt["optimizer_states"]["critic"])
        self.opt_std_actors.load_state_dict(ckpt["optimizer_states"]["std_actors"])
        self.opt_sbs_actor.load_state_dict(ckpt["optimizer_states"]["sbs_actor"])

        # Restore state
        self.iteration = ckpt["iteration"]
        self.best_s_final = ckpt["metrics"].get("best_s_final", float("inf"))

        print(f"  Resumed from iteration {self.iteration}")

    def _print_header(self):
        """Print training header."""
        print("\n" + "=" * 80)
        print(f"{'TELECOM MULTI-AGENT RL TRAINING':^80}")
        print("=" * 80)
        print(f"\nConfiguration:")
        print(f"  Agents: {self.cfg.num_bases} BS + 1 SBS")
        print(f"  Subchannels: {self.cfg.num_subchannels}")
        print(f"  FAPs: {self.cfg.num_fap}")
        print(f"  Parallel envs: {self.cfg.E}")
        print(f"  Episode length: {self.cfg.T}")
        print(f"  Max iterations: {self.cfg.num_iterations}")
        print(f"  Learning rate: {self.cfg.lr}")
        print(f"  Realistic channel: {self.cfg.realistic_channel}")
        print(f"\nDirectories:")
        print(f"  Checkpoints: {self.checkpoint_dir}")
        print(f"  Logs: {self.log_dir}")
        print("\n" + "=" * 80 + "\n")


import time


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Train multi-agent telecom RL")

    # Training settings
    parser.add_argument("--iterations", type=int, default=1000, help="Number of iterations")
    parser.add_argument("--lr", type=float, default=3e-4, help="Learning rate")
    parser.add_argument("--batch-size", type=int, default=256, help="Minibatch size")
    parser.add_argument("--epochs", type=int, default=4, help="PPO epochs per update")

    # Environment
    parser.add_argument("--num-bases", type=int, default=2, help="Number of base stations")
    parser.add_argument("--num-cars", type=int, default=2, help="Number of carriages")
    parser.add_argument("--subchannels", type=int, default=5, help="Subchannels per BS")
    parser.add_argument("--num-fap", type=int, default=10, help="Number of FAPs")

    # Logging
    parser.add_argument("--log-dir", type=str, default="logs", help="Log directory")
    parser.add_argument("--exp-name", type=str, default="train", help="Experiment name")
    parser.add_argument("--save-freq", type=int, default=50, help="Checkpoint save frequency")

    # Resume
    parser.add_argument("--resume", type=str, default=None, help="Resume from checkpoint")

    args = parser.parse_args()
    return args


def main():
    args = parse_args()

    # Create config
    cfg = TrainConfig(
        num_iterations=args.iterations,
        lr=args.lr,
        minibatch_size=args.batch_size,
        epochs=args.epochs,
        num_bases=args.num_bases,
        num_cars=args.num_cars,
        num_subchannels=args.subchannels,
        num_fap=args.num_fap,
        log_dir=args.log_dir,
        experiment_name=args.exp_name,
        save_freq=args.save_freq,
        resume_from=args.resume,
    )

    # Create trainer
    trainer = Trainer(cfg)

    # Train
    trainer.train()


if __name__ == "__main__":
    main()
