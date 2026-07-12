"""Reference-building validation of the whole-building design chain."""

import json

import pytest

from iscodes.design.building import design_building


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
