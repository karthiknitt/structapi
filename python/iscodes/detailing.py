"""Bar / detailing helpers per IS 456:2000 cl 26 and IS 13920:2016.

Covers: standard bar area lookup, practical bar-count/spacing selection for
beams/columns and slabs/walls, lap length (cl 26.2.5), anchorage checks
(cl 26.2.1), and ductile-detailing sanity checks (IS 13920 cl 6-8) built on
tables.DUCTILE.
"""

from __future__ import annotations

import math

from . import tables

#: Standard bar areas (mm2) by diameter (mm)
BAR_AREAS = {dia: math.pi * dia ** 2 / 4 for dia in (8, 10, 12, 16, 20, 25, 28, 32)}


def select_bars(ast_req_mm2: float, dia_pref: tuple = (16, 20, 25),
                min_bars: int = 2, max_layers: int = 2,
                b_mm: float | None = None, cover: float = 30,
                agg: float = 20) -> tuple:
    """Pick a practical bar count/diameter combination for a beam/column face.

    Tries each diameter in `dia_pref`, finds the smallest bar count (>= min_bars)
    that provides Ast >= ast_req_mm2, and — if `b_mm` (section width) is given —
    checks clear spacing >= max(dia, agg+5) (IS 456 cl 26.3.2), splitting across
    up to `max_layers` equal layers if a single layer will not fit.

    Returns (n_bars, dia, ast_prov, note). Among all diameters that satisfy the
    requirement, the candidate with the least steel excess (most economical) is
    chosen; ties broken by fewer bars.
    """
    min_spacing_of = lambda dia: max(dia, agg + 5)

    def fits_in_layers(n, dia):
        """Split n bars across up to max_layers equal layers; check spacing."""
        if b_mm is None:
            return True
        for layers in range(1, max_layers + 1):
            per_layer = math.ceil(n / layers)
            if per_layer < 1:
                continue
            if per_layer == 1:
                spacing_ok = True
            else:
                clear = (b_mm - 2 * cover - per_layer * dia) / (per_layer - 1)
                spacing_ok = clear >= min_spacing_of(dia)
            if spacing_ok:
                return True
        return False

    candidates = []
    for dia in dia_pref:
        area = BAR_AREAS[dia]
        n = min_bars
        while n <= 40:
            ast_prov = n * area
            if ast_prov >= ast_req_mm2 and fits_in_layers(n, dia):
                candidates.append((n, dia, ast_prov))
                break
            n += 1

    if not candidates:
        return (None, None, 0.0, "no combination found within limits")

    n, dia, ast_prov = min(candidates, key=lambda c: (c[2] - ast_req_mm2, c[0]))
    note = (f"{n}-T{dia} provided, Ast_prov={ast_prov:.1f} mm2 "
            f"(req {ast_req_mm2:.1f} mm2), IS 456 cl 26.3.2 spacing checked"
            if b_mm else
            f"{n}-T{dia} provided, Ast_prov={ast_prov:.1f} mm2 (req {ast_req_mm2:.1f} mm2)")
    return (n, dia, ast_prov, note)


def select_bar_spacing(ast_req_per_m: float, dia_pref: tuple = (8, 10, 12, 16),
                       max_spacing: float = 300.0, target_spacing: float = 150.0) -> tuple:
    """Pick bar dia + spacing (rounded down to 5 mm) for a slab/wall face.

    For each candidate diameter, raw spacing = area*1000/ast_req_per_m, capped
    at `max_spacing` (IS 456 cl 26.3.3(b): lesser of 3d or 300 mm), then rounded
    down to the nearest 5 mm (rounding down keeps Ast_prov >= Ast_req). The
    diameter whose resulting spacing is closest to `target_spacing` (a practical
    mid-range default, avoiding both over-congested and overly sparse bars) is
    selected.
    """
    candidates = []
    for dia in dia_pref:
        area = BAR_AREAS[dia]
        raw = area * 1000.0 / ast_req_per_m
        capped = min(raw, max_spacing)
        rounded = math.floor(capped / 5.0) * 5.0
        rounded = max(rounded, 5.0)
        ast_prov = area * 1000.0 / rounded
        candidates.append((dia, rounded, ast_prov))

    dia, spacing, ast_prov = min(candidates, key=lambda c: abs(c[1] - target_spacing))
    return (dia, spacing, ast_prov)


def lap_length(phi: float, fy: float, fck: float, tension: bool = True) -> float:
    """Lap splice length, mm. IS 456 cl 26.2.5.1.

    Tension: max(Ld, 30*phi). Compression: max(Ld, 24*phi).
    """
    ld = tables.development_length(phi, fy, fck, deformed=True, compression=not tension)
    return max(ld, 30 * phi) if tension else max(ld, 24 * phi)


def anchorage_check(available_mm: float, phi: float, fy: float, fck: float) -> dict:
    """Check whether available anchorage length meets Ld. IS 456 cl 26.2.1."""
    required = tables.development_length(phi, fy, fck)
    return {
        "required_mm": required,
        "available_mm": available_mm,
        "ok": available_mm >= required,
    }


def ductile_beam_checks(b: float, D: float, pt: float, pc: float) -> list:
    """Ductile beam detailing sanity checks. IS 13920:2016 cl 6.1-6.2.

    pt, pc: tension/compression steel ratios as PERCENT (100*Ast/(b*d)).
    """
    d = tables.DUCTILE
    checks = []
    checks.append(("beam width >= 200 mm (IS13920 cl 6.1.3)", b >= d["beam_min_b"]))
    checks.append(("b/D >= 0.3 (IS13920 cl 6.1.2)", D > 0 and b / D >= 0.3))
    checks.append(("max tension steel pt <= 2.5% (IS13920 cl 6.2.2)",
                   pt <= d["beam_max_pt"] * 100))
    checks.append(("compression steel pc >= 0.5*pt at section (IS13920 cl 6.2.3)",
                   pc >= 0.5 * pt))
    return checks


def ductile_column_checks(b: float, D: float, hoop_spacing: float, bar_dia: float) -> list:
    """Ductile column detailing sanity checks. IS 13920:2016 cl 7.1, 8.1."""
    d = tables.DUCTILE
    checks = []
    checks.append(("min column dimension >= 300 mm, if supporting > 2 storeys "
                   "(IS13920 cl 7.1.2)", min(b, D) >= d["column_min_b_storeys"]))
    checks.append(("short-to-long side ratio >= 0.4 (IS13920 cl 7.1.1)",
                   max(b, D) > 0 and min(b, D) / max(b, D) >= 0.4))
    max_hoop_spacing = min(d["confine_spacing_max"], d["confine_spacing_6db"] * bar_dia)
    checks.append((f"hoop spacing <= min(100mm, 6*dia)={max_hoop_spacing:.0f} mm "
                   "in confining length lo (IS13920 cl 8.1)",
                   hoop_spacing <= max_hoop_spacing))
    return checks
