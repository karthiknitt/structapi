"""IS 456:2000 cl 22.5.1 (Tables 12 & 13) continuous-beam design.

Covers the primitive (`continuous_moments`), the two-face section design
added to `design_beam()`, the applicability gate in `design_building()`, and
the backward-compatibility guarantee for the frozen single-layer path.
"""

import math

import pytest

from iscodes.analysis.beam import continuous_moments
from iscodes.design import flexure
from iscodes.design.beam import design_beam
from iscodes.design.building import design_building

# ---------------------------------------------------------------------------
# 1. Worked example — hand calc straight off Table 12 / Table 13
# ---------------------------------------------------------------------------
# Three equal 5 m spans, w_dl = 10 kN/m, w_il = 5 kN/m (service).
# The coefficients act on the *factored* loads, DL and IL separately
# (that separation is what encodes the pattern-loading envelope), so
#   w_dl,u = 1.5 x 10 = 15 kN/m,  w_il,u = 1.5 x 5 = 7.5 kN/m,  L^2 = 25 m^2.
#
#   M near middle of end span   = +15/12*25 + 7.5/10*25 = 31.250 + 18.750 =  50.000
#   M middle of interior span   = +15/16*25 + 7.5/12*25 = 23.4375 + 15.625 =  39.0625
#   M at support next to end    = -15/10*25 - 7.5/9*25  = -37.500 - 20.8333 = -58.3333
#   M at other interior support = -15/12*25 - 7.5/9*25  = -31.250 - 20.8333 = -52.0833
#   V at end support            =  0.40*15*5 + 0.45*7.5*5 = 30.000 + 16.875 = 46.875
#   V next to end, outer face   =  0.60*15*5 + 0.60*7.5*5 = 45.000 + 22.500 = 67.500
#   V next to end, inner face   =  0.55*15*5 + 0.60*7.5*5 = 41.250 + 22.500 = 63.750
#   V at interior supports      =  0.50*15*5 + 0.60*7.5*5 = 37.500 + 22.500 = 60.000
W_DL, W_IL, L = 10.0, 5.0, 5.0
HAND = {
    "M_span_end": 50.0,
    "M_span_interior": 39.0625,
    "M_support_next_to_end": -58.3333333333,
    "M_support_interior": -52.0833333333,
    "V_end_support": 46.875,
    "V_support_next_to_end_outer": 67.5,
    "V_support_next_to_end_inner": 63.75,
    "V_support_interior": 60.0,
}


def test_table_12_13_matches_hand_calc():
    cm = continuous_moments(1.5 * W_DL, 1.5 * W_IL, L)
    assert set(cm) == set(HAND)
    for k, expected in HAND.items():
        assert cm[k] == pytest.approx(expected, rel=1e-9), k


def test_table_12_signs_sagging_positive_hogging_negative():
    """A face/sign flip here would silently put hogging steel on the soffit."""
    cm = continuous_moments(1.5 * W_DL, 1.5 * W_IL, L)
    assert cm["M_span_end"] > 0
    assert cm["M_span_interior"] > 0
    assert cm["M_support_next_to_end"] < 0
    assert cm["M_support_interior"] < 0
    # end span always governs the sagging design, interior support is milder
    # than the first interior support
    assert cm["M_span_end"] > cm["M_span_interior"]
    assert abs(cm["M_support_next_to_end"]) > abs(cm["M_support_interior"])


def test_continuity_reduces_span_moment_vs_simply_supported():
    cm = continuous_moments(1.5 * W_DL, 1.5 * W_IL, L)
    m_ss = 1.5 * (W_DL + W_IL) * L ** 2 / 8.0          # 70.3125 kN.m
    assert m_ss == pytest.approx(70.3125)
    assert max(abs(cm["M_span_end"]), abs(cm["M_span_interior"])) < m_ss
    assert abs(cm["M_support_next_to_end"]) < m_ss


