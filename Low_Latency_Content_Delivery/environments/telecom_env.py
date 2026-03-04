"""
Telecom vector environment for heterogeneous multi-agent RL.

Agents:
  - N BaseStation agents: mixed action (carriage selection + power)
  - 1 SBS agent: continuous action (bandwidth allocation)
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Tuple

import torch

from .channel_model import ChannelConfig, create_channel_model


@dataclass
class TelecomEnvConfig:
    """Configuration for the telecom environment."""
    # Environment
    E: int = 8
    T: int = 40

    # Network topology
    num_bases: int = 2
    num_cars: int = 2
    users_per_car: int = 10

    # Resource allocation
    num_subchannels: int = 5
    num_fap: int = 10

    # Physical parameters
    coverage: float = 250
    speed: float = 10
    max_power: float = 100
    max_bandwidth: float = 10

    # Channel parameters
    B_TBS: float = 10
    delta_0: float = 1e-9
    K_gain: float = 1
    gamma: float = 2
    timeslot: float = 0.01

    # Data parameters
    max_rate: float = 100
    mean_demand: float = 8
    std_demand: float = 3

    # Observation space
    D_obs: int = 32

    # Optional realistic channel
    use_realistic_channel: bool = False
    channel_fc: float = 2.1
    channel_speed_kmh: float = 300.0
    channel_fading_model: str = "rician"

    @property
    def N(self) -> int:
        return self.num_bases

    @property
    def N_total(self) -> int:
        return self.num_bases + 1

    @property
    def M(self) -> int:
        return self.num_subchannels

    @property
    def K(self) -> int:
        return self.num_fap


class TelecomVectorEnv:
    """Vectorized telecom environment compatible with MixedPPOTrainer."""

    def __init__(self, cfg: TelecomEnvConfig, device: torch.device) -> None:
        self.cfg = cfg
        self.device = device
        self.N_total = cfg.N_total

        # Base stations laid out along track.
        if cfg.num_bases == 1:
            base_locations = torch.tensor([250.0], dtype=torch.float32, device=device)
        else:
            base_locations = torch.linspace(
                250.0,
                250.0 + 500.0 * (cfg.num_bases - 1),
                steps=cfg.num_bases,
                dtype=torch.float32,
                device=device,
            )
        self.base_locations = base_locations

        # Optional realistic channel model.
        self.channel_model = None
        if cfg.use_realistic_channel:
            ch_cfg = ChannelConfig(
                fc=cfg.channel_fc,
                speed_kmh=cfg.channel_speed_kmh,
                fading_model=cfg.channel_fading_model,
                gamma=cfg.gamma,
            )
            self.channel_model = create_channel_model(ch_cfg, device)

        # Runtime state.
        self._t = 0
        self.car_positions: torch.Tensor | None = None
        self.distances_bs_car: torch.Tensor | None = None
        self.coverage_status: torch.Tensor | None = None

        # User-level data demands.
        self.initial_user_data: torch.Tensor | None = None      # [E,C,U]
        self.remaining_user_data: torch.Tensor | None = None    # [E,C,U]
        self.initial_data: torch.Tensor | None = None           # [E,C]
        self.remaining_data: torch.Tensor | None = None         # [E,C]

        # Episode histories (for evaluator and terminal score).
        self.external_rate_history: torch.Tensor | None = None  # [T,E,C]
        self.power_history: torch.Tensor | None = None          # [T,E,N,M]
        self.bandwidth_history: torch.Tensor | None = None      # [T,E,K]

    def reset(self) -> Tuple[torch.Tensor, torch.Tensor]:
        """Reset environment and return (X, A)."""
        self._t = 0
        E, C, U = self.cfg.E, self.cfg.num_cars, self.cfg.users_per_car

        carriage_init = torch.tensor(
            [-i * 30.0 for i in range(C)],
            dtype=torch.float32,
            device=self.device,
        ).expand(E, -1)
        self.car_positions = carriage_init + torch.rand(E, C, device=self.device) * 10.0

        # Per-user demand is sampled; carriage total is the sum over users.
        user_mean = self.cfg.mean_demand / max(U, 1)
        user_std = self.cfg.std_demand / max(U, 1)
        self.initial_user_data = torch.normal(
            mean=user_mean,
            std=user_std,
            size=(E, C, U),
            device=self.device,
        ).clamp(min=0.1)
        self.remaining_user_data = self.initial_user_data.clone()
        self.initial_data = self.initial_user_data.sum(dim=2)
        self.remaining_data = self.remaining_user_data.sum(dim=2)

        self._update_distances()
        self.coverage_status = (self.distances_bs_car <= self.cfg.coverage).to(torch.float32)

        self.external_rate_history = torch.zeros(
            self.cfg.T, E, C, device=self.device, dtype=torch.float32
        )
        self.power_history = torch.zeros(
            self.cfg.T, E, self.cfg.N, self.cfg.M, device=self.device, dtype=torch.float32
        )
        self.bandwidth_history = torch.zeros(
            self.cfg.T, E, self.cfg.K, device=self.device, dtype=torch.float32
        )

        return self._get_observations(), self._get_adjacency()

    def step(
        self,
        action_dict: Dict[str, torch.Tensor],
    ) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor, Dict]:
        """Execute one step."""
        self._t += 1
        t_idx = self._t - 1

        compartments = action_dict["compartments"]  # [E,N,M]
        power = action_dict["power"]                # [E,N,M]
        bandwidth = action_dict["bandwidth"]        # [E,K]

        power = torch.clamp(power, 0.0, self.cfg.max_power)
        bandwidth = torch.clamp(bandwidth, 0.0, self.cfg.max_bandwidth)

        # Carriage-level external total rates.
        data_rate = self._calculate_data_rate(compartments, power, bandwidth)  # [E,C]
        self.external_rate_history[t_idx].copy_(data_rate)
        self.power_history[t_idx].copy_(power)
        self.bandwidth_history[t_idx].copy_(bandwidth)

        # Allocate external capacity to users (internal service rates).
        served_amount = data_rate * float(self.cfg.timeslot)  # [E,C]
        self._allocate_to_users(served_amount)

        # Move train and refresh geometry.
        self.car_positions = self.car_positions + self.cfg.speed
        self._update_distances()
        self.coverage_status = (self.distances_bs_car <= self.cfg.coverage).to(torch.float32)

        done = self._check_done()
        X_next = self._get_observations()
        A_next = self._get_adjacency()

        info: Dict[str, torch.Tensor] = {}
        if done.any():
            info["S_final"] = self._calculate_terminal_score()

        return X_next, A_next, done, info

    def _update_distances(self) -> None:
        """Update distances between base stations and carriages."""
        self.distances_bs_car = torch.abs(
            self.car_positions.unsqueeze(1) - self.base_locations.view(1, -1, 1)
        )  # [E,N,C]

    def _calculate_data_rate(
        self,
        compartments: torch.Tensor,  # [E,N,M]
        power: torch.Tensor,         # [E,N,M]
        bandwidth: torch.Tensor,     # [E,K]
    ) -> torch.Tensor:
        """Compute external aggregate rate per carriage [E,C]."""
        E, N, M = compartments.shape
        C = self.cfg.num_cars
        env_ids = torch.arange(E, device=self.device)

        data_rate = torch.zeros(E, C, device=self.device, dtype=torch.float32)

        # Map SBS bandwidth to carriages (simple deterministic FAP->carriage map).
        carriage_extra_bw = torch.zeros(E, C, device=self.device, dtype=torch.float32)
        for k in range(self.cfg.K):
            car_idx = k % C
            carriage_extra_bw[:, car_idx] += bandwidth[:, k]

        # Channel gains for each selected link.
        channel_gain = torch.zeros(E, N, M, device=self.device, dtype=torch.float32)
        for n in range(N):
            for m in range(M):
                car_idx = compartments[:, n, m].long()
                distance = self.distances_bs_car[env_ids, n, car_idx]
                if self.channel_model is None:
                    gain = self.cfg.K_gain / (distance.pow(self.cfg.gamma) + 1e-6)
                else:
                    gain = self.channel_model.compute_gain(distance, timestep=self._t)
                channel_gain[:, n, m] = gain.to(torch.float32)

        for n in range(N):
            for m in range(M):
                car_idx = compartments[:, n, m].long()
                p_signal = power[:, n, m] * channel_gain[:, n, m]

                interference = torch.zeros(E, device=self.device, dtype=torch.float32)
                for other_n in range(N):
                    if other_n == n:
                        continue
                    other_car = compartments[:, other_n, m].long()
                    other_dist = self.distances_bs_car[env_ids, other_n, other_car]
                    if self.channel_model is None:
                        other_gain = self.cfg.K_gain / (other_dist.pow(self.cfg.gamma) + 1e-6)
                    else:
                        other_gain = self.channel_model.compute_gain(other_dist, timestep=self._t)
                    interference += power[:, other_n, m] * other_gain.to(torch.float32)

                # SBS bandwidth contributes as additive spectrum for selected carriage.
                extra_bw = carriage_extra_bw[env_ids, car_idx] / max(float(M), 1.0)
                subchannel_bw = self.cfg.B_TBS + extra_bw
                noise = subchannel_bw * self.cfg.delta_0

                snr = p_signal / (interference + noise + 1e-9)
                rate = subchannel_bw * torch.log2(1.0 + snr)
                rate = torch.clamp(rate, min=0.0, max=self.cfg.max_rate)

                data_rate.scatter_add_(1, car_idx.unsqueeze(1), rate.unsqueeze(1))

        return data_rate

    def _allocate_to_users(self, served_amount: torch.Tensor) -> None:
        """Allocate carriage-level served amount to users with remaining demand."""
        E, C = served_amount.shape
        U = self.cfg.users_per_car

        for e in range(E):
            for c in range(C):
                remaining = float(served_amount[e, c].item())
                if remaining <= 0:
                    continue

                for _ in range(U):
                    rem_vec = self.remaining_user_data[e, c, :]
                    active_mask = rem_vec > 1e-8
                    active_count = int(active_mask.sum().item())
                    if active_count == 0 or remaining <= 1e-8:
                        break

                    share = remaining / active_count
                    alloc = torch.where(active_mask, torch.full_like(rem_vec, share), torch.zeros_like(rem_vec))
                    alloc = torch.minimum(alloc, rem_vec)
                    self.remaining_user_data[e, c, :] = rem_vec - alloc
                    remaining -= float(alloc.sum().item())

        self.remaining_data = self.remaining_user_data.sum(dim=2)

    def _check_done(self) -> torch.Tensor:
        """Done if all users served or max horizon reached."""
        E = self.cfg.E
        data_done = (self.remaining_user_data <= 1e-3).all(dim=(1, 2))  # [E]
        time_done = torch.full((E,), self._t >= self.cfg.T, device=self.device, dtype=torch.bool)
        return (data_done | time_done).to(torch.float32)

    def _calculate_terminal_score(self) -> torch.Tensor:
        """
        Terminal objective S_final to minimize.

        Lower is better:
          - less remaining data
          - fewer unfinished users
          - lower average power/bandwidth use
          - fewer coverage violations
        """
        E = self.cfg.E
        valid_steps = max(self._t, 1)

        remaining_penalty = self.remaining_data.sum(dim=1) * 10.0
        unfinished_users = (self.remaining_user_data > 1e-3).to(torch.float32).sum(dim=(1, 2))
        user_penalty = unfinished_users * 2.0

        avg_power = self.power_history[:valid_steps].mean(dim=(0, 2, 3))
        avg_bandwidth = self.bandwidth_history[:valid_steps].mean(dim=(0, 2))
        power_penalty = avg_power * 0.1
        bandwidth_penalty = avg_bandwidth * 0.05

        uncovered = (self.coverage_status.sum(dim=1) == 0).to(torch.float32)  # [E,C]
        coverage_penalty = uncovered.sum(dim=1) * 100.0

        return remaining_penalty + user_penalty + power_penalty + bandwidth_penalty + coverage_penalty

    def _get_observations(self) -> torch.Tensor:
        """Build node observations [E,N_total,D_obs]."""
        E, D_obs = self.cfg.E, self.cfg.D_obs
        X = torch.zeros(E, self.N_total, D_obs, device=self.device, dtype=torch.float32)

        norm_pos = self.car_positions / 1000.0
        norm_data = self.remaining_data / (self.cfg.mean_demand + 1e-6)
        norm_dist = self.distances_bs_car / 1000.0

        user_mean = self.remaining_user_data.mean(dim=2) / (self.cfg.mean_demand + 1e-6)
        user_max = self.remaining_user_data.max(dim=2).values / (self.cfg.mean_demand + 1e-6)
        user_done_ratio = (self.remaining_user_data <= 1e-3).to(torch.float32).mean(dim=2)

        # BS node features.
        for n in range(self.cfg.N):
            feat = torch.cat(
                [
                    norm_dist[:, n, :],          # [E,C]
                    norm_data,                   # [E,C]
                    self.coverage_status[:, n, :],  # [E,C]
                    user_mean,                   # [E,C]
                    user_max,                    # [E,C]
                    user_done_ratio,             # [E,C]
                ],
                dim=1,
            )
            width = min(D_obs, feat.shape[1])
            X[:, n, :width] = feat[:, :width]

        # SBS node features.
        sbs_feat = torch.cat(
            [
                norm_data.mean(dim=1, keepdim=True),      # [E,1]
                user_done_ratio.mean(dim=1, keepdim=True),  # [E,1]
                norm_pos,                                 # [E,C]
                norm_data,                                # [E,C]
            ],
            dim=1,
        )
        width = min(D_obs, sbs_feat.shape[1])
        X[:, self.cfg.N, :width] = sbs_feat[:, :width]

        return X

    def _get_adjacency(self) -> torch.Tensor:
        """Build adjacency [E,N_total,N_total]."""
        E, N, N_total = self.cfg.E, self.cfg.N, self.N_total
        A = torch.eye(N_total, device=self.device, dtype=torch.float32).unsqueeze(0).repeat(E, 1, 1)

        # BS-BS fully connected.
        for i in range(N):
            for j in range(N):
                if i != j:
                    A[:, i, j] = 1.0

        # BS-SBS connectivity weighted by average coverage ratio.
        sbs_idx = N
        coverage_ratio = self.coverage_status.mean(dim=2)  # [E,N]
        for n in range(N):
            A[:, n, sbs_idx] = 0.5 + 0.5 * coverage_ratio[:, n]
            A[:, sbs_idx, n] = 0.5 + 0.5 * coverage_ratio[:, n]

        return A


def create_telecom_env(cfg: TelecomEnvConfig, device: torch.device) -> TelecomVectorEnv:
    """Factory function."""
    return TelecomVectorEnv(cfg=cfg, device=device)
