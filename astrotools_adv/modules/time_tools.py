"""Time handling (astropy.time): conversion, arithmetic, sidereal time, light travel time, IERS."""
from __future__ import annotations

import re
import threading
import warnings
from typing import Any, Callable, Dict, List, Optional, Tuple

import erfa
import numpy as np
from astropy import units as u
from astropy.coordinates import EarthLocation
from astropy.table import Table
from astropy.time import Time, TimeDelta
from astropy.utils import iers
from PyQt5.QtWidgets import QWidget

from ..core.parsing import ParseError, parse_angle, parse_skycoord, parse_time, split_lines
from ..core.registry import ModuleSpec
from ..core.widgets import ParamForm
from ..core.workspace import Workspace
from .units_constants import StoringPanel, read_quantity

CATEGORY = "Basics"

INPUT_FORMATS = ["auto", "iso", "isot", "yday", "fits", "jd", "mjd", "decimalyear", "unix",
                 "unix_tai", "cxcsec", "galexsec", "gps", "plot_date", "byear", "jyear",
                 "byear_str", "jyear_str", "stardate"]
NUMERIC_FORMATS = frozenset({"jd", "mjd", "decimalyear", "unix", "unix_tai", "cxcsec", "galexsec",
                             "gps", "plot_date", "byear", "jyear", "stardate"})
INPUT_SCALES = ["auto", "utc", "tai", "tt", "tdb", "tcb", "tcg", "ut1", "local"]
REPORT_SCALES = ["utc", "tai", "tt", "tdb", "tcb", "tcg", "ut1"]
SIDEREAL_MODELS = ["default", "IAU1982", "IAU2006", "IAU1994", "IAU2000A", "IAU2000B", "IAU2006A"]
MAX_FORMAT_ROWS = 50      # times shown in the "all formats" table
MAX_SCALE_ROWS = 200      # times shown in the "all scales" table
MAX_LISTED = 20           # times echoed in the text report

IERS_STATUS = {iers.FROM_IERS_B: "IERS-B (final)", iers.FROM_IERS_A: "IERS-A (observed)",
               iers.FROM_IERS_A_PREDICTION: "IERS-A (prediction)",
               iers.TIME_BEFORE_IERS_RANGE: "before the table (extrapolated)",
               iers.TIME_BEYOND_IERS_RANGE: "beyond the table (extrapolated)"}

GEOCENTER = EarthLocation.from_geocentric(0 * u.m, 0 * u.m, 0 * u.m)
_LOCK = threading.RLock()  # astropy's config / warnings state is process-global


# --------------------------------------------------------------------------- #
# Offline-safe execution
# --------------------------------------------------------------------------- #
def capture(fn: Callable[[], Any]) -> Tuple[Any, List[str]]:
    """Run ``fn`` without IERS downloads; returns ``(value, warning messages)``.

    Astropy errors that stem from user input become :class:`ParseError` so the
    GUI shows a readable message instead of a traceback dialog.
    """
    with _LOCK, iers.conf.set_temp("auto_download", False), \
            warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        try:
            value = fn()
        except ParseError:
            raise
        except iers.IERSRangeError as exc:
            raise ParseError("UT1-UTC data are not available for these dates in the bundled "
                             f"(offline) IERS table: {exc}") from exc
        except (ValueError, TypeError, u.UnitsError, erfa.ErfaError, OverflowError) as exc:
            raise ParseError(str(exc) or type(exc).__name__) from exc
    notes: List[str] = []
    for w in caught:
        text = str(w.message).replace("\n", " ")
        if text not in notes:
            notes.append(text)
    return value, notes


# --------------------------------------------------------------------------- #
# Input parsing
# --------------------------------------------------------------------------- #
def add_time_inputs(form: ParamForm, default: str, label: str = "Time(s)",
                    key: str = "values", fmt_scale: bool = True) -> None:
    form.add_multiline(key, label, default,
                       "One time per line (ISO, 'now', 'J2000', or numbers for numeric formats).",
                       height=90)
    if fmt_scale:
        form.add_combo("fmt", "Input format", INPUT_FORMATS, "'auto' detects ISO-like strings")
        form.add_combo("scale", "Input scale", INPUT_SCALES, "'auto' = astropy default (UTC)")


