"""End-to-end RC beam design per IS 456:2000 (+ IS 13920 overlay if seismic).

Orchestrates: load factoring -> analysis -> flexure -> bar selection ->
shear stirrups -> deflection -> detailing checks.

Units: kN, m for the public API; N, mm, MPa internally for section design.
"""

from __future__ import annotations

import math

from .. import rounding, tables, serviceability as svc
from ..analysis.beam import BeamCase, analyze
from . import flexure, shear

#: map analysis support type -> serviceability basic L/d key
_DEFLECTION_SUPPORT = {
    "ss": "simply_supported",
    "cantilever": "cantilever",
    "fixed": "continuous",
}


def design_beam(span_m: float, w_dl_kn_m: float, w_il_kn_m: float,
                b: float, D: float, fck: float, fy: float,
                support: str = "ss", point_loads=None,
                cover: float = 30, bar_dia: float = 20,
                stirrup_dia: float = 8, seismic: bool = False) -> dict:
    """Design a single-span rectangular RC beam.

    b, D, cover, bar_dia, stirrup_dia in mm; loads in kN/m and (P_kN, a_m).
    Returns a dict: inputs, analysis (x,V,M arrays), design summary,
    checks list [(name, ok)], and overall ok flag.
    """
    # ---- factored loads (1.5(DL+IL), cl combos gravity) -------------------
    w_u = 1.5 * (w_dl_kn_m + w_il_kn_m)
    pls_u = [(1.5 * P, a) for (P, a) in (point_loads or [])]

    case = BeamCase(span_m=span_m, supports=support,
                    udl_kn_m=w_u, point_loads=pls_u)
    res = analyze(case)
    M, V = res["M"], res["V"]

    Mu_pos = float(M.max())          # kN.m sagging
    Mu_neg = float(M.min())          # kN.m hogging
    Mu_max_kNm = max(abs(Mu_pos), abs(Mu_neg))
    Vu_max_kN = float(max(abs(V.max()), abs(V.min())))

    Mu = Mu_max_kNm * 1e6            # N.mm
    Vu = Vu_max_kN * 1e3            # N

    # ---- effective depth --------------------------------------------------
    d = D - cover - stirrup_dia - bar_dia / 2.0
    dc = cover + stirrup_dia + bar_dia / 2.0

    # ---- flexure ----------------------------------------------------------
    Mlim = flexure.mu_lim(b, d, fck, fy)
    doubly = Mu > Mlim
    if doubly:
        dd = flexure.design_doubly(Mu, b, d, dc, fck, fy)
        Ast_reqd = dd["Ast"]
        Asc_reqd = dd["Asc"]
    else:
        Ast_reqd = flexure.ast_singly(Mu, b, d, fck, fy, raise_on_over=False)
        Asc_reqd = 0.0

    Ast_min = flexure.min_steel(b, d, fy)
    if seismic:
        Ast_min_ductile = max(0.85 / fy, 0.24 * math.sqrt(fck) / fy) * b * d
        Ast_min = max(Ast_min, Ast_min_ductile)
    Ast_max = flexure.max_steel(b, D)
    Ast_reqd = max(Ast_reqd, Ast_min)

    # ---- bar selection (tension) -----------------------------------------
    area_bar = math.pi * bar_dia ** 2 / 4.0
    n_bars = max(2, math.ceil(Ast_reqd / area_bar))
    Ast_prov = n_bars * area_bar

    n_bars_c = 0
    Asc_prov = 0.0
    if Asc_reqd > 0:
        n_bars_c = max(2, math.ceil(Asc_reqd / area_bar))
        Asc_prov = n_bars_c * area_bar

    pt = 100.0 * Ast_prov / (b * d)

    # ---- shear ------------------------------------------------------------
    stirrups = shear.design_stirrups(Vu, b, d, fck, fy, Ast_prov,
                                     stirrup_dia=stirrup_dia)

    # ---- ductile two-zone stirrup schedule (IS 13920:2016 cl 6.3) ---------
    # Applies alongside (never instead of) the IS 456 shear design above: the
    # ductile caps can only tighten the pitch, never relax it.
    ductile_stirrups = None
    if seismic:
        # Smallest longitudinal bar diameter. design_beam() carries a single
        # bar_dia for both tension and compression steel, so dia_min == bar_dia.
        dia_min = bar_dia
        # cl 6.3.5: over a length 2d from each support face the hoop spacing
        # shall not exceed d/4 nor 8*dia_min -- but "need not be less than
        # 100 mm" (constructability floor, retained from IS 13920:1993).
        s_conf_limit = max(min(d / 4.0, 8.0 * dia_min), 100.0)
        s_span_limit = d / 2.0          # cl 6.3.5, elsewhere along the span
        s_conf = rounding.site_spacing(s_conf_limit)
        s_span = rounding.site_spacing(s_span_limit)
        sv_shear = stirrups["sv_provided"]
        if sv_shear > 0:                # shear-governed pitch may govern
            s_conf = min(s_conf, sv_shear)
            s_span = min(s_span, sv_shear)
        ductile_stirrups = {
            "confining_zone_length_mm": 2.0 * d,
            "confining_zone_spacing_limit_mm": s_conf_limit,
            "confining_zone_spacing_mm": s_conf,
            "first_stirrup_offset_mm": 50.0,
            "span_zone_spacing_limit_mm": s_span_limit,
            "span_zone_spacing_mm": s_span,
            "hook": "135 deg bend, extend 10*dia beyond bend, closed hoop",
        }

    # ---- deflection -------------------------------------------------------
    defl = svc.check_deflection(span_m * 1000.0, d,
                                _DEFLECTION_SUPPORT.get(support, "simply_supported"),
                                fy, pt,
                                ast_reqd_by_prov=min(Ast_reqd / Ast_prov, 1.0),
                                pc=100.0 * Asc_prov / (b * d))

    # ---- checks -----------------------------------------------------------
    Mu_capacity = (flexure.mu_capacity(Ast_prov, b, d, fck, fy)
                   + (Asc_prov * (tables.fsc(fy, dc / d) - 0.446 * fck)
                      * (d - dc) if doubly else 0.0))
    checks = []
    checks.append(("flexure Ast >= Ast_min (cl 26.5.1.1a)", Ast_prov >= Ast_min))
    checks.append(("flexure Ast <= Ast_max (cl 26.5.1.1b)", Ast_prov <= Ast_max))
    checks.append(("moment capacity >= Mu", Mu_capacity >= Mu * 0.999))
    checks.append(("shear (cl 40)", stirrups["ok"]))
    checks.append(("deflection L/d (cl 23.2.1)", defl["ok"]))

    side_face = D > 750.0
    if side_face:
        # 0.1% of web area, distributed on both faces, cl 26.5.1.3
        checks.append(("side-face reinforcement required (cl 26.5.1.3, D>750)",
                       True))

    if seismic:
        checks.append((f"IS 13920 min width b >= {tables.DUCTILE['beam_min_b']:.0f} (cl 6.1.1)",
                       b >= tables.DUCTILE["beam_min_b"]))
        checks.append((f"IS 13920 pt <= {tables.DUCTILE['beam_max_pt']*100:.1f}% (cl 6.2.2)",
                       pt / 100.0 <= tables.DUCTILE["beam_max_pt"]))
        checks.append(("IS 13920 min tension steel Ast_min (cl 6.2.1)",
                       Ast_prov >= Ast_min))
        checks.append(("IS 13920 confining-zone (2d) stirrup spacing <= "
                       "max(min(d/4, 8*dia_min), 100) (cl 6.3.5)",
                       0 < ductile_stirrups["confining_zone_spacing_mm"]
                       <= ductile_stirrups["confining_zone_spacing_limit_mm"]))
        checks.append(("IS 13920 span-zone stirrup spacing <= d/2 (cl 6.3.5)",
                       0 < ductile_stirrups["span_zone_spacing_mm"]
                       <= ductile_stirrups["span_zone_spacing_limit_mm"]))

    ok = all(v for _, v in checks)

    summary = {
        "d_mm": d,
        "Mu_max_kNm": Mu_max_kNm,
        "Mu_sagging_kNm": Mu_pos,
        "Mu_hogging_kNm": Mu_neg,
        "Vu_max_kN": Vu_max_kN,
        "Mu_lim_kNm": Mlim / 1e6,
        "doubly_reinforced": doubly,
        "Ast_reqd_mm2": Ast_reqd,
        "Ast_prov_mm2": Ast_prov,
        "n_bars": n_bars,
        "bar_dia": bar_dia,
        "Asc_reqd_mm2": Asc_reqd,
        "Asc_prov_mm2": Asc_prov,
        "n_bars_comp": n_bars_c,
        "pt_percent": pt,
        "Ast_min_mm2": Ast_min,
        "Ast_max_mm2": Ast_max,
        "stirrups": stirrups,
        "deflection": defl,
        "side_face_steel_required": side_face,
    }
    if ductile_stirrups is not None:
        # additive, seismic-only (keeps the frozen non-seismic v1 key set intact)
        summary["ductile_stirrups"] = ductile_stirrups

    return {
        "inputs": {"span_m": span_m, "w_dl_kn_m": w_dl_kn_m,
                   "w_il_kn_m": w_il_kn_m, "w_u_kn_m": w_u,
                   "b": b, "D": D, "fck": fck, "fy": fy,
                   "support": support, "point_loads": point_loads,
                   "cover": cover, "bar_dia": bar_dia,
                   "stirrup_dia": stirrup_dia, "seismic": seismic},
        "analysis": {"x": res["x"], "V": V, "M": M},
        "design": summary,
        "checks": checks,
        "ok": ok,
    }
