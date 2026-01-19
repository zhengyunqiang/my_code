# trainers/ppo_trainer.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

import torch
import torch.nn as nn
import torch.nn.functional as F

from buffers.rollout_buffer import RolloutBufferEpisode

from models.gat import SharedGATNetwork
from models.actor import TelecomHybridActor
from models.critic import SharedCriticLocal


@dataclass
class PPOConfig:
    # rollout
    T: int
    E: int
    N: int
    M: int
    D_obs: int
    P_max: float

    # sparse reward mapping
    scale: float

    # PPO / GAE
    gamma: float = 0.99
    lam: float = 0.95
    clip_eps: float = 0.2
    vf_coef: float = 0.5
    ent_coef: float = 0.01

    # optimization
    epochs: int = 4
    minibatch_size: int = 256
    max_grad_norm: float = 1.0

    # advantage normalization
    normalize_adv: bool = True
    eps_adv: float = 1e-8


def _to_torch(x: Any, device: torch.device, dtype: Optional[torch.dtype] = None) -> torch.Tensor:
    if isinstance(x, torch.Tensor):
        t = x.to(device=device)
        if dtype is not None:
            t = t.to(dtype=dtype)
        return t
    t = torch.as_tensor(x, device=device)
    if dtype is not None:
        t = t.to(dtype=dtype)
    return t


def _extract_step_outputs(step_out: Any) -> Tuple[Any, Any, Any, Optional[Any]]:
    """
    Flexible parser for env.step() outputs.

    Supported patterns:
      (X_next, A_next, done, info)
      (X_next, A_next, done, S_final)
      (X_next, A_next, done, S_final, info)

    Returns:
      X_next, A_next, done, info (info may contain S_final)
    """
    if not isinstance(step_out, (tuple, list)):
        raise ValueError("env.step(...) must return a tuple/list.")

    if len(step_out) == 4:
        Xn, An, done, last = step_out
        # last could be info or S_final
        if isinstance(last, dict):
            info = last
        else:
            info = {"S_final": last}
        return Xn, An, done, info

    if len(step_out) == 5:
        Xn, An, done, S_final, info = step_out
        if info is None:
            info = {}
        if "S_final" not in info:
            info["S_final"] = S_final
        return Xn, An, done, info

    raise ValueError(f"Unsupported env.step return length: {len(step_out)}")


