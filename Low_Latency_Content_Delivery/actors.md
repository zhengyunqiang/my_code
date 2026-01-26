# Actor（单智能体）网络设计与实现细节

本文描述单智能体 Actor（策略网络）：输入为共享 GAT 输出的节点嵌入，输出针对每个子信道的离散用户选择与连续功率分配；并提供 PPO 所需的联合对数概率与熵项计算口径。

---

## 1. 设计目标与约束

### 1.1 目标
在时间步 t，第 i 个智能体根据编码特征 h_i 生成混合动作：

- **离散**：对每条子信道选择 femtoCell 索引  
- **连续**：对每条子信道分配功率（有界）

训练采用 PPO，需要：

- **采样阶段（rollout）**：输出动作 $$(U, P)$$ 及旧策略联合对数概率  
  $$\log\pi_{\theta_i^{\mathrm{old}}}\!\left(a_t^{(i)}\mid s_t\right)$$
- **更新阶段（update）**：在新策略下复算联合对数概率  
  $$\log\pi_{\theta_i}\!\left(a_t^{(i)}\mid s_t\right)$$  
  与熵项 $\mathcal{H}$

### 1.2 约束
- **离散动作**：  
  $$u_{t,j}^{(i)} \in \{0,1,\dots,K-1\}$$
- **连续功率**：  
  $$p_{t,j}^{(i)} \in (0,P_{\max})$$
- **多头结构**：每个智能体有 M 条子信道（对应 M 个离散头 + M 个连续头）

---

## 2. 符号与张量形状（单智能体）

### 2.1 输入
共享 GAT 输出的第 i 个节点嵌入：
$$h_i \in \mathbb{R}^{B\times D_h}$$

其中 B 为 batch size，D_h 为节点编码维度（与 GAT 网络相关）。

### 2.2 输出（策略分布参数）
- **离散 logits**：  
  $$L \in \mathbb{R}^{B\times M\times K}$$
- **连续预变量（pre-squash）正态分布参数**：  
  $$\mu \in \mathbb{R}^{B\times M},\qquad \sigma \in \mathbb{R}_{>0}^{B\times M}$$

说明：$\mu,\sigma$ 参数化的是 $z\in\mathbb{R}$ 上的正态分布；功率通过 Sigmoid 压缩到 $(0,1)$ 后再缩放到 $(0,P_{\max})$。

---

## 3. 动作空间与“维度/规模”口径

### 3.1 动作空间（严格定义）
单智能体动作：
$$a_t^{(i)}=\{(u_{t,j}^{(i)},p_{t,j}^{(i)})\}_{j=1}^{M}$$

其中：
$$u_{t,j}^{(i)}\in\{0,1,\dots,K-1\},\qquad p_{t,j}^{(i)}\in(0,P_{\max})$$

因此单智能体动作空间：
$$\mathcal{A}^{(i)}=\Big(\{0,1,\dots,K-1\}\times(0,P_{\max})\Big)^{M}$$

### 3.2 连续动作欧式维度
连续部分仅功率，共 $M$ 个连续标量：
$$d_{\mathrm{cont}}^{(i)} = M$$

### 3.3 策略输出参数规模（工程常用）
- 离散 logits 数量：$$MK$$  
- 连续参数数量：$$2M\;(\mu\ \text{与}\ \sigma)$$  

因此单智能体输出参数规模：
$$d_{\mathrm{param}}^{(i)} = MK + 2M = M(K+2)$$

---

## 4. 网络结构（Trunk + Heads）

采用“共享 trunk + 三个 head”的结构。

### 4.1 Trunk（特征提取）
Trunk 将 $h_i$ 映射到隐表示 $t$：
$$t=f_{\mathrm{trunk}}(h_i),\qquad t\in\mathbb{R}^{B\times D_a}$$

其中 $D_a$ 为 trunk 输出维度。

### 4.2 离散 Head（logits）
输出并 reshape：
$$\mathrm{vec}(L)=W_L t+b_L,\qquad \mathrm{vec}(L)\in\mathbb{R}^{B\times (MK)}$$
$$L\in\mathbb{R}^{B\times M\times K}$$

### 4.3 连续 Head（$\mu,\sigma$）
$$\mu=W_\mu t+b_\mu,\qquad \mu\in\mathbb{R}^{B\times M}$$
$$\sigma=\mathrm{softplus}(W_\sigma t+b_\sigma)+\sigma_{\min},\qquad \sigma_{\min}>0$$

---

## 5. 分布定义与采样（Rollout 阶段）

### 5.1 离散动作（Categorical）
第 $j$ 条子信道：
$u_{t,j}^{(i)}\sim \mathrm{Categorical}\!\left(\mathrm{softmax}\!\left(L_{t,j}^{(i)}\right)\right)$

