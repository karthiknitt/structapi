"""Tests for mix design, detailing, and report modules."""

import pytest

from iscodes import detailing, report
from iscodes.design import mix


def test_mix_m25_moderate_no_admixture():
    r = mix.design_mix(25, exposure="moderate", msa_mm=20, slump_mm=100,
                       admixture=None)
    d = r.data
    # water: 186 * 1.06 (100 mm slump)
    assert d["water"] == pytest.approx(186 * 1.06, rel=0.01)
    assert d["f_target"] == pytest.approx(31.6, abs=0.1)
    assert d["wc_actual"] <= 0.50
    assert abs(d["volume_sum"] - 1.0) < 1e-3
    assert r.ok, r.checks


def test_mix_m40_severe():
    r = mix.design_mix(40, exposure="severe", msa_mm=20, slump_mm=75)
    d = r.data
    assert d["wc_actual"] <= 0.45
    assert d["cement"] >= 320
    assert r.ok, r.checks


def test_mix_admixture_reduces_water():
    dry = mix.design_mix(30, admixture=None).data["water"]
    wet = mix.design_mix(30, admixture="superplasticizer",
                         water_reduction_pct=20).data["water"]
    assert wet == pytest.approx(dry * 0.80, rel=0.01)


def test_mix_grade_below_exposure_fails():
    r = mix.design_mix(20, exposure="severe")  # severe needs M30
    assert not r.ok


def test_select_bars():
    n, dia, ast_prov, note = detailing.select_bars(982, b_mm=300)
    assert ast_prov >= 982
    assert n >= 2


def test_select_bar_spacing():
    dia, spacing, ast_prov = detailing.select_bar_spacing(500)
    assert ast_prov >= 500 * 0.98
    assert 50 <= spacing <= 300


def test_lap_length_at_least_ld():
    from iscodes import tables
    assert detailing.lap_length(20, 500, 25) >= \
        tables.development_length(20, 500, 25)


def test_ductile_checks():
    ok = detailing.ductile_beam_checks(b=300, D=550, pt=1.2, pc=0.7)
    assert all(o for _, o in ok)
    bad = detailing.ductile_beam_checks(b=150, D=550, pt=3.0, pc=0.5)
    assert not all(o for _, o in bad)


def test_report_render_and_save(tmp_path):
    r = (report.Report("Beam B1 design", ["IS456", "SP16"])
         .add_section("Flexure")
         .add_line("Mu = 120 kNm")
         .add_check("Mu <= Mu_lim (cl 38.1)", True, "0.72 utilization")
         .add_check("failing example", False)
         .add_table(["item", "value"], [["Ast", "982 mm2"]]))
    md = r.render()
    assert "Beam B1 design" in md and "✓" in md and "✗" in md
    assert "IS456" in md and "verify against official BIS" in md
    p = r.save(str(tmp_path / "rep.md"))
    assert (tmp_path / "rep.md").exists()
    assert report.summarize_checks([("a", True), ("b", False)]) == (1, 1, ["b"])