def add_location_inputs(form: ParamForm, required: bool = False) -> None:
    note = "" if required else "optional; "
    form.add_text("lon", "Longitude", "", f"{note}east-positive, e.g. '-5.9' or '5d54m w'")
    form.add_text("lat", "Latitude", "", f"{note}geodetic, e.g. '37.9' or '37d54m'")
    form.add_text("height", "Height", "0 m", "above the ellipsoid; plain numbers are metres")


def read_location(v: Dict[str, Any]) -> Optional[EarthLocation]:
    lon, lat = (v.get("lon") or "").strip(), (v.get("lat") or "").strip()
    if not lon and not lat:
        return None
    if not (lon and lat):
        raise ParseError("Give both longitude and latitude (or leave both empty).")
    height = read_quantity((v.get("height") or "0").strip() or "0", default_unit=u.m,
                           name="height")
    try:
        return EarthLocation.from_geodetic(parse_angle(lon, name="longitude"),
                                           parse_angle(lat, name="latitude"), height)
    except ValueError as exc:
        raise ParseError(f"Invalid location: {exc}") from exc


def _merge(times: List[Time]) -> Time:
    first = times[0]
    if len(times) == 1:
        return first
    scale = first.scale
    conv = [t if t.scale == scale else getattr(t, scale) for t in times]
    merged = Time([t.jd1 for t in conv], [t.jd2 for t in conv], format="jd", scale=scale)
    merged.format = first.format
    return merged


def read_times(v: Dict[str, Any], key: str = "values") -> Time:
    """Parse the multi-line time field ``key`` (plus optional location) into one Time."""
    fmt, scale = v.get("fmt", "auto"), v.get("scale", "auto")
    text = (v.get(key) or "").strip()
    if fmt in NUMERIC_FORMATS:
        lines = [p for p in re.split(r"[\s,;]+", "\n".join(split_lines(text))) if p]
    else:
        lines = split_lines(text)
    if not lines:
        raise ParseError("Enter at least one time.")
    t = _merge([parse_time(ln, fmt, scale, name=f"time {i}") for i, ln in enumerate(lines, 1)])
    loc = read_location(v)
    return t if loc is None else Time(t, location=loc)


def parse_delta(text: str, name: str = "delta") -> TimeDelta:
    """``'1.5 d'``, ``'3600 s'``, ``'2'`` (days) -> TimeDelta."""
    return TimeDelta(read_quantity(text, default_unit=u.day, name=name))


# --------------------------------------------------------------------------- #
# Formatting
# --------------------------------------------------------------------------- #
def _element(x: Any) -> str:
    if isinstance(x, (float, np.floating)):
        return repr(float(x))
    if isinstance(x, np.void):
        return str(tuple(x.tolist()))
    return str(x)


def values_as_text(t: Time, fmt: str) -> List[str]:
    """Per-element text of ``t`` in format ``fmt``."""
    return [_element(x) for x in np.atleast_1d(t.to_value(fmt))]


def _try_values(t: Time, fmt: str) -> List[str]:
    try:
        return values_as_text(t, fmt)
    except Exception as exc:  # noqa: BLE001 - e.g. datetime of a leap second, UT1 offline
        return [f"n/a ({type(exc).__name__}: {exc})"] * max(t.size, 1)


def _listing(t: Time, fmt: str, indent: str = "  ") -> str:
    vals = values_as_text(t, fmt)
    lines = [indent + x for x in vals[:MAX_LISTED]]
    if len(vals) > MAX_LISTED:
        lines.append(f"{indent}... ({len(vals)} in total)")
    return "\n".join(lines)


