"""Liquid-retaining structures per IS 3370 (Parts 1, 2: 2021; Part 4: 1967).

Covers ground-supported circular and rectangular water tanks and underground
sumps (earth + groundwater outside, uplift/flotation).

Design basis (IS 3370-2:2021): Limit State — ULS strength per IS 456 + SLS
crack width limited to 0.2 mm (general faces) / 0.1 mm (faces in contact with
liquid or the airspace above it). Min M30, max w/c 0.45, cover >= 45 mm.

Units: kN, m, kN/m2 for loads/geometry; N, mm, MPa in section checks.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from .. import tables
from .. import serviceability as svc

GAMMA_W = tables.UNIT_WEIGHTS["water"]  # 9.81 kN/m3


# ---------------------------------------------------------------------------
# Circular tanks — IS 3370-4 coefficient method
# ---------------------------------------------------------------------------

@dataclass
class CircularTankForces:
    H2_Dt: float
    hoop_max_kN_per_m: float        # service, per metre height of wall
    moment_kNm_per_m: float          # service vertical wall moment
    base: str
    notes: list = field(default_factory=list)


def circular_tank_forces(H: float, D: float, t: float,
                         base: str = "hinged") -> CircularTankForces:
    """Service hoop tension and wall moment per IS 3370-4 tables.

    H = water depth (m), D = internal diameter (m), t = wall thickness (m).
    Hoop T = coeff * gamma_w * H * D/2 (kN/m); M = coeff * gamma_w * H^3 (kNm/m).
    """
    c = tables.circular_tank_coefficients(H, D, t, base)
    T = c["hoop_max"] * GAMMA_W * H * D / 2.0
    m_key = "moment_base" if "moment_base" in c else "moment_max"
    M = c[m_key] * GAMMA_W * H ** 3
    return CircularTankForces(c["H2_Dt"], T, M, base,
                              [f"IS 3370-4 coefficients at H2/Dt={c['H2_Dt']:.2f}",
                               tables.CODE_EDITIONS["IS3370-4"]])


# ---------------------------------------------------------------------------
# Rectangular tanks — moment coefficients / cantilever method
# ---------------------------------------------------------------------------

def rectangular_wall_forces(H: float, L: float, B: float) -> dict:
    """Service force estimates for rectangular tank walls (full tank).

    Long walls (L/H >= 2): design as vertical cantilevers,
      M_base = gamma_w H^3 / 6 (per m), direct tension from short-wall reaction
      T_long = gamma_w (H - h') B / 2 with h' = min(H/4, 1 m).
    Short walls (B/H < 2): horizontal spanning between long walls,
      M_horz = gamma_w (H - h') L_span^2 / 12 at corners (fixed-edge), plus a
      bottom cantilever; direct tension T_short = gamma_w (H - h') L / 2 ... .
    This is the classical IS 3370-4-style approximation; for panel-accurate
    coefficients transcribe Part 4 Table 3 (flagged for BIS verification).
    """
    hp = min(H / 4.0, 1.0)
    p = GAMMA_W * (H - hp)  # design pressure intensity for horizontal strips
    out = {"h_prime": hp, "pressure_at_hprime": p}
    if L / H >= 2.0:
        out["long_wall"] = {"mode": "vertical cantilever",
                            "M_base_kNm_per_m": GAMMA_W * H ** 3 / 6.0,
                            "T_direct_kN_per_m": p * B / 2.0}
    else:
        out["long_wall"] = {"mode": "horizontal spanning",
                            "M_corner_kNm_per_m": p * L ** 2 / 12.0,
                            "M_mid_kNm_per_m": p * L ** 2 / 16.0,
                            "T_direct_kN_per_m": p * B / 2.0}
    if B / H >= 2.0:
        out["short_wall"] = {"mode": "vertical cantilever",
                             "M_base_kNm_per_m": GAMMA_W * H ** 3 / 6.0,
                             "T_direct_kN_per_m": p * L / 2.0}
    else:
        out["short_wall"] = {"mode": "horizontal spanning",
                             "M_corner_kNm_per_m": p * B ** 2 / 12.0,
                             "M_mid_kNm_per_m": p * B ** 2 / 16.0,
                             "T_direct_kN_per_m": p * L / 2.0}
    out["cantilever_bottom_moment"] = GAMMA_W * hp * H ** 2 / 6.0
    return out


# ---------------------------------------------------------------------------
# Underground sump load cases
# ---------------------------------------------------------------------------

def sump_wall_pressures(H: float, gamma_soil: float = 18.0, phi_deg: float = 30.0,
                        surcharge: float = 10.0, water_table_depth: float = 0.0,
                        gamma_sat: float = 20.0) -> dict:
    """Two governing cases for an underground sump wall (per m run).

    Case A — sump FULL, no backfill (test condition): inside water pushes out.
    Case B — sump EMPTY, backfill + groundwater push in.
    K0 = 1 - sin(phi) (at-rest, rigid walls). Depths from ground level; wall
    height H. water_table_depth: depth of WT below ground (0 = at surface).
    """
    k0 = 1 - math.sin(math.radians(phi_deg))
    # Case A: triangular water pressure from inside
    caseA = {"pressure_base": GAMMA_W * H, "M_cantilever_base": GAMMA_W * H ** 3 / 6.0}
    # Case B: earth (moist above WT, submerged below) + hydrostatic below WT
    zw = min(max(water_table_depth, 0.0), H)
    p_earth_top = k0 * surcharge
    p_earth_wt = p_earth_top + k0 * gamma_soil * zw
    p_earth_base = p_earth_wt + k0 * (gamma_sat - GAMMA_W) * (H - zw)
    p_water_base = GAMMA_W * (H - zw)
    p_base_total = p_earth_base + p_water_base
    # cantilever base moment by numeric integration of the pressure diagram
    n = 200
    Mnum = 0.0
    for i in range(n):
        z = (i + 0.5) * H / n
        if z <= zw:
            p = k0 * (surcharge + gamma_soil * z)
        else:
            p = (k0 * (surcharge + gamma_soil * zw
                       + (gamma_sat - GAMMA_W) * (z - zw))
                 + GAMMA_W * (z - zw))
        Mnum += p * (H - z) * (H / n)  # moment about base of strip at depth z
    # (moment arm measured from base: strip at depth z acts at height H - z)
    caseB = {"K0": k0, "pressure_base_total": p_base_total,
             "M_cantilever_base": Mnum}
    return {"caseA_full_no_backfill": caseA, "caseB_empty_backfilled": caseB,
            "governing_moment": max(caseA["M_cantilever_base"],
                                    caseB["M_cantilever_base"])}


def uplift_check(plan_area: float, structure_weight_kN: float,
                 water_table_above_base: float) -> dict:
    """Flotation check, tank empty. FOS = W / U >= 1.2 (IS 3370 practice)."""
    U = GAMMA_W * water_table_above_base * plan_area
    fos = structure_weight_kN / U if U > 0 else float("inf")
    return {"uplift_kN": U, "weight_kN": structure_weight_kN,
            "FOS": fos, "ok": fos >= tables.UPLIFT_FOS,
            "required_FOS": tables.UPLIFT_FOS}


# ---------------------------------------------------------------------------
# Section design under M (+T) with crack-width governance
# ---------------------------------------------------------------------------

def design_tank_wall_section(M_service_kNm: float, T_service_kN: float,
                             t_mm: float, fck: float, fy: float,
                             bar_dia: float, spacing_mm: float,
                             liquid_face: bool = True,
                             cover_mm: float = 45.0) -> dict:
    """Check a 1 m strip of tank wall for SLS crack width + ULS strength.

    Steel per metre from bar_dia @ spacing on the tension face. Direct tension
    T is carried entirely by steel (concrete tension ignored at ULS).
    """
    b = 1000.0
    ast = math.pi * bar_dia ** 2 / 4 * (1000.0 / spacing_mm)
    d = t_mm - cover_mm - bar_dia / 2
    limit = (tables.CRACK_LIMIT_LIQUID_FACE if liquid_face
             else tables.CRACK_LIMIT_OTHER)

    checks, data = [], {"Ast_mm2_per_m": ast, "d_mm": d, "crack_limit_mm": limit}

    # material minima (IS 3370-1/2:2021)
    checks.append(("fck >= M30 (IS 3370)", fck >= tables.TANK_MIN_FCK))
    checks.append(("cover >= 45 mm liquid face", cover_mm >= tables.TANK_MIN_COVER
                   or not liquid_face))

    # min steel: surface zone each face (t/2 per face, capped 250 mm)
    zone = min(t_mm / 2.0, 250.0) * 1000.0  # mm2 of surface-zone concrete per m
    ast_min = tables.MIN_STEEL_SURFACE_ZONE_HYSD * zone
    data["Ast_min_mm2_per_m"] = ast_min
    checks.append(("min steel 0.35% surface zone (IS 3370-2 A-1)", ast >= ast_min))

    # ULS strength (gamma_f = 1.5)
    Mu = 1.5 * M_service_kNm * 1e6
    Tu = 1.5 * T_service_kN * 1e3
    ast_T = Tu / (0.87 * fy)
    ast_flex_avail = max(ast - ast_T, 1.0)
    # required flexural steel (Annex G-1.1b)
    R = 4.6 * Mu / (fck * b * d * d)
    if R < 1.0:
        ast_flex_req = 0.5 * fck / fy * (1 - math.sqrt(1 - R)) * b * d
        checks.append(("ULS flexure + tension steel adequate",
                       ast_flex_avail >= ast_flex_req))
        data["Ast_flex_required_mm2"] = ast_flex_req
    else:
        checks.append(("section depth adequate for ULS flexure", False))

    # SLS crack width (service moment)
    cw = svc.crack_width_flexure(b, t_mm, d, ast, fck,
                                 M_service_kNm * 1e6, cover_mm,
                                 bar_dia, spacing_mm)
    data["crack_width_mm"] = cw.get("w_cr")
    data["steel_stress_service_MPa"] = cw.get("fs")
    checks.append((f"crack width <= {limit} mm (IS 3370-2:2021)",
                   cw.get("w_cr", 99) <= limit))

    # deemed-to-satisfy alternative: service steel stress
    fs_limit = (tables.STEEL_STRESS_FLEXURE_LIQUID if liquid_face else 0.58 * fy)
    data["fs_deemed_limit_MPa"] = fs_limit
    data["fs_deemed_ok"] = cw.get("fs", 999) <= fs_limit

    return {"ok": all(ok for _, ok in checks), "checks": checks, "data": data}
