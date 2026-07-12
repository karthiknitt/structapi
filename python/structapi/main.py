"""structapi — FastAPI app. Run: uvicorn structapi.main:app --port 8080."""

from __future__ import annotations

import dataclasses
import logging
import time

from fastapi import Depends, FastAPI, Request

import iscodes
from iscodes import loads as ld
from iscodes.design import mix as mixmod
from iscodes.design import slab as slabmod
from iscodes.design import tank as tankmod
from iscodes.design.beam import design_beam
from iscodes.design.building import building_report_pdf, design_building
from iscodes.design.column import (ColumnSection, design_column,
                                   interaction_curve, rect_bar_layout)
from iscodes.design.footing import (design_combined_footing,
                                    design_isolated_footing)
from . import API_VERSION
from .artifacts import pdf_artifact, png_artifact
from .envelope import envelope, sanitize
from .schemas import (BeamIn, BuildingIn, CircularTankIn, ColumnIn,
                      CombinationsIn, CombinedFootingIn, IsolatedFootingIn,
                      MixIn, OneWaySlabIn, SeismicIn, SumpIn,
                      TankWallSectionIn, TwoWaySlabIn, WindIn)
from .security import require_api_key

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(name)s %(message)s")
log = logging.getLogger("structapi")

app = FastAPI(
    title="structapi",
    version=API_VERSION,
    description=("Deterministic IS-code RCC design API over the iscodes "
                 "engine. Contract: docs/PLANFORGE-INTEGRATION.md. "
                 "All results carry clause-referenced checks and an "
                 "engineering disclaimer."),
)


@app.middleware("http")
async def request_log(request: Request, call_next):
    t0 = time.perf_counter()
    response = await call_next(request)
    corr = getattr(request.state, "correlation_id", "") or "-"
    caller = getattr(request.state, "caller", "-")
    log.info("%s %s -> %s (%.0f ms) key=%s corr=%s",
             request.method, request.url.path, response.status_code,
             (time.perf_counter() - t0) * 1000, caller, corr)
    if corr != "-" and corr:
        response.headers["x-correlation-id"] = corr
    return response


@app.get("/v1/health")
def health():
    return {"status": "ok", "api_version": API_VERSION,
            "iscodes_version": iscodes.__version__}


# ------------------------------- loads -----------------------------------

@app.post("/v1/calc/loads/combinations", dependencies=[Depends(require_api_key)])
def loads_combinations(body: CombinationsIn):
    combos = ld.combinations(**body.model_dump())
    return envelope(True, [], {"combinations": combos,
                               "governing": combos[0] if combos else None})


@app.post("/v1/calc/loads/wind", dependencies=[Depends(require_api_key)])
def loads_wind(body: WindIn):
    r = ld.wind_pressure(**body.model_dump())
    return envelope(True, [], dataclasses.asdict(r))


@app.post("/v1/calc/loads/seismic", dependencies=[Depends(require_api_key)])
def loads_seismic(body: SeismicIn):
    r = ld.base_shear(**body.model_dump())
    return envelope(True, [], dataclasses.asdict(r))


# ------------------------------- elements --------------------------------

@app.post("/v1/calc/beam", dependencies=[Depends(require_api_key)])
def calc_beam(body: BeamIn):
    kw = body.model_dump()
    want_pdf = kw.pop("pdf_report")
    r = design_beam(**kw)
    arts = []
    x, V, M = r["analysis"]["x"], r["analysis"]["V"], r["analysis"]["M"]

    def render_png(path):
        from iscodes.plotting import plot_sfd_bmd
        plot_sfd_bmd(x, V, M, f"Beam {body.b:.0f}x{body.D:.0f} - "
                     f"{body.span_m} m {body.support}", path)
    a = png_artifact("sfd_bmd.png", render_png)
    if a:
        arts.append(a)
    if want_pdf:
        def render_pdf(path):
            from iscodes.pdfreport import from_report_checks
            from_report_checks(
                f"Beam design — {body.span_m} m {body.support}",
                r["checks"], figures=[], code_refs=["IS456", "SP16"],
                summary_rows=[["Section", f"{body.b:.0f} x {body.D:.0f} mm"],
                              ["Ast provided",
                               f"{r['design']['Ast_prov_mm2']:.0f} mm2"]],
                path=path)
        a = pdf_artifact("beam_report.pdf", render_pdf)
        if a:
            arts.append(a)
    r.pop("analysis", None)
    return envelope(r["ok"], r["checks"],
                    {k: v for k, v in r.items() if k != "checks"}, arts)


@app.post("/v1/calc/column", dependencies=[Depends(require_api_key)])
def calc_column(body: ColumnIn):
    kw = body.model_dump()
    kw.pop("pdf_report")
    r = design_column(**kw)
    arts = []

    def render_png(path):
        from iscodes.plotting import plot_pm_interaction
        cc = body.cover + body.tie_dia + body.bar_dia / 2
        sec = ColumnSection(body.b, body.D, body.fck, body.fy,
                            rect_bar_layout(body.b, body.D, cc,
                                            body.n_bars, body.bar_dia))
        curve = interaction_curve(sec) / 1e3
        curve[:, 1] /= 1e3
        plot_pm_interaction(curve,
                            [(r.data.get("Mux_design_kNm", 0), body.Pu_kN)],
                            f"Column {body.b:.0f}x{body.D:.0f} P-M", path)
    a = png_artifact("pm_interaction.png", render_png)
    if a:
        arts.append(a)
    return envelope(r.ok, r.checks, r.data, arts)


