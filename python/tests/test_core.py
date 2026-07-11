"""Worked-example validation for the F1 core modules.

References: SP 16 examples, standard textbook results (Pillai & Menon,
Varghese), IS 1893 / IS 875 hand calcs.
"""

import math

import pytest

from iscodes import tables, loads, serviceability as svc
from iscodes.materials import Concrete, Steel
from iscodes.design import column, tank


# ---------------------------------------------------------------------------
# tables.py
# ---------------------------------------------------------------------------

def test_tau_c_matches_table19():
    # IS 456 Table 19 spot values (MPa)
    assert tables.tau_c(0.50, 20) == pytest.approx(0.48, abs=0.02)
    assert tables.tau_c(1.00, 20) == pytest.approx(0.62, abs=0.02)
    assert tables.tau_c(1.00, 25) == pytest.approx(0.64, abs=0.02)
    assert tables.tau_c(2.00, 30) == pytest.approx(0.86, abs=0.03)
    # clamping
    assert tables.tau_c(0.05, 20) == tables.tau_c(0.15, 20)


def test_xu_max_and_mulim():
    assert tables.xu_max_by_d(250) == pytest.approx(0.53, abs=0.005)
    assert tables.xu_max_by_d(415) == pytest.approx(0.479, abs=0.005)
    assert tables.xu_max_by_d(500) == pytest.approx(0.456, abs=0.005)
    assert tables.mu_lim_factor(415) == pytest.approx(0.138, abs=0.002)
    assert tables.mu_lim_factor(500) == pytest.approx(0.133, abs=0.002)


def test_development_length_fe415_m20():
    # Ld = 47 phi for Fe415/M20 deformed tension bars (classic result)
    ld = tables.development_length(20, 415, 20)
    assert ld / 20 == pytest.approx(47.0, abs=0.5)


def test_slab_coefficients_interior_square():
    c = tables.slab_coefficients(1, 1.0)
    assert c["nx"] == pytest.approx(0.032)
    assert c["px"] == pytest.approx(0.024)


def test_bearing_capacity_factors_phi30():
    f = tables.bearing_capacity_factors(30)
    assert f["Nq"] == pytest.approx(18.4, abs=0.1)
    assert f["Nc"] == pytest.approx(30.1, abs=0.2)
    assert f["Ngamma"] == pytest.approx(22.4, abs=0.2)


# ---------------------------------------------------------------------------
# materials.py
# ---------------------------------------------------------------------------

def test_concrete_props():
    c = Concrete(25)
    assert c.Ec == pytest.approx(25000, abs=1)
    assert c.fcr == pytest.approx(3.5, abs=0.01)


def test_steel_stress_strain_fe415():
    s = Steel(415)
    fd = 0.87 * 415
    assert s.stress_at_strain(0.010) == pytest.approx(fd, rel=1e-6)  # yielded
    assert s.stress_at_strain(0.001) == pytest.approx(200, abs=1)    # elastic
    assert s.stress_at_strain(-0.010) == pytest.approx(-fd, rel=1e-6)


# ---------------------------------------------------------------------------
# loads.py
# ---------------------------------------------------------------------------

def test_combinations_gravity_governs():
    combos = loads.combinations(DL=100, IL=50)
    top = combos[0]
    assert top["name"] == "1.5(DL+IL)"
    assert top["value"] == pytest.approx(225.0)


def test_combinations_uplift_case():
    # light DL, strong lateral: 0.9DL - 1.5WL should appear and be negative
    combos = loads.combinations(DL=10, IL=0, WL=50)
    names = [c["name"] for c in combos]
    assert "0.9DL-1.5WL" in names
    v = next(c["value"] for c in combos if c["name"] == "0.9DL-1.5WL")
    assert v == pytest.approx(0.9 * 10 - 1.5 * 50)


def test_wind_pressure_50ms_cat2_10m():
    r = loads.wind_pressure(Vb=50, height=10, terrain_category=2)
    assert r.Vz == pytest.approx(50.0)
    assert r.pz == pytest.approx(1.5, abs=0.01)     # 0.6*50^2 = 1500 N/m2
    assert r.pd == pytest.approx(1.35, abs=0.01)    # Kd=0.9
    assert r.pd >= 0.7 * r.pz


def test_seismic_base_shear_hand_calc():
    # 4-storey RC SMRF, zone III, medium soil, 3.2 m storeys, W = 2000 kN/floor
    hts = [3.2, 6.4, 9.6, 12.8]
    ws = [2000.0] * 4
    r = loads.base_shear(ws, hts, zone="III", soil="medium", I=1.0, R=5.0)
    # Ta = 0.075 * 12.8^0.75 = 0.507 s -> Sa/g = 2.5 (medium, T<=0.55)
    assert r.Ta == pytest.approx(0.075 * 12.8 ** 0.75, rel=1e-6)
    assert r.Sa_g == pytest.approx(2.5)
    assert r.Ah == pytest.approx(0.16 / 2 * 2.5 / 5.0)  # 0.04
    assert r.VB == pytest.approx(0.04 * 8000)           # 320 kN
    assert sum(q for *_, q in r.storey_forces) == pytest.approx(r.VB)
    # top floor takes the largest share
    assert r.storey_forces[-1][3] == max(q for *_, q in r.storey_forces)


