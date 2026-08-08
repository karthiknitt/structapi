"""Validation for the RC beam analysis/design modules."""

import math

import numpy as np
import pytest

from iscodes.analysis.beam import BeamCase, analyze, continuous_moments
from iscodes.design import flexure, shear, beam as beamdesign
from iscodes import plotting


# ---------------------------------------------------------------------------
# analysis/beam.py
# ---------------------------------------------------------------------------

def test_ss_udl():
    r = analyze(BeamCase(6.0, "ss", 20.0))
    ip = int(np.argmax(r["M"]))
    assert r["M"].max() == pytest.approx(90.0, abs=1e-6)   # wL^2/8
    assert r["x"][ip] == pytest.approx(3.0, abs=0.02)      # midspan
    assert abs(r["V"]).max() == pytest.approx(60.0, abs=1e-6)  # wL/2


def test_ss_point_central():
    r = analyze(BeamCase(4.0, "ss", 0.0, [(10.0, 2.0)]))
    assert r["M"].max() == pytest.approx(10.0 * 4.0 / 4.0)  # PL/4
    assert abs(r["V"]).max() == pytest.approx(5.0)          # P/2


def test_cantilever_udl():
    r = analyze(BeamCase(3.0, "cantilever", 10.0))
    # fixing moment at x=0 = -wL^2/2 = -45
    assert r["M"][0] == pytest.approx(-45.0, abs=1e-6)
    assert r["V"][0] == pytest.approx(30.0, abs=1e-6)       # wL


def test_fixed_udl():
    w, L = 20.0, 6.0
    r = analyze(BeamCase(L, "fixed", w))
    end = -w * L ** 2 / 12.0            # -60
    mid = w * L ** 2 / 24.0             # +30
    assert r["M"][0] == pytest.approx(end, abs=1e-6)
    assert r["M"][-1] == pytest.approx(end, abs=1e-6)
    assert r["M"].max() == pytest.approx(mid, abs=1e-6)


def test_fixed_point_central():
    r = analyze(BeamCase(4.0, "fixed", 0.0, [(16.0, 2.0)]))
    # fixed-end moments = -PL/8
    assert r["M"][0] == pytest.approx(-16.0 * 4.0 / 8.0, abs=1e-6)
    assert r["M"][-1] == pytest.approx(-16.0 * 4.0 / 8.0, abs=1e-6)
    # midspan sagging = PL/8
    assert r["M"].max() == pytest.approx(16.0 * 4.0 / 8.0, abs=1e-6)


def test_continuous_moments():
    r = continuous_moments(w_dl=15.0, w_il=10.0, L=6.0)
    T = __import__("iscodes.tables", fromlist=["x"]).TABLE_12_MOMENT
    exp = (T["span_end_DL"] * 15 + T["span_end_IL"] * 10) * 36
    assert r["M_span_end"] == pytest.approx(exp)
    assert r["M_support_interior"] < 0  # hogging


# ---------------------------------------------------------------------------
# design/flexure.py
# ---------------------------------------------------------------------------

def test_ast_singly_textbook():
    # Mu = 100 kN.m, b=230, d=415, M20/Fe415 -> verify against Annex G algebra
    Mu, b, d, fck, fy = 100e6, 230.0, 415.0, 20.0, 415.0
    ast = flexure.ast_singly(Mu, b, d, fck, fy)
    disc = 1 - 4.6 * Mu / (fck * b * d ** 2)
    expected = 0.5 * fck / fy * (1 - math.sqrt(disc)) * b * d
    assert ast == pytest.approx(expected)
    assert ast == pytest.approx(810.6, rel=0.01)


def test_ast_singly_raises_over_mulim():
    b, d, fck, fy = 230.0, 415.0, 20.0, 415.0
    Mlim = flexure.mu_lim(b, d, fck, fy)
    with pytest.raises(ValueError):
        flexure.ast_singly(Mlim * 1.2, b, d, fck, fy)


def test_flexure_roundtrip():
    # ast_singly then mu_capacity should recover the moment
    Mu, b, d, fck, fy = 90e6, 300.0, 500.0, 25.0, 500.0
    ast = flexure.ast_singly(Mu, b, d, fck, fy)
    assert flexure.mu_capacity(ast, b, d, fck, fy) == pytest.approx(Mu, rel=0.01)