@app.post("/v1/calc/footing/isolated", dependencies=[Depends(require_api_key)])
def calc_footing_isolated(body: IsolatedFootingIn):
    kw = body.model_dump()
    kw.pop("pdf_report")
    r = design_isolated_footing(**kw)
    arts = []

    def render_png(path):
        from iscodes.plotting import plot_pressure_diagram
        plot_pressure_diagram(r.data["L_m"], r.data["q_min_service_kPa"],
                              r.data["q_max_service_kPa"],
                              "Base pressure (service)", path)
    a = png_artifact("pressure.png", render_png)
    if a:
        arts.append(a)
    return envelope(r.ok, r.checks, r.data, arts)


@app.post("/v1/calc/footing/combined", dependencies=[Depends(require_api_key)])
def calc_footing_combined(body: CombinedFootingIn):
    r = design_combined_footing(**body.model_dump())
    arts = []
    x, V, M = r.pop("x"), r.pop("V"), r.pop("M")

    def render_png(path):
        from iscodes.plotting import plot_sfd_bmd
        plot_sfd_bmd(x, V, M, "Combined footing — longitudinal", path)
    a = png_artifact("combined_sfd_bmd.png", render_png)
    if a:
        arts.append(a)
    return envelope(r["ok"], r["checks"],
                    {k: v for k, v in r.items() if k != "checks"}, arts)


@app.post("/v1/calc/slab/one-way", dependencies=[Depends(require_api_key)])
def calc_slab_one_way(body: OneWaySlabIn):
    r = slabmod.design_one_way_slab(**body.model_dump())
    return envelope(r["ok"], r["checks"],
                    {k: v for k, v in r.items() if k != "checks"})


@app.post("/v1/calc/slab/two-way", dependencies=[Depends(require_api_key)])
def calc_slab_two_way(body: TwoWaySlabIn):
    r = slabmod.design_two_way_slab(**body.model_dump())
    return envelope(r["ok"], r["checks"],
                    {k: v for k, v in r.items() if k != "checks"})


@app.post("/v1/calc/tank/circular", dependencies=[Depends(require_api_key)])
def calc_tank_circular(body: CircularTankIn):
    r = tankmod.circular_tank_forces(**body.model_dump())
    return envelope(True, [], dataclasses.asdict(r))


@app.post("/v1/calc/tank/wall-section", dependencies=[Depends(require_api_key)])
def calc_tank_wall(body: TankWallSectionIn):
    r = tankmod.design_tank_wall_section(**body.model_dump())
    return envelope(r["ok"], r["checks"], r["data"])


@app.post("/v1/calc/sump", dependencies=[Depends(require_api_key)])
def calc_sump(body: SumpIn):
    kw = body.model_dump()
    uplift_args = {k: kw.pop(k) for k in
                   ("plan_area", "structure_weight_kN",
                    "water_table_above_base")}
    pressures = tankmod.sump_wall_pressures(**kw)
    data = {"pressures": pressures}
    checks = []
    if all(v is not None for v in uplift_args.values()):
        u = tankmod.uplift_check(uplift_args["plan_area"],
                                 uplift_args["structure_weight_kN"],
                                 uplift_args["water_table_above_base"])
        data["uplift"] = u
        checks.append(("uplift/flotation FOS >= 1.2 (IS 3370)", u["ok"]))
    return envelope(all(o for _, o in checks) if checks else True,
                    checks, data)


@app.post("/v1/calc/mix", dependencies=[Depends(require_api_key)])
def calc_mix(body: MixIn):
    r = mixmod.design_mix(**body.model_dump())
    return envelope(r.ok, r.checks, r.data)


# ------------------------------- building --------------------------------

@app.post("/v1/design/building", dependencies=[Depends(require_api_key)])
def design_building_route(body: BuildingIn):
    r = design_building(
        x_spacings_m=body.grid.x_spacings_m,
        y_spacings_m=body.grid.y_spacings_m,
        storeys=body.storeys, storey_height_m=body.storey_height_m,
        occupancy=body.occupancy,
        city=body.location.city,
        basic_wind_speed=body.location.basic_wind_speed,
        seismic_zone=body.location.seismic_zone,
        terrain_category=body.location.terrain_category,
        soil=body.location.soil, sbc_kpa=body.sbc_kpa,
        fck=body.materials.fck, fy=body.materials.fy,
        exposure=body.materials.exposure,
        seismic_detailing=body.options.seismic_detailing)
    arts = []
    if body.options.pdf_report:
        a = pdf_artifact("building_report.pdf",
                         lambda p: building_report_pdf(r, p))
        if a:
            arts.append(a)
    all_checks = []
    for group in ("slabs", "beams", "columns", "footings"):
        for key, el in r[group].items():
            all_checks += [(f"{group}/{key}: {n}", o) for n, o in el["checks"]]
    return envelope(r["ok"], all_checks,
                    {k: v for k, v in r.items() if k != "ok"}, arts)
