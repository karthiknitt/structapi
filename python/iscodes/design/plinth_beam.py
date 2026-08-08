"""RC plinth-level tie beam design per IS 4326:1993 cl 7.3 (mandatory in
seismic Zones III, IV, V) / IS 1893 (Part 1):2016 recommendation.

A continuous RC "plinth band" or tie beam connecting all column/footing
tops at plinth level ties the structure together against differential
settlement and distributes lateral seismic forces between isolated
footings. It rarely carries significant gravity load beyond its own
self-weight and (if present) a nominal ground-floor wall up to plinth
level -- so its design is dominated by a code-mandated MINIMUM tie
reinforcement, not flexure.

This module wraps `design.beam.design_beam()` (flexure + shear + bar
selection + deflection, unchanged) and layers a zone/span-dependent
minimum reinforcement + maximum stirrup spacing floor on top, taking the
governing (larger Ast / tighter spacing) of the two -- never silently
replacing a legitimate flexural design with a nominal one.

Reinforcement table -- corrected from the task brief's draft table:
this codebase's `masonry_bands.py` already encodes IS 4326:1993 cl 7.4.2's
band reinforcement table (lintel/roof bands). IS 4326 cl 7.3 does not
tabulate a *separate* plinth-band table; SP 34:1987 ("Handbook on
Concrete Reinforcement and Detailing") and NDMA seismic-retrofit
guidelines apply the SAME minimum longitudinal reinforcement schedule to
plinth bands as to lintel/roof bands. Rather than inventing a second,
divergent, unverifiable table (the brief's draft had an unexplained
"2 bars" vs "4 bars total" split between zones III and IV/V that doesn't
trace to a specific clause), this module reuses
`masonry_bands.SEISMIC_BAND_REINFORCEMENT` as the per-face minimum,
applied symmetrically to BOTH the tension and compression faces of the
tie beam (a plinth beam, unlike a masonry band, has bars on both faces
by construction). This also keeps the two modules from silently
diverging if the band table is ever corrected.

Stirrup cap: 150 mm c/c uniformly across zones II-V, per cl 7.4.2 (the
same value already used for masonry lintel/roof bands in this codebase).
No verified IS 4326 clause was found mandating a tighter, zone-V-specific
cap for plinth bands specifically, so no such distinction is introduced
here -- a deliberate, documented deviation from the brief's suggestion of
"tighter stirrup spacing" for zone V (see task report).

Units: kN, m, mm, MPa at the API surface (matches beam.py / footing.py).
"""

from __future__ import annotations

import math

from .. import rounding
from . import beam as beam_design
from .masonry_bands import SEISMIC_BAND_REINFORCEMENT

#: IS 4326:1993 cl 7.4.2 stirrup spacing cap, reused for plinth ties (cl 7.3)
STIRRUP_SPACING_MAX_MM = 150.0

_VALID_ZONES = ("II", "III", "IV", "V")


def _tie_minimum(seismic_zone: str, span_m: float) -> dict:
    """Zone/span minimum tie bar count + diameter, per face."""
    zone = seismic_zone.upper()
    if zone not in SEISMIC_BAND_REINFORCEMENT:
        raise KeyError(
            f"unknown seismic zone {seismic_zone!r}; expected one of {_VALID_ZONES}")
    span_key = "span_le_5m" if span_m <= 5.0 else "span_gt_5m"
    spec = SEISMIC_BAND_REINFORCEMENT[zone][span_key]
    return {"n_bars": spec["n_bars"], "bar_dia_mm": spec["bar_dia_mm"]}


