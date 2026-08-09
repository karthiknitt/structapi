"""PC-2: load-combination envelope, overturning axial, lateral beam moments
and the IS 13920 ductile reversal checks wired into design_building().

The acceptance criterion for this task is a textbook portal-frame worked
example whose takedown is hand-computed here and asserted against the code.
"""

import pytest

from iscodes.design import combinations as comb
from iscodes.design.building import design_building


# ---------------------------------------------------------------------------
# 1. The combination table itself
# ---------------------------------------------------------------------------
def test_five_combination_families_expand_to_the_is1893_table():
    env = comb.combination_envelope(P_D_kN=100.0, M_D_kNm=0.0,
                                    P_IL_kN=40.0, M_IL_kNm=0.0,
                                    P_E_kN=30.0, M_E_kNm=20.0)
    names = {c["name"] for c in env["combos"]}
    assert names == {
        "1.5(DL+IL)",
        "1.2(DL+IL+EL)", "1.2(DL+IL-EL)",
        "1.5(DL+EL)", "1.5(DL-EL)",
        "0.9DL+1.5EL", "0.9DL-1.5EL",
    }
    # 1 gravity row + 3 lateral families x 2 directions x 2 signs
    assert len(env["combos"]) == 1 + 3 * 2 * 2


def test_combination_values_match_hand_arithmetic():
    P_D, P_IL, P_E, M_E = 100.0, 40.0, 30.0, 20.0
    env = comb.combination_envelope(P_D, 0.0, P_IL, 0.0, P_E, M_E)
    by = {(c["name"], c["direction"]): c for c in env["combos"]}

    # gravity only: 1.5(100+40) = 210, no moment
    assert by[("1.5(DL+IL)", None)]["Pu_kN"] == pytest.approx(210.0)
    assert by[("1.5(DL+IL)", None)]["Mux_kNm"] == pytest.approx(0.0)

    # 1.2(DL+IL+EL) about x: 1.2*(100+40+30) = 204, Mux = 1.2*20 = 24
    c = by[("1.2(DL+IL+EL)", "x")]
    assert c["Pu_kN"] == pytest.approx(204.0)
    assert c["Mux_kNm"] == pytest.approx(24.0)
    assert c["Muy_kNm"] == pytest.approx(0.0)

    # the y-direction twin carries the same magnitude on the other axis
    cy = by[("1.2(DL+IL+EL)", "y")]
    assert cy["Pu_kN"] == pytest.approx(204.0)
    assert cy["Mux_kNm"] == pytest.approx(0.0)
    assert cy["Muy_kNm"] == pytest.approx(24.0)

    # 0.9DL - 1.5EL: 0.9*100 - 1.5*30 = 90 - 45 = 45, Mu = 1.5*20 = 30
    c = by[("0.9DL-1.5EL", "x")]
    assert c["Pu_kN"] == pytest.approx(45.0)
    assert c["Mux_kNm"] == pytest.approx(30.0)

    assert env["Pu_max_kN"] == pytest.approx(210.0)     # gravity governs
    assert env["Pu_min_kN"] == pytest.approx(45.0)      # 0.9D-1.5E governs
    assert env["Mux_max_kNm"] == pytest.approx(30.0)
    assert env["uplift_governs"] is False


def test_gravity_combo_reproduces_the_pre_envelope_factored_load():
    """1.5(DL+IL) must equal the old 1.5*P_service to the last bit."""
    P_D, P_IL = 137.25, 61.5
    env = comb.combination_envelope(P_D, 0.0, P_IL, 0.0, P_E_kN=0.0, M_E_kNm=0.0)
    assert env["Pu_max_kN"] == pytest.approx(1.5 * (P_D + P_IL), rel=1e-12)


def test_uplift_governs_when_light_gravity_meets_strong_lateral():
    """0.9DL - 1.5EL drives a light exterior column into net tension."""
    env = comb.combination_envelope(P_D_kN=50.0, M_D_kNm=0.0,
                                    P_IL_kN=10.0, M_IL_kNm=0.0,
                                    P_E_kN=80.0, M_E_kNm=60.0)
    # 0.9*50 - 1.5*80 = 45 - 120 = -75 kN, net tension
    assert env["Pu_min_kN"] == pytest.approx(-75.0)
    assert env["uplift_governs"] is True
    assert env["governing_uplift"]["name"] == "0.9DL-1.5EL"


def test_no_uplift_when_gravity_dominates():
    env = comb.combination_envelope(P_D_kN=500.0, M_D_kNm=0.0,
                                    P_IL_kN=100.0, M_IL_kNm=0.0,
                                    P_E_kN=20.0, M_E_kNm=15.0)
    assert env["Pu_min_kN"] > 0
    assert env["uplift_governs"] is False


