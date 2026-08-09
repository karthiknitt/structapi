"""Tests for footing and slab design modules."""

import dataclasses

import pytest

from iscodes import tables
from iscodes.design import footing, slab


def test_sbc_phi30_hand_check():
    r = footing.safe_bearing_capacity(c_kpa=0, phi_deg=30, gamma=18,
                                      B=2, L=2, Df=1.5, FOS=2.5)
    f = tables.bearing_capacity_factors(30)
    assert f["Nq"] == pytest.approx(18.4, abs=0.1)
    assert 150 <= r["q_safe"] <= 400


def test_sbc_default_fos_is_3():
    r_default = footing.safe_bearing_capacity(c_kpa=0, phi_deg=30, gamma=18,
                                               B=2, L=2, Df=1.5)
    r_explicit = footing.safe_bearing_capacity(c_kpa=0, phi_deg=30, gamma=18,
                                                B=2, L=2, Df=1.5, FOS=3.0)
    assert r_default["FOS_used"] == 3.0
    assert r_default["load_tested"] is False
    assert r_default["q_safe"] == pytest.approx(r_default["qu_net"] / 3.0)
    assert r_default["q_safe"] == pytest.approx(r_explicit["q_safe"])


def test_sbc_load_tested_fos_is_2_5():
    r = footing.safe_bearing_capacity(c_kpa=0, phi_deg=30, gamma=18,
                                      B=2, L=2, Df=1.5, load_tested=True)
    assert r["FOS_used"] == 2.5
    assert r["load_tested"] is True
    assert r["q_safe"] == pytest.approx(r["qu_net"] / 2.5)


def test_sbc_explicit_fos_wins_over_load_tested():
    r = footing.safe_bearing_capacity(c_kpa=0, phi_deg=30, gamma=18,
                                      B=2, L=2, Df=1.5,
                                      load_tested=True, FOS=4.0)
    assert r["FOS_used"] == 4.0
    assert r["q_safe"] == pytest.approx(r["qu_net"] / 4.0)


def test_isolated_footing_textbook():
    r = footing.design_isolated_footing(P_service_kN=1000, M_service_kNm=0,
                                        sbc_kpa=200, col_b_mm=400,
                                        col_D_mm=400, fck=25, fy=500)
    d = dataclasses.asdict(r)
    area = d["data"]["L_m"] * d["data"]["B_m"]
    assert area == pytest.approx(5.5, rel=0.15)  # 1.1*1000/200
    assert 300 <= d["data"]["D_overall_mm"] <= 800
    assert r.ok, d["checks"]


def test_isolated_footing_with_moment_pressure_gradient():
    r = footing.design_isolated_footing(P_service_kN=1000, M_service_kNm=100,
                                        sbc_kpa=200, col_b_mm=400,
                                        col_D_mm=400, fck=25, fy=500)
    d = dataclasses.asdict(r)["data"]
    assert d["q_max_service_kPa"] > d["q_min_service_kPa"] >= 0
    assert d["q_max_service_kPa"] <= 200 * 1.01


def test_punching_within_limit():
    r = footing.design_isolated_footing(P_service_kN=1500, M_service_kNm=0,
                                        sbc_kpa=250, col_b_mm=450,
                                        col_D_mm=450, fck=30, fy=500)
    d = dataclasses.asdict(r)["data"]
    assert d["two_way_shear"]["tau_v"] <= d["two_way_shear"]["tau_lim"]


def test_combined_footing_centroid_and_hogging():
    r = footing.design_combined_footing(P1_kN=800, P2_kN=1200, spacing_m=4.0,
                                        sbc_kpa=200, col1_mm=400, col2_mm=400,
                                        fck=25, fy=500)
    assert r["resultant_from_col1_m"] == pytest.approx(2.4)
    assert abs(r["centroid_from_col1_m"] - 2.4) < 0.01
    assert r["M_hogging_kNm"] < 0          # top tension between columns
    assert r["ok"], r["checks"]
    assert 400 <= r["D_overall_mm"] <= 900  # economical beam-type depth


def test_one_way_slab():
    r = slab.design_one_way_slab(lx_m=3.5, w_dl=1.5, w_il=3.0,
                                 fck=25, fy=500, support="ss")
    assert 110 <= r["D_mm"] <= 180
    assert r["main"]["Ast_prov"] >= r["main"]["Ast_req"] - 1e-6
    assert r["main"]["spacing"] <= 300
    assert r["ok"], r["checks"]


def test_two_way_slab_case4():
    r = slab.design_two_way_slab(lx_m=4.0, ly_m=5.0, w_dl=1.5, w_il=3.0,
                                 fck=25, fy=500, case=4)
    c = tables.slab_coefficients(4, 1.25)
    assert r["strips"]["mid_short_x"]["alpha"] == pytest.approx(c["px"])
    # short-span steel >= long-span steel
    assert (r["strips"]["mid_short_x"]["Ast_req"]
            >= r["strips"]["mid_long_y"]["Ast_req"])
    assert r["torsion_note"] is not None
    assert r["ok"], r["checks"]