def design_plinth_beam(span_m: float, wall_load_kn_m: float = 0.0,
                       b: float = 230.0, D: float = 300.0,
                       fck: float = 20.0, fy: float = 415.0,
                       seismic_zone: str = "III", cover: float = 30.0,
                       bar_dia: float = 12.0, stirrup_dia: float = 8.0) -> dict:
    """Design a plinth-level RC tie beam (IS 4326:1993 cl 7.3).

    Reuses `design_beam()` for flexure/shear/deflection under self-weight
    (`b/1000 * D/1000 * 25` kN/m) plus an optional plinth-level wall load,
    then overlays a zone/span-dependent minimum tie reinforcement (both
    faces) and a maximum stirrup spacing cap, taking the governing
    (larger Ast / tighter spacing) of `design_beam()`'s own result and
    the tie minimum.

    Returns the `design_beam()` result dict with additive `design` keys:
    `plinth_tie_min_bars`, `plinth_tie_min_dia_mm`,
    `plinth_tie_stirrup_max_spacing_mm`, `seismic_zone`,
    `tie_minimum_governs` (tension face), `tie_minimum_governs_compression`
    (compression face) -- plus an appended check tuple
    `("plinth tie minimum reinforcement met (IS 4326 cl 7.3)", ok)`.

    Raises `KeyError` if `seismic_zone` is not one of II/III/IV/V.
    """
    zone = seismic_zone.upper()
    w_self_kn_m = (b / 1000.0) * (D / 1000.0) * 25.0  # concrete unit wt 25 kN/m3
    w_dl_kn_m = w_self_kn_m + wall_load_kn_m

    result = beam_design.design_beam(span_m, w_dl_kn_m, 0.0, b, D, fck, fy,
                                     support="ss", cover=cover, bar_dia=bar_dia,
                                     stirrup_dia=stirrup_dia)

    tie_min = _tie_minimum(zone, span_m)
    area_bar_min = math.pi * tie_min["bar_dia_mm"] ** 2 / 4.0
    Ast_tie_min_mm2 = tie_min["n_bars"] * area_bar_min

    design = result["design"]

    # ---- tension face: governing = max(design_beam()'s own Ast_prov, tie
    # minimum) -- only overwritten when the tie minimum actually governs ---
    Ast_prov = design["Ast_prov_mm2"]
    tie_minimum_governs = Ast_tie_min_mm2 > Ast_prov
    if tie_minimum_governs:
        design["Ast_prov_mm2"] = Ast_tie_min_mm2
        design["n_bars"] = tie_min["n_bars"]
        design["bar_dia"] = tie_min["bar_dia_mm"]
        design["pt_percent"] = 100.0 * Ast_tie_min_mm2 / (b * design["d_mm"])

    # ---- compression face: same zone/span minimum applied symmetrically --
    # (a tie beam carries bars on both faces even where pure flexure design
    # would not require compression steel at all)
    Asc_prov = design["Asc_prov_mm2"]
    tie_minimum_governs_compression = Ast_tie_min_mm2 > Asc_prov
    if tie_minimum_governs_compression:
        design["Asc_prov_mm2"] = Ast_tie_min_mm2
        design["n_bars_comp"] = tie_min["n_bars"]

    # ---- stirrups: cap design_beam()'s shear-governed spacing at the
    # tie-beam maximum -- "ductile caps only tighten" pattern, same as
    # beam.py's IS 13920 ductile_stirrups overlay ---------------------------
    sv_shear = design["stirrups"]["sv_provided"]
    sv_capped = rounding.site_spacing(STIRRUP_SPACING_MAX_MM)
    if sv_shear > 0:
        sv_capped = min(sv_capped, sv_shear)
    design["stirrups"]["sv_provided"] = sv_capped

    design["plinth_tie_min_bars"] = tie_min["n_bars"]
    design["plinth_tie_min_dia_mm"] = tie_min["bar_dia_mm"]
    design["plinth_tie_stirrup_max_spacing_mm"] = STIRRUP_SPACING_MAX_MM
    design["seismic_zone"] = zone
    design["tie_minimum_governs"] = tie_minimum_governs
    design["tie_minimum_governs_compression"] = tie_minimum_governs_compression

    tie_ok = (design["Ast_prov_mm2"] >= Ast_tie_min_mm2 - 1e-6
             and design["Asc_prov_mm2"] >= Ast_tie_min_mm2 - 1e-6
             and sv_capped <= STIRRUP_SPACING_MAX_MM + 1e-6)
    result["checks"].append(
        ("plinth tie minimum reinforcement met (IS 4326 cl 7.3)", tie_ok))
    result["ok"] = result["ok"] and tie_ok

    return result
