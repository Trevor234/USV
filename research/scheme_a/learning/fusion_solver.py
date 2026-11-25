#!/usr/bin/env python3
"""融合 NMPC 求解器的 ctypes 绑定（唯一求解入口）。

真正的 OCP/融合语义在 C++（`usv_acados/src/acados_backend.cpp` + `fusion_capi.cpp`），
这里只做参数组装、内存布局与错误翻译。训练环境（P5.4）与回放校验（P5.5）都通过
本模块求解，禁止另写一份 Python 版 OCP。
"""
from __future__ import annotations

import ctypes
import json
import math
import os
from pathlib import Path

import numpy as np

DEFAULT_LIB_PATH = os.environ.get(
    "USV_ACADOS_LIB",
    "/home/trevor/usv_scheme_a_wt/install/scheme_a/usv_acados/lib/libusv_acados_backend.so",
)
N = 20
DT = 0.2
OBS_COLS = N + 1

# contract.json 的 hydro 段键顺序（与 C++ fill_hydro() 逐位一致）
HYDRO_KEYS = (
    "mass", "Iz", "xg", "d_thruster",
    "Xu_dot", "Yv_dot", "Yr_dot", "Nv_dot", "Nr_dot",
    "Xu", "Yv", "Yr", "Nv", "Nr",
    "Xuu", "Yvv", "Yrr", "Nvv", "Nrr",
)


class FusionSolverError(RuntimeError):
    """求解器返回非零状态或 C++ 侧抛出异常。"""


class FusionSolver:
    """一个独占的 dynamic 模型求解器实例（含热启动链）。"""

    def __init__(
        self,
        p_global,
        lower: float = -25.0,
        upper: float = 25.0,
        max_delta: float = 16.0,
        lib_path: str | None = None,
    ) -> None:
        arr = np.ascontiguousarray(np.asarray(p_global, dtype=np.float64).reshape(-1))
        if arr.size != 30:
            raise ValueError(f"p_global 必须是 30 维，实际 {arr.size}")
        if not np.all(np.isfinite(arr)):
            raise ValueError("p_global 含非有限值")
        self._lib = _load_lib(lib_path)
        self._handle = ctypes.c_void_p()
        rc = self._lib.p1_fusion_create(
            arr.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
            ctypes.c_double(float(lower)),
            ctypes.c_double(float(upper)),
            ctypes.c_double(float(max_delta)),
            ctypes.byref(self._handle),
        )
        if rc != 0 or not self._handle:
            raise FusionSolverError(self._last_error(f"p1_fusion_create rc={rc}"))
        self._closed = False

    # ------------------------------------------------------------------
    @classmethod
    def from_contract(cls, contract_path: Path, lib_path: str | None = None) -> "FusionSolver":
        """按运行目录 contract.json 的 hydro + Q/R/Rd/Qf_scale 组装 30 维 p_global。"""
        doc = json.loads(Path(contract_path).read_text(encoding="utf-8"))
        hydro = doc.get("hydro")
        if not isinstance(hydro, dict):
            raise ValueError(f"{contract_path} 缺少 hydro 段")
        missing = [k for k in HYDRO_KEYS if k not in hydro]
        if missing:
            raise ValueError(f"{contract_path} 的 hydro 段缺少参数: {missing}")
        q = list(doc.get("Q") or [])
        r = list(doc.get("R") or [])
        rd = list(doc.get("Rd") or [])
        if len(q) != 6 or len(r) != 2 or len(rd) != 2:
            raise ValueError(
                f"{contract_path} 的 Q/R/Rd 维度不符：Q={len(q)} R={len(r)} Rd={len(rd)}（需要 6/2/2）"
            )
        p_global = [float(hydro[k]) for k in HYDRO_KEYS] + [float(v) for v in q] + [
            float(v) for v in r
        ] + [float(v) for v in rd] + [float(doc.get("Qf_scale", 1.0))]
        t_max = float(doc.get("command_max_n", 25.0))
        t_min = float(doc.get("command_min_n", -25.0))
        dt = float(doc.get("dt", DT))
        d_t_max = float(doc.get("backend_rate_n_s", 80.0))
        return cls(p_global, lower=t_min, upper=t_max, max_delta=d_t_max * dt, lib_path=lib_path)

    # ------------------------------------------------------------------
    def solve(
        self,
        state6,
        ref,
        residuals,
        q_pi,
        lambda_pi: float,
    ) -> tuple[np.ndarray, float]:
        """求解一拍，返回 (u0[2], solve_ms)。ref=(6,N+1)，residuals=(3,N+1)。"""
        if self._closed:
            raise FusionSolverError("solver 已关闭")
        st = np.ascontiguousarray(np.asarray(state6, dtype=np.float64).reshape(-1))
        if st.size != 6:
            raise ValueError(f"state6 必须是 6 维，实际 {st.size}")
        ref_arr = np.asarray(ref, dtype=np.float64)
        res_arr = np.asarray(residuals, dtype=np.float64)
        if ref_arr.shape != (6, OBS_COLS):
            raise ValueError(f"ref 必须是 (6, {OBS_COLS})，实际 {ref_arr.shape}")
        if res_arr.shape != (3, OBS_COLS):
            raise ValueError(f"residuals 必须是 (3, {OBS_COLS})，实际 {res_arr.shape}")
        q = np.ascontiguousarray(np.asarray(q_pi, dtype=np.float64).reshape(-1))
        if q.size != 2:
            raise ValueError(f"q_pi 必须是 2 维，实际 {q.size}")
        if not math.isfinite(lambda_pi) or lambda_pi < 0.0:
            raise ValueError("lambda_pi 必须有限且 >= 0")
        # C++ 侧按行主序映射：C 顺序 (rows, cols) 连续内存即为行主序
        ref_c = np.ascontiguousarray(ref_arr)
        res_c = np.ascontiguousarray(res_arr)
        out_u0 = (ctypes.c_double * 2)()
        out_ms = ctypes.c_double(0.0)
        rc = self._lib.p1_fusion_solve(
            self._handle,
            st.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
            ref_c.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
            res_c.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
            q.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
            ctypes.c_double(float(lambda_pi)),
            out_u0,
            ctypes.byref(out_ms),
        )
        if rc != 0:
            raise FusionSolverError(self._last_error(f"p1_fusion_solve rc={rc}"))
        return np.array([out_u0[0], out_u0[1]], dtype=np.float64), float(out_ms.value)

    def set_anchor(self, anchor) -> None:
        """设定上一拍实际下发控制（生产顺序：reset → set_anchor → solve）。"""
        a = np.ascontiguousarray(np.asarray(anchor, dtype=np.float64).reshape(-1))
        if a.size != 2:
            raise ValueError(f"anchor 必须是 2 维，实际 {a.size}")
        self._lib.p1_fusion_set_anchor(
            self._handle, a.ctypes.data_as(ctypes.POINTER(ctypes.c_double))
        )
        err = self._last_error("")
        if err:
            raise FusionSolverError(err)

    def accept(self, anchor) -> None:
        a = np.ascontiguousarray(np.asarray(anchor, dtype=np.float64).reshape(-1))
        if a.size != 2:
            raise ValueError(f"anchor 必须是 2 维，实际 {a.size}")
        self._lib.p1_fusion_accept(
            self._handle, a.ctypes.data_as(ctypes.POINTER(ctypes.c_double))
        )
        err = self._last_error("")
        if err:
            raise FusionSolverError(err)

    def reset_warmstart(self) -> None:
        self._lib.p1_fusion_reset_warmstart(self._handle)
        err = self._last_error("")
        if err:
            raise FusionSolverError(err)

    def has_warmstart(self) -> bool:
        return bool(self._lib.p1_fusion_has_warmstart(self._handle))

    def close(self) -> None:
        if self._closed:
            return
        self._lib.p1_fusion_destroy(self._handle)
        self._handle = ctypes.c_void_p()
        self._closed = True

    def __del__(self) -> None:  # pragma: no cover - 解释器退出路径
        try:
            self.close()
        except Exception:
            pass

    def __enter__(self) -> "FusionSolver":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # ------------------------------------------------------------------
    def _last_error(self, fallback: str) -> str:
        raw = self._lib.p1_fusion_last_error()
        msg = raw.decode("utf-8", "replace") if raw else ""
        if msg:
            return msg
        return fallback


