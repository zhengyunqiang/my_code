#!/usr/bin/env python
# train_T50.py
"""
具体训练脚本 - 50时隙场景

使用方法:
    python train_T50.py

配置说明:
    - T = 50: 50个时隙
    - E = 8: 8个并行环境
    - N = 2: 2个基站
    - M = 3: 每基站3个子信道
    - K = 5: 5个FAP
"""
from __future__ import annotations

import time
from pathlib import Path

import torch
import torch.nn as nn

from trainers.mixed_ppo_trainer import MixedPPOConfig, MixedPPOTrainer
from models.gat import SharedGATNetwork
from models.actor import TelecomHybridActor, SBSActor
from models.critic import SharedCriticLocal
from environments import TelecomEnvConfig, create_telecom_env


def count_parameters(model):
    """Count trainable parameters."""
    return sum(p.numel() for p in model.parameters() if p.requires_grad)


def main():
    # ====== 1. 设备配置 ======
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"\n使用设备: {device}")

    # ====== 2. 环境配置 (50时隙) ======
    env_cfg = TelecomEnvConfig(
        # 环境规模
        E=8,              # 并行环境数
        T=50,             # ⭐ 时隙数 = 50
        num_bases=2,      # 基站数 (N)
        num_cars=2,       # 车厢数
        users_per_car=10, # 每车厢用户数

        # 资源配置
        num_subchannels=3,    # 子信道数 (M)
        num_fap=5,            # FAP数 (K)

        # 观测空间
        D_obs=32,             # 观测维度

        # 物理参数
        coverage=250,         # 基站覆盖范围 (m)
        speed=10,             # 车厢速度 (m/s)
        max_power=100,        # 最大功率 (W)
        max_bandwidth=10,     # 最大带宽 (MHz)

        # 信道参数
        B_TBS=10,             # 子信道带宽 (Hz)
        delta_0=1e-9,         # 噪声功率密度
        K_gain=1,             # 信道增益常量
        gamma=2,              # 路径损耗指数
        timeslot=0.01,        # 时隙时长 (s)

        # 数据参数
        max_rate=100,         # 最大速率 (Mbps)
        mean_demand=50,       # 平均数据需求 (MB) - 增加以充分利用50时隙
        std_demand=10,        # 数据需求标准差
    )

    print("\n" + "="*70)
    print("【环境配置】".center(70))
    print("="*70)
    print(f"  时隙数 T:           {env_cfg.T}")
    print(f"  并行环境 E:         {env_cfg.E}")
    print(f"  基站数 N:           {env_cfg.num_bases}")
    print(f"  车厢数:             {env_cfg.num_cars}")
    print(f"  子信道 M (per BS):  {env_cfg.num_subchannels}")
    print(f"  FAP数 K:            {env_cfg.num_fap}")
    print(f"  平均数据需求:       {env_cfg.mean_demand} MB")
    print(f"  时隙时长:           {env_cfg.timeslot} s")

    # ====== 3. 网络配置 ======
    N, M, K, E, T = env_cfg.N, env_cfg.M, env_cfg.K, env_cfg.E, env_cfg.T
    D_obs, D_h = env_cfg.D_obs, 64
    P_max, B_max = env_cfg.max_power, env_cfg.max_bandwidth

    # GAT - 共享编码器
    gat = SharedGATNetwork(
        d_obs=D_obs,
        d_h=D_h,
        num_layers=2,
        num_heads=4,
        dropout_attn=0.0,
        use_edge_weight=False,
        use_residual=False,
        use_layernorm=False,
    ).to(device)

    # Critic - 价值函数
    critic = SharedCriticLocal(
        d_h=D_h,
        hidden_layers=(256, 256),
        activation="relu",
        use_layernorm=False,
    ).to(device)

    # 标准智能体 Actor (基站)
    std_actors = []
    for i in range(N):
        actor = TelecomHybridActor(
            input_dim=D_h,
            num_subchannels=M,
            num_femtoCell=env_cfg.num_cars,  # 选择车厢
            max_power=P_max,
            trunk_layers=(256, 256),
            activation="relu",
            dropout=0.0,
            min_std=1e-3,
            eps=1e-6,
            init_mode="xavier",
        ).to(device)
        std_actors.append(actor)

    # SBS Actor (带宽分配)
    sbs_actor = SBSActor(
        input_dim=D_h,
        num_fap=K,
        max_bandwidth=B_max,
        trunk_layers=(256, 256),
        activation="relu",
        dropout=0.0,
        min_std=1e-3,
        eps=1e-6,
        init_mode="xavier",
    ).to(device)

    print("\n" + "="*70)
    print("【模型配置】".center(70))
    print("="*70)
    print(f"  GAT 嵌入维度:       {D_h}")
    print(f"  GAT 参数量:         {count_parameters(gat):,}")
    print(f"  Critic 参数量:      {count_parameters(critic):,}")
    print(f"  Actor 参数量 (each): {count_parameters(std_actors[0]):,}")
    print(f"  SBS Actor 参数量:   {count_parameters(sbs_actor):,}")
    total_params = (count_parameters(gat) + count_parameters(critic) +
                    N * count_parameters(std_actors[0]) + count_parameters(sbs_actor))
    print(f"  总参数量:           {total_params:,}")

    # ====== 4. 优化器 ======
    lr = 3e-4
    opt_gat = torch.optim.Adam(gat.parameters(), lr=lr)
    opt_critic = torch.optim.Adam(critic.parameters(), lr=lr)
    opt_std_actors = torch.optim.Adam(nn.ModuleList(std_actors).parameters(), lr=lr)
    opt_sbs_actor = torch.optim.Adam(sbs_actor.parameters(), lr=lr)

    # ====== 5. PPO 训练器配置 ======
    ppo_cfg = MixedPPOConfig(
        T=T, E=E, N=N, M=M, K=K, D_obs=D_obs,
        P_max=P_max, B_max=B_max,
        scale=100.0,        # reward = -S_final / scale
        gamma=0.99,         # 折扣因子
        lam=0.95,           # GAE lambda
        clip_eps=0.2,       # PPO 裁剪
        vf_coef=0.5,        # Value 损失系数
        ent_coef=0.01,      # 熵系数
        epochs=4,           # PPO 更新轮数
        minibatch_size=64,  # 小批量大小
        max_grad_norm=1.0,  # 梯度裁剪
        normalize_adv=True,
        eps_adv=1e-8,
    )

    trainer = MixedPPOTrainer(
        cfg=ppo_cfg,
        gat=gat,
        critic=critic,
        std_actors=std_actors,
        sbs_actor=sbs_actor,
        opt_gat=opt_gat,
        opt_critic=opt_critic,
        opt_std_actors=opt_std_actors,
        opt_sbs_actor=opt_sbs_actor,
        device=device,
    )

    # ====== 6. 创建环境 ======
    env = create_telecom_env(env_cfg, device)

    print("\n" + "="*70)
    print("【训练配置】".center(70))
    print("="*70)
    print(f"  学习率:             {lr}")
    print(f"  PPO epochs:         {ppo_cfg.epochs}")
    print(f"  Minibatch size:     {ppo_cfg.minibatch_size}")
    print(f"  Gamma:              {ppo_cfg.gamma}")
    print(f"  Lambda:             {ppo_cfg.lam}")
    print(f"  Clip epsilon:       {ppo_cfg.clip_eps}")

    # ====== 7. 训练循环 ======
    num_iterations = 100
    print_freq = 5

    print("\n" + "="*70)
    print("【开始训练】".center(70))
    print("="*70)
    print(f"{'Iter':<8} {'Loss':<12} {'Actor':<12} {'Critic':<12} {'Entropy':<12} {'S_final':<12} {'Time':<10}")
    print("-"*70)

    s_final_history = []
    start_time = time.time()

    for it in range(1, num_iterations + 1):
        iter_start = time.time()

        # 收集 episode
        buf = trainer.collect_episode(env)

        # PPO 更新
        logs = trainer.update(buf)

        # 获取终端得分
        if hasattr(env, 'remaining_data'):
            s_final = env.remaining_data.sum(dim=1).mean().item()
        else:
            s_final = 0.0
        s_final_history.append(s_final)

        iter_time = time.time() - iter_start

        # 打印
        if it % print_freq == 0 or it == 1:
            print(f"{it:<8} "
                  f"{logs['loss_total']:<12.4f} "
                  f"{logs['loss_actor']:<12.4f} "
                  f"{logs['loss_critic']:<12.4f} "
                  f"{logs['entropy']:<12.4f} "
                  f"{s_final:<12.2f} "
                  f"{iter_time:<10.2f}")

    total_time = time.time() - start_time

    # ====== 8. 训练总结 ======
    print("\n" + "="*70)
    print("【训练完成】".center(70))
    print("="*70)
    print(f"  总迭代数:           {num_iterations}")
    print(f"  总训练时间:         {total_time:.1f} 秒")
    print(f"  平均每迭代:         {total_time/num_iterations:.2f} 秒")
    print(f"\n  初始 S_final:       {s_final_history[0]:.2f} MB")
    print(f"  最终 S_final:       {s_final_history[-1]:.2f} MB")
    print(f"  最佳 S_final:       {min(s_final_history):.2f} MB")
    print(f"  平均 S_final:       {sum(s_final_history)/len(s_final_history):.2f} MB")

    # 计算改进率
    if s_final_history[0] > 0:
        improvement = (s_final_history[0] - s_final_history[-1]) / s_final_history[0] * 100
        print(f"  改进率:             {improvement:.1f}%")

    print("="*70 + "\n")

    # 可选: 保存模型
    save_dir = Path("checkpoints/T50")
    save_dir.mkdir(parents=True, exist_ok=True)

    torch.save({
        'gat': gat.state_dict(),
        'critic': critic.state_dict(),
        'std_actors': [a.state_dict() for a in std_actors],
        'sbs_actor': sbs_actor.state_dict(),
        'env_cfg': env_cfg,
        's_final_history': s_final_history,
    }, save_dir / 'model.pt')

    print(f"模型已保存到: {save_dir}/model.pt\n")


if __name__ == "__main__":
    main()
