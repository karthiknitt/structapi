"""Concrete mix proportioning per IS 10262:2019.

Follows the "design mix by absolute volume" method (IS 10262:2019 sec 4-5,
Annex A). Clause references noted inline. This module produces a first-trial
mix; actual trial mixes and adjustments per cl 4.3/Annex A are still required
before use on a real project (see package DISCLAIMER).

Units: kg, mm, MPa, kg/m3 unless noted.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .. import tables

#: Internal strength-based w/c estimate for OPC43, small lookup table keyed by
#: target strength f_target (MPa) -> w/c. Interpolated between listed points.
#: (Simplified stand-in for the fck-vs-wc curves in IS 10262:2019 Fig 1 / SP 23.)
_WC_STRENGTH_TABLE = [
    (30.0, 0.50),
    (35.0, 0.47),
    (40.0, 0.44),
    (45.0, 0.40),
    (50.0, 0.36),
]


def _wc_strength_based(f_target: float) -> float:
    pts = _WC_STRENGTH_TABLE
    if f_target <= pts[0][0]:
        return pts[0][1]
    if f_target >= pts[-1][0]:
        return pts[-1][1]
    for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
        if x1 <= f_target <= x2:
            return y1 + (y2 - y1) * (f_target - x1) / (x2 - x1)
    return pts[-1][1]


@dataclass
class MixDesign:
    ok: bool
    checks: list
    data: dict = field(default_factory=dict)


def design_mix(fck: float, exposure: str = "moderate", msa_mm: int = 20,
               slump_mm: float = 75, fa_zone: str = "II",
               sg_cement: float = 3.15, sg_ca: float = 2.74,
               sg_fa: float = 2.65, sg_admix: float = 1.145,
               admixture: str | None = "superplasticizer",
               water_reduction_pct: float = 20.0,
               cement_type: str = "OPC43",
               pumpable: bool = False) -> MixDesign:
    """Design a concrete mix per IS 10262:2019.

    Returns a MixDesign with .ok, .checks (list of (name, ok)), and .data
    holding target strength, w/c values, water/cement/aggregate quantities,
    mix ratio, and trial-mix guidance.
    """
    checks: list = []
    data: dict = {}
    exp = tables.EXPOSURE[exposure]

    # --- Step 1: target mean strength, IS 10262:2019 cl 4.2 -----------------
    S = tables.mix_std_deviation(fck)
    X = tables.mix_x_factor(fck)
    f_target = max(fck + 1.65 * S, fck + X)
    data["S"] = S
    data["X"] = X
    data["f_target"] = f_target

    # --- Step 2: water-cement ratio, cl 4.2/5.4; durability Table 5 ---------
    wc_strength = _wc_strength_based(f_target)
    wc_durability = exp["max_wc"]
    wc_governing = min(wc_strength, wc_durability)
    governs = "durability" if wc_durability <= wc_strength else "strength"
    data["wc_strength"] = wc_strength
    data["wc_durability"] = wc_durability
    data["wc_governing"] = wc_governing
    data["wc_governs"] = governs

    # --- Step 3: water content, cl 4.3 / Table 4 -----------------------------
    water = float(tables.WATER_CONTENT[msa_mm])
    # +3% per 25 mm slump above the 50 mm base (Table 4 is for 25-50mm slump)
    slump_steps = max(0.0, (slump_mm - 50.0) / 25.0)
    water *= (1 + 0.03 * slump_steps)
    # aggregate shape adjustment (assume angular unless noted elsewhere)
    water += tables.WATER_ADJ_SHAPE.get("angular", 0)

    water_before_admix = water
    admix_reduction_pct = 0.0
    if admixture:
        cap = 23.0 if "super" in admixture.lower() else 10.0
        admix_reduction_pct = min(water_reduction_pct, cap)
        water *= (1 - admix_reduction_pct / 100.0)
    data["water_before_admixture"] = water_before_admix
    data["admix_reduction_pct"] = admix_reduction_pct
    data["water"] = water

    # --- Step 4: cement content, cl 4.4/4.5; IS 456 cl 8.2.4.2 --------------
    cement = water / wc_governing
    wc_actual = wc_governing
    clamped = False
    if cement < exp["min_cement"]:
        cement = exp["min_cement"]
        wc_actual = water / cement
        clamped = True
    if cement > tables.MAX_CEMENT:
        cement = tables.MAX_CEMENT
        wc_actual = water / cement
        clamped = True
    data["cement"] = cement
    data["wc_actual"] = wc_actual
    data["cement_clamped"] = clamped

    # --- Step 5: coarse aggregate volume fraction, cl 4.6 / Table 5 --------
    f_ca_base = tables.CA_VOLUME[msa_mm][fa_zone]
    wc_dev = wc_actual - 0.50
    # +0.01 per -0.05 wc deviation from 0.50 (i.e. lower wc -> more CA)
    f_ca = f_ca_base - (wc_dev / 0.05) * 0.01
    if pumpable:
        f_ca *= 0.90
    data["f_ca_base"] = f_ca_base
    data["f_ca"] = f_ca

    # --- Step 6: absolute volume computation, cl 4.7/Annex A ---------------
    air_pct = tables.AIR_CONTENT[msa_mm]
    admix_mass = cement * 0.01 if (admixture and "super" in (admixture or "").lower()) else 0.0
    v_air = air_pct / 100.0
    v_cement = cement / (sg_cement * 1000.0)
    v_water = water / 1000.0
    v_admix = admix_mass / (sg_admix * 1000.0)
    v_agg = 1.0 - v_air - v_cement - v_water - v_admix
    data["air_pct"] = air_pct
    data["admix_kg"] = admix_mass
    data["v_air"] = v_air
    data["v_cement"] = v_cement
    data["v_water"] = v_water
    data["v_admix"] = v_admix
    data["v_agg"] = v_agg

    ca_mass = v_agg * f_ca * sg_ca * 1000.0
    fa_mass = v_agg * (1 - f_ca) * sg_fa * 1000.0
    data["ca"] = ca_mass
    data["fa"] = fa_mass

    v_ca = ca_mass / (sg_ca * 1000.0)
    v_fa = fa_mass / (sg_fa * 1000.0)
    volume_sum = v_air + v_cement + v_water + v_admix + v_ca + v_fa
    data["volume_sum"] = volume_sum

    # --- Step 7: reporting ---------------------------------------------------
    ratio = f"1 : {fa_mass / cement:.2f} : {ca_mass / cement:.2f} : {wc_actual:.2f}"
    data["mix_ratio"] = ratio
    data["trial_wc_range"] = (wc_actual - 0.05, wc_actual + 0.05)
    data["quantities_per_m3"] = {
        "cement_kg": cement,
        "water_kg": water,
        "fa_kg": fa_mass,
        "ca_kg": ca_mass,
        "admixture_kg": admix_mass,
    }

    checks.append(("absolute volumes sum to 1.0 (cl 4.7)",
                   abs(volume_sum - 1.0) < 1e-3))
    checks.append(("cement >= exposure minimum (IS 456 Table 5)",
                   cement >= exp["min_cement"] - 1e-6))
    checks.append(("cement <= 450 kg/m3 (IS 456 cl 8.2.4.2)",
                   cement <= tables.MAX_CEMENT + 1e-6))
    checks.append(("w/c <= exposure maximum (IS 456 Table 5)",
                   wc_actual <= exp["max_wc"] + 1e-6))
    checks.append((f"grade fck={fck} >= min grade for {exposure} exposure "
                   f"({exp['min_fck']}) (IS 456 Table 5)",
                   fck >= exp["min_fck"]))
    checks.append(("coarse aggregate fraction in (0,1)", 0.0 < f_ca < 1.0))

    ok = all(v for _, v in checks)
    return MixDesign(ok, checks, data)