# ---------------------------------------------------------------------------
# 2. Backward compatibility — the no-override path must not move
# ---------------------------------------------------------------------------
_BASE_KW = dict(span_m=6.0, w_dl_kn_m=15.0, w_il_kn_m=10.0,
                b=300.0, D=550.0, fck=25.0, fy=500.0)


def test_no_override_path_is_unchanged():
    r = design_beam(**_BASE_KW)
    d = r["design"]
    # single-layer envelope design, exactly as before
    assert d["Mu_max_kNm"] == pytest.approx(1.5 * 25 * 36 / 8)
    assert d["Mu_hogging_kNm"] == pytest.approx(0.0)
    # the additive continuous keys must NOT appear (frozen v1 contract:
    # tests/fixtures/beam_envelope_v1.json pins the exact design key set)
    assert "top_steel" not in d
    assert "continuous" not in d
    assert "bottom_steel_Mu_kNm" not in d
    assert [c[0] for c in r["checks"]] == [
        "flexure Ast >= Ast_min (cl 26.5.1.1a)",
        "flexure Ast <= Ast_max (cl 26.5.1.1b)",
        "moment capacity >= Mu",
        "shear (cl 40)",
        "deflection L/d (cl 23.2.1)",
        # additive (PC-5): crack-width SLS, IS 456 cl 43.1, default exposure
        "crack width <= 0.3 mm (IS 456 cl 43.1, moderate exposure)",
    ]


def test_overrides_equal_to_analysis_reproduce_the_single_layer_design():
    """Feeding back the same envelope the analysis produces must not change
    the bottom layer — proves the override plumbing is transparent."""
    ref = design_beam(**_BASE_KW)
    same = design_beam(**_BASE_KW,
                       Mu_span_override_kNm=ref["design"]["Mu_max_kNm"],
                       Mu_support_override_kNm=0.0,
                       Vu_override_kN=ref["design"]["Vu_max_kN"])
    for k in ("Ast_reqd_mm2", "Ast_prov_mm2", "n_bars", "Mu_max_kNm",
              "Vu_max_kN", "doubly_reinforced"):
        assert same["design"][k] == pytest.approx(ref["design"][k]), k


# ---------------------------------------------------------------------------
# 3. Two-face section design
# ---------------------------------------------------------------------------
_CONT_KW = dict(span_m=6.0, w_dl_kn_m=30.0, w_il_kn_m=20.0,
                b=300.0, D=550.0, fck=25.0, fy=500.0, support="fixed")


def _cont_result(w_dl=30.0, w_il=20.0, **over):
    cm = continuous_moments(1.5 * w_dl, 1.5 * w_il, 6.0)
    mu_span = max(abs(cm["M_span_end"]), abs(cm["M_span_interior"]))
    mu_sup = max(abs(cm["M_support_next_to_end"]),
                 abs(cm["M_support_interior"]))
    vu = max(abs(v) for k, v in cm.items() if k.startswith("V_"))
    kw = dict(_CONT_KW, w_dl_kn_m=w_dl, w_il_kn_m=w_il)
    kw.update(over)
    r = design_beam(**kw, Mu_span_override_kNm=mu_span,
                    Mu_support_override_kNm=mu_sup, Vu_override_kN=vu)
    return r, mu_span, mu_sup, vu


def test_continuous_path_produces_real_top_steel():
    r, mu_span, mu_sup, vu = _cont_result()
    d = r["design"]
    assert d["continuous"] is True
    ts = d["top_steel"]
    assert ts["Ast_prov_mm2"] > 0
    assert ts["n_bars"] >= 2
    # semantic, not "a field changed": the top layer must be sized for the
    # HOGGING moment and the bottom layer for the SAGGING one. Support
    # hogging > span sagging here, so a face swap flips this inequality.
    assert mu_sup > mu_span
    assert ts["Ast_reqd_mm2"] > d["Ast_reqd_mm2"]
    assert d["Mu_hogging_kNm"] == pytest.approx(-mu_sup)
    assert d["Mu_sagging_kNm"] == pytest.approx(mu_span)
    assert ts["Mu_hogging_kNm"] == pytest.approx(mu_sup)
    assert d["bottom_steel_Mu_kNm"] == pytest.approx(mu_span)
    assert d["Vu_max_kN"] == pytest.approx(vu)