def with_notes(text: str, notes: List[str]) -> str:
    if not notes:
        return text
    return text + "\n\nNotes:\n" + "\n".join(f" - {n}" for n in notes)


def _long_table(rows: List[tuple], names: List[str], dtypes: tuple) -> Table:
    if not rows:
        return Table(names=names, dtype=dtypes)
    return Table([np.array(c, dtype=d) for c, d in zip(zip(*rows), dtypes)], names=names)


def formats_table(t: Time) -> Table:
    t = t[:MAX_FORMAT_ROWS] if t.size > 1 else t
    rows = []
    for fmt in Time.FORMATS:
        for i, text in enumerate(_try_values(t, fmt)):
            rows.append((i, fmt, text))
    rows.sort(key=lambda r: r[0])
    return _long_table(rows, ["index", "format", "value"], (int, str, str))


def scales_table(t: Time) -> Table:
    t = t[:MAX_SCALE_ROWS] if t.size > 1 else t
    rows = []
    for scale in REPORT_SCALES:
        try:
            ts = getattr(t, scale)
            cols = [_try_values(ts, f) for f in ("iso", "jd", "mjd")]
        except Exception as exc:  # noqa: BLE001
            msg = f"n/a ({type(exc).__name__}: {exc})"
            cols = [[msg] * max(t.size, 1)] * 3
        for i, (iso, jd, mjd) in enumerate(zip(*cols)):
            rows.append((i, scale, iso, jd, mjd))
    rows.sort(key=lambda r: r[0])
    return _long_table(rows, ["index", "scale", "iso", "jd", "mjd"], (int, str, str, str, str))


# --------------------------------------------------------------------------- #
# Computations (pure; run in worker threads via capture())
# --------------------------------------------------------------------------- #
def convert_times(v: Dict[str, Any]) -> Dict[str, Any]:
    t = read_times(v)
    out_scale = v["out_scale"]
    t_out = t if out_scale == "same as input" else getattr(t, out_scale)
    t_out.precision = int(v["precision"])
    fmt = v["out_format"]
    t_in = t.copy()
    t_in.precision = int(v["precision"])
    where = f", location lon={t.location.lon:.5f} lat={t.location.lat:.5f}" \
        if t.location is not None else ""
    lines = [f"Input:  {t.size} time(s), format={t.format}, scale={t.scale}{where}",
             f"Output: scale={t_out.scale}, format={fmt}, precision={t_out.precision}",
             "", f"{fmt}:", _listing(t_out, fmt)]
    pattern = (v.get("strftime") or "").strip()
    if pattern:
        lines += ["", f"strftime({pattern!r}):"]
        lines += [f"  {x}" for x in np.atleast_1d(t_out.strftime(pattern))[:MAX_LISTED]]
    return {"text": "\n".join(lines), "time": t_out,
            "formats": formats_table(t_out), "scales": scales_table(t_in)}


def time_arithmetic(v: Dict[str, Any]) -> Dict[str, Any]:
    t1 = read_times(v, "t1")
    op = v["op"]
    delta_ops = ("t1 + delta", "t1 - delta", "range t1 + k*delta")

    def need_scalar(x: Any, what: str) -> None:
        if not x.isscalar:
            raise ParseError(f"{what} must be a single value for this operation.")

    if op == "t1 - t2":
        result: Any = t1 - read_times(v, "t2")
    else:
        delta = parse_delta(v["delta"]) if op in delta_ops else None
        if op == "t1 + delta":
            result = t1 + delta
        elif op == "t1 - delta":
            result = t1 - delta
        elif op == "range t1 .. t2":
            need_scalar(t1, "t1")
            t2 = read_times(v, "t2")
            need_scalar(t2, "t2")
            result = t1 + (t2 - t1) * np.linspace(0.0, 1.0, int(v["n"]))
        elif op == "range t1 + k*delta":
            need_scalar(t1, "t1")
            need_scalar(delta, "delta")
            result = t1 + delta * np.arange(int(v["n"]))
        else:
            raise ParseError(f"Unknown operation {op!r}.")
    if isinstance(result, TimeDelta):
        lines = [f"{op} =", f"  scale: {result.scale}"]
        for fmt in ("jd", "sec", "datetime", "quantity_str"):
            lines.append(f"  {fmt}: " + ", ".join(_try_values(result, fmt)[:MAX_LISTED]))
        return {"text": "\n".join(lines), "result": result, "table": None}
    result.precision = 6
    lines = [f"{op} =", f"  scale: {result.scale}", "  iso:", _listing(result, "iso", "    "),
             "  jd:", _listing(result, "jd", "    ")]
    table = None
    if result.size > 1:
        iso, jd, mjd = (_try_values(result, f) for f in ("iso", "jd", "mjd"))
        table = _long_table(list(zip(range(result.size), iso, jd, mjd)),
                            ["index", "iso", "jd", "mjd"], (int, str, str, str))
    return {"text": "\n".join(lines), "result": result, "table": table}


