"""Load computation per IS 875 Parts 1-3 and IS 1893 Part 1:2016.

Units here: kN, m, kN/m2, m/s.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import tables


# ---------------------------------------------------------------------------
# Load combinations — IS 456 Table 18
# ---------------------------------------------------------------------------

def combinations(DL: float, IL: float = 0.0, WL: float = 0.0, EL: float = 0.0,
                 limit_state: str = "ULS") -> list[dict]:
    """Factored effects for every IS 456 Table 18 combination.

    Pass characteristic load *effects* (same units in = same units out).
    WL and EL are alternatives; both are run through the lateral-load slot.
    For seismic, IS 1893 cl 6.3 requires +/-EL (covered by the +/- combos).
    Returns list of {name, value, factors} sorted by |value| descending.
    """
    combos = tables.ULS_COMBOS if limit_state.upper() == "ULS" else tables.SLS_COMBOS
    out = []
    for lateral_name, lateral in (("WL", WL), ("EL", EL)):
        if lateral == 0.0 and lateral_name == "EL":
            continue
        for c in combos:
            if c["WL"] == 0.0 and lateral_name == "EL":
                continue  # gravity-only combos emitted once (under WL pass)
            value = c["DL"] * DL + c["IL"] * IL + c["WL"] * lateral
            out.append({"name": c["name"].replace("WL", lateral_name),
                        "value": value, "factors": c})
    # dedupe gravity-only combo if WL == 0
    seen, unique = set(), []
    for c in out:
        if c["name"] not in seen:
            seen.add(c["name"])
            unique.append(c)
    return sorted(unique, key=lambda c: abs(c["value"]), reverse=True)


def governing(DL: float, IL: float = 0.0, WL: float = 0.0, EL: float = 0.0) -> dict:
    """The single worst ULS combination."""
    return combinations(DL, IL, WL, EL)[0]


# ---------------------------------------------------------------------------
# Wind — IS 875 Part 3:2015
# ---------------------------------------------------------------------------

@dataclass
class WindResult:
    Vb: float
    Vz: float
    pz: float      # kN/m2
    pd: float      # kN/m2 design pressure
    factors: dict = field(default_factory=dict)


def wind_pressure(Vb: float, height: float, terrain_category: int = 2,
                  k1: float = 1.0, k3: float = 1.0, k4: float = 1.0,
                  Kd: float = 0.9, Ka: float = 1.0, Kc: float = 1.0) -> WindResult:
    """Design wind pressure at a height. IS 875-3:2015 cl 6.

    Vz = Vb k1 k2 k3 k4 (cl 6.3);  pz = 0.6 Vz^2 (N/m2, cl 7.2);
    pd = Kd Ka Kc pz, but pd >= 0.7 pz (cl 7.2 note).
    """
    k2 = tables.k2(height, terrain_category)
    Vz = Vb * k1 * k2 * k3 * k4
    pz = 0.6 * Vz ** 2 / 1000.0  # kN/m2
    pd = max(Kd * Ka * Kc * pz, 0.7 * pz)
    return WindResult(Vb, Vz, pz, pd,
                      {"k1": k1, "k2": k2, "k3": k3, "k4": k4,
                       "Kd": Kd, "Ka": Ka, "Kc": Kc})


def wind_force_on_frame(pd: float, Cf: float, Ae: float) -> float:
    """F = Cf * Ae * pd (kN). cl 7.4."""
    return Cf * Ae * pd


def wind_pressure_on_cladding(pd: float, Cpe: float, Cpi: float, A: float) -> float:
    """F = (Cpe - Cpi) * A * pd (kN). cl 7.3."""
    return (Cpe - Cpi) * A * pd


# ---------------------------------------------------------------------------
# Seismic — IS 1893 Part 1:2016 equivalent static method (cl 7.6)
# ---------------------------------------------------------------------------

@dataclass
class SeismicResult:
    Ta: float
    Sa_g: float
    Ah: float
    VB: float            # base shear, kN
    storey_forces: list  # [(level, Wi, hi, Qi)]
    params: dict


def fundamental_period(h: float, frame: str = "rc", d: float | None = None) -> float:
    """Approximate Ta (s). cl 7.6.2.

    rc bare frame: 0.075 h^0.75; steel: 0.080 h^0.75;
    with masonry infill: 0.09 h / sqrt(d) (d = base dimension in load dirn, m).
    """
    f = frame.lower()
    if f in ("infill", "masonry_infill"):
        if not d:
            raise ValueError("infill formula needs base dimension d")
        return 0.09 * h / d ** 0.5
    if f in ("steel",):
        return 0.080 * h ** 0.75
    return 0.075 * h ** 0.75


def base_shear(storey_weights: list[float], storey_heights: list[float],
               zone: str, soil: str = "medium", I: float = 1.0, R: float = 5.0,
               frame: str = "rc", base_dim: float | None = None) -> SeismicResult:
    """Equivalent static base shear + vertical distribution.

    storey_weights: seismic weight Wi per floor (kN), bottom-up.
    storey_heights: height hi of each floor above base (m), bottom-up.
    """
    if len(storey_weights) != len(storey_heights):
        raise ValueError("weights and heights must align")
    h = max(storey_heights)
    Z = tables.ZONE_FACTOR[zone.upper()]
    Ta = fundamental_period(h, frame, base_dim)
    sa = tables.sa_by_g(Ta, soil)
    Ah = (Z / 2.0) * sa / (R / I)
    W = sum(storey_weights)
    VB = Ah * W
    # minimum design base shear, cl 7.2.2
    VB_min = tables.MIN_BASE_SHEAR_PCT[zone.upper()] / 100.0 * W
    VB = max(VB, VB_min)
    # vertical distribution Qi = VB * Wi hi^2 / sum(Wj hj^2), cl 7.6.3
    denom = sum(w * hh ** 2 for w, hh in zip(storey_weights, storey_heights))
    forces = [(i + 1, w, hh, VB * w * hh ** 2 / denom)
              for i, (w, hh) in enumerate(zip(storey_weights, storey_heights))]
    return SeismicResult(Ta, sa, Ah, VB, forces,
                         {"Z": Z, "I": I, "R": R, "soil": soil, "W": W,
                          "VB_min": VB_min})


def seismic_weight(dead_kn: float, imposed_kn: float, il_intensity_kn_m2: float,
                   is_roof: bool = False) -> float:
    """Seismic weight of a floor. Table 10: roof IL ignored; else 25%/50%."""
    if is_roof:
        return dead_kn
    return dead_kn + tables.seismic_ll_fraction(il_intensity_kn_m2) * imposed_kn


# ---------------------------------------------------------------------------
# Gravity takedown helpers — IS 875 Parts 1-2
# ---------------------------------------------------------------------------

def slab_dead_load(thickness_m: float, finish_kn_m2: float | None = None) -> float:
    """Self weight + finishes, kN/m2."""
    if finish_kn_m2 is None:
        finish_kn_m2 = tables.UNIT_WEIGHTS["floor_finish_kn_m2"]
    return thickness_m * tables.UNIT_WEIGHTS["rcc"] + finish_kn_m2


def wall_load_per_m(thickness_m: float, height_m: float,
                    material: str = "brick_masonry",
                    plastered_both: bool = True) -> float:
    """Line load of a wall on a beam, kN/m."""
    w = thickness_m * height_m * tables.UNIT_WEIGHTS[material]
    if plastered_both:
        w += 2 * tables.UNIT_WEIGHTS["plaster_12mm_kn_m2"] * height_m
    return w


def imposed_load(occupancy: str) -> float:
    """Characteristic imposed load, kN/m2. IS 875-2."""
    try:
        return tables.IMPOSED_LOADS[occupancy]
    except KeyError:
        raise KeyError(
            f"unknown occupancy '{occupancy}'; known: {sorted(tables.IMPOSED_LOADS)}")
