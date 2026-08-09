"""Whole-building RCC design chain: column grid in -> full structural design out.

The PlanForge integration workhorse (docs/PLANFORGE-INTEGRATION.md Phase B):
loads takedown (IS 875-1/2, 875-3 wind, 1893 seismic) -> two-way slab panels
(Table 26 case by position) -> tributary beams -> columns (gravity + portal-
frame lateral moments, IS 13920 overlay) -> isolated footings -> quantity
takeoff (BOQ-shaped) -> consolidated figures + PDF-ready sections.

Deliberate v1 simplifications (all echoed in result["assumptions"]):
- Regular orthogonal grid; beams on every grid line; columns at intersections.
- Beams on a grid line with >=3 spans that do not differ by more than 15% of
  the longest are designed with IS 456 cl 22.5.1 Table 12/13 continuous-beam
  coefficients, giving separate bottom (sagging) and top (hogging) steel.
  Any other line (<3 spans, or irregular spacing) falls back to simply
  supported on the worst span (conservative vs Table 12 continuity).
- Lateral: equivalent-static seismic and static wind computed; the larger
  base shear governs; portal-frame moment distribution between columns.
- Steel quantity from designed Ast x member length x 7850 kg/m3 + 10% waste.

Units: m, kN externally; mm/N internally per iscodes convention.
"""

from __future__ import annotations

import math
import os
from dataclasses import asdict, is_dataclass

from .. import detailing
from .. import loads as ld
from .. import tables
from ..analysis.beam import continuous_moments
from . import combinations as comb
from . import flexure
from .cantilever import design_parapet
from .column import ColumnSection, design_column, interaction_curve, rect_bar_layout
from .footing import design_combined_footing, design_isolated_footing
from .slab import design_one_way_slab, design_two_way_slab
from .beam import design_beam

STEEL_DENSITY = 7850.0  # kg/m3
WASTE_FACTOR = 1.10

# Occupancies IS 875-2 cl 3.2 (Table 8 note) excludes from storey-count-based
# live-load reduction (roofs, storage, parking, fixed/assembly seating -- the
# imposed load there doesn't attenuate the way ordinary floor occupancy load
# does across storeys). Single module-level source: one copy previously drove
# the `assumptions` text, another drove actual reduction behaviour, so
# editing one without the other made the audit trail lie.
NEVER_REDUCE_OCCUPANCIES = {"roof_accessible", "roof_non_accessible",
                            "office_storage", "parking_car",
                            "assembly_fixed_seating", "assembly_movable_seating"}


def _render_beam_figure(r: dict, key: str, direction: str, span: float,
                        tw: float, b: float, D: float, figures_dir: str,
                        figures: dict) -> None:
    """SFD/BMD PNG for one unique beam. Never raises — a plotting failure
    must not take down the (already-computed) structural design."""
    try:
        from ..plotting import plot_sfd_bmd
        x, V, M = r["analysis"]["x"], r["analysis"]["V"], r["analysis"]["M"]
        fpath = os.path.join(
            figures_dir, f"beam_{direction}_span{span:.2f}_trib{tw:.2f}.png")
        plot_sfd_bmd(x, V, M,
                     f"Beam {b:.0f}x{D:.0f} mm — {direction}-dir span "
                     f"{span:.2f} m (trib {tw:.2f} m)", fpath)
        figures[f"beams:{key}"] = (
            fpath, f"SFD/BMD — {direction}-direction, span {span:.2f} m, "
                   f"tributary width {tw:.2f} m")
    except Exception:
        pass


def _render_column_figure(kind: str, b: float, D: float, fck: float, fy: float,
                          nb: int, dia: float, r, Pu: float, count: int,
                          figures_dir: str, figures: dict, cover: float = 40.0) -> None:
    """P-M interaction PNG for one column kind (corner/edge/interior)."""
    try:
        from ..plotting import plot_pm_interaction
        # tie_dia=8.0 — design_column()'s own default (also not overridden by
        # the building chain). cover is the exposure-derived value actually
        # passed to design_column(), so the section drawn here matches the
        # section actually designed.
        cc = cover + 8.0 + dia / 2.0
        sec = ColumnSection(b, D, fck, fy, rect_bar_layout(b, D, cc, nb, dia))
        curve = interaction_curve(sec) / 1e3
        curve[:, 1] /= 1e3
        fpath = os.path.join(figures_dir, f"column_{kind}_pm.png")
        plot_pm_interaction(
            curve, [(r.data.get("Mux_design_kNm", 0.0), Pu)],
            f"Column ({kind}) {b:.0f}x{D:.0f} mm — P-M interaction", fpath)
        figures[f"columns:{kind}"] = (
            fpath, f"P-M interaction — {kind} columns ({count} nos.)")
    except Exception:
        pass


def _render_footing_figure(kind: str, fd: dict, count: int,
                           figures_dir: str, figures: dict) -> None:
    """Base-pressure PNG for one footing kind. Skipped if the footing design
    didn't converge (its data dict then lacks the pressure fields)."""
    try:
        from ..plotting import plot_pressure_diagram
        d = fd["data"]
        fpath = os.path.join(figures_dir, f"footing_{kind}_pressure.png")
        plot_pressure_diagram(d["L_m"], d["q_min_service_kPa"],
                              d["q_max_service_kPa"],
                              f"Footing ({kind}) base pressure (service)", fpath)
        figures[f"footings:{kind}"] = (
            fpath, f"Base pressure (service) — {kind} footings ({count} nos.)")
    except Exception:
        pass


def _beam_detail_rows(el: dict) -> list:
    d = el.get("design", {})
    rows = [
        ["Section (b x D)", f"{el['b_mm']:.0f} x {el['D_mm']:.0f} mm"],
        ["Span / tributary width",
         f"{el['span_m']:.2f} m / {el['trib_width_m']:.2f} m"],
        ["Bottom (tension) steel",
         f"{d.get('n_bars', '-')}-{d.get('bar_dia', 0):.0f}φ "
         f"({d.get('Ast_prov_mm2', 0):.0f} mm2 prov, "
         f"{d.get('Ast_reqd_mm2', 0):.0f} mm2 reqd)"],
    ]
    if d.get("doubly_reinforced"):
        rows.append(["Top (compression) steel",
                     f"{d.get('n_bars_comp', '-')}-{d.get('bar_dia', 0):.0f}φ "
                     f"({d.get('Asc_prov_mm2', 0):.0f} mm2 prov)"])
    ts = d.get("top_steel")
    if ts:
        # top_steel is populated whenever ANY Mu_support_override_kNm was
        # supplied -- that can be genuine Table 12 continuity OR a purely
        # seismic reversal moment seeded onto a non-continuous beam (see
        # table12_continuous / top_steel_source in design_building()).
        # Attribute the clause correctly rather than assuming Table 12.
        source = el.get("top_steel_source")
        if source == "seismic_reversal":
            label = "IS 1893 cl 6.2.3 seismic moment reversal"
            moments_label = "Design moments (IS 1893 cl 6.2.3 seismic reversal)"
        else:
            label = "IS 456 Table 12"
            moments_label = "Design moments (IS 456 cl 22.5.1)"
        rows.append(["Top (hogging) steel at supports",
                     f"{ts['n_bars']}-{ts['bar_dia']:.0f}φ "
                     f"({ts['Ast_prov_mm2']:.0f} mm2 prov, "
                     f"{ts['Ast_reqd_mm2']:.0f} mm2 reqd) — {label}"])
        rows.append([moments_label,
                     f"sagging {d.get('bottom_steel_Mu_kNm', 0):.1f} kNm / "
                     f"hogging {ts['Mu_hogging_kNm']:.1f} kNm"])
    st = d.get("stirrups", {})
    stirrup_dia = el.get("inputs", {}).get("stirrup_dia", 8)
    rows.append(["Stirrups",
                 f"2-legged {stirrup_dia:.0f} mm dia @ "
                 f"{st.get('sv_provided', '-')} mm c/c ({st.get('governing', '-')})"])
    defl = d.get("deflection", {})
    rows.append(["Deflection L/d",
                 f"{defl.get('actual_L_by_d', 0):.1f} <= "
                 f"{defl.get('allowable_L_by_d', 0):.1f}"])
    rows.append(["pt %", f"{d.get('pt_percent', 0):.2f}%"])
    return rows


def _column_detail_rows(el: dict) -> list:
    d = el.get("data", {})
    rows = [
        ["Section (b x D)", f"{el['b_mm']:.0f} x {el['D_mm']:.0f} mm"],
        ["Longitudinal steel", f"{el['bars']} ({d.get('p_percent', 0):.2f}%)"],
        ["Ties", f"{d.get('tie_dia', '-')} mm dia @ "
                 f"{d.get('tie_pitch_max', 0):.0f} mm c/c max"],
        ["Design axial load Pu", f"{el.get('Pu_kN', 0):.0f} kN"],
        ["Design moments (Mux / Muy)",
         f"{d.get('Mux_design_kNm', 0):.1f} / {d.get('Muy_design_kNm', 0):.1f} kNm"],
        ["Biaxial interaction ratio (cl 39.6)", f"{d.get('interaction', 0):.2f}"],
        ["Slenderness (lex/D, ley/b)",
         f"{d.get('lex_by_D', 0):.1f}, {d.get('ley_by_b', 0):.1f}"],
    ]
    return rows


