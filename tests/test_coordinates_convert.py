import numpy as np
import pytest
from astropy import units as u
from astropy.coordinates import SkyCoord
from astropy.table import Table

from astrotools_adv.core.parsing import ParseError
from astrotools_adv.modules import coordinates_convert as cc
from astrotools_adv.modules import coordinates_common as common
from coord_helpers import errors  # noqa: F401


def make(qtbot, ws, cls):
    panel = cls(ws)
    qtbot.addWidget(panel)
    return panel


def test_m31_icrs_to_galactic(qtbot, ws):
    p = make(qtbot, ws, cc.ConverterPanel)
    p.inp.text.setPlainText("10.684 41.269")
    p.target.frame.setCurrentText("Galactic")
    p.convert()
    assert p.result.l.deg == pytest.approx(121.1744, abs=2e-3)
    assert p.result.b.deg == pytest.approx(-21.5729, abs=2e-3)
    t = p.table
    assert t.colnames == ["l", "b"]
    assert float(t["l"][0]) == pytest.approx(121.1744, abs=2e-3)


def test_converter_hmsdms_and_store(qtbot, ws):
    p = make(qtbot, ws, cc.ConverterPanel)
    p.inp.text.setPlainText("00h42m44.3s +41d16m09s")
    p.target.frame.setCurrentText("ICRS")
    p.form.set_value("fmt", "hmsdms")
    p.convert()
    assert p.table["ra"][0].startswith("00:42:44.3")
    assert p.table["dec"][0].startswith("+41:16:09")
    p.form.set_value("name", "m31")
    p.store()
    assert "m31" in ws and "m31_table" in ws


def test_fk4_to_fk5_known(qtbot, ws):
    # FK4 (B1950) (0,0) -> FK5 J2000 ~ (0.640, 0.278) deg (standard precession+E-terms)
    p = make(qtbot, ws, cc.ConverterPanel)
    p.inp.text.setPlainText("0 0")
    p.inp.frame.frame.setCurrentText("FK4")
    p.target.frame.setCurrentText("FK5")
    p.convert()
    assert p.result.ra.deg == pytest.approx(0.6406, abs=3e-3)
    assert p.result.dec.deg == pytest.approx(0.2778, abs=3e-3)


def test_converter_cartesian_distance_and_motion(qtbot, ws):
    p = make(qtbot, ws, cc.ConverterPanel)
    p.inp.text.setPlainText("0 0\n90 0")
    p.inp.distance.setText("10 pc")
    p.inp.pm_lon.setText("100")
    p.inp.pm_lat.setText("0")
    p.inp.rv.setText("5")
    p.form.set_value("rep", "cartesian")
    p.target.frame.setCurrentText("ICRS")
    p.convert()
    assert p.table["x"][0] == pytest.approx(10) and p.table["y"][1] == pytest.approx(10)
    assert p.result.data.differentials


def test_converter_parallax_to_distance(qtbot, ws):
    p = make(qtbot, ws, cc.ConverterPanel)
    p.inp.text.setPlainText("10 20")
    p.inp.parallax.setText("100")  # mas -> 10 pc
    p.form.set_value("rep", "spherical")
    p.target.frame.setCurrentText("ICRS")
    p.convert()
    assert p.table["distance"][0] == pytest.approx(10.0)


def test_converter_altaz_and_errors(qtbot, ws, errors):
    p = make(qtbot, ws, cc.ConverterPanel)
    p.inp.text.setPlainText("10 20")
    p.target.frame.setCurrentText("AltAz")  # no obstime -> user error, not crash
    p.convert()
    assert len(errors) == 1 and isinstance(errors[0], ParseError)
    p.target.obstime.setText("2024-06-21T12:00:00")
    p.target.location.set_mode("Geodetic")
    p.convert()
    assert len(errors) == 1
    errors.clear()
    assert 0 <= p.result.az.deg < 360


def test_converter_garbage_input(qtbot, ws, errors):
    p = make(qtbot, ws, cc.ConverterPanel)
    for bad in ("", "abc def", "10 95", "1 2 3"):
        p.inp.text.setPlainText(bad)
        p.convert()
    assert len(errors) == 4
    errors.clear()


@pytest.mark.parametrize("frame", common.FRAME_NAMES)
def test_every_target_frame_builds_or_reports(qtbot, ws, frame):
    p = make(qtbot, ws, cc.ConverterPanel)
    p.inp.text.setPlainText("10.684 41.269")
    p.inp.distance.setText("1 kpc")
    p.target.frame.setCurrentText(frame)
    p.target.obstime.setText("2024-06-21T12:00:00")
    p.target.origin.setText("10 41")
    try:
        p.convert()
    except Exception as exc:  # pragma: no cover
        pytest.fail(f"{frame}: {exc!r}")


def test_galactocentric_parameters(qtbot, ws):
    p = make(qtbot, ws, cc.ConverterPanel)
    p.inp.text.setPlainText("266.4051 -28.9362")  # Sgr A*
    p.inp.distance.setText("8.122 kpc")
    p.target.frame.setCurrentText("Galactocentric")
    p.target.galcen_distance.setText("8.122 kpc")
    p.target.z_sun.setText("20.8 pc")
    p.target.galcen_v_sun.setText("12.9 245.6 7.78")
    p.form.set_value("rep", "cartesian")
    p.convert()
    assert abs(p.table["x"][0]) < 0.05 and abs(p.table["y"][0]) < 0.05


