import numpy as np
import pytest
from astropy import units as u
from astropy.coordinates import get_sun
from astropy.table import Table
from astropy.time import Time, TimeDelta
from astropy.utils import iers

from astrotools_adv.core.parsing import ParseError
from astrotools_adv.modules import time_tools as m


@pytest.fixture(autouse=True)
def dialogs(monkeypatch):
    """Collect error dialogs instead of opening modal boxes."""
    shown = []
    monkeypatch.setattr("astrotools_adv.core.widgets.error_box",
                        lambda parent, exc, detail="": shown.append(exc))
    return shown


def panel(qtbot, ws, key):
    spec = next(s for s in m.SPECS if s.key == key)
    w = spec.factory(ws)
    qtbot.addWidget(w)
    return w


def fill(p, **values):
    for k, v in values.items():
        p.form.set_value(k, v)


def first_line(p, prefix):
    return next(ln for ln in p.out.toPlainText().splitlines() if ln.strip().startswith(prefix))


def format_value(p, fmt, index=0):
    t = p.formats.model._table
    return str(t[(t["format"] == fmt) & (t["index"] == index)][0]["value"])


def test_specs(qtbot, ws):
    assert len({s.key for s in m.SPECS}) == len(m.SPECS) == 4
    for s in m.SPECS:
        assert s.category == "Basics" and s.factory(ws) is not None


# ---- converter ------------------------------------------------------------- #
def test_j2000_all_formats(qtbot, ws, dialogs):
    p = panel(qtbot, ws, "time_converter")
    fill(p, values="2000-01-01 12:00:00", scale="utc", out_format="jd")
    p.convert()
    assert "2451545.0" in p.out.toPlainText()
    assert format_value(p, "jd") == "2451545.0"
    assert format_value(p, "mjd") == "51544.5"
    assert format_value(p, "jyear_str") == "J2000.000"
    assert format_value(p, "unix") == "946728000.0"
    assert format_value(p, "gps") == "630763213.0"
    assert format_value(p, "yday") == "2000:001:12:00:00.000"
    assert float(format_value(p, "jyear")) == pytest.approx(2000.0, abs=1e-9)
    assert format_value(p, "ymdhms").startswith("(2000, 1, 1, 12, 0")
    assert "2000-01-01 12:00:00" in format_value(p, "datetime")
    assert not dialogs


def test_scale_conversions(qtbot, ws):
    p = panel(qtbot, ws, "time_converter")
    fill(p, values="2000-01-01 12:00:00", scale="utc", out_scale="tt")
    p.convert()
    assert "2000-01-01 12:01:04.184" in p.out.toPlainText()  # TT = UTC + 64.184 s
    fill(p, out_scale="tai")
    p.convert()
    assert "2000-01-01 12:00:32.000" in p.out.toPlainText()  # TAI = UTC + 32 s
    t = p.scales.model._table
    row = t[t["scale"] == "ut1"][0]
    assert row["iso"].startswith("2000-01-01 12:00:00.35")  # UT1-UTC = +0.355 s


def test_numeric_input_formats_and_multiple_times(qtbot, ws, dialogs):
    p = panel(qtbot, ws, "time_converter")
    fill(p, values="2451545, 2451546.5\n2451547", fmt="jd", scale="utc", out_format="iso",
         precision=0)
    p.convert()
    text = p.out.toPlainText()
    assert "3 time(s)" in text
    assert "2000-01-01 12:00:00" in text and "2000-01-03 00:00:00" in text
    assert isinstance(p._last, Time) and p._last.size == 3
    fill(p, values="51544.5", fmt="mjd", out_format="jd", precision=3)
    p.convert()
    assert "2451545.0" in p.out.toPlainText()
    fill(p, values="J2000", fmt="auto", scale="auto", out_format="isot")
    p.convert()
    assert "2000-01-01T12:00:00" in p.out.toPlainText()
    assert not dialogs


