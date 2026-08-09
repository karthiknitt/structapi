"""Slab design per IS 456:2000 cl 24, Table 26 / Annex D, cl 26.5.2.

One-way (ly/lx > 2) and two-way restrained/simply-supported slabs.
Design per 1 m strip. Units: geometry m, loads kN/m2, sections N/mm/MPa.
"""

from __future__ import annotations

import math

from .. import rounding
from .. import tables
from .. import serviceability as svc

BAR_AREA = {8: 50.3, 10: 78.5, 12: 113.1, 16: 201.1}


def _ast_annex_g(Mu, b, d, fck, fy):
    R = 4.6 * Mu / (fck * b * d * d)
    if R >= 1.0:
        return None
    return 0.5 * fck / fy * (1 - math.sqrt(1 - R)) * b * d


def _spacing_for(ast_req_per_m: float, dia: int, cap: float) -> float:
    s = BAR_AREA[dia] * 1000.0 / max(ast_req_per_m, 1e-6)
    return max(rounding.site_spacing(s, cap), 50.0)


def _strip_design(Mu_Nmm_per_m: float, D: float, d: float, fck: float, fy: float,
                  bar_dia: int, checks: list, tag: str) -> dict:
    b = 1000.0
    ast = _ast_annex_g(Mu_Nmm_per_m, b, d, fck, fy)
    if ast is None:
        checks.append((f"{tag}: depth adequate for flexure (Annex G)", False))
        return {"Ast_req": None}
    ast_min = 0.0012 * b * D  # HYSD, cl 26.5.2.1
    ast_req = max(ast, ast_min)
    cap = min(3 * d, 300.0)  # cl 26.3.3(b)(1)
    s = _spacing_for(ast_req, bar_dia, cap)
    ast_prov = BAR_AREA[bar_dia] * 1000.0 / s
    checks.append((f"{tag}: Ast >= max(flexure, 0.12%bD) (cl 26.5.2.1)",
                   ast_prov >= ast_req - 1e-6))
    checks.append((f"{tag}: spacing <= min(3d, 300) (cl 26.3.3b)", s <= cap))
    return {"Ast_req": ast_req, "Ast_min": ast_min,
            "bar": f"{bar_dia}mm @ {s:.0f} c/c", "spacing": s,
            "Ast_prov": ast_prov}


def design_one_way_slab(lx_m: float, w_dl: float, w_il: float, fck: float,
                        fy: float, support: str = "ss", D_mm: float | None = None,
                        cover: float = 20.0, bar_dia: int = 10) -> dict:
    """One-way slab, 1 m strip. w_dl EXCLUDES self weight if D_mm is None
    (self weight added after the trial depth is chosen); includes finishes.
    When D_mm is None the depth auto-increases until deflection passes."""
    base = 20.0 if support == "ss" else 26.0
    auto = D_mm is None
    if auto:
        d_trial = lx_m * 1000.0 / (base * 1.4)  # assume kt ~ 1.4 for slabs
        D_mm = rounding.site_dimension(d_trial + cover + bar_dia / 2)
        D_mm = max(D_mm, 100.0)
    for _ in range(12):
        result = _one_way_once(lx_m, w_dl, w_il, fck, fy, support, D_mm,
                               cover, bar_dia)
        if result["ok"] or not auto:
            return result
        D_mm += 25.0
    return result


