---
description: Limit State Method design procedure for RC beams per IS 456:2000 — load this before designing any beam. Includes the exact iscodes library calls.
---

# RC Beam Design — Limit State Method (IS 456:2000)

## Procedure

1. **Loads & analysis (cl 22, 36.4)**
   Factored UDL `w_u = 1.5(DL + IL)` for the gravity case (all Table 18 combos
   via `iscodes.loads.combinations` when wind/seismic effects are given).
   Closed-form SFD/BMD: `iscodes.analysis.beam.analyze` (simply supported,
   cantilever, fixed) or `continuous_moments` (IS 456 Table 12/13 coefficients,
   valid for ≥3 spans differing <15% under UDL).

2. **Trial section** — span/depth from cl 23.2.1 basics (SS 20, cantilever 7,
   continuous 26); width ≥ 200 mm if seismic (IS 13920 cl 6.1).

3. **Flexure (cl 38, Annex G)** — `d = D − cover − stirrup − bar/2`.
   If `Mu ≤ Mu_lim = Q·fck·b·d²` (Q from `tables.mu_lim_factor(fy)`; 0.138 for
   Fe415, 0.133 for Fe500): singly reinforced,
   `Ast = 0.5(fck/fy)(1 − √(1 − 4.6Mu/(fck·b·d²)))·b·d` (Annex G-1.1b).
   Else doubly reinforced: `Mu2 = Mu − Mu_lim`,
   `Asc = Mu2/((fsc − 0.446fck)(d − d'))` with fsc from SP 16 Table F.

4. **Shear (cl 40)** — `τv = Vu/(b·d)`; abort if > τc,max (Table 20).
   τc from Table 19 at `pt = 100·Ast/(b·d)`. Stirrups:
   `sv = 0.87·fy·Asv·d/Vus`, `Vus = Vu − τc·b·d`; minimum stirrups per
   cl 26.5.1.6 when τv ≤ τc; spacing ≤ min(0.75d, 300).

5. **Deflection (cl 23.2.1)** — actual L/d ≤ basic × kt(fs, pt) × kc(pc),
   fs = 0.58·fy·(Ast req/prov).

6. **Detailing (cl 26)** — min steel 0.85bd/fy; max 0.04bD; side-face 0.1% when
   D > 750; development length Ld at supports (cl 26.2); curtailment cl 26.2.3.
   Seismic (IS 13920): pt ≤ 2.5%, min 2 bars top+bottom throughout, 2d hoop
   zone at ends with spacing ≤ min(d/4, 8db, 100).

## Library calls (run via run_python; cwd = /workspace)

```python
from iscodes.design.beam import design_beam
from iscodes.plotting import plot_sfd_bmd
import json, os

r = design_beam(span_m=6.0, w_dl_kn_m=15.0, w_il_kn_m=10.0,
                b=300, D=550, fck=25, fy=500,
                support="ss", seismic=False)
os.makedirs("out", exist_ok=True)
plot_sfd_bmd(r["analysis"]["x"], r["analysis"]["V"], r["analysis"]["M"],
             "Beam 300x550 — 6 m SS", "out/sfd_bmd.png", tension_side=True)
print(json.dumps({k: v for k, v in r.items() if k != "analysis"},
                 default=str, indent=1))
```

Checks come back as `r["checks"]` = list of (clause-named check, pass/fail).
Iterate the section until `r["ok"]` is True. Export `out/sfd_bmd.png` with the
`export_artifact` tool. Cite clauses exactly as named in the checks.
