"""Tests for chajja/sunshade cantilever design (IS 456 cl 41 torsion demand)."""

import math

from iscodes.design.cantilever import design_chajja, design_parapet


def test_typical_chajja_uniform_thickness():
    """projection 0.75 m, 100 mm uniform, M20/Fe415 — hand-verified Mu/Vu."""
    r = design_chajja(0.75, 100.0)
    assert r.ok

    w_self = (100.0 / 1000.0) * 25.0  # rcc unit weight
    w_u = 1.5 * (w_self + 0.5 + 0.75)  # self + finish + LL
    Mu = w_u * 0.75 ** 2 / 2.0
    Vu = w_u * 0.75

    assert math.isclose(r.data["w_u_kN_m2"], w_u, rel_tol=1e-9)
    assert math.isclose(r.data["Mu_kNm"], Mu, rel_tol=1e-9)
    assert math.isclose(r.data["Vu_kN"], Vu, rel_tol=1e-9)


def test_tapered_uses_average_self_weight_but_root_thickness_for_d():
    """root 125mm, tip 75mm — self-weight from the average; d from the root."""
    r = design_chajja(0.75, 125.0, 75.0)
    assert r.ok

    D_avg = (125.0 + 75.0) / 2.0
    w_self_expected = (D_avg / 1000.0) * 25.0
    assert math.isclose(r.data["D_avg_mm"], D_avg)
    assert math.isclose(r.data["w_self_kN_m2"], w_self_expected, rel_tol=1e-9)

    # d must come from the ROOT thickness (125mm), not the 100mm average
    d_root_expected = 125.0 - 15.0 - 8.0 / 2.0  # cover=15, bar_dia=8 defaults
    assert math.isclose(r.data["d_root_mm"], d_root_expected, rel_tol=1e-9)
    assert r.data["D_root_mm"] == 125.0
    assert r.data["D_tip_mm"] == 75.0


def test_torsion_fields_match_hand_calculation():
    """Tu_per_m / Ve_addition / Me1_addition per IS 456 cl 41.3.1 / 41.4.2,
    for supporting_beam_width=230mm, depth=300mm (defaults)."""
    r = design_chajja(0.75, 100.0)

    w_self = (100.0 / 1000.0) * 25.0
    w_u = 1.5 * (w_self + 0.5 + 0.75)
    Mu = w_u * 0.75 ** 2 / 2.0

    b_beam_m = 230.0 / 1000.0
    D_beam_m = 300.0 / 1000.0
    Tu_per_m = Mu
    Ve_addition = 1.6 * Tu_per_m / b_beam_m
    Me1_addition = Tu_per_m * (1 + D_beam_m / b_beam_m) / 1.7

    assert math.isclose(r.data["Tu_per_m_kNm"], Tu_per_m, rel_tol=1e-9)
    assert math.isclose(r.data["Ve_addition_per_m_kN"], Ve_addition, rel_tol=1e-9)
    assert math.isclose(r.data["Me1_addition_per_m_kNm"], Me1_addition, rel_tol=1e-9)
    assert r.data["supporting_beam_width_mm"] == 230.0
    assert r.data["supporting_beam_depth_mm"] == 300.0
    assert "informational" in r.data["torsion_note"]


def test_torsion_fields_respect_custom_beam_dimensions():
    r = design_chajja(0.6, 100.0, supporting_beam_width_mm=300.0,
                      supporting_beam_depth_mm=450.0)
    Mu = r.data["Mu_kNm"]
    b_beam_m, D_beam_m = 0.3, 0.45
    expected_ve = 1.6 * Mu / b_beam_m
    expected_me1 = Mu * (1 + D_beam_m / b_beam_m) / 1.7
    assert math.isclose(r.data["Ve_addition_per_m_kN"], expected_ve, rel_tol=1e-9)
    assert math.isclose(r.data["Me1_addition_per_m_kNm"], expected_me1, rel_tol=1e-9)