离散对数概率（每头）：
$$\log\pi_{\theta_i}\!\left(u_{t,j}^{(i)}\mid s_t\right)$$

离散部分联合对数概率（对 $M$ 求和）：
$$\log\pi_{\theta_i}^{U}\!\left(a_t^{(i)}\mid s_t\right)=\sum_{j=1}^{M}\log\pi_{\theta_i}\!\left(u_{t,j}^{(i)}\mid s_t\right)$$

### 5.2 连续功率（Sigmoid-Squashed Gaussian）
先采样预变量：
$$z_{t,j}^{(i)}\sim\mathcal{N}\!\left(\mu_{t,j}^{(i)},\sigma_{t,j}^{(i)}\right)$$

Sigmoid 压缩并缩放：
$$\tilde p_{t,j}^{(i)}=\sigma\!\left(z_{t,j}^{(i)}\right)\in(0,1),\qquad
p_{t,j}^{(i)}=P_{\max}\tilde p_{t,j}^{(i)}\in(0,P_{\max})$$

---

## 6. 联合对数概率（PPO Ratio 口径，必须一致）

### 6.1 总体形式
单智能体联合对数概率：
$\log \pi_{\theta_i}\!\left(a_t^{(i)}\mid s_t\right) = 
\sum_{j=1}^{M}
\left(\log \pi_{\theta_i}\!\left(u_{t,j}^{(i)}\mid s_t\right)+ 
\log \pi_{\theta_i}\!\left(p_{t,j}^{(i)}\mid s_t\right)\right)$

### 6.2 连续部分（change-of-variables + Jacobian）
令：
$$\tilde p=\frac{p}{P_{\max}}\in(0,1), 
z=\operatorname{logit}(\tilde p)=\ln\frac{\tilde p}{1-\tilde p}$$

则单维连续对数概率：
$$\log \pi_{\theta_i}(p\mid s)
=
\log \mathcal{N}(z;\mu,\sigma)
-\log P_{\max}
-\log\!\big(\tilde p(1-\tilde p)\big)$$

对 $M$ 条子信道求和得到连续部分联合对数概率：
$$\log\pi_{\theta_i}^{P}\!\left(a_t^{(i)}\mid s_t\right)=\sum_{j=1}^{M}\log \pi_{\theta_i}\!\left(p_{t,j}^{(i)}\mid s_t\right)$$

---

## 7. 熵项（Entropy Bonus）

### 7.1 离散熵（可精确计算）
$$\mathcal{H}_U =
\sum_{j=1}^{M}
\mathcal{H}\!\left(\mathrm{Categorical}\!\left(\mathrm{softmax}\!\left(L_{t,j}^{(i)}\right)\right)\right)$$

### 7.2 连续熵（工程常用稳定近似）
对预变量正态分布：
$$\mathcal{H}_Z
=
\sum_{j=1}^{M}
\mathcal{H}\!\left(\mathcal{N}\!\left(\mu_{t,j}^{(i)},\sigma_{t,j}^{(i)}\right)\right)$$

整体熵（用于熵奖励项）：
$$\mathcal{H}=\mathcal{H}_U+\mathcal{H}_Z$$

---

## 8. 接口设计（建议的最小接口）

### 8.1 `forward(h_i)`
输入：
$$h_i\in\mathbb{R}^{B\times D_h}$$

输出分布参数：
$$L\in\mathbb{R}^{B\times M\times K},\qquad
\mu\in\mathbb{R}^{B\times M},\qquad
\sigma\in\mathbb{R}_{>0}^{B\times M}$$

### 8.2 `get_action(h_i)`（采样）
返回：
- 离散动作：$$U\in\{0,\dots,K-1\}^{B\times M}$$
- 连续动作：$$P\in(0,P_{\max})^{B\times M}$$
- 联合对数概率：$$\log\pi_{\theta_i}(a\mid s)\in\mathbb{R}^{B}$$
- 熵：$$\mathcal{H}\in\mathbb{R}^{B}$$

### 8.3 `evaluate(h_i,U,P)`（PPO 复算）
返回：
- 新策略下联合对数概率：$\log\pi_{\theta_i}(a\mid s)\in\mathbb{R}^{B}$
- 熵：$\mathcal{H}\in\mathbb{R}^{B}$
- （可选）离散/连续分量：$\log\pi^{U}$ 与 $\log\pi^{P}$ 的求和结果

---

## 9. 数值稳定与实现细节

### 9.1 概率边界 Clamp（避免 $\log(0)$）
对归一化功率：
$$\tilde p=\frac{p}{P_{\max}}$$

必须执行：
$$\tilde p\leftarrow \mathrm{clamp}(\tilde p,\varepsilon,1-\varepsilon),\qquad \varepsilon=10^{-6}\ \text{（推荐）}$$

