#!/usr/bin/env python3
"""Apply the valid review findings.

1. enforce the plan's three known 2026-11-02 source hashes at ingestion
2. RPM branch: require mapping + varying response, not just finite coverage
3. RPM branch: replay must use the SAME per-group input model as fitting
4. replay must never borrow another hardware group's gains
5. status vocabulary: use only the plan's allowed values
6. accepted requires a FRESH holdout; a reused holdout caps at insufficient_holdout
"""
import re

P = "scripts/reidentify_20261102.py"
s = open(P, encoding="utf-8").read()


def sub(old, new, why):
    global s
    assert old in s, f"MISSING: {why}"
    s = s.replace(old, new, 1)


# ---------------------------------------------------------------- 1. hashes
sub('''HIST_ROLES = {''',
    '''# Frozen provenance of the three 2026-11-02 navigation logs (plan verification
# table).  Ingestion must compare against THESE, not merely against its own
# second read, otherwise a silently changed source would be accepted.
EXPECTED_SOURCES = {
    "2026-11-02 15-31-04.bin": (
        "7415f212b32ba8574cb35bdd53bbf3b7f0a3475aa1e84f70ec1ff48e1cacaec2", 27721728),
    "2026-11-02 16-00-09.bin": (
        "6c6c124402ca807a500b11a55c2444e05a1a43e7b836f5929cec54bd5e2d63fd", 31293440),
    "2026-11-02 16-19-57.bin": (
        "d9ea15ece3447354da5e682c13c2e09d9653c57da2e725e0c0f0d9b02815f68e", 21594112),
}

HIST_ROLES = {''', "expected source constants")

sub('''        sha = h.hexdigest()
        size = os.path.getsize(path)
        npz_path = os.path.join(npz_dir, sha[:20] + ".npz")
        rel = os.path.relpath(npz_path, out)
        z, pmeta = parse_source_to_npz(path, npz_path, expected_sha=sha)''',
    '''        sha = h.hexdigest()
        size = os.path.getsize(path)
        exp = EXPECTED_SOURCES.get(base)
        if exp is not None and (sha != exp[0] or size != exp[1]):
            manifest.append({"basename": base, "date": date, "path": path,
                             "size": size, "sha256": sha, "role": role,
                             "error": "source_changed",
                             "expected_sha256": exp[0], "expected_size": exp[1]})
            print(f"[prepare]  {base}: SOURCE CHANGED vs frozen provenance "
                  f"(sha {sha[:16]}… size {size}, expected {exp[0][:16]}… {exp[1]})")
            continue
        npz_path = os.path.join(npz_dir, sha[:20] + ".npz")
        rel = os.path.relpath(npz_path, out)
        z, pmeta = parse_source_to_npz(path, npz_path,
                                       expected_sha=(exp[0] if exp else sha))''',
    "source_changed gate")

# --------------------------------------------------- 2. RPM eligibility rules
sub('''def _rpm_eligible(segs):
    """Decide the group's input model BEFORE mutating anything."""
    if not segs:
        return False, 0.0
    covs = []
    for seg in segs:
        if seg.rpm.ndim != 2 or seg.rpm.shape[1] != 2 or seg.rpm.size == 0:
            return False, 0.0
        rl, rr = seg.rpm[:, 0], seg.rpm[:, 1]
        cov = float(np.mean(np.isfinite(rl) & np.isfinite(rr)))
        covs.append(cov)
        if cov < RPM_MIN_TRAIN_COVERAGE:
            return False, cov
    return True, min(covs)''',
    '''RPM_MIN_NONZERO_FRAC = 0.05
RPM_MIN_STD = 50.0


def _rpm_eligible(segs):
    """Decide the group's input model BEFORE mutating anything.

    Finite coverage is not sufficient: the telemetry must also be mapped to the
    two paddles and must actually vary with the output.  A constant-zero or
    unmapped RPM series would otherwise be selected and silently produce a
    zero-thrust model.
    """
    if not segs:
        return False, 0.0, "no_segments"
    covs = []
    for seg in segs:
        if seg.rpm.ndim != 2 or seg.rpm.shape[1] != 2 or seg.rpm.size == 0:
            return False, 0.0, "rpm_to_paddle_mapping_unresolved"
        rl, rr = seg.rpm[:, 0], seg.rpm[:, 1]
        fin = np.isfinite(rl) & np.isfinite(rr)
        cov = float(fin.mean())
        covs.append(cov)
        if cov < RPM_MIN_TRAIN_COVERAGE:
            return False, cov, "coverage_below_90pct"
        if int(fin.sum()) < 50:
            return False, cov, "too_few_rpm_samples"
        nz = min(float(np.mean(rl[fin] > 50.0)), float(np.mean(rr[fin] > 50.0)))
        if nz < RPM_MIN_NONZERO_FRAC:
            return False, cov, "rpm_does_not_vary_with_output"
        if max(float(np.std(rl[fin])), float(np.std(rr[fin]))) < RPM_MIN_STD:
            return False, cov, "rpm_constant"
    return True, min(covs), None''', "rpm eligibility")

