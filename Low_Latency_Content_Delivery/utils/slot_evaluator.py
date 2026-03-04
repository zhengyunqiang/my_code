"""
Episode-level slot evaluator based on linear programming feasibility.

Given external carriage rates over time and per-user data demand, it solves a
series of LP feasibility problems to find the minimum number of timeslots that
can complete all users' transmissions.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple

import numpy as np
import torch
from scipy.optimize import linprog


@dataclass(frozen=True)
class SlotEvalResult:
    """Evaluation output for one episode batch."""
    min_slots: torch.Tensor      # [E], float32
    feasible_mask: torch.Tensor  # [E], bool


@dataclass(frozen=True)
class CarriageLPSolution:
    """Detailed LP solution for one carriage."""
    min_slots: int                    # first feasible tau, or T+1 when infeasible
    feasible: bool
    rate_vector: np.ndarray           # [T], external carriage rate
    demand_vector: np.ndarray         # [U], user demands
    slot_allocation: np.ndarray       # [T], sum_u r_in(u,t), padded by zeros after tau
    user_allocation: np.ndarray       # [U,T], padded by zeros after tau


@dataclass(frozen=True)
class EpisodeSlotDetail:
    """Detailed LP outputs for all envs and carriages."""
    # details[e][c] -> CarriageLPSolution
    details: List[List[CarriageLPSolution]]
    min_slots: torch.Tensor
    feasible_mask: torch.Tensor


class EpisodeSlotEvaluator:
    """
    Solve minimal completion slots with LP constraints.

    Variables (per carriage c, user u, slot t):
      r_{u,t}^{in} >= 0  (user's internal served rate)

    Constraints:
      1) r_{u,t}^{in} <= R_{c,t}^{out}
      2) sum_u r_{u,t}^{in} <= R_{c,t}^{out}
      3) sum_t r_{u,t}^{in} * dt >= D_u
    """

    def __init__(self, eps: float = 1e-8) -> None:
        self.eps = float(eps)

    def solve_episode(
        self,
        rate_history: torch.Tensor,      # [T, E, C]
        user_demands: torch.Tensor,      # [E, C, U]
        timeslot: float,
    ) -> SlotEvalResult:
        if rate_history.ndim != 3:
            raise ValueError(f"rate_history must be [T,E,C], got {tuple(rate_history.shape)}")
        if user_demands.ndim != 3:
            raise ValueError(f"user_demands must be [E,C,U], got {tuple(user_demands.shape)}")
        if timeslot <= 0:
            raise ValueError(f"timeslot must be > 0, got {timeslot}")

        T, E, C = rate_history.shape
        E2, C2, _ = user_demands.shape
        if E != E2 or C != C2:
            raise ValueError(
                f"shape mismatch: rate_history [T={T},E={E},C={C}] "
                f"vs user_demands [E={E2},C={C2},U]"
            )

        rates_np = rate_history.detach().cpu().numpy()
        demands_np = user_demands.detach().cpu().numpy()

        min_slots = np.full((E,), float(T + 1), dtype=np.float32)
        feasible = np.zeros((E,), dtype=np.bool_)

        for e in range(E):
            carriage_slots = []
            carriage_ok = True
            for c in range(C):
                s_c, ok_c = self._solve_one_carriage(
                    rates=rates_np[:, e, c],
                    demands=demands_np[e, c, :],
                    dt=float(timeslot),
                )
                carriage_slots.append(s_c)
                carriage_ok = carriage_ok and ok_c

            min_slots[e] = float(max(carriage_slots))
            feasible[e] = carriage_ok

        return SlotEvalResult(
            min_slots=torch.from_numpy(min_slots).to(rate_history.device),
            feasible_mask=torch.from_numpy(feasible).to(rate_history.device),
        )

    def solve_episode_with_details(
        self,
        rate_history: torch.Tensor,      # [T, E, C]
        user_demands: torch.Tensor,      # [E, C, U]
        timeslot: float,
    ) -> EpisodeSlotDetail:
        if rate_history.ndim != 3:
            raise ValueError(f"rate_history must be [T,E,C], got {tuple(rate_history.shape)}")
        if user_demands.ndim != 3:
            raise ValueError(f"user_demands must be [E,C,U], got {tuple(user_demands.shape)}")
        if timeslot <= 0:
            raise ValueError(f"timeslot must be > 0, got {timeslot}")

        T, E, C = rate_history.shape
        E2, C2, _ = user_demands.shape
        if E != E2 or C != C2:
            raise ValueError(
                f"shape mismatch: rate_history [T={T},E={E},C={C}] "
                f"vs user_demands [E={E2},C={C2},U]"
            )

        rates_np = rate_history.detach().cpu().numpy()
        demands_np = user_demands.detach().cpu().numpy()

        min_slots = np.full((E,), float(T + 1), dtype=np.float32)
        feasible = np.zeros((E,), dtype=np.bool_)
        all_details: List[List[CarriageLPSolution]] = []

        for e in range(E):
            carriage_details: List[CarriageLPSolution] = []
            carriage_slots = []
            carriage_ok = True
            for c in range(C):
                sol = self._solve_one_carriage_detail(
                    rates=rates_np[:, e, c],
                    demands=demands_np[e, c, :],
                    dt=float(timeslot),
                )
                carriage_details.append(sol)
                carriage_slots.append(sol.min_slots)
                carriage_ok = carriage_ok and sol.feasible

            min_slots[e] = float(max(carriage_slots))
            feasible[e] = carriage_ok
            all_details.append(carriage_details)

        return EpisodeSlotDetail(
            details=all_details,
            min_slots=torch.from_numpy(min_slots).to(rate_history.device),
            feasible_mask=torch.from_numpy(feasible).to(rate_history.device),
        )

    def _solve_one_carriage(
        self,
        rates: np.ndarray,    # [T]
        demands: np.ndarray,  # [U]
        dt: float,
    ) -> Tuple[int, bool]:
        rates = np.maximum(rates.astype(np.float64), 0.0)
        demands = np.maximum(demands.astype(np.float64), 0.0)
        T = rates.shape[0]
        U = demands.shape[0]

        # Progressive LP feasibility: tau = 1..T
        for tau in range(1, T + 1):
            cap_total = rates[:tau].sum() * dt
            if cap_total + self.eps < demands.sum():
                continue

            if self._is_feasible_lp(rates[:tau], demands, dt):
                return tau, True

        # Infeasible in full horizon.
        return T + 1, False

    def _is_feasible_lp(
        self,
        rates_tau: np.ndarray,   # [tau]
        demands: np.ndarray,     # [U]
        dt: float,
    ) -> bool:
        tau = rates_tau.shape[0]
        U = demands.shape[0]
        n_var = U * tau

        # Feasibility LP: min 0
        c_obj = np.zeros((n_var,), dtype=np.float64)

        A_ub = []
        b_ub = []

        # Constraint 2: sum_u r_{u,t}^{in} <= R_t^{out}
        for t in range(tau):
            row = np.zeros((n_var,), dtype=np.float64)
            for u in range(U):
                row[u * tau + t] = 1.0
            A_ub.append(row)
            b_ub.append(float(rates_tau[t]))

        # Constraint 3: sum_t r_{u,t}^{in} * dt >= D_u
        # -> -sum_t r_{u,t}^{in} <= -D_u / dt
        inv_dt = 1.0 / max(dt, self.eps)
        for u in range(U):
            row = np.zeros((n_var,), dtype=np.float64)
            for t in range(tau):
                row[u * tau + t] = -1.0
            A_ub.append(row)
            b_ub.append(float(-demands[u] * inv_dt))

        A_ub = np.asarray(A_ub, dtype=np.float64)
        b_ub = np.asarray(b_ub, dtype=np.float64)

        # Constraint 1 via bounds: 0 <= r_{u,t}^{in} <= R_t^{out}
        bounds = [(0.0, float(rates_tau[t])) for u in range(U) for t in range(tau)]

        res = linprog(
            c=c_obj,
            A_ub=A_ub,
            b_ub=b_ub,
            bounds=bounds,
            method="highs",
        )
        return bool(res.success)

    def _solve_one_carriage_detail(
        self,
        rates: np.ndarray,    # [T]
        demands: np.ndarray,  # [U]
        dt: float,
    ) -> CarriageLPSolution:
        rates = np.maximum(rates.astype(np.float64), 0.0)
        demands = np.maximum(demands.astype(np.float64), 0.0)
        T = rates.shape[0]
        U = demands.shape[0]

        best_tau = T + 1
        best_x = None

        for tau in range(1, T + 1):
            cap_total = rates[:tau].sum() * dt
            if cap_total + self.eps < demands.sum():
                continue

            success, x = self._solve_lp_with_solution(rates[:tau], demands, dt)
            if success:
                best_tau = tau
                best_x = x
                break

        slot_alloc = np.zeros((T,), dtype=np.float64)
        user_alloc = np.zeros((U, T), dtype=np.float64)
        feasible = best_x is not None

        if feasible:
            x_mat = best_x.reshape(U, best_tau)
            user_alloc[:, :best_tau] = x_mat
            slot_alloc[:best_tau] = x_mat.sum(axis=0)

        return CarriageLPSolution(
            min_slots=int(best_tau),
            feasible=bool(feasible),
            rate_vector=rates.copy(),
            demand_vector=demands.copy(),
            slot_allocation=slot_alloc,
            user_allocation=user_alloc,
        )

    def _solve_lp_with_solution(
        self,
        rates_tau: np.ndarray,   # [tau]
        demands: np.ndarray,     # [U]
        dt: float,
    ) -> Tuple[bool, np.ndarray | None]:
        tau = rates_tau.shape[0]
        U = demands.shape[0]
        n_var = U * tau

        c_obj = np.zeros((n_var,), dtype=np.float64)
        A_ub = []
        b_ub = []

        for t in range(tau):
            row = np.zeros((n_var,), dtype=np.float64)
            for u in range(U):
                row[u * tau + t] = 1.0
            A_ub.append(row)
            b_ub.append(float(rates_tau[t]))

        inv_dt = 1.0 / max(dt, self.eps)
        for u in range(U):
            row = np.zeros((n_var,), dtype=np.float64)
            for t in range(tau):
                row[u * tau + t] = -1.0
            A_ub.append(row)
            b_ub.append(float(-demands[u] * inv_dt))

        A_ub = np.asarray(A_ub, dtype=np.float64)
        b_ub = np.asarray(b_ub, dtype=np.float64)
        bounds = [(0.0, float(rates_tau[t])) for u in range(U) for t in range(tau)]

        res = linprog(
            c=c_obj,
            A_ub=A_ub,
            b_ub=b_ub,
            bounds=bounds,
            method="highs",
        )
        if not res.success or res.x is None:
            return False, None
        return True, res.x.astype(np.float64, copy=False)