def test_mu_capacity_capped_at_mulim():
    b, d, fck, fy = 300.0, 500.0, 25.0, 500.0
    huge = flexure.max_steel(b, 550) * 2
    assert flexure.mu_capacity(huge, b, d, fck, fy) == pytest.approx(
        flexure.mu_lim(b, d, fck, fy))


def test_doubly_design():
    b, d, dc, fck, fy = 300.0, 550.0, 50.0, 25.0, 500.0
    Mu = flexure.mu_lim(b, d, fck, fy) * 1.3
    dd = flexure.design_doubly(Mu, b, d, dc, fck, fy)
    assert dd["Asc"] > 0 and dd["Ast"] > dd["Ast_lim"]


def test_min_max_steel():
    assert flexure.min_steel(300, 550, 500) == pytest.approx(0.85 * 300 * 550 / 500)
    assert flexure.max_steel(300, 600) == pytest.approx(0.04 * 300 * 600)


# ---------------------------------------------------------------------------
# design/shear.py
# ---------------------------------------------------------------------------

def test_shear_minimum_stirrups():
    # low shear -> tau_v <= tau_c -> minimum stirrups spacing
    r = shear.design_stirrups(40e3, 300, 500, 25, 415, 1500)
    assert r["ok"]
    assert r["tau_v"] <= r["tau_c"]
    assert "minimum" in r["governing"]
    Asv = 2 * math.pi * 8 ** 2 / 4
    sv_expected = min(0.87 * 415 * Asv / (0.4 * 300), 0.75 * 500, 300)
    assert r["sv_provided"] == int(math.floor(sv_expected / 5) * 5)


def test_shear_designed_from_vus():
    r = shear.design_stirrups(300e3, 300, 500, 25, 415, 1500)
    assert r["ok"]
    assert r["tau_v"] > r["tau_c"]
    assert "shear" in r["governing"]
    assert 0 < r["sv_provided"] <= min(0.75 * 500, 300)


def test_shear_section_inadequate():
    r = shear.design_stirrups(900e3, 300, 400, 25, 415, 1500)
    assert not r["ok"]


# ---------------------------------------------------------------------------
# design/beam.py (end-to-end)
# ---------------------------------------------------------------------------

def test_design_beam_end_to_end():
    r = beamdesign.design_beam(span_m=6.0, w_dl_kn_m=15.0, w_il_kn_m=10.0,
                               b=300, D=550, fck=25, fy=500, support="ss")
    assert r["ok"], r["checks"]
    d = r["design"]
    assert d["Ast_prov_mm2"] >= d["Ast_reqd_mm2"] >= d["Ast_min_mm2"]
    assert d["n_bars"] >= 2
    assert d["Vu_max_kN"] == pytest.approx(1.5 * 25 * 6 / 2, rel=0.02)  # wL/2
    assert d["Mu_max_kNm"] == pytest.approx(1.5 * 25 * 36 / 8, rel=0.02)  # wL^2/8
    names = [n for n, _ in r["checks"]]
    assert any("deflection" in n for n in names)
    assert any("shear" in n for n in names)


def test_design_beam_seismic_checks():
    r = beamdesign.design_beam(span_m=5.0, w_dl_kn_m=20.0, w_il_kn_m=15.0,
                               b=300, D=500, fck=25, fy=500, support="ss",
                               seismic=True)
    names = [n for n, _ in r["checks"]]
    assert any("13920" in n for n in names)