# ---------------------------------------------------------------------------
# 2. Overturning helpers
# ---------------------------------------------------------------------------
def test_seismic_overturning_moment_is_sum_of_Qi_hi():
    # (level, Wi, hi, Qi)
    forces = [(1, 900.0, 3.0, 10.0), (2, 900.0, 6.0, 40.0), (3, 700.0, 9.0, 90.0)]
    # 10*3 + 40*6 + 90*9 = 30 + 240 + 810 = 1080 kNm
    assert comb.overturning_moment_kNm(forces, "seismic", 0.0, 9.0) == pytest.approx(1080.0)


def test_wind_overturning_moment_acts_at_mid_height():
    assert comb.overturning_moment_kNm([], "wind", 200.0, 12.0) == pytest.approx(1200.0)


def test_overturning_axial_is_the_couple_shared_over_the_extreme_line():
    # 1080 kNm / (12 m lever arm x 3 columns per line) = 30 kN per column
    assert comb.overturning_axial_kN(1080.0, 12.0, 3) == pytest.approx(30.0)
    assert comb.overturning_axial_kN(1080.0, 0.0, 3) == 0.0
    assert comb.overturning_axial_kN(1080.0, 12.0, 0) == 0.0


# ---------------------------------------------------------------------------
# 3. Textbook portal-frame worked example — the acceptance criterion
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def portal():
    """A 2x2 bay, 3-storey frame, wind-free so seismic unambiguously governs.

    basic_wind_speed is forced low so lateral_gov == "seismic" and the whole
    takedown can be hand-checked from the seismic storey forces alone.
    """
    return design_building(
        x_spacings_m=[5.0, 5.0], y_spacings_m=[5.0, 5.0],
        storeys=3, storey_height_m=3.0,
        occupancy="residential_room",
        basic_wind_speed=10.0,            # negligible wind -> seismic governs
        seismic_zone="V", terrain_category=1, soil="medium",
        sbc_kpa=200, fck=25, fy=500)


def test_portal_frame_seismic_governs(portal):
    assert portal["lateral"]["governing"] == "seismic"


def test_portal_frame_storey_shear_share_hand_takedown(portal):
    """Portal method: interior columns take 2 shares, exterior 1.

    A 2x2 bay grid has 9 columns: 1 interior, 4 corner, 4 edge.
    shares = 2*1 + (9-1) = 10. The interior column's lateral moment is
    (VB/10)*2*h/2 and every exterior column's is (VB/10)*1*h/2.
    """
    VB = portal["lateral"]["seismic_VB_kN"]
    h = portal["inputs"]["storey_height_m"]
    unit = VB / 10.0

    interior = portal["columns"]["interior"]
    corner = portal["columns"]["corner"]
    edge = portal["columns"]["edge"]

    assert interior["M_lateral_kNm"] == pytest.approx(unit * 2 * h / 2, rel=1e-3)
    assert corner["M_lateral_kNm"] == pytest.approx(unit * 1 * h / 2, rel=1e-3)
    assert edge["M_lateral_kNm"] == pytest.approx(unit * 1 * h / 2, rel=1e-3)
    # interior column carries exactly twice the exterior portal moment
    assert interior["M_lateral_kNm"] == pytest.approx(2 * corner["M_lateral_kNm"],
                                                      rel=1e-6)


def test_portal_frame_overturning_axial_hand_takedown(portal):
    """dP = OTM / (lever arm x columns per extreme line).

    Square 10 x 10 m plan, so lever arm = 10.0 m and each extreme column
    line holds 3 columns -> dP = OTM / 30.
    """
    # rebuild the OTM from the reported seismic quantities
    corner = portal["columns"]["corner"]
    interior = portal["columns"]["interior"]

    # interior columns sit on the neutral axis -> no overturning axial
    assert interior["P_overturning_kN"] == pytest.approx(0.0)
    # edge and corner share the couple equally in this model
    assert corner["P_overturning_kN"] == pytest.approx(
        portal["columns"]["edge"]["P_overturning_kN"])
    assert corner["P_overturning_kN"] > 0

    # dP x lever arm x n_line must reproduce the base overturning moment
    dP = corner["P_overturning_kN"]
    OTM = dP * 10.0 * 3
    # sanity: OTM ~ VB x (an effective height between 0.5h and 1.0h total)
    VB = portal["lateral"]["seismic_VB_kN"]
    h_total = 3 * 3.0
    assert 0.5 * VB * h_total <= OTM <= 1.0 * VB * h_total


