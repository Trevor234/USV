import numpy as np

from usv_planning import speed_profile, trajectory_optimizer


def test_speed_profile_respects_limits_and_time_monotonicity():
    s = np.linspace(0.0, 10.0, 21)
    kappas = np.full_like(s, 0.2)
    vs, rs, ts = speed_profile.compute_profile(
        kappas,
        s,
        u_max=1.0,
        r_max=0.3,
        a_lat_max=1.0,
        a_acc=0.5,
        a_dec=0.5,
        v_start=0.0,
        v_end=0.0,
        v_min=0.1,
    )
    assert len(vs) == len(s)
    assert len(rs) == len(s)
    assert len(ts) == len(s)
    assert np.all(vs <= 1.0 + 1e-9)
    assert np.all(np.abs(rs) <= 0.3 + 1e-9)
    assert np.all(np.diff(ts) >= 0.0)


def test_fillet_path_outputs_finite_geometry():
    xs, ys, psis, kappas, s, warnings = trajectory_optimizer.fillet_path(
        [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0)],
        turn_radius=2.0,
        resolution=0.5,
    )
    assert len(xs) >= 2
    assert len(xs) == len(ys) == len(psis) == len(kappas) == len(s)
    assert np.all(np.isfinite(xs))
    assert np.all(np.isfinite(ys))
    assert np.all(np.isfinite(psis))
    assert np.all(np.isfinite(kappas))
    assert np.all(np.diff(s) >= -1e-9)
    assert warnings == []
