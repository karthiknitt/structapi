"""Beam analysis by superposition of closed-form solutions.

Statically determinate (simply supported, cantilever) and standard
fixed-fixed results, plus IS 456 Table 12/13 coefficients for continuous
members (cl 22.5.1).

Sign convention: sagging moment positive, hogging negative. Shear positive
where the left part of a cut tends to move up relative to the right.

Units: kN, m (and kN.m for moments), consistent with loads.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .. import tables


@dataclass
class BeamCase:
    """A single-span beam load case.

    span_m: clear/effective span L (m).
    supports: 'ss' | 'cantilever' | 'fixed'.
    udl_kn_m: uniformly distributed load (kN/m) — a single value, or a list of
        full-span UDLs that are summed.
    point_loads: list of (P_kN, a_m), a measured from the left support
        (from the fixed end for a cantilever).
    """
    span_m: float
    supports: str = "ss"
    udl_kn_m: object = 0.0
    point_loads: list = field(default_factory=list)

    @property
    def w(self) -> float:
        u = self.udl_kn_m
        if isinstance(u, (list, tuple, np.ndarray)):
            return float(sum(u))
        return float(u)


def analyze(case: BeamCase, n: int = 501) -> dict:
    """Return {x, V, M, L, support} arrays by superposition of closed forms.

    x in m, V in kN, M in kN.m.
    """
    L = float(case.span_m)
    x = np.linspace(0.0, L, n)
    w = case.w
    sup = case.supports
    pls = list(case.point_loads or [])

    V = np.zeros(n)
    M = np.zeros(n)

    if sup == "ss":
        if w:
            V += w * (L / 2.0 - x)
            M += w * x * (L - x) / 2.0
        for P, a in pls:
            b = L - a
            Ra, Rb = P * b / L, P * a / L
            V += np.where(x < a, Ra, -Rb)
            M += np.where(x <= a, Ra * x, Rb * (L - x))

    elif sup == "cantilever":
        # fixed at x = 0, free end at x = L
        if w:
            V += w * (L - x)
            M += -w * (L - x) ** 2 / 2.0
        for P, a in pls:
            V += np.where(x < a, float(P), 0.0)
            M += np.where(x < a, -P * (a - x), 0.0)

    elif sup == "fixed":
        # fixed-fixed: SS solution + linear end-moment (hogging) diagram
        if w:
            V += w * (L / 2.0 - x)
            M += w * x * (L - x) / 2.0 - w * L ** 2 / 12.0
        for P, a in pls:
            b = L - a
            Ra, Rb = P * b / L, P * a / L
            Mss = np.where(x <= a, Ra * x, Rb * (L - x))
            Ma = -P * a * b ** 2 / L ** 2
            Mb = -P * a ** 2 * b / L ** 2
            M += Mss + Ma + (Mb - Ma) * x / L
            Vss = np.where(x < a, Ra, -Rb)
            V += Vss + (Mb - Ma) / L
    else:
        raise ValueError(f"unknown support type: {sup!r}")

    return {"x": x, "V": V, "M": M, "L": L, "support": sup}


def continuous_moments(w_dl: float, w_il: float, L: float) -> dict:
    """Design moments/shears for a continuous beam or one-way slab.

    IS 456 cl 22.5.1, Tables 12 (moments) and 13 (shear). DL and IL are
    factored separately with their own coefficients then summed.
    M = coeff * w * L^2 (kN.m); V = coeff * w * L (kN). Sagging +, hogging -.
    """
    T = tables.TABLE_12_MOMENT
    S = tables.TABLE_13_SHEAR

    def m(dl_key: str, il_key: str) -> float:
        return T[dl_key] * w_dl * L ** 2 + T[il_key] * w_il * L ** 2

    def v(dl_key: str, il_key: str) -> float:
        return S[dl_key] * w_dl * L + S[il_key] * w_il * L

    return {
        "M_span_end": m("span_end_DL", "span_end_IL"),
        "M_span_interior": m("span_interior_DL", "span_interior_IL"),
        "M_support_next_to_end": m("support_next_to_end_DL",
                                   "support_next_to_end_IL"),
        "M_support_interior": m("support_interior_DL", "support_interior_IL"),
        "V_end_support": v("end_support_DL", "end_support_IL"),
        "V_support_next_to_end_outer": v("support_next_to_end_outer_DL",
                                         "support_next_to_end_outer_IL"),
        "V_support_next_to_end_inner": v("support_next_to_end_inner_DL",
                                         "support_next_to_end_inner_IL"),
        "V_support_interior": v("support_interior_DL", "support_interior_IL"),
    }
