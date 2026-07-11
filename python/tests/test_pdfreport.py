"""PDF report generation with embedded PNG figures."""

from iscodes.design.beam import design_beam
from iscodes.pdfreport import PdfReport, from_report_checks
from iscodes.plotting import plot_sfd_bmd


def test_pdf_with_embedded_sfd_bmd(tmp_path):
    r = design_beam(span_m=6.0, w_dl_kn_m=15.0, w_il_kn_m=10.0,
                    b=300, D=550, fck=25, fy=500, support="ss")
    png = str(tmp_path / "sfd_bmd.png")
    plot_sfd_bmd(r["analysis"]["x"], r["analysis"]["V"], r["analysis"]["M"],
                 "Beam 300x550 - 6 m SS", png, tension_side=True)

    pdf = str(tmp_path / "beam_report.pdf")
    out = (PdfReport("Beam B1 — IS 456:2000 LSM design", ["IS456", "SP16"])
           .add_section("Inputs")
           .add_table(["Item", "Value"],
                      [["Span", "6.0 m"], ["Section", "300 x 550"],
                       ["Loads", "DL 15 + IL 10 kN/m"]])
           .add_section("Checks")
           .add_checks(r["checks"])
           .add_section("Figures")
           .add_figure(png, "SFD/BMD — BMD drawn on tension side")
           .save(pdf))
    data = open(out, "rb").read()
    assert data[:5] == b"%PDF-"
    assert len(data) > 30_000  # embedded PNG makes it non-trivial


def test_from_report_checks_convenience(tmp_path):
    pdf = from_report_checks(
        "Quick report", [("check A", True), ("check B", False)],
        figures=[], code_refs=["IS456"],
        summary_rows=[["Ast", "982 mm2"]],
        path=str(tmp_path / "quick.pdf"))
    assert open(pdf, "rb").read()[:5] == b"%PDF-"


def test_missing_figure_is_graceful(tmp_path):
    pdf = (PdfReport("No fig").add_figure("does/not/exist.png", "x")
           .save(str(tmp_path / "nofig.pdf")))
    assert open(pdf, "rb").read()[:5] == b"%PDF-"
