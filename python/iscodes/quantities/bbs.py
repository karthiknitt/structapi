"""Bar bending schedule (BBS) generation per IS 2502:1963.

Tabulation module — NOT a design module. It reads the reinforcement details
an existing `design_*()` function already computed (bar count, diameter,
member dimensions) from its return dict/dataclass and produces per-bar-mark
cutting lengths, unit weights, and total weights for a bill-of-quantities
(BOQ) steel take-off.

Units: mm for lengths/diameters, kg for weights (matching the rest of this
codebase's mm/N/MPa internal convention and kN/m public convention).

Standing simplifications (documented, not defects):
  - Main longitudinal bars (beam tension/compression, column verticals) are
    costed as a single continuous length with development-length anchorage
    at both ends (`span/height*1000 + 2*Ld`). Real detailing splits long
    members with lap splices; this is the same simplification the codebase
    already makes implicitly by not modelling splice locations elsewhere,
    and is adequate for a first-pass steel-quantity estimate, not a cutting
    list ready for site issue.
  - Stirrup/tie cutting length is measured to the bar's own centerline,
    approximated using the section's inner dimensions (b/D minus twice
    cover) as the rectangle "to be enclosed" — a standard simplification
    (ignores the small offset introduced by the stirrup's own bar
    thickness) used throughout basic BBS teaching material and adequate at
    this precision.
"""

from __future__ import annotations

import math

from .. import tables

# ---------------------------------------------------------------------------
# Core helpers (IS 1786 / IS 2502)
# ---------------------------------------------------------------------------


def bar_unit_weight_kg_m(dia_mm: float) -> float:
    """IS 1786 standard HYSD/TMT unit weight: dia^2 / 162 kg/m.

    Verified against commonly-cited reference values: 12 mm -> 0.888 kg/m,
    16 mm -> 1.580 kg/m (both reproduce to 3 s.f. with this constant).
    """
    return dia_mm ** 2 / 162.0


#: IS 2502 Table 1 (approximate, standard detailing-practice values):
#: extra length added at a bend, as a multiple of bar diameter.
_BEND_ALLOWANCE_FACTOR = {45: 1.0, 90: 2.0, 135: 3.0}


def bend_allowance_mm(dia_mm: float, angle_deg: float) -> float:
    """Extra length added at a bend, IS 2502 Table 1 (approximate, standard
    practice values): 45deg -> 1*dia, 90deg -> 2*dia, 135deg -> 3*dia.

    Only the three angles this codebase's own detailing produces (stirrup/
    tie corners at 90 deg, IS 13920 ductile hoop hooks at 135 deg, plus the
    commonly-tabulated 45 deg case) are supported.
    """
    key = round(angle_deg)
    if key not in _BEND_ALLOWANCE_FACTOR:
        raise ValueError(
            f"bend_allowance_mm: unsupported angle {angle_deg} deg "
            f"(supported: {sorted(_BEND_ALLOWANCE_FACTOR)})")
    return _BEND_ALLOWANCE_FACTOR[key] * dia_mm


def hook_allowance_mm(dia_mm: float, hook_type: str = "u_hook") -> float:
    """Standard hook length addition, IS 2502. A U-type (semicircular,
    ~180 deg) hook — used at the free ends of stirrups and at main-bar
    anchorages — adds approximately 9*dia beyond the straight bar length,
    a commonly-cited practice value covering both the bend and its
    straight extension.
    """
    if hook_type != "u_hook":
        raise ValueError(f"hook_allowance_mm: unsupported hook_type {hook_type!r}")
    return 9.0 * dia_mm


#: IS 13920 ductile hoop hook: "135 deg bend, extend 10*dia beyond bend,
#: closed hoop" — the exact wording already used in beam.py/column.py's own
#: ductile_stirrups / confine_hook detailing notes. Kept distinct from the
#: generic u_hook above because it is a codified seismic-detailing
#: requirement, not a general practice figure.
def _seismic_hook_allowance_mm(dia_mm: float) -> float:
    return bend_allowance_mm(dia_mm, 135) + 10.0 * dia_mm


# ---------------------------------------------------------------------------
# Rectangular stirrup/tie cutting length (shared by beam stirrups and
# column ties/hoops)
# ---------------------------------------------------------------------------


