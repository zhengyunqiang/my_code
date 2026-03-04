# train_telecom_env.py
"""
Training script for heterogeneous multi-agent telecom system:
  - N BaseStation agents (TelecomHybridActor)
  - 1 SBS agent (SBSActor)

Environment:
  - E parallel environments
  - N base stations serving num_cars carriages
  - M subchannels per BS
  - K FAPs served by SBS

Usage:
    python train_telecom_env.py
"""
from __future__ import annotations

import torch
import torch.nn as nn

from trainers.mixed_ppo_trainer import MixedPPOConfig, MixedPPOTrainer
from models.gat import SharedGATNetwork
from models.actor import TelecomHybridActor, SBSActor
from models.critic import SharedCriticLocal
from environments import TelecomEnvConfig, create_telecom_env


def main() -> None:
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Using device: {device}")

    # ====== Environment Configuration ======
    env_cfg = TelecomEnvConfig(
        E=8,              # parallel envs
        T=40,             # episode length
        num_bases=2,      # N - base stations (standard agents)
        num_cars=2,       # carriages
        users_per_car=10, # users per carriage
        num_subchannels=5,    # M - subchannels per BS
        num_fap=10,           # K - FAPs for SBS
        coverage=250,
        speed=10,
        max_power=100,    # P_max
        max_bandwidth=10, # B_max
        B_TBS=10,
        delta_0=1e-9,
        K_gain=1,
        gamma=2,
        timeslot=0.01,
        max_rate=100,
        mean_demand=8,
        std_demand=3,
        D_obs=32,         # observation dimension
    )

    N = env_cfg.N
    M = env_cfg.M
    K = env_cfg.K
    E = env_cfg.E
    T = env_cfg.T
    D_obs = env_cfg.D_obs
    D_h = 64            # GAT embedding dim
    P_max = env_cfg.max_power
    B_max = env_cfg.max_bandwidth

    print(f"Environment Configuration:")
    print(f"  Base stations (N): {N}")
    print(f"  Carriages: {env_cfg.num_cars}")
    print(f"  Subchannels per BS (M): {M}")
    print(f"  FAPs for SBS (K): {K}")
    print(f"  Parallel envs (E): {E}")
    print(f"  Episode length (T): {T}")

    # ====== Build modules ======
    # GAT handles N_total = N + 1 agents
    gat = SharedGATNetwork(
        d_obs=D_obs,
        d_h=D_h,
        num_layers=2,
        num_heads=4,
        dropout_attn=0.0,
        use_edge_weight=False,
        use_residual=False,
        use_layernorm=False,
    ).to(device)

    # Critic handles all N_total agents
    critic = SharedCriticLocal(
        d_h=D_h,
        hidden_layers=(256, 256),
        activation="relu",
        use_layernorm=False,
    ).to(device)

    # Standard actors (N BaseStation agents)
    std_actors = []
    for i in range(N):
        std_actors.append(
            TelecomHybridActor(
                input_dim=D_h,
                num_subchannels=M,
                num_femtoCell=env_cfg.num_cars,  # select from carriages
                max_power=P_max,
                trunk_layers=(256, 256),
                activation="relu",
                dropout=0.0,
                min_std=1e-3,
                eps=1e-6,
                init_mode="xavier",
            ).to(device)
        )

    # SBS actor (1 agent)
    sbs_actor = SBSActor(
        input_dim=D_h,
        num_fap=K,
        max_bandwidth=B_max,
        trunk_layers=(256, 256),
        activation="relu",
        dropout=0.0,
        min_std=1e-3,
        eps=1e-6,
        init_mode="xavier",
    ).to(device)

    # ====== Optimizers ======
    opt_gat = torch.optim.Adam(gat.parameters(), lr=3e-4)
    opt_critic = torch.optim.Adam(critic.parameters(), lr=3e-4)
    opt_std_actors = torch.optim.Adam(nn.ModuleList(std_actors).parameters(), lr=3e-4)
    opt_sbs_actor = torch.optim.Adam(sbs_actor.parameters(), lr=3e-4)

    # ====== Trainer config ======
    cfg = MixedPPOConfig(
        T=T, E=E, N=N, M=M, K=K, D_obs=D_obs,
        P_max=P_max, B_max=B_max,
        scale=100.0,  # reward = -S_final / scale
        gamma=0.99,
        lam=0.95,
        clip_eps=0.2,
        vf_coef=0.5,
        ent_coef=0.01,
        epochs=4,
        minibatch_size=256,
        max_grad_norm=1.0,
        normalize_adv=True,
        eps_adv=1e-8,
    )

    trainer = MixedPPOTrainer(
        cfg=cfg,
        gat=gat,
        critic=critic,
        std_actors=std_actors,
        sbs_actor=sbs_actor,
        opt_gat=opt_gat,
        opt_critic=opt_critic,
        opt_std_actors=opt_std_actors,
        opt_sbs_actor=opt_sbs_actor,
        device=device,
    )

    # ====== Create environment ======
    env = create_telecom_env(env_cfg, device)

    # ====== Training loop ======
    print("\nStarting training...")
    print(f"{'Iter':<8} {'Loss':<10} {'Actor':<10} {'Critic':<10} {'Entropy':<10}")
    print("-" * 60)

    for it in range(1, 101):
        buf = trainer.collect_episode(env)
        logs = trainer.update(buf)

        if it % 5 == 0:
            print(
                f"{it:<8} "
                f"{logs['loss_total']:<10.4f} "
                f"{logs['loss_actor']:<10.4f} "
                f"{logs['loss_critic']:<10.4f} "
                f"{logs['entropy']:<10.4f}"
            )

    print("\nTraining complete!")


if __name__ == "__main__":
    main()
