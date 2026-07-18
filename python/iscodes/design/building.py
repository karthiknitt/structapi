"""Whole-building RCC design chain: column grid in -> full structural design out.

The PlanForge integration workhorse (docs/PLANFORGE-INTEGRATION.md Phase B):
loads takedown (IS 875-1/2, 875-3 wind, 1893 seismic) -> two-way slab panels
(Table 26 case by position) -> tributary beams -> columns (gravity + portal-
frame lateral moments, IS 13920 overlay) -> isolated footings -> quantity
takeoff (BOQ-shaped) -> consolidated figures + PDF-ready sections.

Deliberate v1 simplifications (all echoed in result["assumptions"]):
- Regular orthogonal grid; beams on every grid line; columns at intersections.
- Beams designed as simply supported on the worst span (conservative vs
  Table 12 continuity).
- Lateral: equivalent-static seismic and static wind computed; the larger
  base shear governs; portal-frame moment distribution between columns.
- Steel quantity from designed Ast x member length x 7850 kg/m3 + 10% waste.

Units: m, kN externally; mm/N internally per iscodes convention.
"""

from __future__ import annotations

import math
import os
from dataclasses import asdict, is_dataclass

from .. import loads as ld
from .. import tables
from . import flexure
from .column import ColumnSection, design_column, interaction_curve, rect_bar_layout
from .footing import design_isolated_footing
from .slab import design_one_way_slab, design_two_way_slab
from .beam import design_beam

STEEL_DENSITY = 7850.0  # kg/m3
WASTE_FACTOR = 1.10


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
                          figures_dir: str, figures: dict) -> None:
    """P-M interaction PNG for one column kind (corner/edge/interior)."""
    try:
        from ..plotting import plot_pm_interaction
        # cover=40.0, tie_dia=8.0 — design_column()'s own defaults, which the
        # building chain never overrides, so the section drawn here matches
        # the section actually designed.
        cc = 40.0 + 8.0 + dia / 2.0
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


