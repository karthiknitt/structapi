"""Tests for the dog-legged waist-slab staircase module (IS 456 cl 33)."""

import math

from iscodes.design.staircase import design_staircase


def test_typical_g1_dog_legged_stair():
    r = design_staircase(going_m=2.5, riser_mm=150, tread_mm=275,
                         n_risers=10, landing_width_m=1.2,
                         fck=20.0, fy=415.0)
    assert r["ok"] is True
    assert r["L_eff_m"] == 2.5 + 1.2
    expected_slope = math.sqrt(1.0 + (150.0 / 275.0) ** 2)
    assert math.isclose(r["slope_factor"], expected_slope, rel_tol=1e-9)
    assert r["n_flights"] == 2
    assert r["n_risers"] == 10


def test_riser_tread_comfort_check_fires_for_uncomfortable_geometry():
    r_ok = design_staircase(going_m=2.5, riser_mm=150, tread_mm=275,
                            n_risers=10, landing_width_m=1.2)
    label, ok = r_ok["geometry_sanity_check"]
    assert "thumb rule, not a code clause" in label
    assert ok is True

    r_bad = design_staircase(going_m=2.5, riser_mm=220, tread_mm=275,
                             n_risers=10, landing_width_m=1.2)
    _, bad_ok = r_bad["geometry_sanity_check"]
    assert bad_ok is False


def test_waist_thickness_growth_loop():
    # going=4.0m, landing=1.5m -> initial trial thickness 225mm fails
    # (deflection), grows one 25mm step to 250mm and converges.
    r = design_staircase(going_m=4.0, riser_mm=150, tread_mm=275,
                         n_risers=15, landing_width_m=1.5)
    assert r["ok"] is True
    assert r["waist_thickness_mm"] > 225.0
    assert r["waist_thickness_mm"] % 25.0 == 0.0
