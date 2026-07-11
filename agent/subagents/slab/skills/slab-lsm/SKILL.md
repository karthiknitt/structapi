---
description: LSM design procedure for one-way and two-way slabs per IS 456:2000 Table 26 / Annex D — load before any slab design. Includes Table 26 case selection guide.
---

# Slab Design — LSM (IS 456:2000 cl 24, Table 26, Annex D, cl 26.5.2)

## Case selection (Table 26, corners held)
1 interior (4 edges cont) · 2 one short edge disc · 3 one long edge disc ·
4 two adjacent disc (typical corner panel) · 5 two short disc · 6 two long
disc · 7 three disc (one long cont) · 8 three disc (one short cont) ·
9 four edges discontinuous. Corners NOT held → Annex D-2 (simply supported).

## Procedure
- One-way when ly/lx > 2: 1 m strip as beam; Mu = w_u·lx²/8 (SS).
- Two-way: Mx = αx·w_u·lx², My = αy·w_u·lx² (both use lx²; D-1.1); negative
  α at continuous edges, positive at midspan.
- Min steel 0.12% bD (HYSD, cl 26.5.2.1); spacing ≤ min(3d, 300) main,
  min(5d, 450) distribution; max bar dia ≤ D/8.
- Shear: τv ≤ k·τc with k from cl 40.2.1.1 (rarely governs).
- Deflection: cl 24.1 span/depth (auto-thickened by the library).
- Torsion steel at discontinuous corners: 0.75·Ast_mid over lx/5, 4 layers
  (D-1.8). Load to beams: trapezoid/triangle (cl 24.5).

## Library calls (run_python; cwd = /workspace)
```python
import json
from iscodes.design.slab import design_one_way_slab, design_two_way_slab

r = design_two_way_slab(lx_m=4.0, ly_m=5.0, w_dl=1.5, w_il=3.0,
                        fck=25, fy=500, case=4, corners_held=True)
# w_dl EXCLUDES self weight (library adds it), includes finishes
print(json.dumps(r, indent=1, default=str))

o = design_one_way_slab(lx_m=3.0, w_dl=1.5, w_il=2.0, fck=25, fy=500,
                        support="continuous")
print(json.dumps(o, indent=1, default=str))
```
`r["strips"]` has per-strip Mu, Ast and bar callouts; `r["torsion_note"]`
gives D-1.8 corner steel. Iterate only if `ok` is False with a user-fixed D.
