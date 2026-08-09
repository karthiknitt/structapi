"""Tests for iscodes.rounding (Site-Standard 25) and its adoption at the
touch points listed in task PA-4."""

import pytest

from iscodes import rounding
from iscodes.design import footing, shear, slab


# ---------------------------------------------------------------------------
# 1. Property tests on the utility itself — this IS the enforcement
#    mechanism the sprint's rounding rule requires.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("x,cap", [(235, None), (389, None), (235, 300),
                                    (312, 300), (10, None), (25, None)])
def test_site_spacing_never_exceeds_input_or_cap(x, cap):
    r = rounding.site_spacing(x, cap)
    assert r % 25 == 0
    assert r <= x
    if cap is not None:
        assert r <= cap


@pytest.mark.parametrize("x", [385, 235, 25, 401, 1])
def test_site_dimension_never_undershoots_input(x):
    r = rounding.site_dimension(x)
    assert r % 25 == 0
    assert r >= x


# ---------------------------------------------------------------------------
# 2. Worked-value regression tests — literal examples from the source plan.
# ---------------------------------------------------------------------------

def test_site_spacing_worked_values():
    assert rounding.site_spacing(235) == 225
    assert rounding.site_spacing(389) == 375


def test_site_dimension_worked_values():
    assert rounding.site_dimension(385) == 400
    assert rounding.site_dimension(235) == 250


# ---------------------------------------------------------------------------
# 3. Touch-point spot checks — prove adoption at real call sites.
# ---------------------------------------------------------------------------

def test_shear_design_stirrups_spacing_on_25mm_grid():
    r = shear.design_stirrups(Vu_N=150e3, b=300.0, d=450.0, fck=25.0,
                              fy=415.0, Ast_mm2=1200.0)
    assert r["ok"]
    assert r["sv_provided"] % 25 == 0


def test_slab_spacing_for_on_25mm_grid():
    s = slab._spacing_for(ast_req_per_m=800.0, dia=10, cap=300.0)
    assert s % 25 == 0


def test_one_way_slab_end_to_end_on_25mm_grid():
    result = slab.design_one_way_slab(lx_m=3.0, w_dl=1.5, w_il=3.0,
                                      fck=25.0, fy=415.0)
    assert result["D_mm"] % 25 == 0
    assert result["main"]["spacing"] % 25 == 0


def test_footing_bar_for_strip_on_25mm_grid():
    b = footing._bar_for_strip(ast_per_m=900.0)
    assert b["spacing"] % 25 == 0


def test_isolated_footing_end_to_end_on_25mm_grid():
    r = footing.design_isolated_footing(P_service_kN=800.0, M_service_kNm=40.0,
                                        sbc_kpa=150.0, col_b_mm=400.0,
                                        col_D_mm=400.0, fck=25.0, fy=415.0)
    assert (r.data["L_m"] * 1000.0) % 25 == pytest.approx(0.0, abs=1e-6)
    assert (r.data["B_m"] * 1000.0) % 25 == pytest.approx(0.0, abs=1e-6)
    assert r.data["D_overall_mm"] % 25 == 0
