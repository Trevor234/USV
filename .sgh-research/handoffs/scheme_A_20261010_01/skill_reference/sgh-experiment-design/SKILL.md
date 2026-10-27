---
name: sgh-experiment-design
description: >
  Experiment design, simulation execution, and result analysis for SGH's
  research in control / USV / multi-agent formation / reinforcement learning /
  MPC. Three-phase loop: design (hypothesis + theory check + parameter matrix),
  execute (MATLAB / ROS2 / Python scaffolding, logging, parameter sweep), and
  retrospective (result analysis, mechanism diagnosis, next-step decision).
  Integrates with sgh-reading-notes for paper-informed experiment design and
  usv-lit-search for baseline comparison. Use when the user asks to design
  experiments, run simulations, set up parameter sweeps, analyze results, or says
  实验设计, 做实验, 仿真实验, 仿真, 跑仿真, 参数设置, 参数扫描, 对比实验,
  消融实验, 实验结果分析, 实验复盘, MATLAB, ROS2, Gazebo.
---

# SGH Experiment Design

Experiment design, simulation execution, and retrospective analysis for SGH's
research in control systems / USV / multi-agent formation / RL / MPC. Supports
three simulation environments: MATLAB/Simulink, ROS2 (Gazebo/UWSim), and Python.

## Core Architecture: Three-Phase Experiment Loop

Every experiment follows a three-phase loop inspired by the EDAgent control
loop. No phase is skipped. The loop gates whether to iterate or conclude.

```
Phase 1: DESIGN  -->  Phase 2: EXECUTE  -->  Phase 3: RETROSPECTIVE
  hypothesis            scaffold               result analysis
  theory check          env capture            mechanism diagnosis
  param matrix          run + log              next-step decision
  go / no-go            sweep                  iterate or conclude
       ^                                                |
       +------------------------------------------------+
                  (only if retro says iterate)
```

## Phase 1: Experiment Design

Before writing any code or running any simulation, formalize what you are
testing and why. This phase produces a design document that gates execution.

### 1.1 Hypothesis Formulation

