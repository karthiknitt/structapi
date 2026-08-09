"""Tests for the bar bending schedule (BBS) tabulation module."""

import math

import pytest

from iscodes import tables
from iscodes.design.beam import design_beam
from iscodes.design.column import design_column
from iscodes.design.slab import design_one_way_slab
from iscodes.quantities import bbs


# ---------------------------------------------------------------------------
# core helpers
# ---------------------------------------------------------------------------


def test_bar_unit_weight_hand_reference():
    assert bbs.bar_unit_weight_kg_m(12) == pytest.approx(0.888, abs=0.001)
    assert bbs.bar_unit_weight_kg_m(16) == pytest.approx(1.580, abs=0.001)
    assert bbs.bar_unit_weight_kg_m(8) == pytest.approx(0.395, abs=0.001)


def test_bend_allowance_factors():
    assert bbs.bend_allowance_mm(10, 45) == pytest.approx(10.0)
    assert bbs.bend_allowance_mm(10, 90) == pytest.approx(20.0)
    assert bbs.bend_allowance_mm(10, 135) == pytest.approx(30.0)


def test_bend_allowance_rejects_unsupported_angle():
    with pytest.raises(ValueError):
        bbs.bend_allowance_mm(10, 60)


def test_hook_allowance_u_hook():
    assert bbs.hook_allowance_mm(10) == pytest.approx(90.0)
    assert bbs.hook_allowance_mm(12, "u_hook") == pytest.approx(108.0)


def test_hook_allowance_rejects_unknown_type():
    with pytest.raises(ValueError):
        bbs.hook_allowance_mm(10, "fish_tail")


# ---------------------------------------------------------------------------
# beam_bar_marks
# ---------------------------------------------------------------------------


def _beam_result():
    return design_beam(span_m=6.0, w_dl_kn_m=10.0, w_il_kn_m=8.0,
                       b=300, D=500, fck=25, fy=500)


def test_beam_bar_marks_main_tension_cutting_length():
    r = _beam_result()
    marks = bbs.beam_bar_marks(r)
    tension = next(m for m in marks if m["mark"] == "beam-main-tension")

    bar_dia = r["design"]["bar_dia"]
    fck, fy = r["inputs"]["fck"], r["inputs"]["fy"]
    Ld = tables.development_length(bar_dia, fy, fck)
    expected_length = r["inputs"]["span_m"] * 1000.0 + 2 * Ld

    assert tension["dia_mm"] == bar_dia
    assert tension["count"] == r["design"]["n_bars"]
    assert tension["cutting_length_mm"] == pytest.approx(expected_length)
    assert tension["unit_weight_kg_m"] == pytest.approx(
        bbs.bar_unit_weight_kg_m(bar_dia))
    assert tension["total_weight_kg"] == pytest.approx(
        tension["unit_weight_kg_m"] * expected_length / 1000.0 * tension["count"])


def test_beam_bar_marks_no_compression_steel_when_singly_reinforced():
    r = _beam_result()
    assert r["design"]["n_bars_comp"] == 0
    marks = bbs.beam_bar_marks(r)
    assert not any(m["mark"] == "beam-main-compression" for m in marks)


def test_beam_bar_marks_stirrup_count_and_shape():
    r = _beam_result()
    marks = bbs.beam_bar_marks(r)
    stirrup = next(m for m in marks if m["mark"] == "beam-stirrup")

    sv = r["design"]["stirrups"]["sv_provided"]
    span_mm = r["inputs"]["span_m"] * 1000.0
    expected_count = math.ceil(span_mm / sv) + 1
    assert stirrup["count"] == expected_count
    assert stirrup["dia_mm"] == r["inputs"]["stirrup_dia"]

    b, D, cover = r["inputs"]["b"], r["inputs"]["D"], r["inputs"]["cover"]
    b_inner, D_inner = b - 2 * cover, D - 2 * cover
    stirrup_dia = r["inputs"]["stirrup_dia"]
    expected_cutting_length = (
        2 * (b_inner + D_inner)
        + 4 * bbs.bend_allowance_mm(stirrup_dia, 90)
        + 2 * bbs.hook_allowance_mm(stirrup_dia, "u_hook")
    )
    assert stirrup["cutting_length_mm"] == pytest.approx(expected_cutting_length)