def _footing_detail_rows(el: dict) -> list:
    d = el.get("data", {})
    rows = [
        ["Plan size (L x B)", f"{d.get('L_m', 0):.2f} x {d.get('B_m', 0):.2f} m"],
        ["Overall depth", f"{d.get('D_overall_mm', 0):.0f} mm"],
        ["Steel — long direction (x)", d.get("bars_x", "-")],
        ["Steel — transverse (y)", d.get("bars_y", "-")],
        ["Base pressure (service, min/max)",
         f"{d.get('q_min_service_kPa', 0):.1f} / "
         f"{d.get('q_max_service_kPa', 0):.1f} kPa"],
        ["Anchorage", d.get("anchorage_note", "-")],
    ]
    if d.get("dowels_note"):
        rows.append(["Note", d["dowels_note"]])
    return rows


def _slab_detail_rows(el: dict) -> list:
    rows = [
        ["Type", el.get("type", "-")],
        ["Overall depth", f"{el.get('D_mm', 0):.0f} mm"],
    ]
    if el.get("type") == "one-way":
        main, dist = el.get("main", {}), el.get("distribution", {})
        rows.append(["Main steel", main.get("bar", "-")])
        rows.append(["Distribution steel", dist.get("bar", "-")])
    else:
        for tag, s in el.get("strips", {}).items():
            rows.append([f"Steel — {tag.replace('_', ' ')}", s.get("bar", "-")])
    defl = el.get("deflection", {})
    rows.append(["Deflection L/d",
                 f"{defl.get('actual_L_by_d', 0):.1f} <= "
                 f"{defl.get('allowable_L_by_d', 0):.1f}"])
    return rows


_DETAIL_ROWS_BY_GROUP = {
    "slabs": _slab_detail_rows,
    "beams": _beam_detail_rows,
    "columns": _column_detail_rows,
    "footings": _footing_detail_rows,
}


_PANEL_CASE_BY_DISC = {
    # (discontinuous short edges, discontinuous long edges) -> Table 26 case
    (0, 0): 1,  # interior panels (four edges continuous)
    (1, 0): 2,  # one short edge discontinuous
    (0, 1): 3,  # one long edge discontinuous
    (1, 1): 4,  # two adjacent edges discontinuous
    (2, 0): 5,  # two short edges discontinuous
    (0, 2): 6,  # two long edges discontinuous
    (2, 1): 7,  # three edges discontinuous (one long edge continuous)
    (1, 2): 8,  # three edges discontinuous (one short edge continuous)
    (2, 2): 9,  # four edges discontinuous
}


def _panel_case(i: int, j: int, nx: int, ny: int, sx: float, sy: float) -> int:
    """IS 456 Table 26 case from panel position plus this panel's own span
    orientation.

    An edge is continuous where it is shared with a neighbouring panel and
    discontinuous where it lies on the building boundary. Table 26's "short"
    and "long" edges are named by *edge length* relative to lx = min(sx, sy),
    not by grid axis, so which axis carries the short edges flips per panel:

    - edges perpendicular to x (at x=0 and x=sx) have length ``sy``
    - edges perpendicular to y (at y=0 and y=sy) have length ``sx``

    Square panels (sx == sy) have no distinct short/long edge; they take the
    ``sx <= sy`` branch so the mapping stays deterministic.
    """
    n_x_disc = int(i == 0) + int(i == nx - 1)
    n_y_disc = int(j == 0) + int(j == ny - 1)
    if sx <= sy:
        # sx is the short span -> y-perpendicular edges (length sx) are short
        n_short_disc, n_long_disc = n_y_disc, n_x_disc
    else:
        # sy is the short span -> x-perpendicular edges (length sy) are short
        n_short_disc, n_long_disc = n_x_disc, n_y_disc
    return _PANEL_CASE_BY_DISC[(n_short_disc, n_long_disc)]


def _column_kind(i: int, j: int, nx_bays: int, ny_bays: int) -> str:
    """Column class from its grid-intersection position (i,j in grid-line
    index space, 0..nx_bays / 0..ny_bays)."""
    edge_x = i == 0 or i == nx_bays
    edge_y = j == 0 or j == ny_bays
    if edge_x and edge_y:
        return "corner"
    if edge_x or edge_y:
        return "edge"
    return "interior"


# ---------------------------------------------------------------------------
# violations[] — machine-readable failure -> solver-remedy mapping
# (PlanForge closed-loop: v0.2.0, additive to the frozen v1 envelope)
# ---------------------------------------------------------------------------

_ALLOWED_REMEDIES = {"reduce_span", "increase_section", "add_grid_line",
                     "increase_sbc", "increase_grade", "review_inputs"}


def _violation(member_type: str, axis: str | None, grid_ref: str,
              span_m: float | None, check: str, actual, limit, unit: str,
              remedy_hint: str) -> dict:
    assert remedy_hint in _ALLOWED_REMEDIES, remedy_hint
    return {
        "member_type": member_type, "axis": axis, "grid_ref": grid_ref,
        "span_m": None if span_m is None else float(span_m),
        "check": check,
        "actual": None if actual is None else float(actual),
        "limit": None if limit is None else float(limit),
        "unit": unit, "remedy_hint": remedy_hint,
    }


def _beam_moment_capacity_kNm(bm: dict) -> float:
    """Recompute the moment capacity used by design_beam's "moment capacity
    >= Mu" check (cl 26.5.1.1 / doubly-reinforced sum). Not stored on the
    public design_beam() summary (would change the frozen /v1/calc/beam
    contract), so building.py recomputes it from already-known design
    values — no string-parsing of check names involved."""
    inp, d = bm["inputs"], bm["design"]
    b, D, fck, fy = inp["b"], inp["D"], inp["fck"], inp["fy"]
    dd = d["d_mm"]
    dc = inp["cover"] + inp["stirrup_dia"] + inp["bar_dia"] / 2.0
    cap = flexure.mu_capacity(d["Ast_prov_mm2"], b, dd, fck, fy)
    if d["doubly_reinforced"]:
        cap += (d["Asc_prov_mm2"] * (tables.fsc(fy, dc / dd) - 0.446 * fck)
               * (dd - dc))
    return cap / 1e6


def _beam_violations(key: tuple, bm: dict) -> list:
    direction, span, _tw = key
    d = bm["design"]
    grid_ref = (f"beam line axis={direction}, "
               f"grid indices={bm.get('grid_line_indices', [])}, "
               f"span {span:.2f} m")
    out = []
    for name, ok in bm["checks"]:
        if ok:
            continue
        if name.startswith("flexure Ast >= Ast_min"):
            out.append(_violation("beam", direction, grid_ref, span, name,
                                  d["Ast_prov_mm2"], d["Ast_min_mm2"], "mm2",
                                  "review_inputs"))
        elif name.startswith("flexure Ast <= Ast_max"):
            out.append(_violation("beam", direction, grid_ref, span, name,
                                  d["Ast_prov_mm2"], d["Ast_max_mm2"], "mm2",
                                  "reduce_span"))
        elif name.startswith("moment capacity >= Mu"):
            out.append(_violation("beam", direction, grid_ref, span, name,
                                  d["Mu_max_kNm"], _beam_moment_capacity_kNm(bm),
                                  "kNm", "add_grid_line"))
        elif name.startswith("shear (cl 40)"):
            st = d["stirrups"]
            out.append(_violation("beam", direction, grid_ref, span, name,
                                  st.get("tau_v"), st.get("tau_c_max"), "MPa",
                                  "add_grid_line"))
        elif name.startswith("deflection L/d"):
            df = d["deflection"]
            out.append(_violation("beam", direction, grid_ref, span, name,
                                  df.get("actual_L_by_d"),
                                  df.get("allowable_L_by_d"), "ratio",
                                  "reduce_span"))
        elif name.startswith("top steel Ast <= Ast_max"):
            out.append(_violation("beam", direction, grid_ref, span, name,
                                  d.get("top_steel", {}).get("Ast_prov_mm2"),
                                  d["Ast_max_mm2"], "mm2", "reduce_span"))
        elif name.startswith("hogging moment capacity"):
            ts = d.get("top_steel", {})
            out.append(_violation("beam", direction, grid_ref, span, name,
                                  ts.get("Mu_hogging_kNm"),
                                  ts.get("Mu_capacity_kNm"), "kNm",
                                  "add_grid_line"))
        elif name.startswith("IS 13920 min width"):
            out.append(_violation("beam", direction, grid_ref, span, name,
                                  bm["b_mm"], tables.DUCTILE["beam_min_b"],
                                  "mm", "increase_section"))
        elif name.startswith("IS 13920 pt"):
            out.append(_violation("beam", direction, grid_ref, span, name,
                                  d["pt_percent"] / 100.0,
                                  tables.DUCTILE["beam_max_pt"], "ratio",
                                  "add_grid_line"))
        elif name.startswith("IS 13920 confining-zone"):
            ds = d.get("ductile_stirrups", {})
            out.append(_violation("beam", direction, grid_ref, span, name,
                                  ds.get("confining_zone_spacing_mm"),
                                  ds.get("confining_zone_spacing_limit_mm"),
                                  "mm", "review_inputs"))
        elif name.startswith("IS 13920 span-zone"):
            ds = d.get("ductile_stirrups", {})
            out.append(_violation("beam", direction, grid_ref, span, name,
                                  ds.get("span_zone_spacing_mm"),
                                  ds.get("span_zone_spacing_limit_mm"),
                                  "mm", "review_inputs"))
        else:
            out.append(_violation("beam", direction, grid_ref, span, name,
                                  None, None, "", "review_inputs"))
    return out


