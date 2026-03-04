# train_mixed_agents.py
"""
Training script for heterogeneous multi-agent system:
  - N standard agents (TelecomHybridActor)
  - 1 SBS agent (SBSActor)

Example usage:
    python train_mixed_agents.py
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Tuple

import torch
import torch.nn as nn

from trainers.mixed_ppo_trainer import MixedPPOConfig, MixedPPOTrainer
from models.gat import SharedGATNetwork
from models.actor import TelecomHybridActor, SBSActor
from models.critic import SharedCriticLocal


@dataclass
class MixedTelecomVectorEnvConfig:
    """Environment config with mixed agent types."""
    E: int          # num_envs
    N: int          # num standard agents (not including SBS)
    M: int          # subchannels per standard agent
    K: int          # num FAPs for SBS
    D_obs: int      # observation dim
    T: int          # episode length
    P_max: float    # max power for standard agents
    B_max: float    # max bandwidth for SBS


class MixedTelecomVectorEnv:
    """
    Vectorized environment stub for mixed agent types.

    Total agents: N_total = N + 1 (N standard + 1 SBS)

    reset() -> (X0, A0)
      X0: [E, N_total, D_obs]
      A0: [E, N_total, N_total]

    step(action) -> (X1, A1, done, info)
      action["compartments"]: [E, N, M] int64  (standard agents)
      action["power"]:       [E, N, M] float   (standard agents)
      action["bandwidth"]:   [E, K]    float   (SBS agent)
      done: [E] bool
      info: contains "S_final" at episode end (t=T-1)
    """

    def __init__(self, cfg: MixedTelecomVectorEnvConfig, device: torch.device) -> None:
        self.cfg = cfg
        self.device = device
        self.N_total = cfg.N + 1  # including SBS
        self._t = 0

    def _make_obs(self) -> torch.Tensor:
        return torch.randn((self.cfg.E, self.N_total, self.cfg.D_obs), device=self.device)

    def _make_adj(self) -> torch.Tensor:
        # dense adjacency with self-loops
        N = self.N_total
        A = torch.rand((self.cfg.E, N, N), device=self.device)
        eye = torch.eye(N, device=self.device).unsqueeze(0).expand(self.cfg.E, -1, -1)
        A = A + eye
        return A

    def reset(self) -> Tuple[torch.Tensor, torch.Tensor]:
        self._t = 0
        return self._make_obs(), self._make_adj()

    def step(self, action: Dict[str, torch.Tensor]) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor, Dict[str, Any]]:
        C = action["compartments"]  # [E, N, M]
        P = action["power"]         # [E, N, M]
        B = action["bandwidth"]     # [E, K]

        # done at fixed horizon
        self._t += 1
        done = torch.zeros((self.cfg.E,), device=self.device, dtype=torch.bool)
        info: Dict[str, Any] = {}

        if self._t >= self.cfg.T:
            done[:] = True

            # Example terminal score:
            # 1) total power (standard agents)
            total_power = P.sum(dim=(1, 2))  # [E]

            # 2) total bandwidth (SBS)
            total_bandwidth = B.sum(dim=1)  # [E]

            # 3) collision penalty (standard agents)
            collision = torch.zeros((self.cfg.E,), device=self.device)
            for m in range(self.cfg.M):
                cm = C[:, :, m]  # [E, N]
                for e in range(self.cfg.E):
                    vals = cm[e]  # [N]
                    eq = (vals.view(-1, 1) == vals.view(1, -1)).to(torch.float32)
                    collision[e] += (eq.sum() - float(self.cfg.N)) * 0.5

            # Terminal score (to be minimized)
            # Weighted combination of power, bandwidth, and collisions
            S_final = total_power + 0.5 * total_bandwidth + 0.1 * collision
            info["S_final"] = S_final.detach()

        X_next = self._make_obs()
        A_next = self._make_adj()
        return X_next, A_next, done, info


def main() -> None:
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Using device: {device}")

    # ====== Problem sizes ======
    E = 8              # num_envs
    N = 5              # num standard agents
    M = 5              # subchannels per standard agent
    K = 10             # num FAPs for SBS
    D_obs = 32         # observation dim
    D_h = 64           # GAT embedding dim
    T = 40             # episode length
    P_max = 1.0        # max power
    B_max = 10.0       # max bandwidth for SBS

    # Total agents (including SBS)
    N_total = N + 1

    print(f"Configuration:")
    print(f"  Standard agents: {N}")
    print(f"  SBS agents: 1")
    print(f"  Total agents: {N_total}")
    print(f"  Subchannels (std): {M}")
    print(f"  FAPs (SBS): {K}")

    # ====== Build modules ======
    # GAT needs to handle N_total agents
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

    # Standard actors (N of them)
    std_actors = []
    for i in range(N):
        std_actors.append(
            TelecomHybridActor(
                input_dim=D_h,
                num_subchannels=M,
                num_femtoCell=10,     # femtoCell candidates
                max_power=P_max,
                trunk_layers=(256, 256),
                activation="relu",
                dropout=0.0,
                min_std=1e-3,
                eps=1e-6,
                init_mode="xavier",
            ).to(device)
        )

    # SBS actor (1 of them)
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
        scale=10.0,
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

    # ====== Env ======
    env = MixedTelecomVectorEnv(
        MixedTelecomVectorEnvConfig(E=E, N=N, M=M, K=K, D_obs=D_obs, T=T, P_max=P_max, B_max=B_max),
        device=device,
    )

    # ====== Training loop ======
    print("\nStarting training...")
    for it in range(1, 51):
        buf = trainer.collect_episode(env)
        logs = trainer.update(buf)
        if it % 1 == 0:
            print(
                f"[Iter {it:04d}] "
                f"loss={logs['loss_total']:.4f} "
                f"actor={logs['loss_actor']:.4f} "
                f"critic={logs['loss_critic']:.4f} "
                f"ent={logs['entropy']:.4f}"
            )

    print("\nTraining complete!")


if __name__ == "__main__":
    main()
