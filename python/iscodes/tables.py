"""Code tables — single source of truth for IS-code tabulated values.

Every constant cites its clause/table. Values transcribed per project research;
carry the package DISCLAIMER into any report that uses them.

Units: N, mm, MPa unless noted. Loads module uses kN, m, kN/m2.
"""

from __future__ import annotations

import math
from bisect import bisect_left

CODE_EDITIONS = {
    "IS456": "2000 (reaffirmed 2021)",
    "IS875-1": "1987 (reaffirmed 2018)",
    "IS875-2": "1987 (reaffirmed 2018)",
    "IS875-3": "2015",
    "IS1893-1": "2016",
    "IS13920": "2016",
    "IS3370-1": "2021",
    "IS3370-2": "2021",
    "IS3370-4": "1967 (reaffirmed 2021)",
    "IS10262": "2019",
    "IS6403": "1981 (reaffirmed 2016)",
    "SP16": "1980",
}


# ---------------------------------------------------------------------------
# IS 456:2000 — shear
# ---------------------------------------------------------------------------

def tau_c(pt: float, fck: float) -> float:
    """Design shear strength of concrete, MPa. IS 456 Table 19.

    Closed form per SP 24 commentary (matches Table 19 to ~0.01 MPa).
    pt = 100*Ast/(b*d), clamped to [0.15, 3.0].
    """
    pt = min(max(pt, 0.15), 3.0)
    beta = max(0.8 * fck / (6.89 * pt), 1.0)
    return 0.85 * math.sqrt(0.8 * fck) * (math.sqrt(1 + 5 * beta) - 1) / (6 * beta)


#: Maximum shear stress with reinforcement, MPa. IS 456 Table 20.
TAU_C_MAX = {15: 2.5, 20: 2.8, 25: 3.1, 30: 3.5, 35: 3.7, 40: 4.0}


def tau_c_max(fck: float) -> float:
    grades = sorted(TAU_C_MAX)
    for g in reversed(grades):
        if fck >= g:
            return TAU_C_MAX[g]
    return TAU_C_MAX[15]


def k_solid_slab(D_mm: float) -> float:
    """Shear enhancement factor k for solid slabs. IS 456 cl 40.2.1.1."""
    pts = [(150, 1.30), (175, 1.25), (200, 1.20), (225, 1.15),
           (250, 1.10), (275, 1.05), (300, 1.00)]
    if D_mm <= 150:
        return 1.30
    if D_mm >= 300:
        return 1.00
    for (d1, k1), (d2, k2) in zip(pts, pts[1:]):
        if d1 <= D_mm <= d2:
            return k1 + (k2 - k1) * (D_mm - d1) / (d2 - d1)
    return 1.00


# ---------------------------------------------------------------------------
# IS 456:2000 — flexure limits (cl 38.1) and bond (cl 26.2.1)
# ---------------------------------------------------------------------------

ES = 200_000.0  # MPa, cl 5.6.3


def xu_max_by_d(fy: float) -> float:
    """Limiting neutral-axis depth ratio. IS 456 cl 38.1 note."""
    return 0.0035 / (0.0055 + 0.87 * fy / ES)


def mu_lim_factor(fy: float) -> float:
    """Q such that Mu_lim = Q * fck * b * d^2 (cl 38.1 / Annex G)."""
    k = xu_max_by_d(fy)
    return 0.36 * k * (1 - 0.42 * k)


#: Design bond stress for plain bars in tension, MPa. IS 456 cl 26.2.1.1.
TAU_BD_PLAIN = {20: 1.2, 25: 1.4, 30: 1.5, 35: 1.7, 40: 1.9}


def tau_bd(fck: float, deformed: bool = True, compression: bool = False) -> float:
    grades = sorted(TAU_BD_PLAIN)
    val = TAU_BD_PLAIN[grades[0]]
    for g in grades:
        if fck >= g:
            val = TAU_BD_PLAIN[g]
    if deformed:
        val *= 1.6   # cl 26.2.1.1 note
    if compression:
        val *= 1.25  # cl 26.2.1.1
    return val


def development_length(phi: float, fy: float, fck: float,
                       deformed: bool = True, compression: bool = False) -> float:
    """Ld in mm. IS 456 cl 26.2.1."""
    return phi * 0.87 * fy / (4 * tau_bd(fck, deformed, compression))


# ---------------------------------------------------------------------------
# SP 16 Table F — stress in compression steel fsc (MPa) at xu = xu_max
# keyed by fy, then d'/d
# ---------------------------------------------------------------------------