def _column_violations(kind: str, col: dict) -> list:
    grid_ref = f"column class {kind}"
    data = col["data"]
    out = []
    for name, ok in col["checks"]:
        if ok:
            continue
        if name.startswith("min steel 0.8%"):
            out.append(_violation("column", None, grid_ref, None, name,
                                  data.get("p_percent"), 0.8, "%",
                                  "increase_section"))
        elif name.startswith("max steel 6%"):
            out.append(_violation("column", None, grid_ref, None, name,
                                  data.get("p_percent"), 6.0, "%",
                                  "increase_section"))
        elif name.startswith("min 4 bars"):
            out.append(_violation("column", None, grid_ref, None, name,
                                  col.get("bar_dia"), 12.0, "mm",
                                  "review_inputs"))
        elif name.startswith("slenderness"):
            actual = max(data.get("lex_by_D", 0.0), data.get("ley_by_b", 0.0))
            out.append(_violation("column", None, grid_ref, None, name,
                                  actual, 60.0, "ratio", "increase_section"))
        elif name.startswith("biaxial interaction"):
            out.append(_violation("column", None, grid_ref, None, name,
                                  data.get("interaction"), 1.0, "ratio",
                                  "increase_section"))
        elif name.startswith("tie dia"):
            out.append(_violation("column", None, grid_ref, None, name,
                                  data.get("tie_dia"), data.get("tie_dia_min"),
                                  "mm", "review_inputs"))
        elif name.startswith("IS 13920 confining hoop Ash"):
            # Ash falls as Ag/Ak -> 1, i.e. as the section grows relative to
            # its cover; a bigger section is the solver-actionable remedy.
            # demand/capacity orientation (like "moment capacity >= Mu"):
            # actual = Ash required, limit = Ash provided by the hoop bar.
            out.append(_violation("column", None, grid_ref, None, name,
                                  data.get("Ash_required_mm2"),
                                  data.get("Ash_provided_mm2"), "mm2",
                                  "increase_section"))
        elif name.startswith("IS 13920 confining hoop spacing"):
            out.append(_violation("column", None, grid_ref, None, name,
                                  data.get("confine_spacing_max"),
                                  data.get("confine_spacing_limit"), "mm",
                                  "review_inputs"))
        elif name.startswith("min width"):
            out.append(_violation("column", None, grid_ref, None, name,
                                  min(col["b_mm"], col["D_mm"]),
                                  data.get("min_dim_required",
                                          tables.DUCTILE["column_min_b_storeys"]),
                                  "mm", "increase_section"))
        else:
            out.append(_violation("column", None, grid_ref, None, name,
                                  None, None, "", "review_inputs"))
    return out


def _footing_violations(kind: str, foot: dict, sbc_kpa: float) -> list:
    grid_ref = f"footing class {kind}"
    data = foot.get("data", {})
    out = []
    for name, ok in foot["checks"]:
        if ok:
            continue
        if name == "depth converged for shear":
            out.append(_violation("footing", None, grid_ref, None, name,
                                  None, None, "", "increase_sbc"))
        elif name.startswith("service q_max"):
            out.append(_violation("footing", None, grid_ref, None, name,
                                  data.get("q_max_service_kPa"), sbc_kpa,
                                  "kPa", "increase_sbc"))
        elif name.startswith("service q_min"):
            out.append(_violation("footing", None, grid_ref, None, name,
                                  data.get("q_min_service_kPa"), 0.0, "kPa",
                                  "review_inputs"))
        elif name.startswith("two-way shear"):
            tws = data.get("two_way_shear", {})
            out.append(_violation("footing", None, grid_ref, None, name,
                                  tws.get("tau_v"), tws.get("tau_lim"), "MPa",
                                  "increase_section"))
        elif name.startswith("one-way shear X"):
            ows = data.get("one_way_shear", {})
            out.append(_violation("footing", None, grid_ref, None, name,
                                  ows.get("tau_vx"), ows.get("tcx"), "MPa",
                                  "increase_section"))
        elif name.startswith("one-way shear Y"):
            ows = data.get("one_way_shear", {})
            out.append(_violation("footing", None, grid_ref, None, name,
                                  ows.get("tau_vy"), ows.get("tcy"), "MPa",
                                  "increase_section"))
        elif name.startswith("development length"):
            avail = data.get("Ld_available_mm")
            dia = data.get("main_bar_dia_max_mm")
            actual = (avail + 8.0 * dia) if (avail is not None
                                             and dia is not None) else None
            out.append(_violation("footing", None, grid_ref, None, name,
                                  actual, data.get("Ld_mm"), "mm",
                                  "increase_section"))
        elif name.startswith("bearing at column base"):
            out.append(_violation("footing", None, grid_ref, None, name,
                                  data.get("bearing_sigma_MPa"),
                                  data.get("bearing_limit_MPa"), "MPa",
                                  "increase_grade"))
        else:
            out.append(_violation("footing", None, grid_ref, None, name,
                                  None, None, "", "review_inputs"))
    return out


def _slab_violations(p: dict) -> list:
    grid_ref = (f"slab panel {p['type']} lx={p['lx_m']:.2f}m "
               f"ly={p['ly_m']:.2f}m case={p['case_']}")
    d_x = p.get("d_mm") if p["type"] == "one-way" else p.get("d_x_mm")
    d_y = p.get("d_y_mm")
    out = []
    for name, ok in p["checks"]:
        if ok:
            continue
        if "Ast >= max(flexure" in name:
            tag = name.split(":")[0]
            strip = p.get("main") if tag == "main" else (p.get("strips") or {}).get(tag, {})
            out.append(_violation("slab", None, grid_ref, p["lx_m"], name,
                                  strip.get("Ast_prov"), strip.get("Ast_req"),
                                  "mm2/m", "add_grid_line"))
        elif "depth adequate for flexure" in name:
            out.append(_violation("slab", None, grid_ref, p["lx_m"], name,
                                  None, None, "", "add_grid_line"))
        elif "spacing <=" in name:
            tag = name.split(":")[0]
            strip = p.get("main") if tag == "main" else (p.get("strips") or {}).get(tag, {})
            d_eff = d_y if "long_y" in tag else d_x
            cap = min(3 * d_eff, 300.0) if d_eff else None
            out.append(_violation("slab", None, grid_ref, p["lx_m"], name,
                                  strip.get("spacing"), cap, "mm",
                                  "review_inputs"))
        elif name.startswith("shear tau_v"):
            out.append(_violation("slab", None, grid_ref, p["lx_m"], name,
                                  p.get("tau_v"), p.get("tau_allow"), "MPa",
                                  "add_grid_line"))
        elif name.startswith("deflection L/d"):
            defl = p.get("deflection", {})
            out.append(_violation("slab", None, grid_ref, p["lx_m"], name,
                                  defl.get("actual_L_by_d"),
                                  defl.get("allowable_L_by_d"), "ratio",
                                  "reduce_span"))
        else:
            out.append(_violation("slab", None, grid_ref, p["lx_m"], name,
                                  None, None, "", "review_inputs"))
    return out


def _collect_violations(panels: dict, beams: dict, columns: dict,
                        footings: dict, sbc_kpa: float) -> list:
    violations = []
    for p in panels.values():
        violations += _slab_violations(p)
    for key, bm in beams.items():
        violations += _beam_violations(key, bm)
    for kind, col in columns.items():
        violations += _column_violations(kind, col)
    for kind, foot in footings.items():
        violations += _footing_violations(kind, foot, sbc_kpa)
    return violations