def test_table_source(qtbot, ws):
    ws.put("cat", Table({"RAJ2000": [10.0, 20.0], "DEJ2000": [1.0, 2.0],
                         "plx": [10.0, 5.0]}))
    p = make(qtbot, ws, cc.ConverterPanel)
    p.inp.source.setCurrentText(common.WS_TABLE)
    assert p.inp.cols["lon"].currentText() == "RAJ2000"
    p.inp.cols["distance"].setCurrentText("plx")
    p.form.set_value("rep", "spherical")
    p.target.frame.setCurrentText("Galactic")
    p.convert()
    assert len(p.result) == 2
    assert p.result.distance[0].to_value(u.pc) == pytest.approx(10.0)


def test_table_source_sexagesimal_strings(qtbot, ws):
    ws.put("cat", Table({"ra": ["00:42:44.3", "10:00:00"], "dec": ["+41:16:09", "-5:00:00"]}))
    p = make(qtbot, ws, cc.ConverterPanel)
    p.inp.source.setCurrentText(common.WS_TABLE)
    p.inp.lon_unit.setCurrentText("hourangle")
    sc = p.inp.get()
    assert sc.ra.deg[0] == pytest.approx(10.6846, abs=1e-3)
    assert sc.dec.deg[1] == pytest.approx(-5.0)


def test_workspace_skycoord_source(qtbot, ws):
    ws.put("c", SkyCoord(1 * u.deg, 2 * u.deg))
    p = make(qtbot, ws, cc.ConverterPanel)
    p.inp.source.setCurrentText(common.WS_SKYCOORD)
    p.convert()
    assert p.result.size == 1


def test_name_resolver_offline_degrades(qtbot, ws, monkeypatch):
    def boom(name, *a, **k):
        raise OSError("no network")
    monkeypatch.setattr(SkyCoord, "from_name", staticmethod(boom))
    p = make(qtbot, ws, cc.NameResolverPanel)
    p.resolve()
    assert "Nothing could be resolved" in p.out.toPlainText()
    assert "M31: no network" in p.out.toPlainText()


def test_name_resolver_mocked_success(qtbot, ws, monkeypatch):
    monkeypatch.setattr(SkyCoord, "from_name", staticmethod(
        lambda name, *a, **k: SkyCoord(10.684 * u.deg, 41.269 * u.deg)))
    p = make(qtbot, ws, cc.NameResolverPanel)
    p.resolve()
    assert "resolved" in ws and len(ws.get("resolved")) == 2
    assert p.table_view.model.rowCount() == 2


def test_distance_panel(qtbot, ws):
    p = make(qtbot, ws, cc.DistancePanel)
    p.form.set_value("kind", "parallax")
    p.form.set_value("values", "100")
    p.form.set_value("mag", "5")
    p.calculate()
    assert p._table["pc"][0] == pytest.approx(10.0)
    assert p._table["distmod_mag"][0] == pytest.approx(0.0)
    assert p._table["abs_mag"][0] == pytest.approx(5.0)
    p.form.set_value("kind", "distmod")
    p.form.set_value("values", "5 10")
    p.calculate()
    assert p._table["pc"][0] == pytest.approx(100.0) and p._table["pc"][1] == pytest.approx(1000.0)


def test_distance_errors(qtbot, ws, errors):
    p = make(qtbot, ws, cc.DistancePanel)
    p.form.set_value("values", "-5")
    p.calculate()
    p.form.set_value("values", "abc")
    p.calculate()
    p.form.set_value("kind", "parallax")
    p.form.set_value("values", "0")
    p.calculate()
    assert len(errors) == 3
    errors.clear()


def test_angle_panel(qtbot, ws, errors):
    p = make(qtbot, ws, cc.AnglePanel)
    p.calculate()
    t = p.table_view.model._table
    assert t["deg"][0] == pytest.approx(157.5) and t["deg"][1] == pytest.approx(-5.2008333)
    assert t["hms"][0].startswith("10:30:00")
    p.form.set_value("op", "Wrap at 360 (0..360)")
    p.calculate()
    assert p.table_view.model._table["deg"][1] == pytest.approx(354.7991667)
    p.form.set_value("op", "A + B")
    p.calculate()
    assert len(errors) == 1  # B missing
    p.form.set_value("b", "10")
    p.calculate()
    assert p.table_view.model._table["deg"][0] == pytest.approx(167.5)
    p.form.set_value("op", "Validate as Latitude")
    p.form.set_value("a", "95")
    p.calculate()
    assert len(errors) == 2
    p.form.set_value("op", "Circular mean of A")
    p.form.set_value("a", "350\n10")
    p.calculate()
    mean = p.table_view.model._table["deg"][0]
    assert min(mean, 360 - mean) == pytest.approx(0.0, abs=1e-9)
    p.form.set_value("op", "A / k")
    p.form.set_value("k", "0")
    p.calculate()
    assert len(errors) == 3
    errors.clear()


def test_all_specs_open(qtbot, ws):
    for spec in cc.SPECS:
        qtbot.addWidget(spec.factory(ws))