def test_ductile_beam_min_steel_is13920():
    """Verify IS 13920 cl 6.2.1 minimum tension steel enforcement in seismic design."""
    # Design parameters per acceptance criterion
    b, D, fck, fy = 230.0, 450.0, 25.0, 500.0
    cover, bar_dia, stirrup_dia = 30.0, 20.0, 8.0
    d = D - cover - stirrup_dia - bar_dia / 2.0  # 402 mm

    # Expected IS 13920 minimum: max(0.85/fy, 0.24*sqrt(fck)/fy) * b * d
    ast_min_ductile_expected = max(0.85 / fy, 0.24 * math.sqrt(fck) / fy) * b * d
    # 0.24*sqrt(25)/500 = 0.0024, which governs over 0.0017
    assert ast_min_ductile_expected == pytest.approx(0.0024 * b * d, rel=0.01)

    # Light loads to ensure minimum-steel-governed section
    r_seismic = beamdesign.design_beam(
        span_m=2.0, w_dl_kn_m=5.0, w_il_kn_m=2.0,
        b=b, D=D, fck=fck, fy=fy, support="ss",
        cover=cover, bar_dia=bar_dia, stirrup_dia=stirrup_dia,
        seismic=True
    )

    # Assertion 1: Ast_prov_mm2 meets the ductile minimum
    ast_prov_seismic = r_seismic["design"]["Ast_prov_mm2"]
    assert ast_prov_seismic >= ast_min_ductile_expected

    # Assertion 2: New check tuple is present and True
    check_names = [name for name, ok in r_seismic["checks"]]
    assert any("IS 13920 min tension steel Ast_min (cl 6.2.1)" in name for name in check_names)
    seismic_check_ok = [ok for name, ok in r_seismic["checks"]
                        if "IS 13920 min tension steel Ast_min (cl 6.2.1)" in name]
    assert len(seismic_check_ok) == 1 and seismic_check_ok[0]

    # Non-seismic regression guard
    r_non_seismic = beamdesign.design_beam(
        span_m=2.0, w_dl_kn_m=5.0, w_il_kn_m=2.0,
        b=b, D=D, fck=fck, fy=fy, support="ss",
        cover=cover, bar_dia=bar_dia, stirrup_dia=stirrup_dia,
        seismic=False
    )

    ast_prov_non_seismic = r_non_seismic["design"]["Ast_prov_mm2"]
    # Seismic should require at least as much steel as non-seismic
    assert ast_prov_seismic >= ast_prov_non_seismic

    # Check tuple should be absent in non-seismic case
    check_names_non_seismic = [name for name, ok in r_non_seismic["checks"]]
    assert not any("IS 13920 min tension steel Ast_min (cl 6.2.1)" in name
                   for name in check_names_non_seismic)


def test_ductile_beam_two_zone_stirrups_worked_example():
    """IS 13920:2016 cl 6.3.5 two-zone hoop schedule — hand-worked example.

    G+1 residential seismic beam, M25 / Fe500:
        b = 300, D = 500, cover 30, 20 dia main bars, 8 dia hoops
        d  = 500 - 30 - 8 - 20/2                       = 452 mm
        confining zone length  = 2d                    = 904 mm
        confining pitch limit  = max(min(d/4, 8*20), 100)
                               = max(min(113.0, 160.0), 100) = 113.0 mm
                               -> Site-Standard 25 floor          = 100 mm
        span-zone pitch limit  = d/2 = 226 mm -> floor            = 225 mm
    Loads are light enough that IS 456 shear gives sv = 300 mm (the cl 26.5.1.6
    cap), so the ductile limits govern in both zones.
    """
    b, D, fck, fy = 300.0, 500.0, 25.0, 500.0
    cover, bar_dia, stirrup_dia = 30.0, 20.0, 8.0
    d_hand = D - cover - stirrup_dia - bar_dia / 2.0
    assert d_hand == 452.0

    r = beamdesign.design_beam(span_m=4.0, w_dl_kn_m=12.0, w_il_kn_m=8.0,
                               b=b, D=D, fck=fck, fy=fy, support="ss",
                               cover=cover, bar_dia=bar_dia,
                               stirrup_dia=stirrup_dia, seismic=True)
    ds = r["design"]["ductile_stirrups"]
    assert r["design"]["d_mm"] == pytest.approx(d_hand)
    # shear design is untouched and does not govern here
    assert r["design"]["stirrups"]["sv_provided"] == 300.0

    # hand-computed limits
    assert ds["confining_zone_length_mm"] == pytest.approx(904.0)
    assert ds["confining_zone_spacing_limit_mm"] == pytest.approx(113.0)
    assert ds["span_zone_spacing_limit_mm"] == pytest.approx(226.0)
    # hand-computed provided (Site-Standard 25) spacings
    assert ds["confining_zone_spacing_mm"] == 100.0
    assert ds["span_zone_spacing_mm"] == 225.0
    assert ds["first_stirrup_offset_mm"] == 50.0
    assert ds["hook"] == "135 deg bend, extend 10*dia beyond bend, closed hoop"

    # zone relationships and code caps
    assert ds["confining_zone_spacing_mm"] <= ds["span_zone_spacing_mm"]
    assert ds["confining_zone_spacing_mm"] <= max(
        min(d_hand / 4.0, 8.0 * bar_dia), 100.0)
    assert ds["span_zone_spacing_mm"] <= d_hand / 2.0
    # Site-Standard 25
    assert ds["confining_zone_spacing_mm"] % 25 == 0
    assert ds["span_zone_spacing_mm"] % 25 == 0

    names = [n for n, _ in r["checks"]]
    assert any("cl 6.3.5" in n and "confining-zone" in n for n in names)
    assert any("cl 6.3.5" in n and "span-zone" in n for n in names)
    assert all(ok for n, ok in r["checks"] if "cl 6.3.5" in n)
    # stale clause citation fixed (cl 6.1.1, not 6.1.3)
    assert any("cl 6.1.1" in n for n in names)
    assert not any("cl 6.1.3" in n for n in names)