def _rect_link_cutting_length_mm(b_mm: float, D_mm: float, cover_mm: float,
                                  link_dia_mm: float, seismic: bool) -> float:
    """Cutting length of a closed rectangular link (stirrup or tie/hoop).

    Perimeter is measured to the link's own centerline, approximated by the
    section's inner dimensions (b/D minus twice cover). Four 90-degree
    corner bends are additive (bend_allowance_mm is defined as an ADDITION
    to the straight length, per its own docstring — using it as a
    subtraction elsewhere would contradict that definition, so this
    function stays internally consistent and adds at every bend). The two
    free ends close with hooks: IS 13920 135-degree ductile hooks when
    `seismic`, else a standard U-hook.
    """
    b_inner = b_mm - 2 * cover_mm
    D_inner = D_mm - 2 * cover_mm
    perimeter = 2 * (b_inner + D_inner)
    corner_bends = 4 * bend_allowance_mm(link_dia_mm, 90)
    if seismic:
        hooks = 2 * _seismic_hook_allowance_mm(link_dia_mm)
    else:
        hooks = 2 * hook_allowance_mm(link_dia_mm, "u_hook")
    return perimeter + corner_bends + hooks


def _mark_entry(mark: str, shape: str, dia_mm: float, cutting_length_mm: float,
                 count: int) -> dict:
    unit_weight = bar_unit_weight_kg_m(dia_mm)
    total_length_m = cutting_length_mm * count / 1000.0
    return {
        "mark": mark,
        "shape": shape,
        "dia_mm": dia_mm,
        "cutting_length_mm": cutting_length_mm,
        "count": count,
        "unit_weight_kg_m": unit_weight,
        "total_weight_kg": unit_weight * total_length_m,
    }


# ---------------------------------------------------------------------------
# Per-member bar-mark extraction
# ---------------------------------------------------------------------------


def beam_bar_marks(beam_result: dict, span_m: float | None = None) -> list[dict]:
    """Extract bar marks (main tension, main compression if doubly
    reinforced, stirrups) from a `design_beam()` result dict.

    Each entry: {"mark": str, "shape": str, "dia_mm": float,
                 "cutting_length_mm": float, "count": int,
                 "unit_weight_kg_m": float, "total_weight_kg": float}
    """
    inputs = beam_result["inputs"]
    design = beam_result["design"]
    span_m = span_m if span_m is not None else inputs["span_m"]
    fck, fy = inputs["fck"], inputs["fy"]
    seismic = bool(inputs.get("seismic", False))

    bar_dia = design["bar_dia"]
    n_bars = design["n_bars"]
    n_bars_comp = design.get("n_bars_comp", 0)
    stirrup_dia = inputs["stirrup_dia"]
    b, D, cover = inputs["b"], inputs["D"], inputs["cover"]

    Ld = tables.development_length(bar_dia, fy, fck)
    span_mm = span_m * 1000.0

    marks = [
        _mark_entry("beam-main-tension", "straight, dev-length anchorage "
                    "each end", bar_dia, span_mm + 2 * Ld, n_bars),
    ]
    if n_bars_comp > 0:
        marks.append(_mark_entry(
            "beam-main-compression", "straight, dev-length anchorage each "
            "end", bar_dia, span_mm + 2 * Ld, n_bars_comp))

    # Top (hogging) steel layer -- added by the continuous-beam task, which
    # landed after this function was written. building.py's beam_steel_area()
    # was patched to include it (see that function's comment); BBS, a
    # different consumer of the same design_beam() output, was missed.
    top_steel = design.get("top_steel")
    if top_steel and top_steel.get("n_bars", 0) > 0:
        top_bar_dia = top_steel.get("bar_dia", bar_dia)
        top_Ld = tables.development_length(top_bar_dia, fy, fck)
        marks.append(_mark_entry(
            "beam-top-tension", "straight, dev-length anchorage each end "
            "(hogging/support steel)", top_bar_dia,
            span_mm + 2 * top_Ld, top_steel["n_bars"]))
        n_bars_top_comp = top_steel.get("n_bars_comp", 0)
        if n_bars_top_comp > 0:
            marks.append(_mark_entry(
                "beam-top-compression", "straight, dev-length anchorage "
                "each end (hogging/support steel)", top_bar_dia,
                span_mm + 2 * top_Ld, n_bars_top_comp))

    # Ductile two-zone stirrup schedule (IS 13920 cl 6.3) takes over from
    # the uniform IS 456 shear spacing when seismic -- mirror the pattern
    # column_bar_marks() already uses for confine_spacing_max.
    ductile_stirrups = design.get("ductile_stirrups")
    sv_provided = (ductile_stirrups["confining_zone_spacing_mm"]
                   if ductile_stirrups else design["stirrups"]["sv_provided"])
    if sv_provided and sv_provided > 0:
        n_stirrups = math.ceil(span_mm / sv_provided) + 1
        cutting_length = _rect_link_cutting_length_mm(b, D, cover, stirrup_dia,
                                                        seismic)
        marks.append(_mark_entry("beam-stirrup", "closed rectangular "
                                  "stirrup", stirrup_dia, cutting_length,
                                  n_stirrups))
    return marks


