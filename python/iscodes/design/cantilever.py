"""Chajja / sunshade cantilever slab design per IS 456:2000 cl 23.2.1,
cl 26.5.2, cl 40.2.1.1 — plus the torsional demand it imposes on its
supporting beam per IS 456 cl 41 (combined shear + torsion).

A chajja is a short RC cantilever slab projecting from the face of a beam
or wall (typically 0.45-1.0 m). Two distinct problems are handled here:

1. The chajja slab itself: a simple cantilever, hogging (TOP-face tension)
   moment at the root. Standard flexure/shear/deflection design, 1 m strip.
2. The torque this imposes on the supporting beam: the root moment acts
   eccentric to the beam's longitudinal axis and twists it. This module
   computes that demand (IS 456 cl 41.3.1 equivalent shear, cl 41.4.2
   equivalent bending moment) as INFORMATIONAL output only -- it does not
   redesign or check the supporting beam. A later chain-integration task
   feeds these numbers into `design_beam()` once that module grows a
   torsion-aware overlay; this module intentionally does not touch
   `beam.py`.

Units: geometry m, loads kN/m2, sections N/mm/MPa (mirrors slab.py).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .. import tables
from .. import serviceability as svc
# `_strip_design` and `_spacing_for` are `_`-prefixed (private-by-convention)
# in slab.py, but the flexure/shear/min-steel logic they implement (Annex G
# closed-form Ast, 0.12% HYSD minimum, cl 26.3.3(b) spacing caps) is exactly
# what a chajja's root section and distribution steel need too -- duplicating
# it here would just be a second place for the same IS 456 clause to drift
# out of sync. Reused explicitly rather than silently, per the brief's
# guidance on `_`-prefixed cross-module imports.
from .slab import _strip_design, _spacing_for


@dataclass
class ChajjaResult:
    ok: bool
    checks: list
    data: dict = field(default_factory=dict)


def design_chajja(projection_m: float, thickness_root_mm: float,
                  thickness_tip_mm: float | None = None, fck: float = 20.0,
                  fy: float = 415.0, LL_kn_m2: float = 0.75,
                  finish_kn_m2: float = 0.5, cover: float = 15.0,
                  bar_dia: int = 8,
                  supporting_beam_width_mm: float = 230.0,
                  supporting_beam_depth_mm: float = 300.0) -> ChajjaResult:
    """Design a chajja/sunshade cantilever slab, 1 m strip, and compute the
    torsional demand it imposes on its supporting beam.

    `LL_kn_m2` defaults to 0.75 kN/m2 -- this matches IS 875 Part 2's
    "roof, non-accessible" imposed load (see `tables.IMPOSED_LOADS
    ["roof_non_accessible"]` = 0.75, already used elsewhere in this
    codebase), the standard assumption for a chajja not intended for foot
    traffic beyond occasional maintenance access.

    `thickness_tip_mm=None` means uniform thickness = `thickness_root_mm`.
    If tapered, self-weight uses the AVERAGE of root/tip thickness, but the
    root section (critical for both moment and shear on a cantilever) is
    always designed using the root thickness for `d`.

    The root moment is HOGGING -- tension is on the TOP face (opposite of a
    normal simply-supported slab). The flexure result is returned under
    `data["top_steel"]` with an explicit `data["reinforced_face"] == "top"`
    marker so this can't silently regress to a bottom-face label.

    `supporting_beam_width_mm` / `supporting_beam_depth_mm` are assumed/
    typical values (this module has no access to an actual beam object);
    the caller overrides them once wired to a real supporting beam.
    """
    checks: list = []

    D_root = float(thickness_root_mm)
    D_tip = float(thickness_tip_mm) if thickness_tip_mm is not None else D_root
    D_avg = (D_root + D_tip) / 2.0
    d_root = D_root - cover - bar_dia / 2.0

    # ---- loads -----------------------------------------------------------
    w_self = D_avg / 1000.0 * tables.UNIT_WEIGHTS["rcc"]  # self-weight uses AVERAGE D
    w_u = 1.5 * (w_self + finish_kn_m2 + LL_kn_m2)  # kN/m per m-wide strip

    Mu = w_u * projection_m ** 2 / 2.0  # kNm/m, hogging at the root
    Vu = w_u * projection_m  # kN/m, at the root

    # ---- flexure at root, TOP face (hogging) — uses ROOT thickness -------
    top = _strip_design(Mu * 1e6, D_root, d_root, fck, fy, bar_dia, checks,
                        "top (hogging, root)")

    # ---- distribution steel (cl 26.5.2.1, spacing cl 26.3.3(b)(2)) -------
    ast_dist = 0.0012 * 1000.0 * D_root
    s_dist = _spacing_for(ast_dist, 8, min(5 * d_root, 450.0))
    dist = {"Ast_req": ast_dist, "bar": f"8mm @ {s_dist:.0f} c/c"}

    # ---- shear at root, cl 40.2.1.1 ---------------------------------------
    tau_v = Vu * 1e3 / (1000.0 * d_root)
    pt = 100.0 * top.get("Ast_prov", 0.0) / (1000.0 * d_root)
    tau_allow = tables.k_solid_slab(D_root) * tables.tau_c(pt, fck)
    checks.append(("shear tau_v <= k*tau_c (cl 40.2.1.1)", tau_v <= tau_allow))

    # ---- deflection, cl 23.2.1 — cantilever basic ratio (7, not 20/26) ---
    ast_ratio = (top["Ast_req"] / top["Ast_prov"]) if top.get("Ast_prov") else 1.0
    defl = svc.check_deflection(projection_m * 1000.0, d_root, "cantilever",
                                fy, max(pt, 0.1), ast_ratio)
    checks.append(("deflection L/d <= 7 for cantilever (cl 23.2.1)", defl["ok"]))

    # ---- Part 2: torsional demand on the supporting beam (IS 456 cl 41) --
    # Verified against IS 456:2000 cl 41.3.1 (equivalent shear) and
    # cl 41.4.2 (equivalent bending moment) — both the 1.6 and 1.7
    # coefficients and the formula shape in the brief match the code
    # clauses exactly, so no correction was needed here (unlike some other
    # domain-judgment tasks this sprint):
    #   cl 41.3.1: Ve = Vu + 1.6 * Tu / b   -> "addition" term = 1.6*Tu/b
    #   cl 41.4.2: Me1 = Mu + Mt, Mt = Tu * (1 + D/b) / 1.7
    b_beam_m = supporting_beam_width_mm / 1000.0
    D_beam_m = supporting_beam_depth_mm / 1000.0
    Tu_per_m = Mu  # kNm/m — the chajja's own root moment IS the applied torque per unit beam length
    Ve_addition_per_m = 1.6 * Tu_per_m / b_beam_m
    Me1_addition_per_m = Tu_per_m * (1 + D_beam_m / b_beam_m) / 1.7

    data = {
        "D_root_mm": D_root, "D_tip_mm": D_tip, "D_avg_mm": D_avg,
        "d_root_mm": d_root, "w_self_kN_m2": w_self, "w_u_kN_m2": w_u,
        "Mu_kNm": Mu, "Vu_kN": Vu,
        "reinforced_face": "top",
        "top_steel": top,
        "distribution": dist,
        "tau_v": tau_v, "tau_allow": tau_allow,
        "deflection": defl,
        # torsion-on-supporting-beam — informational only, see torsion_note
        "Tu_per_m_kNm": Tu_per_m,
        "Ve_addition_per_m_kN": Ve_addition_per_m,
        "Me1_addition_per_m_kNm": Me1_addition_per_m,
        "supporting_beam_width_mm": supporting_beam_width_mm,
        "supporting_beam_depth_mm": supporting_beam_depth_mm,
        "torsion_note": (
            "Tu_per_m/Ve_addition/Me1_addition are informational — apply to "
            "the actual supporting beam's design in a later chain-integration "
            "step; this module does not verify the beam."
        ),
    }

    return ChajjaResult(ok=all(o for _, o in checks), checks=checks, data=data)
