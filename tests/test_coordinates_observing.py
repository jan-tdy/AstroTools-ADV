import numpy as np
import pytest
from astropy import units as u
from astropy.coordinates import EarthLocation, SkyCoord
from astropy.table import Table
from astropy.time import Time
from astropy.utils import iers

from astrotools_adv.core.parsing import ParseError
from astrotools_adv.modules import coordinates_common as common
from astrotools_adv.modules import coordinates_observing as co
from coord_helpers import errors  # noqa: F401


def make(qtbot, ws, cls):
    p = cls(ws)
    qtbot.addWidget(p)
    return p


# ---- offline guard ---------------------------------------------------------- #
def test_offline_iers_sets_and_restores():
    before = (iers.conf.auto_download, iers.conf.iers_degraded_accuracy)
    with common.offline_iers():
        assert iers.conf.auto_download is False
        assert iers.conf.iers_degraded_accuracy == "ignore"
    assert (iers.conf.auto_download, iers.conf.iers_degraded_accuracy) == before
    with pytest.raises(RuntimeError):
        with common.offline_iers():
            raise RuntimeError("boom")
    assert (iers.conf.auto_download, iers.conf.iers_degraded_accuracy) == before


def test_far_future_altaz_works_offline():
    loc = EarthLocation.from_geodetic(0 * u.deg, 50 * u.deg, 0 * u.m)
    with common.offline_iers():
        from astropy.coordinates import AltAz
        t = Time("2090-01-01T00:00:00")
        aa = SkyCoord(10 * u.deg, 20 * u.deg).transform_to(AltAz(obstime=t, location=loc))
    assert np.isfinite(aa.alt.deg)


# ---- location input / observatory ------------------------------------------ #
def test_location_modes(qtbot, ws, errors):
    li = common.LocationInput(ws)
    qtbot.addWidget(li)
    li.lon.setText("-4.7")
    li.lat.setText("38d")
    li.height.setText("500")
    g = li.get().geodetic
    assert g.lon.deg == pytest.approx(-4.7) and g.lat.deg == pytest.approx(38.0)
    assert g.height.to_value(u.m) == pytest.approx(500.0)
    li.set_mode("Geocentric")
    li.xyz.setText("6378137 0 0 m")
    assert li.get().lat.deg == pytest.approx(0.0)
    li.xyz.setText("1 2")
    with pytest.raises(ParseError):
        li.get()
    li.set_mode("Site name")
    li.site.setEditText("greenwich")
    assert li.get().lat.deg == pytest.approx(51.4769, abs=0.01)
    li.site.setEditText("no such place at all xyz")
    with pytest.raises(ParseError):
        li.get()
    li.set_mode("Geodetic")
    li.lat.setText("95")
    with pytest.raises(ParseError):
        li.get()
    li.set_mode("Workspace")
    with pytest.raises(ParseError):
        li.get()
    ws.put("here", EarthLocation.from_geodetic(1 * u.deg, 2 * u.deg, 3 * u.m))
    assert li.get().lon.deg == pytest.approx(1.0)


def test_site_names_and_fallback(monkeypatch):
    assert "greenwich" in [s.lower() for s in common.site_names()]
    monkeypatch.setattr(EarthLocation, "of_site", classmethod(
        lambda cls, name, **k: (_ for _ in ()).throw(OSError("offline"))))
    loc = common.site_location("Greenwich")  # built-in fallback
    assert loc.lat.deg == pytest.approx(51.4769, abs=1e-3)


def test_observatory_panel(qtbot, ws, errors):
    p = make(qtbot, ws, co.ObservatoryPanel)
    p.loc.set_mode("Geodetic")
    p.loc.lon.setText("-4.7")
    p.loc.lat.setText("38")
    p.show_location()
    t = p.table_view.model._table
    rows = {r["property"]: r["value"] for r in t}
    assert float(rows["latitude [deg]"]) == pytest.approx(38.0)
    p.store()
    assert isinstance(ws.get("site"), EarthLocation)
    p.loc.lat.setText("abc")
    p.show_location()
    assert len(errors) == 1
    errors.clear()


