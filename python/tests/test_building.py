"""Reference-building validation of the whole-building design chain."""

import json

import pytest

from iscodes.design.building import _panel_case, design_building
from iscodes.tables import TABLE_26


@pytest.fixture(scope="module")
def ref():
    # G+1 (2 storeys), 3x2 bays, Chennai zone III — the documented reference
    return design_building(
        x_spacings_m=[3.5, 4.0, 3.5], y_spacings_m=[4.0, 4.5],
        storeys=2, storey_height_m=3.0,
        occupancy="residential_room", city="chennai",
        seismic_zone="III", terrain_category=3, soil="medium",
        sbc_kpa=200, fck=25, fy=500)


def test_all_elements_pass(ref):
    assert ref["ok"], {k: v.get("ok") for k, v in ref["columns"].items()}


def test_sbc_kpa_defaults_to_150_when_omitted():
    r = design_building(
        x_spacings_m=[3.5, 4.0, 3.5], y_spacings_m=[4.0, 4.5],
        storeys=2, storey_height_m=3.0,
        occupancy="residential_room", city="chennai",
        seismic_zone="III", terrain_category=3, soil="medium",
        fck=25, fy=500)
    assert r["inputs"]["sbc_kpa"] == 150.0
    assert any("sbc_kpa not provided" in a for a in r["assumptions"])


def test_sbc_kpa_explicit_value_used_unchanged():
    r = design_building(
        x_spacings_m=[3.5, 4.0, 3.5], y_spacings_m=[4.0, 4.5],
        storeys=2, storey_height_m=3.0,
        occupancy="residential_room", city="chennai",
        seismic_zone="III", terrain_category=3, soil="medium",
        sbc_kpa=200.0, fck=25, fy=500)
    assert r["inputs"]["sbc_kpa"] == 200.0
    assert not any("sbc_kpa not provided" in a for a in r["assumptions"])


def test_column_load_takedown_ballpark(ref):
    # interior column: trib 4.0 x 4.5 = 18 m2; w_floor ~ (D/1000*25+1.5+2) kN/m2
    col = ref["columns"]["interior"]
    at = 4.0 * 4.5
    # service load per floor should be within a sane band (slab+finish+LL+walls)
    per_floor = col["P_service_kN"] / 2
    assert 100 <= per_floor <= 300, per_floor


def test_seismic_base_shear_consistent(ref):
    lat = ref["lateral"]
    # zone III, R=5 SMRF, low-rise -> Ah = 0.16/2*2.5/5 = 0.04
    assert lat["seismic_Ah"] == pytest.approx(0.04, abs=0.005)
    assert lat["seismic_detailing_IS13920"] is True
    assert lat["governing"] in ("seismic", "wind")


def test_counts_add_up(ref):
    cols = ref["columns"]
    assert sum(c["count"] for c in cols.values()) == 4 * 3  # (3+1)x(2+1)
    assert cols["interior"]["count"] == 2
    assert cols["corner"]["count"] == 4


def test_quantities_sane(ref):
    q = ref["quantities"]
    total_conc = q["concrete_m3"]["total"]
    total_steel = q["steel_kg"]["total"]
    area = 11.0 * 8.5 * 2  # floor area x storeys
    assert 0.15 <= total_conc / area <= 0.60      # m3 concrete per m2 typical
    assert 15 <= total_steel / total_conc <= 160  # kg steel per m3 concrete


def test_json_serializable_and_deterministic(ref):
    s1 = json.dumps(ref, sort_keys=True, default=str)
    ref2 = design_building(
        x_spacings_m=[3.5, 4.0, 3.5], y_spacings_m=[4.0, 4.5],
        storeys=2, storey_height_m=3.0,
        occupancy="residential_room", city="chennai",
        seismic_zone="III", terrain_category=3, soil="medium",
        sbc_kpa=200, fck=25, fy=500)
    s2 = json.dumps(ref2, sort_keys=True, default=str)
    assert s1 == s2


def test_assumptions_echoed(ref):
    assert any("simply supported" in a for a in ref["assumptions"])
    assert len(ref["assumptions"]) >= 5


# --------------------------------------------------------------------------
# IS 456 Table 26 panel-case mapping (white-box unit tests on _panel_case)
#
# An edge is discontinuous when it lies on the building boundary. Edges
# perpendicular to x have length sy; edges perpendicular to y have length sx.
# Table 26 names edges by length: "short" edges are the pair of length
# lx = min(sx, sy), "long" edges the pair of length ly = max(sx, sy).
# --------------------------------------------------------------------------

