"""Pydantic v2 input models — field names and units mirror the iscodes
function signatures exactly (mm/N/MPa for sections, m/kN for loads/geometry).
extra='forbid' so typos fail loudly at 422 instead of silently defaulting.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CombinationsIn(_In):
    DL: float
    IL: float = 0.0
    WL: float = 0.0
    EL: float = 0.0
    limit_state: str = "ULS"


class WindIn(_In):
    Vb: float = Field(gt=0, description="basic wind speed m/s")
    height: float = Field(gt=0)
    terrain_category: int = Field(default=2, ge=1, le=4)
    k1: float = 1.0
    k3: float = 1.0
    k4: float = 1.0


class SeismicIn(_In):
    storey_weights: list[float]
    storey_heights: list[float]
    zone: str
    soil: str = "medium"
    I: float = 1.0
    R: float = 5.0
    frame: str = "rc"
    base_dim: float | None = None


class BeamIn(_In):
    span_m: float = Field(gt=0)
    w_dl_kn_m: float = Field(ge=0)
    w_il_kn_m: float = Field(ge=0)
    b: float = Field(gt=0, description="mm")
    D: float = Field(gt=0, description="mm")
    fck: float
    fy: float
    support: str = "ss"
    point_loads: list[tuple[float, float]] | None = None
    cover: float = 30.0
    bar_dia: float = 20.0
    stirrup_dia: float = 8.0
    seismic: bool = False
    exposure: str = "moderate"
    pdf_report: bool = False


class ColumnIn(_In):
    b: float
    D: float
    fck: float
    fy: float
    Pu_kN: float
    Mux_kNm: float = 0.0
    Muy_kNm: float = 0.0
    L_unsupported_mm: float | None = 3000.0
    n_bars: int = 8
    bar_dia: float = 20.0
    cover: float = 40.0
    tie_dia: float = 8.0
    seismic: bool = False
    pdf_report: bool = False


class IsolatedFootingIn(_In):
    P_service_kN: float = Field(gt=0)
    M_service_kNm: float = 0.0
    sbc_kpa: float = Field(gt=0)
    col_b_mm: float = Field(gt=0)
    col_D_mm: float = Field(gt=0)
    fck: float
    fy: float
    pdf_report: bool = False


class CombinedFootingIn(_In):
    P1_kN: float = Field(gt=0)
    P2_kN: float = Field(gt=0)
    spacing_m: float = Field(gt=0)
    sbc_kpa: float = Field(gt=0)
    col1_mm: float = Field(gt=0)
    col2_mm: float = Field(gt=0)
    fck: float
    fy: float
    edge_limit_m: float | None = None


class OneWaySlabIn(_In):
    lx_m: float = Field(gt=0)
    w_dl: float = Field(ge=0, description="kN/m2 EXCLUDING self weight")
    w_il: float = Field(ge=0)
    fck: float
    fy: float
    support: str = "ss"
    D_mm: float | None = None


class TwoWaySlabIn(_In):
    lx_m: float = Field(gt=0)
    ly_m: float = Field(gt=0)
    w_dl: float = Field(ge=0, description="kN/m2 EXCLUDING self weight")
    w_il: float = Field(ge=0)
    fck: float
    fy: float
    case: int = Field(default=4, ge=1, le=9)
    corners_held: bool = True
    D_mm: float | None = None


class CircularTankIn(_In):
    H: float = Field(gt=0, description="water depth m")
    D: float = Field(gt=0, description="internal diameter m")
    t: float = Field(gt=0, description="wall thickness m")
    base: str = "hinged"


class TankWallSectionIn(_In):
    M_service_kNm: float
    T_service_kN: float = 0.0
    t_mm: float
    fck: float
    fy: float
    bar_dia: float = 16.0
    spacing_mm: float = 150.0
    liquid_face: bool = True


class SumpIn(_In):
    H: float = Field(gt=0)
    gamma_soil: float = 18.0
    phi_deg: float = 30.0
    surcharge: float = 10.0
    water_table_depth: float = 0.0
    gamma_sat: float = 20.0
    plan_area: float | None = None
    structure_weight_kN: float | None = None
    water_table_above_base: float | None = None


class MixIn(_In):
    fck: float
    exposure: str = "moderate"
    msa_mm: int = 20
    slump_mm: float = 75
    fa_zone: str = "II"
    admixture: str | None = "superplasticizer"
    water_reduction_pct: float = 20.0
    pumpable: bool = False


class BuildingGrid(_In):
    x_spacings_m: list[float] = Field(min_length=1)
    y_spacings_m: list[float] = Field(min_length=1)


class BuildingLocation(_In):
    city: str | None = None
    basic_wind_speed: float | None = None
    seismic_zone: str = "III"
    terrain_category: int = 2
    soil: str = "medium"


class BuildingMaterials(_In):
    fck: float = 25.0
    fy: float = 500.0
    exposure: str = "moderate"


class BuildingOptions(_In):
    seismic_detailing: bool | None = None
    pdf_report: bool = True


class BuildingIn(_In):
    grid: BuildingGrid
    storeys: int = Field(ge=1, le=10)
    storey_height_m: float = 3.0
    occupancy: str = "residential_room"
    location: BuildingLocation = BuildingLocation()
    sbc_kpa: float = 200.0
    materials: BuildingMaterials = BuildingMaterials()
    options: BuildingOptions = BuildingOptions()