def design_building(x_spacings_m: list, y_spacings_m: list, storeys: int,
                    storey_height_m: float = 3.0,
                    occupancy: str = "residential_room",
                    city: str | None = None, basic_wind_speed: float | None = None,
                    seismic_zone: str = "III", terrain_category: int = 2,
                    soil: str = "medium", sbc_kpa: float | None = None,
                    fck: float = 25.0, fy: float = 500.0,
                    exposure: str = "moderate",
                    finish_kn_m2: float = 1.5,
                    wall_thickness_m: float = 0.23,
                    seismic_detailing: bool | None = None,
                    apply_ll_reduction: bool = False,
                    parapet_height_m: float | None = None,
                    oh_tank_capacity_litres: float | None = None,
                    edge_setback_m: float | None = None,
                    figures_dir: str | None = None) -> dict:
    """Design every unique element of a regular RC frame building.

    figures_dir: when set, renders an SFD/BMD PNG per unique beam, a P-M
    interaction PNG per column kind, and a base-pressure PNG per footing
    kind into this directory, and returns their paths+captions in
    result["figures"]. Left None (default) to skip rendering entirely —
    matches every pre-existing caller/test exactly.

    parapet_height_m / oh_tank_capacity_litres / edge_setback_m: PD-5 chain
    integration, all None by default (no behaviour change for existing
    callers who don't pass them):
    - parapet_height_m: when set, designs a roof-level RC parapet wall
      (IS 875-2 minimum 0.75 kN/m lateral barrier load) and reports it under
      result["parapet"]. Informational/report-only — does not feed into the
      roof slab/column/seismic load chain (a parapet's own self-weight is
      negligible against the frame; only its lateral demand is of interest,
      and that demand is a standalone barrier-load check on the parapet
      wall itself, not a lateral action on the building frame).
    - oh_tank_capacity_litres: when set, estimates an overhead tank's total
      weight (water + ~18% structure allowance) and adds it to the roof-
      level seismic weight and to a representative roof-supporting column's
      axial load (see the "OH-tank" comments below for exactly which column
      kind and why). Does not design the tank's own walls/base — tank.py
      has no such function; see design/tank.py module docstring.
    - edge_setback_m: when set, detects edge/corner columns whose isolated
      footing would project past this distance from the column grid line,
      and computes a full two-column combined footing (design_combined_footing)
      for that case, reported under result["combined_footings"] alongside a
      violations[] entry (the isolated footing entry in result["footings"]
      is left as-is — combined_footings is additive/supplementary, not a
      replacement, so BOQ quantities/all existing "footings" consumers are
      unaffected; see PD-5 report for the reasoning).
    """
    nx_bays, ny_bays = len(x_spacings_m), len(y_spacings_m)
    if nx_bays < 1 or ny_bays < 1 or storeys < 1:
        raise ValueError("need >=1 bay each way and >=1 storey")
    Lx, Ly = sum(x_spacings_m), sum(y_spacings_m)
    area = Lx * Ly
    h_total = storeys * storey_height_m
    assumptions = [
        "regular orthogonal grid; columns at all intersections; beams on all grid lines",
        "beams with >=3 spans differing by <=15% of the longest use IS 456 "
        "cl 22.5.1 Table 12/13 continuous-beam coefficients (separate top/"
        "bottom steel, worst span as L); all other beam lines fall back to "
        "simply supported on worst span (conservative)",
        f"wall load: {wall_thickness_m*1000:.0f} mm brick on every beam, full storey height",
        "portal-frame lateral distribution (interior columns 2x exterior share)",
        "steel mass = designed Ast x length x 7850 kg/m3 x 1.10 waste",
        "column moments: lateral portal moments + minimum eccentricity per IS 456 cl 25.4",
        "columns designed for the full IS 1893 cl 6.3.1.2 combination set "
        "{1.5(DL+IL), 1.2(DL+IL+-EL), 1.5(DL+-EL), 0.9DL+-1.5EL} about both "
        "axes; every combination is checked and the worst P-M interaction "
        "governs. Reported Pu/Mux/Muy are the envelope maxima",
        "beams under ductile detailing carry an additional support (hogging) "
        "moment of 1.5 x the portal joint moment for seismic reversal, added "
        "on top of the gravity moment; this is a single always-added worst "
        "case, not a per-combination beam envelope",
    ]
    if sbc_kpa is None:
        sbc_kpa = 150.0
        assumptions.append(
            "sbc_kpa not provided — defaulted to 150 kPa (conservative "
            "placeholder; verify against an actual soil report)")
    il = ld.imposed_load(occupancy)
    # Live-load reduction assumption (added before seismic_detailing check
    # because reduction state is decided here and applies globally)
    if apply_ll_reduction:
        if occupancy not in NEVER_REDUCE_OCCUPANCIES:
            pct_at_this_storeys = tables.ll_reduction_pct(storeys)
            assumptions.append(
                f"live-load reduction (IS 875-2 cl 3.2): applied, "
                f"{pct_at_this_storeys:.0f}% at {storeys} storey(ies) carried")
        else:
            assumptions.append(
                f"live-load reduction (IS 875-2 cl 3.2): not applied "
                f"(occupancy '{occupancy}' in exclusion list)")
    else:
        assumptions.append("live-load reduction (IS 875-2 cl 3.2): not applied (default)")
    if seismic_detailing is None:
        seismic_detailing = seismic_zone.upper() in ("III", "IV", "V")
    figures: dict = {}

    # IS 456 Table 5 durability: exposure -> min grade + nominal cover.
    # Invalid exposure keys raise KeyError here, matching how invalid
    # soil/zone strings already fail naturally (tables.ZONE_FACTOR[zone.upper()]
    # in loads.base_shear()) rather than a redundant explicit check.
    exp = tables.EXPOSURE[exposure]
    cov = exp["cover"]

    # ---------------- slabs (unique panels) ----------------
    panels, panel_map = {}, {}
    for i, sx in enumerate(x_spacings_m):
        for j, sy in enumerate(y_spacings_m):
            case = _panel_case(i, j, nx_bays, ny_bays, sx, sy)
            lx, ly = min(sx, sy), max(sx, sy)
            key = (round(lx, 2), round(ly, 2), case)
            panel_map[(i, j)] = key
            if key in panels:
                panels[key]["count"] += 1
                continue
            if ly / lx > 2.0:
                r = design_one_way_slab(lx, finish_kn_m2, il, fck, fy,
                                        support="continuous", cover=cov)
                r["type"] = "one-way"
            else:
                r = design_two_way_slab(lx, ly, finish_kn_m2, il, fck, fy,
                                        case=case, cover=cov)
                r["type"] = "two-way"
            r["count"] = 1
            r["lx_m"], r["ly_m"], r["case_"] = lx, ly, case
            panels[key] = r

    panel_indices = {}
    for (i, j), key in panel_map.items():
        panel_indices.setdefault(key, []).append([i, j])
    for key, p in panels.items():
        p["panel_indices"] = panel_indices[key]

    slab_D = max(p["D_mm"] for p in panels.values())
    slab_dl = slab_D / 1000.0 * tables.UNIT_WEIGHTS["rcc"] + finish_kn_m2
    w_floor_service = slab_dl + il                       # kN/m2

    # ---------------- OH tank (roof-level weight only) ----------------
    # tank.py has no top-level "design a complete tank" function (only
    # circular_tank_forces / rectangular_wall_forces / uplift_check /
    # design_tank_wall_section pieces) -- this integration is deliberately
    # scoped to "its weight reaches the roof-level load chain", not a full
    # tank structural design (see PD-5 report).
    OH_TANK_STRUCTURE_FACTOR = 1.18  # water weight + ~18% RC structure allowance
    oh_tank_weight_kN = 0.0
    if oh_tank_capacity_litres is not None:
        water_weight_kN = (oh_tank_capacity_litres / 1000.0) * tables.UNIT_WEIGHTS["water"]
        oh_tank_weight_kN = water_weight_kN * OH_TANK_STRUCTURE_FACTOR
        assumptions.append(
            f"OH tank ({oh_tank_capacity_litres:.0f} litres): estimated total "
            f"weight {oh_tank_weight_kN:.1f} kN (water {water_weight_kN:.1f} kN "
            f"x {OH_TANK_STRUCTURE_FACTOR:.2f} structure-allowance factor) added "
            "to the roof-level seismic weight and to a representative roof-"
            "supporting column's axial load; the tank's own walls/base are "
            "NOT designed by this model")

    # ---------------- lateral loads ----------------
    # Computed before the beam loop (it moved up from below the beams in the
    # gravity-only version) because beams now need the portal frame moment to
    # build their seismic reversal demand, not just the columns.
    floor_dead = (slab_dl + 2.0) * area             # +2 kN/m2 frame allowance
    storey_weights = [ld.seismic_weight(floor_dead, il * area, il,
                                        is_roof=(k == storeys - 1))
                     for k in range(storeys)]
    if oh_tank_weight_kN > 0.0:
        # roof storey only (grep confirms is_roof=True is the last entry) —
        # other storeys' weights are untouched.
        storey_weights[-1] += oh_tank_weight_kN
    heights = [(k + 1) * storey_height_m for k in range(storeys)]
    R_seismic = 5.0 if seismic_detailing else 3.0
    # cl 7.6.2 masonry-infill formula (0.09h/sqrt(d)), computed once per
    # principal direction with that direction's own plan dimension as d —
    # this building model always carries mandatory infill wall loads
    # (wall_thickness_m/wall_kn_m below), so the infill formula applies
    # throughout, not the bare-RC-frame formula (0.075h^0.75) used
    # previously. Ta_x/Ta_y (hence Ah_x/Ah_y) only differ when Lx != Ly.
    seis_x = ld.base_shear(storey_weights, heights, zone=seismic_zone,
                           soil=soil, I=1.0, R=R_seismic,
                           frame="infill", base_dim=Lx)
    seis_y = ld.base_shear(storey_weights, heights, zone=seismic_zone,
                           soil=soil, I=1.0, R=R_seismic,
                           frame="infill", base_dim=Ly)
    # Governing scalar: the numerically larger of Ah_x/Ah_y, not an assumed
    # "shorter dimension -> shorter period -> higher Ah" rule. The IS 1893
    # cl 6.4.2 design spectrum (tables.sa_by_g) is *not* monotonic in T: it
    # rises (1+15T) below T=0.10s, is flat at the 2.5 plateau up to Tc
    # (0.40/0.55/0.67 s depending on soil), then falls as ~1/T beyond Tc.
    # Low-rise masonry-infill buildings often land on the rising branch or
    # the plateau, where the *shorter* period can give an equal or *lower*
    # Ah than the longer one — so min(Lx, Ly) is not a safe proxy; compare
    # the computed Ah values directly and take the worse case.
    seis = seis_x if seis_x.Ah >= seis_y.Ah else seis_y
    assumptions.append(
        "fundamental period switched from the bare-RC-frame formula "
        "(0.075 h^0.75) to the IS 1893 cl 7.6.2 masonry-infill formula "
        "(0.09 h / sqrt(d)), applied separately per direction with d=Lx "
        "and d=Ly (this building model always has mandatory infill walls, "
        "so there is no bare-frame case to preserve); the governing scalar "
        "used downstream (V_lateral, storey_shear_unit, M_lateral_kNm, "
        "column/footing design) is whichever direction gives the larger "
        "Ah, not assumed from the shorter plan dimension -- the cl 6.4.2 "
        "spectrum's rising/plateau/falling shape makes that assumption "
        "unsafe. This generally shortens Ta and can raise base shear "
        "relative to the old bare-frame value -- a disclosed behavioural "
        "change, not a silent one")
    Vb = basic_wind_speed or (tables.BASIC_WIND_SPEED.get((city or "").lower(), 39))
    wind = ld.wind_pressure(Vb, h_total, terrain_category)
    wind_base_shear = 1.2 * wind.pd * Ly * h_total   # Cf=1.2 on broader face
    lateral_gov = "seismic" if seis.VB >= wind_base_shear else "wind"
    V_lateral = max(seis.VB, wind_base_shear)

    n_cols = (nx_bays + 1) * (ny_bays + 1)
    n_int = max(nx_bays - 1, 0) * max(ny_bays - 1, 0)
    # portal frame: interior columns take 2 shares, exterior 1
    shares = 2 * n_int + (n_cols - n_int)
    storey_shear_unit = V_lateral / shares

    # Base overturning moment and the per-column axial couple it induces on
    # the extreme column lines (IS 1893 cl 6.3.1.2 combos need P_E, not just
    # the storey shear). V_lateral is a single scalar enveloping both
    # principal directions, so the shorter plan dimension is taken as the
    # lever arm -- the conservative attribution, since it maximises dP.
    OTM_kNm = comb.overturning_moment_kNm(seis.storey_forces, lateral_gov,
                                          wind_base_shear, h_total)
    if Lx <= Ly:
        otm_lever_arm_m, n_extreme_line = Lx, ny_bays + 1
    else:
        otm_lever_arm_m, n_extreme_line = Ly, nx_bays + 1
    dP_otm_kN = comb.overturning_axial_kN(OTM_kNm, otm_lever_arm_m,
                                          n_extreme_line)
    assumptions.append(
        "overturning axial: base OTM resisted by a portal couple between the "
        f"extreme column lines ({otm_lever_arm_m:.2f} m lever arm, "
        f"{n_extreme_line} columns per line) -> +-{dP_otm_kN:.1f} kN on edge/"
        "corner columns, interior columns unaffected (near the neutral axis)")
    assumptions.append(
        "lateral action is a single scalar envelope max(seismic VB, wind) "
        "with no per-direction split, so Ex and Ey carry the same magnitude "
        "in the combination table (conservative, not a directional analysis)")

    # Portal beam-end moment at a joint. Joint equilibrium: the column
    # moments above and below a joint are balanced by the beam moments left
    # and right of it, so a beam end picks up roughly one column moment.
    # The interior (2-share) column moment is used for every beam -- beams
    # are keyed by span/tributary, not by the column kind they frame into,
    # so the larger of the two is the conservative choice.
    M_E_beam_kNm = storey_shear_unit * 2 * storey_height_m / 2.0

    # ---------------- beams (unique by span/tributary) ----------------
    wall_kn_m = ld.wall_load_per_m(wall_thickness_m, storey_height_m)
    beams, beam_len_total = {}, 0.0
    crack_width_deemed_relied_on = False

    def trib_width(spacings, idx_line):
        left = spacings[idx_line - 1] / 2 if idx_line > 0 else 0.0
        right = spacings[idx_line] / 2 if idx_line < len(spacings) else 0.0
        return left + right

    for direction, spans, perp in (("x", x_spacings_m, y_spacings_m),
                                   ("y", y_spacings_m, x_spacings_m)):
        n_lines = len(perp) + 1
        n_spans_total = len(spans)
        # IS 456 cl 22.5.1: the Table 12/13 coefficients apply to beams of
        # uniform cross-section carrying substantially uniformly distributed
        # loads "over three or more spans which do not differ by more than 15
        # percent of the longest". Point loads never occur on these beams, and
        # b/D are constant per grid line, so the span regularity test is the
        # only run-time condition left to check.
        continuous_ok = (n_spans_total >= 3
                         and min(spans) >= 0.85 * max(spans))
        for line in range(n_lines):
            tw = trib_width(perp, line)
            span = max(spans)                       # worst span, conservative
            key = (direction, round(span, 2), round(tw, 2))
            if key in beams:
                beams[key]["count"] += 1
                beams[key]["grid_line_indices"].append(line)
                beam_len_total += sum(spans)
                continue
            w_dl = slab_dl * tw + wall_kn_m
            w_il = il * tw
            b = 230.0 if span <= 4.5 else 300.0
            D = max(math.ceil(span * 1000 / 12 / 25) * 25, 300)
            # Table 12/13 coefficients act on the *factored* DL and IL, each
            # with its own coefficient (that separation is what encodes the
            # pattern-loading envelope), so DL and IL are factored by 1.5
            # individually rather than pre-summed.
            kw = {}
            if continuous_ok:
                cm = continuous_moments(1.5 * w_dl, 1.5 * w_il, span)
                kw = {
                    "Mu_span_override_kNm": max(abs(cm["M_span_end"]),
                                                abs(cm["M_span_interior"])),
                    "Mu_support_override_kNm": max(
                        abs(cm["M_support_next_to_end"]),
                        abs(cm["M_support_interior"])),
                    "Vu_override_kN": max(abs(v) for k, v in cm.items()
                                          if k.startswith("V_")),
                }
            # ---- lateral (seismic) end moment, IS 1893 cl 6.3.1.2 ----------
            # Under a ductile-detailing design the frame's lateral moment
            # reverses, so a beam end must carry hogging in one direction and
            # sagging in the other. The lateral moment peaks at the *supports*
            # (mid-span is the portal point of contraflection), so it is added
            # to the support/hogging demand only, on top of whatever gravity
            # moment the Table 12/13 path (or the simply-supported fallback)
            # already produced. The 1.5 factor is the worst lateral factor in
            # the combination table -- a single always-added worst case rather
            # than a full 5-combo beam envelope (see PC-2 report).
            M_E_support_kNm = 0.0
            if seismic_detailing and M_E_beam_kNm > 0:
                M_E_support_kNm = 1.5 * M_E_beam_kNm
                if not continuous_ok:
                    # Simply-supported gravity fallback carries no support
                    # moment of its own; seed the span override with the
                    # unchanged gravity value so only the top face changes.
                    kw["Mu_span_override_kNm"] = 1.5 * (w_dl + w_il) * span ** 2 / 8.0
                kw["Mu_support_override_kNm"] = (
                    kw.get("Mu_support_override_kNm", 0.0) + M_E_support_kNm)
            # 'fixed' only selects the continuous L/d basic ratio (cl 23.2.1)
            # and a continuity-shaped SFD/BMD for the figure; the section is
            # designed from the Table 12/13 overrides above, not from analyze().
            sup = "fixed" if continuous_ok else "ss"
            # ---- IS 13920 ductile detailing checks (reversal) --------------
            # Wired here rather than inside design_beam() so the frozen
            # /v1/calc/beam contract is untouched. pt is the TENSION face at
            # the joint (top steel, hogging under lateral load) and pc the
            # compression face there (bottom steel) -- that pairing is what
            # makes the cl 6.2.3 ratio a reversal check.
            def _ductile(res: dict, b_mm: float, D_mm: float) -> list:
                if not seismic_detailing:
                    return []
                dsn = res["design"]
                pt_top = dsn.get("top_steel", {}).get("pt_percent", 0.0)
                pc_bot = dsn.get("pt_percent", 0.0)
                # cl 6.2.3 (pc >= 0.5*pt) is already enforced inside
                # design_beam() on areas for the same b,d -- identical
                # condition, so it is dropped here to avoid a duplicate
                # check name with a different wording in the same list.
                return [c for c in detailing.ductile_beam_checks(
                            b_mm, D_mm, pt_top, pc_bot)
                        if not c[0].startswith("compression steel")]

            r = None
            dchecks: list = []
            while D <= 1200:
                r = design_beam(span, w_dl, w_il, b, D, fck, fy,
                                support=sup, seismic=seismic_detailing,
                                cover=cov, exposure=exposure, **kw)
                # the ductile checks participate in the auto-sizing loop, not
                # just the report -- a pt > 2.5% at the joint is fixed by a
                # deeper section, so the sizer must be able to see it.
                dchecks = _ductile(r, b, D)
                if r["ok"] and all(v for _, v in dchecks):
                    break
                D += 50
            if seismic_detailing:
                r["ductile_beam_checks"] = dchecks
                r["checks"] = list(r["checks"]) + dchecks
                r["ok"] = r["ok"] and all(v for _, v in dchecks)
                r["M_lateral_support_kNm"] = M_E_support_kNm
            r["b_mm"], r["D_mm"] = b, D
            # crack-width deemed-to-satisfy (cl 43.1 note / cl 26.3.3(b)):
            # if the explicit Annex F calc fails but the bar-spacing
            # deemed-to-satisfy alternative passes, the design still relies
            # on that alternative route -- surface it in assumptions so a
            # reader knows crack control isn't resting on the explicit
            # number alone.
            cwid = r["design"].get("crack_width", {})
            if not cwid.get("ok") and cwid.get("deemed_to_satisfy", {}).get("ok"):
                crack_width_deemed_relied_on = True
            r["span_m"], r["trib_width_m"] = span, tw
            r["count"], r["n_spans"] = 1, n_spans_total
            # Table-12-eligibility flag (IS 456 cl 22.5.1) -- NOT the same as
            # design["continuous"] (set inside design_beam() whenever ANY
            # Mu_*_override_kNm is supplied, including a seismic-only
            # override on a non-Table-12 beam). Keep the names distinct so
            # downstream code can't confuse "genuinely continuous per Table
            # 12" with "override-triggered continuous mode".
            r["table12_continuous"] = continuous_ok
            # Where the beam's top (hogging) steel demand actually came
            # from, for correct clause attribution in report output --
            # design["top_steel"] presence alone doesn't distinguish the two.
            if continuous_ok:
                r["top_steel_source"] = "table12"
            elif seismic_detailing and M_E_support_kNm > 0:
                r["top_steel_source"] = "seismic_reversal"
            else:
                r["top_steel_source"] = None
            r["axis"] = direction
            r["grid_line_indices"] = [line]
            r["span_indices"] = list(range(n_spans_total))
            if figures_dir:
                _render_beam_figure(r, f"{key[0]}-span{key[1]}-trib{key[2]}",
                                    direction, span, tw, b, D,
                                    figures_dir, figures)
            r.pop("analysis", None)                 # arrays not JSON-safe
            beams[key] = r
            beam_len_total += sum(spans)

    beam_D_typ = max(bm["D_mm"] for bm in beams.values())

    # ---------------- columns (corner / edge / interior) ----------------
    n_corner = 4
    n_edge = n_cols - n_int - n_corner
    tx, ty = max(x_spacings_m), max(y_spacings_m)
    trib = {"interior": tx * ty, "edge": tx * ty / 2, "corner": tx * ty / 4}
    counts = {"interior": n_int, "edge": n_edge, "corner": n_corner}
    col_h_mm = storey_height_m * 1000

    # OH-tank roof-level column load: attributed to a single representative
    # roof-supporting column KIND (interior columns are the typical location
    # for an overhead tank/staircase head -- most central, shortest span to
    # the tank's own support beams; fall back to edge, then corner, for
    # small/single-bay grids where no interior column exists), split evenly
    # across that kind's column COUNT. This is a roof-only addition (applied
    # once, not multiplied by storeys like the rest of P_D below), consistent
    # with "OH tank sits on the roof" rather than every floor.
    oh_tank_kind = next((k for k in ("interior", "edge", "corner")
                        if counts.get(k, 0) > 0), None)
    oh_tank_kN_per_column = (oh_tank_weight_kN / counts[oh_tank_kind]
                             if oh_tank_kind and oh_tank_weight_kN > 0.0 else 0.0)

    intersections = {"interior": [], "edge": [], "corner": []}
    for i in range(nx_bays + 1):
        for j in range(ny_bays + 1):
            intersections[_column_kind(i, j, nx_bays, ny_bays)].append([i, j])

    # IS 13920 cl 7.1.2 trigger: beams are keyed by (direction, span, trib
    # width), not by which column kind they frame into, and the grid-line
    # indices they carry don't cleanly resolve to interior/edge/corner
    # without disproportionate new bookkeeping -- use the single largest
    # span in the building as a conservative proxy for every column kind.
    max_beam_span_m = max((bm["span_m"] for bm in beams.values()), default=0.0)

    columns = {}
    uplift_violations: list = []
    for kind, at in trib.items():
        if counts[kind] == 0:
            continue
        # Split the service takedown back into its dead and imposed parts --
        # the combination table factors them differently (0.9/1.2/1.5 on DL,
        # 0.0/1.2/1.5 on IL), so the pre-summed P_service is not enough.
        # P_D + P_IL == P_service exactly, so the gravity combo 1.5(DL+IL)
        # still reproduces the previous 1.5*P_service to the last bit.
        P_D = (slab_dl * at + wall_kn_m * (tx + ty) / 2) * storeys
        if kind == oh_tank_kind:
            P_D += oh_tank_kN_per_column
        P_IL = il * at * storeys
        P_IL_unreduced = P_IL  # save for later comparison/reporting if needed
        # Apply IS 875-2 cl 3.2 live-load reduction if enabled and occupancy allows
        ll_reduction_pct_applied = 0.0
        if apply_ll_reduction and occupancy not in NEVER_REDUCE_OCCUPANCIES:
            ll_reduction_pct_applied = tables.ll_reduction_pct(storeys)
            P_IL = P_IL * (1.0 - ll_reduction_pct_applied / 100.0)
        P_service = P_D + P_IL
        share = 2 if kind == "interior" else 1
        M_lat = storey_shear_unit * share * storey_height_m / 2  # kNm portal
        # interior columns sit near the neutral axis of overturning
        P_E = 0.0 if kind == "interior" else dP_otm_kN
        env = comb.combination_envelope(P_D_kN=P_D, M_D_kNm=0.0,
                                        P_IL_kN=P_IL, M_IL_kNm=0.0,
                                        P_E_kN=P_E, M_E_kNm=M_lat)
        # Only the compression combos can be run through design_column(),
        # which assumes an axially compressed section. A net-tension combo is
        # reported via uplift_governs instead (see below).
        design_combos = [c for c in env["combos"] if c["Pu_kN"] > 0.0]
        b = D = 300.0
        nb, dia = 8, 16
        r = None
        gov = None
        for _ in range(14):
            trials = [
                (c, design_column(b, D, fck, fy, Pu_kN=c["Pu_kN"],
                                  Mux_kNm=c["Mux_kNm"], Muy_kNm=c["Muy_kNm"],
                                  L_unsupported_mm=col_h_mm - beam_D_typ,
                                  n_bars=nb, bar_dia=dia,
                                  seismic=seismic_detailing, cover=cov,
                                  max_beam_span_m=max_beam_span_m))
                for c in design_combos
            ]
            # every combination must pass; the reported one is the worst.
            # Taking the max P-M interaction (rather than simply the max Pu)
            # matters because a column is not monotonically worse with axial
            # load -- below the balanced point more compression *raises*
            # moment capacity, so the max-Pu row is not always governing.
            gov, r = max(trials, key=lambda t: (not t[1].ok,
                                                t[1].data.get("interaction", 0.0)))
            if r.ok:
                break
            if dia < 25:
                dia += 4 if dia == 16 else 5
            else:
                b = D = D + 50
                dia = 16
        columns[kind] = {"ok": r.ok, "checks": r.checks, "data": r.data,
                         "b_mm": b, "D_mm": D, "bars": f"{nb}-{dia} dia",
                         "n_bars": nb, "bar_dia": dia,
                         # Headline design actions are the ENVELOPE maxima,
                         # not the interaction-governing row: every combo in
                         # the table was designed for, and the maxima are what
                         # a reader/BOQ/PDF means by "the design axial load"
                         # and "the design moment". The interaction-governing
                         # row is reported separately below.
                         "Pu_kN": env["Pu_max_kN"], "P_service_kN": P_service,
                         "M_lateral_kNm": M_lat, "count": counts[kind],
                         "grid_intersections": intersections[kind],
                         # ---- additive: combination envelope (PC-2) ----
                         "P_dead_kN": P_D, "P_imposed_kN": P_IL,
                         "P_overturning_kN": P_E,
                         "Pu_gravity_kN": 1.5 * P_service,
                         # NOTE: no top-level "Mux_kNm"/"Muy_kNm" pair here
                         # (Important 6). The load-combination envelope never
                         # carries simultaneous Mux+Muy (each lateral family
                         # expands into an x-only row and a y-only row -- see
                         # combinations.py), so a (Pu_kN, Mux_max, Muy_max)
                         # triple built from independent per-axis maxima
                         # would correspond to no combo row the building was
                         # actually designed against, and is unsafe to feed
                         # back into /v1/calc/column as if it were one.
                         # Mux_envelope_max_kNm/Muy_envelope_max_kNm below are
                         # the same envelope-maxima data, kept for diagnostics
                         # but named so they can't be mistaken for a
                         # same-row triple with Pu_kN. For the physically
                         # coherent triple, use
                         # Pu_governing_kN/Mux_governing_kNm/Muy_governing_kNm
                         # below -- those three are read off the SAME
                         # interaction-governing row.
                         "governing_combination": gov["name"],
                         "Pu_governing_kN": gov["Pu_kN"],
                         "Mux_governing_kNm": gov["Mux_kNm"],
                         "Muy_governing_kNm": gov["Muy_kNm"],
                         "Pu_max_kN": env["Pu_max_kN"],
                         "Pu_min_kN": env["Pu_min_kN"],
                         "Mux_envelope_max_kNm": env["Mux_max_kNm"],
                         "Muy_envelope_max_kNm": env["Muy_max_kNm"],
                         "uplift_governs": env["uplift_governs"],
                         "combinations": env["combos"]}
        if env["uplift_governs"]:
            # Disclosed scope boundary: no tension-column design exists in
            # this library, so the compression checks above do NOT cover
            # this column's governing condition.
            uplift_violations.append(_violation(
                member_type="column", axis=None,
                grid_ref=f"column class {kind}", span_m=None,
                check=("net tension under 0.9DL-1.5EL (IS 1893 cl 6.3.1.2) — "
                       "uplift/anchorage design not performed by this model"),
                actual=env["Pu_min_kN"], limit=0.0, unit="kN",
                remedy_hint="review_inputs"))
        if figures_dir:
            _render_column_figure(kind, b, D, fck, fy, nb, dia, r, gov["Pu_kN"],
                                  counts[kind], figures_dir, figures, cover=cov)

    # ---------------- footings ----------------
    footings = {}
    for kind, col in columns.items():
        f = design_isolated_footing(
            P_service_kN=col["P_service_kN"],
            # col["M_lateral_kNm"] (M_lat) is passed to comb.combination_
            # envelope() as M_E_kNm, whose docstring states its inputs are
            # already unfactored/service-level -- PC-2's D/IL/E-split
            # machinery both computes and consumes it that way. The
            # stale "/1.2" here predates that split (when this value was
            # still an ultimate/factored moment needing de-factoring) and
            # has not tracked the refactor: dividing an already-unfactored
            # moment by 1.2 under-states the service moment fed to the
            # footing design. Pass it through unmodified.
            M_service_kNm=col["M_lateral_kNm"],
            sbc_kpa=sbc_kpa, col_b_mm=col["b_mm"], col_D_mm=col["D_mm"],
            fck=fck, fy=fy)
        fd = asdict(f) if is_dataclass(f) else f
        fd["count"] = col["count"]
        fd["grid_intersections"] = col["grid_intersections"]
        footings[kind] = fd
        if figures_dir and fd.get("ok") and "q_min_service_kPa" in fd.get("data", {}):
            _render_footing_figure(kind, fd, col["count"], figures_dir, figures)

    # ---------------- combined-footing detection (edge_setback_m) ----------
    # Detects when an edge/corner column's isolated footing would project
    # past the plot boundary (half its plan length > edge_setback_m from the
    # column grid line) and, when triggered, ALSO runs a full two-column
    # combined-footing design (design_combined_footing() already exists in
    # footing.py -- confirmed present, contrary to the task brief's
    # from-memory claim that no such function exists; see PD-5 report).
    #
    # Scope decision: the combined-footing result is attached under the new
    # result["combined_footings"] key (supplementary/informational) rather
    # than replacing the entry in result["footings"] -- this building model
    # designs one representative footing per column KIND (interior/edge/
    # corner), not per grid intersection, so "replacing" the isolated
    # footing would silently apply a combined-footing section to every
    # column of that kind (including ones nowhere near the plot boundary),
    # and would also require reworking the BOQ/quantities aggregation (which
    # assumes every footings[kind] entry is an isolated-footing shape) --
    # out of scope for the M budget. The isolated footings[kind] entry is
    # therefore left exactly as-is; combined_footings is additive.
    combined_footings: dict = {}
    combined_footing_violations: list = []
    if edge_setback_m is not None:
        # nearest-neighbour spacing for the combined-footing beam span: the
        # first bay in whichever direction is tighter is used as a
        # conservative (shorter, hence stiffer-moment) representative
        # spacing -- this model has no per-intersection bay bookkeeping for
        # edge/corner footings, only kind-level aggregates.
        neighbour_spacing_m = min(x_spacings_m[0], y_spacings_m[0])
        for kind in ("corner", "edge"):
            if kind not in footings:
                continue
            fd = footings[kind]
            L_m = fd.get("data", {}).get("L_m")
            if L_m is None:
                continue
            half_L_m = L_m / 2.0
            if half_L_m <= edge_setback_m:
                continue
            combined_footing_violations.append(_violation(
                member_type="footing", axis=None,
                grid_ref=f"footing class {kind}", span_m=None,
                check=(f"isolated footing L/2 <= edge_setback_m (would "
                       "project past the plot boundary) -- combined "
                       "footing computed, see result['combined_footings']"),
                actual=half_L_m, limit=edge_setback_m, unit="m",
                remedy_hint="review_inputs"))
            fallback_kind = "edge" if kind == "corner" else "corner"
            neighbour_kind = "interior" if "interior" in columns else (
                fallback_kind if fallback_kind in columns else None)
            col_a, col_b_ = columns[kind], columns.get(neighbour_kind, columns[kind])
            cf = design_combined_footing(
                P1_kN=col_a["P_service_kN"], P2_kN=col_b_["P_service_kN"],
                spacing_m=neighbour_spacing_m, sbc_kpa=sbc_kpa,
                col1_mm=col_a["b_mm"], col2_mm=col_b_["b_mm"],
                fck=fck, fy=fy, edge_limit_m=edge_setback_m)
            cf.pop("x", None); cf.pop("V", None); cf.pop("M", None)  # numpy arrays, not JSON-safe
            cf["paired_kind"] = neighbour_kind or kind
            cf["spacing_assumption_m"] = neighbour_spacing_m
            combined_footings[kind] = cf
        if combined_footings:
            assumptions.append(
                "combined footing(s) computed for edge/corner column kind(s) "
                f"{sorted(combined_footings)} whose isolated footing would "
                f"exceed edge_setback_m={edge_setback_m:.2f} m -- see "
                "result['combined_footings']; the isolated footings[] entry "
                "for that kind is left unchanged (informational, not a "
                "replacement -- see design_building() docstring)")

    # ---------------- quantities (BOQ-shaped) ----------------
    def slab_steel(p):
        if p["type"] == "one-way":
            ast = p["main"]["Ast_prov"] + p["distribution"]["Ast_req"]
        else:
            ast = sum(s.get("Ast_prov", 0) for s in p["strips"].values()) / 2
        a = p["lx_m"] * p["ly_m"] if p["type"] == "two-way" else p["lx_m"] ** 2
        return ast * 1e-6 * a * STEEL_DENSITY * p["count"]  # both faces approx

    conc = {"slabs": area * slab_D / 1000 * storeys,
            "beams": sum(bm["b_mm"] * bm["D_mm"] * 1e-6 * bm["span_m"]
                         * bm["n_spans"] * bm["count"]
                         for bm in beams.values()) * storeys,
            "columns": sum(c["b_mm"] * c["D_mm"] * 1e-6 * storey_height_m
                           * storeys * c["count"] for c in columns.values()),
            "footings": sum(f["data"]["L_m"] * f["data"]["B_m"]
                            * f["data"]["D_overall_mm"] / 1000 * f["count"]
                            for f in footings.values())}
    def beam_steel_area(bm: dict) -> float:
        """Longitudinal bar area per beam cross-section (mm2). Continuous
        beams also carry a top (hogging) layer, which must be billed or the
        BOQ silently under-reports them."""
        d = bm.get("design")
        if not d or "Ast_prov_mm2" not in d:
            return 2 * 314.0
        return d["Ast_prov_mm2"] + d.get("top_steel", {}).get("Ast_prov_mm2", 0.0)

    steel = {"slabs": sum(slab_steel(p) for p in panels.values()) * storeys,
             "beams": sum(beam_steel_area(bm)
                          * 1e-6 * bm["span_m"] * bm["n_spans"]
                          * bm["count"] * STEEL_DENSITY
                          for bm in beams.values()) * storeys,
             "columns": sum(c["n_bars"] * math.pi * c["bar_dia"] ** 2 / 4
                            * 1e-6 * storey_height_m * storeys
                            * STEEL_DENSITY * c["count"]
                            for c in columns.values()),
             "footings": sum((f["data"]["Ast_x_mm2"] + f["data"]["Ast_y_mm2"])
                             * 1e-6 * max(f["data"]["L_m"], f["data"]["B_m"])
                             * STEEL_DENSITY * f["count"]
                             for f in footings.values())}
    steel = {k: v * WASTE_FACTOR for k, v in steel.items()}
    quantities = {
        "concrete_m3": {**{k: round(v, 2) for k, v in conc.items()},
                        "total": round(sum(conc.values()), 2)},
        "steel_kg": {**{k: round(v, 1) for k, v in steel.items()},
                     "total": round(sum(steel.values()), 1)},
        "grade": f"M{fck:.0f} / Fe{fy:.0f}",
    }

    all_checks_ok = (all(p["ok"] for p in panels.values())
                     and all(bm["ok"] for bm in beams.values())
                     and all(c["ok"] for c in columns.values())
                     and all(f["ok"] for f in footings.values()))

    # ---------------- grid geometry (cumulative, from 0.0) ----------------
    x_coords_m, cx = [0.0], 0.0
    for s in x_spacings_m:
        cx += s
        x_coords_m.append(round(cx, 4))
    y_coords_m, cy = [0.0], 0.0
    for s in y_spacings_m:
        cy += s
        y_coords_m.append(round(cy, 4))
    grid_lines = {"x_coords_m": x_coords_m, "y_coords_m": y_coords_m}

    violations = _collect_violations(panels, beams, columns, footings, sbc_kpa)
    violations += uplift_violations
    violations += combined_footing_violations
    if fck < exp["min_fck"]:
        # Building-level, not per-member — no existing member_type="building"
        # (or equivalent whole-building-scope) convention found elsewhere in
        # this file's violation helpers, so this establishes the precedent.
        violations.append(_violation(
            member_type="building", axis=None, grid_ref="whole building",
            span_m=None, check=f"fck >= exposure min grade ({exposure})",
            actual=fck, limit=exp["min_fck"], unit="MPa",
            remedy_hint="increase_grade"))

    if crack_width_deemed_relied_on:
        assumptions.append(
            "crack-width SLS (IS 456 cl 43.1): at least one beam's explicit "
            "Annex F crack-width calculation exceeds the exposure limit, but "
            "the cl 26.3.3(b) deemed-to-satisfy bar-spacing rule passes for "
            "it -- that beam's crack control relies on the deemed-to-satisfy "
            "route, not the explicit number")

    # ---------------- parapet (roof-level only, report-only) ----------------
    parapet_result = None
    if parapet_height_m is not None:
        pr = design_parapet(height_m=parapet_height_m)
        parapet_result = {"ok": pr.ok, "checks": pr.checks, "data": pr.data}
        assumptions.append(
            f"roof-level parapet ({parapet_height_m:.2f} m high) designed for "
            "the IS 875-2 minimum 0.75 kN/m lateral barrier load -- "
            "result['parapet']; report-only, does not feed into the roof "
            "slab/column/seismic load chain (see design_building() docstring)")

    # all_checks_ok only reflects panels/beams/columns/footings' own "ok"
    # flags, computed before uplift/combined-footing/exposure-grade
    # violations are folded into `violations` above -- fold them back in so
    # result["ok"] == (result["violations"] == []) always holds.
    all_checks_ok = all_checks_ok and not violations

    result = {
        "ok": all_checks_ok,
        "inputs": {"grid_x_m": x_spacings_m, "grid_y_m": y_spacings_m,
                   "storeys": storeys, "storey_height_m": storey_height_m,
                   "occupancy": occupancy, "seismic_zone": seismic_zone,
                   "soil": soil, "terrain_category": terrain_category,
                   "sbc_kpa": sbc_kpa, "fck": fck, "fy": fy,
                   "exposure": exposure},
        "lateral": {"governing": lateral_gov,
                    "seismic_VB_kN": round(seis.VB, 1),
                    "seismic_Ah": seis.Ah, "seismic_Ta_s": round(seis.Ta, 3),
                    "seismic_Ta_x_s": round(seis_x.Ta, 3),
                    "seismic_Ah_x": seis_x.Ah,
                    "seismic_Ta_y_s": round(seis_y.Ta, 3),
                    "seismic_Ah_y": seis_y.Ah,
                    "wind_pd_kN_m2": round(wind.pd, 3),
                    "wind_base_shear_kN": round(wind_base_shear, 1),
                    "R": 5.0 if seismic_detailing else 3.0,
                    "seismic_detailing_IS13920": seismic_detailing},
        "slabs": {str(k): v for k, v in panels.items()},
        "beams": {f"{k[0]}-span{k[1]}-trib{k[2]}": v for k, v in beams.items()},
        "columns": columns,
        "footings": footings,
        "quantities": quantities,
        "assumptions": assumptions,
        "grid_lines": grid_lines,
        "violations": violations,
        "figures": figures,
    }
    if parapet_result is not None:
        result["parapet"] = parapet_result
    if oh_tank_capacity_litres is not None:
        result["oh_tank"] = {
            "capacity_litres": oh_tank_capacity_litres,
            "estimated_weight_kN": round(oh_tank_weight_kN, 2),
            "structure_allowance_factor": OH_TANK_STRUCTURE_FACTOR,
            "supporting_column_kind": oh_tank_kind,
            "load_per_column_kN": round(oh_tank_kN_per_column, 2),
        }
    if combined_footings:
        result["combined_footings"] = combined_footings
    return result


