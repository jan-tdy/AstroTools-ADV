import numpy as np
import pytest
from astropy import units as u
from astropy.coordinates import SkyCoord
from astropy.table import Table

from astrotools_adv.modules import coordinates_common as common
from astrotools_adv.modules import coordinates_match as cm
from coord_helpers import errors  # noqa: F401


@pytest.fixture
def tables(ws):
    a = Table({"ra": [10.0, 20.0, 30.0], "dec": [0.0, 0.0, 0.0], "name": ["x", "y", "z"]})
    b = Table({"RA": [10.0 + 0.5 / 3600, 20.0 + 5 / 3600, 100.0], "DEC": [0.0, 0.0, 0.0],
               "mag": [1.0, 2.0, 3.0]})
    ws.put("A", a)
    ws.put("B", b)
    return a, b


def make(qtbot, ws, cls):
    p = cls(ws)
    qtbot.addWidget(p)
    return p


def match_panel(qtbot, ws):
    p = make(qtbot, ws, cm.MatchPanel)
    p.a.tbl_combo.setCurrentText("A")
    p.b.tbl_combo.setCurrentText("B")
    assert p.b.cols["lon"].currentText() == "RA"
    return p


def test_match_nearest_sky(qtbot, ws, tables):
    p = match_panel(qtbot, ws)
    p.form.set_value("limit", "1 arcsec")
    p.match()
    r = p.result
    assert list(r["idx_b"]) == [0, 1, 1] or list(r["idx_b"])[:2] == [0, 1]
    assert list(r["matched"]) == [True, False, False]
    assert r["sep_arcsec"][0] == pytest.approx(0.5, abs=1e-6)
    assert "a_name" in r.colnames and "b_mag" in r.colnames
    assert r["b_mag"].mask.tolist() == [False, True, True]


def test_match_drop_unmatched_and_store(qtbot, ws, tables):
    p = match_panel(qtbot, ws)
    p.form.set_value("keep", False)
    p.match()
    assert len(p.result) == 1 and p.result["a_name"][0] == "x"
    p.store()
    assert "matched" in ws


def test_search_around_sky(qtbot, ws, tables):
    p = match_panel(qtbot, ws)
    p.form.set_value("op", cm.MATCH_OPS[2])
    p.form.set_value("limit", "10 arcsec")
    p.match()
    r = p.result
    assert sorted(zip(r["idx_a"], r["idx_b"])) == [(0, 0), (1, 1)]
    assert r["b_mag"][0] == 1.0 and r["a_name"][1] == "y"


def test_search_requires_limit(qtbot, ws, tables, errors):
    p = match_panel(qtbot, ws)
    p.form.set_value("op", cm.MATCH_OPS[2])
    p.form.set_value("limit", "")
    p.match()
    assert len(errors) == 1
    errors.clear()


def test_match_3d(qtbot, ws, errors):
    a = Table({"ra": [0.0, 0.0], "dec": [0.0, 0.0], "d": [10.0, 20.0]})
    b = Table({"ra": [0.0, 0.0], "dec": [0.0, 0.0], "d": [10.5, 100.0]})
    ws.put("A", a)
    ws.put("B", b)
    p = make(qtbot, ws, cm.MatchPanel)
    p.a.tbl_combo.setCurrentText("A")
    p.b.tbl_combo.setCurrentText("B")
    p.form.set_value("op", cm.MATCH_OPS[1])
    p.match()
    assert len(errors) == 1  # no distance columns chosen
    errors.clear()
    p.a.cols["distance"].setCurrentText("d")
    p.b.cols["distance"].setCurrentText("d")
    p.form.set_value("limit", "1 pc")
    p.match()
    assert list(p.result["matched"]) == [True, False]
    assert p.result["sep3d_pc"][0] == pytest.approx(0.5)
    p.form.set_value("op", cm.MATCH_OPS[3])
    p.form.set_value("limit", "11 pc")
    p.match()
    assert len(p.result) >= 2


def test_text_input_match(qtbot, ws):
    p = make(qtbot, ws, cm.MatchPanel)
    p.a.source.setCurrentText(common.TEXT)
    p.b.source.setCurrentText(common.TEXT)
    p.a.text.setPlainText("10 10")
    p.b.text.setPlainText("10 10.001\n50 50")
    p.form.set_value("limit", "")
    p.match()
    assert p.result["idx_b"][0] == 0
    assert p.result["sep_arcsec"][0] == pytest.approx(3.6, abs=1e-3)


def test_space_motion_barnards_star(qtbot, ws):
    p = make(qtbot, ws, cm.SpaceMotionPanel)
    p.inp.text.setPlainText("269.45402305 4.66828815")
    p.form.set_value("new_obstime", "J2010.0")
    p.apply()
    t = p.table_view.model._table
    # 10 yr * 10.328"/yr in dec (RV/perspective effects change this by < 0.1")
    assert t["shift_arcsec"][0] == pytest.approx(103.6, abs=0.5)
    assert t["lat_after_deg"][0] - t["lat_before_deg"][0] == pytest.approx(0.02869, abs=2e-4)
    assert "moved" in ws


def test_space_motion_dt_and_errors(qtbot, ws, errors):
    p = make(qtbot, ws, cm.SpaceMotionPanel)
    p.form.set_value("new_obstime", "")
    p.form.set_value("dt", "10 yr")
    p.apply()
    assert not errors
    p.form.set_value("dt", "")
    p.apply()  # neither
    p.form.set_value("new_obstime", "J2020")
    p.inp.pm_lon.setText("")
    p.inp.pm_lat.setText("")
    p.inp.rv.setText("")
    p.apply()  # no PM
    p.inp.pm_lon.setText("1")
    p.inp.pm_lat.setText("1")
    p.inp.frame.obstime.setText("")
    p.apply()  # no epoch
    assert len(errors) == 3
    errors.clear()


def test_concatenate(qtbot, ws, errors):
    ws.put("one", SkyCoord(1 * u.deg, 2 * u.deg))
    ws.put("two", SkyCoord([3, 4] * u.deg, [5, 6] * u.deg))
    p = make(qtbot, ws, cm.ConcatPanel)
    p.concat()
    assert len(errors) == 1
    errors.clear()
    for i in range(p.list.count()):
        p.list.item(i).setSelected(True)
    p.concat()
    assert len(ws.get("combined")) == 3


def test_specs_open(qtbot, ws):
    for spec in cm.SPECS:
        qtbot.addWidget(spec.factory(ws))


def test_concatenate_mixed_frames(qtbot, ws):
    ws.put("icrs", SkyCoord(10 * u.deg, 20 * u.deg))
    ws.put("gal", SkyCoord(120 * u.deg, -20 * u.deg, frame="galactic"))
    p = make(qtbot, ws, cm.ConcatPanel)
    for i in range(p.list.count()):
        p.list.item(i).setSelected(True)
    p.concat()
    out = ws.get("combined")
    assert len(out) == 2 and out.frame.name == "galactic"  # frame of the first (sorted) item
    assert out[0].l.deg == pytest.approx(120.0)
    assert out[1].icrs.ra.deg == pytest.approx(10.0)