FSC_SP16 = {
    250: {0.05: 217, 0.10: 217, 0.15: 217, 0.20: 217},
    415: {0.05: 355, 0.10: 353, 0.15: 342, 0.20: 329},
    500: {0.05: 412, 0.10: 412, 0.15: 395, 0.20: 370},
}


def fsc(fy: float, dc_by_d: float) -> float:
    """Compression steel design stress, interpolated from SP 16 Table F."""
    table = FSC_SP16.get(int(fy))
    if table is None:  # generic: strain compatibility with bilinear ~ conservative
        table = FSC_SP16[415 if fy < 460 else 500]
    keys = sorted(table)
    r = min(max(dc_by_d, keys[0]), keys[-1])
    i = min(bisect_left(keys, r), len(keys) - 1)
    if keys[i] == r or i == 0:
        return float(table[keys[i]])
    k1, k2 = keys[i - 1], keys[i]
    return table[k1] + (table[k2] - table[k1]) * (r - k1) / (k2 - k1)


# ---------------------------------------------------------------------------
# IS 456:2000 Table 18 — load combinations (partial safety factors, ULS + SLS)
# Each combo: dict of factors for DL, IL (imposed), WL (wind or earthquake)
# ---------------------------------------------------------------------------

ULS_COMBOS = [
    {"name": "1.5(DL+IL)",       "DL": 1.5, "IL": 1.5, "WL": 0.0},
    {"name": "1.2(DL+IL+WL)",    "DL": 1.2, "IL": 1.2, "WL": 1.2},
    {"name": "1.2(DL+IL-WL)",    "DL": 1.2, "IL": 1.2, "WL": -1.2},
    {"name": "1.5(DL+WL)",       "DL": 1.5, "IL": 0.0, "WL": 1.5},
    {"name": "1.5(DL-WL)",       "DL": 1.5, "IL": 0.0, "WL": -1.5},
    {"name": "0.9DL+1.5WL",      "DL": 0.9, "IL": 0.0, "WL": 1.5},
    {"name": "0.9DL-1.5WL",      "DL": 0.9, "IL": 0.0, "WL": -1.5},
]

SLS_COMBOS = [
    {"name": "DL+IL",            "DL": 1.0, "IL": 1.0, "WL": 0.0},
    {"name": "DL+0.8IL+0.8WL",   "DL": 1.0, "IL": 0.8, "WL": 0.8},
    {"name": "DL+0.8IL-0.8WL",   "DL": 1.0, "IL": 0.8, "WL": -0.8},
    {"name": "DL+WL",            "DL": 1.0, "IL": 0.0, "WL": 1.0},
    {"name": "DL-WL",            "DL": 1.0, "IL": 0.0, "WL": -1.0},
]


# ---------------------------------------------------------------------------
# IS 456:2000 Table 5 — durability requirements for RC (by exposure)
# (min fck MPa, max free w/c, min cement kg/m3, nominal cover mm per Table 16)
# ---------------------------------------------------------------------------

EXPOSURE = {
    "mild":        {"min_fck": 20, "max_wc": 0.55, "min_cement": 300, "cover": 20},
    "moderate":    {"min_fck": 25, "max_wc": 0.50, "min_cement": 300, "cover": 30},
    "severe":      {"min_fck": 30, "max_wc": 0.45, "min_cement": 320, "cover": 45},
    "very severe": {"min_fck": 35, "max_wc": 0.45, "min_cement": 340, "cover": 50},
    "extreme":     {"min_fck": 40, "max_wc": 0.40, "min_cement": 360, "cover": 75},
}

MAX_CEMENT = 450.0  # kg/m3, IS 456 cl 8.2.4.2


# ---------------------------------------------------------------------------
# IS 456:2000 Table 12 / 13 — continuous beam/slab moment & shear coefficients
# (cl 22.5.1-22.5.2; valid for >=3 spans differing <15%, UDL)
# M = coeff * w * L^2 ; V = coeff * w * L
# ---------------------------------------------------------------------------

TABLE_12_MOMENT = {
    # span moments (sagging, +)
    "span_end_DL": 1 / 12, "span_end_IL": 1 / 10,
    "span_interior_DL": 1 / 16, "span_interior_IL": 1 / 12,
    # support moments (hogging, -)
    "support_next_to_end_DL": -1 / 10, "support_next_to_end_IL": -1 / 9,
    "support_interior_DL": -1 / 12, "support_interior_IL": -1 / 9,
}