def test_reinforces_top_face_not_bottom():
    """A cantilever's root moment is hogging — tension (and main steel) is on
    the TOP face. This must be asserted semantically, not just numerically,
    since a sign/face error here would silently produce a "valid-looking"
    but structurally wrong design (bottom steel resisting a hogging moment
    does nothing)."""
    r = design_chajja(0.75, 100.0)

    assert r.data["reinforced_face"] == "top"
    assert "top_steel" in r.data
    assert "bottom_steel" not in r.data

    # the check label itself must say "top", not "bottom" or generic "main"
    flexure_check_names = [name for name, _ in r.checks if "top" in name.lower()]
    assert flexure_check_names, "expected a flexure check explicitly labeled 'top'"
    assert not any("bottom" in name.lower() for name, _ in r.checks)


def test_minimum_and_distribution_steel_present():
    r = design_chajja(0.75, 100.0)
    assert r.data["top_steel"]["Ast_prov"] >= r.data["top_steel"]["Ast_min"]
    assert "distribution" in r.data
    assert r.data["distribution"]["Ast_req"] > 0


def test_deflection_uses_cantilever_basic_ratio():
    r = design_chajja(0.75, 100.0)
    defl = r.data["deflection"]
    # cantilever basic L/d = 7 (vs 20 ss / 26 continuous) before modification
    # factors; allowable must be well below the ss/continuous baselines for
    # the same span since only the cantilever base ratio applies.
    assert defl["allowable_L_by_d"] < 20.0
    assert defl["ok"]


# ---------------------------------------------------------------------------
# Parapet / handrail — IS 875-2 0.75 kN/m minimum lateral line load
# ---------------------------------------------------------------------------

def test_parapet_default_hand_computed_base_moment_shear():
    """height 1.0 m, 0.75 kN/m default lateral load -- hand-verified Mu/Vu
    for a point-load-at-tip vertical cantilever (M = W*h, V = W)."""
    r = design_parapet()
    W = 0.75
    h = 1.0
    Mu = 1.5 * W * h
    Vu = 1.5 * W
    assert math.isclose(r.data["Mu_kNm"], Mu, rel_tol=1e-9)
    assert math.isclose(r.data["Vu_kN"], Vu, rel_tol=1e-9)
    assert r.data["lateral_load_kN_per_m"] == 0.75
    assert r.data["height_m"] == 1.0


def test_parapet_taller_wall_scales_moment_linearly_with_height():
    """M = W*h at the base of a point-tip-load cantilever -- moment is
    linear in height for a fixed load, unlike a UDL cantilever (which is
    quadratic in the span)."""
    r1 = design_parapet(height_m=1.0, thickness_mm=200.0)
    r2 = design_parapet(height_m=2.0, thickness_mm=200.0)
    assert math.isclose(r2.data["Mu_kNm"], 2 * r1.data["Mu_kNm"], rel_tol=1e-9)
    # Vu is independent of height (same tip load, same base shear)
    assert math.isclose(r1.data["Vu_kN"], r2.data["Vu_kN"], rel_tol=1e-9)


def test_parapet_ok_with_reasonable_section():
    r = design_parapet(height_m=1.0, thickness_mm=150.0)
    assert r.ok, r.checks
    assert r.data["base_steel"]["Ast_prov"] >= r.data["base_steel"]["Ast_min"]
    assert "distribution" in r.data


def test_parapet_deflection_uses_cantilever_basic_ratio():
    r = design_parapet(height_m=1.0, thickness_mm=150.0)
    defl = r.data["deflection"]
    assert defl["allowable_L_by_d"] < 20.0
    assert defl["ok"]


def test_parapet_custom_lateral_load_overrides_default():
    r = design_parapet(height_m=1.1, lateral_kN_per_m=1.5)
    assert math.isclose(r.data["Mu_kNm"], 1.5 * 1.5 * 1.1, rel_tol=1e-9)
