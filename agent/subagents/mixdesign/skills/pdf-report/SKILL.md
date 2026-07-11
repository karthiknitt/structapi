---
description: Produce a PDF design report with SFD/BMD (or other) PNG figures embedded inline — load when the user asks for a PDF, a report file, or a printable deliverable.
---

# PDF design report (with inline figures)

Generate the PNGs FIRST (plots into `/workspace/out/`), then build the PDF
with `iscodes.pdfreport` (reportlab is preinstalled in the sandbox), then
export the PDF with the `export_artifact` tool exactly like a PNG.

## Library calls (run_python; cwd = /workspace)

```python
from iscodes.pdfreport import PdfReport

p = (PdfReport("Beam B1 — IS 456:2000 LSM design", ["IS456", "SP16"])
     .add_section("Inputs")
     .add_table(["Item", "Value"],
                [["Span", "6.0 m"], ["Section", "300 x 550 mm"],
                 ["Materials", "M25 / Fe500"],
                 ["Loads", "DL 15 + IL 10 kN/m (factored 1.5)"]])
     .add_section("Design summary")
     .add_table(["Item", "Value"],
                [["Tension steel", "3-20 dia (942 mm2)"],
                 ["Stirrups", "8 dia 2-legged @ 300 c/c"]])
     .add_section("Code checks")
     # r["checks"] from the design function drops straight in:
     .add_checks(r["checks"])
     .add_section("Figures")
     .add_figure("out/sfd_bmd.png", "SFD/BMD — BMD drawn on tension side "
                                    "(sagging positive), IS convention")
     .save("out/beam_b1_report.pdf"))
print("pdf written:", p)
```

Or the one-call form:
```python
from iscodes.pdfreport import from_report_checks
from_report_checks("Beam B1 design", r["checks"],
                   figures=[("out/sfd_bmd.png", "SFD/BMD")],
                   code_refs=["IS456", "SP16"],
                   summary_rows=[["Ast", "942 mm2"]],
                   path="out/beam_b1_report.pdf")
```

Rules:
- Every figure the report references must exist before `save()` — missing
  figures render as a placeholder note, not an error.
- Always `export_artifact` the PDF (`out/<name>.pdf`) and give the user the
  returned path; the web UI serves it with the correct content type.
- The report automatically appends code-edition references and the
  engineering disclaimer — do not remove them.
