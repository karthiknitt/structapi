---
description: Load computation procedure per IS 875 Pt 1-3 (2015 wind) and IS 1893:2016 equivalent static seismic — load before computing any loads or combinations.
---

# Loads — IS 875 & IS 1893 (equivalent static)

## Procedure
1. **Gravity (IS 875-1/2):** unit weights from `tables.UNIT_WEIGHTS` (RCC 25
   kN/m³, water 9.81); imposed loads from `tables.IMPOSED_LOADS` by occupancy;
   column LL reduction per floors carried (`tables.ll_reduction_pct`).
2. **Wind (IS 875-3:2015 cl 6-7):** Vz = Vb·k1·k2·k3·k4; pz = 0.6Vz²;
   pd = Kd·Ka·Kc·pz ≥ 0.7pz. Vb from `tables.BASIC_WIND_SPEED[city]` or user.
3. **Seismic (IS 1893:2016 cl 7.6):** Ta = 0.075h^0.75 (RC bare frame);
   Ah = (Z/2)(Sa/g)/(R/I); VB = Ah·W with the cl 7.2.2 minimum floor;
   Qi ∝ Wi·hi². Seismic weight: DL + 25%/50% IL (Table 10), roof IL nil.
4. **Combinations (IS 456 Table 18):** run every combo, both signs of lateral;
   report ranked list. Seismic detailing note: zones III-V need SMRF/IS 13920.

## Library calls (run_python; cwd = /workspace)
```python
from iscodes import loads, tables
import json

# wind
w = loads.wind_pressure(Vb=tables.BASIC_WIND_SPEED["chennai"], height=15,
                        terrain_category=3)
print("wind:", w.Vz, w.pz, w.pd, w.factors)

# seismic: storey weights (kN) and heights (m), bottom-up
r = loads.base_shear([2000, 2000, 2000, 1800], [3.2, 6.4, 9.6, 12.8],
                     zone="III", soil="medium", I=1.0, R=5.0)
print("VB:", r.VB, "Ah:", r.Ah, "Ta:", r.Ta)
print("storey forces:", r.storey_forces)

# combinations of load EFFECTS (same units in = out)
combos = loads.combinations(DL=150, IL=80, WL=45, EL=60)
print(json.dumps(combos[:5], indent=1, default=str))
```
Helpers: `loads.slab_dead_load(t_m)`, `loads.wall_load_per_m(t, h)`,
`loads.imposed_load("office")`, `loads.seismic_weight(...)`.