sub('''def apply_input_model(segments_by_group):
    """Frozen per-group input model: RPM^2 where RPM qualifies, else equivalent PWM.

    The decision is made for the whole group first and applied atomically; a
    partially converted group would mix two thrust units.
    """
    decision = {}
    for g, segs in segments_by_group.items():
        eligible, cov = _rpm_eligible(segs)
        if eligible:
            for seg in segs:
                terms, _c = rpm_terms(seg)
                seg.terms = terms
            decision[g] = {"model": "rpm_squared", "unit": "N per RPM^2",
                           "min_coverage": float(cov)}
        else:
            decision[g] = {"model": "pwm_equivalent", "unit": "N at |q| = 1",
                           "min_coverage": float(cov),
                           "note": "ESC RPM absent, incomplete (<90%) or not resolvable"}
    return decision''',
    '''def apply_input_model(segments_by_group):
    """Frozen per-group input model: RPM^2 where RPM qualifies, else equivalent PWM.

    The decision is made for the whole group first and applied atomically; a
    partially converted group would mix two thrust units.
    """
    decision = {}
    for g, segs in segments_by_group.items():
        eligible, cov, why = _rpm_eligible(segs)
        if eligible:
            for seg in segs:
                terms, _c = rpm_terms(seg)
                seg.terms = terms
            decision[g] = {"model": "rpm_squared", "unit": "N per RPM^2",
                           "min_coverage": float(cov)}
        else:
            decision[g] = {"model": "pwm_equivalent", "unit": "N at |q| = 1",
                           "min_coverage": float(cov), "reason": why}
    return decision''', "apply_input_model signature")

# --------------------------------------- 3/4. model carries its input models
sub('''def model_dict(hydro, gains, kind):
    return {"kind": kind,
            "hydro": {k: float(hydro[k]) for k in HYDRO_KEYS},
            "gains": {g: [float(v) for v in gv] for g, gv in gains.items()}}''',
    '''def model_dict(hydro, gains, kind, input_models=None):
    return {"kind": kind,
            "hydro": {k: float(hydro[k]) for k in HYDRO_KEYS},
            "gains": {g: [float(v) for v in gv] for g, gv in gains.items()},
            "input_models": {g: (dict(v) if isinstance(v, dict) else v)
                             for g, v in (input_models or {}).items()}}''',
    "model_dict input_models")

sub('''def prior_model(p_base, group_names):
    g = prior_gain_vector(p_base)
    gains = {name: list(g) for name in group_names}
    return model_dict(p_base, gains, "baseline_prior")''',
    '''def prior_model(p_base, group_names):
    g = prior_gain_vector(p_base)
    gains = {name: list(g) for name in group_names}
    ims = {name: {"model": "pwm_equivalent", "unit": "N at |q| = 1"}
           for name in group_names}
    return model_dict(p_base, gains, "baseline_prior", ims)''', "prior_model input_models")

sub('''        "model": model_dict(hydro, gains, "identified"),''',
    '''        "model": model_dict(hydro, gains, "identified", input_models),''',
    "fit_model input_models")

# ---------------------------------------- 3/4. replay uses matching terms
start = s.index("def replay_windows(segments, model, win_s=REPLAY_WIN_S):")
end = s.index("def _group_of_segment(seg, gains):")
new_replay = '''def replay_windows(segments, model, win_s=REPLAY_WIN_S):
    """Independent replay; only the first state is taken from data.

    Each window is replayed with the SAME per-group input model that was used to
    fit that group (RPM^2 vs equivalent PWM).  A segment whose hardware group has
    no gains in this model is skipped and reported as not_evaluable: borrowing
    another group's thrust parameters would silently transplant a thruster model
    across the 2026-09-08 replacement.
    """
    n = int(round(win_s / DT))
    hold = max(1, int(round(CTRL_REFRESH_S / DT)))
    gains = model.get("gains") or {}
    ims = model.get("input_models") or {}
    hydro = dict(model["hydro"])
    d = hydro["d_thruster"]

    segs, starts, ends, gnames = [], [], [], []
    q_blocks, x0_blocks, obs_blocks = [], [], []
    skipped = {}
    for seg in segments:
        gm = seg.group if seg.group in gains else None
        if gm is None:
            skipped.setdefault(seg.group or "unknown", []).append(seg.sid)
            continue
        mode = (ims.get(gm) or {}).get("model", "pwm_equivalent")
        if mode == "rpm_squared":
            terms, _cov = rpm_terms(seg)
            if terms is None or not np.isfinite(terms).all():
                skipped.setdefault(gm, []).append(seg.sid)
                continue
        else:
            terms = seg.ui
        k = (len(seg) - 1) // n
        for i in range(k):
            a, b = i * n, (i + 1) * n
            segs.append(seg)
            starts.append(a)
            ends.append(b)
            gnames.append(gm)
            q_blocks.append(terms[a:b])
            x0_blocks.append(seg.x[a])
            obs_blocks.append(seg.x[a:b + 1])
    if not segs:
        return None

    X0 = np.stack(x0_blocks)
    OBS = np.stack(obs_blocks)
    Q = np.stack(q_blocks)
    idx = (np.arange(n) // hold) * hold
    Q = Q[:, idx, :]
    tau = np.empty((len(segs), n, 3))
    for i, gm in enumerate(gnames):
        tau[i:i + 1] = tau_from_q(Q[i:i + 1], gains[gm], d)
    sim = simulate(X0, tau, hydro)
    return {"segments": segs, "starts": starts, "ends": ends, "sim": sim,
            "obs": OBS, "Q": Q, "groups": gnames,
            "skipped_by_group": skipped,
            "not_evaluable_segments": sum(len(v) for v in skipped.values())}


'''
s = s[:start] + new_replay + s[end:]

