"""Solar-system bodies, ephemerides, barycentric vectors, Sun/Moon events and twilight."""
from __future__ import annotations

import contextlib
import importlib.util
from typing import Any, Dict, Iterator, List, Optional, Tuple

import numpy as np
from astropy import units as u
from astropy.coordinates import (
    AltAz, EarthLocation, GeocentricTrueEcliptic, SkyCoord, get_body, get_body_barycentric,
    get_body_barycentric_posvel, get_sun, solar_system_ephemeris,
)
from astropy.table import Table
from astropy.time import Time
from astropy.utils.data import conf as data_conf
from PyQt5.QtWidgets import QAbstractItemView, QGroupBox, QListWidget, QVBoxLayout, QWidget

from ..core.parsing import ParseError, parse_time
from ..core.registry import ModuleSpec
from ..core.widgets import ModulePanel
from ..core.workspace import Workspace
from .coordinates_common import (
    CATEGORY, CoordInput, LocationInput, altitude_function, dark_intervals, find_crossings,
    find_culminations, fmt_angle, grid_size, moon_illumination, offline_iers, parse_times, time_strings,
)

APPARENT_BODIES = ("sun", "moon", "mercury", "venus", "mars", "jupiter", "saturn", "uranus",
                   "neptune")
BARYCENTRIC_BODIES = ("sun", "mercury", "venus", "earth", "moon", "earth-moon-barycenter",
                      "mars", "jupiter", "saturn", "uranus", "neptune")
EPHEMERIDES = ("builtin", "jpl", "de430", "de432s", "de440", "de440s")
SUN_HORIZON = -0.833  # deg: standard refraction + solar semi-diameter
TWILIGHTS = (("Civil", -6.0), ("Nautical", -12.0), ("Astronomical", -18.0))
MAX_SAMPLES = 20000


# --------------------------------------------------------------------------- #
# Ephemeris handling
# --------------------------------------------------------------------------- #
@contextlib.contextmanager
def ephemeris_context(name: str) -> Iterator[None]:
    """Use ``solar_system_ephemeris`` ``name``; non-builtin ones need jplephem and a cached
    or downloadable kernel - failures become a :class:`ParseError`."""
    if name == "builtin":
        with solar_system_ephemeris.set("builtin"):
            yield
        return
    if importlib.util.find_spec("jplephem") is None:
        raise ParseError(f"The {name!r} ephemeris needs the 'jplephem' package "
                         "(pip install jplephem) and a kernel file; use 'builtin' for "
                         "an offline calculation.")
    try:
        with data_conf.set_temp("remote_timeout", 10.0):
            ctx = solar_system_ephemeris.set(name)
            get_body_barycentric("earth", Time("2024-01-01"))  # forces the kernel load
    except Exception as exc:  # noqa: BLE001 - download failure, unknown name, ...
        solar_system_ephemeris.set("builtin")
        raise ParseError(f"Ephemeris {name!r} is not available (kernel not cached and could "
                         f"not be downloaded): {exc}") from None
    with ctx:
        yield


def _body_coord(name: str, times: Time, location: Optional[EarthLocation]) -> SkyCoord:
    """Apparent geocentric (or topocentric when ``location`` is given) GCRS position."""
    if name == "sun" and location is None:
        return get_sun(times)
    return get_body(name, times, location)


