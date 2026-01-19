# models/critic.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional, Sequence, Tuple

import torch
import torch.nn as nn
import torch.nn.functional as F


ActivationName = Literal["relu", "tanh", "elu", "gelu", "silu"]


@dataclass(frozen=True)
class CriticOutput:
    """
    Shared Critic (Local View) output.

    Attributes
    ----------
    V : torch.Tensor
        Value tensor with shape [B, N, 1].
    """
    V: torch.Tensor


def _get_activation(name: ActivationName) -> nn.Module:
    if name == "relu":
        return nn.ReLU(inplace=True)
    if name == "tanh":
        return nn.Tanh()
    if name == "elu":
        return nn.ELU()
    if name == "gelu":
        return nn.GELU()
    if name == "silu":
        return nn.SiLU(inplace=True)
    raise ValueError(f"Unsupported activation: {name}")


def _init_linear_(m: nn.Module, mode: Literal["xavier", "orthogonal"] = "xavier") -> None:
    """
    Initialize Linear layers. This is optional but helps stabilize early training.
    """
    if isinstance(m, nn.Linear):
        if mode == "xavier":
            nn.init.xavier_uniform_(m.weight)
        elif mode == "orthogonal":
            nn.init.orthogonal_(m.weight)
        else:
            raise ValueError(f"Unsupported init mode: {mode}")
        if m.bias is not None:
            nn.init.zeros_(m.bias)


class SharedCriticLocal(nn.Module):
    """
    Shared Critic (Local View)

    Definition
    ----------
    Input:  H in R^{B x N x D_h}
    Output: V in R^{B x N x 1}

    Local View meaning:
      V_{b,i} = f_psi(h_{b,i}),  where h_{b,i} is node embedding for agent i.
    All nodes share the same parameters (shared MLP value head).

    Parameters
    ----------
    d_h : int
        Node embedding dimension D_h (from GAT output).
    hidden_layers : Sequence[int]
        Hidden layer sizes for the shared MLP.
    activation : str
        Activation function name.
    dropout : float
        Dropout probability applied between hidden layers (0.0 disables).
    use_layernorm : bool
        Whether to apply LayerNorm after each Linear and before activation.
    init_mode : {"xavier", "orthogonal"}
        Linear layer initialization strategy.
    """

    def __init__(
        self,
        d_h: int,
        hidden_layers: Sequence[int] = (256, 256),
        activation: ActivationName = "relu",
        dropout: float = 0.0,
        use_layernorm: bool = False,
        init_mode: Literal["xavier", "orthogonal"] = "xavier",
    ) -> None:
        super().__init__()
        if d_h <= 0:
            raise ValueError(f"d_h must be positive, got {d_h}")
        if any(h <= 0 for h in hidden_layers):
            raise ValueError(f"hidden_layers must be positive ints, got {hidden_layers}")
        if not (0.0 <= dropout < 1.0):
            raise ValueError(f"dropout must be in [0, 1), got {dropout}")

        self.d_h = int(d_h)
        self.hidden_layers = tuple(int(x) for x in hidden_layers)
        self.activation_name: ActivationName = activation
        self.dropout_p = float(dropout)
        self.use_layernorm = bool(use_layernorm)

        act = _get_activation(activation)

        dims: Tuple[int, ...] = (self.d_h,) + self.hidden_layers
        blocks = []

        for in_dim, out_dim in zip(dims[:-1], dims[1:]):
            blocks.append(nn.Linear(in_dim, out_dim))
            if self.use_layernorm:
                blocks.append(nn.LayerNorm(out_dim))
            blocks.append(act)
            if self.dropout_p > 0.0:
                blocks.append(nn.Dropout(p=self.dropout_p))

        self.mlp = nn.Sequential(*blocks)
        self.value_head = nn.Linear(dims[-1], 1)

        # Initialize
        self.apply(lambda m: _init_linear_(m, mode=init_mode))

    def forward(self, H: torch.Tensor) -> CriticOutput:
        """
        Forward pass.

        Parameters
        ----------
        H : torch.Tensor
            Node embeddings with shape [B, N, D_h].

        Returns
        -------
        CriticOutput
            V with shape [B, N, 1].
        """
        if H.ndim != 3:
            raise ValueError(f"H must be rank-3 [B,N,D_h], got shape {tuple(H.shape)}")
        B, N, Dh = H.shape
        if Dh != self.d_h:
            raise ValueError(f"Expected last dim D_h={self.d_h}, got {Dh}")

        # Flatten [B,N,D_h] -> [(B*N),D_h]
        x = H.reshape(B * N, Dh).contiguous()

        # Shared MLP over nodes
        x = self.mlp(x)

        # Value head -> [(B*N), 1]
        v = self.value_head(x)

        # Restore [B,N,1]
        V = v.view(B, N, 1)
        return CriticOutput(V=V)

    @torch.no_grad()
    def value_of_agent(self, H: torch.Tensor, i: int) -> torch.Tensor:
        """
        Convenience method for debugging / single-agent view.

        Returns
        -------
        torch.Tensor
            V^{(i)} with shape [B, 1].
        """
        out = self.forward(H).V  # [B,N,1]
        if not (0 <= i < out.shape[1]):
            raise IndexError(f"agent index i out of range: i={i}, N={out.shape[1]}")
        return out[:, i, :]  # [B,1]