def test_mixed_formats_in_lines_and_strftime(qtbot, ws):
    p = panel(qtbot, ws, "time_converter")
    fill(p, values="2020-02-29T23:59:59\n# comment\n2021-12-31 00:00:00", fmt="auto",
         scale="utc", strftime="%d.%m.%Y", out_format="iso")
    p.convert()
    text = p.out.toPlainText()
    assert "29.02.2020" in text and "31.12.2021" in text


def test_precision_and_epochs(qtbot, ws):
    p = panel(qtbot, ws, "time_converter")
    fill(p, values="2000-01-01 12:00:00", scale="utc", out_format="iso", precision=6)
    p.convert()
    assert "2000-01-01 12:00:00.000000" in p.out.toPlainText()
    fill(p, values="B1950", fmt="auto", scale="auto", out_format="jd", precision=3)
    p.convert()
    assert "2433282.4234" in p.out.toPlainText()  # Besselian 1950.0 = JD 2433282.4235


def test_location_is_used(qtbot, ws, dialogs):
    p = panel(qtbot, ws, "time_converter")
    fill(p, values="2024-06-01 00:00:00", scale="utc", out_scale="tdb", lon="-5.9", lat="37.9",
         height="100 m", precision=9)
    p.convert()
    assert "location lon=-5.9" in p.out.toPlainText()
    assert p._last.location is not None and not dialogs
    fill(p, lat="")
    p.convert()
    assert isinstance(dialogs[-1], ParseError)


def test_converter_errors(qtbot, ws, dialogs):
    p = panel(qtbot, ws, "time_converter")
    for values, fmt, scale in [("", "auto", "auto"), ("not a time", "auto", "auto"),
                               ("abc", "jd", "utc"), ("2000-13-45", "auto", "auto"),
                               ("2000-01-01", "mjd", "utc")]:
        dialogs.clear()
        fill(p, values=values, fmt=fmt, scale=scale)
        p.convert()
        assert len(dialogs) == 1 and isinstance(dialogs[0], ParseError), values


def test_store_in_workspace(qtbot, ws, dialogs):
    p = panel(qtbot, ws, "time_converter")
    p.store_last()
    assert isinstance(dialogs[-1], ParseError)
    fill(p, values="2000-01-01 12:00:00", scale="utc", store_name="t0")
    p.convert()
    p.store_last()
    assert ws.get("t0").jd == pytest.approx(2451545.0)


def test_iers_download_is_disabled_and_restored(qtbot, ws):
    before = iers.conf.auto_download
    seen = {}

    def probe():
        seen["inside"] = iers.conf.auto_download

    m.capture(probe)
    assert seen["inside"] is False and iers.conf.auto_download == before
    with pytest.raises(ParseError):
        m.capture(lambda: Time("garbage"))
    assert iers.conf.auto_download == before


def test_capture_collects_warnings():
    _, notes = m.capture(lambda: __import__("warnings").warn("careful"))
    assert notes == ["careful"]


def test_far_future_ut1_degrades_gracefully(qtbot, ws, dialogs):
    p = panel(qtbot, ws, "time_converter")
    fill(p, values="2400-01-01 00:00:00", scale="utc", out_scale="ut1")
    p.convert()
    assert not dialogs  # extrapolated or reported, never a crash
    assert "2399-12-31 23:59:59" in p.out.toPlainText()  # UT1 slightly before UTC
    assert "Notes:" in p.out.toPlainText()  # ERFA 'dubious year' is surfaced


# ---- arithmetic ---------------------------------------------------------------- #
def arith(p, op, **kw):
    fill(p, op=op, **kw)
    p.compute()


def test_difference(qtbot, ws, dialogs):
    p = panel(qtbot, ws, "time_arithmetic")
    arith(p, "t1 - t2", t1="2024-03-10 06:00:00", t2="2024-03-12 18:30:00")
    text = p.out.toPlainText()
    assert "sec: -217800.0" in text and "jd: -2.5208333" in text
    assert isinstance(p._last, TimeDelta)
    assert p._last.to_value(u.h) == pytest.approx(-60.5)


