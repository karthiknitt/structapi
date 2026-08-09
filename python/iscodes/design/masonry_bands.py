"""RC seismic bands in load-bearing masonry per IS 4326:1993.

Clause 7.4 requires continuous horizontal RC bands (lintel and roof) in
masonry buildings, all seismic zones II–V. Lintel band (primary) runs at lintel
level, continuous around the building perimeter and over internal walls;
roof band sits at roof/eave level (unless the roof is already an RC slab).
Both are reinforced per a zone/span-dependent table (cl 7.4.2).

This module provides standalone design for lintel and roof bands, selecting
longitudinal and transverse reinforcement based on seismic zone and the
horizontal wall span (distance between cross-wall supports) — the caller
decides which band type applies.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from .. import tables, rounding


# ---------------------------------------------------------------------------
# Reinforcement lookup table — IS 4326:1993 cl 7.4.2
# ---------------------------------------------------------------------------

# Minimum longitudinal reinforcement (n_bars, bar_dia_mm) by seismic zone
# and span (m) between cross-wall supports / building edges
SEISMIC_BAND_REINFORCEMENT = {
    "II": {
        "span_le_5m": {"n_bars": 2, "bar_dia_mm": 8},
        "span_gt_5m": {"n_bars": 2, "bar_dia_mm": 10},
    },
    "III": {
        "span_le_5m": {"n_bars": 2, "bar_dia_mm": 10},
        "span_gt_5m": {"n_bars": 2, "bar_dia_mm": 12},
    },
    "IV": {
        "span_le_5m": {"n_bars": 2, "bar_dia_mm": 12},
        "span_gt_5m": {"n_bars": 3, "bar_dia_mm": 12},
    },
    "V": {
        "span_le_5m": {"n_bars": 2, "bar_dia_mm": 12},
        "span_gt_5m": {"n_bars": 3, "bar_dia_mm": 16},
    },
}

# Transverse reinforcement (stirrups/links)
STIRRUP_DIA_MM = 6  # IS 4326 cl 7.4.2 typical detailing
STIRRUP_SPACING_MAX_MM = 150  # code maximum; floor to site standard 25 mm


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class BandResult:
    """Result of seismic band design.

    ok: True if all checks pass; False otherwise.
    checks: list of (check_name, pass_fail) tuples for traceability.
    data: dict with full design output (band geometry, reinforcement, etc.).
    """
    ok: bool
    checks: list = field(default_factory=list)
    data: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Main design function
# ---------------------------------------------------------------------------

def design_seismic_band(
    band_type: str,
    wall_thickness_mm: float,
    wall_span_m: float,
    seismic_zone: str,
    fck: float = 20.0,
    fy: float = 415.0,
    band_depth_mm: float | None = None,
) -> BandResult:
    """Design a seismic band (lintel or roof) in load-bearing masonry.

    Parameters
    ----------
    band_type : str
        "lintel" or "roof"; determines which band is being designed.
    wall_thickness_mm : float
        Thickness of the masonry wall in which the band runs (mm).
        The band width equals the wall thickness.
    wall_span_m : float
        Horizontal distance the band spans between two consecutive cross-wall
        supports or building edges (m). Used to select reinforcement from
        the code table (≤5m vs >5m branches).
    seismic_zone : str
        Seismic zone code: "II", "III", "IV", or "V".
        Raises KeyError if invalid (matches codebase pattern for table lookups).
    fck : float, optional
        Concrete grade (MPa), default 20.0.
    fy : float, optional
        Steel yield strength (MPa), default 415.0.
    band_depth_mm : float, optional
        Requested band depth (mm). If not provided or below 75 mm (the
        code minimum), floors to 75 mm per Site-Standard 25.

    Returns
    -------
    BandResult
        ok: True if all checks pass.
        checks: list of (description, pass_fail) tuples.
        data: dict with band_type, width_mm, depth_mm, n_bars, bar_dia_mm,
              Ast_prov_mm2, stirrup_dia_mm, stirrup_spacing_mm, seismic_zone,
              wall_span_m, etc.

    Raises
    ------
    KeyError
        If seismic_zone is not in the reinforcement table (e.g., "I" or "VI").
    """

    # Validate seismic zone (lookup will raise KeyError if invalid,
    # matching the pattern used by tables.ZONE_FACTOR)
    _ = SEISMIC_BAND_REINFORCEMENT[seismic_zone.upper()]
    seismic_zone = seismic_zone.upper()

    # 1. Band geometry
    width_mm = float(wall_thickness_mm)

    # Depth: minimum 75 mm per IS 4326 cl 7.4.1, floored to site standard
    depth_requested_mm = band_depth_mm if band_depth_mm is not None else 75.0
    depth_mm = max(rounding.site_dimension(depth_requested_mm), 75.0)
    # Ensure depth is a multiple of 25 mm (site standard)
    depth_mm = rounding.site_dimension(max(depth_requested_mm, 75.0))

    # 2. Select reinforcement from table based on zone and span
    span_key = "span_le_5m" if wall_span_m <= 5.0 else "span_gt_5m"
    rebar_spec = SEISMIC_BAND_REINFORCEMENT[seismic_zone][span_key]
    n_bars = rebar_spec["n_bars"]
    bar_dia_mm = rebar_spec["bar_dia_mm"]

    # Compute provided longitudinal steel area (mm2)
    bar_area_mm2 = math.pi * (bar_dia_mm ** 2) / 4.0
    Ast_prov_mm2 = n_bars * bar_area_mm2

    # 3. Transverse reinforcement (stirrups/links)
    stirrup_dia_mm = STIRRUP_DIA_MM
    # Floor stirrup spacing to site standard 25 mm but cap at code max
    stirrup_spacing_mm = rounding.site_spacing(
        STIRRUP_SPACING_MAX_MM, cap=STIRRUP_SPACING_MAX_MM
    )

    # 4. Checks
    checks = []

    # Band depth >= 75 mm (cl 7.4.1)
    checks.append(("band depth >= 75 mm (IS 4326 cl 7.4.1)", depth_mm >= 75.0))

    # Seismic zone valid (implicitly checked by KeyError on lookup)
    checks.append(("seismic zone in II–V", seismic_zone in SEISMIC_BAND_REINFORCEMENT))

    # Reinforcement table consistency check: verify the lookup succeeded
    # and the bar count/dia are sensible (non-zero, positive)
    checks.append(("reinforcement selected (n_bars > 0, dia > 0)",
                   n_bars > 0 and bar_dia_mm > 0))

    # Stirrup spacing is a multiple of 25 mm (site standard)
    checks.append(("stirrup spacing % 25 == 0 (site standard)",
                   stirrup_spacing_mm % 25.0 == 0))

    # Stirrup spacing does not exceed code maximum
    checks.append(("stirrup spacing <= code max 150 mm",
                   stirrup_spacing_mm <= STIRRUP_SPACING_MAX_MM + 1e-6))

    ok = all(chk for _, chk in checks)

    # 5. Output data
    data = {
        "band_type": band_type.lower(),
        "width_mm": width_mm,
        "depth_mm": depth_mm,
        "n_bars": n_bars,
        "bar_dia_mm": bar_dia_mm,
        "Ast_prov_mm2": Ast_prov_mm2,
        "stirrup_dia_mm": stirrup_dia_mm,
        "stirrup_spacing_mm": stirrup_spacing_mm,
        "seismic_zone": seismic_zone,
        "wall_span_m": wall_span_m,
        "fck_MPa": fck,
        "fy_MPa": fy,
        "notes": [
            f"Longitudinal: {n_bars} bars, {bar_dia_mm} mm dia (IS 4326:1993 Table, zone {seismic_zone}, span {'<=5m' if wall_span_m <= 5.0 else '>5m'})",
            f"Transverse: {stirrup_dia_mm} mm dia @ {stirrup_spacing_mm} mm c/c (IS 4326 cl 7.4.2)",
            "Band width = wall thickness (runs full width of masonry layer)",
        ],
    }

    return BandResult(ok=ok, checks=checks, data=data)