def sidereal_and_light_time(v: Dict[str, Any]) -> Dict[str, Any]:
    t = read_times(v)
    if not (v["do_lst"] or v["do_ltt"]):
        raise ParseError("Tick at least one of sidereal time / light travel time.")
    iso_t = t.copy()
    iso_t.precision = 3
    cols: Dict[str, Any] = {"time": np.array(values_as_text(iso_t, "iso"), dtype=str)}
    lines = [f"{t.size} time(s), scale={t.scale}"]
    if v["do_lst"]:
        lon = None if t.location is not None else "greenwich"
        model = None if v["model"] == "default" else v["model"]
        lst = t.sidereal_time(v["kind"], longitude=lon, model=model)
        cols["LST [hms]"] = np.array(lst.to_string(unit=u.hourangle, sep=":", precision=4,
                                                   pad=True)).reshape(-1)
        cols["LST [h]"] = np.atleast_1d(lst.hour)
        lines.append(f"{v['kind']} sidereal time at "
                     + ("the given longitude" if lon is None else "Greenwich (no location given)"))
    if v["do_ltt"]:
        sky = parse_skycoord(v["sky"], name="source position")
        observer = t.location if t.location is not None else GEOCENTER
        ltt = t.light_travel_time(sky, kind=v["ltt_kind"], location=observer,
                                  ephemeris=v["ephemeris"] or None)
        corrected = t.tdb + ltt
        corrected.precision = 6
        cols["LTT [s]"] = np.atleast_1d(ltt.to_value(u.s))
        cols["corrected (TDB)"] = np.array(values_as_text(corrected, "iso"), dtype=str)
        cols["corrected JD"] = np.atleast_1d(corrected.jd)
        lines.append(f"{v['ltt_kind']} light travel time, "
                     + ("observer at the given location" if t.location is not None
                        else "geocentric (no location given)"))
    table = Table(cols)
    shown = "\n".join(table[:MAX_LISTED].pformat(max_width=-1, max_lines=-1))
    if len(table) > MAX_LISTED:
        shown += f"\n... ({len(table)} rows in total)"
    return {"text": "\n".join(lines) + "\n\n" + shown, "table": table}


def leap_seconds_table() -> Tuple[Table, str]:
    leaps = iers.LeapSeconds.auto_open()
    table = Table([np.asarray(leaps["year"]), np.asarray(leaps["month"]),
                   np.asarray(leaps["tai_utc"])], names=["year", "month", "TAI-UTC [s]"])
    return table, f"{len(table)} entries; table expires {leaps.expires}."


def tai_minus_utc(t: Time) -> np.ndarray:
    """TAI-UTC in seconds for UTC times."""
    tai, utc = t.tai, t.utc
    return ((tai.jd1 - utc.jd1) + (tai.jd2 - utc.jd2)) * 86400.0