def _one_way_once(lx_m, w_dl, w_il, fck, fy, support, D_mm, cover, bar_dia):
    checks = []
    d = D_mm - cover - bar_dia / 2

    w_self = D_mm / 1000.0 * tables.UNIT_WEIGHTS["rcc"]
    w_u = 1.5 * (w_dl + w_self + w_il)  # kN/m per m strip
    L = lx_m
    Mu = (w_u * L ** 2 / 8.0) if support == "ss" else (w_u * L ** 2 / 12.0)
    Vu = w_u * L / 2.0
    main = _strip_design(Mu * 1e6, D_mm, d, fck, fy, bar_dia, checks, "main")

    # distribution steel, cl 26.5.2.1; spacing <= min(5d, 450) cl 26.3.3(b)(2)
    ast_dist = 0.0012 * 1000.0 * D_mm
    s_dist = _spacing_for(ast_dist, 8, min(5 * d, 450.0))
    dist = {"Ast_req": ast_dist, "bar": f"8mm @ {s_dist:.0f} c/c"}

    # shear, cl 40.2.1.1
    tau_v = Vu * 1e3 / (1000.0 * d)
    pt = 100 * main.get("Ast_prov", 0) / (1000.0 * d)
    tau_allow = tables.k_solid_slab(D_mm) * tables.tau_c(pt, fck)
    checks.append(("shear tau_v <= k*tau_c (cl 40.2.1.1)", tau_v <= tau_allow))

    # deflection, cl 23.2.1
    supp = "simply_supported" if support == "ss" else "continuous"
    ratio = (main["Ast_req"] / main["Ast_prov"]) if main.get("Ast_prov") else 1.0
    defl = svc.check_deflection(lx_m * 1000.0, d, supp, fy, max(pt, 0.1), ratio)
    checks.append(("deflection L/d (cl 23.2.1)", defl["ok"]))

    return {"ok": all(o for _, o in checks), "checks": checks,
            "D_mm": D_mm, "d_mm": d, "w_u_kN_m2": w_u,
            "Mu_kNm": Mu, "Vu_kN": Vu, "main": main, "distribution": dist,
            "tau_v": tau_v, "tau_allow": tau_allow, "deflection": defl}


def design_two_way_slab(lx_m: float, ly_m: float, w_dl: float, w_il: float,
                        fck: float, fy: float, case: int = 4,
                        corners_held: bool = True, D_mm: float | None = None,
                        cover: float = 20.0, bar_dia: int = 10) -> dict:
    """Two-way slab per IS 456 Annex D. lx = shorter span. w_dl excludes self
    weight when D_mm is None; includes finishes."""
    if ly_m < lx_m:
        lx_m, ly_m = ly_m, lx_m
    r = ly_m / lx_m
    if r > 2.0:
        raise ValueError("ly/lx > 2 — design as one-way slab")
    auto = D_mm is None
    if auto:
        # cl 24.1: span/overall-depth 28 (ss) / 32 (cont) for HYSD as start
        base = 32.0 if case != 9 else 28.0
        D_mm = max(rounding.site_dimension(lx_m * 1000.0 / base), 100.0)
    for _ in range(12):
        result = _two_way_once(lx_m, ly_m, r, w_dl, w_il, fck, fy, case,
                               corners_held, D_mm, cover, bar_dia)
        if result["ok"] or not auto:
            return result
        D_mm += 25.0
    return result


