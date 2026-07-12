"""structapi contract tests: auth, envelope, determinism, artifacts, freeze."""

import base64
import json
import os
import pathlib

import pytest
from fastapi.testclient import TestClient

os.environ["STRUCTAPI_KEYS"] = "test-key-1"
os.environ["STRUCTAPI_RATE_LIMIT"] = "0"  # disable for tests

from structapi.main import app  # noqa: E402

client = TestClient(app)
H = {"x-api-key": "test-key-1"}

BEAM_BODY = {"span_m": 6.0, "w_dl_kn_m": 15.0, "w_il_kn_m": 10.0,
             "b": 300, "D": 550, "fck": 25, "fy": 500, "support": "ss"}


def test_health_open():
    r = client.get("/v1/health")
    assert r.status_code == 200
    assert r.json()["api_version"] == "1"


def test_auth_required():
    assert client.post("/v1/calc/mix", json={"fck": 25}).status_code == 401
    assert client.post("/v1/calc/mix", json={"fck": 25},
                       headers={"x-api-key": "wrong"}).status_code == 401


def test_validation_422_on_typo():
    bad = dict(BEAM_BODY, span_metres=6.0)  # extra field -> forbid
    r = client.post("/v1/calc/beam", json=bad, headers=H)
    assert r.status_code == 422


def test_beam_envelope_and_artifact():
    r = client.post("/v1/calc/beam", json=BEAM_BODY, headers=H)
    assert r.status_code == 200
    e = r.json()
    assert e["api_version"] == "1" and e["ok"] is True
    assert all(set(c) == {"name", "ok"} for c in e["checks"])
    assert "disclaimer" in e and "code_editions" in e
    png = next(a for a in e["artifacts"] if a["name"] == "sfd_bmd.png")
    raw = base64.b64decode(png["content"])
    assert raw[:8] == b"\x89PNG\r\n\x1a\n" and len(raw) > 5000


def test_beam_pdf_artifact():
    r = client.post("/v1/calc/beam", json=dict(BEAM_BODY, pdf_report=True),
                    headers=H)
    pdf = next(a for a in r.json()["artifacts"]
               if a["name"] == "beam_report.pdf")
    assert base64.b64decode(pdf["content"])[:5] == b"%PDF-"


def test_determinism():
    a = client.post("/v1/calc/footing/isolated",
                    json={"P_service_kN": 1000, "sbc_kpa": 200,
                          "col_b_mm": 400, "col_D_mm": 400,
                          "fck": 25, "fy": 500}, headers=H).json()
    b = client.post("/v1/calc/footing/isolated",
                    json={"P_service_kN": 1000, "sbc_kpa": 200,
                          "col_b_mm": 400, "col_D_mm": 400,
                          "fck": 25, "fy": 500}, headers=H).json()
    assert a["data"] == b["data"] and a["checks"] == b["checks"]


def test_mix_endpoint():
    r = client.post("/v1/calc/mix",
                    json={"fck": 30, "exposure": "severe",
                          "slump_mm": 100}, headers=H).json()
    assert r["ok"] and r["data"]["cement"] >= 320


def test_column_endpoint_with_pm_diagram():
    r = client.post("/v1/calc/column",
                    json={"b": 450, "D": 450, "fck": 25, "fy": 415,
                          "Pu_kN": 1500, "Mux_kNm": 80, "Muy_kNm": 40,
                          "n_bars": 8, "bar_dia": 25}, headers=H).json()
    assert r["ok"]
    assert any(a["name"] == "pm_interaction.png" for a in r["artifacts"])


def test_building_chain_endpoint():
    body = {"grid": {"x_spacings_m": [3.5, 4.0, 3.5],
                     "y_spacings_m": [4.0, 4.5]},
            "storeys": 2,
            "location": {"city": "chennai", "seismic_zone": "III",
                         "terrain_category": 3},
            "options": {"pdf_report": True}}
    r = client.post("/v1/design/building", json=body, headers=H)
    assert r.status_code == 200
    e = r.json()
    assert e["ok"], [c for c in e["checks"] if not c["ok"]][:5]
    assert e["data"]["quantities"]["steel_kg"]["total"] > 0
    pdf = next(a for a in e["artifacts"]
               if a["name"] == "building_report.pdf")
    assert base64.b64decode(pdf["content"])[:5] == b"%PDF-"


# ------------------------- contract freeze (golden) -----------------------

GOLDEN = pathlib.Path(__file__).parent / "fixtures" / "beam_envelope_v1.json"


def _envelope_shape(e: dict) -> dict:
    """Structure-only projection: keys + check names, not values."""
    return {
        "top_keys": sorted(e.keys()),
        "check_names": [c["name"] for c in e["checks"]],
        "data_keys": sorted(e["data"].keys()),
        "design_keys": sorted(e["data"].get("design", {}).keys()),
        "artifact_names": sorted(a["name"] for a in e["artifacts"]),
    }


def test_contract_freeze_beam():
    """v1 envelope shape for the beam endpoint is FROZEN. If this fails you
    have made a breaking change — add /v2 instead of mutating v1."""
    e = client.post("/v1/calc/beam", json=BEAM_BODY, headers=H).json()
    shape = _envelope_shape(e)
    if not GOLDEN.exists():
        GOLDEN.parent.mkdir(parents=True, exist_ok=True)
        GOLDEN.write_text(json.dumps(shape, indent=1))
        pytest.skip("golden fixture recorded (first run)")
    assert shape == json.loads(GOLDEN.read_text()), (
        "v1 contract drift detected — see docstring")