def earth_orientation(date_text: str) -> str:
    t = parse_time(date_text, scale="utc", name="date")
    table = iers.earth_orientation_table.get()
    dut1, status = table.ut1_utc(t, return_status=True)
    px, py = table.pm_xy(t)
    lines = [f"UTC:        {t.iso}  (JD {np.asarray(t.jd).tolist()})",
             f"TAI-UTC:    {np.round(tai_minus_utc(t), 6)} s",
             f"UT1-UTC:    {np.asarray(dut1.to_value(u.s))} s   [{_status(status)}]",
             f"Polar x, y: {np.asarray(px.to_value(u.arcsec))} , {np.asarray(py.to_value(u.arcsec))} arcsec"]
    return "\n".join(lines)


def _status(status: Any) -> str:
    codes = np.unique(np.atleast_1d(status))
    return ", ".join(IERS_STATUS.get(int(c), f"status {int(c)}") for c in codes)


def iers_range() -> str:
    table = iers.earth_orientation_table.get()
    mjd = np.asarray(table["MJD"].to_value(u.d))
    first, last = Time(mjd[0], format="mjd"), Time(mjd[-1], format="mjd")
    return (f"Table: {type(table).__name__}, {len(table)} rows\n"
            f"MJD range: {mjd[0]:.0f} .. {mjd[-1]:.0f}\n"
            f"Dates:     {first.iso[:10]} .. {last.iso[:10]}\n"
            f"Auto-download: {iers.conf.auto_download} (this tool never downloads IERS data)")


# --------------------------------------------------------------------------- #
# Panels
# --------------------------------------------------------------------------- #
class TimeConverterPanel(StoringPanel):
    default_store_name = "time"

    def __init__(self, ws: Workspace) -> None:
        super().__init__(ws)
        f = self.form
        add_time_inputs(f, "2000-01-01 12:00:00")
        add_location_inputs(f)
        f.add_combo("out_scale", "Output scale", ["same as input", *REPORT_SCALES],
                    "Time scale conversion (ut1 needs the bundled IERS table)")
        f.add_combo("out_format", "Output format", list(Time.FORMATS), current="iso")
        f.add_int("precision", "Precision", 3, 0, 9, "Digits of sub-second precision for strings")
        f.add_text("strftime", "strftime", "", "Optional pattern, e.g. %Y/%m/%d %H:%M:%S")
        self.add_store_controls()
        self.add_button("Convert", self.convert)
        self.out = self.add_output("Result")
        self.formats = self.add_table("All formats")
        self.scales = self.add_table("All scales")

    def convert(self) -> None:
        values = self.form.values()

        def show(res: Tuple[Dict[str, Any], List[str]]) -> None:
            data, notes = res
            self.out.show_text(with_notes(data["text"], notes))
            self.formats.set_table(data["formats"])
            self.scales.set_table(data["scales"])
            self._last = data["time"]

        self.run(lambda: capture(lambda: convert_times(values)), show, busy_text="Converting...")


class TimeArithmeticPanel(StoringPanel):
    default_store_name = "time_result"

    def __init__(self, ws: Workspace) -> None:
        super().__init__(ws)
        f = self.form
        add_time_inputs(f, "2024-03-10 06:00:00", "t1", "t1")
        f.add_text("t2", "t2", "2024-03-12 18:30:00", "Second time (same format/scale as t1)")
        f.add_text("delta", "delta", "1.5 d", "Duration, e.g. '36 h', '3600 s'; plain numbers are days")
        f.add_combo("op", "Operation", ["t1 - t2", "t1 + delta", "t1 - delta", "range t1 .. t2",
                                         "range t1 + k*delta"])
        f.add_int("n", "Points N", 5, 1, 100000, "Number of points for ranges")
        self.add_store_controls()
        self.add_button("Compute", self.compute)
        self.out = self.add_output("Result")
        self.table = self.add_table("Range")

    def compute(self) -> None:
        values = self.form.values()

        def show(res: Tuple[Dict[str, Any], List[str]]) -> None:
            data, notes = res
            self.out.show_text(with_notes(data["text"], notes))
            self.table.set_table(data["table"])
            self._last = data["result"]

        self.run(lambda: capture(lambda: time_arithmetic(values)), show, busy_text="Computing...")


