"""RC flexure design/analysis per IS 456:2000 Annex G and cl 26.5.1.

Units: N, mm, MPa.
"""

from __future__ import annotations

import math

from .. import tables


def mu_lim(b: float, d: float, fck: float, fy: float) -> float:
    """Limiting moment of resistance Mu_lim (N.mm), cl 38.1 / Annex G."""
    return tables.mu_lim_factor(fy) * fck * b * d ** 2


def ast_singly(Mu_Nmm: float, b: float, d: float, fck: float, fy: float,
               raise_on_over: bool = True) -> float:
    """Tension steel for a singly-reinforced section (Annex G-1.1(b)).

    Ast = 0.5 fck/fy (1 - sqrt(1 - 4.6 Mu/(fck b d^2))) b d.
    Raises ValueError if Mu exceeds Mu_lim (section needs compression steel),
    unless raise_on_over is False.
    """
    Mlim = mu_lim(b, d, fck, fy)
    if Mu_Nmm > Mlim:
        if raise_on_over:
            raise ValueError(
                f"Mu={Mu_Nmm:.3e} N.mm exceeds Mu_lim={Mlim:.3e} N.mm; "
                "design as doubly reinforced (use design_doubly).")
    disc = 1.0 - 4.6 * Mu_Nmm / (fck * b * d ** 2)
    if disc < 0:
        raise ValueError("no singly-reinforced solution (discriminant < 0)")
    return 0.5 * fck / fy * (1.0 - math.sqrt(disc)) * b * d


def ast_lim(b: float, d: float, fck: float, fy: float) -> float:
    """Tension steel corresponding to Mu_lim."""
    k = tables.xu_max_by_d(fy)
    return mu_lim(b, d, fck, fy) / (0.87 * fy * d * (1.0 - 0.42 * k))


def design_doubly(Mu_Nmm: float, b: float, d: float, dc: float,
                  fck: float, fy: float) -> dict:
    """Doubly-reinforced design (Annex G-1.2).

    Returns dict with Ast, Asc, Mu_lim, Mu2, fsc, Ast_lim.
    """
    Mlim = mu_lim(b, d, fck, fy)
    Mu2 = Mu_Nmm - Mlim
    if Mu2 <= 0:
        raise ValueError("Mu <= Mu_lim; use ast_singly (no compression steel)")
    fsc_val = tables.fsc(fy, dc / d)
    Asc = Mu2 / ((fsc_val - 0.446 * fck) * (d - dc))
    Astl = ast_lim(b, d, fck, fy)
    Ast = Astl + Mu2 / (0.87 * fy * (d - dc))
    return {"Ast": Ast, "Asc": Asc, "Mu_lim": Mlim, "Mu2": Mu2,
            "fsc": fsc_val, "Ast_lim": Astl}


def min_steel(b: float, d: float, fy: float) -> float:
    """Minimum tension steel, cl 26.5.1.1(a): As/(bd) = 0.85/fy."""
    return 0.85 * b * d / fy


def max_steel(b: float, D: float) -> float:
    """Maximum tension (or compression) steel, cl 26.5.1.1(b) / 26.5.1.2."""
    return 0.04 * b * D


def mu_capacity(Ast: float, b: float, d: float, fck: float, fy: float) -> float:
    """Moment capacity (N.mm) of a singly-reinforced section.

    xu = 0.87 fy Ast / (0.36 fck b). If xu > xu_max the section is
    over-reinforced; capacity is capped at Mu_lim.
    """
    xu = 0.87 * fy * Ast / (0.36 * fck * b)
    xu_max = tables.xu_max_by_d(fy) * d
    if xu > xu_max:
        return mu_lim(b, d, fck, fy)
    return 0.87 * fy * Ast * d * (1.0 - 0.42 * xu / d)
