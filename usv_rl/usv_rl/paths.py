"""运行产物目录解析 —— 唯一真源。

训练产物（models/ 与 runs/）不再放在 usv_rl/ 包内，而是集中到仓库顶层的
artifacts/ 下，与代码分离。需要覆盖位置时设 USV_ARTIFACTS_DIR。

本模块刻意不做「旧位置回退」：训练入口会自动 mkdir，若在找不到 artifacts/
时静默回落到 usv_rl/models，会让产物在两个位置各写一半且无从察觉。
"""
import os
from pathlib import Path

__all__ = ["PROJECT_ROOT", "ARTIFACTS_ROOT", "RL_MODELS", "RL_RUNS"]

# /home/trevor/USV （本文件是 <repo>/usv_rl/usv_rl/paths.py）
PROJECT_ROOT = Path(__file__).resolve().parents[2]

# 空字符串（`export USV_ARTIFACTS_DIR=`）视同未设置——否则 Path("") == "."，
# 产物会静默落到当前工作目录。相对路径按 cwd 解析后统一 resolve。
_override = os.environ.get("USV_ARTIFACTS_DIR", "").strip()
ARTIFACTS_ROOT = (
    Path(_override).expanduser() if _override else PROJECT_ROOT / "artifacts"
).resolve()

RL_MODELS = ARTIFACTS_ROOT / "rl_models"
RL_RUNS = ARTIFACTS_ROOT / "rl_runs"
