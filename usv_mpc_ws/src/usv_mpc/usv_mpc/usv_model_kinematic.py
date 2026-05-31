"""3-DOF kinematic model for USV (Scheme A).

State: [x, y, psi] — NED position and heading
Control: [u_surge, r_yaw] — surge velocity and yaw rate

Uses CasADi for symbolic differentiation and RK4 integration.
"""

import math
from typing import Optional

import casadi as ca
import numpy as np


class USVKinematicModel:
    """USV kinematic model: dot_x = u*cos(psi), dot_y = u*sin(psi), dot_psi = r."""

    def __init__(self, dt: float = 0.2, rk4_substeps: int = 4):
        self.dt = dt
        self.rk4_substeps = rk4_substeps
        self._setup_casadi()

    def _setup_casadi(self):
        """Build CasADi symbolic functions for the kinematic model."""
        x = ca.SX.sym("x")
        y = ca.SX.sym("y")
        psi = ca.SX.sym("psi")
        states = ca.vertcat(x, y, psi)

        u_surge = ca.SX.sym("u_surge")
        r_yaw = ca.SX.sym("r_yaw")
        controls = ca.vertcat(u_surge, r_yaw)

        rhs = ca.vertcat(
            u_surge * ca.cos(psi),
            u_surge * ca.sin(psi),
            r_yaw,
        )
        self._f_continuous = ca.Function("f", [states, controls], [rhs])

        # RK4 discrete-time dynamics
        X0 = ca.SX.sym("X0", 3)
        U = ca.SX.sym("U", 2)
        X = X0
        h = self.dt / self.rk4_substeps
        for _ in range(self.rk4_substeps):
            k1 = self._f_continuous(X, U)
            k2 = self._f_continuous(X + h / 2 * k1, U)
            k3 = self._f_continuous(X + h / 2 * k2, U)
            k4 = self._f_continuous(X + h * k3, U)
            X = X + h / 6 * (k1 + 2 * k2 + 2 * k3 + k4)
        self._f_rk4 = ca.Function("f_rk4", [X0, U], [X])

    def forward(self, state: np.ndarray, control: np.ndarray) -> np.ndarray:
        """Evolve state forward by dt using RK4.

        Args:
            state: [x, y, psi]
            control: [u_surge, r_yaw]

        Returns:
            next_state: [x, y, psi]
        """
        result = self._f_rk4(state, control)
        x_next = np.array(result).flatten()
        x_next[2] = math.atan2(math.sin(x_next[2]), math.cos(x_next[2]))
        return x_next

    def casadi_function(self) -> ca.Function:
        """Return the CasADi discrete dynamics function."""
        return self._f_rk4

    @property
    def n_states(self) -> int:
        return 3

    @property
    def n_controls(self) -> int:
        return 2
