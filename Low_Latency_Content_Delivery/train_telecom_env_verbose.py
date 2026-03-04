# train_telecom_env_verbose.py
"""
Training script with detailed logging for heterogeneous multi-agent telecom system.

Prints core data during training:
  - Action allocations (compartments, power, bandwidth)
  - Data rates per carriage
  - Remaining data
  - Terminal scores
"""
from __future__ import annotations

import torch
import torch.nn as nn
from typing import Dict, List

from trainers.mixed_ppo_trainer import MixedPPOConfig, MixedPPOTrainer
from models.gat import SharedGATNetwork
from models.actor import TelecomHybridActor, SBSActor
from models.critic import SharedCriticLocal
from environments import TelecomEnvConfig, create_telecom_env


class VerboseTrainer(MixedPPOTrainer):
    """Trainer with detailed logging of actions and states."""

    def __init__(self, *args, verbose: bool = True, print_freq: int = 1, **kwargs):
        super().__init__(*args, **kwargs)
        self.verbose = verbose
        self.print_freq = print_freq
        self.episode_data: List[Dict] = []

    @torch.no_grad()
    def collect_episode_verbose(self, env, iteration: int = 0) -> Dict:
        """
        Collect episode with detailed logging.

        Returns summary statistics for the episode.
        """
        cfg = self.cfg
        self.episode_data = []

        X, A = env.reset()
        X = X.to(self.device).float()
        A = A.to(self.device).float()

        S_final = None
        episode_summary = {
            "compartments": [],
            "power": [],
            "bandwidth": [],
            "data_rate": [],
            "remaining_data": [],
        }

        for t in range(cfg.T):
            # Shared encoding
            H = self.gat(X, A)  # [E, N_total, D_h]

            # Value estimate
            V_out = self.critic(H)
            V = V_out.V  # [E, N_total, 1]

            # Standard agents actions
            C_list: List[torch.Tensor] = []
            P_list: List[torch.Tensor] = []
            logp_std_list: List[torch.Tensor] = []

            for i in range(cfg.N):
                h_i = H[:, i, :]
                act = self.std_actors[i].get_action(h_i)
                c_i = act.get("compartments", act.get("users"))
                p_i = act["power"]
                logp_i = act["logp"]
                C_list.append(c_i)
                P_list.append(p_i)
                logp_std_list.append(logp_i)

            C_t = torch.stack(C_list, dim=1).to(torch.long)
            P_t = torch.stack(P_list, dim=1).to(torch.float32)
            logp_std_t = torch.stack(logp_std_list, dim=1).to(torch.float32)

            # SBS agent action
            h_sbs = H[:, cfg.N, :]
            sbs_act = self.sbs_actor.get_action(h_sbs)
            B_sbs_t = sbs_act["bandwidth"]
            logp_sbs_t = sbs_act["logp"]

            # Store actions before step
            episode_summary["compartments"].append(C_t.clone())
            episode_summary["power"].append(P_t.clone())
            episode_summary["bandwidth"].append(B_sbs_t.clone())

            # Get environment state before step
            remaining_before = env.remaining_data.clone() if hasattr(env, 'remaining_data') else None

            # Env step
            step_out = env.step({
                "compartments": C_t,
                "power": P_t,
                "bandwidth": B_sbs_t,
            })
            X_next, A_next, done, info = _extract_step_outputs(step_out)

            X_next = X_next.to(self.device).float()
            A_next = A_next.to(self.device).float()
            done_t = done.to(self.device).float().view(cfg.E)

            X, A = X_next, A_next

            # Record data rate (change in remaining data)
            if hasattr(env, 'remaining_data') and remaining_before is not None:
                data_transmitted = remaining_before - env.remaining_data
                data_rate = data_transmitted / env.cfg.timeslot
                episode_summary["data_rate"].append(data_rate.clone())
                episode_summary["remaining_data"].append(env.remaining_data.clone())

            if info is not None and ("S_final" in info):
                S_final = info["S_final"]

        # Compute terminal score
        if S_final is None:
            S_final = torch.zeros(cfg.E, device=self.device)
        else:
            S_final = S_final.to(self.device)

        # Print summary if verbose
        if self.verbose and (iteration % self.print_freq == 0):
            self._print_episode_summary(episode_summary, S_final, iteration, t)

        return {
            "episode_summary": episode_summary,
            "S_final": S_final,
            "final_remaining_data": env.remaining_data.clone() if hasattr(env, 'remaining_data') else None,
        }

    def _print_episode_summary(self, summary: Dict, S_final: torch.Tensor, iteration: int, final_t: int):
        """Print detailed episode summary."""
        cfg = self.cfg
        E = cfg.E

        print("\n" + "=" * 80)
        print(f" ITERATION {iteration} - Episode Summary ".center(80))
        print("=" * 80)

        # Average over first env (or all envs)
        avg_compartments = torch.stack([c.float().mean() for c in summary["compartments"]]).mean().item()
        avg_power = torch.stack([p.mean() for p in summary["power"]]).mean().item()
        avg_bandwidth = torch.stack([b.mean() for b in summary["bandwidth"]]).mean().item()

        print(f"\n[ACTION STATISTICS]")
        print(f"  Avg Compartments (carriage selection): {avg_compartments:.2f} / {env_cfg.num_cars}")
        print(f"  Avg Power per subchannel:           {avg_power:.2f} / {cfg.P_max}")
        print(f"  Avg Bandwidth per FAP:              {avg_bandwidth:.2f} / {cfg.B_max}")

        # Final actions (last timestep)
        last_compartments = summary["compartments"][-1]  # [E, N, M]
        last_power = summary["power"][-1]              # [E, N, M]
        last_bandwidth = summary["bandwidth"][-1]      # [E, K]

        print(f"\n[FINAL TIMESTEP ACTIONS (Env 0)]")
        print(f"  Subchannel Compartments (BS x Subch):")
        for n in range(cfg.N):
            for m in range(cfg.M):
                car = last_compartments[0, n, m].item()
                pwr = last_power[0, n, m].item()
                print(f"    BS{n}-Ch{m}: Carriage={int(car)}, Power={pwr:.2f}")

        print(f"\n  Bandwidth Allocation (SBS -> FAPs):")
        for k in range(min(cfg.K, 10)):  # Print first 10 FAPs
            bw = last_bandwidth[0, k].item()
            print(f"    FAP{k}: Bandwidth={bw:.2f}")

        # Data rate statistics
        if summary["data_rate"]:
            data_rates = torch.stack(summary["data_rate"])  # [T, E, num_cars]
            avg_rate = data_rates.mean().item()
            max_rate = data_rates.max().item()

            print(f"\n[DATA RATE STATISTICS]")
            print(f"  Avg Rate per Carriage:  {avg_rate:.4f} Mbps")
            print(f"  Max Rate per Carriage:  {max_rate:.4f} Mbps")

        # Remaining data
        if summary["remaining_data"]:
            final_remaining = summary["remaining_data"][-1]  # [E, num_cars]
            print(f"\n[REMAINING DATA]")
            for car_idx in range(env_cfg.num_cars):
                avg_remaining = final_remaining[:, car_idx].mean().item()
                print(f"  Carriage {car_idx}: {avg_remaining:.2f} MB")

        # Terminal score
        print(f"\n[TERMINAL SCORE]")
        print(f"  S_final (to minimize): {S_final.mean().item():.4f}")
        print(f"  Reward = -S_final / scale: {-S_final.mean().item() / cfg.scale:.4f}")

        print("=" * 80)


