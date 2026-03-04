#!/usr/bin/env python
"""
Showcase script for LP evaluator with per-timeslot vectors.

What it prints (display-friendly):
  1) External total rate vector per carriage (each timeslot)
  2) LP solution vector per carriage (sum of user allocations each timeslot)
  3) User demand vector and delivered-data checks
  4) Episode-level minimum completion slots
"""
from __future__ import annotations

import argparse
import json
from typing import Dict

import numpy as np
import torch

from environments import TelecomEnvConfig, create_telecom_env
from utils.slot_evaluator import EpisodeSlotEvaluator


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="LP showcase for telecom environment")
    p.add_argument("--episodes", type=int, default=1, help="number of episodes to run")
    p.add_argument("--t", type=int, default=200, help="episode timeslots")
    p.add_argument("--num-envs", type=int, default=1, help="parallel env count (建议展示用 1)")
    p.add_argument("--show-env-index", type=int, default=0, help="which env index to print in detail")
    p.add_argument("--num-bases", type=int, default=2, help="base station agents")
    p.add_argument("--num-cars", type=int, default=2, help="carriage count")
    p.add_argument("--users-per-car", type=int, default=10, help="users in each carriage")
    p.add_argument("--num-subchannels", type=int, default=3, help="subchannels per BS")
    p.add_argument("--num-fap", type=int, default=5, help="SBS FAP count")
    p.add_argument("--mean-demand", type=float, default=127.0, help="carriage-level mean demand")
    p.add_argument("--std-demand", type=float, default=8.0, help="carriage-level demand std")
    p.add_argument("--seed", type=int, default=42, help="random seed")
    p.add_argument(
        "--print-full-user-matrix",
        action="store_true",
        help="print full [U,T] LP user allocation matrix (very long output)",
    )
    return p.parse_args()


def _as_list(x: np.ndarray, ndigits: int = 4) -> list[float]:
    return np.round(x.astype(np.float64), ndigits).tolist()


def _action_policy(env_cfg: TelecomEnvConfig, step_idx: int, device: torch.device) -> Dict[str, torch.Tensor]:
    """
    Deterministic heuristic action policy for stable demo traces.
    """
    E, N, M, C, K = env_cfg.E, env_cfg.N, env_cfg.M, env_cfg.num_cars, env_cfg.K

    # Alternating carriage assignment pattern over time/subchannels.
    compartments = torch.zeros((E, N, M), device=device, dtype=torch.long)
    for n in range(N):
        for m in range(M):
            compartments[:, n, m] = (step_idx + n + m) % C

    # High but bounded power with light oscillation.
    base_power = 0.78 + 0.18 * np.sin(step_idx / 12.0)
    power = torch.full((E, N, M), float(base_power * env_cfg.max_power), device=device, dtype=torch.float32)
    power = torch.clamp(power, 0.0, env_cfg.max_power)

    # SBS bandwidth also oscillates a bit for richer vectors.
    bw_base = 0.62 + 0.22 * np.cos(step_idx / 18.0)
    bandwidth = torch.full((E, K), float(bw_base * env_cfg.max_bandwidth), device=device, dtype=torch.float32)
    bandwidth = torch.clamp(bandwidth, 0.0, env_cfg.max_bandwidth)

    return {
        "compartments": compartments,
        "power": power,
        "bandwidth": bandwidth,
    }


def main() -> None:
    args = parse_args()
    if args.episodes <= 0:
        raise ValueError(f"--episodes must be > 0, got {args.episodes}")
    torch.manual_seed(args.seed)
    np.random.seed(args.seed)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    env_cfg = TelecomEnvConfig(
        E=args.num_envs,
        T=args.t,
        num_bases=args.num_bases,
        num_cars=args.num_cars,
        users_per_car=args.users_per_car,
        num_subchannels=args.num_subchannels,
        num_fap=args.num_fap,
        D_obs=32,
        max_power=100.0,
        max_bandwidth=10.0,
        mean_demand=args.mean_demand,
        std_demand=args.std_demand,
        use_realistic_channel=False,
    )
    env = create_telecom_env(env_cfg, device)
    evaluator = EpisodeSlotEvaluator()

    print("=" * 96)
    print("LP SHOWCASE REPORT".center(96))
    print("=" * 96)
    print(
        f"config: episodes={args.episodes}, T={env_cfg.T}, E={env_cfg.E}, C={env_cfg.num_cars}, "
        f"U/car={env_cfg.users_per_car}, mean_demand={env_cfg.mean_demand}, std_demand={env_cfg.std_demand}"
    )
    print("=" * 96)

    if not (0 <= args.show_env_index < env_cfg.E):
        raise ValueError(f"--show-env-index must be in [0, {env_cfg.E - 1}]")

    for ep in range(1, args.episodes + 1):
        X, A = env.reset()
        for t in range(env_cfg.T):
            act = _action_policy(env_cfg, t, device)
            X, A, done, info = env.step(act)
            if bool(done.all().item()):
                pass

        detail = evaluator.solve_episode_with_details(
            rate_history=env.external_rate_history,   # [T,E,C]
            user_demands=env.initial_user_data,       # [E,C,U]
            timeslot=float(env_cfg.timeslot),
        )

        print(f"EPISODE {ep}/{args.episodes}")
        print(f"episode_min_slots (per env): {[int(x) for x in detail.min_slots.cpu().tolist()]}")
        print(f"episode_feasible (per env): {[bool(x) for x in detail.feasible_mask.cpu().tolist()]}")
        print("-" * 96)

        e = args.show_env_index
        print(f"SHOW ENV INDEX = {e}")
        print("-" * 96)

        for c in range(env_cfg.num_cars):
            sol = detail.details[e][c]
            tau = int(sol.min_slots)
            feasible = bool(sol.feasible)

            demand_vec = sol.demand_vector  # [U]
            rate_vec = sol.rate_vector      # [T]
            lp_slot_vec = sol.slot_allocation  # [T]
            user_alloc = sol.user_allocation    # [U,T]

            delivered_per_user = user_alloc.sum(axis=1) * float(env_cfg.timeslot)
            demand_gap = delivered_per_user - demand_vec
            cap_gap = np.zeros_like(rate_vec)
            cap_gap[:tau] = lp_slot_vec[:tau] - rate_vec[:tau]

            payload = {
                "carriage": c,
                "feasible": feasible,
                "min_slots_integer": tau,
                "user_demand_vector_MB": _as_list(demand_vec),
                "external_total_rate_vector_per_timeslot": _as_list(rate_vec),
                "lp_solution_vector_per_timeslot_sum_users": _as_list(lp_slot_vec),
                "delivered_data_per_user_MB": _as_list(delivered_per_user),
                "demand_gap_MB_delivered_minus_demand": _as_list(demand_gap),
                "capacity_gap_rate_lp_minus_external_until_min_slots": _as_list(cap_gap),
                "user_allocation_matrix_shape": [int(user_alloc.shape[0]), int(user_alloc.shape[1])],
                "user_allocation_first3_users": [_as_list(user_alloc[i]) for i in range(min(3, user_alloc.shape[0]))],
            }
            if args.print_full_user_matrix:
                payload["user_allocation_full_matrix"] = [_as_list(row) for row in user_alloc]

            print(json.dumps(payload, ensure_ascii=False, indent=2))
            print("-" * 96)

        print("=" * 96)


if __name__ == "__main__":
    main()
