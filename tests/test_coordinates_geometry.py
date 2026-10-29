import numpy as np
import pytest
from astropy import units as u
from astropy.coordinates import SkyCoord
from astropy.table import Table

from astrotools_adv.modules import coordinates_common as common
from astrotools_adv.modules import coordinates_geometry as cg
from coord_helpers import errors  # noqa: F401


def panel(qtbot, ws):
    p = cg.GeometryPanel(ws)
    qtbot.addWidget(p)
    return p


def run(p, op, a="0 0", b="0 90", **fields):
    p.a.text.setPlainText(a)
    p.b.text.setPlainText(b)
    p.form.set_value("op", op)
    for k, v in fields.items():
        p.form.set_value(k, v)
    p.compute()
    return p.table


def test_separation_pole(qtbot, ws):
    t = run(panel(qtbot, ws), "Separation + position angle (A to B)")
    assert t["sep_deg"][0] == pytest.approx(90.0)
    assert t["pa_deg"][0] == pytest.approx(0.0, abs=1e-9)  # north
    assert t["sep_arcmin"][0] == pytest.approx(5400)


def test_position_angle_cardinals(qtbot, ws):
    p = panel(qtbot, ws)
    assert run(p, "Position angle (A to B)", "0 0", "0 1")["pa_deg"][0] == pytest.approx(0.0)
    assert run(p, "Position angle (A to B)", "0 0", "1 0")["pa_deg"][0] == pytest.approx(90.0)
    assert run(p, "Position angle (A to B)", "0 0", "0 -1")["pa_deg"][0] == pytest.approx(180.0)
    assert run(p, "Position angle (A to B)", "0 0", "359 0")["pa_deg"][0] == pytest.approx(270.0)


def test_broadcast_and_mismatch(qtbot, ws, errors):
    p = panel(qtbot, ws)
    t = run(p, "Separation + position angle (A to B)", "0 0\n0 10\n0 20", "0 0")
    assert list(np.round(t["sep_deg"], 6)) == [0, 10, 20]
    run(p, "Separation + position angle (A to B)", "0 0\n0 10\n0 20", "0 0\n1 1")
    assert len(errors) == 1
    errors.clear()


def test_separation_3d(qtbot, ws, errors):
    p = panel(qtbot, ws)
    p.a.distance.setText("1 pc")
    p.b.distance.setText("2 pc")
    t = run(p, "3D separation (needs distances)", "0 0", "0 0")
    assert t["sep3d_pc"][0] == pytest.approx(1.0)
    p.a.distance.setText("")
    run(p, "3D separation (needs distances)", "0 0", "0 0")
    assert len(errors) == 1
    errors.clear()


def test_offset_by(qtbot, ws):
    p = panel(qtbot, ws)
    t = run(p, "Offset A by position angle + separation", "10 20", "0 0",
            pa="0", sep="1 deg")
    assert t["lon_deg"][0] == pytest.approx(10.0)
    assert t["lat_deg"][0] == pytest.approx(21.0)
    p.form.set_value("name", "off")
    p.store()
    assert ws.get("off").dec.deg == pytest.approx(21.0)


def test_spherical_offsets_roundtrip(qtbot, ws):
    p = panel(qtbot, ws)
    t = run(p, "Spherical offsets A to B (dlon, dlat)", "10 20", "11 21")
    t2 = run(p, "Spherical offsets: A by (dlon, dlat)", "10 20", "0 0",
             dlon=f"{t['dlon_deg'][0]} deg", dlat=f"{t['dlat_deg'][0]} deg")
    assert t2["lon_deg"][0] == pytest.approx(11.0, abs=1e-8)
    assert t2["lat_deg"][0] == pytest.approx(21.0, abs=1e-8)


def test_skyoffset(qtbot, ws):
    t = run(panel(qtbot, ws), "B in sky-offset frame centred on A", "10 20", "10 21")
    assert t["lat_deg"][0] == pytest.approx(1.0)
    assert t["lon_arcsec"][0] == pytest.approx(0.0, abs=1e-6)


def test_great_circle_and_antipode(qtbot, ws):
    p = panel(qtbot, ws)
    t = run(p, "Great circle A to B", "0 0", "90 0", n=10)
    assert len(t) == 10
    assert t["lon_deg"][-1] == pytest.approx(90.0) and t["from_A_deg"][-1] == pytest.approx(90.0)
    assert np.allclose(t["lat_deg"], 0, atol=1e-9)
    t = run(p, "Great circle A to B", "0 0", "0 90", n=3)
    assert t["lat_deg"][1] == pytest.approx(45.0)
    p.store()
    assert "geometry_table" in ws


def test_random_points_reproducible(qtbot, ws):
    p = panel(qtbot, ws)
    t1 = run(p, "Uniform random points on sphere", n=50, seed=7)
    t2 = run(p, "Uniform random points on sphere", n=50, seed=7)
    t3 = run(p, "Uniform random points on sphere", n=50, seed=8)
    assert np.array_equal(t1["lon_deg"], t2["lon_deg"])
    assert not np.array_equal(t1["lon_deg"], t3["lon_deg"])
    assert (np.abs(t1["lat_deg"]) <= 90).all()
    t = run(p, "Golden-spiral grid on sphere", n=20)
    assert len(t) == 20


def test_raw_angle_utils_matches_skycoord(qtbot, ws):
    p = panel(qtbot, ws)
    t = run(p, "Raw lon/lat trigonometry (angle utilities)", "10 20", "30 -10",
            pa="90", sep="1 deg")
    a, b = SkyCoord(10 * u.deg, 20 * u.deg), SkyCoord(30 * u.deg, -10 * u.deg)
    assert t["angular_separation_deg"][0] == pytest.approx(a.separation(b).deg)
    assert t["position_angle_deg"][0] == pytest.approx(a.position_angle(b).deg)
    ref = a.directional_offset_by(90 * u.deg, 1 * u.deg)
    assert t["offset_by_lon_deg"][0] == pytest.approx(ref.ra.deg)


def test_missing_input_reports_error(qtbot, ws, errors):
    p = panel(qtbot, ws)
    run(p, "Separation + position angle (A to B)", "", "0 0")
    run(p, "Offset A by position angle + separation", "0 0", "0 0", pa="north")
    assert len(errors) == 2
    errors.clear()


def test_table_source_separation(qtbot, ws):
    ws.put("t", Table({"ra": [0.0, 0.0], "dec": [0.0, 90.0]}))
    p = panel(qtbot, ws)
    p.a.source.setCurrentText(common.WS_TABLE)
    p.b.text.setPlainText("0 0")
    p.form.set_value("op", "Separation + position angle (A to B)")
    p.compute()
    assert list(np.round(p.table["sep_deg"], 6)) == [0, 90]


def test_field_enabling(qtbot, ws):
    p = panel(qtbot, ws)
    p.form.set_value("op", "Great circle A to B")
    assert p.form.fields["n"].isEnabled() and not p.form.fields["pa"].isEnabled()
    p.form.set_value("op", "Uniform random points on sphere")
    assert not p.a.isEnabled() and p.form.fields["seed"].isEnabled()