TABLE_13_SHEAR = {
    "end_support_DL": 0.4, "end_support_IL": 0.45,
    "support_next_to_end_outer_DL": 0.6, "support_next_to_end_outer_IL": 0.6,
    "support_next_to_end_inner_DL": 0.55, "support_next_to_end_inner_IL": 0.6,
    "support_interior_DL": 0.5, "support_interior_IL": 0.6,
}


# ---------------------------------------------------------------------------
# IS 456:2000 Table 26 — two-way restrained slab BM coefficients (Annex D-1)
# M = alpha * w * lx^2. Cases 1-9; per case: {'nx': [-alpha_x at cont. edge],
# 'px': [+alpha_x midspan], 'ny': -alpha_y, 'py': +alpha_y} at LY_BY_LX points.
# None = edge not continuous (no negative moment coefficient).
# ---------------------------------------------------------------------------

LY_BY_LX = [1.0, 1.1, 1.2, 1.3, 1.4, 1.5, 1.75, 2.0]

TABLE_26 = {
    1: {"desc": "Interior panels (four edges continuous)",
        "nx": [0.032, 0.037, 0.043, 0.047, 0.051, 0.053, 0.060, 0.065],
        "px": [0.024, 0.028, 0.032, 0.036, 0.039, 0.041, 0.045, 0.049],
        "ny": 0.032, "py": 0.024},
    2: {"desc": "One short edge discontinuous",
        "nx": [0.037, 0.043, 0.048, 0.051, 0.055, 0.057, 0.064, 0.068],
        "px": [0.028, 0.032, 0.036, 0.039, 0.041, 0.044, 0.048, 0.052],
        "ny": 0.037, "py": 0.028},
    3: {"desc": "One long edge discontinuous",
        "nx": [0.037, 0.044, 0.052, 0.057, 0.063, 0.067, 0.077, 0.085],
        "px": [0.028, 0.033, 0.039, 0.044, 0.047, 0.051, 0.059, 0.065],
        "ny": 0.037, "py": 0.028},
    4: {"desc": "Two adjacent edges discontinuous",
        "nx": [0.047, 0.053, 0.060, 0.065, 0.071, 0.075, 0.084, 0.091],
        "px": [0.035, 0.040, 0.045, 0.049, 0.053, 0.056, 0.063, 0.069],
        "ny": 0.047, "py": 0.035},
    5: {"desc": "Two short edges discontinuous",
        "nx": [0.045, 0.049, 0.052, 0.056, 0.059, 0.060, 0.065, 0.069],
        "px": [0.035, 0.037, 0.040, 0.043, 0.044, 0.045, 0.049, 0.052],
        "ny": None, "py": 0.035},
    6: {"desc": "Two long edges discontinuous",
        "nx": None,
        "px": [0.035, 0.043, 0.051, 0.057, 0.063, 0.068, 0.080, 0.088],
        "ny": 0.045, "py": 0.035},
    7: {"desc": "Three edges discontinuous (one long edge continuous)",
        "nx": [0.057, 0.064, 0.071, 0.076, 0.080, 0.084, 0.091, 0.097],
        "px": [0.043, 0.048, 0.053, 0.057, 0.060, 0.064, 0.069, 0.073],
        "ny": None, "py": 0.043},
    8: {"desc": "Three edges discontinuous (one short edge continuous)",
        "nx": None,
        "px": [0.043, 0.051, 0.059, 0.065, 0.071, 0.076, 0.087, 0.096],
        "ny": 0.057, "py": 0.043},
    9: {"desc": "Four edges discontinuous",
        "nx": None,
        "px": [0.056, 0.064, 0.072, 0.079, 0.085, 0.089, 0.100, 0.107],
        "ny": None, "py": 0.056},
}


def _interp(xs, ys, x):
    if x <= xs[0]:
        return ys[0]
    if x >= xs[-1]:
        return ys[-1]
    i = bisect_left(xs, x)
    x1, x2, y1, y2 = xs[i - 1], xs[i], ys[i - 1], ys[i]
    return y1 + (y2 - y1) * (x - x1) / (x2 - x1)


def slab_coefficients(case: int, ly_by_lx: float) -> dict:
    """Interpolated Table 26 coefficients for a restrained two-way slab."""
    row = TABLE_26[case]
    out = {"desc": row["desc"], "ny": row["ny"], "py": row["py"]}
    for key in ("nx", "px"):
        out[key] = None if row[key] is None else _interp(LY_BY_LX, row[key], ly_by_lx)
    return out


