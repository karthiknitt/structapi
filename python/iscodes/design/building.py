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
from dataclasses import asdict, is_dataclass

from .. import loads as ld
from .. import tables
from .column import design_column
from .footing import design_isolated_footing
from .slab import design_one_way_slab, design_two_way_slab
from .beam import design_beam

STEEL_DENSITY = 7850.0  # kg/m3
WASTE_FACTOR = 1.10


def _panel_case(i: int, j: int, nx: int, ny: int) -> int:
    """IS 456 Table 26 case from panel position in the grid."""
    edge_x = i == 0 or i == nx - 1
    edge_y = j == 0 or j == ny - 1
    if edge_x and edge_y:
        return 4  # two adjacent edges discontinuous (corner panel)
    if edge_x or edge_y:
        return 2 if edge_y else 3  # one short/long edge discontinuous (approx)
    return 1  # interior


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
                    seismic_detailing: bool | None = None) -> dict:
    """Design every unique element of a regular RC frame building."""
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
                         "M_lateral_kNm": M_lat, "count": counts[kind]}

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
        footings[kind] = fd

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
    }


def building_report_pdf(result: dict, path: str = "out/building_report.pdf",
                        figures: list | None = None) -> str:
    """Consolidated PDF from a design_building() result."""
    from ..pdfreport import PdfReport

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
        for key, el in result[group].items():
            p.add_line(f"<b>{key}</b> (x{el.get('count', 1)})")
            p.add_checks(el["checks"])
    q = result["quantities"]
    p.add_section("Quantity takeoff")
    p.add_table(["Element", "Concrete (m3)", "Steel (kg)"],
                [[k, q["concrete_m3"].get(k, "-"), q["steel_kg"].get(k, "-")]
                 for k in ("slabs", "beams", "columns", "footings", "total")])
    p.add_section("Assumptions")
    for a in result["assumptions"]:
        p.add_line(f"• {a}")
    for fig in figures or []:
        png, caption = fig if isinstance(fig, (list, tuple)) else (fig, "")
        p.add_figure(png, caption)
    return p.save(path)