def test_each_layer_matches_flexure_first_principles():
    """Ast on each face must equal ast_singly() of that face's own moment."""
    r, mu_span, mu_sup, _vu = _cont_result(w_dl=20.0, w_il=10.0)
    d = r["design"]
    b, D, fck, fy = 300.0, 550.0, 25.0, 500.0
    dd = D - 30 - 8 - 20 / 2.0
    assert d["d_mm"] == pytest.approx(dd)
    assert not d["doubly_reinforced"] and not d["top_steel"]["doubly_reinforced"]
    assert flexure.mu_lim(b, dd, fck, fy) > mu_sup * 1e6, "expect singly reinf"
    exp_bot = flexure.ast_singly(mu_span * 1e6, b, dd, fck, fy)
    exp_top = flexure.ast_singly(mu_sup * 1e6, b, dd, fck, fy)
    assert d["Ast_reqd_mm2"] == pytest.approx(exp_bot)
    assert d["top_steel"]["Ast_reqd_mm2"] == pytest.approx(exp_top)
    # bars are the rounded-up whole-bar realisation of those areas
    area_bar = math.pi * 20 ** 2 / 4.0
    assert d["n_bars"] == max(2, math.ceil(exp_bot / area_bar))
    assert d["top_steel"]["n_bars"] == max(2, math.ceil(exp_top / area_bar))


def test_top_layer_goes_doubly_reinforced_independently_of_bottom():
    """Hogging (282 kNm) exceeds Mu_lim while sagging (241 kNm) does not:
    each face must pick its own singly/doubly branch."""
    r, mu_span, mu_sup, _vu = _cont_result(w_dl=30.0, w_il=20.0)
    d = r["design"]
    mlim = d["Mu_lim_kNm"]
    assert mu_span < mlim < mu_sup
    assert d["doubly_reinforced"] is False
    assert d["Asc_reqd_mm2"] == 0.0
    assert d["top_steel"]["doubly_reinforced"] is True
    assert d["top_steel"]["Asc_reqd_mm2"] > 0
    assert d["top_steel"]["n_bars_comp"] >= 2


def test_continuous_beam_is_lighter_than_simply_supported_equivalent():
    """The whole point of Table 12: the span layer gets smaller."""
    r, _, _, _ = _cont_result()
    ss = design_beam(span_m=6.0, w_dl_kn_m=30.0, w_il_kn_m=20.0,
                     b=300.0, D=550.0, fck=25.0, fy=500.0)
    assert r["design"]["Ast_reqd_mm2"] < ss["design"]["Ast_reqd_mm2"]


def test_continuous_checks_are_additive_and_pass():
    r, _, _, _ = _cont_result()
    names = [c[0] for c in r["checks"]]
    assert "top steel Ast <= Ast_max (cl 26.5.1.1b)" in names
    assert "hogging moment capacity >= Mu_support (cl 22.5.1)" in names
    assert r["ok"], [c for c in r["checks"] if not c[1]]


def test_seismic_continuous_enforces_is13920_cl_6_2_3():
    """Bottom steel at a joint face >= half the top steel there."""
    cm = continuous_moments(1.5 * 30.0, 1.5 * 20.0, 6.0)
    mu_span = max(abs(cm["M_span_end"]), abs(cm["M_span_interior"]))
    mu_sup = max(abs(cm["M_support_next_to_end"]),
                 abs(cm["M_support_interior"]))
    r = design_beam(span_m=6.0, w_dl_kn_m=30.0, w_il_kn_m=20.0,
                    b=300.0, D=550.0, fck=25.0, fy=500.0, support="fixed",
                    seismic=True, Mu_span_override_kNm=mu_span,
                    Mu_support_override_kNm=mu_sup)
    d = r["design"]
    assert d["Ast_prov_mm2"] >= 0.5 * d["top_steel"]["Ast_prov_mm2"]
    assert ("IS 13920 bottom steel >= 0.5 x top steel at joint face (cl 6.2.3)",
            True) in r["checks"]


