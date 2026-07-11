"""RC shear design (vertical stirrups) per IS 456:2000 cl 40 and cl 26.5.1.6.

Units: N, mm, MPa.
"""

from __future__ import annotations

import math

from .. import tables


def design_stirrups(Vu_N: float, b: float, d: float, fck: float, fy: float,
                    Ast_mm2: float, stirrup_dia: float = 8,
                    legs: int = 2) -> dict:
    """Design vertical stirrups for factored shear Vu (N).

    Returns dict with tau_v, tau_c, tau_c_max, Asv, sv_calc, sv_provided
    (rounded down to 5 mm), governing check name, and ok flag.
    """
    tau_v = Vu_N / (b * d)
    tau_cmax = tables.tau_c_max(fck)
    Asv = legs * math.pi * stirrup_dia ** 2 / 4.0

    if tau_v > tau_cmax:
        return {"tau_v": tau_v, "tau_c": None, "tau_c_max": tau_cmax,
                "Asv": Asv, "sv_calc": 0.0, "sv_provided": 0,
                "governing": "tau_v > tau_c_max (section inadequate, cl 40.2.3)",
                "ok": False}

    pt = 100.0 * Ast_mm2 / (b * d)
    tau_c = tables.tau_c(pt, fck)
    sv_max = min(0.75 * d, 300.0)

    if tau_v <= tau_c:
        sv = 0.87 * fy * Asv / (0.4 * b)  # cl 26.5.1.6 minimum shear steel
        governing = "minimum stirrups (cl 26.5.1.6)"
    else:
        Vus = Vu_N - tau_c * b * d
        sv = 0.87 * fy * Asv * d / Vus     # cl 40.4
        governing = "designed shear (cl 40.4)"

    sv = min(sv, sv_max)
    sv_prov = int(math.floor(sv / 5.0) * 5)
    return {"tau_v": tau_v, "tau_c": tau_c, "tau_c_max": tau_cmax,
            "Asv": Asv, "sv_calc": sv, "sv_provided": sv_prov,
            "governing": governing, "ok": True}