class SiderealPanel(StoringPanel):
    default_store_name = "time_corrected"

    def __init__(self, ws: Workspace) -> None:
        super().__init__(ws)
        f = self.form
        add_time_inputs(f, "2024-03-10 22:00:00")
        add_location_inputs(f)
        f.add_check("do_lst", "Sidereal time", True)
        f.add_combo("kind", "Kind", ["mean", "apparent"], "Mean or apparent sidereal time")
        f.add_combo("model", "Model", SIDEREAL_MODELS, "Precession-nutation model ('default' = astropy's)")
        f.add_check("do_ltt", "Light travel time", False)
        f.add_text("sky", "Source", "12.5 -45.2",
                   "RA Dec (degrees or hms/dms) or a name resolvable by Sesame (needs network)")
        f.add_combo("ltt_kind", "Correction", ["barycentric", "heliocentric"])
        f.add_combo("ephemeris", "Ephemeris", ["builtin"], "Other ephemerides need a download",
                    editable=True)
        self.add_store_controls()
        self.add_button("Compute", self.compute)
        self.out = self.add_output("Result")
        self.table = self.add_table("Table")

    def compute(self) -> None:
        values = self.form.values()

        def show(res: Tuple[Dict[str, Any], List[str]]) -> None:
            data, notes = res
            self.out.show_text(with_notes(data["text"], notes))
            self.table.set_table(data["table"])
            self._last = data["table"]

        self.run(lambda: capture(lambda: sidereal_and_light_time(values)), show,
                 busy_text="Computing...")


class IersPanel(StoringPanel):
    def __init__(self, ws: Workspace) -> None:
        super().__init__(ws)
        self.form.add_text("date", "UTC date", "2020-01-01 00:00:00",
                           "Date for TAI-UTC, UT1-UTC and polar motion")
        self.add_button("Leap seconds", self.leap_seconds)
        self.add_button("Earth orientation at date", self.orientation)
        self.add_button("IERS table range", self.table_range)
        self.out = self.add_output("Result")
        self.table = self.add_table("Leap seconds")

    def _show_text(self, res: Tuple[str, List[str]]) -> None:
        self.out.show_text(with_notes(res[0], res[1]))
        self.tabs.setCurrentWidget(self.out)

    def leap_seconds(self) -> None:
        def show(res: Tuple[Tuple[Table, str], List[str]]) -> None:
            (table, info), notes = res
            self.table.set_table(table)
            self.out.show_text(with_notes(info, notes))
            self.tabs.setCurrentWidget(self.table)

        self.run(lambda: capture(leap_seconds_table), show)

    def orientation(self) -> None:
        text = self.form.value("date")
        self.run(lambda: capture(lambda: earth_orientation(text)), self._show_text)

    def table_range(self) -> None:
        self.run(lambda: capture(iers_range), self._show_text)


def _spec(key: str, title: str, cls: type, description: str) -> ModuleSpec:
    def make(ws: Workspace) -> QWidget:
        return cls(ws)
    return ModuleSpec(key, title, CATEGORY, make, description)


SPECS = [
    _spec("time_converter", "Time converter", TimeConverterPanel,
          "Convert between time formats and scales, strftime, epochs"),
    _spec("time_arithmetic", "Time arithmetic", TimeArithmeticPanel,
          "Differences, offsets and ranges with TimeDelta"),
    _spec("sidereal_light_time", "Sidereal & light time", SiderealPanel,
          "Sidereal time and barycentric / heliocentric corrections"),
    _spec("time_leap_iers", "Leap seconds & IERS", IersPanel,
          "TAI-UTC, UT1-UTC, polar motion and leap-second table"),
]