# (i, j, nx, ny, sx, sy, expected_case)
_PANEL_CASE_VECTORS = [
    # --- 3x2 reference grid: x_spacings=[3.5, 4.0, 3.5], y_spacings=[4.0, 4.5]
    # corner: x-edges 1 disc (long, len sy=4.0), y-edges 1 disc (short, 3.5)
    (0, 0, 3, 2, 3.5, 4.0, 4),
    # x-interior, y-boundary; sx == sy -> sx treated as short span
    (1, 0, 3, 2, 4.0, 4.0, 2),
    # x-interior, j == ny-1 so the top (short, len sx=4.0) edge is disc
    (1, 1, 3, 2, 4.0, 4.5, 2),
    # far corner: one short + one long edge disc
    (2, 1, 3, 2, 3.5, 4.5, 4),
    (0, 1, 3, 2, 3.5, 4.5, 4),
    # --- single row of panels (ny == 1): both y-perpendicular edges disc
    # sx > sy -> y-edges (len sx) are the LONG pair -> two long edges disc
    (1, 0, 3, 1, 4.0, 3.0, 6),
    # ...same row, end panel: + one short (x-perpendicular, len sy) edge disc
    (0, 0, 3, 1, 4.0, 3.0, 8),
    (2, 0, 3, 1, 4.0, 3.0, 8),
    # sx < sy -> y-edges (len sx) are the SHORT pair -> two short edges disc
    (1, 0, 3, 1, 3.0, 4.0, 5),
    # ...plus one long edge disc at the row end
    (0, 0, 3, 1, 3.0, 4.0, 7),
    # --- single column of panels (nx == 1), mirror of the above
    (0, 1, 1, 3, 3.0, 4.0, 6),
    (0, 1, 1, 3, 4.0, 3.0, 5),
    # --- isolated single panel: four edges discontinuous
    (0, 0, 1, 1, 4.0, 3.0, 9),
    (0, 0, 1, 1, 4.0, 4.0, 9),
    # --- 3x3 grid: true interior and single-edge-discontinuous panels
    (1, 1, 3, 3, 4.0, 4.0, 1),
    # i == 0 -> one x-perpendicular (len sy=4.0 = long) edge disc
    (0, 1, 3, 3, 3.5, 4.0, 3),
    # j == 0 -> one y-perpendicular (len sx=3.5 = short) edge disc
    (1, 0, 3, 3, 3.5, 4.0, 2),
]


@pytest.mark.parametrize("i,j,nx,ny,sx,sy,expected", _PANEL_CASE_VECTORS)
def test_panel_case_mapping(i, j, nx, ny, sx, sy, expected):
    assert _panel_case(i, j, nx, ny, sx, sy) == expected


@pytest.mark.parametrize(
    "i,j,nx,ny,sx,sy,expected",
    [v for v in _PANEL_CASE_VECTORS if v[4] != v[5]])
def test_panel_case_span_swap_is_symmetric(i, j, nx, ny, sx, sy, expected):
    """Transposing the grid and the spans must give the same Table 26 case:
    the case depends on edge lengths and continuity, not on axis naming.
    (Square panels are excluded — there the short/long split is an arbitrary
    tie-break, so transposition can legitimately flip e.g. case 2 <-> 3.)"""
    assert _panel_case(j, i, ny, nx, sy, sx) == expected


@pytest.mark.parametrize("i,j,nx,ny,sx,sy,expected", _PANEL_CASE_VECTORS)
def test_panel_case_matches_table_26_continuity_pattern(
        i, j, nx, ny, sx, sy, expected):
    """Cross-check against tables.TABLE_26: the negative-moment coefficient
    nx (short-span direction) exists only if at least one LONG edge is
    continuous, and ny only if at least one SHORT edge is continuous."""
    n_x_disc = int(i == 0) + int(i == nx - 1)
    n_y_disc = int(j == 0) + int(j == ny - 1)
    n_short, n_long = (n_y_disc, n_x_disc) if sx <= sy else (n_x_disc, n_y_disc)
    row = TABLE_26[expected]
    assert (row["nx"] is None) == (n_long == 2)
    assert (row["ny"] is None) == (n_short == 2)


def test_panel_case_covers_all_nine_cases():
    """Cases 5-9 were unreachable before this fix; guard against regression."""
    produced = {c for *_, c in _PANEL_CASE_VECTORS}
    assert produced == set(range(1, 10)), sorted(set(range(1, 10)) - produced)