# Annex D-2 (simply supported, corners not held down): alpha_x, alpha_y
D2_LY_BY_LX = [1.0, 1.1, 1.2, 1.3, 1.4, 1.5, 1.75, 2.0, 2.5, 3.0]
D2_ALPHA_X = [0.062, 0.074, 0.084, 0.093, 0.099, 0.104, 0.113, 0.118, 0.122, 0.124]
D2_ALPHA_Y = [0.062, 0.061, 0.059, 0.055, 0.051, 0.046, 0.037, 0.029, 0.020, 0.014]


def slab_ss_coefficients(ly_by_lx: float) -> dict:
    return {"ax": _interp(D2_LY_BY_LX, D2_ALPHA_X, ly_by_lx),
            "ay": _interp(D2_LY_BY_LX, D2_ALPHA_Y, ly_by_lx)}


# ---------------------------------------------------------------------------
# IS 875 Part 1 — unit weights (kN/m3 unless noted)
# ---------------------------------------------------------------------------

UNIT_WEIGHTS = {
    "rcc": 25.0, "pcc": 24.0, "steel": 78.5,
    "brick_masonry": 20.0, "stone_masonry": 24.0,
    "water": 9.81, "soil_dry": 18.0, "soil_saturated": 20.0,
    "screed": 24.0, "aac_block": 8.0, "glass": 25.0,
    "floor_finish_kn_m2": 1.5, "plaster_12mm_kn_m2": 0.24,
}


# ---------------------------------------------------------------------------
# IS 875 Part 2 — imposed loads (kN/m2)
# ---------------------------------------------------------------------------

IMPOSED_LOADS = {
    "residential_room": 2.0, "residential_corridor": 3.0,
    "office": 2.5, "office_storage": 5.0, "office_corridor": 4.0,
    "classroom": 3.0, "retail": 4.0,
    "assembly_fixed_seating": 4.0, "assembly_movable_seating": 5.0,
    "parking_car": 2.5,
    "roof_accessible": 1.5, "roof_non_accessible": 0.75,
    "partition_allowance_min": 1.0,
}

#: Column live-load reduction (%), IS 875-2 cl 3.2: floors carried -> reduction
LL_REDUCTION = {1: 0, 2: 10, 3: 20, 4: 30, 5: 40, 6: 40, 7: 40, 8: 40, 9: 40, 10: 40}


def ll_reduction_pct(floors_carried: int) -> float:
    if floors_carried > 10:
        return 50.0
    return float(LL_REDUCTION.get(max(floors_carried, 1), 0))


# ---------------------------------------------------------------------------
# IS 875 Part 3:2015 — wind
# ---------------------------------------------------------------------------

#: Basic wind speed Vb (m/s) for common cities (Fig 1 / Annex A)
BASIC_WIND_SPEED = {
    "chennai": 50, "delhi": 47, "mumbai": 44, "kolkata": 50,
    "bangalore": 33, "bengaluru": 33, "hyderabad": 44, "pune": 39,
    "ahmedabad": 39, "bhubaneswar": 50, "guwahati": 50, "kochi": 39,
    "coimbatore": 39, "jaipur": 47, "lucknow": 47, "chandigarh": 47,
}

#: k2 — terrain/height factor, Table 2. heights (m) x terrain category 1-4
K2_HEIGHTS = [10, 15, 20, 30, 50, 100, 150, 200, 250, 300, 350, 400, 450, 500]
K2_TABLE = {
    1: [1.05, 1.09, 1.12, 1.15, 1.20, 1.26, 1.30, 1.32, 1.34, 1.35, 1.37, 1.38, 1.39, 1.40],
    2: [1.00, 1.05, 1.07, 1.12, 1.17, 1.24, 1.28, 1.30, 1.32, 1.34, 1.36, 1.37, 1.38, 1.39],
    3: [0.91, 0.97, 1.01, 1.06, 1.12, 1.20, 1.24, 1.27, 1.29, 1.31, 1.32, 1.34, 1.35, 1.36],
    4: [0.80, 0.80, 0.80, 0.97, 1.10, 1.20, 1.24, 1.27, 1.28, 1.30, 1.31, 1.32, 1.33, 1.34],
}


def k2(height_m: float, terrain_category: int) -> float:
    return _interp(K2_HEIGHTS, K2_TABLE[terrain_category], max(height_m, 10.0))


# ---------------------------------------------------------------------------
# IS 1893 Part 1:2016 — seismic
# ---------------------------------------------------------------------------

