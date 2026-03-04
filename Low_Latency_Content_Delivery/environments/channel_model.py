# environments/channel_model.py
"""
Realistic channel models for wireless communication.

Includes:
  - Path loss models (Okumura-Hata, COST-231)
  - Small-scale fading (Rayleigh, Rician, Nakagami)
  - Doppler shift for high-mobility scenarios
  - Shadowing
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

import torch
import torch.nn as nn
import numpy as np


@dataclass
class ChannelConfig:
    """Channel model configuration."""
    # Carrier frequency (GHz)
    fc: float = 2.1
    # Base station height (m)
    h_bs: float = 30
    # User height (m)
    h_ue: float = 1.5
    # Path loss exponent
    gamma: float = 2.5
    # Shadowing standard deviation (dB)
    sigma_shadow: float = 8.0
    # Fading model: 'rayleigh', 'rician', 'nakagami'
    fading_model: str = 'rician'
    # Rician K-factor (dB)
    K_factor: float = 10.0
    # Vehicle speed (km/h) for Doppler
    speed_kmh: float = 300.0
    # Timeslot duration (s)
    timeslot: float = 0.01
    # Number of multipath components
    num_paths: int = 20


class PathLossModel:
    """
    Path loss models for different scenarios.

    Supports:
      - Free space path loss
      - Okumura-Hata model (urban)
      - COST-231 Hata model
    """

    @staticmethod
    def free_space(d_km: torch.Tensor, fc_ghz: float) -> torch.Tensor:
        """
        Free space path loss.

        PL(dB) = 20*log10(d_km) + 20*log10(fc_MHz) + 32.44
        """
        fc_mhz = fc_ghz * 1000
        pl_db = 20 * torch.log10(d_km + 1e-9) + 20 * math.log10(fc_mhz) + 32.44
        return pl_db

    @staticmethod
    def okumura_hata(
        d_km: torch.Tensor,
        fc_ghz: float,
        h_bs: float,
        h_ue: float,
        urban: bool = True,
    ) -> torch.Tensor:
        """
        Okumura-Hata path loss model.

        For urban area:
          PL = 69.55 + 26.16*log10(fc) - 13.82*log10(h_bs)
               - a(h_ue) + (44.9 - 6.55*log10(h_bs))*log10(d)

        For suburban: PL_urban - 2*[log10(fc/28)]^2 - 5.4
        For rural: PL_urban - 4.79*[log10(fc)]^2 - 18.33*log10(fc) - 40.94
        """
        fc_mhz = fc_ghz * 1000
        log_fc = math.log10(fc_mhz)
        log_hbs = math.log10(h_bs)

        # Correction factor for mobile antenna height
        a_h_ue = (
            3.2 * (math.log10(11.75 * h_ue) ** 2)
            - 4.97
        )

        # Urban path loss
        pl = (
            69.55
            + 26.16 * log_fc
            - 13.82 * log_hbs
            - a_h_ue
            + (44.9 - 6.55 * log_hbs) * torch.log10(d_km + 1e-9)
        )

        if not urban:
            # Suburban/rural correction
            pl = pl - 2 * (math.log10(fc_mhz / 28) ** 2) - 5.4

        return pl

    @staticmethod
    def cost231(
        d_km: torch.Tensor,
        fc_ghz: float,
        h_bs: float,
        h_ue: float,
        urban: bool = True,
    ) -> torch.Tensor:
        """
        COST-231 Hata model for 1.5-2 GHz.

        Extends Okumura-Hata to 2 GHz.
        """
        pl = PathLossModel.okumura_hata(d_km, fc_ghz, h_bs, h_ue, urban)

        # Additional correction for COST-231
        if fc_ghz > 1.5:
            pl = pl + 3 * (math.log10(fc_ghz * 1000 / 28) ** 2)

        return pl


class FadingModel:
    """
    Small-scale fading models.

    Supports:
      - Rayleigh (NLOS)
      - Rician (LOS with dominant path)
      - Nakagami-m
    """

    def __init__(self, cfg: ChannelConfig, device: torch.device):
        self.cfg = cfg
        self.device = device

    def generate_fading(self, shape: torch.Size, seed: Optional[int] = None) -> torch.Tensor:
        """
        Generate fading coefficients.

        Returns:
            Complex fading coefficients with shape [shape]
        """
        if self.cfg.fading_model == "rayleigh":
            return self._rayleigh(shape, seed)
        elif self.cfg.fading_model == "rician":
            return self._rician(shape, seed)
        elif self.cfg.fading_model == "nakagami":
            return self._nakagami(shape, seed)
        else:
            raise ValueError(f"Unknown fading model: {self.cfg.fading_model}")

    def _rayleigh(self, shape: torch.Size, seed: Optional[int] = None) -> torch.Tensor:
        """Rayleigh fading (NLOS)."""
        if seed is not None:
            torch.manual_seed(seed)

        # h = (X + jY) / sqrt(2) where X, Y ~ N(0,1)
        h_real = torch.randn(shape, device=self.device)
        h_imag = torch.randn(shape, device=self.device)
        h = (h_real + 1j * h_imag) / np.sqrt(2)
        return h

    def _rician(self, shape: torch.Size, seed: Optional[int] = None) -> torch.Tensor:
        """
        Rician fading (LOS with dominant component).

        K-factor: ratio of LOS power to scattered power
        """
        if seed is not None:
            torch.manual_seed(seed)

        K_linear = 10 ** (self.cfg.K_factor / 10)

        # LOS component (deterministic)
        h_los = math.sqrt(K_linear / (1 + K_linear))

        # Scattered component (Rayleigh)
        h_real = torch.randn(shape, device=self.device)
        h_imag = torch.randn(shape, device=self.device)
        h_scattered = (h_real + 1j * h_imag) / math.sqrt(2 * (1 + K_linear))

        return h_los + h_scattered

    def _nakagami(self, shape: torch.Size, seed: Optional[int] = None) -> torch.Tensor:
        """
        Nakagami-m fading (generalizes Rayleigh).

        m=1 is Rayleigh, m->inf is AWGN.
        """
        if seed is not None:
            torch.manual_seed(seed)

        # For simplicity, use m=2 as default
        m = 2.0

        # Gamma distribution for envelope
        gamma = torch.distributions.Gamma(m, 1/m)
        envelope = gamma.sample(shape).to(self.device)

        # Random phase
        phase = torch.rand(shape, device=self.device) * 2 * np.pi

        return envelope * torch.exp(1j * phase)


class DopplerModel:
    """
    Doppler effect model for high-mobility scenarios.

    Models time-varying channel due to vehicle movement.
    """

    def __init__(self, cfg: ChannelConfig, device: torch.device):
        self.cfg = cfg
        self.device = device

        # Calculate Doppler frequency
        # fd = v * fc / c
        # v: speed (m/s), fc: carrier frequency (Hz), c: 3e8 m/s
        v_ms = cfg.speed_kmh / 3.6
        fc_hz = cfg.fc * 1e9
        c = 3e8
        self.fd = v_ms * fc_hz / c

    def get_correlation_matrix(self, num_taps: int) -> torch.Tensor:
        """
        Get temporal correlation matrix for Jakes model.

        Returns:
            Correlation matrix [num_taps, num_taps]
        """
        # Time delays
        t = torch.arange(num_taps, device=self.device) * self.cfg.timeslot

        # Jakes spectrum correlation
        # rho(tau) = J0(2*pi*fd*tau)
        tau = t.unsqueeze(0) - t.unsqueeze(1)  # [num_taps, num_taps]
        rho = torch.special.bessel_j0(2 * np.pi * self.fd * tau.abs())

        return rho


class RealisticChannel:
    """
    Complete channel model with path loss, shadowing, and fading.

    Combines:
      - Path loss (distance-dependent)
      - Shadowing (log-normal)
      - Small-scale fading (Rayleigh/Rician/Nakagami)
      - Doppler (time correlation)
    """

    def __init__(self, cfg: ChannelConfig, device: torch.device):
        self.cfg = cfg
        self.device = device

        self.pathloss = PathLossModel()
        self.fading = FadingModel(cfg, device)
        self.doppler = DopplerModel(cfg, device)

        # Pre-generate correlation matrix for efficiency
        self.max_taps = 100
        self.corr_matrix = self.doppler.get_correlation_matrix(self.max_taps)

    def compute_gain(
        self,
        distance: torch.Tensor,  # [E, ...] in meters
        timestep: int = 0,
        seed: Optional[int] = None,
    ) -> torch.Tensor:
        """
        Compute channel gain including all effects.

        Args:
            distance: Distance in meters [E, N, M]
            timestep: Current timestep (for Doppler)
            seed: Random seed

        Returns:
            Channel gain (linear scale) [E, N, M]
        """
        # Convert to km for path loss
        d_km = distance / 1000.0

        # Path loss (dB)
        pl_db = self.pathloss.okumura_hata(
            d_km,
            self.cfg.fc,
            self.cfg.h_bs,
            self.cfg.h_ue,
        )

        # Shadowing (log-normal, dB)
        if seed is not None:
            torch.manual_seed(seed)
        shadowing_db = torch.randn_like(pl_db) * self.cfg.sigma_shadow

        # Total loss in dB
        total_loss_db = pl_db + shadowing_db

        # Convert to linear
        large_scale = 10 ** (-total_loss_db / 10)

        # Small-scale fading
        h_fading = self.fading.generate_fading(distance.shape, seed)
        small_scale = torch.abs(h_fading) ** 2

        # Combine
        gain = large_scale * small_scale

        return gain

    def compute_sinr(
        self,
        power: torch.Tensor,           # [E, N, M] transmit power
        distance: torch.Tensor,         # [E, N, M] distance
        interference_power: torch.Tensor,  # [E, N, M] interference
        noise_density: float = 1e-9,   # W/Hz
        bandwidth: float = 10e6,       # Hz
    ) -> torch.Tensor:
        """
        Compute SINR (Signal-to-Interference-plus-Noise Ratio).

        Args:
            power: Transmit power per subchannel
            distance: Distance from BS to UE
            interference_power: Power from interfering BSs
            noise_density: Noise power spectral density
            bandwidth: Subchannel bandwidth

        Returns:
            SINR in linear scale
        """
        # Channel gain
        gain = self.compute_gain(distance)

        # Signal power
        signal_power = power * gain

        # Noise power
        noise_power = noise_density * bandwidth

        # SINR
        sinr = signal_power / (interference_power + noise_power + 1e-9)

        return sinr


def create_channel_model(
    cfg: Optional[ChannelConfig] = None,
    device: torch.device = torch.device("cpu"),
) -> RealisticChannel:
    """Factory function to create a channel model."""
    if cfg is None:
        cfg = ChannelConfig()
    return RealisticChannel(cfg, device)