# --------------------------------------------------------------------------- #
# Bodies table
# --------------------------------------------------------------------------- #
def body_tables(bodies: List[str], times: Time, location: Optional[EarthLocation],
                ephemeris: str) -> Tuple[Table, Table]:
    """Apparent positions and barycentric position/velocity of the requested bodies."""
    times = Time(np.atleast_1d(times)) if times.isscalar else times
    if not bodies:
        raise ParseError("Select at least one body.")
    if len(bodies) * len(times) > 100_000:
        raise ParseError("Too many body x time combinations (max 100000).")
    app_rows: List[Table] = []
    bary_rows: List[Table] = []
    with offline_iers(), ephemeris_context(ephemeris):
        sun_geo = get_body("sun", times)
        for name in bodies:
            if name in APPARENT_BODIES:
                sc = _body_coord(name, times, location)
                t = Table()
                t["time_utc"] = time_strings(times, precision=3)
                t["body"] = [name] * len(times)
                t["ra_deg"], t["dec_deg"] = sc.ra.deg, sc.dec.deg
                t["ra_hms"] = fmt_angle(sc.ra, "hmsdms", hours=True, precision=2)
                t["dec_dms"] = fmt_angle(sc.dec, "hmsdms", precision=1)
                t["distance_AU"] = sc.distance.to_value(u.AU)
                ecl = sc.transform_to(GeocentricTrueEcliptic(equinox=times))
                t["ecl_lon_deg"], t["ecl_lat_deg"] = ecl.lon.deg, ecl.lat.deg
                t["elongation_deg"] = sun_geo.separation(sc).deg
                if location is not None:
                    aa = sc.transform_to(AltAz(obstime=times, location=location))
                    t["alt_deg"], t["az_deg"] = aa.alt.deg, aa.az.deg
                app_rows.append(t)
            if name in BARYCENTRIC_BODIES:
                pos, vel = get_body_barycentric_posvel(name, times)
                b = Table()
                b["time_utc"] = time_strings(times, precision=3)
                b["body"] = [name] * len(times)
                for axis in ("x", "y", "z"):
                    b[f"{axis}_AU"] = getattr(pos, axis).to_value(u.AU)
                for axis in ("x", "y", "z"):
                    b[f"v{axis}_kms"] = getattr(vel, axis).to_value(u.km / u.s)
                bary_rows.append(b)
    from astropy.table import vstack
    apparent = vstack(app_rows) if app_rows else Table()
    barycentric = vstack(bary_rows) if bary_rows else Table()
    return apparent, barycentric


class SolarSystemPanel(ModulePanel):
    def __init__(self, ws: Workspace) -> None:
        super().__init__(ws)
        self.use_loc = LocationInput(ws, "Observer (optional, for topocentric + alt/az)",
                                     default_mode="Geodetic")
        self.controls_layout.insertWidget(0, self.use_loc)
        self.form.add_check("topo", "Use observer location", False,
                            "Topocentric positions plus altitude/azimuth.")
        self.form.add_multiline("times", "Times (UTC)", "now", "One per line; 'now' allowed.")
        self.form.add_combo("ephemeris", "Ephemeris", EPHEMERIDES,
                            tip="'builtin' works offline. jpl/de* need the jplephem package "
                                "and a cached or downloadable kernel.")
        self.bodies = QListWidget()
        self.bodies.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.bodies.setFixedHeight(130)
        self.bodies.addItems(list(BARYCENTRIC_BODIES))
        for i in range(self.bodies.count()):
            self.bodies.item(i).setSelected(True)
        self.bodies.setToolTip("Bodies to compute. 'earth' and the barycentre appear only in "
                               "the barycentric table.")
        box = QGroupBox("Bodies")
        QVBoxLayout(box).addWidget(self.bodies)
        self.controls_layout.insertWidget(1, box)
        self.form.add_text("name", "Workspace name", "bodies")
        self.apparent_view = self.add_table("Apparent positions")
        self.bary_view = self.add_table("Barycentric pos / vel")
        self.add_button("Compute", self.compute)
        self.add_button("Store tables in workspace", self.store)
        self.result: Optional[Tuple[Table, Table]] = None

    def selected_bodies(self) -> List[str]:
        return [i.text() for i in self.bodies.selectedItems()]

    def compute(self) -> None:
        def prepare() -> None:
            v = self.form.values()
            times = parse_times(v["times"])
            loc = self.use_loc.get() if v["topo"] else None
            self.run(body_tables, self._done, self.selected_bodies(), times, loc,
                     v["ephemeris"], busy_text="Computing ephemerides...")
        self.guard(prepare)

    def _done(self, res: Tuple[Table, Table]) -> None:
        self.result = res
        self.apparent_view.set_table(res[0] if len(res[0]) else None)
        self.bary_view.set_table(res[1] if len(res[1]) else None)

    def store(self) -> None:
        def go() -> None:
            if self.result is None:
                raise ParseError("Compute first.")
            name = self.form.value("name")
            if len(self.result[0]):
                self.ws.put(name + "_apparent", self.result[0])
            if len(self.result[1]):
                self.ws.put(name + "_barycentric", self.result[1])
        self.guard(go)


