---
description: IS 10262:2019 concrete mix proportioning pipeline (target strength, w/c, water, cement, aggregates by absolute volume) — load before any mix design.
---

# Concrete Mix Design — IS 10262:2019

## Pipeline (cl 4-5, Annex A)
1. Target strength f'ck = max(fck + 1.65·S, fck + X); S = 4.0 (M20-25) /
   5.0 (M30+); X = 5.5 (M20-45).
2. w/c: strength-based estimate capped by durability (IS 456 Table 5 —
   moderate 0.50/M25/300kg; severe 0.45/M30/320kg). Record which governs.
3. Water: Table 4 base (186 kg for 20 mm, 25-50 slump); +3% per 25 mm extra
   slump; −up to 23% with superplasticizer.
4. Cement = water/(w/c), clamped to [exposure minimum, 450] (IS 456
   cl 8.2.4.2).
5. Coarse-aggregate fraction: Table 5 by MSA + FA zone (0.62 for 20 mm/Zone
   II at w/c 0.50), +0.01 per −0.05 w/c; −10% if pumpable.
6. Absolute volumes close to 1.000 m³ → CA/FA masses.

## Library call (run_python; cwd = /workspace)
```python
import json
from iscodes.design.mix import design_mix

r = design_mix(30, exposure="severe", msa_mm=20, slump_mm=100,
               fa_zone="II", admixture="superplasticizer",
               water_reduction_pct=20)
print(json.dumps({"ok": r.ok, "checks": r.checks, **r.data},
                 indent=1, default=str))
```
Key outputs: `data["quantities_per_m3"]`, `data["mix_ratio"]`,
`data["wc_governs"]`, `data["trial_wc_range"]`. Present quantities as a
table; note aggregate moisture corrections are site-specific.
