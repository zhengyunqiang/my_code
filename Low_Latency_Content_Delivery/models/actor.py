# models/actor.py
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, Literal, Optional, Sequence, Tuple

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.distributions import Categorical, Normal


InitMode = Literal["xavier", "orthogonal"]
ActName = Literal["relu", "elu", "gelu", "tanh", "silu"]


def _get_activation(name: ActName) -> nn.Module:
    if name == "relu":
        return nn.ReLU(inplace=True)
    if name == "elu":
        return nn.ELU(inplace=True)
    if name == "gelu":
        return nn.GELU()
    if name == "tanh":
        return nn.Tanh()
    if name == "silu":
        return nn.SiLU(inplace=True)
    raise ValueError(f"Unsupported activation: {name}")


def _init_linear_(m: nn.Module, mode: InitMode = "xavier") -> None:
    if isinstance(m, nn.Linear):
        if mode == "xavier":
            nn.init.xavier_uniform_(m.weight)
        elif mode == "orthogonal":
            nn.init.orthogonal_(m.weight)
        else:
            raise ValueError(f"Unsupported init mode: {mode}")
        if m.bias is not None:
            nn.init.zeros_(m.bias)


def logit(x: torch.Tensor) -> torch.Tensor:
    """
    logit(x) = log(x) - log(1-x), for x in (0,1)
    """
    return torch.log(x) - torch.log1p(-x)


@dataclass(frozen=True)
class ActorOutput:
    """
    Actor distribution parameters for a single agent.

    Attributes
    ----------
    logits : torch.Tensor
        Discrete logits for femtoCell selection, shape [B, M, K].
    mu : torch.Tensor
        Gaussian mean for pre-squash variable z, shape [B, M].
    std : torch.Tensor
        Gaussian std (>0) for pre-squash variable z, shape [B, M].
    """
    logits: torch.Tensor  # [B, M, K]
    mu: torch.Tensor      # [B, M]
    std: torch.Tensor     # [B, M] > 0


