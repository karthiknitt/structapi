---
description: Design procedure for RC water tanks per IS 3370-1/2:2021 (crack-width-governed LSM) and IS 3370-4 coefficients — load before any tank design.
---

# Water Tank Design — IS 3370 (2021)

## Design basis (IS 3370-2:2021)
- Limit state design + MANDATORY crack-width serviceability check
  (WSM was deleted in the 2021 revision).
- Crack limits: **0.1 mm** faces in contact with liquid (or airspace above);
  0.2 mm other faces. Deemed-to-satisfy fallback: service steel stress
  ≤ 130 MPa (flexure) / 100 MPa (direct tension) near the liquid face.
- Materials: min M30, max w/c 0.45, cover ≥ 45 mm liquid face.
- Min steel: 0.35% (HYSD) of the surface zone (t/2 per face, ≤ 250 mm) each
  face, each direction.

## Member forces
- **Circular** (IS 3370-4): hoop T = coeff·γw·H·D/2, wall moment =
  coeff·γw·H³, coefficients keyed by H²/(D·t) — hinged or fixed base.
- **Rectangular**: L/H ≥ 2 walls act as vertical cantilevers
  (M = γwH³/6); shorter panels span horizontally (corner M ≈ pL²/12) with
  direct tension from the adjacent wall's reaction — design for M + T.
- Load case: tank FULL with no external backfill (test condition).

## Library calls (run_python; cwd = /workspace)
```python
import json
from iscodes.design.tank import (circular_tank_forces,
                                 rectangular_wall_forces,
                                 design_tank_wall_section)

f = circular_tank_forces(H=4.0, D=10.0, t=0.20, base="hinged")
print("hoop kN/m:", f.hoop_max_kN_per_m, "M kNm/m:", f.moment_kNm_per_m)

w = rectangular_wall_forces(H=3.0, L=8.0, B=4.0)
print(json.dumps(w, indent=1, default=str))

s = design_tank_wall_section(M_service_kNm=45, T_service_kN=60, t_mm=300,
                             fck=30, fy=500, bar_dia=16, spacing_mm=125,
                             liquid_face=True)
print(json.dumps(s, indent=1, default=str))
```
Iterate thickness/steel until crack width ≤ limit AND ULS check passes.
Hoop steel for circular tanks: Ast = T_service·1e3 / 130 (deemed stress) per
metre height band, then verify with `design_tank_wall_section` style checks.