def test_beam_bar_marks_seismic_stirrup_uses_135_hook():
    r = design_beam(span_m=6.0, w_dl_kn_m=10.0, w_il_kn_m=8.0,
                    b=300, D=500, fck=25, fy=500, seismic=True)
    marks_seismic = bbs.beam_bar_marks(r)
    stirrup_seismic = next(m for m in marks_seismic if m["mark"] == "beam-stirrup")

    r_ns = _beam_result()
    marks_ns = bbs.beam_bar_marks(r_ns)
    stirrup_ns = next(m for m in marks_ns if m["mark"] == "beam-stirrup")

    # Same section geometry -> the seismic (135 deg hook) cutting length
    # must differ from the non-seismic (u-hook) one.
    assert stirrup_seismic["cutting_length_mm"] != pytest.approx(
        stirrup_ns["cutting_length_mm"])


def test_beam_bar_marks_doubly_reinforced_adds_compression_mark():
    r = design_beam(span_m=8.0, w_dl_kn_m=30.0, w_il_kn_m=25.0,
                    b=250, D=400, fck=25, fy=500)
    assert r["design"]["doubly_reinforced"]
    marks = bbs.beam_bar_marks(r)
    comp = next(m for m in marks if m["mark"] == "beam-main-compression")
    assert comp["count"] == r["design"]["n_bars_comp"]
    assert comp["dia_mm"] == r["design"]["bar_dia"]


# ---------------------------------------------------------------------------
# Important 3 regression -- BBS must include the top (hogging) steel layer
# and use ductile stirrup spacing when seismic.
# ---------------------------------------------------------------------------

def _continuous_seismic_beam_result():
    from iscodes.analysis.beam import continuous_moments
    cm = continuous_moments(1.5 * 30.0, 1.5 * 20.0, 6.0)
    mu_span = max(abs(cm["M_span_end"]), abs(cm["M_span_interior"]))
    mu_sup = max(abs(cm["M_support_next_to_end"]),
                abs(cm["M_support_interior"]))
    return design_beam(span_m=6.0, w_dl_kn_m=30.0, w_il_kn_m=20.0,
                       b=300.0, D=550.0, fck=25.0, fy=500.0, support="fixed",
                       seismic=True, Mu_span_override_kNm=mu_span,
                       Mu_support_override_kNm=mu_sup)


def test_beam_bar_marks_includes_top_steel_layer():
    r = _continuous_seismic_beam_result()
    assert r["design"]["top_steel"]["n_bars"] > 0
    marks = bbs.beam_bar_marks(r)
    top = next(m for m in marks if m["mark"] == "beam-top-tension")
    assert top["count"] == r["design"]["top_steel"]["n_bars"]
    assert top["dia_mm"] == r["design"]["top_steel"]["bar_dia"]


def test_beam_bar_marks_total_weight_increases_with_top_steel():
    # Same beam with and without the top-steel bar mark included -- total
    # weight must visibly increase once the omission is fixed (previously
    # ~50% under-reported on a beam with a substantial hogging layer).
    r = _continuous_seismic_beam_result()
    marks = bbs.beam_bar_marks(r)
    total_with_top = sum(m["total_weight_kg"] for m in marks)
    total_without_top = sum(m["total_weight_kg"] for m in marks
                            if not m["mark"].startswith("beam-top"))
    assert total_with_top > total_without_top


def test_beam_bar_marks_uses_ductile_confining_spacing_when_seismic():
    r = _continuous_seismic_beam_result()
    ds = r["design"]["ductile_stirrups"]
    marks = bbs.beam_bar_marks(r)
    stirrup = next(m for m in marks if m["mark"] == "beam-stirrup")
    span_mm = r["inputs"]["span_m"] * 1000.0
    expected_count = math.ceil(
        span_mm / ds["confining_zone_spacing_mm"]) + 1
    assert stirrup["count"] == expected_count
    # sanity: confining-zone spacing is tighter (more stirrups) than the
    # plain IS 456 shear spacing would have given
    plain_count = math.ceil(
        span_mm / r["design"]["stirrups"]["sv_provided"]) + 1
    assert expected_count >= plain_count


# ---------------------------------------------------------------------------
# column_bar_marks
# ---------------------------------------------------------------------------