class TelecomHybridActor(nn.Module):
    """
    Hybrid Multi-Head Actor (Single Agent)

    Input
    -----
    h : [B, D_h]  (node embedding from shared GAT for one agent)

    Outputs (distribution parameters)
    -------------------------------
    logits : [B, M, K]    (Categorical over K femtoCells for each subchannel)
    mu     : [B, M]       (Normal mean for pre-squash variable z)
    std    : [B, M] > 0   (Normal std  for pre-squash variable z)

    Sampling
    --------
    Discrete (femtoCell selection):
      u_j ~ Categorical(logits_j)

    Continuous (Sigmoid-squashed Gaussian):
      z_j ~ Normal(mu_j, std_j)
      p_norm_j = sigmoid(z_j) in (0,1)
      p_j = P_max * p_norm_j in (0, P_max)

    Joint log-prob (PPO convention)
    -------------------------------
      log pi(a|s) = sum_{j=1..M} ( log pi(u_j|s) + log pi(p_j|s) )

    Continuous log pi(p|s) uses change-of-variables:
      p_norm = p / P_max
      z = logit(p_norm)
      log pi(p|s) = log N(z; mu, std) - log P_max - log(p_norm*(1-p_norm))
    """

    def __init__(
        self,
        input_dim: int,                 # D_h
        num_subchannels: int,           # M
        num_femtoCell: int,             # K
        max_power: float,               # P_max
        trunk_layers: Sequence[int] = (256, 256),
        activation: ActName = "relu",
        dropout: float = 0.0,
        min_std: float = 1e-3,
        eps: float = 1e-6,
        init_mode: InitMode = "xavier",
    ) -> None:
        super().__init__()
        if input_dim <= 0:
            raise ValueError(f"input_dim must be positive, got {input_dim}")
        if num_subchannels <= 0:
            raise ValueError(f"num_subchannels (M) must be positive, got {num_subchannels}")
        if num_femtoCell <= 1:
            raise ValueError(f"num_femtoCell (K) must be >= 2, got {num_femtoCell}")
        if max_power <= 0:
            raise ValueError(f"max_power (P_max) must be > 0, got {max_power}")
        if any(h <= 0 for h in trunk_layers):
            raise ValueError(f"trunk_layers must be positive ints, got {trunk_layers}")
        if not (0.0 <= dropout < 1.0):
            raise ValueError(f"dropout must be in [0,1), got {dropout}")
        if min_std <= 0:
            raise ValueError(f"min_std must be > 0, got {min_std}")
        if eps <= 0:
            raise ValueError(f"eps must be > 0, got {eps}")

        self.D_h = int(input_dim)
        self.M = int(num_subchannels)
        self.K = int(num_femtoCell)
        self.Pmax = float(max_power)
        self.min_std = float(min_std)
        self.eps = float(eps)

        act = _get_activation(activation)

        # Trunk: MLP
        dims: Tuple[int, ...] = (self.D_h,) + tuple(int(x) for x in trunk_layers)
        layers = []
        for in_dim, out_dim in zip(dims[:-1], dims[1:]):
            layers.append(nn.Linear(in_dim, out_dim))
            layers.append(act)
            if dropout > 0.0:
                layers.append(nn.Dropout(p=float(dropout)))
        self.trunk = nn.Sequential(*layers)
        trunk_out = dims[-1]

        # Heads
        self.logits_head = nn.Linear(trunk_out, self.M * self.K)
        self.mu_head = nn.Linear(trunk_out, self.M)
        self.log_std_head = nn.Linear(trunk_out, self.M)

        # Init
        self.apply(lambda m: _init_linear_(m, mode=init_mode))

    def forward(self, h: torch.Tensor) -> ActorOutput:
        """
        Parameters
        ----------
        h : torch.Tensor
            Node embedding, shape [B, D_h].

        Returns
        -------
        ActorOutput
            logits [B,M,K], mu [B,M], std [B,M] (>0)
        """
        if h.ndim != 2:
            raise ValueError(f"h must be rank-2 [B,D_h], got shape {tuple(h.shape)}")
        B, Dh = h.shape
        if Dh != self.D_h:
            raise ValueError(f"Expected h last dim D_h={self.D_h}, got {Dh}")

        t = self.trunk(h)  # [B, D_a]
        logits = self.logits_head(t).view(B, self.M, self.K)  # [B,M,K]
        mu = self.mu_head(t)                                  # [B,M]
        log_std = self.log_std_head(t)                        # [B,M]
        std = F.softplus(log_std) + self.min_std              # [B,M] > 0
        return ActorOutput(logits=logits, mu=mu, std=std)

    def _discrete_dist(self, logits: torch.Tensor) -> Categorical:
        # Categorical supports batch shape [B,M]
        return Categorical(logits=logits)

    def _continuous_dist(self, mu: torch.Tensor, std: torch.Tensor) -> Normal:
        # Normal supports batch shape [B,M]
        return Normal(mu, std)

    def _power_from_z(self, z: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor]:
        """
        Map pre-squash z -> (p_norm, p) with sigmoid + scaling.

        Returns
        -------
        p_norm : (0,1), shape [B,M]
        p      : (0,Pmax), shape [B,M]
        """
        p_norm = torch.sigmoid(z)
        p = p_norm * self.Pmax
        return p_norm, p

    def _log_prob_power_from_z(
        self, z: torch.Tensor, p_norm: torch.Tensor, dist_z: Normal
    ) -> torch.Tensor:
        """
        Given sampled z and corresponding p_norm = sigmoid(z), compute log pi(p|s)
        using change-of-variables:
          log pi(p|s) = log N(z;mu,std) - log Pmax - log(p_norm*(1-p_norm))
        """
        logp_z = dist_z.log_prob(z)  # [B,M]
        log_det = -math.log(self.Pmax) - torch.log(p_norm * (1.0 - p_norm) + self.eps)
        return logp_z + log_det  # [B,M]

    def _log_prob_power_from_p(
        self, power: torch.Tensor, mu: torch.Tensor, std: torch.Tensor
    ) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        """
        Given power p in (0,Pmax), compute:
          p_norm = clamp(p/Pmax, eps, 1-eps)
          z = logit(p_norm)
          log pi(p|s) = log N(z;mu,std) - log Pmax - log(p_norm*(1-p_norm))

        Returns
        -------
        logp_p : [B,M]
        p_norm : [B,M]
        z      : [B,M]
        """
        p_norm = (power / self.Pmax).clamp(self.eps, 1.0 - self.eps)
        z = logit(p_norm)
        dist_z = Normal(mu, std)
        logp_z = dist_z.log_prob(z)
        log_det = -math.log(self.Pmax) - torch.log(p_norm * (1.0 - p_norm) + self.eps)
        logp_p = logp_z + log_det
        return logp_p, p_norm, z

    @torch.no_grad()
    def get_action(self, h: torch.Tensor) -> Dict[str, torch.Tensor]:
        """
        Sample hybrid actions for rollout.

        Returns
        -------
        dict with keys:
          users   : [B,M] int64
          power   : [B,M] float
          logp    : [B]   float  (joint log-prob)
          entropy : [B]   float  (discrete entropy + normal entropy, summed over M)
        """
        out = self.forward(h)

        # Discrete: users
        dist_u = self._discrete_dist(out.logits)
        users = dist_u.sample()                 # [B,M]
        logp_u = dist_u.log_prob(users)         # [B,M]
        ent_u = dist_u.entropy()                # [B,M]

        # Continuous: power via sigmoid-squashed Gaussian
        dist_z = self._continuous_dist(out.mu, out.std)
        z = dist_z.rsample()                    # [B,M]
        p_norm, power = self._power_from_z(z)   # [B,M], [B,M]
        logp_p = self._log_prob_power_from_z(z, p_norm, dist_z)  # [B,M]

        # Joint log-prob summed over subchannels
        logp = (logp_u + logp_p).sum(dim=-1)    # [B]

        # Entropy bonus:
        #   - Discrete entropy is exact
        #   - Continuous uses pre-squash Normal entropy (common stable approximation)
        ent_p = dist_z.entropy()                # [B,M]
        entropy = (ent_u + ent_p).sum(dim=-1)   # [B]

        return {"users": users, "power": power, "logp": logp, "entropy": entropy}

    def evaluate(
        self,
        h: torch.Tensor,
        users: torch.Tensor,
        power: torch.Tensor,
    ) -> Dict[str, torch.Tensor]:
        """
        Re-evaluate log-prob and entropy for PPO update under current policy.

        Parameters
        ----------
        h : [B, D_h]
        users : [B, M]  (int indices)
        power : [B, M]  (float in (0,Pmax))  - stored rollout action

        Returns
        -------
        dict with keys:
          logp_new   : [B]
          entropy    : [B]
          logp_u_sum : [B] (optional decomposition)
          logp_p_sum : [B] (optional decomposition)
        """
        if users.ndim != 2:
            raise ValueError(f"users must be rank-2 [B,M], got shape {tuple(users.shape)}")
        if power.ndim != 2:
            raise ValueError(f"power must be rank-2 [B,M], got shape {tuple(power.shape)}")

        out = self.forward(h)
        B = out.mu.shape[0]

        if users.shape[0] != B or users.shape[1] != self.M:
            raise ValueError(
                f"users shape mismatch: expected [B={B}, M={self.M}], got {tuple(users.shape)}"
            )
        if power.shape[0] != B or power.shape[1] != self.M:
            raise ValueError(
                f"power shape mismatch: expected [B={B}, M={self.M}], got {tuple(power.shape)}"
            )

        # Discrete
        dist_u = self._discrete_dist(out.logits)
        logp_u = dist_u.log_prob(users)         # [B,M]
        ent_u = dist_u.entropy()                # [B,M]

        # Continuous (invert power -> z)
        logp_p, _, _ = self._log_prob_power_from_p(power, out.mu, out.std)  # [B,M]
        dist_z = self._continuous_dist(out.mu, out.std)
        ent_p = dist_z.entropy()                # [B,M]

        logp_new = (logp_u + logp_p).sum(dim=-1)  # [B]
        entropy = (ent_u + ent_p).sum(dim=-1)     # [B]

        return {
            "logp_new": logp_new,
            "entropy": entropy,
            "logp_u_sum": logp_u.sum(dim=-1),
            "logp_p_sum": logp_p.sum(dim=-1),
        }
