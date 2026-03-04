# trainers/mixed_ppo_trainer.py
"""
PPO Trainer for heterogeneous multi-agent systems.

Supports:
  - N standard agents (TelecomHybridActor): output compartments [M] + power [M]
  - 1 SBS agent (SBSActor): output bandwidth [K]
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

import torch
import torch.nn as nn
import torch.nn.functional as F
import sys

# Ensure sibling packages (buffers/models/utils) are importable even when this
# file is executed from non-project-root working directories.
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from buffers.mixed_rollout_buffer import MixedRolloutBufferEpisode
from utils.slot_evaluator import EpisodeSlotEvaluator

from models.gat import SharedGATNetwork
from models.actor import TelecomHybridActor, SBSActor
from models.critic import SharedCriticLocal


@dataclass
class MixedPPOConfig:
    # rollout
    T: int
    E: int
    N: int                 # number of standard agents (not including SBS)
    M: int                 # subchannels per standard agent
    K: int                 # number of FAPs for SBS
    D_obs: int
    P_max: float           # max power for standard agents
    B_max: float           # max bandwidth for SBS

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

    # evaluator-guided critic supervision
    use_slot_evaluator: bool = True
    evaluator_coef: float = 0.1


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


class MixedPPOTrainer:
    """
    PPO trainer for heterogeneous multi-agent systems:
      SharedGATNetwork + N * TelecomHybridActor + 1 * SBSActor + SharedCriticLocal

    Total agents: N_total = N + 1 (SBS is the last agent)

    Rollout: collect ONE full episode of length T for E parallel envs.
    Update : flatten (T,E) -> B'=T*E and run PPO epochs.
    """

    def __init__(
        self,
        cfg: MixedPPOConfig,
        gat: SharedGATNetwork,
        critic: SharedCriticLocal,
        std_actors: Sequence[TelecomHybridActor],  # N standard agents
        sbs_actor: SBSActor,                       # 1 SBS agent
        opt_gat: torch.optim.Optimizer,
        opt_critic: torch.optim.Optimizer,
        opt_std_actors: torch.optim.Optimizer,
        opt_sbs_actor: torch.optim.Optimizer,
        device: Union[str, torch.device] = "cpu",
    ) -> None:
        self.cfg = cfg
        self.device = torch.device(device)

        self.gat = gat.to(self.device)
        self.critic = critic.to(self.device)
        self.std_actors = nn.ModuleList(list(std_actors)).to(self.device)
        self.sbs_actor = sbs_actor.to(self.device)

        if len(self.std_actors) != cfg.N:
            raise ValueError(f"Expected N={cfg.N} standard actors, got {len(self.std_actors)}")

        self.opt_gat = opt_gat
        self.opt_critic = opt_critic
        self.opt_std_actors = opt_std_actors
        self.opt_sbs_actor = opt_sbs_actor

        # Basic checks
        if cfg.scale <= 0:
            raise ValueError("scale must be > 0")
        if cfg.P_max <= 0:
            raise ValueError("P_max must be > 0")
        if cfg.B_max <= 0:
            raise ValueError("B_max must be > 0")

        self.slot_evaluator = EpisodeSlotEvaluator() if cfg.use_slot_evaluator else None

    @torch.no_grad()
    def collect_episode(self, env: Any) -> MixedRolloutBufferEpisode:
        """
        Collect one full episode (T steps) for E parallel envs.

        Env contract (recommended):
          reset() -> (X0, A0) where:
            X_t : [E, N_total, D_obs]  (N_total = N + 1 for SBS)
            A_t : [E, N_total, N_total]
          step(action_dict) -> (X1, A1, done, info)
            action_dict = {
                "compartments": [E, N, M],  # standard agents
                "power": [E, N, M],         # standard agents
                "bandwidth": [E, K],        # SBS agent
            }
          done: [E] bool/int
          info: includes S_final at episode end (t=T-1)
        """
        cfg = self.cfg
        N_total = cfg.N + 1  # including SBS

        buf = MixedRolloutBufferEpisode(
            T=cfg.T, E=cfg.E, N=cfg.N, M=cfg.M, K=cfg.K,
            D_obs=cfg.D_obs, device=self.device
        )

        X, A = env.reset()
        X = _to_torch(X, self.device, dtype=torch.float32)
        A = _to_torch(A, self.device, dtype=torch.float32)

        S_final = None

        for t in range(cfg.T):
            # 1) Shared encoding (include SBS)
            H = self.gat(X, A)  # [E, N_total, D_h]

            # 2) Value estimate (all agents)
            V_out = self.critic(H)  # CriticOutput with .V
            V = V_out.V  # [E, N_total, 1]

            # 3) Standard agents actions (first N agents)
            C_list: List[torch.Tensor] = []
            P_list: List[torch.Tensor] = []
            logp_std_list: List[torch.Tensor] = []

            for i in range(cfg.N):
                h_i = H[:, i, :]  # [E, D_h]
                act = self.std_actors[i].get_action(h_i)

                c_i = act.get("compartments", act.get("users"))
                if c_i is None:
                    raise KeyError('Actor.get_action must return "users" or "compartments".')
                p_i = act["power"]
                logp_i = act["logp"]

                # shapes: c_i [E,M], p_i [E,M], logp_i [E]
                C_list.append(c_i)
                P_list.append(p_i)
                logp_std_list.append(logp_i)

            C_t = torch.stack(C_list, dim=1).to(torch.long)          # [E, N, M]
            P_t = torch.stack(P_list, dim=1).to(torch.float32)       # [E, N, M]
            logp_std_t = torch.stack(logp_std_list, dim=1).to(torch.float32)  # [E, N]

            # 4) SBS agent action (last agent, index N)
            h_sbs = H[:, cfg.N, :]  # [E, D_h]
            sbs_act = self.sbs_actor.get_action(h_sbs)

            B_sbs_t = sbs_act["bandwidth"]      # [E, K]
            logp_sbs_t = sbs_act["logp"]        # [E]

            # 5) Env step
            step_out = env.step({
                "compartments": C_t,
                "power": P_t,
                "bandwidth": B_sbs_t,
            })
            X_next, A_next, done, info = _extract_step_outputs(step_out)

            X_next = _to_torch(X_next, self.device, dtype=torch.float32)
            A_next = _to_torch(A_next, self.device, dtype=torch.float32)
            done_t = _to_torch(done, self.device).to(torch.float32).view(cfg.E)  # [E]

            # 6) Store step
            buf.store_step(
                X_t=X, A_t=A,
                C_t=C_t, P_t=P_t, B_sbs_t=B_sbs_t,
                logp_std_t=logp_std_t, logp_sbs_t=logp_sbs_t,
                V_t=V, done_t=done_t, r_t=None,
            )

            X, A = X_next, A_next

            # episode end score capture
            if info is not None and ("S_final" in info):
                S_final = info["S_final"]

        if S_final is None:
            raise RuntimeError('env.step(...) did not provide "S_final" at episode end.')

        S_final_t = _to_torch(S_final, self.device, dtype=torch.float32).view(cfg.E)  # [E]
        R_final = -S_final_t / float(cfg.scale)  # [E]
        buf.set_final_reward(R_final)

        # Episode-level evaluator target (minimum completion slots)
        if self.slot_evaluator is not None and hasattr(env, "external_rate_history") and hasattr(env, "initial_user_data"):
            eval_res = self.slot_evaluator.solve_episode(
                rate_history=env.external_rate_history,   # [T,E,C]
                user_demands=env.initial_user_data,       # [E,C,U]
                timeslot=float(env.cfg.timeslot),
            )
            buf.set_evaluator_targets(eval_res.min_slots, eval_res.feasible_mask)

        buf.compute_gae_and_returns(
            gamma=cfg.gamma,
            lam=cfg.lam,
            normalize_adv=cfg.normalize_adv,
            eps_adv=cfg.eps_adv,
        )
        return buf

    def update(self, buf: MixedRolloutBufferEpisode) -> Dict[str, float]:
        """
        PPO update using data from one collected episode.
        """
        cfg = self.cfg
        self.gat.train()
        self.critic.train()
        self.std_actors.train()
        self.sbs_actor.train()

        total_actor_loss = 0.0
        total_critic_loss = 0.0
        total_evaluator_loss = 0.0
        total_entropy = 0.0
        total_loss = 0.0
        n_updates = 0

        for _ in range(cfg.epochs):
            for sel, batch in buf.minibatches(cfg.minibatch_size, shuffle=True):
                # Recompute shared encoding
                H = self.gat(batch.X, batch.A)  # [B', N_total, D_h]
                V_new = self.critic(H).V        # [B', N_total, 1]

                # Critic loss: MSE(V_new, G)
                critic_loss = F.mse_loss(V_new, batch.ret)

                # Evaluator-guided auxiliary value loss
                evaluator_loss = torch.zeros((), device=self.device)
                if cfg.use_slot_evaluator and (buf.eval_min_slots is not None):
                    env_idx = torch.remainder(sel, cfg.E).long()  # [B']
                    t_idx = torch.div(sel, cfg.E, rounding_mode="floor").to(torch.float32)  # [B']
                    min_slots = buf.eval_min_slots[env_idx]  # [B']

                    # Target remaining slots at step t, normalized by horizon.
                    slot_target = (min_slots - t_idx).clamp(min=0.0) / max(float(cfg.T), 1.0)
                    slot_target = slot_target.view(-1, 1, 1).expand(-1, cfg.N + 1, 1)

                    # Normalize both tensors to keep this auxiliary loss scale-stable.
                    pred = V_new
                    pred_norm = (pred - pred.mean()) / (pred.std(unbiased=False) + 1e-6)
                    tgt_norm = (slot_target - slot_target.mean()) / (slot_target.std(unbiased=False) + 1e-6)

                    if buf.eval_feasible is not None:
                        feasible = buf.eval_feasible[env_idx].to(pred.dtype).view(-1, 1, 1)
                        if feasible.sum() > 0:
                            denom = (feasible.sum() * pred.shape[1]).clamp_min(1.0)
                            evaluator_loss = (((pred_norm - tgt_norm).pow(2)) * feasible).sum() / denom
                        else:
                            evaluator_loss = F.mse_loss(pred_norm, tgt_norm)
                    else:
                        evaluator_loss = F.mse_loss(pred_norm, tgt_norm)

                # === Standard agents PPO update ===
                actor_losses = []
                entropies = []

                for i in range(cfg.N):
                    h_i = H[:, i, :]                # [B', D_h]
                    c_i = batch.C[:, i, :]          # [B', M]
                    p_i = batch.P[:, i, :]          # [B', M]
                    adv_i = batch.adv_std[:, i]     # [B']
                    logp_old_i = batch.logp_std[:, i]  # [B']

                    eval_out = self.std_actors[i].evaluate(h_i, c_i, p_i)
                    logp_new_i = eval_out["logp_new"]    # [B']
                    entropy_i = eval_out["entropy"]       # [B']

                    ratio = torch.exp(logp_new_i - logp_old_i)
                    surr1 = ratio * adv_i
                    surr2 = torch.clamp(ratio, 1.0 - cfg.clip_eps, 1.0 + cfg.clip_eps) * adv_i
                    actor_loss_i = -torch.mean(torch.minimum(surr1, surr2))

                    actor_losses.append(actor_loss_i)
                    entropies.append(torch.mean(entropy_i))

                # === SBS agent PPO update ===
                h_sbs = H[:, cfg.N, :]              # [B', D_h]
                b_sbs = batch.B_sbs                 # [B', K]
                adv_sbs = batch.adv_sbs             # [B']
                logp_old_sbs = batch.logp_sbs       # [B']

                sbs_eval_out = self.sbs_actor.evaluate(h_sbs, b_sbs)
                logp_new_sbs = sbs_eval_out["logp_new"]  # [B']
                entropy_sbs = sbs_eval_out["entropy"]     # [B']

                ratio_sbs = torch.exp(logp_new_sbs - logp_old_sbs)
                surr1_sbs = ratio_sbs * adv_sbs
                surr2_sbs = torch.clamp(ratio_sbs, 1.0 - cfg.clip_eps, 1.0 + cfg.clip_eps) * adv_sbs
                actor_loss_sbs = -torch.mean(torch.minimum(surr1_sbs, surr2_sbs))

                actor_losses.append(actor_loss_sbs)
                entropies.append(torch.mean(entropy_sbs))

                # Aggregate
                actor_loss = torch.stack(actor_losses).mean()
                entropy = torch.stack(entropies).mean()

                # Total loss
                loss = (
                    actor_loss
                    + cfg.vf_coef * critic_loss
                    + cfg.evaluator_coef * evaluator_loss
                    - cfg.ent_coef * entropy
                )

                # Backprop
                self.opt_gat.zero_grad(set_to_none=True)
                self.opt_critic.zero_grad(set_to_none=True)
                self.opt_std_actors.zero_grad(set_to_none=True)
                self.opt_sbs_actor.zero_grad(set_to_none=True)

                loss.backward()

                # Gradient clipping
                if cfg.max_grad_norm is not None and cfg.max_grad_norm > 0:
                    torch.nn.utils.clip_grad_norm_(self.gat.parameters(), cfg.max_grad_norm)
                    torch.nn.utils.clip_grad_norm_(self.critic.parameters(), cfg.max_grad_norm)
                    torch.nn.utils.clip_grad_norm_(self.std_actors.parameters(), cfg.max_grad_norm)
                    torch.nn.utils.clip_grad_norm_(self.sbs_actor.parameters(), cfg.max_grad_norm)

                self.opt_gat.step()
                self.opt_critic.step()
                self.opt_std_actors.step()
                self.opt_sbs_actor.step()

                total_actor_loss += float(actor_loss.detach().cpu())
                total_critic_loss += float(critic_loss.detach().cpu())
                total_evaluator_loss += float(evaluator_loss.detach().cpu())
                total_entropy += float(entropy.detach().cpu())
                total_loss += float(loss.detach().cpu())
                n_updates += 1

        if n_updates == 0:
            n_updates = 1

        return {
            "loss_total": total_loss / n_updates,
            "loss_actor": total_actor_loss / n_updates,
            "loss_critic": total_critic_loss / n_updates,
            "loss_evaluator": total_evaluator_loss / n_updates,
            "entropy": total_entropy / n_updates,
        }