### 9.2 标准差下限（避免方差塌缩）
$$\sigma \leftarrow \max(\sigma,\sigma_{\min}),\qquad \sigma_{\min}=10^{-3}\ \text{（推荐）}$$

### 9.3 log-prob 聚合口径（用于 PPO ratio）
离散与连续的 `log_prob` 通常为形状 $B\times M$，必须在子信道维度求和得到 $B$：
$$\log\pi(a\mid s)=\sum_{j=1}^{M}\big(\log\pi(u_j\mid s)+\log\pi(p_j\mid s)\big)\in\mathbb{R}^{B}$$

---

## 10. PyTorch 参考实现（单智能体 Actor）

说明：以下为可运行参考实现；其中数学公式在正文已给出严格口径，代码遵循同一口径。

```python
import math
from dataclasses import dataclass
from typing import Dict, Tuple

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.distributions import Categorical, Normal


def logit(x: torch.Tensor) -> torch.Tensor:
    return torch.log(x) - torch.log1p(-x)


@dataclass
class ActorOutput:
    logits: torch.Tensor  # [B, M, K]
    mu: torch.Tensor      # [B, M]
    std: torch.Tensor     # [B, M] > 0


class TelecomHybridActor(nn.Module):
    def __init__(
        self,
        input_dim: int,          # D_h
        num_subchannels: int,    # M
        num_femtoCell: int,      # K
        max_power: float,        # Pmax
        trunk_layers: Tuple[int, ...] = (256, 256),
        min_std: float = 1e-3,
        eps: float = 1e-6,
    ) -> None:
        super().__init__()
        self.M = num_subchannels
        self.K = num_femtoCell
        self.Pmax = float(max_power)
        self.min_std = float(min_std)
        self.eps = float(eps)

        dims = (input_dim,) + trunk_layers
        layers = []
        for a, b in zip(dims[:-1], dims[1:]):
            layers += [nn.Linear(a, b), nn.ReLU(inplace=True)]
        self.trunk = nn.Sequential(*layers)
        trunk_out = dims[-1]

        self.logits_head = nn.Linear(trunk_out, self.M * self.K)
        self.mu_head = nn.Linear(trunk_out, self.M)
        self.log_std_head = nn.Linear(trunk_out, self.M)

    def forward(self, h: torch.Tensor) -> ActorOutput:
        t = self.trunk(h)
        logits = self.logits_head(t).view(-1, self.M, self.K)
        mu = self.mu_head(t)
        log_std = self.log_std_head(t)
        std = F.softplus(log_std) + self.min_std
        return ActorOutput(logits=logits, mu=mu, std=std)

    @torch.no_grad()
    def get_action(self, h: torch.Tensor) -> Dict[str, torch.Tensor]:
        out = self.forward(h)

        dist_u = Categorical(logits=out.logits)   # batch [B,M]
        users = dist_u.sample()                   # [B,M]
        logp_u = dist_u.log_prob(users)           # [B,M]
        ent_u = dist_u.entropy()                  # [B,M]

        dist_z = Normal(out.mu, out.std)          # batch [B,M]
        z = dist_z.rsample()                      # [B,M]
        p_norm = torch.sigmoid(z)                 # (0,1)
        power = p_norm * self.Pmax                # (0,Pmax)

        logp_z = dist_z.log_prob(z)               # [B,M]
        log_det = -math.log(self.Pmax) - torch.log(p_norm * (1.0 - p_norm) + self.eps)
        logp_p = logp_z + log_det                 # [B,M]

        logp = (logp_u + logp_p).sum(dim=-1)      # [B]

        ent_p = dist_z.entropy()                  # [B,M]
        entropy = (ent_u + ent_p).sum(dim=-1)     # [B]

        return {"users": users, "power": power, "logp": logp, "entropy": entropy}

    def evaluate(self, h: torch.Tensor, users: torch.Tensor, power: torch.Tensor) -> Dict[str, torch.Tensor]:
        out = self.forward(h)

        dist_u = Categorical(logits=out.logits)
        logp_u = dist_u.log_prob(users)           # [B,M]
        ent_u = dist_u.entropy()                  # [B,M]

        p_norm = (power / self.Pmax).clamp(self.eps, 1.0 - self.eps)
        z = logit(p_norm)

        dist_z = Normal(out.mu, out.std)
        logp_z = dist_z.log_prob(z)
        log_det = -math.log(self.Pmax) - torch.log(p_norm * (1.0 - p_norm) + self.eps)
        logp_p = logp_z + log_det

        logp_new = (logp_u + logp_p).sum(dim=-1)  # [B]

        ent_p = dist_z.entropy()
        entropy = (ent_u + ent_p).sum(dim=-1)     # [B]

        return {
            "logp_new": logp_new,
            "entropy": entropy,
            "logp_u_sum": logp_u.sum(dim=-1),
            "logp_p_sum": logp_p.sum(dim=-1),
        }