ZONE_FACTOR = {"II": 0.10, "III": 0.16, "IV": 0.24, "V": 0.36}  # Table 3

IMPORTANCE = {"ordinary": 1.0, "residential_large": 1.2, "important": 1.5}  # Table 8

RESPONSE_REDUCTION = {"OMRF": 3.0, "SMRF": 5.0,
                      "ordinary_shear_wall": 3.0, "ductile_shear_wall": 4.0,
                      "ductile_shear_wall_SMRF": 5.0}  # Table 9

#: Minimum design base-shear coefficient rho (%), cl 7.2.2
MIN_BASE_SHEAR_PCT = {"II": 0.7, "III": 1.1, "IV": 1.6, "V": 2.4}


def sa_by_g(T: float, soil: str = "medium") -> float:
    """Design spectral acceleration coefficient, 5% damping. IS 1893 cl 6.4.2."""
    s = soil.lower()
    if T < 0:
        raise ValueError("period must be >= 0")
    if T <= 0.10:
        return 1 + 15 * T
    if s in ("rock", "hard", "i", "type i"):
        return 2.5 if T <= 0.40 else min(2.5, max(1.36 / T, 0.34 if T > 4 else 1.36 / T))
    if s in ("medium", "ii", "type ii"):
        return 2.5 if T <= 0.55 else 1.36 / T if T <= 4.0 else 1.36 / 4
    if s in ("soft", "iii", "type iii"):
        return 2.5 if T <= 0.67 else 1.67 / T if T <= 4.0 else 1.67 / 4
    raise ValueError(f"unknown soil type: {soil}")


#: Fraction of imposed load in seismic weight, Table 10
def seismic_ll_fraction(il_kn_m2: float) -> float:
    return 0.25 if il_kn_m2 <= 3.0 else 0.5


# ---------------------------------------------------------------------------
# IS 3370 Part 4:1967 — circular tank coefficients
# Hoop tension T = coeff * gamma_w * H * R ; wall base moment M = coeff * gamma_w * H^3
# keyed by H^2/(D*t). Values from IS 3370-4 Tables (fixed base: T1/T2; hinged: T5/T6).
# Subset of standard design points; interpolate between.
# ---------------------------------------------------------------------------

H2_DT = [0.4, 0.8, 1.2, 1.6, 2.0, 3.0, 4.0, 5.0, 6.0, 8.0, 10.0, 12.0, 14.0, 16.0]

#: max hoop tension coefficient over wall height — FIXED base (Table 1)
HOOP_MAX_FIXED = [0.149, 0.263, 0.283, 0.265, 0.234, 0.134, 0.067, 0.025,
                  0.018, 0.011, 0.008, 0.011, 0.015, 0.008]
# NOTE: above small-H2/Dt trend from Table 1 columns at 0.0-0.5H; for design use
# HOOP_MAX_FIXED_ENVELOPE below (max over depth), which is the practical set.
HOOP_MAX_FIXED_ENVELOPE = [0.149, 0.263, 0.283, 0.285, 0.287, 0.322, 0.362, 0.404,
                           0.436, 0.499, 0.552, 0.592, 0.628, 0.660]

#: max hoop tension coefficient — HINGED base (Table 5)
HOOP_MAX_HINGED = [0.44, 0.473, 0.512, 0.543, 0.564, 0.607, 0.643, 0.665,
                   0.687, 0.721, 0.746, 0.764, 0.776, 0.786]

#: wall base moment coefficient — FIXED base (Table 2), M = coeff * gamma * H^3
MOM_BASE_FIXED = [0.0765, 0.0465, 0.0325, 0.0250, 0.0205, 0.0142, 0.0110, 0.0090,
                  0.0077, 0.0059, 0.0048, 0.0041, 0.0036, 0.0032]

#: max vertical moment coefficient — HINGED base (Table 6, +ve at ~0.6-0.7H)
MOM_MAX_HINGED = [0.0245, 0.0172, 0.0138, 0.0118, 0.0105, 0.0084, 0.0071, 0.0061,
                  0.0055, 0.0045, 0.0039, 0.0035, 0.0032, 0.0029]


def circular_tank_coefficients(H: float, D: float, t: float, base: str = "hinged") -> dict:
    """Interpolated IS 3370-4 coefficients. H, D, t in consistent units (m)."""
    x = H * H / (D * t)
    x = min(max(x, H2_DT[0]), H2_DT[-1])
    if base.lower().startswith("fix"):
        return {"H2_Dt": x,
                "hoop_max": _interp(H2_DT, HOOP_MAX_FIXED_ENVELOPE, x),
                "moment_base": _interp(H2_DT, MOM_BASE_FIXED, x)}
    return {"H2_Dt": x,
            "hoop_max": _interp(H2_DT, HOOP_MAX_HINGED, x),
            "moment_max": _interp(H2_DT, MOM_MAX_HINGED, x)}