Convert the research question into falsifiable hypotheses. Each hypothesis
must have:
- A clear statement (H1: "Distributed MPC achieves lower formation error
  than decentralized PD under wave disturbance JONSWAP Hs=1.5m")
- A disproof condition (what result would reject H1)
- Metrics that match the decision question (not just easy-to-collect metrics)
- At least one negative control or ablation when feasible

Write hypotheses to the experiment design note (see templates).

### 1.2 Theory Check (Veto Gate)

Before committing to a simulation run, check the proposal against control
theory and domain knowledge. This prevents running experiments that are
doomed by theory. Produce a verdict:

- **GO**: assumptions are sound, no theoretical contradictions
- **CONDITIONAL**: proceed only if specific conditions are met (list them)
- **NO-GO**: theoretical impossibility or invalid comparison

Domain-specific veto checks:
- MPC: Is the horizon length sufficient for stability? Are terminal
  ingredients correct? Is the problem feasible given constraints?
- RL: Is the MDP formulation correct? Is the reward free of reward hacking?
  Is the state observable? Is exploration safe?
- Formation: Is the communication graph connected? Is the formation
  geometry feasible given vehicle dynamics? Are collision constraints
  satisfiable?
- USV: Is the vehicle model appropriate (3-DOF vs 6-DOF)? Are environmental
  disturbances modeled? Are actuator saturations respected?

Reference: load `references/domain-metrics.md` for domain-specific theory
checks and evaluation metrics.

### 1.3 Simulation Environment Selection

Choose the simulation environment based on the experiment goal:

| Environment | Best for | Limitations |
|-------------|----------|-------------|
| MATLAB/Simulink | Control law design, MPC toolbox, rapid prototyping, analytical verification | Closed-source, license-dependent, limited multi-agent scalability |
| ROS2 + Gazebo/UWSim | Multi-agent scenarios, sensor simulation, realistic dynamics, colcon build system | Steeper setup, heavier compute, real-time constraints |
| Python (custom) | RL training (Gymnasium), algorithm prototyping, batch experiments, parameter sweeps | Must implement dynamics manually, less realistic physics |

Reference: load `references/simulation-environments.md` for detailed setup
guidance for each environment.

### 1.4 Parameter Matrix Design

Define the parameter sweep as a structured matrix. For each parameter:
- Name and symbol
- Default value
- Sweep range or list of values
- Type: independent variable / control variable / fixed parameter

Common USV/MPC/RL parameter groups:
- Vehicle: mass, length, drag coefficients, actuator limits
- MPC: horizon N, sample time Ts, weights Q/R, terminal cost P, constraints
- RL: learning rate, batch size, network architecture, reward weights,
  exploration noise, training episodes
- Formation: number of agents, communication topology, formation geometry,
  leader trajectory
- Environment: wave height/period, wind speed/direction, current velocity

### 1.5 Go / No-Go Decision

Before proceeding to execution, confirm:
- [ ] Hypotheses are falsifiable with explicit disproof conditions
- [ ] Theory check verdict is GO or CONDITIONAL (conditions listed)
- [ ] Simulation environment is selected and available
- [ ] Parameter matrix is complete (no undefined values)
- [ ] Baselines are identified (from usv-lit-search or prior experiments)
- [ ] Success/failure metrics are defined with thresholds
- [ ] Estimated runtime is acceptable

If any item fails, revise the design before proceeding.

Output: `<experiment-dir>/design.md` (see templates).

## Phase 2: Experiment Execution

### 2.1 Scaffold the Experiment

Use the scaffold script to create a self-contained experiment directory:

```bash
python scripts/new_experiment.py --name <slug> --env <matlab|ros2|python> --workspace <workspace-path>
```

This creates:
```
<workspace>/.sgh-research/experiments/<exp-id>/
  design.md              # experiment design note (from Phase 1)
  hypothesis_matrix.tsv  # hypothesis-experiment matrix
  params.json            # parameter configuration
  env_snapshot.json      # environment capture (auto-filled)
  commands.log           # all commands run (append-only)
  results/
    metrics.json         # quantitative results
    metrics.csv          # tabular results for comparison
    figures/             # plots and visualizations
    logs/                # raw simulation logs
  report.md              # final report (filled in Phase 3)
  retro.md               # retrospective (filled in Phase 3)
```

Each experiment is a self-contained package. Never write experiment artifacts
outside this directory unless explicitly requested.

### 2.2 Environment Capture

Before running, capture the simulation environment for reproducibility:

- **MATLAB**: version, toolbox licenses (Model Predictive Control Toolbox,
  Robotics System Toolbox, Simulink), Simulink version
- **ROS2**: distro (Humble/Iron/Jazzy), Gazebo version, colcon version,
  installed packages, workspace overlay
- **Python**: version, key packages (numpy, scipy, casadi, gymnasium,
  stable-baselines3, torch), CUDA availability

The scaffold script auto-fills `env_snapshot.json`. If the environment
changes between runs, re-capture and note the delta.

### 2.3 Run with Logging

Execute the simulation with full logging:

1. Append every command to `commands.log` with timestamp.
2. Save raw output to `results/logs/<run-tag>.log`.
3. Extract metrics to `results/metrics.json` and `results/metrics.csv`.
4. Save figures to `results/figures/`.
5. Use deterministic seeds where supported (MATLAB `rng()`, Python `np.random.seed()`,
   ROS2 simulation seed).

### 2.4 Parameter Sweep Management

For parameter sweeps, run each configuration as a separate sub-experiment:

```
<experiment-dir>/
  runs/
    config_001/          # first parameter set
      metrics.json
      logs/
    config_002/          # second parameter set
      metrics.json
      logs/
  results/
    metrics.csv          # aggregated across all configs
    sweep_summary.md     # comparison table
```

Track which config corresponds to which hypothesis (via hypothesis_matrix.tsv).

## Phase 3: Experiment Retrospective

After the simulation completes (or fails), perform a structured retrospective.

### 3.1 Result Consolidation

Extract the smallest set of outcome metrics that answer the hypotheses:

- Tracking error (RMSE, max, steady-state)
- Formation error (centroid deviation, inter-vehicle distance error)
- Settling time, overshoot
- Computation time per step (for real-time feasibility)
- Energy consumption / control effort
- Collision incidents count
- RL-specific: cumulative reward, sample efficiency, convergence episodes

Compare against baselines and prior experiments.

### 3.2 Mechanism Diagnosis

Diagnose WHY the result occurred, not just WHAT happened. Assign one primary
mechanism and optional secondary mechanisms:

- `model_mismatch`: vehicle model does not match real dynamics
- `controller_tuning`: MPC/RL parameters not appropriate for the scenario
- `constraint_violation`: constraints too tight or too loose
- `disturbance_dominant`: environmental disturbance overwhelmed the controller
- `communication_failure`: multi-agent communication assumptions violated
- `numerical_issue`: solver convergence, discretization, integration step
- `implementation_bug`: code error in the simulation
- `insufficient_training`: RL policy not converged
- `baseline_unfair`: baseline not properly tuned or different conditions

### 3.3 Next-Step Decision

Score improvement proposals for each candidate next action:
- Confidence (low/medium/high) — how sure are we this will help
- Impact (low/medium/high) — expected improvement magnitude
- Cost (low/medium/high) — time and compute to implement
- Risk (low/medium/high) — chance of regression or new issues

Decision rules:
- **Iterate**: if confidence >= medium AND impact >= medium AND risk acceptable
- **Collect more data**: if evidence is insufficient to decide
- **Conclude**: if hypotheses are answered (confirmed or rejected) and no
  high-value next step exists
- **Pivot**: if the result fundamentally changes the research direction

Output: `<experiment-dir>/retro.md` and `<experiment-dir>/report.md`.

## Integration with Other Skills

### From sgh-reading-notes

When a QDR note identifies actionable insights or methods to test, this skill
turns them into experiments. The QDR note's "Actionable Insights" section
directly feeds Phase 1 hypothesis formulation.

Flow: read paper (QDR) --> extract testable claims --> formulate hypotheses
--> design experiment --> run simulation --> compare with paper's results.

### From usv-lit-search

Ranked search results provide baselines for comparison. The "Top Picks" from
usv-lit-search that have been read (sgh-reading-notes QDR notes) become
candidate baselines in the experiment design.

### To manuscript-writing (future)

Experiment reports (`report.md`) with metrics, figures, and comparison tables
feed directly into manuscript drafts. The `results/metrics.csv` provides
data for result tables and figures.

## Domain Awareness

The skill understands USV/MPC/RL/control domain terminology and applies it
throughout the experiment lifecycle:

- **USV dynamics**: 3-DOF (surge, sway, yaw) vs 6-DOF, Fossen model,
  underactuated constraints, actuator saturation
- **MPC formulations**: centralized, distributed, consensus-based, robust,
  learning-based, terminal ingredients, recursive feasibility
- **RL methods**: SAC, PPO, DDPG, TD3, model-based RL, reward shaping,
  sim-to-real transfer, curriculum learning
- **Formation control**: leader-follower, virtual structure, behavioral,
  consensus-based, rigidity theory, collision avoidance
- **Stability**: Lyapunov-based, input-to-state stability (ISS), string
  stability for cascaded formations
- **Environment**: JONSWAP/Pierson-Moskowitz wave spectrum, wind models,
  ocean current models, wave disturbance forces

## Experiment Principles

- Every experiment must have a falsifiable hypothesis with a disproof condition.
- Theory check (veto gate) runs before any simulation. Never skip it.
- Each experiment is a self-contained package with env snapshot and full logging.
- Use deterministic seeds for reproducibility.
- Never fabricate results. If a simulation fails, record the failure.
- Distinguish simulation results from real-world expectations. Note the
  reality gap explicitly.
- Compare against at least one baseline whenever feasible.
- Record negative results. They are as valuable as positive ones.
- Default language follows the user's language. For Chinese output, use Simplified Chinese.
- Keep the first run small (smoke test) before scaling to full parameter sweeps.

## Scripts

### new_experiment.py

Scaffolds a new experiment directory with all required files and templates.

```bash
python scripts/new_experiment.py --name mpc_formation_wave --env matlab --workspace .
python scripts/new_experiment.py --name rl_collision_avoidance --env python --workspace .
python scripts/new_experiment.py --name multi_usv_gazebo --env ros2 --workspace .
```

Creates the full directory structure, fills `env_snapshot.json` with detected
environment info, and generates template `design.md` and `hypothesis_matrix.tsv`.

## References

| File | When to Load |
|------|-------------|
| references/experiment-templates.md | Templates for design note, report, retro |
| references/simulation-environments.md | MATLAB / ROS2 / Python setup and execution guidance |
| references/domain-metrics.md | USV / MPC / RL / formation evaluation metrics and theory checks |