def _panel_case(i: int, j: int, nx: int, ny: int) -> int:
    """IS 456 Table 26 case from panel position in the grid."""
    edge_x = i == 0 or i == nx - 1
    edge_y = j == 0 or j == ny - 1
    if edge_x and edge_y:
        return 4  # two adjacent edges discontinuous (corner panel)
    if edge_x or edge_y:
        return 2 if edge_y else 3  # one short/long edge discontinuous (approx)
    return 1  # interior


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
        elif name.startswith("IS 13920 min width"):
            out.append(_violation("beam", direction, grid_ref, span, name,
                                  bm["b_mm"], tables.DUCTILE["beam_min_b"],
                                  "mm", "increase_section"))
        elif name.startswith("IS 13920 pt"):
            out.append(_violation("beam", direction, grid_ref, span, name,
                                  d["pt_percent"] / 100.0,
                                  tables.DUCTILE["beam_max_pt"], "ratio",
                                  "add_grid_line"))
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
        elif name.startswith("min width 300"):
            out.append(_violation("column", None, grid_ref, None, name,
                                  min(col["b_mm"], col["D_mm"]),
                                  tables.DUCTILE["column_min_b_storeys"], "mm",
                                  "increase_section"))
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
                    soil: str = "medium", sbc_kpa: float = 200.0,
                    fck: float = 25.0, fy: float = 500.0,
                    exposure: str = "moderate",
                    finish_kn_m2: float = 1.5,
                    wall_thickness_m: float = 0.23,
                    seismic_detailing: bool | None = None,
                    figures_dir: str | None = None) -> dict:
    """Design every unique element of a regular RC frame building.

    figures_dir: when set, renders an SFD/BMD PNG per unique beam, a P-M
    interaction PNG per column kind, and a base-pressure PNG per footing
    kind into this directory, and returns their paths+captions in
    result["figures"]. Left None (default) to skip rendering entirely —
    matches every pre-existing caller/test exactly.
    """
    nx_bays, ny_bays = len(x_spacings_m), len(y_spacings_m)
    if nx_bays < 1 or ny_bays < 1 or storeys < 1:
        raise ValueError("need >=1 bay each way and >=1 storey")
    Lx, Ly = sum(x_spacings_m), sum(y_spacings_m)
    area = Lx * Ly
    h_total = storeys * storey_height_m
    assumptions = [
        "regular orthogonal grid; columns at all intersections; beams on all grid lines",
        "beams designed simply supported on worst span (conservative)",
        f"wall load: {wall_thickness_m*1000:.0f} mm brick on every beam, full storey height",
        "portal-frame lateral distribution (interior columns 2x exterior share)",
        "steel mass = designed Ast x length x 7850 kg/m3 x 1.10 waste",
        "column moments: lateral portal moments + minimum eccentricity per IS 456 cl 25.4",
    ]
    il = ld.imposed_load(occupancy)
    if seismic_detailing is None:
        seismic_detailing = seismic_zone.upper() in ("III", "IV", "V")
    figures: dict = {}

    # ---------------- slabs (unique panels) ----------------
    panels, panel_map = {}, {}
    for i, sx in enumerate(x_spacings_m):
        for j, sy in enumerate(y_spacings_m):
            case = _panel_case(i, j, nx_bays, ny_bays)
            lx, ly = min(sx, sy), max(sx, sy)
            key = (round(lx, 2), round(ly, 2), case)
            panel_map[(i, j)] = key
            if key in panels:
                panels[key]["count"] += 1
                continue
            if ly / lx > 2.0:
                r = design_one_way_slab(lx, finish_kn_m2, il, fck, fy,
                                        support="continuous")
                r["type"] = "one-way"
            else:
                r = design_two_way_slab(lx, ly, finish_kn_m2, il, fck, fy,
                                        case=case)
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

    # ---------------- beams (unique by span/tributary) ----------------
    wall_kn_m = ld.wall_load_per_m(wall_thickness_m, storey_height_m)
    beams, beam_len_total = {}, 0.0

    def trib_width(spacings, idx_line):
        left = spacings[idx_line - 1] / 2 if idx_line > 0 else 0.0
        right = spacings[idx_line] / 2 if idx_line < len(spacings) else 0.0
        return left + right

    for direction, spans, perp in (("x", x_spacings_m, y_spacings_m),
                                   ("y", y_spacings_m, x_spacings_m)):
        n_lines = len(perp) + 1
        for line in range(n_lines):
            tw = trib_width(perp, line)
            span = max(spans)                       # worst span, conservative
            key = (direction, round(span, 2), round(tw, 2))
            n_spans_total = len(spans)
            if key in beams:
                beams[key]["count"] += 1
                beams[key]["grid_line_indices"].append(line)
                beam_len_total += sum(spans)
                continue
            w_dl = slab_dl * tw + wall_kn_m
            w_il = il * tw
            b = 230.0 if span <= 4.5 else 300.0
            D = max(math.ceil(span * 1000 / 12 / 25) * 25, 300)
            r = None
            while D <= 1200:
                r = design_beam(span, w_dl, w_il, b, D, fck, fy,
                                support="ss", seismic=seismic_detailing)
                if r["ok"]:
                    break
                D += 50
            r["b_mm"], r["D_mm"] = b, D
            r["span_m"], r["trib_width_m"] = span, tw
            r["count"], r["n_spans"] = 1, n_spans_total
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

    # ---------------- lateral loads ----------------
    floor_dead = (slab_dl + 2.0) * area             # +2 kN/m2 frame allowance
    storey_weights = [ld.seismic_weight(floor_dead, il * area, il,
                                        is_roof=(k == storeys - 1))
                     for k in range(storeys)]
    heights = [(k + 1) * storey_height_m for k in range(storeys)]
    seis = ld.base_shear(storey_weights, heights, zone=seismic_zone,
                         soil=soil, I=1.0, R=5.0 if seismic_detailing else 3.0)
    Vb = basic_wind_speed or (tables.BASIC_WIND_SPEED.get((city or "").lower(), 39))
    wind = ld.wind_pressure(Vb, h_total, terrain_category)
    wind_base_shear = 1.2 * wind.pd * Ly * h_total   # Cf=1.2 on broader face
    lateral_gov = "seismic" if seis.VB >= wind_base_shear else "wind"
    V_lateral = max(seis.VB, wind_base_shear)

    # ---------------- columns (corner / edge / interior) ----------------
    n_cols = (nx_bays + 1) * (ny_bays + 1)
    n_int = max(nx_bays - 1, 0) * max(ny_bays - 1, 0)
    n_corner = 4
    n_edge = n_cols - n_int - n_corner
    tx, ty = max(x_spacings_m), max(y_spacings_m)
    trib = {"interior": tx * ty, "edge": tx * ty / 2, "corner": tx * ty / 4}
    counts = {"interior": n_int, "edge": n_edge, "corner": n_corner}
    # portal frame: interior columns take 2 shares, exterior 1
    shares = 2 * n_int + (n_cols - n_int)
    storey_shear_unit = V_lateral / shares
    col_h_mm = storey_height_m * 1000

    intersections = {"interior": [], "edge": [], "corner": []}
    for i in range(nx_bays + 1):
        for j in range(ny_bays + 1):
            intersections[_column_kind(i, j, nx_bays, ny_bays)].append([i, j])

    columns = {}
    for kind, at in trib.items():
        if counts[kind] == 0:
            continue
        P_service = (w_floor_service * at + wall_kn_m * (tx + ty) / 2) * storeys
        Pu = 1.5 * P_service
        share = 2 if kind == "interior" else 1
        M_lat = storey_shear_unit * share * storey_height_m / 2  # kNm portal
        b = D = 300.0
        nb, dia = 8, 16
        r = None
        for _ in range(14):
            r = design_column(b, D, fck, fy, Pu_kN=Pu,
                              Mux_kNm=M_lat, Muy_kNm=0.3 * M_lat,
                              L_unsupported_mm=col_h_mm - beam_D_typ,
                              n_bars=nb, bar_dia=dia,
                              seismic=seismic_detailing)
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
                         "Pu_kN": Pu, "P_service_kN": P_service,
                         "M_lateral_kNm": M_lat, "count": counts[kind],
                         "grid_intersections": intersections[kind]}
        if figures_dir:
            _render_column_figure(kind, b, D, fck, fy, nb, dia, r, Pu,
                                  counts[kind], figures_dir, figures)

    # ---------------- footings ----------------
    footings = {}
    for kind, col in columns.items():
        f = design_isolated_footing(
            P_service_kN=col["P_service_kN"],
            M_service_kNm=col["M_lateral_kNm"] / 1.2,   # service-level moment
            sbc_kpa=sbc_kpa, col_b_mm=col["b_mm"], col_D_mm=col["D_mm"],
            fck=fck, fy=fy)
        fd = asdict(f) if is_dataclass(f) else f
        fd["count"] = col["count"]
        fd["grid_intersections"] = col["grid_intersections"]
        footings[kind] = fd
        if figures_dir and fd.get("ok") and "q_min_service_kPa" in fd.get("data", {}):
            _render_footing_figure(kind, fd, col["count"], figures_dir, figures)

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
    steel = {"slabs": sum(slab_steel(p) for p in panels.values()) * storeys,
             "beams": sum((bm["design"]["Ast_prov_mm2"]
                           if "design" in bm and "Ast_prov_mm2" in bm.get("design", {})
                           else 2 * 314) * 1e-6 * bm["span_m"] * bm["n_spans"]
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

    return {
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