def test_portal_frame_column_envelope_matches_hand_combinations(portal):
    """Rebuild the 5-combo envelope by hand from the reported components."""
    for kind, col in portal["columns"].items():
        P_D = col["P_dead_kN"]
        P_IL = col["P_imposed_kN"]
        P_E = col["P_overturning_kN"]
        M_E = col["M_lateral_kNm"]

        # dead + imposed must reconstitute the service takedown exactly
        assert P_D + P_IL == pytest.approx(col["P_service_kN"], rel=1e-12)

        hand_Pu = [
            1.5 * (P_D + P_IL),
            1.2 * (P_D + P_IL + P_E), 1.2 * (P_D + P_IL - P_E),
            1.5 * (P_D + P_E), 1.5 * (P_D - P_E),
            0.9 * P_D + 1.5 * P_E, 0.9 * P_D - 1.5 * P_E,
        ]
        assert col["Pu_max_kN"] == pytest.approx(max(hand_Pu), rel=1e-9)
        assert col["Pu_min_kN"] == pytest.approx(min(hand_Pu), rel=1e-9)
        # largest lateral factor in the table is 1.5. These are envelope
        # maxima across independent per-axis combo rows (Important 6) --
        # NOT a same-row (Pu, Mux, Muy) design triple, hence the
        # unambiguous "_envelope_max_" naming rather than bare Mux_kNm/
        # Muy_kNm (which this building-level output no longer exposes).
        assert col["Mux_envelope_max_kNm"] == pytest.approx(1.5 * M_E, rel=1e-9)
        assert col["Muy_envelope_max_kNm"] == pytest.approx(1.5 * M_E, rel=1e-9)


def test_portal_frame_interior_column_gravity_still_governs(portal):
    """Interior columns get no overturning axial, so 1.5(DL+IL) is max Pu."""
    col = portal["columns"]["interior"]
    assert col["Pu_kN"] == pytest.approx(col["Pu_gravity_kN"], rel=1e-12)


# ---------------------------------------------------------------------------
# Important 6 regression -- no non-physical (Pu, Mux, Muy) headline triple.
# ---------------------------------------------------------------------------

def test_no_misleading_top_level_mux_muy_pair(portal):
    """Building-level column output must not expose a bare "Mux_kNm"/
    "Muy_kNm" pair alongside "Pu_kN" -- that combination previously mixed
    the zero-moment gravity row's Pu with two DIFFERENT lateral rows' axis
    maxima, a triple that corresponds to no combo row actually designed
    against."""
    for col in portal["columns"].values():
        assert "Mux_kNm" not in col
        assert "Muy_kNm" not in col


def test_governing_triple_is_a_single_combination_row(portal):
    """The unambiguous (Pu_governing_kN, Mux_governing_kNm,
    Muy_governing_kNm) triple must be read off the SAME combination row --
    the one named by governing_combination -- not independently maxed."""
    for col in portal["columns"].values():
        matches = [c for c in col["combinations"]
                  if c["name"] == col["governing_combination"]
                  and c["Pu_kN"] > 0.0]
        assert matches, (col["governing_combination"], col["combinations"])
        # there can be two rows sharing a name (+EL / -EL direction); the
        # governing one must be among them, matching on all three components
        assert any(
            m["Pu_kN"] == pytest.approx(col["Pu_governing_kN"], rel=1e-9)
            and m["Mux_kNm"] == pytest.approx(col["Mux_governing_kNm"], rel=1e-9)
            and m["Muy_kNm"] == pytest.approx(col["Muy_governing_kNm"], rel=1e-9)
            for m in matches)


# ---------------------------------------------------------------------------
# 4. Uplift flag surfaces end-to-end
# ---------------------------------------------------------------------------
def test_uplift_governs_flag_and_violation_for_tall_light_frame():
    """Tall, light, zone V, huge wind -> exterior columns lose all compression."""
    r = design_building(
        x_spacings_m=[3.0, 3.0], y_spacings_m=[3.0, 3.0],
        storeys=12, storey_height_m=3.5,
        occupancy="residential_room",
        basic_wind_speed=55.0, terrain_category=1,
        seismic_zone="V", soil="soft", sbc_kpa=250, fck=30, fy=500)

    exterior = [c for k, c in r["columns"].items() if k != "interior"]
    assert any(c["uplift_governs"] for c in exterior), \
        {k: c["Pu_min_kN"] for k, c in r["columns"].items()}
    for c in exterior:
        if c["uplift_governs"]:
            assert c["Pu_min_kN"] < 0
            assert c["governing_combination"] is not None

    # the disclosed scope boundary must reach the violations list
    assert any(v["member_type"] == "column" and "net tension" in v["check"]
               for v in r["violations"])
    # interior columns are unaffected by overturning and stay in compression
    assert r["columns"]["interior"]["uplift_governs"] is False


