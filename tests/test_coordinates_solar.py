import importlib.util

import numpy as np
import pytest
from astropy import units as u
from astropy.coordinates import AltAz, EarthLocation, SkyCoord, get_body, solar_system_ephemeris
from astropy.time import Time

from astrotools_adv.modules import coordinates_common as common
from astrotools_adv.modules import coordinates_solar as cs
from coord_helpers import errors  # noqa: F401


def make(qtbot, ws, cls):
    p = cls(ws)
    qtbot.addWidget(p)
    return p


def bodies_panel(qtbot, ws, times="2024-03-20T03:06:00"):
    p = make(qtbot, ws, cs.SolarSystemPanel)
    p.form.set_value("times", times)
    return p


def row(table, body, key):
    return next(r[key] for r in table if r["body"] == body)


def test_sun_at_equinox(qtbot, ws):
    p = bodies_panel(qtbot, ws)
    p.compute()
    app, bary = p.result
    # GCRS axes are J2000: 24 yr of precession puts the equinox Sun at dec ~ -0.134 deg
    assert row(app, "sun", "dec_deg") == pytest.approx(-0.134, abs=0.01)
    assert row(app, "sun", "distance_AU") == pytest.approx(0.9958, abs=0.001)
    assert 0.0024 < row(app, "moon", "distance_AU") < 0.0028
    assert 3.9 < row(app, "jupiter", "distance_AU") < 6.5
    assert row(app, "sun", "ecl_lat_deg") == pytest.approx(0.0, abs=0.01)
    lon = row(app, "sun", "ecl_lon_deg")  # true ecliptic of date: ~0 at the March equinox
    assert min(lon, 360 - lon) < 0.01
    assert "alt_deg" not in app.colnames


def test_barycentric_vectors(qtbot, ws):
    p = bodies_panel(qtbot, ws)
    p.compute()
    _app, bary = p.result
    earth = next(r for r in bary if r["body"] == "earth")
    r = np.sqrt(earth["x_AU"] ** 2 + earth["y_AU"] ** 2 + earth["z_AU"] ** 2)
    v = np.sqrt(earth["vx_kms"] ** 2 + earth["vy_kms"] ** 2 + earth["vz_kms"] ** 2)
    assert r == pytest.approx(0.996, abs=0.01)
    assert 29.0 < v < 30.5
    sun = next(r for r in bary if r["body"] == "sun")
    assert np.sqrt(sun["x_AU"] ** 2 + sun["y_AU"] ** 2 + sun["z_AU"] ** 2) < 0.012
    assert {"earth", "earth-moon-barycenter"} <= set(bary["body"])


def test_topocentric_option_and_multiple_times(qtbot, ws):
    p = bodies_panel(qtbot, ws, "2024-03-20T00:00:00\n2024-03-20T12:00:00")
    p.form.set_value("topo", True)
    p.use_loc.lon.setText("0")
    p.use_loc.lat.setText("51.4769")
    p.compute()
    app = p.result[0]
    assert "alt_deg" in app.colnames
    sun_rows = [r for r in app if r["body"] == "sun"]
    assert len(sun_rows) == 2 and sun_rows[0]["alt_deg"] < 0 < sun_rows[1]["alt_deg"]
    p.store()
    assert "bodies_apparent" in ws and "bodies_barycentric" in ws


def test_unavailable_ephemeris_reports(qtbot, ws, errors, monkeypatch):
    p = bodies_panel(qtbot, ws)
    p.form.set_value("ephemeris", "de432s")
    monkeypatch.setattr(importlib.util, "find_spec", lambda name, *a, **k: None)
    p.compute()
    assert len(errors) == 1 and "jplephem" in str(errors[0])
    errors.clear()
    assert solar_system_ephemeris.get() == "builtin"


def test_failed_kernel_download_resets_to_builtin(monkeypatch):
    monkeypatch.setattr(importlib.util, "find_spec", lambda *a, **k: object())

    def boom(name):
        raise OSError("no network")
    original = solar_system_ephemeris.set

    class Fake:
        set = staticmethod(lambda name: boom(name) if name != "builtin" else original(name))
        get = staticmethod(solar_system_ephemeris.get)
    monkeypatch.setattr(cs, "solar_system_ephemeris", Fake)
    with pytest.raises(cs.ParseError) as exc:
        with cs.ephemeris_context("de440"):
            pass
    assert "not available" in str(exc.value)
    assert solar_system_ephemeris.get() == "builtin"


def test_bodies_garbage(qtbot, ws, errors):
    p = bodies_panel(qtbot, ws, "yesterday-ish")
    p.compute()
    p.form.set_value("times", "2024-01-01")
    for i in range(p.bodies.count()):
        p.bodies.item(i).setSelected(False)
    p.compute()
    assert len(errors) == 2
    errors.clear()