def test_leap_second_difference(qtbot, ws):
    p = panel(qtbot, ws, "time_arithmetic")
    arith(p, "t1 - t2", t1="2017-01-01 00:00:00", t2="2016-12-31 23:59:59", scale="utc")
    assert p._last.to_value(u.s) == pytest.approx(2.0)  # leap second 2016-12-31T23:59:60


def test_offsets(qtbot, ws, dialogs):
    p = panel(qtbot, ws, "time_arithmetic")
    arith(p, "t1 + delta", t1="2024-03-10 06:00:00", delta="1.5 d")
    assert p._last.iso.startswith("2024-03-11 18:00:00")
    arith(p, "t1 - delta", delta="36 h")
    assert p._last.iso.startswith("2024-03-08 18:00:00")
    arith(p, "t1 + delta", delta="2")  # plain number = days
    assert p._last.iso.startswith("2024-03-12 06:00:00")
    arith(p, "t1 + delta", delta="3600 s")
    assert p._last.iso.startswith("2024-03-10 07:00:00")
    assert not dialogs


def test_ranges(qtbot, ws, dialogs):
    p = panel(qtbot, ws, "time_arithmetic")
    arith(p, "range t1 .. t2", t1="2024-01-01 00:00:00", t2="2024-01-02 00:00:00", n=5)
    t = p.table.model._table
    assert len(t) == 5 and t["iso"][2].startswith("2024-01-01 12:00:00")
    assert float(t["jd"][4]) - float(t["jd"][0]) == pytest.approx(1.0)
    arith(p, "range t1 + k*delta", delta="6 h", n=4)
    assert [x[11:19] for x in p.table.model._table["iso"]] == ["00:00:00", "06:00:00", "12:00:00",
                                                               "18:00:00"]
    assert not dialogs


def test_arithmetic_errors(qtbot, ws, dialogs):
    p = panel(qtbot, ws, "time_arithmetic")
    cases = [dict(op="t1 + delta", delta="3 m"), dict(op="t1 + delta", delta=""),
             dict(op="t1 + delta", delta="junk"), dict(op="t1 - t2", t2=""),
             dict(op="range t1 .. t2", t1="2024-01-01\n2024-01-02", t2="2024-01-03", n=3),
             dict(op="t1 + delta", t1="not a time", delta="1 d")]
    for case in cases:
        dialogs.clear()
        fill(p, t1="2024-01-01 00:00:00", t2="2024-01-02 00:00:00", delta="1 d", n=3)
        arith(p, **case)
        assert len(dialogs) == 1 and isinstance(dialogs[0], ParseError), case


# ---- sidereal / light time ------------------------------------------------------ #
def sidereal(p, **kw):
    fill(p, **kw)
    p.compute()
    return p.table.model._table


def test_gmst_at_j2000(qtbot, ws, dialogs):
    p = panel(qtbot, ws, "sidereal_light_time")
    t = sidereal(p, values="2000-01-01 12:00:00", scale="ut1", kind="mean", do_ltt=False)
    assert t["LST [h]"][0] == pytest.approx(18.697374558, abs=2e-5)  # GMST at J2000.0
    assert t["LST [hms]"][0].startswith("18:41:50.5")
    assert "Greenwich" in p.out.toPlainText()
    t = sidereal(p, lon="90", lat="0")
    assert t["LST [h]"][0] == pytest.approx((18.697374558 + 6) % 24, abs=2e-5)
    t = sidereal(p, lon="-5.9", lat="37.9", kind="apparent")
    assert t["LST [h]"][0] == pytest.approx(18.697374558 - 5.9 / 15, abs=1e-3)
    assert not dialogs


def test_sidereal_models_and_errors(qtbot, ws, dialogs):
    p = panel(qtbot, ws, "sidereal_light_time")
    sidereal(p, values="2000-01-01 12:00:00", scale="ut1", do_ltt=False, kind="mean",
             model="IAU1982")
    assert not dialogs
    sidereal(p, model="IAU2000A")  # model does not belong to 'mean'
    assert isinstance(dialogs[-1], ParseError)
    dialogs.clear()
    fill(p, model="default", do_lst=False, do_ltt=False)
    p.compute()
    assert isinstance(dialogs[-1], ParseError)


