---
description: LSM design procedure for RC columns per IS 456:2000 cl 25/39 (uniaxial/biaxial, slender) + IS 13920 detailing — load before any column design.
---

# RC Column Design — LSM (IS 456:2000 cl 25, 39, 26.5.3; IS 13920)

## Procedure
1. **Classify (cl 25.1.2)**: short if lex/D ≤ 12 and ley/b ≤ 12; slenderness
   ≤ 60 (cl 25.3). Min eccentricity e_min = max(L/500 + D/30, 20) each axis
   (cl 25.4) — moments never below Pu·e_min.
2. **Slender columns (cl 39.7)**: additional moment Ma = (PuD/2000)(le/D)²
   with reduction factor k = (Puz−Pu)/(Puz−Pb) ≤ 1.
3. **Capacity**: uniaxial Mu1 at the applied Pu from the strain-compatibility
   interaction curve (equivalent to SP 16 charts); **biaxial (cl 39.6)**:
   (Mux/Mux1)^αn + (Muy/Muy1)^αn ≤ 1, αn from Pu/Puz
   (Puz = 0.45fck·Ac + 0.75fy·Asc).
4. **Detailing (cl 26.5.3)**: steel 0.8-6% (≤4% practical), ≥4 bars ≥12 dia;
   ties ≥ max(db/4, 6) at ≤ min(least dim, 16db, 300).
5. **Seismic (IS 13920)**: min dim 300 (>2 storeys); confinement zone lo =
   max(D, hc/6, 450) with hoops ≤ min(6db, 100); strong column ΣMc ≥ 1.4ΣMb.

## Library calls (run_python; cwd = /workspace)
```python
import json, os
import numpy as np
from iscodes.design.column import (design_column, ColumnSection,
                                   rect_bar_layout, interaction_curve)
from iscodes.plotting import plot_pm_interaction

r = design_column(b=450, D=450, fck=25, fy=415,
                  Pu_kN=1500, Mux_kNm=80, Muy_kNm=40,
                  L_unsupported_mm=3000, n_bars=8, bar_dia=25,
                  seismic=False)
print(json.dumps({"ok": r.ok, "checks": r.checks, **r.data},
                 indent=1, default=str))

# P-M diagram about the x axis with the design point
sec = ColumnSection(450, 450, 25, 415, rect_bar_layout(450, 450, 60, 8, 25))
curve = interaction_curve(sec) / 1e3          # N,N.mm -> kN, kN.m/1000
curve[:, 1] /= 1e3
os.makedirs("out", exist_ok=True)
plot_pm_interaction(curve, [(r.data["Mux_design_kNm"], 1500)],
                    "Column 450x450 P-M (x axis)", "out/pm_x.png")
```
Iterate steel/section until `r.ok`. Export PNGs with `export_artifact`.
