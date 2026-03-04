# buffers/mixed_rollout_buffer.py
"""
Mixed rollout buffer for heterogeneous multi-agent systems.

Supports:
  - N standard agents (TelecomHybridActor): output compartments [M] + power [M]
  - 1 SBS agent (SBSActor): output bandwidth [K]
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterator, Optional, Tuple

import torch


@dataclass
class MixedEpisodeBatch:
    """
    Flattened batch (B' = T*E) for PPO update with mixed agent types.

    Shapes:
      X         : [B', N_total, D_obs]  where N_total = N + 1 (including SBS)
      A         : [B', N_total, N_total]
      C         : [B', N, M]            compartments for standard agents only
      P         : [B', N, M]            power for standard agents only
      B_sbs     : [B', K]               bandwidth for SBS agent only
      logp_std  : [B', N]               old log-prob for standard agents
      logp_sbs  : [B']                  old log-prob for SBS agent
      V_old     : [B', N_total, 1]      old value prediction for all agents
      adv_std   : [B', N]               GAE advantage for standard agents
      adv_sbs   : [B']                  GAE advantage for SBS agent
      ret       : [B', N_total, 1]      target return for all agents
      done      : [B'] or [B', 1]       optional mask
    """
    X: torch.Tensor
    A: torch.Tensor
    C: torch.Tensor
    P: torch.Tensor
    B_sbs: torch.Tensor
    logp_std: torch.Tensor
    logp_sbs: torch.Tensor
    V_old: torch.Tensor
    adv_std: torch.Tensor
    adv_sbs: torch.Tensor
    ret: torch.Tensor
    done: Optional[torch.Tensor] = None


class MixedRolloutBufferEpisode:
    """
    Rollout buffer for mixed agent types:
      - N standard agents (TelecomHybridActor)
      - 1 SBS agent (SBSActor)

    Total agents: N_total = N + 1
    SBS is always the last agent (index N)

    Storage shapes (time-major):
      X        : [T, E, N_total, D_obs]
      A        : [T, E, N_total, N_total]
      C        : [T, E, N, M]           (standard agents only)
      P        : [T, E, N, M]           (standard agents only)
      B_sbs    : [T, E, K]              (SBS agent only)
      logp_std : [T, E, N]              (standard agents only)
      logp_sbs : [T, E]                 (SBS agent only)
      V        : [T, E, N_total, 1]     (all agents)
      r        : [T, E]                 (env-level sparse reward)
      done     : [T, E]                 (env-level done)
      adv_std  : [T, E, N]              (standard agents only)
      adv_sbs  : [T, E]                 (SBS agent only)
      ret      : [T, E, N_total, 1]     (all agents)
    """

    def __init__(
        self,
        T: int,
        E: int,
        N: int,                 # number of standard agents
        M: int,                 # subchannels per standard agent
        K: int,                 # number of FAPs for SBS
        D_obs: int,
        device: torch.device,
        dtype_obs: torch.dtype = torch.float32,
        dtype_adj: torch.dtype = torch.float32,
        dtype_power: torch.dtype = torch.float32,
    ) -> None:
        self.T = int(T)
        self.E = int(E)
        self.N = int(N)          # standard agents
        self.K = int(K)          # SBS FAPs
        self.M = int(M)          # subchannels
        self.N_total = N + 1     # including SBS
        self.D_obs = int(D_obs)
        self.device = device

        # Observations and adjacency (include SBS)
        self.X = torch.zeros((T, E, self.N_total, D_obs), device=device, dtype=dtype_obs)
        self.A = torch.zeros((T, E, self.N_total, self.N_total), device=device, dtype=dtype_adj)

        # Standard agents actions
        self.C = torch.zeros((T, E, N, M), device=device, dtype=torch.long)
        self.P = torch.zeros((T, E, N, M), device=device, dtype=dtype_power)

        # SBS agent action
        self.B_sbs = torch.zeros((T, E, K), device=device, dtype=dtype_power)

        # Log-probs
        self.logp_std = torch.zeros((T, E, N), device=device, dtype=torch.float32)
        self.logp_sbs = torch.zeros((T, E), device=device, dtype=torch.float32)

        # Values (all agents)
        self.V = torch.zeros((T, E, self.N_total, 1), device=device, dtype=torch.float32)

        # Rewards
        self.r = torch.zeros((T, E), device=device, dtype=torch.float32)
        self.done = torch.zeros((T, E), device=device, dtype=torch.float32)

        # Advantages and returns
        self.adv_std = torch.zeros((T, E, N), device=device, dtype=torch.float32)
        self.adv_sbs = torch.zeros((T, E), device=device, dtype=torch.float32)
        self.ret = torch.zeros((T, E, self.N_total, 1), device=device, dtype=torch.float32)

        # Episode-level evaluator outputs (filled after rollout)
        self.eval_min_slots: Optional[torch.Tensor] = None   # [E]
        self.eval_feasible: Optional[torch.Tensor] = None    # [E] bool

        self._t = 0

    def reset_ptr(self) -> None:
        self._t = 0

    @property
    def is_full(self) -> bool:
        return self._t >= self.T

    def store_step(
        self,
        X_t: torch.Tensor,              # [E, N_total, D_obs]
        A_t: torch.Tensor,              # [E, N_total, N_total]
        C_t: torch.Tensor,              # [E, N, M]
        P_t: torch.Tensor,              # [E, N, M]
        B_sbs_t: torch.Tensor,          # [E, K]
        logp_std_t: torch.Tensor,       # [E, N]
        logp_sbs_t: torch.Tensor,       # [E]
        V_t: torch.Tensor,              # [E, N_total, 1]
        done_t: torch.Tensor,           # [E]
        r_t: Optional[torch.Tensor] = None,  # [E]
    ) -> None:
        if self.is_full:
            raise RuntimeError("Buffer is full. Create a new buffer or reset_ptr().")

        t = self._t
        self.X[t].copy_(X_t)
        self.A[t].copy_(A_t)
        self.C[t].copy_(C_t)
        self.P[t].copy_(P_t)
        self.B_sbs[t].copy_(B_sbs_t)
        self.logp_std[t].copy_(logp_std_t)
        self.logp_sbs[t].copy_(logp_sbs_t)
        self.V[t].copy_(V_t)
        self.done[t].copy_(done_t.to(self.done.dtype))

        if r_t is not None:
            self.r[t].copy_(r_t.to(self.r.dtype))

        self._t += 1

    def set_final_reward(self, R_final: torch.Tensor) -> None:
        """Write terminal reward to last time step: r[T-1] = R_final, where R_final is [E]."""
        if self._t != self.T:
            raise RuntimeError(f"Episode not complete: ptr={self._t}, expected T={self.T}")
        self.r[self.T - 1].copy_(R_final.to(self.r.dtype))

    def set_evaluator_targets(
        self,
        min_slots: torch.Tensor,      # [E]
        feasible_mask: torch.Tensor,  # [E] bool
    ) -> None:
        """Attach episode-level slot evaluator outputs."""
        if min_slots.shape != (self.E,):
            raise ValueError(f"min_slots must be [E={self.E}], got {tuple(min_slots.shape)}")
        if feasible_mask.shape != (self.E,):
            raise ValueError(f"feasible_mask must be [E={self.E}], got {tuple(feasible_mask.shape)}")
        self.eval_min_slots = min_slots.to(self.device, dtype=torch.float32)
        self.eval_feasible = feasible_mask.to(self.device, dtype=torch.bool)

    @torch.no_grad()
    def compute_gae_and_returns(
        self,
        gamma: float,
        lam: float,
        normalize_adv: bool = True,
        eps_adv: float = 1e-8,
    ) -> None:
        """
        Compute GAE and target returns for both agent types.
        """
        gamma_t = float(gamma)
        lam_t = float(lam)

        # Initialize for all agents
        gae_next_std = torch.zeros((self.E, self.N, 1), device=self.device, dtype=torch.float32)
        gae_next_sbs = torch.zeros((self.E, 1, 1), device=self.device, dtype=torch.float32)
        V_next = torch.zeros((self.E, self.N_total, 1), device=self.device, dtype=torch.float32)

        for t in reversed(range(self.T)):
            done_t = self.done[t].view(self.E, 1, 1)  # [E,1,1]
            nonterminal = 1.0 - done_t

            r_t = self.r[t].view(self.E, 1, 1).expand(self.E, self.N_total, 1)  # [E,N_total,1]
            V_t = self.V[t]  # [E,N_total,1]

            # Split V_t for standard agents and SBS
            V_std = V_t[:, :self.N, :]  # [E,N,1]
            V_sbs = V_t[:, self.N:self.N+1, :]  # [E,1,1] (squeeze to [E,1])

            # Delta for standard agents
            delta_std = r_t[:, :self.N, :] + gamma_t * V_next[:, :self.N, :] * nonterminal - V_std
            gae_std = delta_std + gamma_t * lam_t * nonterminal * gae_next_std

            # Delta for SBS (using shared reward)
            r_sbs = r_t[:, self.N:self.N+1, :]  # [E,1,1]
            delta_sbs = r_sbs + gamma_t * V_next[:, self.N:self.N+1, :] * nonterminal - V_sbs
            gae_sbs = delta_sbs + gamma_t * lam_t * nonterminal * gae_next_sbs

            # Store advantages and returns
            self.adv_std[t].copy_(gae_std.squeeze(-1))  # [E,N]
            self.adv_sbs[t].copy_(gae_sbs.squeeze(-1).squeeze(-1))  # [E]

            # Compute returns: G = A + V
            ret_std = gae_std + V_std  # [E,N,1]
            ret_sbs = gae_sbs + V_sbs  # [E,1,1]
            self.ret[t] = torch.cat([ret_std, ret_sbs], dim=1)  # [E,N_total,1]

            gae_next_std = gae_std
            gae_next_sbs = gae_sbs
            V_next = V_t

        if normalize_adv:
            # Normalize advantages separately
            adv_std_flat = self.adv_std.reshape(self.T * self.E * self.N)
            mean_std = adv_std_flat.mean()
            var_std = adv_std_flat.var(unbiased=False)
            self.adv_std = (self.adv_std - mean_std) / torch.sqrt(var_std + eps_adv)

            adv_sbs_flat = self.adv_sbs.reshape(self.T * self.E)
            mean_sbs = adv_sbs_flat.mean()
            var_sbs = adv_sbs_flat.var(unbiased=False)
            self.adv_sbs = (self.adv_sbs - mean_sbs) / torch.sqrt(var_sbs + eps_adv)

    def to_flat(self) -> MixedEpisodeBatch:
        """Flatten (T,E) -> B' where B' = T*E for PPO updates."""
        T, E = self.T, self.E
        Bp = T * E

        X = self.X.reshape(Bp, self.N_total, self.D_obs)
        A = self.A.reshape(Bp, self.N_total, self.N_total)
        C = self.C.reshape(Bp, self.N, self.M)
        P = self.P.reshape(Bp, self.N, self.M)
        B_sbs = self.B_sbs.reshape(Bp, self.K)
        logp_std = self.logp_std.reshape(Bp, self.N)
        logp_sbs = self.logp_sbs.reshape(Bp)
        V_old = self.V.reshape(Bp, self.N_total, 1)
        adv_std = self.adv_std.reshape(Bp, self.N)
        adv_sbs = self.adv_sbs.reshape(Bp)
        ret = self.ret.reshape(Bp, self.N_total, 1)
        done = self.done.reshape(Bp)

        return MixedEpisodeBatch(
            X=X, A=A, C=C, P=P, B_sbs=B_sbs,
            logp_std=logp_std, logp_sbs=logp_sbs,
            V_old=V_old, adv_std=adv_std, adv_sbs=adv_sbs,
            ret=ret, done=done,
        )

    def minibatches(
        self,
        minibatch_size: int,
        shuffle: bool = True,
        generator: Optional[torch.Generator] = None,
    ) -> Iterator[Tuple[torch.Tensor, MixedEpisodeBatch]]:
        """Yield (indices, MixedEpisodeBatch slice) with indices over B' = T*E."""
        batch = self.to_flat()
        Bp = batch.X.shape[0]
        mb = int(minibatch_size)
        if mb <= 0:
            raise ValueError(f"minibatch_size must be positive, got {mb}")

        if shuffle:
            idx = torch.randperm(Bp, device=self.device, generator=generator)
        else:
            idx = torch.arange(Bp, device=self.device)

        for start in range(0, Bp, mb):
            end = min(start + mb, Bp)
            sel = idx[start:end]
            yield sel, MixedEpisodeBatch(
                X=batch.X[sel],
                A=batch.A[sel],
                C=batch.C[sel],
                P=batch.P[sel],
                B_sbs=batch.B_sbs[sel],
                logp_std=batch.logp_std[sel],
                logp_sbs=batch.logp_sbs[sel],
                V_old=batch.V_old[sel],
                adv_std=batch.adv_std[sel],
                adv_sbs=batch.adv_sbs[sel],
                ret=batch.ret[sel],
                done=batch.done[sel] if batch.done is not None else None,
            )