# ---------------------------------------------------------------------------
# IS 3370-2:2021 — crack width limits and steel-stress deemed-to-satisfy
# ---------------------------------------------------------------------------

CRACK_LIMIT_LIQUID_FACE = 0.1   # mm — faces in contact with liquid / airspace above
CRACK_LIMIT_OTHER = 0.2         # mm — faces not in contact with liquid

#: Deemed-to-satisfy service steel stress (MPa) near liquid face, HYSD bars
STEEL_STRESS_FLEXURE_LIQUID = 130.0
STEEL_STRESS_DIRECT_TENSION_LIQUID = 100.0

MIN_STEEL_SURFACE_ZONE_HYSD = 0.0035  # 0.35% of surface zone each face, each dirn
MIN_STEEL_SURFACE_ZONE_MILD = 0.0064

TANK_MIN_FCK = 30.0     # M30 min for liquid-retaining RC
TANK_MAX_WC = 0.45
TANK_MIN_COVER = 45.0   # mm, liquid face
UPLIFT_FOS = 1.2        # flotation factor of safety, tank empty + high water table


# ---------------------------------------------------------------------------
# IS 10262:2019 — mix design tables
# ---------------------------------------------------------------------------

#: Table 2 — assumed standard deviation S (MPa) by grade
def mix_std_deviation(fck: float) -> float:
    if fck <= 15:
        return 3.5
    if fck <= 25:
        return 4.0
    return 5.0


#: Table 1 — X factor (MPa) for target strength = max(fck+1.65S, fck+X)
def mix_x_factor(fck: float) -> float:
    if fck <= 15:
        return 5.0
    if fck <= 45:
        return 5.5
    return 6.5


#: Table 3 — approx entrapped air (%) by nominal max aggregate size (mm)
AIR_CONTENT = {10: 1.5, 20: 1.0, 40: 0.8}

#: Table 4 — water content (kg/m3) for 25-50 mm slump, angular aggregate
WATER_CONTENT = {10: 208, 20: 186, 40: 165}

#: Water adjustment per aggregate shape (kg)
WATER_ADJ_SHAPE = {"angular": 0, "sub_angular": -10, "gravel": -20, "rounded": -25}

#: Table 5 — volume of coarse aggregate per unit volume of total aggregate,
#: at w/c = 0.50, by nominal max size and fine-aggregate zone
CA_VOLUME = {
    10: {"I": 0.44, "II": 0.46, "III": 0.48, "IV": 0.50},
    20: {"I": 0.60, "II": 0.62, "III": 0.64, "IV": 0.66},
    40: {"I": 0.69, "II": 0.71, "III": 0.73, "IV": 0.75},
}


# ---------------------------------------------------------------------------
# IS 6403:1981 — bearing capacity factors (Vesic Ngamma)
# ---------------------------------------------------------------------------

def bearing_capacity_factors(phi_deg: float) -> dict:
    """Nc, Nq (Prandtl/Reissner), Ngamma (Vesic) per IS 6403."""
    phi = math.radians(phi_deg)
    if phi_deg == 0:
        return {"Nc": 5.14, "Nq": 1.0, "Ngamma": 0.0}
    nq = math.exp(math.pi * math.tan(phi)) * math.tan(math.pi / 4 + phi / 2) ** 2
    nc = (nq - 1) / math.tan(phi)
    ng = 2 * (nq + 1) * math.tan(phi)
    return {"Nc": nc, "Nq": nq, "Ngamma": ng}


# ---------------------------------------------------------------------------
# IS 13920:2016 — key ductile-detailing constants
# ---------------------------------------------------------------------------

DUCTILE = {
    "beam_min_b": 200.0,           # mm, cl 6.1.3
    "beam_max_pt": 0.025,          # cl 6.2.2
    "column_min_b_storeys": 300.0, # mm, columns supporting > 2 storeys
    "strong_column_factor": 1.4,   # sum Mc >= 1.4 sum Mb, cl 7.2.1
    "confine_spacing_max": 100.0,  # mm hoop spacing in lo, cl 8.1
    "confine_spacing_6db": 6.0,    # 6 x smallest long. bar dia
}
