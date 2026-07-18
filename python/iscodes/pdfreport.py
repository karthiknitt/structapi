"""PDF design reports with inline figures (SFD/BMD PNGs, P-M diagrams).

Mirrors report.Report but renders to PDF via reportlab. Figures referenced by
path are embedded inline, scaled to the content width.
"""

from __future__ import annotations

import os

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import (Image, PageBreak, Paragraph,
                                SimpleDocTemplate, Spacer, Table, TableStyle)

from . import DISCLAIMER, tables

_CONTENT_W = A4[0] - 40 * mm

_styles = getSampleStyleSheet()
_H1 = ParagraphStyle("H1x", parent=_styles["Heading1"], fontSize=16,
                     spaceAfter=6)
_H2 = ParagraphStyle("H2x", parent=_styles["Heading2"], fontSize=12,
                     spaceBefore=10, spaceAfter=4,
                     textColor=colors.HexColor("#1a355e"))
_BODY = ParagraphStyle("Bodyx", parent=_styles["BodyText"], fontSize=9.5,
                       leading=13)
_CHECK = ParagraphStyle("Checkx", parent=_BODY, leftIndent=6)
_CAPTION = ParagraphStyle("Capx", parent=_BODY, fontSize=8.5,
                          textColor=colors.HexColor("#555555"),
                          spaceAfter=8)
_FOOT = ParagraphStyle("Footx", parent=_BODY, fontSize=8,
                       textColor=colors.HexColor("#777777"))
_TOC_H = ParagraphStyle("TOCHx", parent=_H2, spaceBefore=0)
_TOC1 = ParagraphStyle("TOC1x", parent=_BODY, fontSize=10, spaceAfter=3,
                       textColor=colors.HexColor("#1a5fb4"))
_TOC2 = ParagraphStyle("TOC2x", parent=_TOC1, fontSize=9, leftIndent=10,
                       textColor=colors.HexColor("#3a71b8"))


class PdfReport:
    """Build a clause-referenced design report PDF.

    Usage mirrors report.Report:
        p = PdfReport("Beam B1 design", ["IS456", "SP16"])
        p.add_section("Flexure"); p.add_line("Mu = 120 kNm")
        p.add_check("Mu <= Mu_lim (cl 38.1)", True)
        p.add_table(["item", "value"], [["Ast", "982 mm2"]])
        p.add_figure("out/sfd_bmd.png", "SFD/BMD — BMD on tension side")
        p.save("out/beam_b1.pdf")
    """

    def __init__(self, title: str, code_refs: list | None = None):
        self.title = title
        self.code_refs = code_refs or []
        self._flow: list = [Paragraph(title, _H1), Spacer(1, 2 * mm)]
        self._toc: list = []  # (level, text, anchor)

    def _anchored_heading(self, heading: str, style, level: int) -> str:
        anchor = f"toc{len(self._toc)}"
        self._toc.append((level, heading, anchor))
        self._flow.append(Paragraph(f'<a name="{anchor}"/>{heading}', style))
        return anchor

    def add_section(self, heading: str) -> "PdfReport":
        self._anchored_heading(heading, _H2, 0)
        return self

    def add_subsection(self, heading: str) -> "PdfReport":
        """Like add_line, but registers a level-1 entry in the TOC."""
        self._anchored_heading(heading, _CHECK, 1)
        return self

    def add_line(self, text: str) -> "PdfReport":
        self._flow.append(Paragraph(text, _BODY))
        return self

    def add_check(self, name: str, ok: bool, detail: str = "") -> "PdfReport":
        mark = ("<font color='#1e7a34'><b>PASS</b></font>" if ok
                else "<font color='#b3261e'><b>FAIL</b></font>")
        text = f"{mark}&nbsp;&nbsp;{name}"
        if detail:
            text += f" — {detail}"
        self._flow.append(Paragraph(text, _CHECK))
        return self

    def add_checks(self, checks: list) -> "PdfReport":
        for name, ok in checks:
            self.add_check(name, bool(ok))
        return self

    def add_table(self, headers: list, rows: list) -> "PdfReport":
        data = [[Paragraph(f"<b>{h}</b>", _BODY) for h in headers]]
        data += [[Paragraph(str(c), _BODY) for c in row] for row in rows]
        t = Table(data, hAlign="LEFT", colWidths=[_CONTENT_W / len(headers)] *
                  len(headers))
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eef2f8")),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#b9c4d4")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        self._flow += [Spacer(1, 2 * mm), t, Spacer(1, 2 * mm)]
        return self

    def add_figure(self, png_path: str, caption: str = "") -> "PdfReport":
        """Embed a PNG inline, scaled to content width (aspect preserved)."""
        if not os.path.exists(png_path):
            self._flow.append(Paragraph(
                f"[missing figure: {png_path}]", _CAPTION))
            return self
        iw, ih = ImageReader(png_path).getSize()
        w = min(_CONTENT_W, iw)
        h = ih * w / iw
        self._flow += [Spacer(1, 3 * mm), Image(png_path, width=w, height=h)]
        if caption:
            self._flow.append(Paragraph(caption, _CAPTION))
        return self

    def save(self, path: str) -> str:
        # self._flow[0:2] are the title Paragraph + Spacer set up in
        # __init__; the TOC (built last, once every anchor is known) is
        # spliced in right after them so it appears on its own page up
        # front, before section content begins.
        flow = list(self._flow[:2])
        if self._toc:
            flow.append(Paragraph("Table of Contents", _TOC_H))
            for level, text, anchor in self._toc:
                style = _TOC1 if level == 0 else _TOC2
                flow.append(Paragraph(
                    f'<a href="#{anchor}" color="#1a5fb4">{text}</a>',
                    style))
            flow.append(PageBreak())
        flow += self._flow[2:]
        if self.code_refs:
            flow.append(Paragraph("Code references", _H2))
            for ref in self.code_refs:
                ed = tables.CODE_EDITIONS.get(ref, "")
                flow.append(Paragraph(
                    f"• {ref}" + (f" — {ed}" if ed else ""), _BODY))
        flow += [Spacer(1, 6 * mm), Paragraph(DISCLAIMER, _FOOT)]
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        SimpleDocTemplate(
            path, pagesize=A4,
            leftMargin=20 * mm, rightMargin=20 * mm,
            topMargin=18 * mm, bottomMargin=18 * mm,
            title=self.title,
        ).build(flow)
        return path


def from_report_checks(title: str, checks: list, figures: list,
                       code_refs: list | None = None,
                       summary_rows: list | None = None,
                       path: str = "out/report.pdf") -> str:
    """One-call convenience: checks + summary table + figures -> PDF."""
    p = PdfReport(title, code_refs)
    if summary_rows:
        p.add_section("Design summary")
        p.add_table(["Item", "Value"], summary_rows)
    p.add_section("Code checks")
    p.add_checks(checks)
    if figures:
        p.add_section("Figures")
        for fig in figures:
            png, caption = fig if isinstance(fig, (list, tuple)) else (fig, "")
            p.add_figure(png, caption)
    return p.save(path)