# --------------------------------------------------------------------------- #
# Sun, Moon, twilight
# --------------------------------------------------------------------------- #
def phase_name(illumination: float, waxing: bool) -> str:
    if illumination < 0.03:
        return "New Moon"
    if illumination > 0.97:
        return "Full Moon"
    if abs(illumination - 0.5) < 0.05:
        return "First Quarter" if waxing else "Last Quarter"
    side = "Waxing" if waxing else "Waning"
    return f"{side} {'Crescent' if illumination < 0.5 else 'Gibbous'}"


def is_waxing(t: Time) -> bool:
    """Moon east of the Sun in ecliptic longitude (0..180 deg) means waxing."""
    frame = GeocentricTrueEcliptic(equinox=t)
    sun = get_body("sun", t).transform_to(frame)
    moon = get_body("moon", t).transform_to(frame)
    return 0.0 < (moon.lon - sun.lon).wrap_at(360 * u.deg).deg < 180.0


def sun_moon_events(location: EarthLocation, start: Time, hours: float, step_minutes: float,
                    offset_hours: float = 0.0, targets: Optional[SkyCoord] = None,
                    labels: Optional[List[str]] = None) -> Dict[str, Any]:
    """Sun/Moon rise/set/transit, twilight times and dark intervals within the window."""
    if hours <= 0 or step_minutes <= 0:
        raise ParseError("Duration and step must be positive.")
    n = grid_size(hours, step_minutes)
    if n > MAX_SAMPLES:
        raise ParseError(f"Too many samples ({n}); increase the step (max {MAX_SAMPLES}).")
    rows: List[Tuple[float, str, str, float]] = []  # (jd, event, time string, altitude)

    def add(name: str, times: List[Time], alt: float = np.nan) -> None:
        for t in times:
            rows.append((t.jd, name, time_strings(t, offset_hours)[0], alt))

    with offline_iers():
        end = start + hours * u.hour
        sun_f = altitude_function(location, None, "sun")
        moon_f = altitude_function(location, None, "moon")
        grid = start + np.linspace(0.0, hours, n) * u.hour
        sun_alt, moon_alt = sun_f(grid).deg, moon_f(grid).deg
        rise, sett = find_crossings(sun_f, start, hours, step_minutes, SUN_HORIZON,
                                    values=sun_alt)
        add("Sunrise", rise)
        add("Sunset", sett)
        dark: List[Tuple[Time, Time]] = []
        for label, level in TWILIGHTS:
            rise_l, set_l = find_crossings(sun_f, start, hours, step_minutes, level,
                                           values=sun_alt)
            add(f"{label} dawn (Sun at {level:g} deg)", rise_l)
            add(f"{label} dusk (Sun at {level:g} deg)", set_l)
            if label == "Astronomical":
                dark = dark_intervals(set_l, rise_l, start, end, bool(sun_alt[0] < level))
        for t, alt in find_culminations(sun_f, start, hours, step_minutes, values=sun_alt):
            add("Solar noon", [t], alt)
        m_rise, m_set = find_crossings(moon_f, start, hours, step_minutes, SUN_HORIZON,
                                       values=moon_alt)
        add("Moonrise", m_rise)
        add("Moonset", m_set)
        for t, alt in find_culminations(moon_f, start, hours, step_minutes, values=moon_alt):
            add("Moon transit", [t], alt)
        moon = moon_illumination(start)
        waxing = is_waxing(start)
        sep = None
        if targets is not None:
            moon_sc = get_body("moon", start, location)
            sep = np.atleast_1d(moon_sc.separation(targets).deg)
    rows.sort(key=lambda r: r[0])
    events = Table({"event": [r[1] for r in rows], "time": [r[2] for r in rows],
                    "altitude_deg": [r[3] for r in rows]})
    darkness = Table({"start": [time_strings(a, offset_hours)[0] for a, _ in dark],
                      "end": [time_strings(b, offset_hours)[0] for _, b in dark],
                      "hours": [(b - a).to_value(u.hour) for a, b in dark]})
    sep_table = None
    if sep is not None:
        sep_table = Table()
        sep_table["target"] = labels or [f"#{i + 1}" for i in range(len(sep))]
        sep_table["moon_sep_deg"] = sep
    return {
        "events": events, "darkness": darkness, "moon_separation": sep_table,
        "x": list((grid + offset_hours * u.hour).to_datetime()), "sun_alt": sun_alt,
        "moon_alt": moon_alt, "offset": offset_hours,
        "illumination": float(moon["illumination"]),
        "phase_angle": float(moon["phase_angle"].value),
        "elongation": float(moon["elongation"].value),
        "phase": phase_name(float(moon["illumination"]), waxing),
    }