def _load_lib(lib_path: str | None) -> ctypes.CDLL:
    path = Path(lib_path or DEFAULT_LIB_PATH)
    if not path.is_file():
        raise FileNotFoundError(
            f"未找到融合求解器库 {path}；先执行 colcon build 构建 usv_acados，"
            "或用环境变量 USV_ACADOS_LIB 指定 libusv_acados_backend.so"
        )
    try:
        lib = ctypes.CDLL(str(path))
    except OSError as exc:  # pragma: no cover - 环境问题
        raise FusionSolverError(
            f"加载 {path} 失败: {exc}；确认 acados 运行库在 LD_LIBRARY_PATH 上"
        ) from exc

    lib.p1_fusion_create.restype = ctypes.c_int
    lib.p1_fusion_create.argtypes = [
        ctypes.POINTER(ctypes.c_double), ctypes.c_double, ctypes.c_double,
        ctypes.c_double, ctypes.POINTER(ctypes.c_void_p),
    ]
    lib.p1_fusion_destroy.restype = None
    lib.p1_fusion_destroy.argtypes = [ctypes.c_void_p]
    lib.p1_fusion_solve.restype = ctypes.c_int
    lib.p1_fusion_solve.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_double),   # state6
        ctypes.POINTER(ctypes.c_double),   # ref 6x21
        ctypes.POINTER(ctypes.c_double),   # res 3x21
        ctypes.POINTER(ctypes.c_double),   # q_pi
        ctypes.c_double,                   # lambda_pi
        ctypes.POINTER(ctypes.c_double),   # out_u0
        ctypes.POINTER(ctypes.c_double),   # out_solve_ms
    ]
    lib.p1_fusion_set_anchor.restype = None
    lib.p1_fusion_set_anchor.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_double)]
    lib.p1_fusion_accept.restype = None
    lib.p1_fusion_accept.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_double)]
    lib.p1_fusion_reset_warmstart.restype = None
    lib.p1_fusion_reset_warmstart.argtypes = [ctypes.c_void_p]
    lib.p1_fusion_has_warmstart.restype = ctypes.c_int
    lib.p1_fusion_has_warmstart.argtypes = [ctypes.c_void_p]
    lib.p1_fusion_last_error.restype = ctypes.c_char_p
    lib.p1_fusion_last_error.argtypes = []
    return lib
