"""Observer location, target visibility (alt/az, rise/set/transit) and velocity corrections."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import numpy as np
from astropy import units as u
from astropy.coordinates import AltAz, EarthLocation, SkyCoord, get_body
from astropy.table import Table
from astropy.time import Time
from PyQt5.QtWidgets import QWidget

from ..core.parsing import ParseError, parse_float, parse_quantity, parse_time
from ..core.registry import ModuleSpec
from ..core.widgets import ModulePanel
from ..core.workspace import Workspace
from .coordinates_common import (
    CATEGORY, CoordInput, LocationInput, altitude_function, find_crossings, find_culminations,
    grid_size, moon_illumination, offline_iers, parse_times, time_strings,
)

MAX_SAMPLES = 5000
MAX_CELLS = 1_000_000
MAX_TARGETS = 200


# --------------------------------------------------------------------------- #
# Observatory
# --------------------------------------------------------------------------- #
def location_table(loc: EarthLocation, ellipsoid: str = "WGS84") -> Table:
    """Key/value table describing an EarthLocation."""
    geo = loc.to_geodetic(ellipsoid)
    x, y, z = (c.to_value(u.m) for c in (loc.x, loc.y, loc.z))
    rows = [
        ("ellipsoid", ellipsoid),
        ("longitude [deg]", f"{geo.lon.wrap_at(180 * u.deg).deg:.8f}"),
        ("latitude [deg]", f"{geo.lat.deg:.8f}"),
        ("longitude (dms)", geo.lon.wrap_at(180 * u.deg).to_string(u.deg, sep=":", precision=3)),
        ("latitude (dms)", geo.lat.to_string(u.deg, sep=":", precision=3, alwayssign=True)),
        ("height [m]", f"{geo.height.to_value(u.m):.3f}"),
        ("geocentric x [m]", f"{x:.3f}"),
        ("geocentric y [m]", f"{y:.3f}"),
        ("geocentric z [m]", f"{z:.3f}"),
        ("distance from Earth centre [km]", f"{np.sqrt(x * x + y * y + z * z) / 1000.0:.4f}"),
    ]
    t = Table(rows=rows, names=("property", "value"))
    return t


class ObservatoryPanel(ModulePanel):
    def __init__(self, ws: Workspace) -> None:
        super().__init__(ws)
        self.loc = LocationInput(ws, default_mode="Site name")
        self.controls_layout.insertWidget(0, self.loc)
        self.form.add_text("name", "Workspace name", "site")
        self.table_view = self.add_table("Location")
        self.add_button("Show", self.show_location)
        self.add_button("Store EarthLocation in workspace", self.store)
        self.location: Optional[EarthLocation] = None

    def show_location(self) -> None:
        def go() -> None:
            loc = self.loc.get()
            ell = self.loc.ellipsoid.currentText()
            self.location = loc
            self.table_view.set_table(location_table(loc, ell))
            self.set_status("Ready")
        self.guard(go)

    def store(self) -> None:
        def go() -> None:
            self.location = self.loc.get()
            name = self.ws.put(self.form.value("name"), self.location)
            self.ws.log(f"Stored EarthLocation {name!r}")
        self.guard(go)


# --------------------------------------------------------------------------- #
# Visibility
# --------------------------------------------------------------------------- #
def refraction_dict(pressure_hpa: float, temperature_c: float, humidity_pct: float,
                    wavelength_um: float) -> Dict[str, Any]:
    if pressure_hpa < 0:
        raise ParseError("pressure must be >= 0.")
    if not 0 <= humidity_pct <= 100:
        raise ParseError("relative humidity must be between 0 and 100 %.")
    if wavelength_um <= 0:
        raise ParseError("wavelength must be positive.")
    return {"pressure": pressure_hpa * u.hPa, "temperature": temperature_c * u.deg_C,
            "relative_humidity": humidity_pct / 100.0, "obswl": wavelength_um * u.micron}


def compute_visibility(location: EarthLocation, targets: SkyCoord, labels: List[str], start: Time,
                       hours: float, step_minutes: float, refraction: Dict[str, Any],
                       horizon_deg: float = 0.0, offset_hours: float = 0.0) -> Dict[str, Any]:
    """Altitude/azimuth/airmass tracks plus rise/transit/set events for each target."""
    if hours <= 0 or step_minutes <= 0:
        raise ParseError("Duration and step must be positive.")
    n = grid_size(hours, step_minutes)
    targets = targets.reshape(-1) if targets.isscalar else targets
    if n > MAX_SAMPLES:
        raise ParseError(f"Too many time samples ({n}); increase the step or shorten the "
                         f"duration (max {MAX_SAMPLES}).")
    if len(targets) > MAX_TARGETS or len(targets) * n > MAX_CELLS:
        raise ParseError(f"Too many targets x samples (max {MAX_TARGETS} targets, "
                         f"{MAX_CELLS} values).")
    with offline_iers():
        times = start + np.linspace(0.0, hours, n) * u.hour
        frame = AltAz(obstime=times, location=location, **refraction)
        aa = targets[:, None].transform_to(frame)
        sun = get_body("sun", times, location).transform_to(frame)
        moon = get_body("moon", times, location).transform_to(frame)
        alt, az = aa.alt.to(u.deg), aa.az.to(u.deg)
        secz = np.where(alt.value > 0, aa.secz.value, np.nan)
        events = []
        for i in range(len(targets)):
            func = altitude_function(location, refraction, targets[i])
            rising, setting = find_crossings(func, start, hours, step_minutes, horizon_deg,
                                             values=alt[i].value)
            culm = find_culminations(func, start, hours, step_minutes, values=alt[i].value)
            best = max(culm, key=lambda c: c[1]) if culm else None
            above = alt[i].value > horizon_deg
            if rising or setting:
                status = ""
            else:
                status = "always above horizon" if above.all() else "always below horizon"
            events.append({
                "rise": ", ".join(time_strings(t, offset_hours)[0] for t in rising) or "--",
                "transit": time_strings(best[0], offset_hours)[0] if best else "--",
                "transit_alt_deg": best[1] if best else np.nan,
                "set": ", ".join(time_strings(t, offset_hours)[0] for t in setting) or "--",
                "status": status,
            })
        moon_info = moon_illumination(start)
        moon_sep = get_body("moon", start, location).separation(targets)
    shown = times + offset_hours * u.hour
    long = Table()
    long["target"] = np.repeat(labels, n)
    long["time"] = np.tile(time_strings(times, offset_hours), len(targets))
    long["alt_deg"] = alt.value.ravel()
    long["az_deg"] = az.value.ravel()
    long["airmass"] = secz.ravel()
    ev = Table()
    ev["target"] = labels
    for key in ("rise", "transit", "transit_alt_deg", "set", "status"):
        ev[key] = [e[key] for e in events]
    ev["moon_sep_deg"] = np.atleast_1d(moon_sep.deg)
    return {
        "times": times, "x": [d for d in shown.to_datetime()], "alt": alt.value,
        "az": az.value, "secz": secz, "sun_alt": sun.alt.deg, "moon_alt": moon.alt.deg,
        "labels": labels, "table": long, "events": ev, "moon": moon_info,
        "offset": offset_hours,
    }


def plot_visibility(alt_canvas: Any, air_canvas: Any, sky_canvas: Any, res: Dict[str, Any]) -> None:
    """Draw the three plots (GUI thread only)."""
    x, labels = res["x"], res["labels"]
    legend = len(labels) <= 12
    ax = alt_canvas.axes()
    for i, lab in enumerate(labels):
        ax.plot(x, res["alt"][i], label=lab)
    ax.plot(x, res["sun_alt"], "--", color="goldenrod", label="Sun")
    ax.plot(x, res["moon_alt"], ":", color="gray", label="Moon")
    ax.fill_between(x, -90, 90, where=res["sun_alt"] < -18, color="k", alpha=0.12,
                    label="astronomical night")
    ax.axhline(0, color="k", lw=0.6)
    ax.set_ylim(-20, 90)
    ax.set_ylabel("Altitude [deg]")
    ax.set_xlabel(f"Time (UTC{res['offset']:+g} h)")
    ax.grid(alpha=0.3)
    if legend:
        ax.legend(fontsize="small", ncol=2)
    alt_canvas.figure.autofmt_xdate()
    alt_canvas.canvas.draw()

    ax = air_canvas.axes()
    for i, lab in enumerate(labels):
        ax.plot(x, res["secz"][i], label=lab)
    ax.set_ylim(3.0, 1.0)
    ax.set_ylabel("Airmass (sec z)")
    ax.set_xlabel(f"Time (UTC{res['offset']:+g} h)")
    ax.grid(alpha=0.3)
    if legend:
        ax.legend(fontsize="small", ncol=2)
    air_canvas.figure.autofmt_xdate()
    air_canvas.canvas.draw()

    ax = sky_canvas.axes(projection="polar")
    ax.set_theta_zero_location("N")
    ax.set_theta_direction(1)  # looking up at the sky: east is to the left of north
    for i, lab in enumerate(labels):
        up = res["alt"][i] > 0
        theta = np.deg2rad(np.where(up, res["az"][i], np.nan))
        r = np.where(up, 90.0 - res["alt"][i], np.nan)
        ax.plot(theta, r, ".", ms=3, label=lab)
    ax.set_rlim(0, 90)
    ax.set_yticks([30, 60, 90])
    ax.set_yticklabels(["60°", "30°", "0°"])
    ax.set_title("Sky chart (N up, E left; radius = zenith distance)", fontsize="small")
    if legend:
        ax.legend(fontsize="small", loc="upper left", bbox_to_anchor=(1.05, 1.0))
        sky_canvas.figure.subplots_adjust(right=0.72)
    sky_canvas.canvas.draw()


class VisibilityPanel(ModulePanel):
    def __init__(self, ws: Workspace) -> None:
        super().__init__(ws)
        self.loc = LocationInput(ws, default_mode="Geodetic")
        self.targets = CoordInput(ws, "Targets", default_text="10.684 41.269\n279.2347 38.7837",
                                  motion=False)
        self.controls_layout.insertWidget(0, self.loc)
        self.controls_layout.insertWidget(1, self.targets)
        self.form.add_text("start", "Start (UTC)", "now", "ISO time or 'now'.")
        self.form.add_float("hours", "Duration [h]", 24.0, 0.01, 8760.0, 3)
        self.form.add_float("step", "Step [min]", 10.0, 0.1, 1440.0, 2)
        self.form.add_float("offset", "Display UTC offset [h]", 0.0, -14.0, 14.0, 2,
                            "Shifts displayed times only (e.g. 2 for CEST).")
        self.form.add_float("horizon", "Horizon altitude [deg]", 0.0, -90.0, 90.0, 3,
                            "Altitude used for rise/set events.")
        self.form.add_text("pressure", "Pressure [hPa]", "0", "0 disables refraction.")
        self.form.add_text("temperature", "Temperature [C]", "10")
        self.form.add_text("humidity", "Rel. humidity [%]", "0")
        self.form.add_text("wavelength", "Wavelength [um]", "0.55")
        self.form.add_text("name", "Workspace name", "visibility")
        self.table_view = self.add_table("Alt/Az track")
        self.events_view = self.add_table("Rise / transit / set")
        self.alt_plot = self.add_plot("Altitude")
        self.air_plot = self.add_plot("Airmass")
        self.sky_plot = self.add_plot("Sky chart")
        self.info = self.add_output("Moon")
        self.add_button("Compute", self.compute)
        self.add_button("Store tables in workspace", self.store)
        self.result: Optional[Dict[str, Any]] = None

    def compute(self) -> None:
        def prepare() -> None:
            v = self.form.values()
            loc = self.loc.get()
            targets = self.targets.get()
            labels = self.targets.labels(targets.size)
            start = parse_time(v["start"], name="start")
            refr = refraction_dict(parse_float(v["pressure"], "pressure"),
                                   parse_float(v["temperature"], "temperature"),
                                   parse_float(v["humidity"], "humidity"),
                                   parse_float(v["wavelength"], "wavelength"))
            self.run(compute_visibility, self._done, loc, targets, labels, start, v["hours"],
                     v["step"], refr, v["horizon"], v["offset"], busy_text="Computing tracks...")
        self.guard(prepare)

    def _done(self, res: Dict[str, Any]) -> None:
        self.result = res
        self.table_view.set_table(res["table"])
        self.events_view.set_table(res["events"])
        plot_visibility(self.alt_plot, self.air_plot, self.sky_plot, res)
        moon = res["moon"]
        self.info.show_text(
            f"Moon at start time (geocentric):\n"
            f"  illuminated fraction: {float(moon['illumination']):.3f}\n"
            f"  phase angle:          {float(moon['phase_angle'].value):.1f} deg\n"
            f"  elongation from Sun:  {float(moon['elongation'].value):.1f} deg\n"
            "Moon separation from each target is in the events table.")

    def store(self) -> None:
        def go() -> None:
            if self.result is None:
                raise ParseError("Compute first.")
            name = self.form.value("name")
            self.ws.put(name + "_track", self.result["table"])
            self.ws.put(name + "_events", self.result["events"])
        self.guard(go)


# --------------------------------------------------------------------------- #
# Velocity / light-travel-time corrections
# --------------------------------------------------------------------------- #
C_KMS = 299792.458


def velocity_corrections(location: EarthLocation, targets: SkyCoord, times: Time,
                         observed_rv: Optional[u.Quantity]) -> Table:
    """Barycentric/heliocentric RV corrections and light-travel times."""
    targets = targets.reshape(-1) if targets.isscalar else targets
    times = Time(np.atleast_1d(times)) if times.isscalar else times
    n_t, n_s = len(targets), len(times)
    if n_t != n_s and 1 not in (n_t, n_s):
        raise ParseError(f"{n_t} targets vs {n_s} times: use equal counts or a single one.")
    n = max(n_t, n_s)
    with offline_iers():
        tg = targets if n_t == n else targets[np.zeros(n, dtype=int)]
        tm = times if n_s == n else times[np.zeros(n, dtype=int)]
        out = Table()
        out["time_utc"] = time_strings(tm.utc, precision=3)
        out["jd_utc"] = tm.utc.jd
        out["rv_corr_bary_kms"] = tg.radial_velocity_correction("barycentric", obstime=tm,
                                                                 location=location).to_value(u.km / u.s)
        out["rv_corr_helio_kms"] = tg.radial_velocity_correction("heliocentric", obstime=tm,
                                                                  location=location).to_value(u.km / u.s)
        ltt_b = tm.light_travel_time(tg, "barycentric", location=location)
        ltt_h = tm.light_travel_time(tg, "heliocentric", location=location)
        out["ltt_bary_s"] = ltt_b.to_value(u.s)
        out["ltt_helio_s"] = ltt_h.to_value(u.s)
        out["bjd_tdb"] = (tm.tdb + ltt_b).jd
        out["hjd_utc"] = (tm.utc + ltt_h).jd
        if observed_rv is not None:
            rv = observed_rv.to_value(u.km / u.s)
            for kind in ("bary", "helio"):
                corr = out[f"rv_corr_{kind}_kms"]
                out[f"rv_{kind}_kms"] = rv + corr + rv * corr / C_KMS
    return out


class VelocityPanel(ModulePanel):
    def __init__(self, ws: Workspace) -> None:
        super().__init__(ws)
        self.loc = LocationInput(ws, default_mode="Geodetic")
        self.targets = CoordInput(ws, "Targets", default_text="10.684 41.269", motion=False)
        self.controls_layout.insertWidget(0, self.loc)
        self.controls_layout.insertWidget(1, self.targets)
        self.form.add_multiline("times", "Observation times (UTC)", "2024-01-01T00:00:00\n"
                                "2024-07-01T00:00:00", "One per line; 'now' allowed.")
        self.form.add_text("rv", "Observed RV", "", "Optional, e.g. '-300 km/s': adds corrected RVs.")
        self.form.add_text("name", "Workspace name", "velocity_corr")
        self.table_view = self.add_table("Corrections")
        self.add_button("Compute", self.compute)
        self.add_button("Store table in workspace", self.store)
        self.result: Optional[Table] = None

    def compute(self) -> None:
        def prepare() -> None:
            v = self.form.values()
            loc, targets = self.loc.get(), self.targets.get()
            times = parse_times(v["times"], "observation time")
            rv = parse_quantity(v["rv"], u.km / u.s, "observed RV") if v["rv"] else None
            self.run(velocity_corrections, self._done, loc, targets, times, rv,
                     busy_text="Computing corrections...")
        self.guard(prepare)

    def _done(self, table: Table) -> None:
        self.result = table
        self.table_view.set_table(table)

    def store(self) -> None:
        def go() -> None:
            if self.result is None:
                raise ParseError("Compute first.")
            self.ws.put(self.form.value("name"), self.result)
        self.guard(go)


def _observatory(ws: Workspace) -> QWidget:
    return ObservatoryPanel(ws)


def _visibility(ws: Workspace) -> QWidget:
    return VisibilityPanel(ws)


def _velocity(ws: Workspace) -> QWidget:
    return VelocityPanel(ws)


SPECS = [
    ModuleSpec("coord_observatory", "Observatory (EarthLocation)", CATEGORY, _observatory,
               "Observer location from site registry, geodetic or geocentric values"),
    ModuleSpec("coord_visibility", "Alt/Az & visibility", CATEGORY, _visibility,
               "Altitude, azimuth, airmass, rise/transit/set and sky chart"),
    ModuleSpec("coord_velocity", "Velocity corrections", CATEGORY, _velocity,
               "Barycentric/heliocentric RV corrections and BJD/HJD"),
]