def building_report_pdf(result: dict, path: str = "out/building_report.pdf",
                        figures: dict | list | None = None) -> str:
    """Consolidated PDF from a design_building() result.

    Every unique member TYPE (e.g. "interior columns", "x-dir span 4.00 m
    beams", "corner footings") gets its own reinforcement detail table, its
    clause-referenced checks, and — for beams/columns/footings — its SFD/BMD,
    P-M interaction, or base-pressure PNG (from figures_dir on
    design_building()). Deliberately long: this is the as-designed record an
    engineer signs off, not a pass/fail summary.

    figures: the dict keyed "{group}:{key}" -> (png_path, caption) returned
    by design_building(figures_dir=...). A bare list of (path, caption) is
    still accepted for backwards compatibility (dumped at the end, unkeyed).
    """
    from ..pdfreport import PdfReport

    fig_map = figures if isinstance(figures, dict) else {}
    trailing_figs = figures if isinstance(figures, list) else []

    p = PdfReport("Building structural design — IS 456:2000 LSM",
                  ["IS456", "IS875-3", "IS1893-1", "IS13920", "SP16"])
    i = result["inputs"]
    p.add_section("Inputs")
    p.add_table(["Item", "Value"], [
        ["Grid", f"x: {i['grid_x_m']} m, y: {i['grid_y_m']} m"],
        ["Storeys", f"{i['storeys']} @ {i['storey_height_m']} m"],
        ["Materials", f"M{i['fck']:.0f} / Fe{i['fy']:.0f}, {i['exposure']}"],
        ["Seismic / soil / SBC",
         f"zone {i['seismic_zone']} / {i['soil']} / {i['sbc_kpa']} kPa"],
    ])
    lat = result["lateral"]
    p.add_section("Lateral analysis")
    p.add_table(["Item", "Value"], [
        ["Governing", lat["governing"]],
        ["Seismic VB", f"{lat['seismic_VB_kN']} kN (Ah={lat['seismic_Ah']})"],
        ["Wind base shear", f"{lat['wind_base_shear_kN']} kN"],
        ["IS 13920 detailing", str(lat["seismic_detailing_IS13920"])],
    ])
    for group, title in (("slabs", "Slab panels"), ("beams", "Beams"),
                         ("columns", "Columns"), ("footings", "Footings")):
        p.add_section(title)
        detail_fn = _DETAIL_ROWS_BY_GROUP[group]
        for key, el in result[group].items():
            p.add_subsection(f"<b>{key}</b> (x{el.get('count', 1)})")
            try:
                rows = detail_fn(el)
            except Exception:
                rows = []
            if rows:
                p.add_table(["Item", "Value"], rows)
            p.add_checks(el["checks"])
            fig = fig_map.get(f"{group}:{key}")
            if fig:
                p.add_figure(fig[0], fig[1])
    q = result["quantities"]
    p.add_section("Quantity takeoff")
    p.add_table(["Element", "Concrete (m3)", "Steel (kg)"],
                [[k, q["concrete_m3"].get(k, "-"), q["steel_kg"].get(k, "-")]
                 for k in ("slabs", "beams", "columns", "footings", "total")])
    p.add_section("Assumptions")
    for a in result["assumptions"]:
        p.add_line(f"• {a}")
    for fig in trailing_figs:
        png, caption = fig if isinstance(fig, (list, tuple)) else (fig, "")
        p.add_figure(png, caption)
    return p.save(path)
