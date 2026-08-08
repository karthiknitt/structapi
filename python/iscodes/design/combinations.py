"""Limit-state load combinations for gravity + lateral (seismic/wind).

IS 456:2000 Table 18 / IS 1893 (Part 1):2016 cl 6.3.1.2 — the five design
combination families for a building frame carrying dead load (DL), imposed
load (IL) and a lateral earthquake/wind action (EL):

    1.  1.5 (DL + IL)
    2.  1.2 (DL + IL +- EL)          [EL taken along x and along y]
    3.  1.5 (DL +- EL)
    4.  0.9 DL +- 1.5 EL

Combination 4 is the uplift/overturning case: the dead load that stabilises
the frame is *reduced* to 0.9 while the destabilising lateral action is
factored up to 1.5, so it produces the minimum axial force on a column and
is the one that can drive an exterior column into net tension.

Everything here is pure arithmetic on kN / kNm — no section design, no IS
table lookups. The consumer (``design.building``) supplies the already
separated dead / imposed / lateral action components and decides what to do
with the resulting envelope.

Sign convention
---------------
``P_*`` are compressions (positive = compression on the column).
``M_E_*`` are supplied as *magnitudes*; the +- of the combination is applied
to the axial term only, because a frame moment reverses with the load
direction and its magnitude is what a symmetric section must be designed
for either way. That is why every lateral combo row carries
``+factor * M_E`` regardless of the axial sign.
"""

from __future__ import annotations

#: (label, dead factor, imposed factor, lateral factor) for the five families.
#: The lateral factor sign is expanded to +- by ``combination_envelope``.
_COMBOS: tuple[tuple[str, float, float, float], ...] = (
    ("1.5(DL+IL)", 1.5, 1.5, 0.0),
    ("1.2(DL+IL+-EL)", 1.2, 1.2, 1.2),
    ("1.5(DL+-EL)", 1.5, 0.0, 1.5),
    ("0.9DL+-1.5EL", 0.9, 0.0, 1.5),
)


def combination_envelope(P_D_kN: float, M_D_kNm: float,
                         P_IL_kN: float, M_IL_kNm: float,
                         P_E_kN: float, M_E_kNm: float,
                         M_Ey_kNm: float | None = None) -> dict:
    """Build the IS 1893 cl 6.3.1.2 combination table and envelope it.

    Parameters are per-column action components, all unfactored
    (characteristic) values:

    ``P_D_kN`` / ``M_D_kNm``
        dead-load axial (compression +ve) and moment.
    ``P_IL_kN`` / ``M_IL_kNm``
        imposed-load axial and moment.
    ``P_E_kN`` / ``M_E_kNm``
        lateral-action axial (the overturning couple's contribution, +ve on
        the leeward side) and the lateral frame moment about x, as a
        magnitude.
    ``M_Ey_kNm``
        lateral frame moment about y. Defaults to ``M_E_kNm`` — this model
        derives a single scalar storey shear, so the two principal
        directions carry the same magnitude unless told otherwise.

    Returns a dict with:

    ``combos``
        the full expanded table, one row per (family, direction, sign):
        ``{"name", "direction", "Pu_kN", "Mux_kNm", "Muy_kNm"}``.
    ``Pu_max_kN`` / ``Pu_min_kN``
        the extreme axial values over the table. ``Pu_min_kN`` is the
        uplift case and is negative when the column goes into net tension.
    ``Mux_max_kNm`` / ``Muy_max_kNm``
        the largest moment magnitude about each axis over the table.
    ``uplift_governs``
        True when ``Pu_min_kN`` is negative, i.e. an exterior column sheds
        all of its gravity compression under ``0.9DL - 1.5EL`` and needs a
        tension/anchorage design this model does not perform.
    ``governing_compression`` / ``governing_uplift``
        the specific rows producing ``Pu_max_kN`` and ``Pu_min_kN``.
    """
    M_Ex = abs(M_E_kNm)
    M_Ey = abs(M_E_kNm if M_Ey_kNm is None else M_Ey_kNm)

    combos: list[dict] = []
    for name, fD, fIL, fE in _COMBOS:
        Pu_grav = fD * P_D_kN + fIL * P_IL_kN
        Mu_grav = fD * M_D_kNm + fIL * M_IL_kNm
        if fE == 0.0:
            combos.append({"name": name, "direction": None,
                           "Pu_kN": Pu_grav,
                           "Mux_kNm": abs(Mu_grav), "Muy_kNm": 0.0})
            continue
        for direction, Mx, My in (("x", fE * M_Ex, 0.0),
                                  ("y", 0.0, fE * M_Ey)):
            for sign in (1.0, -1.0):
                label = name.replace("+-", "+" if sign > 0 else "-")
                combos.append({
                    "name": label,
                    "direction": direction,
                    "Pu_kN": Pu_grav + sign * fE * P_E_kN,
                    # the frame moment magnitude does not reverse with the
                    # sign of the lateral action -- see module docstring
                    "Mux_kNm": abs(Mu_grav) + Mx,
                    "Muy_kNm": My,
                })

    gov_comp = max(combos, key=lambda c: c["Pu_kN"])
    gov_up = min(combos, key=lambda c: c["Pu_kN"])
    return {
        "combos": combos,
        "Pu_max_kN": gov_comp["Pu_kN"],
        "Pu_min_kN": gov_up["Pu_kN"],
        "Mux_max_kNm": max(c["Mux_kNm"] for c in combos),
        "Muy_max_kNm": max(c["Muy_kNm"] for c in combos),
        "uplift_governs": gov_up["Pu_kN"] < 0.0,
        "governing_compression": gov_comp,
        "governing_uplift": gov_up,
    }


def overturning_moment_kNm(storey_forces: list, lateral_governing: str,
                           wind_base_shear_kN: float,
                           h_total_m: float) -> float:
    """Base overturning moment (kNm) for the governing lateral case.

    Seismic: ``sum(Qi * hi)`` over the equivalent-static storey forces
    (``loads.SeismicResult.storey_forces`` rows are ``(level, Wi, hi, Qi)``).

    Wind: the frame shear here is derived from a single uniform design
    pressure over the full elevation, so its resultant acts at the centroid
    of that pressure block, i.e. mid-height — ``V * h/2``. This is an
    approximation consistent with the uniform-pressure model already used
    to derive the base shear, not a code clause; a real design would
    integrate the height-varying ``pz``.
    """
    if lateral_governing == "wind":
        return wind_base_shear_kN * h_total_m / 2.0
    return sum(Qi * hi for (_lvl, _Wi, hi, Qi) in storey_forces)


def overturning_axial_kN(OTM_kNm: float, lever_arm_m: float,
                         n_columns_per_extreme_line: int) -> float:
    """Per-column axial increment from the overturning couple (kN).

    Portal-method idealisation: the base overturning moment is resisted by
    a force couple between the two extreme column lines, separated by
    ``lever_arm_m``. The couple force ``OTM / lever_arm`` is shared equally
    among the columns on each extreme line, giving

        dP = OTM / (lever_arm * n_columns_per_extreme_line)

    added as compression on the leeward line and subtracted (relief, then
    net tension) on the windward line. Interior columns sit near the
    neutral axis of overturning and are taken as unaffected — the standard
    portal-method treatment.
    """
    if lever_arm_m <= 0 or n_columns_per_extreme_line <= 0:
        return 0.0
    return OTM_kNm / (lever_arm_m * n_columns_per_extreme_line)