class SunMoonPanel(ModulePanel):
    def __init__(self, ws: Workspace) -> None:
        super().__init__(ws)
        self.loc = LocationInput(ws, default_mode="Geodetic")
        self.targets = CoordInput(ws, "Targets for Moon separation (optional)",
                                  default_text="", motion=False)
        self.controls_layout.insertWidget(0, self.loc)
        self.controls_layout.insertWidget(1, self.targets)
        self.form.add_text("start", "Start (UTC)", "now", "Start of the search window.")
        self.form.add_float("hours", "Window [h]", 24.0, 0.5, 720.0, 2)
        self.form.add_float("step", "Step [min]", 5.0, 0.5, 120.0, 2,
                            "Sampling step; events are then refined to sub-second accuracy.")
        self.form.add_float("offset", "Display UTC offset [h]", 0.0, -14.0, 14.0, 2)
        self.form.add_text("name", "Workspace name", "sunmoon")
        self.events_view = self.add_table("Events")
        self.dark_view = self.add_table("Astronomical night")
        self.sep_view = self.add_table("Moon separation")
        self.plot = self.add_plot("Sun and Moon altitude")
        self.info = self.add_output("Moon phase")
        self.add_button("Compute", self.compute)
        self.add_button("Store tables in workspace", self.store)
        self.result: Optional[Dict[str, Any]] = None

    def compute(self) -> None:
        def prepare() -> None:
            v = self.form.values()
            loc = self.loc.get()
            start = parse_time(v["start"], name="start")
            targets = labels = None
            if self.targets.source.currentText() != "Typed text" or self.targets.lines():
                targets = self.targets.get()
                targets = targets.reshape(-1) if targets.isscalar else targets
                labels = self.targets.labels(targets.size)
            self.run(sun_moon_events, self._done, loc, start, v["hours"], v["step"], v["offset"],
                     targets, labels, busy_text="Searching events...")
        self.guard(prepare)

    def _done(self, res: Dict[str, Any]) -> None:
        self.result = res
        self.events_view.set_table(res["events"])
        self.dark_view.set_table(res["darkness"])
        self.sep_view.set_table(res["moon_separation"])
        ax = self.plot.axes()
        x = res["x"]
        ax.plot(x, res["sun_alt"], color="goldenrod", label="Sun")
        ax.plot(x, res["moon_alt"], color="gray", label="Moon")
        for _label, level in ((None, SUN_HORIZON),) + tuple(TWILIGHTS):
            ax.axhline(level, color="k", lw=0.5, ls=":")
        ax.axhline(0, color="k", lw=0.6)
        ax.set_ylabel("Altitude [deg]")
        ax.set_xlabel(f"Time (UTC{res['offset']:+g} h)")
        ax.grid(alpha=0.3)
        ax.legend()
        self.plot.figure.autofmt_xdate()
        self.plot.canvas.draw()
        self.info.show_text(
            f"Moon at window start: {res['phase']}\n"
            f"  illuminated fraction: {res['illumination']:.3f}\n"
            f"  phase angle:          {res['phase_angle']:.1f} deg\n"
            f"  elongation from Sun:  {res['elongation']:.1f} deg\n\n"
            f"Sun rise/set uses a horizon of {SUN_HORIZON} deg (standard refraction and "
            "semi-diameter); Moon events use the same topocentric horizon.")

    def store(self) -> None:
        def go() -> None:
            if self.result is None:
                raise ParseError("Compute first.")
            name = self.form.value("name")
            self.ws.put(name + "_events", self.result["events"])
            self.ws.put(name + "_night", self.result["darkness"])
        self.guard(go)


def _solar(ws: Workspace) -> QWidget:
    return SolarSystemPanel(ws)


def _sunmoon(ws: Workspace) -> QWidget:
    return SunMoonPanel(ws)


SPECS = [
    ModuleSpec("coord_solar", "Solar system bodies", CATEGORY, _solar,
               "get_body/get_sun positions, ephemeris choice, barycentric position & velocity"),
    ModuleSpec("coord_sunmoon", "Sun, Moon & twilight", CATEGORY, _sunmoon,
               "Rise/set, twilight windows, astronomical night, Moon phase and separation"),
]