def test_single_row_building_uses_two_long_edges_discontinuous():
    """End-to-end: a single row of panels must now produce a case >= 5."""
    res = design_building(
        x_spacings_m=[3.5, 4.0, 3.5], y_spacings_m=[3.0],
        storeys=1, storey_height_m=3.0,
        occupancy="residential_room", city="chennai",
        seismic_zone="III", terrain_category=3, soil="medium",
        sbc_kpa=200, fck=25, fy=500)
    cases = {p["case_"] for p in res["slabs"].values()}
    assert cases <= {5, 6, 7, 8, 9}, cases
    assert 6 in cases, cases


# ---------------------------------------------------------------------------
# PA-5: IS 456 Table 5 exposure enforcement
# ---------------------------------------------------------------------------

def test_ref_building_at_grade_exposure_boundary_has_no_grade_violation(ref):
    # ref uses exposure default ("moderate", min_fck=25) with fck=25 exactly
    # -- the boundary case (fck == min_fck) must NOT raise increase_grade.
    grade_violations = [v for v in ref["violations"]
                        if v["remedy_hint"] == "increase_grade"
                        and v["member_type"] == "building"]
    assert grade_violations == []


def test_exposure_cover_propagates_to_beam(ref):
    # ref uses exposure default ("moderate" -> cover=30), which happens to
    # equal design_beam()'s own hardcoded default (30) -- so this alone
    # can't prove propagation happened rather than a coincidental match.
    # Use exposure="severe" (cover=45, != beam's default of 30) as the real
    # propagation proof: design_beam()'s returned inputs.cover must be 45,
    # not the function's own default.
    severe = design_building(
        x_spacings_m=[3.5, 4.0, 3.5], y_spacings_m=[4.0, 4.5],
        storeys=2, storey_height_m=3.0,
        occupancy="residential_room", city="chennai",
        seismic_zone="III", terrain_category=3, soil="medium",
        sbc_kpa=200, fck=30, fy=500, exposure="severe")
    beam_s = next(iter(severe["beams"].values()))
    assert beam_s["inputs"]["cover"] == 45.0

    # ref's beam (moderate default) still matches for a sanity cross-check.
    beam_ref = next(iter(ref["beams"].values()))
    assert beam_ref["inputs"]["cover"] == 30.0


def test_exposure_crack_width_limit_reaches_beam(ref):
    # ref (exposure="moderate") -> 0.3 mm cl 43.1 limit on every beam.
    for b in ref["beams"].values():
        assert b["design"]["crack_width"]["limit_mm"] == pytest.approx(0.3)
        assert b["design"]["crack_width"]["exposure"] == "moderate"

    extreme = design_building(
        x_spacings_m=[3.5, 4.0, 3.5], y_spacings_m=[4.0, 4.5],
        storeys=2, storey_height_m=3.0,
        occupancy="residential_room", city="chennai",
        seismic_zone="III", terrain_category=3, soil="medium",
        sbc_kpa=200, fck=40, fy=500, exposure="extreme")
    for b in extreme["beams"].values():
        assert b["design"]["crack_width"]["limit_mm"] == pytest.approx(0.2)
        assert b["design"]["crack_width"]["exposure"] == "extreme"


def test_crack_width_deemed_to_satisfy_assumption_string(monkeypatch):
    """When the explicit Annex F crack-width check fails but the cl
    26.3.3(b) deemed-to-satisfy bar-spacing route still passes, an
    assumption string must be emitted disclosing that reliance.

    In practice design_building()'s own D auto-sizing loop resolves the
    explicit check for realistic geometries before D hits its 1200 mm cap
    (deep sections often go "uncracked" under service moment, cl 43.1 note),
    so the trigger condition is forced deterministically here by patching
    tables.crack_limit_for_exposure to an impossible 0.0 mm limit -- this
    isolates and proves the building.py trigger/assumption-append logic
    itself, independent of whether a real design happens to land there.
    """
    from iscodes import tables as tbl
    monkeypatch.setattr(tbl, "crack_limit_for_exposure", lambda exposure: 0.0)

    r = design_building(
        x_spacings_m=[3.5, 4.0, 3.5], y_spacings_m=[4.0, 4.5],
        storeys=2, storey_height_m=3.0,
        occupancy="residential_room", city="chennai",
        seismic_zone="III", terrain_category=3, soil="medium",
        sbc_kpa=200, fck=25, fy=500, exposure="moderate")

    assert any(cw["design"]["crack_width"]["deemed_to_satisfy"]["ok"]
              and not cw["design"]["crack_width"]["ok"]
              for cw in r["beams"].values()), \
        "expected at least one beam relying on the deemed-to-satisfy route"
    assert any("deemed-to-satisfy" in a for a in r["assumptions"])
