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