def test_ductile_beam_shear_spacing_governs_over_ductile_cap():
    """Where IS 456 shear demands a tighter pitch than IS 13920, shear wins.

    Deep, heavily loaded beam: d = 700 - 30 - 8 - 12.5 = 649.5 mm, so the
    ductile span-zone limit is d/2 = 324.75 -> 300 mm, but designed shear
    (cl 40.4) forces a much tighter pitch, which must carry into both zones.
    """
    r = beamdesign.design_beam(span_m=7.0, w_dl_kn_m=60.0, w_il_kn_m=40.0,
                               b=300, D=700, fck=25, fy=500, support="ss",
                               cover=30, bar_dia=25, stirrup_dia=8,
                               seismic=True)
    sv = r["design"]["stirrups"]["sv_provided"]
    ds = r["design"]["ductile_stirrups"]
    assert 0 < sv < 100.0, sv           # shear-governed, tighter than 100 mm
    assert ds["confining_zone_spacing_mm"] == sv
    assert ds["span_zone_spacing_mm"] == sv
    assert ds["confining_zone_spacing_mm"] % 25 == 0
    assert ds["span_zone_spacing_mm"] % 25 == 0


def test_ductile_beam_stirrups_absent_when_not_seismic():
    """Non-seismic regression guard: no ductile field, no cl 6.3.5 checks."""
    r = beamdesign.design_beam(span_m=4.0, w_dl_kn_m=12.0, w_il_kn_m=8.0,
                               b=300, D=500, fck=25, fy=500, support="ss",
                               cover=30, bar_dia=20, stirrup_dia=8,
                               seismic=False)
    assert "ductile_stirrups" not in r["design"]
    assert "stirrups" in r["design"]          # existing field untouched
    assert not any("cl 6.3.5" in n for n, _ in r["checks"])


# ---------------------------------------------------------------------------
# plotting.py
# ---------------------------------------------------------------------------

def test_plot_sfd_bmd(tmp_path):
    r = analyze(BeamCase(6.0, "ss", 20.0))
    p = tmp_path / "sfd_bmd.png"
    out = plotting.plot_sfd_bmd(r["x"], r["V"], r["M"], "SS beam",
                                str(p), loads_desc="UDL 20 kN/m")
    assert out == str(p)
    assert p.exists() and p.stat().st_size > 5000


def test_plot_pm_interaction(tmp_path):
    curve = np.array([[2000, 0], [1500, 120], [800, 180], [0, 90]], float)
    p = tmp_path / "pm.png"
    plotting.plot_pm_interaction(curve, [(80, 1500)], "Column P-M", str(p))
    assert p.exists() and p.stat().st_size > 5000


def test_plot_pressure_diagram(tmp_path):
    p = tmp_path / "pressure.png"
    plotting.plot_pressure_diagram(3.0, 80.0, 150.0, "Footing pressure", str(p))
    assert p.exists() and p.stat().st_size > 5000