def test_continuous_uses_continuous_deflection_ratio():
    """cl 23.2.1 basic L/d: 26 for continuous vs 20 for simply supported."""
    r, _, _, _ = _cont_result()
    ss = design_beam(span_m=6.0, w_dl_kn_m=30.0, w_il_kn_m=20.0,
                     b=300.0, D=550.0, fck=25.0, fy=500.0)
    assert (r["design"]["deflection"]["allowable_L_by_d"]
            > ss["design"]["deflection"]["allowable_L_by_d"])


# ---------------------------------------------------------------------------
# 4. Applicability gate inside design_building()
# ---------------------------------------------------------------------------
def _flags(**kw):
    r = design_building(storeys=2, sbc_kpa=150.0, **kw)
    return r, {k[0]: v["table12_continuous"] for k, v in r["beams"].items()}


def test_gate_three_equal_spans_selects_continuous():
    r, flags = _flags(x_spacings_m=[4.0, 4.0, 4.0],
                      y_spacings_m=[4.0, 4.0, 4.0])
    assert flags == {"x": True, "y": True}
    for bm in r["beams"].values():
        assert bm["design"]["top_steel"]["Ast_prov_mm2"] > 0
        assert bm["n_spans"] == 3


def test_gate_two_spans_falls_back_to_simply_supported():
    # Zone II (seismic_detailing off) so the cl 22.5.1 continuity gate is
    # observed in isolation. Under ductile detailing the beam also picks up a
    # top layer from IS 1893 lateral reversal (PC-2) -- a separate demand
    # path that has nothing to do with gravity continuity, covered by
    # test_seismic_lateral_moment_adds_top_steel_to_two_span_beams below.
    r, flags = _flags(x_spacings_m=[4.0, 4.0], y_spacings_m=[4.0, 4.0],
                      seismic_zone="II")
    assert flags == {"x": False, "y": False}
    for bm in r["beams"].values():
        assert "top_steel" not in bm["design"]
        assert bm["inputs"]["support"] == "ss"


def test_gate_irregular_spans_fall_back_even_with_three_spans():
    """3.0 m is only 50% of the 6.0 m longest — outside cl 22.5.1's 15%."""
    _r, flags = _flags(x_spacings_m=[4.0, 4.0, 4.0],
                       y_spacings_m=[3.0, 6.0, 3.0])
    assert flags == {"x": True, "y": False}


def test_gate_boundary_15_percent_is_inclusive():
    """5.1 m = 0.85 x 6.0 m — exactly the cl 22.5.1 limit, still valid."""
    _r, flags = _flags(x_spacings_m=[6.0, 5.1, 6.0],
                       y_spacings_m=[6.0, 5.0, 6.0])
    assert flags["x"] is True      # 15.0% variation -> allowed
    assert flags["y"] is False     # 16.7% variation -> rejected


# ---------------------------------------------------------------------------
# 5. Building-level integration
# ---------------------------------------------------------------------------
def test_building_continuous_end_to_end():
    r = design_building(x_spacings_m=[4.5, 4.5, 4.5],
                        y_spacings_m=[4.0, 4.0, 4.0],
                        storeys=3, sbc_kpa=180.0)
    assert all(bm["table12_continuous"] for bm in r["beams"].values())
    assert any("Table 12/13" in a for a in r["assumptions"])
    # simply-supported fallback is still advertised as available
    assert any("simply supported" in a for a in r["assumptions"])
    assert r["quantities"]["steel_kg"]["beams"] > 0
    # top steel is billed, not silently dropped from the BOQ
    naive = sum(bm["design"]["Ast_prov_mm2"] * 1e-6 * bm["span_m"]
                * bm["n_spans"] * bm["count"] * 7850.0
                for bm in r["beams"].values()) * 3 * 1.10
    assert r["quantities"]["steel_kg"]["beams"] > naive