def test_seismic_minimum_base_shear_floor():
    # very tall/flexible: min base shear percentage must govern
    hts = [3.0 * i for i in range(1, 21)]
    ws = [1000.0] * 20
    r = loads.base_shear(ws, hts, zone="V", soil="rock", I=1.0, R=5.0)
    assert r.VB >= 0.024 * sum(ws)


# ---------------------------------------------------------------------------
# serviceability.py
# ---------------------------------------------------------------------------

def test_deflection_check_typical_beam():
    # SS beam, Fe415, pt = 0.72, fully utilized -> kt ~ 1.0-1.1
    r = svc.check_deflection(6000, 550, "simply_supported", 415, 0.72)
    assert 0.9 < r["allowable_L_by_d"] / 20.0 < 1.4
    assert r["ok"]  # 6000/550 = 10.9 << allowable


def test_crack_width_reasonable():
    # 200 mm slab-like wall strip, service moment 25 kNm/m, 12 dia @ 125
    ast = math.pi * 36 * (1000 / 125)
    r = svc.crack_width_flexure(1000, 200, 200 - 45 - 6, ast, 30,
                                25e6, 45, 12, 125)
    assert 0 < r["w_cr"] < 0.5


# ---------------------------------------------------------------------------
# design/column.py
# ---------------------------------------------------------------------------

def test_pure_axial_capacity():
    # 450x450, 8-25dia, M25/Fe415: Puz = 0.45 fck (Ag-Asc) + 0.75 fy Asc
    sec = column.ColumnSection(450, 450, 25, 415,
                               column.rect_bar_layout(450, 450, 60, 8, 25))
    curve = column.interaction_curve(sec)
    puz_expected = 0.45 * 25 * (450 * 450 - sec.Asc) + 0.75 * 415 * sec.Asc
    assert curve[:, 0].max() == pytest.approx(puz_expected, rel=0.02)


def test_interaction_monotone_moment_at_low_axial():
    sec = column.ColumnSection(400, 400, 25, 415,
                               column.rect_bar_layout(400, 400, 60, 8, 20))
    m_low = column.uniaxial_moment_capacity(sec, 0.1e6)
    m_bal = column.uniaxial_moment_capacity(sec, 0.35 * 0.45 * 25 * 160000)
    assert m_low > 0 and m_bal > 0
    # balanced-region capacity should exceed low-axial pure-bending capacity
    assert m_bal > 0.8 * m_low


def test_design_column_passes_reasonable_case():
    r = column.design_column(b=450, D=450, fck=25, fy=415,
                             Pu_kN=1500, Mux_kNm=80, Muy_kNm=40,
                             L_unsupported_mm=3000, n_bars=8, bar_dia=25)
    assert r.data["p_percent"] == pytest.approx(1.94, abs=0.05)
    assert not r.data["slender"]
    assert r.ok, r.checks


def test_design_column_fails_overloaded():
    r = column.design_column(b=300, D=300, fck=20, fy=415,
                             Pu_kN=3000, Mux_kNm=150,
                             L_unsupported_mm=3000, n_bars=4, bar_dia=16)
    assert not r.ok


# ---------------------------------------------------------------------------
# design/tank.py
# ---------------------------------------------------------------------------

def test_circular_tank_hinged_coefficient():
    # H=4, D=10, t=0.2 -> H2/Dt = 8 -> hinged hoop coeff ~ 0.72
    f = tank.circular_tank_forces(4, 10, 0.2, base="hinged")
    assert f.H2_Dt == pytest.approx(8.0)
    T_expected = 0.721 * 9.81 * 4 * 5
    assert f.hoop_max_kN_per_m == pytest.approx(T_expected, rel=0.02)


def test_rect_tank_long_wall_cantilever():
    r = tank.rectangular_wall_forces(H=3, L=8, B=4)
    lw = r["long_wall"]
    assert lw["mode"] == "vertical cantilever"
    assert lw["M_base_kNm_per_m"] == pytest.approx(9.81 * 27 / 6, rel=1e-6)


def test_sump_case_b_governs_with_backfill():
    r = tank.sump_wall_pressures(H=3.5, water_table_depth=0.5)
    assert r["caseB_empty_backfilled"]["M_cantilever_base"] > 0
    assert r["governing_moment"] >= r["caseA_full_no_backfill"]["M_cantilever_base"] * 0.99


def test_uplift_check():
    r = tank.uplift_check(plan_area=50, structure_weight_kN=1000,
                          water_table_above_base=2.0)
    # U = 9.81 * 2 * 50 = 981 -> FOS ~ 1.02 < 1.2 -> fail
    assert not r["ok"]
    r2 = tank.uplift_check(50, 1500, 2.0)
    assert r2["ok"]


def test_tank_wall_section_design():
    r = tank.design_tank_wall_section(M_service_kNm=45, T_service_kN=60,
                                      t_mm=300, fck=30, fy=500,
                                      bar_dia=16, spacing_mm=125,
                                      liquid_face=True)
    assert r["data"]["Ast_mm2_per_m"] == pytest.approx(1608, rel=0.01)
    assert isinstance(r["ok"], bool)
    assert r["data"]["crack_width_mm"] is not None