def test_column_bar_marks_main_and_ties():
    b, D, fck, fy = 300, 300, 25, 500
    n_bars, bar_dia, cover, tie_dia = 8, 16, 40, 8
    L_column_m = 3.0
    r = design_column(b=b, D=D, fck=fck, fy=fy, Pu_kN=800,
                      n_bars=n_bars, bar_dia=bar_dia, cover=cover,
                      tie_dia=tie_dia, L_unsupported_mm=L_column_m * 1000.0)
    assert r.ok

    marks = bbs.column_bar_marks(r, L_column_m, b, D, fck, fy, n_bars,
                                 bar_dia, cover, tie_dia)
    main = next(m for m in marks if m["mark"] == "column-main")
    Ld = tables.development_length(bar_dia, fy, fck)
    assert main["cutting_length_mm"] == pytest.approx(
        L_column_m * 1000.0 + 2 * Ld)
    assert main["count"] == n_bars

    tie = next(m for m in marks if m["mark"] == "column-tie")
    spacing = r.data["tie_pitch_max"]
    expected_count = math.ceil(L_column_m * 1000.0 / spacing) + 1
    assert tie["count"] == expected_count
    assert tie["dia_mm"] == tie_dia


def test_column_bar_marks_seismic_uses_confining_spacing():
    b, D, fck, fy = 300, 300, 25, 500
    n_bars, bar_dia, cover, tie_dia = 8, 16, 40, 8
    L_column_m = 3.0
    r = design_column(b=b, D=D, fck=fck, fy=fy, Pu_kN=500,
                      n_bars=n_bars, bar_dia=bar_dia, cover=cover,
                      tie_dia=tie_dia, L_unsupported_mm=L_column_m * 1000.0,
                      seismic=True)

    marks = bbs.column_bar_marks(r, L_column_m, b, D, fck, fy, n_bars,
                                 bar_dia, cover, tie_dia, seismic=True)
    tie = next(m for m in marks if m["mark"] == "column-tie")
    spacing = r.data["confine_spacing_max"]
    expected_count = math.ceil(L_column_m * 1000.0 / spacing) + 1
    assert tie["count"] == expected_count


# ---------------------------------------------------------------------------
# slab_bar_marks
# ---------------------------------------------------------------------------


def test_slab_bar_marks_straight_bars_with_hooks():
    r = design_one_way_slab(lx_m=3.5, w_dl=1.5, w_il=3.0, fck=25, fy=500,
                            support="ss")
    span_m = 3.5
    strip_width_m = 1.0
    bar_dia = 10
    cover = 20.0
    marks = bbs.slab_bar_marks(r["main"], span_m, strip_width_m, bar_dia, cover)
    assert len(marks) == 1
    mark = marks[0]

    spacing = r["main"]["spacing"]
    expected_count = math.floor(strip_width_m * 1000.0 / spacing) + 1
    expected_length = span_m * 1000.0 + 2 * bbs.hook_allowance_mm(bar_dia)
    assert mark["count"] == expected_count
    assert mark["cutting_length_mm"] == pytest.approx(expected_length)
    assert mark["dia_mm"] == bar_dia


# ---------------------------------------------------------------------------
# bbs_summary
# ---------------------------------------------------------------------------


def test_bbs_summary_aggregates_by_diameter_and_total():
    bar_marks = [
        {"mark": "a", "dia_mm": 12, "total_weight_kg": 10.0},
        {"mark": "b", "dia_mm": 12, "total_weight_kg": 5.0},
        {"mark": "c", "dia_mm": 8, "total_weight_kg": 2.5},
    ]
    summary = bbs.bbs_summary(bar_marks)
    assert summary["by_diameter_kg"][12] == pytest.approx(15.0)
    assert summary["by_diameter_kg"][8] == pytest.approx(2.5)
    assert summary["total_kg"] == pytest.approx(17.5)


def test_bbs_summary_end_to_end_from_beam():
    r = _beam_result()
    marks = bbs.beam_bar_marks(r)
    summary = bbs.bbs_summary(marks)
    assert summary["total_kg"] == pytest.approx(
        sum(m["total_weight_kg"] for m in marks))
    assert set(summary["by_diameter_kg"]) == {m["dia_mm"] for m in marks}
