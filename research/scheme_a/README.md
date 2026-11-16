# Scheme A Commissioning Research Packages (Isolated)

This directory isolates the Scheme A `shipboard_commissioning` research packages
and their `usv_acados` / `usv_nmpc` capsule fork from the production workspace
under `src/` (which serves live Scheme B via `/home/trevor/usv_mpc_ws/install`).

- **Origin**: Parent frozen candidate `scheme-a-clockdiag2-20261116T114727Z`,
  with the `scheme-a-commissioning-20261116T142713Z` additions and acceptance
  fixes F1–F2 (`check_shipboard_commissioning.py`, `test_p1_commissioning_checker.py`,
  and install-base discovery in `test_shipboard_commissioning.py`).
- **`COLCON_IGNORE`**: Prevents standard `colcon build` / `colcon list` from
  discovering duplicate `usv_acados` or `usv_nmpc` packages or modifying the
  production `install/`.
- **Building**: Only build explicitly via `--base-paths research/scheme_a/src
  src/usv_bringup` into isolated `--build-base`, `--install-base`, and
  `--log-base` directories (`*_scheme_a`), with `-DUSV_RESEARCH_TEST_SEAMS=OFF`.
- **Safety stance**: `shipboard_commissioning` is a zero-solve, zero-thrust
  service takeover mode (`physical_execute_release_enabled=false`,
  `physical_output_enabled=false`, `closed_loop_verified=false`).
