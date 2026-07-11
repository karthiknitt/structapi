---
description: LSM design procedure for isolated and combined footings per IS 456:2000 cl 34, 31.6 + IS 6403 bearing capacity — load before any foundation design.
---

# Footing Design — LSM (IS 456:2000 cl 34, 31.6; IS 6403)

## Procedure (isolated)
1. **SBC**: given, or from `safe_bearing_capacity` (IS 6403: qu = cNc·s·d +
   q(Nq−1)·s·d + 0.5γBNγ·s·d·W′, FOS 2.5).
2. **Plan sizing (service)**: A ≈ 1.1P/SBC; with moment e = M/P,
   q = P/LB(1 ± 6e/L): q_max ≤ SBC, q_min ≥ 0.
3. **Depth**: two-way (punching) shear at d/2 perimeter usually governs —
   τv ≤ ks·0.25√fck (cl 31.6.3); one-way shear at d from face vs τc (Table 19).
4. **Flexure** at column face (cl 34.2.3.2), Annex G steel; min 0.12% bD;
   rectangular footings: short-direction central band gets 2/(β+1) share.
5. **Development length** (cl 26.2) and **column-base bearing** (cl 34.4,
   0.45fck√(A1/A2) ≤ 2) — else dowels.

## Procedure (combined, 2 columns)
Centroid of footing must coincide with load resultant → uniform pressure.
Longitudinal direction acts as a beam (upward UDL + column point loads):
hogging between columns (top steel governs), stirrups per cl 40.4; transverse
bands under each column (width = col + 0.75d each side); punching per column.

## Library calls (run_python; cwd = /workspace)
```python
import dataclasses, json, os
from iscodes.design.footing import (safe_bearing_capacity,
                                    design_isolated_footing,
                                    design_combined_footing)
from iscodes.plotting import plot_pressure_diagram, plot_sfd_bmd

r = design_isolated_footing(P_service_kN=1000, M_service_kNm=80, sbc_kpa=200,
                            col_b_mm=400, col_D_mm=400, fck=25, fy=500)
d = dataclasses.asdict(r)
print(json.dumps({"ok": d["ok"], "checks": d["checks"],
                  **{k: v for k, v in d["data"].items()
                     if not isinstance(v, dict)}}, indent=1, default=str))
os.makedirs("out", exist_ok=True)
plot_pressure_diagram(d["data"]["L_m"], d["data"]["q_min_service_kPa"],
                      d["data"]["q_max_service_kPa"],
                      "Isolated footing base pressure", "out/pressure.png")

c = design_combined_footing(P1_kN=800, P2_kN=1200, spacing_m=4.0,
                            sbc_kpa=200, col1_mm=400, col2_mm=400,
                            fck=25, fy=500)
plot_sfd_bmd(c["x"], c["V"], c["M"], "Combined footing — longitudinal",
             "out/combined_sfd_bmd.png", tension_side=True)
```
(Check `plot_pressure_diagram`'s exact signature with `help()` first if
unsure.) Iterate until `ok` is True; export every PNG.