def column_bar_marks(column_result, L_column_m: float, b: float, D: float,
                      fck: float, fy: float, n_bars: int, bar_dia: float,
                      cover: float, tie_dia: float,
                      seismic: bool = False) -> list[dict]:
    """Extract bar marks (main longitudinal bars, ties/hoops) from a
    `design_column()` result (`ColumnCheck` dataclass) plus the section
    inputs used to produce it.

    `design_column()`'s return value does not echo its own b/D/fck/fy/
    n_bars/bar_dia/cover/tie_dia back in a nested `inputs` dict the way
    `design_beam()` does (only derived quantities live in `.data`), so
    these are accepted as explicit parameters here rather than re-read from
    the result.
    """
    data = column_result.data
    Ld = tables.development_length(bar_dia, fy, fck)
    L_mm = L_column_m * 1000.0

    marks = [
        _mark_entry("column-main", "straight, dev-length anchorage each "
                    "end (single-lift simplification, no lap splice "
                    "modelled)", bar_dia, L_mm + 2 * Ld, n_bars),
    ]

    spacing = data.get("confine_spacing_max") if seismic else data.get("tie_pitch_max")
    if spacing:
        n_ties = math.ceil(L_mm / spacing) + 1
        cutting_length = _rect_link_cutting_length_mm(b, D, cover, tie_dia,
                                                        seismic)
        shape = ("closed rectangular confining hoop (IS 13920 cl 7.4)"
                  if seismic else "closed rectangular tie")
        marks.append(_mark_entry("column-tie", shape, tie_dia, cutting_length,
                                  n_ties))
    return marks


def slab_bar_marks(strip_result: dict, span_m: float, strip_width_m: float,
                    bar_dia: float, cover: float) -> list[dict]:
    """Extract bar marks for a slab reinforcement strip.

    `strip_result` is a design_one_way_slab()/design_two_way_slab() strip
    dict (e.g. the `"main"` key of a one-way result, or one of the
    `"strips"` entries of a two-way result) carrying at least a `"spacing"`
    key (bar spacing, mm c/c, as produced by `slab.py`'s `_strip_design`).

    Straight bars at a given spacing across `strip_width_m`, spanning
    `span_m` in the reinforced direction, with standard end hooks — no
    bends beyond that.
    """
    spacing = strip_result["spacing"]
    count = math.floor(strip_width_m * 1000.0 / spacing) + 1
    cutting_length = span_m * 1000.0 + 2 * hook_allowance_mm(bar_dia, "u_hook")
    return [_mark_entry("slab-main", "straight with end hooks", bar_dia,
                         cutting_length, count)]


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------


def bbs_summary(bar_marks: list[dict]) -> dict:
    """Aggregate a list of bar-mark entries into totals by diameter and a
    grand total weight — the BOQ-facing summary.

    Returns {"by_diameter_kg": {dia_mm: total_kg, ...}, "total_kg": ...}.
    """
    by_diameter: dict[float, float] = {}
    total = 0.0
    for mark in bar_marks:
        dia = mark["dia_mm"]
        weight = mark["total_weight_kg"]
        by_diameter[dia] = by_diameter.get(dia, 0.0) + weight
        total += weight
    return {"by_diameter_kg": by_diameter, "total_kg": total}