def test_two_way_slab_rejects_oblong():
    with pytest.raises(ValueError):
        slab.design_two_way_slab(lx_m=2.0, ly_m=5.0, w_dl=1.5, w_il=3.0,
                                 fck=25, fy=500)


# --- PC-6: long-edge trapezoidal shear check ------------------------------

def test_two_way_slab_long_edge_shear_hand_check():
    """Hand-derive Vu_long_edge = w_u*lx/2*(1-1/(2r)) for a genuinely
    oblong panel (r > 1) and confirm the function reproduces it.

    lx=4.0, ly=6.0 -> r=1.5. w_dl=1.5, w_il=3.0, fck=25, fy=500, D fixed
    at 200mm so w_self and w_u are pinned (no auto-depth-growth noise)."""
    D_mm = 200.0
    r = slab.design_two_way_slab(lx_m=4.0, ly_m=6.0, w_dl=1.5, w_il=3.0,
                                 fck=25, fy=500, case=4, D_mm=D_mm)
    ratio = ly_by_lx = r["ly_by_lx"]
    assert ratio == pytest.approx(1.5)
    w_self = D_mm / 1000.0 * 25.0
    w_u = 1.5 * (1.5 + w_self + 3.0)
    expected_long = w_u * 4.0 / 2.0 * (1.0 - 1.0 / (2.0 * 1.5))
    assert r["Vu_long_edge_kN"] == pytest.approx(expected_long)
    # sanity: matches (2*r-1)/(2*r) closed form too
    assert r["Vu_long_edge_kN"] == pytest.approx(
        w_u * 4.0 / 2.0 * (2 * 1.5 - 1) / (2 * 1.5))


def test_two_way_slab_long_edge_shear_square_panel_half_of_peak():
    """At r=1 (square panel) there is no physical short/long distinction,
    but the two reported quantities are different statistics of the same
    triangular/trapezoidal load pattern: the existing short-edge check
    reports the PEAK ordinate (w_u*lx/2); the new long-edge check reports
    the AVERAGE ordinate along the edge (w_u*lx/2*(1-1/(2r))). At r=1 the
    trapezoid degenerates into a triangle identical to the short edge's,
    so the average is exactly half the peak -- verified algebraically in
    slab.py's comment, confirmed numerically here. This is a documented
    deviation from a literal "the two values are equal at r=1" reading;
    see task-PC-6-report.md."""
    D_mm = 200.0
    r = slab.design_two_way_slab(lx_m=4.0, ly_m=4.0, w_dl=1.5, w_il=3.0,
                                 fck=25, fy=500, case=4, D_mm=D_mm)
    assert r["ly_by_lx"] == pytest.approx(1.0)
    assert r["Vu_long_edge_kN"] == pytest.approx(_short_edge_vu(r) / 2.0)


def _short_edge_vu(result: dict) -> float:
    """Reconstruct the existing (unchanged) short-edge peak Vu from the
    reported w_u and lx (via tau_v * d_x, back-solving avoids re-deriving
    lx from the result dict)."""
    return result["tau_v"] * 1000.0 * result["d_x_mm"] / 1e3


def test_two_way_slab_long_edge_shear_conservative_direction():
    """Conservative-direction finding (PC-6 acceptance criterion): for
    r in [1.0, 2.0], Vu_long_edge (average-based trapezoidal intensity)
    is always <= the existing short-edge Vu (peak-based triangular
    intensity), with equality only approached in the limit r -> inf and
    the ratio fixed at 0.5 for r=1. i.e. the OLD flat w*lx/2-everywhere
    approximation was always >= the new long-edge value -- it was already
    conservative (safe), just imprecise, for this average-intensity
    reading of the long edge. (See report for the alternate, peak-based
    reading under which the two edges are exactly equal, not merely
    Vu_long <= Vu_short.)"""
    for ly_m in (4.0, 4.4, 5.0, 6.0, 8.0):
        r = slab.design_two_way_slab(lx_m=4.0, ly_m=ly_m, w_dl=1.5,
                                     w_il=3.0, fck=25, fy=500, case=4,
                                     D_mm=200.0)
        short_edge_vu = _short_edge_vu(r)
        assert r["Vu_long_edge_kN"] <= short_edge_vu + 1e-9
        ratio = r["Vu_long_edge_kN"] / short_edge_vu
        assert 0.5 <= ratio <= 1.0


def test_two_way_slab_long_edge_shear_check_participates_in_ok():
    """The new check is wired into the same checks/ok mechanism as every
    other check in _two_way_once, so it participates in the auto-depth
    -growth loop in design_two_way_slab() automatically (no caller change
    needed, per the brief's scope note)."""
    r = slab.design_two_way_slab(lx_m=4.0, ly_m=6.0, w_dl=1.5, w_il=3.0,
                                 fck=25, fy=500, case=4)
    labels = [c[0] for c in r["checks"]]
    assert any("long edge" in c for c in labels)
    assert r["ok"], r["checks"]
    # existing short-edge check untouched: same label, still present
    assert "shear tau_v <= k*tau_c (cl 40.2.1.1)" in labels