def _extract_step_outputs(step_out):
    """Extract step outputs."""
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


def main() -> None:
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Using device: {device}")

    # ====== Environment Configuration ======
    global env_cfg
    env_cfg = TelecomEnvConfig(
        E=4,              # parallel envs
        T=20,             # episode length
        num_bases=2,      # N - base stations (standard agents)
        num_cars=2,       # carriages
        users_per_car=10, # users per carriage
        num_subchannels=3,    # M - subchannels per BS
        num_fap=5,            # K - FAPs for SBS
        coverage=250,
        speed=10,
        max_power=100,    # P_max
        max_bandwidth=10, # B_max
        B_TBS=10,
        delta_0=1e-9,
        K_gain=1,
        gamma=2,
        timeslot=0.01,
        max_rate=100,
        mean_demand=8,
        std_demand=3,
        D_obs=32,         # observation dimension
    )

    N = env_cfg.N
    M = env_cfg.M
    K = env_cfg.K
    E = env_cfg.E
    T = env_cfg.T
    D_obs = env_cfg.D_obs
    D_h = 64            # GAT embedding dim
    P_max = env_cfg.max_power
    B_max = env_cfg.max_bandwidth

    print(f"\n{'='*80}")
    print(f"{'TELECOM MULTI-AGENT RL TRAINING':^80}")
    print(f"{'='*80}")
    print(f"Environment Configuration:")
    print(f"  Base stations (N):        {N}")
    print(f"  Carriages:                {env_cfg.num_cars}")
    print(f"  Subchannels per BS (M):   {M}")
    print(f"  FAPs for SBS (K):         {K}")
    print(f"  Parallel envs (E):        {E}")
    print(f"  Episode length (T):       {T}")
    print(f"  Max Power (P_max):        {P_max}")
    print(f"  Max Bandwidth (B_max):    {B_max}")
    print(f"{'='*80}\n")

    # ====== Build modules ======
    gat = SharedGATNetwork(
        d_obs=D_obs, d_h=D_h, num_layers=2, num_heads=4,
        dropout_attn=0.0, use_edge_weight=False, use_residual=False, use_layernorm=False,
    ).to(device)

    critic = SharedCriticLocal(
        d_h=D_h, hidden_layers=(256, 256), activation="relu", use_layernorm=False,
    ).to(device)

    std_actors = []
    for i in range(N):
        std_actors.append(
            TelecomHybridActor(
                input_dim=D_h, num_subchannels=M, num_femtoCell=env_cfg.num_cars,
                max_power=P_max, trunk_layers=(256, 256), activation="relu",
                dropout=0.0, min_std=1e-3, eps=1e-6, init_mode="xavier",
            ).to(device)
        )

    sbs_actor = SBSActor(
        input_dim=D_h, num_fap=K, max_bandwidth=B_max,
        trunk_layers=(256, 256), activation="relu",
        dropout=0.0, min_std=1e-3, eps=1e-6, init_mode="xavier",
    ).to(device)

    # ====== Optimizers ======
    opt_gat = torch.optim.Adam(gat.parameters(), lr=3e-4)
    opt_critic = torch.optim.Adam(critic.parameters(), lr=3e-4)
    opt_std_actors = torch.optim.Adam(nn.ModuleList(std_actors).parameters(), lr=3e-4)
    opt_sbs_actor = torch.optim.Adam(sbs_actor.parameters(), lr=3e-4)

    # ====== Trainer config ======
    cfg = MixedPPOConfig(
        T=T, E=E, N=N, M=M, K=K, D_obs=D_obs, P_max=P_max, B_max=B_max,
        scale=100.0, gamma=0.99, lam=0.95, clip_eps=0.2, vf_coef=0.5,
        ent_coef=0.01, epochs=4, minibatch_size=256, max_grad_norm=1.0,
        normalize_adv=True, eps_adv=1e-8,
    )

    # Use verbose trainer
    trainer = VerboseTrainer(
        cfg=cfg, gat=gat, critic=critic, std_actors=std_actors, sbs_actor=sbs_actor,
        opt_gat=opt_gat, opt_critic=opt_critic, opt_std_actors=opt_std_actors,
        opt_sbs_actor=opt_sbs_actor, device=device, verbose=True, print_freq=5,
    )

    # ====== Create environment ======
    env = create_telecom_env(env_cfg, device)

    # ====== Training loop ======
    num_iterations = 20
    print(f"\nTraining for {num_iterations} iterations...\n")

    S_final_history = []
    loss_history = []

    for it in range(1, num_iterations + 1):
        # Collect with verbose output
        episode_data = trainer.collect_episode_verbose(env, iteration=it)

        # Regular update
        buf = trainer.collect_episode(env)
        logs = trainer.update(buf)

        S_final_history.append(episode_data["S_final"].mean().item())
        loss_history.append(logs["loss_total"])

    # ====== Final Summary ======
    print("\n" + "=" * 80)
    print(f"{'TRAINING COMPLETE - FINAL SUMMARY':^80}")
    print("=" * 80)

    print(f"\n[TERMINAL SCORE PROGRESS]")
    print(f"  Initial:  {S_final_history[0]:.4f}")
    print(f"  Final:    {S_final_history[-1]:.4f}")
    print(f"  Best:     {min(S_final_history):.4f}")
    print(f"  Average:  {sum(S_final_history)/len(S_final_history):.4f}")

    print(f"\n[LOSS PROGRESS]")
    print(f"  Initial:  {loss_history[0]:.4f}")
    print(f"  Final:    {loss_history[-1]:.4f}")
    print(f"  Average:  {sum(loss_history)/len(loss_history):.4f}")

    print(f"\n[FINAL REMAINING DATA]")
    if episode_data["final_remaining_data"] is not None:
        final_rem = episode_data["final_remaining_data"].mean(dim=0)
        for car_idx in range(env_cfg.num_cars):
            print(f"  Carriage {car_idx}: {final_rem[car_idx].item():.2f} MB")

    print("\n" + "=" * 80)


if __name__ == "__main__":
    main()