# ---- visibility ---------------------------------------------------------------- #
def vis_panel(qtbot, ws, lat="45", lon="0", targets="37.9546 89.2641"):
    p = make(qtbot, ws, co.VisibilityPanel)
    p.loc.lon.setText(lon)
    p.loc.lat.setText(lat)
    p.loc.height.setText("0 m")
    p.targets.text.setPlainText(targets)
    return p


def test_polaris_altitude_is_latitude(qtbot, ws):
    p = vis_panel(qtbot, ws)
    p.form.set_value("start", "2024-03-20T00:00:00")
    p.form.set_value("hours", 24)
    p.compute()
    alt = p.result["alt"][0]
    assert np.all(np.abs(alt - 45.0) < 1.0)
    assert alt.max() - alt.min() > 0.3  # it does move around the pole a bit
    assert p.alt_plot.figure.axes and p.sky_plot.figure.axes
    ev = p.result["events"]
    assert ev["status"][0] == "always above horizon"


def test_sun_altitude_greenwich_solstice(qtbot, ws):
    p = vis_panel(qtbot, ws, lat="51.4769", lon="0")
    p.form.set_value("start", "2024-06-21T11:00:00")
    p.form.set_value("hours", 2)
    p.form.set_value("step", 1)
    p.compute()
    assert p.result["sun_alt"].max() == pytest.approx(90 - 51.4769 + 23.44, abs=0.25)
    assert p.result["moon_alt"].shape == p.result["sun_alt"].shape


def test_rise_transit_set(qtbot, ws):
    start = Time("2024-03-20T00:00:00")
    ra = (start + 3 * u.hour).sidereal_time("mean", "greenwich").deg  # transits ~3h after start
    p = vis_panel(qtbot, ws, lat="0", lon="0", targets=f"{ra} 0")
    p.form.set_value("start", "2024-03-20T00:00:00")
    p.form.set_value("hours", 22)
    p.form.set_value("step", 5)
    p.compute()
    ev = p.result["events"]
    t_tr, t_set, t_rise = (Time(ev[k][0]) for k in ("transit", "set", "rise"))
    sid = 0.9972696
    assert (t_tr - start).to_value(u.h) == pytest.approx(3 * sid, abs=0.06)
    assert (t_set - t_tr).to_value(u.h) == pytest.approx(6 * sid, abs=0.03)
    assert (t_rise - t_tr).to_value(u.h) == pytest.approx(18 * sid, abs=0.03)
    assert ev["transit_alt_deg"][0] > 89.5
    # all sample times at the event are consistent with the altitude track
    alt = p.result["alt"][0]
    assert alt.max() > 89.0 and alt.min() < -80.0


def test_sunrise_equator_equinox_via_helper():
    loc = EarthLocation.from_geodetic(0 * u.deg, 0 * u.deg, 0 * u.m)
    start = Time("2024-03-20T00:00:00")
    with common.offline_iers():
        func = common.altitude_function(loc, None, "sun")
        rise, setting = common.find_crossings(func, start, 24, 10, level=-0.833)
    assert len(rise) == 1 and len(setting) == 1
    assert (rise[0] - start).to_value(u.h) == pytest.approx(6.07, abs=0.08)  # ~06:04 UTC
    assert (setting[0] - start).to_value(u.h) == pytest.approx(18.2, abs=0.1)


def test_refraction_raises_altitude(qtbot, ws):
    p = vis_panel(qtbot, ws, targets="100 0", lat="0")
    p.form.set_value("start", "2024-03-20T00:00:00")
    p.form.set_value("hours", 24)
    p.form.set_value("step", 5)
    p.compute()
    a0 = p.result["alt"][0].copy()
    p.form.set_value("pressure", "1013")
    p.compute()
    a1 = p.result["alt"][0]
    low = (a0 > -0.3) & (a0 < 10)
    assert low.any() and np.all(a1[low] > a0[low])