def _two_way_once(lx_m, ly_m, r, w_dl, w_il, fck, fy, case, corners_held,
                  D_mm, cover, bar_dia):
    checks = []
    d_x = D_mm - cover - bar_dia / 2          # short-span steel outermost
    d_y = d_x - bar_dia

    w_self = D_mm / 1000.0 * tables.UNIT_WEIGHTS["rcc"]
    w_u = 1.5 * (w_dl + w_self + w_il)

    if corners_held:
        c = tables.slab_coefficients(case, r)
        coeffs = {"neg_x": c["nx"], "pos_x": c["px"],
                  "neg_y": c["ny"], "pos_y": c["py"]}
    else:
        c = tables.slab_ss_coefficients(r)
        coeffs = {"neg_x": None, "pos_x": c["ax"],
                  "neg_y": None, "pos_y": c["ay"]}

    out_strips = {}
    for tag, alpha, d_eff in (("mid_short_x", coeffs["pos_x"], d_x),
                              ("edge_short_x", coeffs["neg_x"], d_x),
                              ("mid_long_y", coeffs["pos_y"], d_y),
                              ("edge_long_y", coeffs["neg_y"], d_y)):
        if alpha is None:
            continue
        Mu = alpha * w_u * lx_m ** 2  # kNm/m (both directions use lx^2, D-1.1)
        out_strips[tag] = {"alpha": alpha, "Mu_kNm": Mu,
                           **_strip_design(Mu * 1e6, D_mm, d_eff, fck, fy,
                                           bar_dia, checks, tag)}

    # shear (approx: V = w lx/2 per m at long edge, cl 24.5 trapezoid)
    Vu = w_u * lx_m / 2.0
    tau_v = Vu * 1e3 / (1000.0 * d_x)
    pt = 100 * out_strips["mid_short_x"].get("Ast_prov", 0) / (1000.0 * d_x)
    tau_allow = tables.k_solid_slab(D_mm) * tables.tau_c(pt, fck)
    checks.append(("shear tau_v <= k*tau_c (cl 40.2.1.1)", tau_v <= tau_allow))

    # shear, long-span edge (additive; PC-6): the block above uses the peak
    # ordinate of the 45 deg yield-line load-dispersion pattern (2 triangles
    # + 2 trapezoids per panel) -- that peak ordinate is w_u*lx/2 at BOTH the
    # short-edge (triangle apex) and the long-edge (trapezoid plateau), so it
    # is not itself reduced by r. What IS reduced by r is the *average*
    # intensity the trapezoid delivers along the long-span edge's full
    # length ly (total trapezoid load / ly): Vu_long = w_u*lx/2*(1-1/(2r)).
    # Derivation: trapezoid area = (lx/4)(2*ly-lx) -> total load w_u*that ->
    # /ly = w_u*lx/2*(1-lx/(2ly)) = w_u*lx/2*(1-1/(2r)). At r=1 this equals
    # w_u*lx/4, i.e. HALF of the peak-based Vu above (not equal to it) --
    # the two formulas measure different statistics (peak vs average) of
    # the same load pattern, so exact numeric coincidence at r=1 is not
    # expected; see task-PC-6-report.md for the verified 0.5x relationship
    # and confidence notes. Checked against d_y/pt from the long-span
    # (mid_long_y) steel -- the inner-layer, lower-pt direction -- so this
    # check can fail even when the short-edge check above passes.
    Vu_long_edge = w_u * lx_m / 2.0 * (1.0 - 1.0 / (2.0 * r))
    tau_v_long_edge = Vu_long_edge * 1e3 / (1000.0 * d_y)
    pt_y = (100 * out_strips.get("mid_long_y", {}).get("Ast_prov", 0)
            / (1000.0 * d_y))
    tau_allow_long_edge = tables.k_solid_slab(D_mm) * tables.tau_c(pt_y, fck)
    checks.append(("shear tau_v <= k*tau_c, long edge (cl 40.2.1.1, "
                   "trapezoid)", tau_v_long_edge <= tau_allow_long_edge))

    # deflection: short span governs (cl 24.1 note / 23.2)
    ast_ratio = 1.0
    s = out_strips["mid_short_x"]
    if s.get("Ast_prov"):
        ast_ratio = s["Ast_req"] / s["Ast_prov"]
    supp = "continuous" if (corners_held and case != 9) else "simply_supported"
    defl = svc.check_deflection(lx_m * 1000.0, d_x, supp, fy, max(pt, 0.1),
                                ast_ratio)
    checks.append(("deflection L/d short span (cl 24.1/23.2)", defl["ok"]))

    torsion_note = None
    if corners_held and case != 1:
        ast_t = 0.75 * s.get("Ast_req", 0.0)
        torsion_note = (f"Torsion steel at discontinuous corners (D-1.8): "
                        f"{ast_t:.0f} mm2/m in 4 layers over lx/5 = "
                        f"{lx_m / 5:.2f} m each way")

    return {"ok": all(o for _, o in checks), "checks": checks,
            "ly_by_lx": r, "case": case if corners_held else "D-2 (ss)",
            "D_mm": D_mm, "d_x_mm": d_x, "d_y_mm": d_y, "w_u_kN_m2": w_u,
            "strips": out_strips, "tau_v": tau_v, "tau_allow": tau_allow,
            "Vu_long_edge_kN": Vu_long_edge, "tau_v_long_edge": tau_v_long_edge,
            "tau_allow_long_edge": tau_allow_long_edge,
            "deflection": defl, "torsion_note": torsion_note}