sub('''def _group_of_segment(seg, gains):
    if seg.group in gains:
        return seg.group
    return None''',
    '''def _group_of_segment(seg, gains):
    """No fallback: an unmatched group has no usable propulsion model."""
    return seg.group if seg.group in gains else None''', "no group fallback")

sub('''    out = {"name": name, "n_windows": len(segs), "by_label": {}, "per_window": []}''',
    '''    out = {"name": name, "n_windows": len(segs),
           "not_evaluable_segments": res.get("not_evaluable_segments", 0),
           "skipped_by_group": res.get("skipped_by_group", {}),
           "by_label": {}, "per_window": []}''', "replay metrics not_evaluable")

# -------------------------------------------------- 5. allowed status values
sub('''    if bound > 0 and value >= 0.99 * bound:
        return "boundary_hit_no_shooting_ci"
    if abs(prior) > 1e-9 and value <= 0.01 * abs(prior):
        return "near_zero_no_shooting_ci"
    return "conditional_on_prior_no_shooting_ci"''',
    '''    # Only the plan's vocabulary is returned here.  Bound hits / near-zero
    # values are published as separate diagnostic fields, and the shooting
    # estimate's own uncertainty is `not_evaluable`, so such a parameter is
    # simply not a usable update.
    if bound > 0 and value >= 0.99 * bound:
        return "not_identifiable"
    if abs(prior) > 1e-9 and value <= 0.01 * abs(prior):
        return "not_identifiable"
    return "conditional_on_prior"''', "status vocabulary")

sub('''def _gain_status(gains, gi):
    """Qualification of one effective thrust scale.

    No identifiability claim is made here: left/right separation is decided by
    the design matrix, not by a magnitude threshold.  The paddle ratio is
    reported as a diagnostic alongside.
    """
    return "conditional_on_prior_no_shooting_ci"''',
    '''def _gain_status(gains, gi):
    """Qualification of one effective thrust scale.

    No identifiability claim is made: left/right separability is decided by the
    regression design, never by a magnitude threshold.  Ratios are diagnostics.
    """
    return "conditional_on_prior"''', "gain status vocabulary")

# ------------------------------------- 6. reused holdout cannot be accepted
sub('''def _gate(name, value, ok):''',
    '''def _holdout_verdict_cap(verdict, exposure):
    """An accepted result needs a FRESH independent holdout.

    A holdout that was already scored by an earlier pass cannot license
    `accepted`, however good the numbers look; the replay metrics are kept but
    the verdict is capped (§6: fresh independent blind test required).
    """
    if verdict == "accepted" and (exposure or {}).get("status") == \\
            "reused_after_prior_exposure":
        return "insufficient_holdout"
    return verdict


def _gate(name, value, ok):''', "holdout cap helper")

sub('''    elif failed:
        verdict = "rejected"
    else:
        verdict = "accepted"''',
    '''    elif failed:
        verdict = "rejected"
    else:
        verdict = "accepted"
    gates.append(_gate("fresh_independent_holdout", HOLDOUT_EXPOSURE.get("status"),
                       HOLDOUT_EXPOSURE.get("status") != "reused_after_prior_exposure"))
    verdict = _holdout_verdict_cap(verdict, HOLDOUT_EXPOSURE)
    if verdict == "insufficient_holdout":
        failed = failed or ["fresh_independent_holdout"]''', "verdict cap")

# ------------------------------------------- holdout window counting
sub('''def holdout_windows(segments, win_s=REPLAY_WIN_S):
    """Non-overlapping windows fully inside one segment."""
    wins = []
    n = int(round(win_s / DT))
    for seg in segments:
        k = len(seg) // n''',
    '''def holdout_windows(segments, win_s=REPLAY_WIN_S):
    """Non-overlapping windows fully inside one segment."""
    wins = []
    n = int(round(win_s / DT))
    for seg in segments:
        k = (len(seg) - 1) // n''', "holdout window count")

open(P, "w", encoding="utf-8").write(s)
print("patched", P)
