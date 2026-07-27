"""RC footing design per IS 456:2000 (cl 34, 31.6) and IS 6403:1981.

Covers safe bearing capacity (IS 6403 general shear equation), isolated
(square / rectangular, axial + uniaxial moment) footings and two-column
combined footings.

Design basis: net factored soil pressure (self weight excluded from the
structural pressure, allowed for by the 1.1 service factor on sizing).
Depth is fixed by shear — two-way (punching) at d/2 from the column faces
(cl 31.6.3) and one-way at d from the face (cl 40) — never by flexure.
Flexure steel by the Annex G-1.1(b) closed form, minimum 0.12 % (HYSD).

Units: kN, m, kN/m2 at the API surface; N, mm, MPa inside section checks.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from .. import tables


# ---------------------------------------------------------------------------
# shared section helpers (self-contained — no dependency on flexure/shear)
# ---------------------------------------------------------------------------

def _ast_annex_g(Mu_Nmm: float, b: float, d: float, fck: float, fy: float):
    """Tension steel (mm2) for a singly-reinforced rectangular section,
    IS 456 Annex G-1.1(b). Returns None if the section is inadequate."""
    if d <= 0 or b <= 0:
        return None
    R = 4.6 * Mu_Nmm / (fck * b * d * d)
    if R >= 1.0:
        return None
    return 0.5 * fck / fy * (1 - math.sqrt(1 - R)) * b * d


def _bar_for_strip(ast_per_m: float, dias=(8, 10, 12, 16, 20, 25),
                   s_max: float = 300.0, s_min: float = 75.0) -> dict:
    """Pick bar dia + spacing (mm) for a 1 m strip giving >= ast_per_m (mm2/m)."""
    ast_per_m = max(ast_per_m, 1.0)
    for dia in dias:
        a = math.pi * dia ** 2 / 4.0
        s = math.floor(a / ast_per_m * 1000.0 / 5.0) * 5.0
        if s >= s_min:
            s = min(s, s_max)
            return {"dia": dia, "spacing": s, "ast_prov": a * 1000.0 / s}
    dia = dias[-1]
    a = math.pi * dia ** 2 / 4.0
    return {"dia": dia, "spacing": s_min, "ast_prov": a * 1000.0 / s_min}


# ---------------------------------------------------------------------------
# IS 6403:1981 — safe bearing capacity (general shear failure)
# ---------------------------------------------------------------------------

def safe_bearing_capacity(c_kpa: float, phi_deg: float, gamma: float = 18.0,
                          B: float = 1.5, L: float = 1.5, Df: float = 1.5,
                          FOS: float = 2.5, water_table: str = "deep") -> dict:
    """Net safe bearing capacity per IS 6403 general shear equation.

    qu_net = c Nc sc dc + q(Nq-1) sq dq + 0.5 gamma B Ngamma sgamma W'
    with q = gamma * Df (effective overburden). Returns qu_net and q_safe
    (kPa). Shape (cl 5.1.1 rect), depth and water-table factors as flagged.
    """
    f = tables.bearing_capacity_factors(phi_deg)
    Nc, Nq, Ng = f["Nc"], f["Nq"], f["Ngamma"]
    q = gamma * Df

    # shape factors (rectangular, IS 6403 Table)
    sc = 1 + 0.2 * B / L
    sq = 1 + 0.2 * B / L
    sg = 1 - 0.4 * B / L

    # depth factors
    Kp = math.tan(math.radians(45 + phi_deg / 2.0)) ** 2
    dc = 1 + 0.2 * (Df / B) * math.sqrt(Kp)
    if phi_deg < 10:
        dq = dg = 1.0
    else:
        dq = dg = 1 + 0.1 * (Df / B) * math.sqrt(Kp)

    # water-table reduction on the surcharge / self-weight term
    Wd = 0.5 if water_table in ("base", "at_base", "shallow") else 1.0

    qu_net = (c_kpa * Nc * sc * dc
              + q * (Nq - 1) * sq * dq
              + 0.5 * gamma * B * Ng * sg * Wd)
    q_safe = qu_net / FOS
    return {"qu_net": qu_net, "q_safe": q_safe,
            "Nc": Nc, "Nq": Nq, "Ngamma": Ng,
            "sc": sc, "sq": sq, "sgamma": sg, "dc": dc, "dq": dq, "W_prime": Wd,
            "note": "IS 6403:1981 general shear; net values (surcharge removed)."}


# ---------------------------------------------------------------------------
# Isolated footing — IS 456 cl 34
# ---------------------------------------------------------------------------

@dataclass
class FootingResult:
    ok: bool
    checks: list
    data: dict = field(default_factory=dict)


def design_isolated_footing(P_service_kN: float, M_service_kNm: float,
                            sbc_kpa: float, col_b_mm: float, col_D_mm: float,
                            fck: float, fy: float, gamma_soil: float = 18.0,
                            Df_m: float = 1.5, cover: float = 50.0,
                            bar_dia: float = 16.0) -> FootingResult:
    """Design a square/rectangular isolated footing (axial + uniaxial moment).

    Lx runs along col_D_mm (the moment-bending direction); Ly along col_b_mm.
    """
    P = float(P_service_kN)
    M = abs(float(M_service_kNm))
    e = M / P if P else 0.0

    # ---- 1. plan sizing (service): A = 1.1 P / sbc, then satisfy pressure ----
    A_req = 1.1 * P / sbc_kpa
    side = math.sqrt(A_req)
    L = B = math.ceil(side / 0.05) * 0.05  # L along bending, B transverse

    # Development-length floor on the plan size (cl 26.2.1 / 34.2.4.3).
    # Step 6 below auto-selects a smaller bar when anchorage is tight, but it
    # bottoms out at 8 mm: if even a bent 8 mm bar cannot develop within the
    # projection this footing offers, no amount of re-detailing fixes it — the
    # footing itself has to be wider. Size for that here, so the design comes
    # out self-consistent instead of reporting an "increase_section" violation
    # the caller has no knob to act on. Only L is raised: `avail` below takes
    # max(proj_x, proj_y), so developing in one direction is enough, and
    # growing both would oversize every footing on the plot.
    _DIA_MIN = 8.0
    _proj_req = tables.development_length(_DIA_MIN, fy, fck) - 8.0 * _DIA_MIN + cover
    L = max(L, math.ceil((col_D_mm + 2 * _proj_req) / 1000.0 / 0.05) * 0.05)

    for _ in range(400):
        A = L * B
        q_avg = P / A
        q_max = q_avg * (1 + 6 * e / L)
        q_min = q_avg * (1 - 6 * e / L)
        if q_max <= sbc_kpa * 1.0001 and q_min >= -1e-6:
            break
        if q_min < 0:
            L += 0.05
        elif L <= B:
            L += 0.05
        else:
            B += 0.05
    A = L * B
    q_avg = P / A
    q_max = q_avg * (1 + 6 * e / L)
    q_min = q_avg * (1 - 6 * e / L)

    # ---- 2. factored NET pressure (1.5 P, 1.5 M; self weight excluded) ----
    pu_avg = 1.5 * P / A
    pu_max = pu_avg * (1 + 6 * e / L)          # kPa
    pu_min = pu_avg * (1 - 6 * e / L)
    pu_max_MPa = pu_max / 1000.0
    pu_avg_MPa = pu_avg / 1000.0

    Lx_mm, Ly_mm = L * 1000.0, B * 1000.0
    cs, cl_ = min(col_b_mm, col_D_mm), max(col_b_mm, col_D_mm)
    ks = min(0.5 + cs / cl_, 1.0)
    tau_p_lim = ks * 0.25 * math.sqrt(fck)

    proj_x = (Lx_mm - col_D_mm) / 2.0
    proj_y = (Ly_mm - col_b_mm) / 2.0

    # ---- 3. depth from shear (punching + one-way, both directions) ----
    d = 150.0
    result = None
    while d <= 2500.0:
        # two-way (punching) at d/2 from the column faces
        b0 = 2 * ((col_b_mm + d) + (col_D_mm + d))
        punch_area = Lx_mm * Ly_mm - (col_D_mm + d) * (col_b_mm + d)
        Vp = pu_max_MPa * punch_area
        tau_p = Vp / (b0 * d)

        # flexure steel at this d (needed for one-way tau_c)
        ggrad = (pu_max_MPa - pu_min / 1000.0) / Lx_mm  # per mm along Lx
        p_face_x = pu_max_MPa - ggrad * proj_x
        Mx = Ly_mm * (p_face_x * proj_x ** 2 / 2.0
                      + (pu_max_MPa - p_face_x) * proj_x ** 2 / 3.0)
        My = Lx_mm * pu_max_MPa * proj_y ** 2 / 2.0
        Ast_x = _ast_annex_g(Mx, Ly_mm, d, fck, fy) or 0.0
        Ast_y = _ast_annex_g(My, Lx_mm, d - bar_dia, fck, fy) or 0.0
        pt_x = 100 * max(Ast_x, 1.0) / (Ly_mm * d)
        pt_y = 100 * max(Ast_y, 1.0) / (Lx_mm * (d - bar_dia))

        # one-way shear at d from the column face
        Vx = pu_max_MPa * Ly_mm * max(proj_x - d, 0.0)
        Vy = pu_max_MPa * Lx_mm * max(proj_y - d, 0.0)
        tau_vx = Vx / (Ly_mm * d)
        tau_vy = Vy / (Lx_mm * d)
        tcx = tables.tau_c(pt_x, fck)
        tcy = tables.tau_c(pt_y, fck)

        if (tau_p <= tau_p_lim and tau_vx <= tcx and tau_vy <= tcy):
            result = dict(d=d, tau_p=tau_p, Mx=Mx, My=My, Ast_x=Ast_x,
                          Ast_y=Ast_y, pt_x=pt_x, pt_y=pt_y, tau_vx=tau_vx,
                          tau_vy=tau_vy, tcx=tcx, tcy=tcy, b0=b0)
            break
        d += 25.0

    checks = []
    if result is None:
        return FootingResult(False, [("depth converged for shear", False)],
                             {"L_m": L, "B_m": B, "note": "no d <= 2.5 m satisfied shear"})

    d = result["d"]
    D_overall = math.ceil((d + cover + bar_dia) / 25.0) * 25.0

    # ---- 4. flexure steel + minimums (0.12 % of B * D_overall) ----
    Ast_x = result["Ast_x"]
    Ast_y = result["Ast_y"]
    ast_min_x = 0.0012 * Ly_mm * D_overall
    ast_min_y = 0.0012 * Lx_mm * D_overall
    Ast_x = max(Ast_x, ast_min_x)
    Ast_y = max(Ast_y, ast_min_y)

    # ---- 5. rectangular short-direction band factor (cl 34.3.1c) ----
    beta = max(L, B) / min(L, B)
    band_factor = 2.0 / (beta + 1.0)  # fraction of short-dir steel in central band

    # bar callouts (per 1 m strip)
    bars_x = _bar_for_strip(Ast_x / B)   # long/bending direction steel
    bars_y = _bar_for_strip(Ast_y / L)   # transverse direction steel

    # ---- checks ----
    checks.append(("service q_max <= sbc (cl 34.1)", q_max <= sbc_kpa * 1.0001))
    checks.append(("service q_min >= 0 (no uplift)", q_min >= -1e-6))
    checks.append(("two-way shear tau_v <= ks*0.25*sqrt(fck) (cl 31.6.3)",
                   result["tau_p"] <= tau_p_lim))
    checks.append(("one-way shear X tau_v <= tau_c (cl 40)",
                   result["tau_vx"] <= result["tcx"]))
    checks.append(("one-way shear Y tau_v <= tau_c (cl 40)",
                   result["tau_vy"] <= result["tcy"]))
    checks.append(("min steel 0.12% both directions (cl 34.5.1)", True))

    # ---- 6. development length (cl 34.2.4.3 / 26.2.1) ----
    # A standard 90-degree bend contributes 8*phi of anchorage (cl 26.2.2.1).
    # On compact footings even a bent bar of the requested diameter may not
    # develop; standard practice is smaller bars at closer spacing — select
    # the largest diameter (<= requested) that develops with a bend.
    avail = max(proj_x, proj_y) - cover
    sel_dia = bar_dia
    for cand in sorted({bar_dia, 12.0, 10.0, 8.0}, reverse=True):
        if cand > bar_dia:
            continue
        if avail + 8.0 * cand >= tables.development_length(cand, fy, fck):
            sel_dia = cand
            break
    else:
        sel_dia = 8.0
    Ld = tables.development_length(sel_dia, fy, fck)
    needs_bend = avail < Ld
    checks.append(("development length (bar dia auto-selected, 90-deg bend "
                   "credited; cl 26.2.1/26.2.2.1)",
                   avail + 8.0 * sel_dia >= Ld))

    # ---- 7. bearing at column base (cl 34.4) ----
    A2 = col_b_mm * col_D_mm            # loaded (column) area
    A1 = Lx_mm * Ly_mm                  # supporting area
    ratio = min(math.sqrt(A1 / A2), 2.0)
    sigma_br = 1.5 * P * 1e3 / A2
    br_lim = 0.45 * fck * ratio
    checks.append(("bearing at column base (cl 34.4)", sigma_br <= br_lim))

    ok = all(v for _, v in checks)
    data = {
        "L_m": round(L, 3), "B_m": round(B, 3),
        "D_overall_mm": D_overall, "d_mm": d,
        "q_max_service_kPa": q_max, "q_min_service_kPa": q_min,
        "pu_max_kPa": pu_max, "pu_min_kPa": pu_min, "pu_avg_kPa": pu_avg,
        "Ast_x_mm2": Ast_x, "Ast_y_mm2": Ast_y,
        "Ast_x_per_m": Ast_x / B, "Ast_y_per_m": Ast_y / L,
        "bars_x": bars_x, "bars_y": bars_y,
        "band_factor_short_dir": band_factor, "beta_L_by_B": beta,
        "two_way_shear": {"tau_v": result["tau_p"], "tau_lim": tau_p_lim, "ks": ks},
        "one_way_shear": {"tau_vx": result["tau_vx"], "tcx": result["tcx"],
                          "tau_vy": result["tau_vy"], "tcy": result["tcy"]},
        "Mx_kNm": result["Mx"] / 1e6, "My_kNm": result["My"] / 1e6,
        "Ld_mm": Ld, "Ld_available_mm": avail,
        "main_bar_dia_max_mm": sel_dia,
        "anchorage_note": ((f"use <= {sel_dia:.0f} mm dia bars with 90-deg "
                            "end bends (cl 26.2.2.1)")
                           if needs_bend else "straight bars develop fully"),
        "bearing_sigma_MPa": sigma_br, "bearing_limit_MPa": br_lim,
        "dowels_note": None if sigma_br <= br_lim
        else "column bearing exceeds limit — provide dowels/starter bars (cl 34.4.3)",
    }
    return FootingResult(ok, checks, data)


# ---------------------------------------------------------------------------
# Combined footing (two columns) — IS 456 cl 34
# ---------------------------------------------------------------------------

def design_combined_footing(P1_kN: float, P2_kN: float, spacing_m: float,
                            sbc_kpa: float, col1_mm: float, col2_mm: float,
                            fck: float, fy: float, edge_limit_m: float | None = None,
                            cover: float = 50.0, bar_dia: float = 16.0,
                            margin_m: float = 0.3) -> dict:
    """Rectangular two-column combined footing.

    Length chosen so the footing centroid coincides with the load resultant
    (uniform soil pressure). If it cannot (edge constraint), a trapezoid is
    flagged. Longitudinal beam analysed with net upward UDL + downward column
    loads (numpy arrays for callers to plot).
    """
    P = P1_kN + P2_kN
    xr = P2_kN * spacing_m / P                     # resultant from col1

    # ---- plan sizing + geometry ----
    A_req = 1.1 * P / sbc_kpa
    trapezoid = False
    if edge_limit_m is not None:
        right_proj = edge_limit_m
        L = 2.0 * (spacing_m + right_proj - xr)
        if L <= 0:
            trapezoid = True
            L = 2.0 * max(xr, spacing_m - xr) + 2 * margin_m
    else:
        L = 2.0 * max(xr, spacing_m - xr) + 2 * margin_m
    B = math.ceil((A_req / L) / 0.05) * 0.05
    A = L * B

    col1_pos = L / 2.0 - xr                         # from left edge
    col2_pos = col1_pos + spacing_m
    centroid = L / 2.0
    centroid_from_col1 = centroid - col1_pos        # == xr by construction

    # ---- longitudinal beam: net upward UDL, downward point loads ----
    Pu1, Pu2 = 1.5 * P1_kN, 1.5 * P2_kN
    Pu = Pu1 + Pu2
    w_u = Pu / L                                    # kN/m upward
    x = np.linspace(0.0, L, 501)
    V = w_u * x - Pu1 * (x >= col1_pos) - Pu2 * (x >= col2_pos)
    M = (w_u * x ** 2 / 2.0
         - Pu1 * np.clip(x - col1_pos, 0, None)
         - Pu2 * np.clip(x - col2_pos, 0, None))
    M_hog = float(M.min())      # negative -> top tension between columns
    M_sag = float(M.max())      # positive -> bottom tension (cantilevers)
    V_max = float(np.abs(V).max())

    q_net_MPa = (Pu / A) / 1000.0                   # net factored pressure
    B_mm = B * 1000.0
    # depth: combined footings act as beams WITH stirrups — size the depth
    # from flexure (Mu <= Mu_lim with margin) and cap shear at tau_c_max
    # (Table 20); stirrups carry the excess (cl 40.4).
    Mu_gov = max(abs(M_hog), abs(M_sag)) * 1e6  # N.mm
    Q = tables.mu_lim_factor(fy)
    d_flex = math.sqrt(Mu_gov / (0.75 * Q * fck * B_mm))  # 75% utilization
    d = max(300.0, math.ceil(d_flex / 25.0) * 25.0)
    while d <= 2500.0 and V_max * 1e3 / (B_mm * d) > tables.tau_c_max(fck):
        d += 25.0
    D_overall = math.ceil((d + cover + bar_dia) / 25.0) * 25.0

    # ---- longitudinal steel (Annex G) ----
    ast_top = _ast_annex_g(abs(M_hog) * 1e6, B_mm, d, fck, fy) or 0.0
    ast_bot = _ast_annex_g(abs(M_sag) * 1e6, B_mm, d, fck, fy) or 0.0
    ast_min = 0.0012 * B_mm * D_overall
    ast_top = max(ast_top, ast_min)
    ast_bot = max(ast_bot, ast_min)

    checks = []
    checks.append(("centroid aligns with resultant (uniform pressure)",
                   abs(centroid_from_col1 - xr) < 0.01 and not trapezoid))
    tau_v_final = V_max * 1e3 / (B_mm * d)
    pt_final = 100 * ast_top / (B_mm * d)
    needs_stirrups = tau_v_final > tables.tau_c(pt_final, fck)
    checks.append(("longitudinal shear tau_v <= tau_c_max (cl 40.2.3)",
                   tau_v_final <= tables.tau_c_max(fck)))

    # ---- punching per column (as isolated) ----
    punch = {}
    for tag, cpos, csz, Pcol in (("col1", col1_pos, col1_mm, Pu1),
                                 ("col2", col2_pos, col2_mm, Pu2)):
        b0 = 2 * ((csz + d) + (csz + d))
        Vp = Pcol * 1e3 - q_net_MPa * (csz + d) ** 2
        tau_p = Vp / (b0 * d)
        tau_lim = min(0.5 + 1.0, 1.0) * 0.25 * math.sqrt(fck)  # square column ks=1
        punch[tag] = {"tau_v": tau_p, "tau_lim": tau_lim}
        checks.append((f"two-way shear {tag} (cl 31.6.3)", tau_p <= tau_lim))

    # ---- transverse band under each column (width = col + 0.75 d each side) ----
    bands = {}
    for tag, csz in (("col1", col1_mm), ("col2", col2_mm)):
        band_w = csz + 2 * 0.75 * d          # mm
        proj = (B_mm - csz) / 2.0
        Mt = q_net_MPa * proj ** 2 / 2.0     # N.mm per mm width
        ast_t = _ast_annex_g(Mt * band_w, band_w, d, fck, fy) or 0.0
        ast_t = max(ast_t, 0.0012 * band_w * D_overall)
        bands[tag] = {"band_width_mm": band_w, "Ast_mm2": ast_t,
                      "bars": _bar_for_strip(ast_t / (band_w / 1000.0))}

    ok = all(v for _, v in checks)
    return {
        "ok": ok, "checks": checks,
        "L_m": round(L, 3), "B_m": round(B, 3), "D_overall_mm": D_overall,
        "d_mm": d, "resultant_from_col1_m": xr,
        "centroid_from_col1_m": centroid_from_col1,
        "col1_pos_m": col1_pos, "col2_pos_m": col2_pos, "trapezoid": trapezoid,
        "w_u_kN_per_m": w_u, "x": x, "V": V, "M": M,
        "M_hogging_kNm": M_hog, "M_sagging_kNm": M_sag, "V_max_kN": V_max,
        "Ast_top_mm2": ast_top, "Ast_bottom_mm2": ast_bot,
        "bars_top": _bar_for_strip(ast_top / B), "bars_bottom": _bar_for_strip(ast_bot / B),
        "punching": punch, "transverse_bands": bands,
        "stirrup_note": ("design shear stirrups per cl 40.4 (tau_v > tau_c)"
                         if needs_stirrups
                         else "nominal stirrups per cl 26.5.1.6"),
    }
