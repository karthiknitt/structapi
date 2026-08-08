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


def test_sa_by_g_rock_spectrum():
    """Type I (rock) spectrum per IS 1893 cl 6.4.2 — correct 1.00/T branch."""
    # Ascending branch (T <= 0.40 s)
    assert tables.sa_by_g(0.40, "rock") == pytest.approx(2.5, abs=0.005)

    # Descending branch (0.40 < T <= 4.0 s)
    assert tables.sa_by_g(1.0, "rock") == pytest.approx(1.00, abs=0.005)

    # Floor (T > 4.0 s)
    assert tables.sa_by_g(4.0, "rock") == pytest.approx(0.25, abs=0.005)
    assert tables.sa_by_g(5.0, "rock") == pytest.approx(0.25, abs=0.005)

    # Regression: medium and soft soil coefficients unchanged
    assert tables.sa_by_g(1.0, "medium") == pytest.approx(1.36, abs=0.005)
    assert tables.sa_by_g(1.0, "soft") == pytest.approx(1.67, abs=0.005)


def test_importance_factor_table8():
    assert tables.IMPORTANCE == {"ordinary": 1.0, "important_community": 1.2}



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


def test_fundamental_period_steel_coefficient():
    assert loads.fundamental_period(12.0, frame="steel") == pytest.approx(
        0.080 * 12.0 ** 0.75, rel=1e-6)
    # RC branch unaffected — regression guard
    assert loads.fundamental_period(12.0, frame="rc") == pytest.approx(
        0.075 * 12.0 ** 0.75, rel=1e-6)


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


def test_ductile_column_confining_hoops_worked_example():
    """IS 13920:2016 cl 7.4.6 / 7.4.8 special confining reinforcement.

    Hand-worked G+1 seismic column, M25 / Fe500, 300 x 450, 40 mm cover,
    8-20 dia longitudinal bars:
        pitch limits: min(b,D)/4 = 75 mm   <-- governs
                      6 x 20     = 120 mm
                      cl cap     = 100 mm
                      -> s = 75 mm (already a multiple of 25)
        core to hoop outer face: 450-80 = 370 mm (> 300 -> 1 crosstie,
                                 2 segments, h = 185 mm)
                                 300-80 = 220 mm
        Ak = 370 x 220 = 81 400 mm2 ; Ag = 135 000 mm2 ; Ag/Ak - 1 = 0.658477
        Ash = max(0.18 x 75 x 185 x (25/500) x 0.658477,
                  0.05 x 75 x 185 x (25/500))
            = max(82.23, 34.69) = 82.23 mm2
        -> 8 dia hoop (50.3 mm2) FAILS, 12 dia hoop (113.1 mm2) PASSES.
    """
    b, D, fck, fy, cover, bar_dia = 300.0, 450.0, 25.0, 500.0, 40.0, 20.0
    Ag_hand = b * D
    Ak_hand = (D - 2 * cover) * (b - 2 * cover)
    h_hand = (D - 2 * cover) / 2.0            # 370 / 2 segments (h <= 300)
    s_hand = 75.0
    ash_hand = max(0.18 * s_hand * h_hand * (fck / fy) * (Ag_hand / Ak_hand - 1),
                   0.05 * s_hand * h_hand * (fck / fy))
    assert Ak_hand == 81400.0
    assert ash_hand == pytest.approx(82.23, abs=0.05)

    kw = dict(b=b, D=D, fck=fck, fy=fy, Pu_kN=900, Mux_kNm=60,
              L_unsupported_mm=3000, n_bars=8, bar_dia=bar_dia,
              cover=cover, seismic=True)

    r = column.design_column(tie_dia=12.0, **kw)
    d = r.data
    # spacing: the newly added min(b,D)/4 term is the binding limit
    assert d["confine_spacing_limit"] == pytest.approx(75.0)
    assert d["confine_spacing_limit"] < min(100.0, 6 * bar_dia)
    assert d["confine_spacing_max"] == 75.0
    assert d["confine_spacing_max"] % 25 == 0
    assert d["confine_length_lo"] == pytest.approx(max(D, 3000 / 6, 450.0))
    # hoop geometry + area
    assert d["confine_hoop_h_mm"] == pytest.approx(h_hand)
    assert d["confine_hoop_h_mm"] <= 300.0
    assert d["confine_crossties_required"] is True
    assert d["confine_core_Ak_mm2"] == pytest.approx(Ak_hand)
    assert d["Ash_required_mm2"] == pytest.approx(ash_hand, rel=1e-9)
    assert d["Ash_provided_mm2"] == pytest.approx(math.pi * 12.0 ** 2 / 4)
    assert d["confine_hoop_dia_mm"] == 12.0
    assert d["confine_hook"].startswith("135 deg bend")
    ash_checks = [ok for n, ok in r.checks if "Ash" in n]
    assert ash_checks == [True]

    # undersized hoop -> the same check must fail
    r8 = column.design_column(tie_dia=8.0, **kw)
    assert r8.data["Ash_required_mm2"] == pytest.approx(ash_hand, rel=1e-9)
    assert r8.data["Ash_provided_mm2"] < ash_hand
    assert [ok for n, ok in r8.checks if "Ash" in n] == [False]
    assert not r8.ok