def critic_mse_loss(V: torch.Tensor, G: torch.Tensor, reduction: Literal["mean", "sum"] = "mean") -> torch.Tensor:
    """
    Critic MSE loss for value regression.

    Parameters
    ----------
    V : torch.Tensor
        Predicted values with shape [B, N, 1] (or broadcastable to that).
    G : torch.Tensor
        Target returns with shape [B, N, 1] (or broadcastable to that).
    reduction : {"mean", "sum"}
        Reduction over all elements.

    Returns
    -------
    torch.Tensor
        Scalar loss.
    """
    if V.shape != G.shape:
        # Allow broadcastable shapes, but enforce final rank compatibility.
        try:
            diff = V - G
        except RuntimeError as e:
            raise ValueError(f"V and G are not broadcastable: V={tuple(V.shape)}, G={tuple(G.shape)}") from e
    else:
        diff = V - G

    loss = diff.pow(2)
    if reduction == "mean":
        return loss.mean()
    if reduction == "sum":
        return loss.sum()
    raise ValueError(f"Unsupported reduction: {reduction}")


def critic_value_clip_loss(
    V_new: torch.Tensor,
    V_old: torch.Tensor,
    G: torch.Tensor,
    eps_v: float,
    reduction: Literal["mean", "sum"] = "mean",
) -> torch.Tensor:
    """
    Optional PPO-style value clipping loss.

    Definitions
    ----------
    V_clip = clip(V_new, V_old - eps_v, V_old + eps_v)
    L_v = max( (V_new - G)^2, (V_clip - G)^2 )

    Parameters
    ----------
    V_new : torch.Tensor
        Current critic prediction, shape [B,N,1].
    V_old : torch.Tensor
        Old critic prediction stored in buffer, shape [B,N,1].
    G : torch.Tensor
        Target return, shape [B,N,1].
    eps_v : float
        Value clip range (positive).
    reduction : {"mean", "sum"}
        Reduction over all elements.

    Returns
    -------
    torch.Tensor
        Scalar loss.
    """
    if eps_v <= 0:
        raise ValueError(f"eps_v must be positive, got {eps_v}")

    V_clip = torch.clamp(V_new, V_old - eps_v, V_old + eps_v)
    loss_unclipped = (V_new - G).pow(2)
    loss_clipped = (V_clip - G).pow(2)
    loss = torch.maximum(loss_unclipped, loss_clipped)

    if reduction == "mean":
        return loss.mean()
    if reduction == "sum":
        return loss.sum()
    raise ValueError(f"Unsupported reduction: {reduction}")
