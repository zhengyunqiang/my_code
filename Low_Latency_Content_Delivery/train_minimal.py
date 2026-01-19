# train_minimal.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Tuple

import torch
import torch.nn as nn

# Adjust these imports to match your actual file paths
from trainers.ppo_trainer import PPOConfig, PPOTrainer

from models.gat import SharedGATNetwork
from models.actor import TelecomHybridActor
from models.critic import SharedCriticLocal


@dataclass
class DummyTelecomVectorEnvConfig:
    E: int
    N: int
    M: int
    K: int
    D_obs: int
    T: int
    P_max: float


class DummyTelecomVectorEnv:
    """
    A minimal vectorized environment stub that matches the trainer contract.

    reset() -> (X0, A0)
      X0: [E,N,D_obs]
      A0: [E,N,N]

    step(action) -> (X1, A1, done, info)
      action["compartments"]: [E,N,M] int64
      action["power"]       : [E,N,M] float
      done: [E] bool
      info: contains "S_final" at episode end (t=T-1)

    This env is ONLY for verifying end-to-end code wiring.
    Replace it with your real environment implementation.
    """

    def __init__(self, cfg: DummyTelecomVectorEnvConfig, device: torch.device) -> None:
        self.cfg = cfg
        self.device = device
        self._t = 0

    def _make_obs(self) -> torch.Tensor:
        # simple random observations
        return torch.randn((self.cfg.E, self.cfg.N, self.cfg.D_obs), device=self.device)

    def _make_adj(self) -> torch.Tensor:
        # dense adjacency with self-loops; random positive weights
        A = torch.rand((self.cfg.E, self.cfg.N, self.cfg.N), device=self.device)
        eye = torch.eye(self.cfg.N, device=self.device).unsqueeze(0).expand(self.cfg.E, -1, -1)
        A = A + eye
        return A

    def reset(self) -> Tuple[torch.Tensor, torch.Tensor]:
        self._t = 0
        return self._make_obs(), self._make_adj()

    def step(self, action: Dict[str, torch.Tensor]) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor, Dict[str, Any]]:
        C = action["compartments"]  # [E,N,M]
        P = action["power"]         # [E,N,M]

        # done at fixed horizon
        self._t += 1
        done = torch.zeros((self.cfg.E,), device=self.device, dtype=torch.bool)
        info: Dict[str, Any] = {}

        if self._t >= self.cfg.T:
            done[:] = True

            # Example terminal score:
            # 1) total power
            total_power = P.sum(dim=(1, 2))  # [E]

            # 2) collision penalty: same compartment chosen by multiple agents on same subchannel
            # compute collisions per env, per subchannel
            # C: [E,N,M] -> for each env e and m, count duplicates across N
            collision = torch.zeros((self.cfg.E,), device=self.device)
            for m in range(self.cfg.M):
                cm = C[:, :, m]  # [E,N]
                # for each env, count how many pairs share same id
                for e in range(self.cfg.E):
                    vals = cm[e]  # [N]
                    # naive O(N^2) (fine for dummy); replace in real env
                    eq = (vals.view(-1, 1) == vals.view(1, -1)).to(torch.float32)
                    # subtract diagonal, then count pairs /2
                    collision[e] += (eq.sum() - float(self.cfg.N)) * 0.5

            # terminal score (to be minimized)
            S_final = total_power + 0.1 * collision
            info["S_final"] = S_final.detach()

        X_next = self._make_obs()
        A_next = self._make_adj()
        return X_next, A_next, done, info


def main() -> None:
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    # ====== Problem sizes (example) ======
    E = 8          # num_envs
    N = 5          # num_agents
    M = 5          # subchannels per agent
    K = 10         # compartments candidates
    D_obs = 32     # observation dim
    D_h = 64       # GAT embedding dim
    T = 40         # episode length
    P_max = 1.0

    # ====== Build modules ======
    gat = SharedGATNetwork(
        d_obs=D_obs,
        d_h=D_h,
        num_layers=2,
        num_heads=4,
        dropout=0.0,
        use_edge_weight=False,
        use_residual=False,
        use_layernorm=False,
    ).to(device)

    critic = SharedCriticLocal(
        d_h=D_h,
        hidden_layers=(256, 256),
        activation="relu",
        use_layernorm=False,
    ).to(device)

    actors = []
    for _ in range(N):
        actors.append(
            TelecomHybridActor(
                input_dim=D_h,
                num_subchannels=M,
                num_femtoCell=K,      # number of femtoCell candidates
                max_power=P_max,
                trunk_layers=(256, 256),
                activation="relu",
                dropout=0.0,
                min_std=1e-3,
                eps=1e-6,
                init_mode="xavier",
            ).to(device)
        )

    # ====== Optimizers ======
    opt_gat = torch.optim.Adam(gat.parameters(), lr=3e-4)
    opt_critic = torch.optim.Adam(critic.parameters(), lr=3e-4)
    opt_actors = torch.optim.Adam(nn.ModuleList(actors).parameters(), lr=3e-4)

    # ====== Trainer config ======
    cfg = PPOConfig(
        T=T, E=E, N=N, M=M, D_obs=D_obs, P_max=P_max,
        scale=10.0,          # reward = -S_final/scale
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

    trainer = PPOTrainer(
        cfg=cfg,
        gat=gat,
        critic=critic,
        actors=actors,
        opt_gat=opt_gat,
        opt_critic=opt_critic,
        opt_actors=opt_actors,
        device=device,
    )

    # ====== Env ======
    env = DummyTelecomVectorEnv(
        DummyTelecomVectorEnvConfig(E=E, N=N, M=M, K=K, D_obs=D_obs, T=T, P_max=P_max),
        device=device,
    )

    # ====== Training loop ======
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


if __name__ == "__main__":
    main()