def test_visibility_table_and_store(qtbot, ws):
    p = vis_panel(qtbot, ws, targets="10 20\n30 -20")
    p.form.set_value("start", "2024-03-20T00:00:00")
    p.form.set_value("hours", 2)
    p.form.set_value("step", 30)
    p.form.set_value("offset", 2)
    p.compute()
    t = p.result["table"]
    assert len(t) == 2 * 5 and t["time"][0].startswith("2024-03-20 02:00")
    assert t["target"][0] == "10 20"
    p.store()
    assert "visibility_track" in ws and "visibility_events" in ws


def test_visibility_errors(qtbot, ws, errors):
    p = vis_panel(qtbot, ws)
    p.form.set_value("start", "garbage")
    p.compute()
    p.form.set_value("start", "2024-01-01")
    p.form.set_value("hours", 24 * 365)
    p.form.set_value("step", 1)
    p.compute()  # too many samples
    p.form.set_value("hours", 1)
    p.form.set_value("pressure", "-5")
    p.compute()
    p.form.set_value("pressure", "0")
    p.targets.text.setPlainText("")
    p.compute()
    assert len(errors) == 4
    errors.clear()


# ---- moon ----------------------------------------------------------------- #
def test_moon_illumination_new_and_full():
    new = common.moon_illumination(Time("2024-04-08T18:21:00"))
    full = common.moon_illumination(Time("2024-04-24T23:49:00"))
    assert float(new["illumination"]) < 0.01
    assert float(full["illumination"]) > 0.99
    quarter = common.moon_illumination(Time("2024-04-15T19:13:00"))
    assert float(quarter["illumination"]) == pytest.approx(0.5, abs=0.03)


# ---- velocity corrections -------------------------------------------------- #
def test_velocity_corrections(qtbot, ws):
    p = make(qtbot, ws, co.VelocityPanel)
    p.targets.text.setPlainText("0 0")  # on the ecliptic/equator crossing
    p.form.set_value("times", "2024-03-20\n2024-06-20\n2024-09-22\n2024-12-21")
    p.form.set_value("rv", "-300 km/s")
    p.compute()
    t = p.result
    corr = np.array(t["rv_corr_bary_kms"])
    assert 27 < np.abs(corr).max() < 31
    assert np.all(np.abs(np.array(t["rv_corr_bary_kms"]) - np.array(t["rv_corr_helio_kms"])) < 0.02)
    assert np.all(np.abs(np.array(t["ltt_bary_s"])) < 520)
    assert "rv_bary_kms" in t.colnames
    expected = -300 + corr[0] + (-300) * corr[0] / 299792.458
    assert t["rv_bary_kms"][0] == pytest.approx(expected, abs=1e-6)
    # ecliptic pole is (almost) at rest w.r.t. the orbital motion
    p.targets.text.setPlainText("270 66.56")
    p.compute()
    assert np.abs(np.array(p.result["rv_corr_bary_kms"])).max() < 1.0
    p.store()
    assert "velocity_corr" in ws


def test_velocity_broadcast_and_errors(qtbot, ws, errors):
    p = make(qtbot, ws, co.VelocityPanel)
    p.targets.text.setPlainText("0 0\n10 10\n20 20")
    p.form.set_value("times", "2024-01-01")
    p.compute()
    assert len(p.result) == 3
    p.form.set_value("times", "2024-01-01\n2024-02-01")
    p.compute()  # 3 targets vs 2 times
    p.form.set_value("times", "")
    p.compute()
    assert len(errors) == 2
    errors.clear()


def test_specs_open(qtbot, ws):
    for spec in co.SPECS:
        qtbot.addWidget(spec.factory(ws))