class PPOTrainer:
    """
    End-to-end PPO trainer for:
      SharedGATNetwork + N * TelecomHybridActor + SharedCriticLocal

    Rollout: collect ONE full episode of length T for E parallel envs.
    Update : flatten (T,E) -> B'=T*E and run PPO epochs.
    """

    def __init__(
        self,
        cfg: PPOConfig,
        gat: nn.Module,
        critic: nn.Module,
        actors: Sequence[nn.Module],
        opt_gat: torch.optim.Optimizer,
        opt_critic: torch.optim.Optimizer,
        opt_actors: torch.optim.Optimizer,
        device: Union[str, torch.device] = "cpu",
    ) -> None:
        self.cfg = cfg
        self.device = torch.device(device)

        self.gat = gat.to(self.device)
        self.critic = critic.to(self.device)
        self.actors = nn.ModuleList(list(actors)).to(self.device)

        if len(self.actors) != cfg.N:
            raise ValueError(f"Expected N={cfg.N} actors, got {len(self.actors)}")

        self.opt_gat = opt_gat
        self.opt_critic = opt_critic
        self.opt_actors = opt_actors

        # basic checks
        if cfg.scale <= 0:
            raise ValueError("scale must be > 0")
        if cfg.P_max <= 0:
            raise ValueError("P_max must be > 0")

    @torch.no_grad()
    def collect_episode(self, env: Any) -> RolloutBufferEpisode:
        """
        Collect one full episode (T steps) for E parallel envs.

        Env contract (recommended):
          reset() -> (X0, A0)
          step(action_dict) -> (X1, A1, done, info)  # or compatible forms
        where:
          X_t : [E,N,D_obs]
          A_t : [E,N,N]
          done: [E] bool/int
          info: includes S_final at episode end (t=T-1)
        """
        cfg = self.cfg

        buf = RolloutBufferEpisode(
            T=cfg.T, E=cfg.E, N=cfg.N, M=cfg.M, D_obs=cfg.D_obs, device=self.device
        )

        X, A = env.reset()
        X = _to_torch(X, self.device, dtype=torch.float32)
        A = _to_torch(A, self.device, dtype=torch.float32)

        S_final = None

        for t in range(cfg.T):
            # 1) Shared encoding
            H = self.gat(X, A)  # [E,N,D_h]

            # 2) Value estimate
            V_out = self.critic(H)  # expected CriticOutput with attribute .V
            V = V_out.V  # [E,N,1]

            # 3) Per-agent actions
            C_list: List[torch.Tensor] = []
            P_list: List[torch.Tensor] = []
            logp_list: List[torch.Tensor] = []

            for i in range(cfg.N):
                h_i = H[:, i, :]  # [E,D_h]
                act = self.actors[i].get_action(h_i)

                # Actor code might return key "users"; interpret as compartment ids
                c_i = act.get("compartments", act.get("users"))
                if c_i is None:
                    raise KeyError('Actor.get_action must return "users" or "compartments".')
                p_i = act["power"]
                logp_i = act["logp"]

                # shapes: c_i [E,M], p_i [E,M], logp_i [E]
                C_list.append(c_i)
                P_list.append(p_i)
                logp_list.append(logp_i)

            C_t = torch.stack(C_list, dim=1).to(torch.long)          # [E,N,M]
            P_t = torch.stack(P_list, dim=1).to(torch.float32)       # [E,N,M]
            logp_t = torch.stack(logp_list, dim=1).to(torch.float32) # [E,N]

            # 4) Env step
            step_out = env.step({"compartments": C_t, "power": P_t})
            X_next, A_next, done, info = _extract_step_outputs(step_out)

            X_next = _to_torch(X_next, self.device, dtype=torch.float32)
            A_next = _to_torch(A_next, self.device, dtype=torch.float32)
            done_t = _to_torch(done, self.device).to(torch.float32).view(cfg.E)  # [E]

            # 5) Store step (sparse reward default 0 here)
            buf.store_step(
                X_t=X,
                A_t=A,
                C_t=C_t,
                P_t=P_t,
                logp_t=logp_t,
                V_t=V,
                done_t=done_t,
                r_t=None,
            )

            X, A = X_next, A_next

            # episode end score capture (expected at last step)
            if info is not None and ("S_final" in info):
                S_final = info["S_final"]

        if S_final is None:
            raise RuntimeError('env.step(...) did not provide "S_final" at episode end.')

        S_final_t = _to_torch(S_final, self.device, dtype=torch.float32).view(cfg.E)  # [E]
        R_final = -S_final_t / float(cfg.scale)  # [E]
        buf.set_final_reward(R_final)

        # If env doesn't produce done, enforce fixed-horizon terminal at last step
        # (The stored done masks are already present; if all zeros, GAE still correct with V_T=0.)
        buf.compute_gae_and_returns(
            gamma=cfg.gamma,
            lam=cfg.lam,
            normalize_adv=cfg.normalize_adv,
            eps_adv=cfg.eps_adv,
        )
        return buf

    def update(self, buf: RolloutBufferEpisode) -> Dict[str, float]:
        """
        PPO update using data from one collected episode.

        Uses:
          - Old log-prob: buf.logp
          - Returns G:    buf.ret
          - Advantage A:  buf.adv
        """
        cfg = self.cfg
        self.gat.train()
        self.critic.train()
        self.actors.train()

        total_actor_loss = 0.0
        total_critic_loss = 0.0
        total_entropy = 0.0
        total_loss = 0.0
        n_updates = 0

        for _ in range(cfg.epochs):
            for _, batch in buf.minibatches(cfg.minibatch_size, shuffle=True):
                # Recompute shared encoding
                H = self.gat(batch.X, batch.A)  # [B',N,D_h]
                V_new = self.critic(H).V        # [B',N,1]

                # Critic loss: MSE(V_new, G)
                critic_loss = F.mse_loss(V_new, batch.ret)

                # Per-agent PPO actor loss and entropy
                actor_losses = []
                entropies = []

                for i in range(cfg.N):
                    h_i = H[:, i, :]                # [B',D_h]
                    c_i = batch.C[:, i, :]          # [B',M]
                    p_i = batch.P[:, i, :]          # [B',M]
                    adv_i = batch.adv[:, i]         # [B']
                    logp_old_i = batch.logp[:, i]   # [B']

                    # evaluate under current policy
                    eval_out = self.actors[i].evaluate(h_i, c_i, p_i)
                    logp_new_i = eval_out["logp_new"]    # [B']
                    entropy_i = eval_out["entropy"]      # [B']

                    # ratio
                    ratio = torch.exp(logp_new_i - logp_old_i)

                    # PPO clipped surrogate
                    surr1 = ratio * adv_i
                    surr2 = torch.clamp(ratio, 1.0 - cfg.clip_eps, 1.0 + cfg.clip_eps) * adv_i
                    actor_loss_i = -torch.mean(torch.minimum(surr1, surr2))

                    actor_losses.append(actor_loss_i)
                    entropies.append(torch.mean(entropy_i))

                actor_loss = torch.stack(actor_losses).mean()
                entropy = torch.stack(entropies).mean()

                # Total loss
                loss = actor_loss + cfg.vf_coef * critic_loss - cfg.ent_coef * entropy

                # Backprop
                self.opt_gat.zero_grad(set_to_none=True)
                self.opt_critic.zero_grad(set_to_none=True)
                self.opt_actors.zero_grad(set_to_none=True)

                loss.backward()

                # Gradient clipping (three groups, consistent with parameter partition)
                if cfg.max_grad_norm is not None and cfg.max_grad_norm > 0:
                    torch.nn.utils.clip_grad_norm_(self.gat.parameters(), cfg.max_grad_norm)
                    torch.nn.utils.clip_grad_norm_(self.critic.parameters(), cfg.max_grad_norm)
                    torch.nn.utils.clip_grad_norm_(self.actors.parameters(), cfg.max_grad_norm)

                self.opt_gat.step()
                self.opt_critic.step()
                self.opt_actors.step()

                total_actor_loss += float(actor_loss.detach().cpu())
                total_critic_loss += float(critic_loss.detach().cpu())
                total_entropy += float(entropy.detach().cpu())
                total_loss += float(loss.detach().cpu())
                n_updates += 1

        if n_updates == 0:
            n_updates = 1

        return {
            "loss_total": total_loss / n_updates,
            "loss_actor": total_actor_loss / n_updates,
            "loss_critic": total_critic_loss / n_updates,
            "entropy": total_entropy / n_updates,
        }
