# python/iscodes — deterministic IS-code engine

Indeterminate structural design per Indian Standards: numpy + matplotlib + reportlab, 94 unit tests. NO LLM in the calculation path — agents decide *what* to design; this library decides *what the numbers are*.

## Rules

- **No hallucination boundary.** Agents route and sequence; this engine computes. Every check must trace to an IS clause (reported in `assumptions` and clause summaries).
- **Code table values transcribed from standards.** `tables.py` is versioned per code edition (IS 456:2000, SP 16, IS 875 Parts 1-3, IS 1893:2016, IS 13920:2016, IS 3370 Parts 1-4, IS 10262:2019, IS 6403:1981). Verify against official BIS copies before professional use — a disclaimer is embedded in every report.
- **Sign conventions for output figures:** SFD/BMD use Indian convention — BMD plotted on tension side; sagging positive. Verified in `plotting.py` tests.
- **Module map:** `analysis/` (beam bending), `design/` (beam, column, slab, footing, tank), `loads.py` (dead/imposed/wind/seismic), `materials.py` (concrete/steel grades), `tables.py` (code coefficients), `detailing.py` (rebar spacing/laps), `serviceability.py` (deflection/crack width), `pdfreport.py` (clause-referenced PDFs), `plotting.py` (SFD/BMD/P-M diagrams).

## Gotchas

- Isolated footing method (IS 6403 Annex D) is conservative — assume rigid; combined footings run a first-order stiffness matrix. Irregular grids set `confident: false`.
- Water-tank wall thickness governed by crack width (IS 3370 Table 10), not flexure — changes can flip the design when only checking flexure.