# ---- sun / moon / twilight --------------------------------------------------- #
def sunmoon_panel(qtbot, ws, start="2024-03-20T12:00:00", lat="0", lon="0", **kw):
    p = make(qtbot, ws, cs.SunMoonPanel)
    p.loc.lon.setText(lon)
    p.loc.lat.setText(lat)
    p.loc.height.setText("0 m")
    p.form.set_value("start", start)
    for k, v in kw.items():
        p.form.set_value(k, v)
    return p


def event_time(res, name):
    return Time(next(r["time"] for r in res["events"] if r["event"] == name))


def test_sunrise_sunset_and_twilight_equator(qtbot, ws):
    p = sunmoon_panel(qtbot, ws)
    p.compute()
    r = p.result
    sunrise, sunset = event_time(r, "Sunrise"), event_time(r, "Sunset")
    day0 = Time("2024-03-20T00:00:00")
    assert (sunrise - day0).to_value(u.h) == pytest.approx(30.07, abs=0.08)
    assert (sunset - day0).to_value(u.h) == pytest.approx(18.2, abs=0.1)
    civil = event_time(r, "Civil dawn (Sun at -6 deg)")
    naut = event_time(r, "Nautical dawn (Sun at -12 deg)")
    astro = event_time(r, "Astronomical dawn (Sun at -18 deg)")
    assert (sunrise - civil).to_value(u.min) == pytest.approx(20.7, abs=2)
    assert (sunrise - naut).to_value(u.min) == pytest.approx(44.7, abs=3)
    assert (sunrise - astro).to_value(u.min) == pytest.approx(68.7, abs=3)
    noon = next(row for row in r["events"] if row["event"] == "Solar noon")
    assert noon["altitude_deg"] > 89
    dark = r["darkness"]
    assert len(dark) == 1 and 9.3 < dark["hours"][0] < 9.9


def test_window_starting_in_the_dark(qtbot, ws):
    p = sunmoon_panel(qtbot, ws, start="2024-03-20T00:00:00", hours=4)
    p.compute()
    dark = p.result["darkness"]
    assert len(dark) == 1 and dark["hours"][0] == pytest.approx(4.0)  # clipped to window
    assert "Sunrise" not in [r["event"] for r in p.result["events"]]


def test_polar_summer_no_sunset(qtbot, ws):
    p = sunmoon_panel(qtbot, ws, start="2024-06-21T00:00:00", lat="80", lon="0")
    p.compute()
    names = [r["event"] for r in p.result["events"]]
    assert "Sunrise" not in names and "Sunset" not in names
    assert len(p.result["darkness"]) == 0


def test_moonrise_altitude_is_horizon(qtbot, ws):
    p = sunmoon_panel(qtbot, ws, hours=30)
    p.compute()
    r = p.result
    rises = [x for x in r["events"] if x["event"] == "Moonrise"]
    assert rises
    t = Time(rises[0]["time"])
    loc = EarthLocation.from_geodetic(0 * u.deg, 0 * u.deg, 0 * u.m)
    with common.offline_iers():
        alt = get_body("moon", t, loc).transform_to(AltAz(obstime=t, location=loc)).alt.deg
    assert alt == pytest.approx(-0.833, abs=0.05)  # events print whole seconds (~0.004 deg)


def test_moon_phase_and_separation(qtbot, ws):
    p = sunmoon_panel(qtbot, ws, start="2024-04-08T18:21:00")
    p.targets.text.setPlainText("0 0\n180 0")
    p.compute()
    assert p.result["phase"] == "New Moon" and p.result["illumination"] < 0.01
    sep = p.result["moon_separation"]
    assert len(sep) == 2 and np.all((sep["moon_sep_deg"] >= 0) & (sep["moon_sep_deg"] <= 180))
    total = sep["moon_sep_deg"][0] + sep["moon_sep_deg"][1]  # triangle inequality on the sphere
    assert 180.0 - 1e-9 <= total < 195.0
    assert "New Moon" in p.info.toPlainText()
    p.store()
    assert "sunmoon_events" in ws and "sunmoon_night" in ws


def test_phase_names():
    assert cs.phase_name(0.5, True) == "First Quarter"
    assert cs.phase_name(0.5, False) == "Last Quarter"
    assert cs.phase_name(0.99, True) == "Full Moon"
    assert cs.phase_name(0.2, False) == "Waning Crescent"
    assert cs.phase_name(0.8, True) == "Waxing Gibbous"
    assert cs.is_waxing(Time("2024-04-15T19:13:00"))
    assert not cs.is_waxing(Time("2024-05-01T11:27:00"))


def test_sunmoon_errors(qtbot, ws, errors):
    p = sunmoon_panel(qtbot, ws, start="nonsense")
    p.compute()
    p.form.set_value("start", "2024-01-01")
    p.form.set_value("hours", 720)
    p.form.set_value("step", 0.5)
    p.compute()
    p.loc.lat.setText("100")
    p.compute()
    assert len(errors) == 3
    errors.clear()


def test_specs_open(qtbot, ws):
    for spec in cs.SPECS:
        qtbot.addWidget(spec.factory(ws))
