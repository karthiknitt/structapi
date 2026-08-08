"""v0.2.0 — machine-readable violations[] + grid_lines on design_building().

Additive to the frozen v1 envelope (docs/PLANFORGE-INTEGRATION.md): when any
check in the building chain fails, data.violations carries structured
actual/limit/remedy_hint entries PlanForge can map to a solver constraint,
instead of parsing pass/fail check-name strings.
"""

import json

import pytest

from iscodes.design.building import design_building

ALLOWED_REMEDIES = {"reduce_span", "increase_section", "add_grid_line",
                    "increase_sbc", "increase_grade", "review_inputs"}
# "building" = whole-building-scope checks (e.g. fck vs exposure min grade,
# IS 456 Table 5) that don't belong to any single member.
ALLOWED_MEMBER_TYPES = {"beam", "column", "slab", "footing", "building"}


def _pass_kwargs():
    # the documented reference building (also used by test_building.py) —
    # every element passes with sane sections.
    return dict(
        x_spacings_m=[3.5, 4.0, 3.5], y_spacings_m=[4.0, 4.5],
        storeys=2, storey_height_m=3.0,
        occupancy="residential_room", city="chennai",
        seismic_zone="III", terrain_category=3, soil="medium",
        sbc_kpa=200, fck=25, fy=500)


def _fail_kwargs():
    # deliberately oversized bays (12 m), tall (5-storey, zone V), soft soil
    # + low SBC + low grade concrete — beams exceed shear/ductile-pt limits
    # even at the max section the auto-iteration reaches, columns fail
    # biaxial interaction, footings fail column-base bearing.
    return dict(
        x_spacings_m=[12.0, 12.0], y_spacings_m=[12.0],
        storeys=5, storey_height_m=3.5,
        occupancy="residential_room", city="chennai",
        seismic_zone="V", terrain_category=3, soil="soft",
        sbc_kpa=50, fck=20, fy=415)


@pytest.fixture(scope="module")
def passing():
    return design_building(**_pass_kwargs())


@pytest.fixture(scope="module")
def failing():
    return design_building(**_fail_kwargs())


# ---------------------------------------------------------------------------
# passing building
# ---------------------------------------------------------------------------

def test_passing_building_violations_empty(passing):
    assert passing["ok"] is True
    assert passing["violations"] == []


def test_passing_building_grid_lines_match_cumulative_spacings(passing):
    gl = passing["grid_lines"]
    assert gl["x_coords_m"] == [0.0, 3.5, 7.5, 11.0]
    assert gl["y_coords_m"] == [0.0, 4.0, 8.5]


# ---------------------------------------------------------------------------
# failing building
# ---------------------------------------------------------------------------

def test_failing_building_is_not_ok(failing):
    assert failing["ok"] is False


def test_violations_non_empty(failing):
    assert len(failing["violations"]) > 0


def test_violations_cover_multiple_member_types(failing):
    # this fixture is engineered to fail beams, columns AND footings —
    # exercises the extractor for more than one member type at once.
    types = {v["member_type"] for v in failing["violations"]}
    assert types >= {"beam", "column", "footing"}


def test_violation_schema(failing):
    required_keys = {"member_type", "axis", "grid_ref", "span_m", "check",
                     "actual", "limit", "unit", "remedy_hint"}
    for v in failing["violations"]:
        assert set(v.keys()) == required_keys
        assert v["member_type"] in ALLOWED_MEMBER_TYPES
        assert v["remedy_hint"] in ALLOWED_REMEDIES
        assert isinstance(v["check"], str) and v["check"]
        assert isinstance(v["grid_ref"], str) and v["grid_ref"]
        assert v["axis"] in ("x", "y", None)
        if v["span_m"] is not None:
            assert isinstance(v["span_m"], float)
        if v["actual"] is not None:
            assert isinstance(v["actual"], float)
        if v["limit"] is not None:
            assert isinstance(v["limit"], float)


def test_violation_actual_exceeds_limit_where_finite(failing):
    # every mapped check here is an "actual <= limit" style clause, so a
    # violation with both values finite must show actual > limit.
    # Exception: member_type="building" (e.g. fck vs exposure min grade) is a
    # "actual >= limit" style clause instead — its shortfall direction is
    # inverted (actual < limit on violation), so it's excluded here.
    checked_any = False
    for v in failing["violations"]:
        if v["member_type"] == "building":
            continue
        a, lim = v["actual"], v["limit"]
        if a is None or lim is None:
            continue
        if a != a or lim != lim:          # NaN guard
            continue
        if a in (float("inf"), float("-inf")) or lim in (float("inf"), float("-inf")):
            continue
        checked_any = True
        assert a > lim, v
    assert checked_any


def test_violations_deterministic():
    r1 = design_building(**_fail_kwargs())
    r2 = design_building(**_fail_kwargs())
    assert json.dumps(r1["violations"], sort_keys=True, default=str) == \
        json.dumps(r2["violations"], sort_keys=True, default=str)


def test_grid_lines_deterministic_and_shaped(failing):
    gl = failing["grid_lines"]
    assert gl["x_coords_m"] == [0.0, 12.0, 24.0]
    assert gl["y_coords_m"] == [0.0, 12.0]


# ---------------------------------------------------------------------------
# PA-5: IS 456 Table 5 exposure enforcement — grade-vs-exposure violation
# ---------------------------------------------------------------------------

def test_exposure_grade_violation_when_fck_below_min():
    # severe exposure requires min_fck=30 (tables.EXPOSURE); fck=20 is
    # durability-inadequate and must surface as a building-level violation.
    r = design_building(**{**_pass_kwargs(), "exposure": "severe", "fck": 20})
    grade_violations = [v for v in r["violations"]
                        if v["remedy_hint"] == "increase_grade"
                        and v["member_type"] == "building"]
    assert len(grade_violations) == 1
    v = grade_violations[0]
    assert "severe" in v["check"]
    assert v["actual"] == 20.0
    assert v["limit"] == 30.0


# ---------------------------------------------------------------------------
# per-member positional/grid geometry (Deliverable 2)
# ---------------------------------------------------------------------------

def test_beam_entries_carry_axis_and_grid_indices(passing):
    for bm in passing["beams"].values():
        assert bm["axis"] in ("x", "y")
        assert isinstance(bm["grid_line_indices"], list) and bm["grid_line_indices"]
        assert isinstance(bm["span_indices"], list) and bm["span_indices"]


def test_column_entries_carry_grid_intersections(passing):
    all_ij = []
    for kind, col in passing["columns"].items():
        gi = col["grid_intersections"]
        assert isinstance(gi, list) and len(gi) == col["count"]
        for pair in gi:
            assert len(pair) == 2
        all_ij += [tuple(p) for p in gi]
    # every grid intersection accounted for exactly once across classes
    nx, ny = len(passing["inputs"]["grid_x_m"]), len(passing["inputs"]["grid_y_m"])
    assert len(set(all_ij)) == len(all_ij) == (nx + 1) * (ny + 1)


def test_footing_entries_inherit_grid_intersections(passing):
    for kind, foot in passing["footings"].items():
        assert foot["grid_intersections"] == passing["columns"][kind]["grid_intersections"]


def test_slab_entries_carry_panel_indices(passing):
    for p in passing["slabs"].values():
        assert isinstance(p["panel_indices"], list) and p["panel_indices"]
        for pair in p["panel_indices"]:
            assert len(pair) == 2
