# buffers/rollout_buffer.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterator, Optional, Tuple

import torch


@dataclass
class EpisodeBatch:
    """
    Flattened batch (B' = T*E) for PPO update.
    Shapes:
      X      : [B', N, D_obs]
      A      : [B', N, N]
      C      : [B', N, M]        compartments (int64)
      P      : [B', N, M]        power (float)
      logp   : [B', N]           old joint log-prob per agent
      V_old  : [B', N, 1]        old value prediction (optional usage)
      adv    : [B', N]           GAE advantage
      ret    : [B', N, 1]        target return (G)
      done   : [B'] or [B', 1]   optional mask; in fixed-horizon typically not needed
    """
    X: torch.Tensor
    A: torch.Tensor
    C: torch.Tensor
    P: torch.Tensor
    logp: torch.Tensor
    V_old: torch.Tensor
    adv: torch.Tensor
    ret: torch.Tensor
    done: Optional[torch.Tensor] = None


class RolloutBufferEpisode:
    """
    Rollout buffer storing ONE full episode for E parallel envs, fixed horizon T.

    Storage shapes (time-major):
      X    : [T, E, N, D_obs]
      A    : [T, E, N, N]
      C    : [T, E, N, M]
      P    : [T, E, N, M]
      logp : [T, E, N]
      V    : [T, E, N, 1]
      r    : [T, E]        (env-level sparse reward; only last step non-zero)
      done : [T, E]        (env-level done)
      adv  : [T, E, N]
      ret  : [T, E, N, 1]
    """

    def __init__(
        self,
        T: int,
        E: int,
        N: int,
        M: int,
        D_obs: int,
        device: torch.device,
        dtype_obs: torch.dtype = torch.float32,
        dtype_adj: torch.dtype = torch.float32,
        dtype_power: torch.dtype = torch.float32,
    ) -> None:
        self.T = int(T)
        self.E = int(E)
        self.N = int(N)
        self.M = int(M)
        self.D_obs = int(D_obs)
        self.device = device

        self.X = torch.zeros((T, E, N, D_obs), device=device, dtype=dtype_obs)
        self.A = torch.zeros((T, E, N, N), device=device, dtype=dtype_adj)
        self.C = torch.zeros((T, E, N, M), device=device, dtype=torch.long)
        self.P = torch.zeros((T, E, N, M), device=device, dtype=dtype_power)
        self.logp = torch.zeros((T, E, N), device=device, dtype=torch.float32)
        self.V = torch.zeros((T, E, N, 1), device=device, dtype=torch.float32)

        self.r = torch.zeros((T, E), device=device, dtype=torch.float32)
        self.done = torch.zeros((T, E), device=device, dtype=torch.float32)  # store as float mask {0,1}

        self.adv = torch.zeros((T, E, N), device=device, dtype=torch.float32)
        self.ret = torch.zeros((T, E, N, 1), device=device, dtype=torch.float32)

        self._t = 0  # write pointer

    def reset_ptr(self) -> None:
        self._t = 0

    @property
    def is_full(self) -> bool:
        return self._t >= self.T

    def store_step(
        self,
        X_t: torch.Tensor,          # [E,N,D_obs]
        A_t: torch.Tensor,          # [E,N,N]
        C_t: torch.Tensor,          # [E,N,M]
        P_t: torch.Tensor,          # [E,N,M]
        logp_t: torch.Tensor,       # [E,N]
        V_t: torch.Tensor,          # [E,N,1]
        done_t: torch.Tensor,       # [E]
        r_t: Optional[torch.Tensor] = None,  # [E] optional (default zeros; set final later)
    ) -> None:
        if self.is_full:
            raise RuntimeError("Buffer is full. Create a new buffer or reset_ptr().")

        t = self._t
        self.X[t].copy_(X_t)
        self.A[t].copy_(A_t)
        self.C[t].copy_(C_t)
        self.P[t].copy_(P_t)
        self.logp[t].copy_(logp_t)
        self.V[t].copy_(V_t)
        self.done[t].copy_(done_t.to(self.done.dtype))

        if r_t is not None:
            self.r[t].copy_(r_t.to(self.r.dtype))
        else:
            # default sparse reward: keep zero; final step will be set after episode ends
            pass

        self._t += 1

    def set_final_reward(self, R_final: torch.Tensor) -> None:
        """
        Write terminal reward to last time step: r[T-1] = R_final, where R_final is [E].
        """
        if self._t != self.T:
            raise RuntimeError(f"Episode not complete: ptr={self._t}, expected T={self.T}")
        self.r[self.T - 1].copy_(R_final.to(self.r.dtype))

    @torch.no_grad()
    def compute_gae_and_returns(
        self,
        gamma: float,
        lam: float,
        normalize_adv: bool = True,
        eps_adv: float = 1e-8,
    ) -> None:
        """
        Compute GAE and target returns using env-level reward r[t,e] broadcast to agents.

        Definitions:
          V_T^{(i)} = 0
          delta_t^{(i)} = r_t^{(i)} + gamma * V_{t+1}^{(i)} * (1-done_t) - V_t^{(i)}
          A_t^{(i)} = delta_t^{(i)} + gamma*lam*(1-done_t)*A_{t+1}^{(i)}
          G_t^{(i)} = A_t^{(i)} + V_t^{(i)}

        Shapes:
          done[t] is [E] -> broadcast to [E,N,1]
          r[t] is [E]    -> broadcast to [E,N,1]
        """
        gamma_t = float(gamma)
        lam_t = float(lam)

        gae_next = torch.zeros((self.E, self.N, 1), device=self.device, dtype=torch.float32)
        V_next = torch.zeros((self.E, self.N, 1), device=self.device, dtype=torch.float32)  # V_T = 0

        for t in reversed(range(self.T)):
            done_t = self.done[t].view(self.E, 1, 1)  # [E,1,1]
            nonterminal = 1.0 - done_t                # [E,1,1]

            r_t = self.r[t].view(self.E, 1, 1).expand(self.E, self.N, 1)  # [E,N,1]
            V_t = self.V[t]  # [E,N,1]

            delta = r_t + gamma_t * V_next * nonterminal - V_t
            gae = delta + gamma_t * lam_t * nonterminal * gae_next

            self.adv[t].copy_(gae.squeeze(-1))            # [E,N]
            self.ret[t].copy_(gae + V_t)                  # [E,N,1]

            gae_next = gae
            V_next = V_t

        if normalize_adv:
            adv_flat = self.adv.reshape(self.T * self.E * self.N)
            mean = adv_flat.mean()
            var = adv_flat.var(unbiased=False)
            self.adv = (self.adv - mean) / torch.sqrt(var + eps_adv)

    def to_flat(self) -> EpisodeBatch:
        """
        Flatten (T,E) -> B' where B' = T*E for PPO updates.
        """
        T, E, N = self.T, self.E, self.N
        Bp = T * E

        X = self.X.reshape(Bp, N, self.D_obs)
        A = self.A.reshape(Bp, N, N)
        C = self.C.reshape(Bp, N, self.M)
        P = self.P.reshape(Bp, N, self.M)
        logp = self.logp.reshape(Bp, N)
        V_old = self.V.reshape(Bp, N, 1)
        adv = self.adv.reshape(Bp, N)
        ret = self.ret.reshape(Bp, N, 1)
        done = self.done.reshape(Bp)  # optional; in fixed-horizon mostly unused

        return EpisodeBatch(X=X, A=A, C=C, P=P, logp=logp, V_old=V_old, adv=adv, ret=ret, done=done)

    def minibatches(
        self,
        minibatch_size: int,
        shuffle: bool = True,
        generator: Optional[torch.Generator] = None,
    ) -> Iterator[Tuple[torch.Tensor, EpisodeBatch]]:
        """
        Yield (indices, EpisodeBatch slice) with indices over B' = T*E.
        """
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
            yield sel, EpisodeBatch(
                X=batch.X[sel],
                A=batch.A[sel],
                C=batch.C[sel],
                P=batch.P[sel],
                logp=batch.logp[sel],
                V_old=batch.V_old[sel],
                adv=batch.adv[sel],
                ret=batch.ret[sel],
                done=batch.done[sel] if batch.done is not None else None,
            )