def test_ductile_column_confining_absent_when_not_seismic():
    """Non-seismic regression guard for the cl 7.4 additions."""
    r = column.design_column(b=300, D=450, fck=25, fy=500, Pu_kN=900,
                             Mux_kNm=60, L_unsupported_mm=3000, n_bars=8,
                             bar_dia=20, cover=40, tie_dia=8.0, seismic=False)
    for k in ("Ash_required_mm2", "Ash_provided_mm2", "confine_hoop_dia_mm",
              "confine_spacing_max", "confine_length_lo", "confine_hook"):
        assert k not in r.data
    assert not any("cl 7.4" in n for n, _ in r.checks)
    # pre-existing IS 456 tie fields are untouched
    assert r.data["tie_pitch_max"] % 25 == 0


def test_design_column_fails_overloaded():
    r = column.design_column(b=300, D=300, fck=20, fy=415,
                             Pu_kN=3000, Mux_kNm=150,
                             L_unsupported_mm=3000, n_bars=4, bar_dia=16)
    assert not r.ok


# ---------------------------------------------------------------------------
# design/column.py -- IS 13920 cl 7.1.2 min-dimension trigger (seismic)
# ---------------------------------------------------------------------------

def test_design_column_seismic_lenient_200mm_when_short_span_and_length():
    r = column.design_column(b=250, D=250, fck=25, fy=415,
                             Pu_kN=500, Mux_kNm=20,
                             L_unsupported_mm=3000, n_bars=8, bar_dia=16,
                             seismic=True, max_beam_span_m=4.0)
    assert r.data["min_dim_required"] == 200.0
    assert r.data["strict_trigger"] is False
    name, ok = next(c for c in r.checks if c[0].startswith("min width"))
    assert ok  # 250 >= 200


def test_design_column_seismic_strict_300mm_span_triggered():
    r = column.design_column(b=250, D=250, fck=25, fy=415,
                             Pu_kN=500, Mux_kNm=20,
                             L_unsupported_mm=3000, n_bars=8, bar_dia=16,
                             seismic=True, max_beam_span_m=6.0)
    assert r.data["min_dim_required"] == 300.0
    assert r.data["strict_trigger"] is True
    name, ok = next(c for c in r.checks if c[0].startswith("min width"))
    assert not ok  # 250 < 300


def test_design_column_seismic_strict_300mm_length_triggered():
    r = column.design_column(b=250, D=250, fck=25, fy=415,
                             Pu_kN=500, Mux_kNm=20,
                             L_unsupported_mm=4500, n_bars=8, bar_dia=16,
                             seismic=True, max_beam_span_m=3.0)
    assert r.data["min_dim_required"] == 300.0
    assert r.data["strict_trigger"] is True
    name, ok = next(c for c in r.checks if c[0].startswith("min width"))
    assert not ok  # 250 < 300


def test_design_column_non_seismic_has_no_min_width_check():
    r = column.design_column(b=250, D=250, fck=25, fy=415,
                             Pu_kN=500, Mux_kNm=20,
                             L_unsupported_mm=4500, n_bars=8, bar_dia=16,
                             seismic=False, max_beam_span_m=6.0)
    assert not any(name.startswith("min width") for name, _ in r.checks)
    assert "min_dim_required" not in r.data


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
