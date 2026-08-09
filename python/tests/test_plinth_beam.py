"""Tests for `iscodes.design.plinth_beam.design_plinth_beam` (IS 4326 cl 7.3)."""

from iscodes.design.beam import design_beam
from iscodes.design.plinth_beam import design_plinth_beam


def test_nominal_span_tie_minimum_governs():
    """A typical G+1 span with nominal self-weight only (no wall load) and a
    small starter bar_dia: the zone III / span<=5m tie minimum (2 bars,
    10mm dia per the codebase's own IS 4326 cl 7.4.2 table, reused here for
    cl 7.3) should govern over the tiny flexural requirement."""
    r = design_plinth_beam(3.5, wall_load_kn_m=0.0, seismic_zone="III",
                           bar_dia=8.0)
    design = r["design"]

    assert design["tie_minimum_governs"] is True
    assert design["plinth_tie_min_bars"] == 2
    assert design["plinth_tie_min_dia_mm"] == 10
    assert design["n_bars"] == 2
    assert design["bar_dia"] == 10
    assert design["tie_minimum_governs_compression"] is True
    assert design["Asc_prov_mm2"] == design["Ast_prov_mm2"]

    assert r["ok"] is True
    assert ("plinth tie minimum reinforcement met (IS 4326 cl 7.3)", True) in r["checks"]


def test_heavy_wall_load_flexure_governs():
    """A heavy plinth-level wall load pushes design_beam()'s own flexural
    Ast above the tie minimum: flexure should govern, and the beam's own
    Ast_prov must be exactly what design_beam() alone would produce (the
    tie-minimum overlay must not silently replace a legitimate flexural
    design with a nominal one)."""
    span_m, b, D, fck, fy = 3.5, 230.0, 300.0, 20.0, 415.0
    wall_load_kn_m = 40.0
    cover, bar_dia, stirrup_dia = 30.0, 8.0, 8.0

    w_self_kn_m = (b / 1000.0) * (D / 1000.0) * 25.0
    direct = design_beam(span_m, w_self_kn_m + wall_load_kn_m, 0.0, b, D,
                         fck, fy, support="ss", cover=cover,
                         bar_dia=bar_dia, stirrup_dia=stirrup_dia)

    wrapped = design_plinth_beam(span_m, wall_load_kn_m=wall_load_kn_m,
                                 seismic_zone="III", b=b, D=D, fck=fck,
                                 fy=fy, cover=cover, bar_dia=bar_dia,
                                 stirrup_dia=stirrup_dia)
    design = wrapped["design"]

    assert design["tie_minimum_governs"] is False
    assert design["Ast_prov_mm2"] == direct["design"]["Ast_prov_mm2"]
    assert design["n_bars"] == direct["design"]["n_bars"]
    assert design["bar_dia"] == direct["design"]["bar_dia"]


def test_stirrup_spacing_site_standard_and_capped():
    r = design_plinth_beam(3.5, wall_load_kn_m=0.0, seismic_zone="V",
                           bar_dia=8.0)
    sv = r["design"]["stirrups"]["sv_provided"]

    assert sv % 25 == 0
    assert sv <= r["design"]["plinth_tie_stirrup_max_spacing_mm"]


def test_zone_lookup_varies_tie_minimum():
    """Different seismic zones at the same span should (generally) produce
    different minimum tie bar diameters -- sanity-checks the table lookup
    actually varies with zone rather than being a constant."""
    minima = {}
    for zone in ("II", "III", "IV", "V"):
        r = design_plinth_beam(3.5, wall_load_kn_m=0.0, seismic_zone=zone,
                               bar_dia=8.0)
        minima[zone] = (r["design"]["plinth_tie_min_bars"],
                        r["design"]["plinth_tie_min_dia_mm"])

    # Zone II (lightest) must differ from Zone V (heaviest).
    assert minima["II"] != minima["V"]
    # Minimum diameter must be monotonically non-decreasing with zone severity.
    dias = [minima[z][1] for z in ("II", "III", "IV", "V")]
    assert dias == sorted(dias)


def test_unknown_zone_raises_keyerror():
    import pytest
    with pytest.raises(KeyError):
        design_plinth_beam(3.5, seismic_zone="VI")
