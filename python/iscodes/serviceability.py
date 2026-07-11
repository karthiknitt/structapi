"""Serviceability: deflection control (IS 456 cl 23.2.1) and crack width
(IS 456 Annex F, referenced by IS 3370-2:2021 for liquid-retaining work).

Units: N, mm, MPa.
"""

from __future__ import annotations

import math

from .materials import Concrete, Steel

BASIC_L_BY_D = {"cantilever": 7.0, "simply_supported": 20.0, "continuous": 26.0}


def kt_tension(fs: float, pt: float) -> float:
    """Modification factor for tension reinforcement, IS 456 Fig 4 curve fit.

    fs = 0.58 fy (Ast_reqd / Ast_prov), pt = 100 Ast/(b d).
    """
    pt = max(pt, 0.05)
    # published fit of Fig 4: kt = 1/(0.225 + 0.00322 fs - 0.625 log10(bd/100Ast))
    # and bd/(100 Ast) = 1/pt, so the pt term enters with a POSITIVE log10(pt).
    kt = 1.0 / (0.225 + 0.00322 * fs + 0.625 * math.log10(pt))
    return min(max(kt, 0.4), 2.0)


def kc_compression(pc: float) -> float:
    """Modification factor for compression reinforcement, Fig 5 fit."""
    return min(1.0 + pc / (pc + 3.0), 1.5)


def kf_flanged(bw_by_bf: float) -> float:
    """Reduction factor for flanged sections, Fig 6 (linear fit)."""
    if bw_by_bf >= 1.0:
        return 1.0
    return max(0.8, 0.8 + 0.2 * (bw_by_bf - 0.3) / 0.7)


def allowable_span_by_depth(support: str, fy: float, pt: float,
                            ast_reqd_by_prov: float = 1.0, pc: float = 0.0,
                            bw_by_bf: float = 1.0, span_m: float | None = None) -> float:
    """Permissible L/d per cl 23.2.1 with Figs 4-6 modifications."""
    base = BASIC_L_BY_D[support]
    fs = 0.58 * fy * ast_reqd_by_prov
    ratio = base * kt_tension(fs, pt) * kc_compression(pc) * kf_flanged(bw_by_bf)
    if span_m and span_m > 10 and support != "cantilever":
        ratio *= 10.0 / span_m
    return ratio


def check_deflection(span_mm: float, d_mm: float, support: str, fy: float,
                     pt: float, ast_reqd_by_prov: float = 1.0, pc: float = 0.0,
                     bw_by_bf: float = 1.0) -> dict:
    allow = allowable_span_by_depth(support, fy, pt, ast_reqd_by_prov, pc,
                                    bw_by_bf, span_mm / 1000.0)
    actual = span_mm / d_mm
    return {"actual_L_by_d": actual, "allowable_L_by_d": allow,
            "ok": actual <= allow}


# ---------------------------------------------------------------------------
# Crack width — IS 456 Annex F (used with IS 3370-2:2021 limits)
# ---------------------------------------------------------------------------

def cracked_section_na(b: float, d: float, Ast: float, fck: float,
                       Asc: float = 0.0, dc: float = 0.0) -> float:
    """Neutral axis depth x (mm) of a cracked transformed section (m = Es/Ec,
    long-term modular ratio taken as 280/(3 sigma_cbc) is the WSM convention;
    for Annex F service analysis use m = Es/Ec)."""
    m = 200000.0 / Concrete(fck).Ec
    # b x^2/2 + (m-1) Asc (x - dc) = m Ast (d - x)
    A = b / 2.0
    B = (m - 1) * Asc + m * Ast
    C = -((m - 1) * Asc * dc + m * Ast * d)
    return (-B + math.sqrt(B * B - 4 * A * C)) / (2 * A)


def steel_stress_service(M_service_Nmm: float, b: float, d: float, Ast: float,
                         fck: float) -> float:
    """Service steel stress from cracked-section analysis (MPa)."""
    x = cracked_section_na(b, d, Ast, fck)
    z = d - x / 3.0
    return M_service_Nmm / (Ast * z)


def crack_width_flexure(b: float, D: float, d: float, Ast: float, fck: float,
                        M_service_Nmm: float, cover_min: float,
                        bar_dia: float, bar_spacing: float) -> dict:
    """Flexural surface crack width per IS 456 Annex F.

    w_cr = 3 a_cr eps_m / (1 + 2 (a_cr - c_min)/(D - x))
    eps_m = eps_1 - relief term F-1: b(D-x)(a-x) / (3 Es As (d-x))
    """
    Es = 200000.0
    x = cracked_section_na(b, d, Ast, fck)
    fs = steel_stress_service(M_service_Nmm, b, d, Ast, fck)
    eps_s = fs / Es
    # strain at the surface (a = D, extreme tension fiber)
    eps_1 = eps_s * (D - x) / (d - x)
    relief = b * (D - x) * (D - x) / (3 * Es * Ast * (d - x))
    eps_m = eps_1 - relief
    # a_cr: distance from the point considered (surface midway between bars)
    # to the nearest bar surface
    a_cr = math.sqrt((bar_spacing / 2.0) ** 2 + (D - d) ** 2) - bar_dia / 2.0
    if eps_m <= 0:
        return {"x": x, "fs": fs, "eps_m": eps_m, "w_cr": 0.0, "note": "uncracked"}
    w = 3 * a_cr * eps_m / (1 + 2 * (a_cr - cover_min) / (D - x))
    return {"x": x, "fs": fs, "eps_1": eps_1, "eps_m": eps_m, "a_cr": a_cr, "w_cr": w}


def crack_width_direct_tension(T_service_N: float, Ac: float, Ast: float,
                               cover_min: float, bar_dia: float,
                               bar_spacing: float, D: float) -> dict:
    """Crack width under direct tension: w = 3 a_cr eps_m (fully cracked)."""
    Es = 200000.0
    fs = T_service_N / Ast
    eps_1 = fs / Es
    relief = 2.0 * Ac / (3.0 * Es * Ast * 2)  # Annex F-3 stiffening (approx, both faces)
    eps_m = max(eps_1 - relief * 1.0, eps_1 * 0.6)  # conservative floor
    a_cr = math.sqrt((bar_spacing / 2.0) ** 2 + (cover_min + bar_dia / 2) ** 2) \
        - bar_dia / 2.0
    return {"fs": fs, "eps_m": eps_m, "a_cr": a_cr, "w_cr": 3 * a_cr * eps_m}
