---
description: Design procedure for underground sumps per IS 3370 (2021) — dual load cases (full/no-backfill, empty/backfilled), at-rest earth pressure, groundwater, uplift FOS 1.2. Load before any sump design.
---

# Underground Sump Design — IS 3370 (2021) + earth/water pressures

## Load cases (design for the ENVELOPE)
- **Case A — sump full, no backfill** (test condition): internal water only,
  p = γw·H; cantilever wall M = γwH³/6 (liquid face tension inside).
- **Case B — sump empty, backfilled**: at-rest earth K0 = 1 − sinφ (rigid
  walls), surcharge K0·q, submerged soil below the water table
  (γsat − γw), PLUS full hydrostatic groundwater. Tension on the earth face.
- **Uplift (flotation)**: empty sump, highest water table:
  FOS = W_structure/U ≥ 1.2, U = γw·hw·plan area. Fix with thicker base,
  extended heel (soil weight on heel counts), or anchors.

## Section design
Crack width governs (0.1 mm inside faces, 0.2 mm earth face); min steel
0.35% surface zone each face; M30, cover 45 (liquid) / 50 (earth face).

## Library calls (run_python; cwd = /workspace)
```python
import json
from iscodes.design.tank import (sump_wall_pressures, uplift_check,
                                 design_tank_wall_section)

p = sump_wall_pressures(H=3.5, gamma_soil=18, phi_deg=30, surcharge=10,
                        water_table_depth=1.0, gamma_sat=20)
print(json.dumps(p, indent=1, default=str))
# governing_moment (kNm/m) -> wall section design

u = uplift_check(plan_area=48.0, structure_weight_kN=1450,
                 water_table_above_base=2.5)
print(json.dumps(u, indent=1))

s = design_tank_wall_section(M_service_kNm=p["governing_moment"],
                             T_service_kN=0, t_mm=300, fck=30, fy=500,
                             bar_dia=16, spacing_mm=125, liquid_face=True)
print(json.dumps(s, indent=1, default=str))
```
Check BOTH faces: Case A puts tension on the inside (liquid face, 0.1 mm);
Case B on the outside (0.2 mm). Iterate thickness/steel until both pass and
uplift FOS ≥ 1.2.
