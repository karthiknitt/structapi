"""Dog-legged RC staircase (waist slab + landing) per IS 456:2000 cl 33.

A dog-legged stair is two straight flights with a 180-degree turn at an
intermediate landing (no open well) — the standard G+1 residential stair.
Both flights are assumed identical, so this module designs ONE
representative flight (going + the intermediate landing it lands on) and
reuses that design for both (`n_flights: 2` in the return, informational
only — no doubling of steel/depth is implied, each flight is built the
same).

Design basis:
- Effective span: IS 456 cl 33.1(b) — where the landing slab spans in the
  same direction as the flight (the usual G+1 case: wall/beam support at
  the top of the flight, intermediate landing at the bottom), flight and
  landing act together as one slab spanning wall-to-wall/beam-to-wall, so
  the FULL landing width is added to the going (not halved, not capped at
  1 m — that halved/1m-capped rule is cl 33.1(c), which applies only when
  the landing spans TRANSVERSE to the flight and does not participate in
  carrying the flight's load). This module's default (one landing, full
  width, added to going) matches cl 33.1(b) for the common case of a wall
  support at the top of the flight and an in-line intermediate landing at
  the bottom. If a project's stair has landings at BOTH ends spanning
  in-line, add both landing widths before calling, or extend this
  function.
- Loading: flexure/shear/deflection are all done by
  `design_one_way_slab()` (cl 24 / Annex D-adjacent one-way slab design) —
  this module's job is only to derive the correct effective span and the
  correct equivalent UDL (self weight of a SLOPED waist slab plus
  triangular step loads differs from a flat slab of the same thickness).

Units: geometry in m/mm as labelled, loads kN/m2, per 1 m width design
(mirrors `design_one_way_slab`).
"""

from __future__ import annotations

import math

from .. import rounding
from .slab import design_one_way_slab

_D_CAP_MM = 300.0
_D_GROWTH_MM = 25.0


def design_staircase(going_m: float, riser_mm: float, tread_mm: float,
                     n_risers: int, landing_width_m: float,
                     waist_thickness_mm: float | None = None,
                     fck: float = 20.0, fy: float = 415.0,
                     finish_kn_m2: float = 0.5, LL_kn_m2: float = 3.0,
                     cover: float = 20.0, bar_dia: int = 10) -> dict:
    """Design one flight (+ intermediate landing) of a dog-legged staircase.

    `going_m`: horizontal run of ONE flight. `n_risers`: risers in that one
    flight. A dog-legged stair has two identical flights (`n_flights: 2` in
    the return is informational: total rise = 2 * n_risers * riser_mm, and
    only one flight is actually designed/reinforced here since the second
    is built identically).

    Effective span (cl 33.1(b)): going + the in-line landing width (see
    module docstring for the cl 33.1(b) vs 33.1(c) distinction).

    `waist_thickness_mm`: if given, used as-is (no auto-growth — caller's
    explicit choice is respected, mirroring `design_one_way_slab`'s own
    auto/explicit split). If omitted, a trial thickness is derived from the
    span/effective-depth heuristic and grown by 25 mm steps (Site-Standard
    25) until the design converges (`ok`) or a 300 mm cap is hit.
    """
    # ---- Step 1: effective span, cl 33.1(b) -------------------------------
    L_eff_m = going_m + landing_width_m

    # ---- Step 2: slope factor + equivalent UDL ----------------------------
    slope_factor = math.sqrt(1.0 + (riser_mm / tread_mm) ** 2)

    def _w_dl_avg(D_mm: float) -> float:
        waist_extra_kn_m2 = (D_mm / 1000.0 * 25.0) * (slope_factor - 1.0)
        step_load_kn_m2 = 0.5 * (riser_mm / 1000.0) * 25.0
        going_w_dl = waist_extra_kn_m2 + step_load_kn_m2 + finish_kn_m2
        return (going_w_dl * going_m
                + finish_kn_m2 * landing_width_m) / L_eff_m

    # ---- Step 3: waist thickness (trial + growth loop) ---------------------
    auto = waist_thickness_mm is None
    if auto:
        d_trial = L_eff_m * 1000.0 / (20.0 * 1.4)  # ss heuristic, cl 24.1 basis
        D_mm = rounding.site_dimension(d_trial + cover + bar_dia / 2.0)
    else:
        D_mm = float(waist_thickness_mm)

    result = None
    while True:
        w_dl_avg = _w_dl_avg(D_mm)
        result = design_one_way_slab(L_eff_m, w_dl_avg, LL_kn_m2, fck, fy,
                                     support="ss", D_mm=D_mm, cover=cover,
                                     bar_dia=bar_dia)
        if result["ok"] or not auto or D_mm >= _D_CAP_MM:
            break
        D_mm += _D_GROWTH_MM

    comfort_ok = (150.0 <= riser_mm <= 190.0) and (250.0 <= tread_mm <= 300.0)
    # Non-structural usability check — deliberately NOT folded into `checks`
    # / `ok` (those stay purely IS 456 structural), and its name string is
    # explicit that it is a thumb rule, not a code clause.
    comfort_check = ("riser/tread within comfort range 150-190mm riser / "
                     "250-300mm tread (thumb rule, not a code clause)",
                     comfort_ok)

    return {
        **result,
        "going_m": going_m,
        "riser_mm": riser_mm,
        "tread_mm": tread_mm,
        "n_risers": n_risers,
        "landing_width_m": landing_width_m,
        "L_eff_m": L_eff_m,
        "slope_factor": slope_factor,
        "waist_thickness_mm": D_mm,
        "n_flights": 2,
        "geometry_sanity_check": comfort_check,
    }
