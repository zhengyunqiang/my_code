#!/usr/bin/env python
"""
High-load T=200 training script with LP-evaluator diagnostics.

Goal:
  Keep LP minimum completion slots around a hard regime (~165) and optimize
  policies to push this value down.
"""
from __future__ import annotations

import argparse
import time
from statistics import mean

import torch
import torch.nn as nn

from environments import TelecomEnvConfig, create_telecom_env
from models.actor import SBSActor, TelecomHybridActor
from models.critic import SharedCriticLocal
from models.gat import SharedGATNetwork
from trainers.mixed_ppo_trainer import MixedPPOConfig, MixedPPOTrainer


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Train high-load T=200 with LP evaluator")
    p.add_argument("--iterations", type=int, default=40, help="training iterations")
    p.add_argument("--t", type=int, default=200, help="episode horizon")
    p.add_argument("--mean-demand", type=float, default=128.0, help="mean carriage demand")
    p.add_argument("--std-demand", type=float, default=8.0, help="std carriage demand")
    p.add_argument("--num-envs", type=int, default=4, help="parallel envs")
    p.add_argument("--seed", type=int, default=7, help="random seed")
    p.add_argument("--sleep-seconds", type=float, default=0.35, help="extra delay per episode")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    torch.manual_seed(args.seed)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"device={device}")

    env_cfg = TelecomEnvConfig(
        E=args.num_envs,
        T=args.t,
        num_bases=2,
        num_cars=2,
        users_per_car=10,
        num_subchannels=3,
        num_fap=5,
        D_obs=32,
        max_power=100.0,
        max_bandwidth=10.0,
        mean_demand=args.mean_demand,
        std_demand=args.std_demand,
        use_realistic_channel=False,
    )
    env = create_telecom_env(env_cfg, device)

    N, M, K = env_cfg.N, env_cfg.M, env_cfg.K
    D_h = 64

    gat = SharedGATNetwork(
        d_obs=env_cfg.D_obs,
        d_h=D_h,
        num_layers=2,
        num_heads=4,
        dropout_attn=0.0,
    ).to(device)
    critic = SharedCriticLocal(
        d_h=D_h,
        hidden_layers=(256, 256),
        activation="relu",
    ).to(device)
    std_actors = nn.ModuleList([
        TelecomHybridActor(
            input_dim=D_h,
            num_subchannels=M,
            num_femtoCell=env_cfg.num_cars,
            max_power=env_cfg.max_power,
            trunk_layers=(256, 256),
        ).to(device)
        for _ in range(N)
    ])
    sbs_actor = SBSActor(
        input_dim=D_h,
        num_fap=K,
        max_bandwidth=env_cfg.max_bandwidth,
        trunk_layers=(256, 256),
    ).to(device)

    opt_gat = torch.optim.Adam(gat.parameters(), lr=3e-4)
    opt_critic = torch.optim.Adam(critic.parameters(), lr=3e-4)
    opt_std = torch.optim.Adam(std_actors.parameters(), lr=3e-4)
    opt_sbs = torch.optim.Adam(sbs_actor.parameters(), lr=3e-4)

    cfg = MixedPPOConfig(
        T=env_cfg.T,
        E=env_cfg.E,
        N=env_cfg.N,
        M=env_cfg.M,
        K=env_cfg.K,
        D_obs=env_cfg.D_obs,
        P_max=env_cfg.max_power,
        B_max=env_cfg.max_bandwidth,
        scale=100.0,
        gamma=0.99,
        lam=0.95,
        clip_eps=0.2,
        vf_coef=0.5,
        ent_coef=0.01,
        epochs=2,
        minibatch_size=128,
        max_grad_norm=1.0,
        use_slot_evaluator=True,
        evaluator_coef=0.15,
    )
    trainer = MixedPPOTrainer(
        cfg=cfg,
        gat=gat,
        critic=critic,
        std_actors=std_actors,
        sbs_actor=sbs_actor,
        opt_gat=opt_gat,
        opt_critic=opt_critic,
        opt_std_actors=opt_std,
        opt_sbs_actor=opt_sbs,
        device=device,
    )

    print(
        f"T={env_cfg.T}, E={env_cfg.E}, mean_demand={env_cfg.mean_demand}, "
        f"std_demand={env_cfg.std_demand}"
    )
    print(
        f"{'iter':<6} {'lp_slots_mean':<14} {'lp_slots_env':<28} "
        f"{'feasible':<10} {'ext_data_env0_MB':<22} {'display_tag':<12}"
    )
    print("-" * 116)

    lp_history: list[float] = []
    best_lp = float("inf")

    for it in range(1, args.iterations + 1):
        buf = trainer.collect_episode(env)
        trainer.update(buf)

        slots = buf.eval_min_slots.detach().cpu()
        feasible = buf.eval_feasible.detach().cpu().float()

        lp_mean = float(slots.mean())
        lp_history.append(lp_mean)
        best_lp = min(best_lp, lp_mean)

        # LP slots are integer per env; mean over env can be fractional.
        slots_env = "[" + ",".join(str(int(x)) for x in slots.tolist()) + "]"
        feasible_rate = float(feasible.mean())

        # Display-friendly external totals for env0.
        ext_rate_sum_env0 = env.external_rate_history[:, 0, :].sum(dim=0)  # [C]
        ext_data_env0 = ext_rate_sum_env0 * float(env_cfg.timeslot)         # [C]
        ext_data_text = "[" + ",".join(f"{x:.2f}" for x in ext_data_env0.tolist()) + "]"

        # Presentation tag (purely for display grouping).
        display_tag = f"SHOW-{it:03d}"

        if it % 1 == 0:
            print(
                f"{it:<6d} {lp_mean:<14.2f} {slots_env:<28} "
                f"{feasible_rate:<10.2f} {ext_data_text:<22} {display_tag:<12}"
            )
            print("  per-timeslot external total rate vectors:")
            # external_rate_history: [T, E, C]
            rate_hist = env.external_rate_history.detach().cpu().permute(1, 2, 0).contiguous()  # [E,C,T]
            for e in range(env_cfg.E):
                for c in range(env_cfg.num_cars):
                    vec = ",".join(f"{v:.3f}" for v in rate_hist[e, c].tolist())
                    print(f"    env={e} carriage={c} rates=[{vec}]")
            print("-" * 116)

        if args.sleep_seconds > 0:
            time.sleep(args.sleep_seconds)

    print("\nsummary:")
    print(f"  best lp_slots_mean: {best_lp:.2f}")
    print(f"  last 5 avg: {mean(lp_history[-5:]):.2f}")
    print(f"  first 5 avg: {mean(lp_history[:5]):.2f}")


if __name__ == "__main__":
    main()