# ---------------------------------------------------------------------------
# 5. Lateral beam moments
# ---------------------------------------------------------------------------
def _beams(**kw):
    base = dict(x_spacings_m=[4.0, 4.0], y_spacings_m=[4.0, 4.0],
                storeys=3, storey_height_m=3.0, sbc_kpa=200,
                fck=25, fy=500, city="chennai", terrain_category=3)
    base.update(kw)
    return design_building(**base)


def test_seismic_beams_carry_a_lateral_support_moment():
    seismic = _beams(seismic_zone="V")
    for bm in seismic["beams"].values():
        assert bm["M_lateral_support_kNm"] > 0


def test_non_seismic_beams_carry_no_lateral_moment_and_no_ductile_checks():
    plain = _beams(seismic_zone="II")
    assert plain["lateral"]["seismic_detailing_IS13920"] is False
    for bm in plain["beams"].values():
        assert "M_lateral_support_kNm" not in bm
        assert "ductile_beam_checks" not in bm


def test_seismic_lateral_moment_adds_top_steel_to_two_span_beams():
    """Two spans fail the cl 22.5.1 continuity gate, but lateral demand
    still requires a top layer at the joint — the gravity path's continuity
    and the seismic reversal demand are independent."""
    seismic = _beams(seismic_zone="V")
    for bm in seismic["beams"].values():
        # table12_continuous (Important 5 rename, was "continuous"): 2 spans
        # -> the IS 456 cl 22.5.1 gate rejects, so this is genuinely False --
        # distinct from design["continuous"], which override-triggered
        # "continuous mode" still sets True for the seismic reversal moment.
        assert bm["table12_continuous"] is False
        assert bm["design"]["continuous"] is True
        assert bm["top_steel_source"] == "seismic_reversal"
        assert bm["design"]["top_steel"]["Ast_prov_mm2"] > 0


def test_seismic_beams_have_more_top_steel_than_non_seismic():
    seismic = _beams(seismic_zone="V")
    plain = _beams(seismic_zone="II")
    for key, bm in seismic["beams"].items():
        top_seismic = bm["design"].get("top_steel", {}).get("Ast_prov_mm2", 0.0)
        top_plain = plain["beams"][key]["design"].get(
            "top_steel", {}).get("Ast_prov_mm2", 0.0)
        assert top_seismic > top_plain


# ---------------------------------------------------------------------------
# 6. ductile_beam_checks wired into output
# ---------------------------------------------------------------------------
def test_ductile_beam_checks_appear_in_seismic_beam_output():
    seismic = _beams(seismic_zone="V")
    for bm in seismic["beams"].values():
        names = [n for n, _ in bm["ductile_beam_checks"]]
        assert any("beam width >= 200 mm" in n for n in names)
        assert any("b/D >= 0.3" in n for n in names)
        assert any("max tension steel pt <= 2.5%" in n for n in names)
        # they must also be merged into the beam's public checks list
        assert set(names).issubset({n for n, _ in bm["checks"]})


def test_ductile_beam_checks_do_not_duplicate_the_cl_623_reversal_check():
    """design_beam() already enforces bottom >= 0.5 x top on areas; the
    percentage-based twin from detailing.ductile_beam_checks is dropped."""
    seismic = _beams(seismic_zone="V")
    for bm in seismic["beams"].values():
        names = [n for n, _ in bm["ductile_beam_checks"]]
        assert not any(n.startswith("compression steel") for n in names)
        # the design_beam() reversal check is the one that survives
        assert any("bottom steel >= 0.5 x top steel" in n
                   for n, _ in bm["checks"])


def test_stale_is13920_clause_citation_is_gone_from_detailing():
    from iscodes import detailing
    names = [n for n, _ in detailing.ductile_beam_checks(300.0, 500.0, 1.0, 0.6)]
    assert any("cl 6.1.1" in n for n in names)
    assert not any("cl 6.1.3" in n for n in names)


# ---------------------------------------------------------------------------
# 7. Regression: the non-seismic gravity path is untouched
# ---------------------------------------------------------------------------
def test_non_seismic_column_axial_is_unchanged_by_the_envelope():
    """1.5(DL+IL) still governs max Pu wherever overturning is small, so
    Pu_kN reproduces the pre-envelope 1.5 * P_service exactly."""
    r = _beams(seismic_zone="II")
    for kind, col in r["columns"].items():
        assert col["Pu_kN"] == pytest.approx(1.5 * col["P_service_kN"], rel=1e-12)
        assert col["Pu_gravity_kN"] == pytest.approx(1.5 * col["P_service_kN"],
                                                     rel=1e-12)