def test_light_travel_time(qtbot, ws, dialogs):
    p = panel(qtbot, ws, "sidereal_light_time")
    when = Time("2000-01-01 12:00:00", scale="utc")
    sun = get_sun(when)
    sky = f"{sun.ra.deg:.6f} {sun.dec.deg:.6f}"
    anti = f"{(sun.ra.deg + 180) % 360:.6f} {-sun.dec.deg:.6f}"
    sidereal(p, values="2000-01-01 12:00:00", scale="utc", do_lst=False, do_ltt=True, sky=sky,
             ltt_kind="barycentric")
    bary = p.table.model._table["LTT [s]"][0]
    assert 485.0 < abs(bary) < 500.0  # ~1 AU light time (Earth near perihelion)
    sidereal(p, ltt_kind="heliocentric")
    helio = p.table.model._table["LTT [s]"][0]
    assert abs(bary - helio) < 5.0
    sidereal(p, ltt_kind="barycentric", sky=anti)
    assert np.sign(p.table.model._table["LTT [s]"][0]) == -np.sign(bary)
    assert "geocentric" in p.out.toPlainText()
    sidereal(p, lon="-5.9", lat="37.9")
    assert "given location" in p.out.toPlainText()
    corrected = Time(p.table.model._table["corrected JD"][0], format="jd", scale="tdb")
    assert abs((corrected - when.tdb).to_value(u.s)) < 600
    assert not dialogs
    sidereal(p, sky="")
    assert isinstance(dialogs[-1], ParseError)


# ---- IERS ------------------------------------------------------------------------ #
def test_leap_seconds_table(qtbot, ws, dialogs):
    p = panel(qtbot, ws, "time_leap_iers")
    p.leap_seconds()
    t = p.table.model._table
    assert isinstance(t, Table) and t["year"][0] == 1960
    assert (t["year"][-1], t["month"][-1], t["TAI-UTC [s]"][-1]) == (2017, 1, 37.0)
    assert "expires" in p.out.toPlainText() and not dialogs


def test_earth_orientation_at_date(qtbot, ws, dialogs):
    p = panel(qtbot, ws, "time_leap_iers")
    p.form.set_value("date", "2020-01-01 00:00:00")
    p.orientation()
    text = p.out.toPlainText()
    assert "TAI-UTC:    37.0 s" in text
    assert "UT1-UTC:    -0.17" in text and "IERS-B" in text
    assert "Polar x, y: 0.0766" in text
    p.form.set_value("date", "1950-01-01")
    p.orientation()
    assert "before the table" in p.out.toPlainText() and not dialogs
    p.form.set_value("date", "nonsense")
    p.orientation()
    assert isinstance(dialogs[-1], ParseError)


def test_iers_range(qtbot, ws, dialogs):
    p = panel(qtbot, ws, "time_leap_iers")
    p.table_range()
    text = p.out.toPlainText()
    assert "MJD range: 41684" in text and "Auto-download: False" in text and not dialogs


def test_tai_minus_utc_across_history():
    for date, expected in [("1972-01-01", 10.0), ("1999-01-01", 32.0), ("2017-01-01", 37.0),
                           ("2024-01-01", 37.0)]:
        assert m.tai_minus_utc(Time(date, scale="utc")) == pytest.approx(expected, abs=1e-6)


def test_tai_minus_utc_on_a_leap_second_day():
    """The day ending in a leap second must not show a fractional offset (was 36.999977)."""
    for date in ("2016-12-31 00:00:00", "2016-12-31 12:00:00", "2016-12-31 23:59:59"):
        assert m.tai_minus_utc(Time(date, scale="utc")) == pytest.approx(36.0, abs=1e-9)
    assert m.tai_minus_utc(Time("2017-01-01", scale="utc")) == pytest.approx(37.0, abs=1e-9)
    arr = m.tai_minus_utc(Time(["2016-12-31 23:59:59", "2017-01-01"], scale="utc"))
    assert list(arr) == [36.0, 37.0]
