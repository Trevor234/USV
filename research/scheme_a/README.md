# Scheme A Commissioning Research Packages (Isolated)

This directory isolates the Scheme A research packages (`usv_nmpc`,
`usv_research_interfaces`, `usv_research_safety_cpp`) from the production
workspace under `src/` (which serves live Scheme B via
`/home/trevor/usv_mpc_ws/install`). `usv_acados` has been unified into the
shared top-level `src/usv_acados` package.

- **Origin**: Parent frozen candidate `scheme-a-clockdiag2-20261116T114727Z`,
  with the `scheme-a-commissioning-20261116T142713Z` additions and acceptance
  fixes F1–F2 (`check_shipboard_commissioning.py`, `test_p1_commissioning_checker.py`,
  and install-base discovery in `test_shipboard_commissioning.py`).
- **`COLCON_IGNORE`**: Prevents standard `colcon build` / `colcon list` from
  discovering the duplicate research `usv_nmpc` or `usv_research_*` packages or
  modifying the production `install/`.
- **Building**: Only build explicitly via `--base-paths src/usv_acados
  src/usv_bringup research/scheme_a/src` into isolated `--build-base`,
  `--install-base`, and `--log-base` directories (`*_scheme_a`), with
  `-DUSV_RESEARCH_TEST_SEAMS=OFF`.
- **Safety stance**: `shipboard_commissioning` is a zero-solve, zero-thrust
  service takeover mode (`physical_execute_release_enabled=false`,
  `physical_output_enabled=false`, `closed_loop_verified=false`), and the
  `p1-shipboard-execute-v1` / `research_execute` water execution locks remain
  `false` (`shipboard_water_execute_release_enabled=false`).
