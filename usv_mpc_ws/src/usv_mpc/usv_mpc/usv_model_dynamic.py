"""3-DOF Fossen dynamic model for USV (Scheme B).

State:  [x, y, psi, u, v, r]  (6-DOF in NED + body)
Control: [T_L, T_R]           (left and right thruster forces, N)

M * dot_nu + C(nu)*nu + D(nu)*nu = tau
"""

import math
from typing import Optional

import casadi as ca
import numpy as np


class USVDynamicModel:
    """Fossen 3-DOF USV dynamic model with dual thrusters."""

    def __init__(
        self,
        dt: float = 0.1,
        rk4_substeps: int = 4,
        # Hull parameters
        mass: float = 30.0,
        Iz: float = 8.0,
        xg: float = 0.0,
        d_thruster: float = 0.3,
        # Added mass
        Xu_dot: float = -3.0,
        Yv_dot: float = -20.0,
        Yr_dot: float = -0.5,
        Nv_dot: float = -0.5,
        Nr_dot: float = -2.0,
        # Linear damping
        Xu: float = -8.0,
        Yv: float = -30.0,
        Yr: float = -1.0,
        Nv: float = -1.0,
        Nr: float = -5.0,
        # Quadratic damping
        Xuu: float = -15.0,
        Yvv: float = -60.0,
        Yrr: float = -1.0,
        Nvv: float = -1.0,
        Nrr: float = -3.0,
    ):
        self.dt = dt
        self.rk4_substeps = rk4_substeps

        # Store parameters for inspection
        self.mass = mass
        self.Iz = Iz
        self.xg = xg
        self.d_thruster = d_thruster
        self.Xu_dot = Xu_dot
        self.Yv_dot = Yv_dot
        self.Yr_dot = Yr_dot
        self.Nv_dot = Nv_dot
        self.Nr_dot = Nr_dot
        self.Xu = Xu
        self.Yv = Yv
        self.Yr = Yr
        self.Nv = Nv
        self.Nr = Nr
        self.Xuu = Xuu
        self.Yvv = Yvv
        self.Yrr = Yrr
        self.Nvv = Nvv
        self.Nrr = Nrr

        self._setup_casadi()

    def _setup_casadi(self):
        """Build CasADi symbolic functions for the dynamic model."""
        # State: [x, y, psi, u, v, r]
        x_s = ca.SX.sym("x")
        y_s = ca.SX.sym("y")
        psi_s = ca.SX.sym("psi")
        u_s = ca.SX.sym("u")
        v_s = ca.SX.sym("v")
        r_s = ca.SX.sym("r")
        states = ca.vertcat(x_s, y_s, psi_s, u_s, v_s, r_s)

        # Control: [T_L, T_R]
        TL = ca.SX.sym("TL")
        TR = ca.SX.sym("TR")
        controls = ca.vertcat(TL, TR)

        # Inertia matrix M (with added mass)
        m11 = self.mass - self.Xu_dot
        m22 = self.mass - self.Yv_dot
        m23 = self.mass * self.xg - self.Yr_dot
        m32 = self.mass * self.xg - self.Nv_dot
        m33 = self.Iz - self.Nr_dot

        M = ca.SX(3, 3)
        M[0, 0] = m11
        M[1, 1] = m22
        M[1, 2] = m23
        M[2, 1] = m32
        M[2, 2] = m33

        M_inv = ca.inv(M)

        # Coriolis matrix C(nu)
        c13 = -m22 * v_s - m23 * r_s
        c23 = m11 * u_s
        C = ca.SX(3, 3)
        C[0, 2] = c13
        C[1, 2] = c23
        C[2, 0] = -c13
        C[2, 1] = -c23

        # Damping matrix D(nu) — linear + quadratic
        D = ca.SX(3, 3)
        D[0, 0] = -self.Xu - self.Xuu * ca.fabs(u_s)
        D[1, 1] = -self.Yv - self.Yvv * ca.fabs(v_s)
        D[1, 2] = -self.Yr - self.Yrr * ca.fabs(r_s)
        D[2, 1] = -self.Nv - self.Nvv * ca.fabs(v_s)
        D[2, 2] = -self.Nr - self.Nrr * ca.fabs(r_s)

        # Thrust mapping: tau = B(theta) * [TL, TR]^T
        # tau_X = TL + TR, tau_Y = 0 (underactuated), tau_N = d*(TR - TL)
        tau = ca.vertcat(
            TL + TR,
            0,
            self.d_thruster * (TR - TL),
        )

        # Kinematics: dot_eta = J(psi) * nu
        nu = ca.vertcat(u_s, v_s, r_s)
        cos_psi = ca.cos(psi_s)
        sin_psi = ca.sin(psi_s)
        J = ca.SX(3, 3)
        J[0, 0] = cos_psi
        J[0, 1] = -sin_psi
        J[1, 0] = sin_psi
        J[1, 1] = cos_psi
        J[2, 2] = 1
        eta_dot = ca.mtimes(J, nu)

        # Dynamics: dot_nu = M^{-1} * (tau - C*nu - D*nu)
        Cnu = ca.mtimes(C, nu)
        Dnu = ca.mtimes(D, nu)
        nu_dot = ca.mtimes(M_inv, tau - Cnu - Dnu)

        rhs = ca.vertcat(eta_dot, nu_dot)
        self._f_continuous = ca.Function("f_dyn", [states, controls], [rhs])

        # RK4 discrete-time dynamics
        X0 = ca.SX.sym("X0", 6)
        U = ca.SX.sym("U", 2)
        X = X0
        h = self.dt / self.rk4_substeps
        for _ in range(self.rk4_substeps):
            k1 = self._f_continuous(X, U)
            k2 = self._f_continuous(X + h / 2 * k1, U)
            k3 = self._f_continuous(X + h / 2 * k2, U)
            k4 = self._f_continuous(X + h * k3, U)
            X = X + h / 6 * (k1 + 2 * k2 + 2 * k3 + k4)
        self._f_rk4 = ca.Function("f_rk4_dyn", [X0, U], [X])

    def forward(self, state: np.ndarray, control: np.ndarray) -> np.ndarray:
        """Evolve 6-DOF state forward by dt."""
        result = self._f_rk4(state, control)
        x_next = np.array(result).flatten()
        x_next[2] = math.atan2(math.sin(x_next[2]), math.cos(x_next[2]))
        return x_next

    def casadi_function(self) -> ca.Function:
        return self._f_rk4

    @property
    def n_states(self) -> int:
        return 6

    @property
    def n_controls(self) -> int:
        return 2
