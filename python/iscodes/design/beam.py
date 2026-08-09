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
                stirrup_dia: float = 8, seismic: bool = False,
                Mu_span_override_kNm: float | None = None,
                Mu_support_override_kNm: float | None = None,
                Vu_override_kN: float | None = None,
                exposure: str = "moderate") -> dict:
    """Design a single-span rectangular RC beam.

    b, D, cover, bar_dia, stirrup_dia in mm; loads in kN/m and (P_kN, a_m).
    Returns a dict: inputs, analysis (x,V,M arrays), design summary,
    checks list [(name, ok)], and overall ok flag.

    Continuous-member mode (IS 456 cl 22.5.1 / Tables 12-13)
    --------------------------------------------------------
    Supplying ``Mu_span_override_kNm`` and/or ``Mu_support_override_kNm``
    switches the section design from "one envelope moment, one reinforcement
    layer" to a genuine two-face design: **bottom** steel sized for the
    sagging span moment and **top** steel sized for the hogging support
    moment, each run through the same singly/doubly logic against ``Mlim``.
    ``Vu_override_kN`` likewise replaces the analysis-derived shear.

    The overrides are design *actions*, not loads — the caller has already
    factored them (the building chain passes
    ``continuous_moments(1.5*w_dl, 1.5*w_il, L)`` results). The internal
    ``analyze()`` call still runs so the returned SFD/BMD arrays remain
    available for plotting, but its moments no longer drive the section.

    With no overrides the behaviour and every pre-existing computed value are
    bit-for-bit identical to the pre-existing single-layer design (the frozen
    ``/v1/calc/beam`` v1 contract) — the ``top_steel``/``continuous`` keys are
    added only in override mode, and the new ``crack_width`` key/check below
    is additive (present in every mode, new field only).

    Crack-width SLS (IS 456 cl 43.1)
    ---------------------------------
    Every call also checks flexural crack width at the bottom (sagging/span)
    tension face per Annex F (``serviceability.crack_width_flexure``),
    against the cl 43.1 limit for ``exposure`` (0.3 mm mild/moderate, 0.2 mm
    severe/very severe/extreme — see ``tables.crack_limit_for_exposure``),
    plus the cl 26.3.3(b) deemed-to-satisfy max bar-spacing alternative. Two
    approximations, both documented at the call site: the service moment is
    back-calculated as ``Mu_bottom / 1.5`` (undoing this module's own
    1.5(DL+IL) gravity factor; not exact when IL/DL proportions vary or a
    lateral moment is present), and the clear bar spacing is derived
    assuming a single reinforcement layer (this model doesn't track bar
    layout beyond a count, consistent with everything else here).
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
    Vu_max_kN = float(max(abs(V.max()), abs(V.min())))

    # ---- continuous-member overrides (IS 456 cl 22.5.1) -------------------
    continuous = (Mu_span_override_kNm is not None
                  or Mu_support_override_kNm is not None)
    if Mu_span_override_kNm is not None:
        Mu_pos = abs(float(Mu_span_override_kNm))       # sagging, bottom face
    if Mu_support_override_kNm is not None:
        Mu_neg = -abs(float(Mu_support_override_kNm))   # hogging, top face
    if Vu_override_kN is not None:
        Vu_max_kN = abs(float(Vu_override_kN))

    Mu_max_kNm = max(abs(Mu_pos), abs(Mu_neg))

    # Bottom (tension-face) design moment. In single-layer mode this is the
    # whole envelope, exactly as before; in continuous mode the hogging
    # moment is carried by its own top layer instead of inflating the bottom.
    Mu_bottom_kNm = abs(Mu_pos) if continuous else Mu_max_kNm
    Mu_top_kNm = abs(Mu_neg) if continuous else 0.0

    Mu = Mu_bottom_kNm * 1e6         # N.mm
    Vu = Vu_max_kN * 1e3            # N

    # ---- effective depth --------------------------------------------------
    d = D - cover - stirrup_dia - bar_dia / 2.0
    dc = cover + stirrup_dia + bar_dia / 2.0

    # ---- flexure ----------------------------------------------------------
    Mlim = flexure.mu_lim(b, d, fck, fy)

    def _layer(Mu_Nmm: float) -> tuple[float, float, bool]:
        """Ast, Asc, doubly? for one face at one design moment."""
        if Mu_Nmm > Mlim:
            dd = flexure.design_doubly(Mu_Nmm, b, d, dc, fck, fy)
            return dd["Ast"], dd["Asc"], True
        return (flexure.ast_singly(Mu_Nmm, b, d, fck, fy, raise_on_over=False),
                0.0, False)

    doubly = Mu > Mlim
    Ast_reqd, Asc_reqd, _ = _layer(Mu)

    Ast_min = flexure.min_steel(b, d, fy)
    if seismic:
        Ast_min_ductile = max(0.85 / fy, 0.24 * math.sqrt(fck) / fy) * b * d
        Ast_min = max(Ast_min, Ast_min_ductile)
    Ast_max = flexure.max_steel(b, D)
    Ast_reqd = max(Ast_reqd, Ast_min)

    # ---- top (hogging) layer, continuous members only ---------------------
    Ast_top_reqd = Asc_top_reqd = 0.0
    doubly_top = False
    if continuous:
        Ast_top_reqd, Asc_top_reqd, doubly_top = _layer(Mu_top_kNm * 1e6)
        Ast_top_reqd = max(Ast_top_reqd, Ast_min)
        if seismic:
            # IS 13920:2016 cl 6.2.3 — the positive (bottom) steel at a joint
            # face shall be at least half the negative (top) steel there.
            # This model carries one bottom layer for the whole span, so the
            # requirement is enforced on that layer (conservative).
            Ast_reqd = max(Ast_reqd, 0.5 * Ast_top_reqd)

    # ---- bar selection (tension) -----------------------------------------
    area_bar = math.pi * bar_dia ** 2 / 4.0
    n_bars = max(2, math.ceil(Ast_reqd / area_bar))
    Ast_prov = n_bars * area_bar

    n_bars_c = 0
    Asc_prov = 0.0
    if Asc_reqd > 0:
        n_bars_c = max(2, math.ceil(Asc_reqd / area_bar))
        Asc_prov = n_bars_c * area_bar

    n_bars_top = n_bars_top_c = 0
    Ast_top_prov = Asc_top_prov = 0.0
    if continuous:
        n_bars_top = max(2, math.ceil(Ast_top_reqd / area_bar))
        Ast_top_prov = n_bars_top * area_bar
        if Asc_top_reqd > 0:
            n_bars_top_c = max(2, math.ceil(Asc_top_reqd / area_bar))
            Asc_top_prov = n_bars_top_c * area_bar

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

    # ---- crack width, IS 456 cl 43.1 / Annex F -----------------------------
    # Bottom (sagging/span) tension layer, service load. M_service is
    # approximated as Mu_bottom / 1.5, undoing this module's own 1.5(DL+IL)
    # gravity factor (see docstring); not exact when a lateral component is
    # blended into Mu_bottom via Mu_span_override_kNm.
    M_service_kNm = Mu_bottom_kNm / 1.5
    # Clear spacing between adjacent bars in a single layer (approximation:
    # assumes all n_bars sit in one layer, ignores multi-layer stacking for
    # large n_bars — consistent with the rest of this model, which doesn't
    # track bar layout beyond a count). This is the cl 26.3.3(b)
    # deemed-to-satisfy quantity (face-to-face gap between bars) -- NOT what
    # crack_width_flexure() needs (see below).
    if n_bars > 1:
        bar_spacing_clear_mm = (b - 2 * cover - 2 * stirrup_dia
                                - n_bars * bar_dia) / (n_bars - 1)
    else:
        bar_spacing_clear_mm = b - 2 * cover - 2 * stirrup_dia - bar_dia
    bar_spacing_clear_mm = max(bar_spacing_clear_mm, 1.0)  # geometric floor, degenerate case
    # crack_width_flexure()'s a_cr term (sqrt((bar_spacing/2)**2 + (D-d)**2))
    # requires centre-to-centre bar pitch, not clear spacing between bar
    # faces -- passing clear spacing under-predicts w_cr (confirmed ~6% on a
    # 300x550 M25/Fe500 beam, growing with bar count).
    bar_spacing_ctc_mm = bar_spacing_clear_mm + bar_dia
    cw = svc.crack_width_flexure(b, D, d, Ast_prov, fck,
                                 M_service_kNm * 1e6, cover,
                                 bar_dia, bar_spacing_ctc_mm)
    crack_limit_mm = tables.crack_limit_for_exposure(exposure)
    crack_width_mm = cw.get("w_cr")
    crack_ok = crack_width_mm is not None and crack_width_mm <= crack_limit_mm
    # Deemed-to-satisfy alternative (cl 43.1 note / cl 26.3.3(b)): compliance
    # with the max tension-bar-spacing rule is generally sufficient without
    # an explicit Annex F calculation. 0%-redistribution column (this model
    # doesn't track redistribution) — see tables.max_bar_spacing_tension.
    # cl 26.3.3(b)'s limit is itself a clear-spacing rule, so this check
    # correctly keeps using bar_spacing_clear_mm.
    deemed_spacing_limit_mm = tables.max_bar_spacing_tension(fy)
    deemed_ok = bar_spacing_clear_mm <= deemed_spacing_limit_mm
    crack_width = {
        "exposure": exposure,
        "M_service_kNm": M_service_kNm,
        "bar_spacing_mm": bar_spacing_ctc_mm,
        "bar_spacing_clear_mm": bar_spacing_clear_mm,
        "crack_width_mm": crack_width_mm,
        "steel_stress_service_MPa": cw.get("fs"),
        "limit_mm": crack_limit_mm,
        "ok": crack_ok,
        "deemed_to_satisfy": {
            "max_spacing_mm": deemed_spacing_limit_mm,
            "actual_spacing_mm": bar_spacing_clear_mm,
            "ok": deemed_ok,
        },
    }

    # ---- checks -----------------------------------------------------------
    def _capacity(Ast_p: float, Asc_p: float, dbl: bool) -> float:
        return (flexure.mu_capacity(Ast_p, b, d, fck, fy)
                + (Asc_p * (tables.fsc(fy, dc / d) - 0.446 * fck)
                   * (d - dc) if dbl else 0.0))

    Mu_capacity = _capacity(Ast_prov, Asc_prov, doubly)
    checks = []
    checks.append(("flexure Ast >= Ast_min (cl 26.5.1.1a)", Ast_prov >= Ast_min))
    checks.append(("flexure Ast <= Ast_max (cl 26.5.1.1b)", Ast_prov <= Ast_max))
    checks.append(("moment capacity >= Mu", Mu_capacity >= Mu * 0.999))
    checks.append(("shear (cl 40)", stirrups["ok"]))
    checks.append(("deflection L/d (cl 23.2.1)", defl["ok"]))
    checks.append((f"crack width <= {crack_limit_mm} mm "
                   f"(IS 456 cl 43.1, {exposure} exposure)", crack_ok))

    if continuous:
        # Additive, continuous-only: the frozen single-layer /v1/calc/beam
        # check-name list is untouched when no override is supplied.
        checks.append(("top steel Ast <= Ast_max (cl 26.5.1.1b)",
                       Ast_top_prov <= Ast_max))
        checks.append(("hogging moment capacity >= Mu_support (cl 22.5.1)",
                       _capacity(Ast_top_prov, Asc_top_prov, doubly_top)
                       >= Mu_top_kNm * 1e6 * 0.999))
        if seismic:
            checks.append(("IS 13920 bottom steel >= 0.5 x top steel at joint "
                           "face (cl 6.2.3)",
                           Ast_prov >= 0.5 * Ast_top_prov - 1e-6))

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
        "crack_width": crack_width,
    }
    if ductile_stirrups is not None:
        # additive, seismic-only (keeps the frozen non-seismic v1 key set intact)
        summary["ductile_stirrups"] = ductile_stirrups
    if continuous:
        # additive, continuous-only (same reason). "Ast_*"/"n_bars" at the top
        # level remain the bottom/sagging layer, so every existing consumer
        # keeps reading exactly what it read before.
        summary["continuous"] = True
        summary["top_steel"] = {
            "Mu_hogging_kNm": Mu_top_kNm,
            "Ast_reqd_mm2": Ast_top_reqd,
            "Ast_prov_mm2": Ast_top_prov,
            "n_bars": n_bars_top,
            "bar_dia": bar_dia,
            "doubly_reinforced": doubly_top,
            # compression steel for the hogging layer sits at the *bottom*
            # face at the support (continuing bottom bars, cl 26.5.1)
            "Asc_reqd_mm2": Asc_top_reqd,
            "Asc_prov_mm2": Asc_top_prov,
            "n_bars_comp": n_bars_top_c,
            "pt_percent": 100.0 * Ast_top_prov / (b * d),
            "Mu_capacity_kNm": _capacity(Ast_top_prov, Asc_top_prov,
                                         doubly_top) / 1e6,
        }
        summary["bottom_steel_Mu_kNm"] = Mu_bottom_kNm

    return {
        "inputs": {"span_m": span_m, "w_dl_kn_m": w_dl_kn_m,
                   "w_il_kn_m": w_il_kn_m, "w_u_kn_m": w_u,
                   "b": b, "D": D, "fck": fck, "fy": fy,
                   "support": support, "point_loads": point_loads,
                   "cover": cover, "bar_dia": bar_dia,
                   "stirrup_dia": stirrup_dia, "seismic": seismic,
                   "exposure": exposure},
        "analysis": {"x": res["x"], "V": V, "M": M},
        "design": summary,
        "checks": checks,
        "ok": ok,
    }
