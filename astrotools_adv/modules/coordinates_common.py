"""Shared helpers and input widgets for the Coordinates pages.

Not a page itself (``SPECS`` is empty); imported by the ``coordinates_*`` modules.
"""
from __future__ import annotations

import contextlib
import re
import warnings
from typing import Any, Callable, Dict, Iterator, List, Optional, Sequence, Tuple

import numpy as np
from astropy import units as u
from astropy.coordinates import (
    AltAz, Angle, BarycentricMeanEcliptic, BarycentricTrueEcliptic, CIRS, Distance,
    EarthLocation, FK4, FK4NoETerms, FK5, GCRS, Galactic, GalacticLSR, Galactocentric,
    GeocentricMeanEcliptic, GeocentricTrueEcliptic, HADec, HCRS, HeliocentricEclipticIAU76,
    HeliocentricMeanEcliptic, HeliocentricTrueEcliptic, ICRS, ITRS, LSR, LSRD, LSRK,
    Latitude, Longitude, PrecessedGeocentric, SkyCoord, SphericalCosLatDifferential,
    SphericalRepresentation, Supergalactic, TETE, UnitSphericalCosLatDifferential,
    UnitSphericalRepresentation, get_body,
)
from astropy.coordinates.representation import (
    CartesianDifferential, CylindricalRepresentation, PhysicsSphericalRepresentation,
)
from astropy.table import QTable, Table
from astropy.time import Time
from astropy.utils import iers
from PyQt5.QtWidgets import (
    QComboBox, QFormLayout, QGroupBox, QLineEdit, QPlainTextEdit, QVBoxLayout, QWidget,
)

from ..core.parsing import (
    ParseError, parse_angle, parse_float, parse_quantity, parse_skycoord, parse_time,
    parse_unit,
)
from ..core.widgets import monospace
from ..core.workspace import Workspace

CATEGORY = "Coordinates"
SPECS: list = []  # helper module: contributes no pages


# --------------------------------------------------------------------------- #
# Offline-safe astropy context
# --------------------------------------------------------------------------- #
@contextlib.contextmanager
def offline_iers() -> Iterator[None]:
    """Never touch the network for IERS data and silence 'dubious year' noise.

    Restores the previous configuration on exit, also after an exception.
    """
    import erfa
    from astropy.utils.exceptions import AstropyWarning

    with iers.conf.set_temp("auto_download", False), \
            iers.conf.set_temp("iers_degraded_accuracy", "ignore"), \
            warnings.catch_warnings():
        warnings.simplefilter("ignore", erfa.ErfaWarning)
        warnings.simplefilter("ignore", AstropyWarning)  # e.g. "IERS data not valid for date"
        yield


# --------------------------------------------------------------------------- #
# Frames
# --------------------------------------------------------------------------- #
FRAME_CLASSES: Dict[str, type] = {
    "ICRS": ICRS, "FK5": FK5, "FK4": FK4, "FK4NoETerms": FK4NoETerms,
    "Galactic": Galactic, "GalacticLSR": GalacticLSR, "Supergalactic": Supergalactic,
    "GeocentricMeanEcliptic": GeocentricMeanEcliptic,
    "GeocentricTrueEcliptic": GeocentricTrueEcliptic,
    "BarycentricMeanEcliptic": BarycentricMeanEcliptic,
    "BarycentricTrueEcliptic": BarycentricTrueEcliptic,
    "HeliocentricMeanEcliptic": HeliocentricMeanEcliptic,
    "HeliocentricTrueEcliptic": HeliocentricTrueEcliptic,
    "HeliocentricEclipticIAU76": HeliocentricEclipticIAU76,
    "GCRS": GCRS, "CIRS": CIRS, "TETE": TETE, "ITRS": ITRS,
    "PrecessedGeocentric": PrecessedGeocentric, "HCRS": HCRS,
    "AltAz": AltAz, "HADec": HADec, "Galactocentric": Galactocentric,
    "LSR": LSR, "LSRK": LSRK, "LSRD": LSRD,
}
SKYOFFSET = "SkyOffset"
FRAME_NAMES: List[str] = list(FRAME_CLASSES) + [SKYOFFSET]
REFRACTION_KEYS = ("pressure", "temperature", "relative_humidity", "obswl")
TOPOCENTRIC = ("AltAz", "HADec")  # frames that need an observer location


def frame_attribute_names(name: str) -> Tuple[str, ...]:
    """Frame attribute names of ``name`` (empty for SkyOffset)."""
    cls = FRAME_CLASSES.get(name)
    return tuple(cls.frame_attributes) if cls is not None else ()


def build_frame(name: str, *, equinox: Optional[Time] = None, obstime: Optional[Time] = None,
                location: Optional[EarthLocation] = None,
                refraction: Optional[Dict[str, Any]] = None,
                galcen: Optional[Dict[str, Any]] = None,
                origin: Optional[SkyCoord] = None):
    """Build a frame instance, passing only the attributes the class understands."""
    if name == SKYOFFSET:
        if origin is None:
            raise ParseError("SkyOffset frame needs an origin coordinate.")
        return origin.reshape(-1)[0].skyoffset_frame()
    cls = FRAME_CLASSES.get(name)
    if cls is None:
        raise ParseError(f"Unknown frame {name!r}.")
    attrs = cls.frame_attributes
    kw: Dict[str, Any] = {}
    for key, val in (("equinox", equinox), ("obstime", obstime), ("location", location)):
        if val is not None and key in attrs:
            kw[key] = val
    for key, val in (refraction or {}).items():
        if val is not None and key in attrs:
            kw[key] = val
    if cls is Galactocentric:
        kw.update({k: v for k, v in (galcen or {}).items() if v is not None})
    if name in ("AltAz", "HADec"):
        if location is None:
            raise ParseError(f"{name} needs an observer location.")
        if obstime is None:
            raise ParseError(f"{name} needs an observation time (obstime).")
    return cls(**kw)


def _vector(text: str, default_unit: Any, name: str) -> u.Quantity:
    """'12.9 245.6 7.78 km/s' / '12.9, 245.6, 7.78' -> 3-vector Quantity."""
    nums = re.findall(r"[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?", text)
    if len(nums) != 3:
        raise ParseError(f"{name}: expected 3 numbers, got {text!r}.")
    unit_txt = text[text.rfind(nums[-1]) + len(nums[-1]):].strip()
    unit = parse_unit(unit_txt, name) if unit_txt else u.Unit(default_unit)
    return np.array([float(n) for n in nums]) * unit


def set_row_visible(form: QFormLayout, field: QWidget, visible: bool) -> None:
    """Show/hide a form row (field and its label); QFormLayout.setRowVisible is Qt6 only."""
    field.setVisible(visible)
    label = form.labelForField(field)
    if label is not None:
        label.setVisible(visible)


def _blank(text: str) -> bool:
    return not text.strip() or text.strip().lower() in ("default", "auto")


# --------------------------------------------------------------------------- #
# Observer location
# --------------------------------------------------------------------------- #
_FALLBACK_SITES = {
    "greenwich": (0.0, 51.4769, 46.0), "roque de los muchachos": (-17.892, 28.7606, 2396.0),
    "paranal": (-70.4042, -24.6253, 2635.0), "mauna kea": (-155.4681, 19.8207, 4205.0),
}
_site_cache: Optional[List[str]] = None


def site_names() -> List[str]:
    """Known observatory names (astropy's registry; small built-in list as fallback)."""
    global _site_cache
    if _site_cache is None:
        try:
            _site_cache = sorted(EarthLocation.get_site_names())
        except Exception:  # noqa: BLE001 - registry unavailable offline
            _site_cache = sorted(_FALLBACK_SITES)
    return _site_cache


def site_location(name: str) -> EarthLocation:
    """``EarthLocation.of_site`` with a friendly error and an offline fallback."""
    name = name.strip()
    if not name:
        raise ParseError("Site name is empty.")
    try:
        return EarthLocation.of_site(name)
    except Exception as exc:  # noqa: BLE001
        fb = _FALLBACK_SITES.get(name.lower())
        if fb is not None:
            return EarthLocation.from_geodetic(fb[0] * u.deg, fb[1] * u.deg, fb[2] * u.m)
        raise ParseError(f"Unknown site {name!r}: {exc}") from None


GEODETIC_ELLIPSOIDS = ("WGS84", "GRS80", "WGS72")


class LocationInput(QGroupBox):
    """Observer location: registry site, geodetic, geocentric or workspace object."""

    MODES = ("Site name", "Geodetic", "Geocentric", "Workspace")

    def __init__(self, ws: Workspace, title: str = "Observer location",
                 default_mode: str = "Geodetic", lon: str = "0", lat: str = "51.4769",
                 height: str = "46 m", parent: Optional[QWidget] = None) -> None:
        super().__init__(title, parent)
        self.ws = ws
        self.mode = QComboBox()
        self.mode.addItems(self.MODES)
        self.site = QComboBox()
        self.site.setEditable(True)
        self.site.addItems(site_names())
        self.site.setEditText("")
        self.lon = QLineEdit(lon)
        self.lat = QLineEdit(lat)
        self.height = QLineEdit(height)
        self.ellipsoid = QComboBox()
        self.ellipsoid.addItems(GEODETIC_ELLIPSOIDS)
        self.xyz = QLineEdit("3980608.9 -102.5 4966861.3 m")
        self.stored = QComboBox()
        self.lon.setToolTip("Geodetic longitude in degrees, east positive (e.g. -4.7 or "
                            "-4d42m).")
        self.lat.setToolTip("Geodetic latitude, degrees or d:m:s.")
        self.height.setToolTip("Height above the ellipsoid, e.g. '46 m' (default unit: m).")
        self.xyz.setToolTip("Geocentric x y z with a common unit, e.g. '3980608.9 -102.5 "
                            "4966861.3 m'.")
        self.site.setToolTip("Observatory from astropy's site registry, e.g. 'greenwich'.")
        self._form = QFormLayout(self)
        self._rows: Dict[str, List[QWidget]] = {}
        self._form.addRow("Mode", self.mode)
        for key, label, widget in (
                ("Site name", "Site", self.site), ("Geodetic", "Longitude [deg]", self.lon),
                ("Geodetic", "Latitude [deg]", self.lat), ("Geodetic", "Height", self.height),
                ("Geodetic", "Ellipsoid", self.ellipsoid),
                ("Geocentric", "x y z", self.xyz), ("Workspace", "Object", self.stored)):
            self._form.addRow(label, widget)
            self._rows.setdefault(key, []).append(widget)
        ws.changed.connect(self.refresh)
        self.mode.currentTextChanged.connect(self._update_rows)
        self.refresh()
        self.set_mode(default_mode)

    def set_mode(self, mode: str) -> None:
        self.mode.setCurrentText(mode)
        self._update_rows()

    def _update_rows(self) -> None:
        current = self.mode.currentText()
        for key, widgets in self._rows.items():
            for w in widgets:
                set_row_visible(self._form, w, key == current)

    def refresh(self) -> None:
        keep = self.stored.currentText()
        self.stored.clear()
        self.stored.addItems(self.ws.names(EarthLocation))
        if self.stored.findText(keep) >= 0:
            self.stored.setCurrentText(keep)

    def get(self) -> EarthLocation:
        mode = self.mode.currentText()
        try:
            if mode == "Site name":
                return site_location(self.site.currentText())
            if mode == "Geodetic":
                lon = parse_angle(self.lon.text(), u.deg, "longitude")
                lat = parse_angle(self.lat.text(), u.deg, "latitude")
                if abs(lat.deg) > 90:
                    raise ParseError("latitude must be within -90..90 degrees.")
                h = parse_quantity(self.height.text() or "0 m", u.m, "height")
                return EarthLocation.from_geodetic(
                    lon, lat, h, ellipsoid=self.ellipsoid.currentText())
            if mode == "Geocentric":
                xyz = _vector(self.xyz.text(), u.m, "geocentric xyz")
                return EarthLocation.from_geocentric(*xyz)
            name = self.stored.currentText()
            if not name:
                raise ParseError("No EarthLocation in the workspace.")
            obj = self.ws.get(name)
            if not isinstance(obj, EarthLocation):
                raise ParseError(f"{name!r} is not an EarthLocation.")
            return obj
        except ParseError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise ParseError(f"Invalid location: {exc}") from None


# --------------------------------------------------------------------------- #
# Frame input widget
# --------------------------------------------------------------------------- #
class FrameInput(QGroupBox):
    """Frame selector with the attribute fields relevant to the chosen frame."""

    def __init__(self, ws: Workspace, title: str = "Frame", default: str = "ICRS",
                 frames: Optional[Sequence[str]] = None, parent: Optional[QWidget] = None) -> None:
        super().__init__(title, parent)
        self.ws = ws
        self.frame = QComboBox()
        self.frame.addItems(list(frames) if frames else FRAME_NAMES)
        self.frame.setCurrentText(default)
        self.equinox = QLineEdit()
        self.equinox.setPlaceholderText("default (e.g. J2000, B1950, 2020-01-01)")
        self.obstime = QLineEdit()
        self.obstime.setPlaceholderText("default (ISO, 'now', J2015.5)")
        self.location = LocationInput(ws, "Observer (for AltAz, HADec, ITRS, CIRS, TETE)")
        self.pressure = QLineEdit("0")
        self.temperature = QLineEdit("10")
        self.humidity = QLineEdit("0")
        self.wavelength = QLineEdit("0.55")
        self.galcen_distance = QLineEdit()
        self.galcen_v_sun = QLineEdit()
        self.z_sun = QLineEdit()
        self.roll = QLineEdit()
        self.galcen_coord = QLineEdit()
        self.origin = QLineEdit("0 0")
        tips = {
            self.frame: "Target/input reference frame.",
            self.equinox: "Equinox of the frame (FK4/FK5/ecliptic/PrecessedGeocentric).",
            self.obstime: "Observation time (needed by AltAz/HADec; optional for GCRS, CIRS, "
                          "ITRS, HCRS, ...). Also epoch of proper motions.",
            self.pressure: "Atmospheric pressure in hPa. 0 disables refraction.",
            self.temperature: "Air temperature in deg C.",
            self.humidity: "Relative humidity in percent (0-100).",
            self.wavelength: "Observing wavelength in micron (refraction).",
            self.galcen_distance: "Sun-Galactic centre distance, e.g. '8.122 kpc'. Blank = default.",
            self.galcen_v_sun: "Sun velocity, 'vx vy vz km/s', e.g. '12.9 245.6 7.78'. Blank = default.",
            self.z_sun: "Sun height above the Galactic mid-plane, e.g. '20.8 pc'. Blank = default.",
            self.roll: "Galactic roll angle, e.g. '0 deg'. Blank = default.",
            self.galcen_coord: "ICRS position of the Galactic centre, 'ra dec' (deg). Blank = default.",
            self.origin: "Origin of the offset frame ('ra dec' ICRS, degrees or sexagesimal).",
        }
        for w, t in tips.items():
            w.setToolTip(t)
        self._form = QFormLayout()
        self._rows: Dict[str, List[QWidget]] = {}
        self._form.addRow("Frame", self.frame)
        for key, label, widget in (
                ("equinox", "Equinox", self.equinox), ("obstime", "Obstime", self.obstime),
                ("location", "", self.location),
                ("refraction", "Pressure [hPa]", self.pressure),
                ("refraction", "Temperature [C]", self.temperature),
                ("refraction", "Rel. humidity [%]", self.humidity),
                ("refraction", "Wavelength [um]", self.wavelength),
                ("galcen", "Galcen distance", self.galcen_distance),
                ("galcen", "Sun velocity", self.galcen_v_sun),
                ("galcen", "z_sun", self.z_sun), ("galcen", "Roll", self.roll),
                ("galcen", "Galcen coord", self.galcen_coord),
                ("origin", "Origin", self.origin)):
            if label:
                self._form.addRow(label, widget)
            else:
                self._form.addRow(widget)
            self._rows.setdefault(key, []).append(widget)
        outer = QVBoxLayout(self)
        outer.addLayout(self._form)
        self.frame.currentTextChanged.connect(self._update_rows)
        self._update_rows()

    def name(self) -> str:
        return self.frame.currentText()

    def _update_rows(self) -> None:
        name = self.name()
        attrs = frame_attribute_names(name)
        show = {
            "equinox": "equinox" in attrs, "obstime": "obstime" in attrs,
            "location": name in TOPOCENTRIC, "refraction": "pressure" in attrs,
            "galcen": name == "Galactocentric", "origin": name == SKYOFFSET,
        }
        for key, widgets in self._rows.items():
            for w in widgets:
                set_row_visible(self._form, w, show[key])

    def obstime_value(self) -> Optional[Time]:
        return None if _blank(self.obstime.text()) else parse_time(self.obstime.text(),
                                                                    name="obstime")

    def build(self) -> Any:
        """Frame instance for the current selection (raises ParseError)."""
        name = self.name()
        attrs = frame_attribute_names(name)
        equinox = None
        if "equinox" in attrs and not _blank(self.equinox.text()):
            text = self.equinox.text().strip()
            equinox = parse_time(text, name="equinox")
        obstime = self.obstime_value() if "obstime" in attrs else None
        location = self.location.get() if name in TOPOCENTRIC else None
        refraction = None
        if "pressure" in attrs:
            p = parse_float(self.pressure.text() or "0", "pressure")
            if p < 0:
                raise ParseError("pressure must be >= 0.")
            refraction = {
                "pressure": p * u.hPa,
                "temperature": parse_float(self.temperature.text() or "0", "temperature") * u.deg_C,
                "relative_humidity": parse_float(self.humidity.text() or "0", "humidity") / 100.0,
                "obswl": parse_float(self.wavelength.text() or "0.55", "wavelength") * u.micron,
            }
        galcen = origin = None
        if name == "Galactocentric":
            galcen = self._galcen()
        if name == SKYOFFSET:
            origin = parse_skycoord(self.origin.text(), name="origin")
        return build_frame(name, equinox=equinox, obstime=obstime, location=location,
                           refraction=refraction, galcen=galcen, origin=origin)

    def _galcen(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        if not _blank(self.galcen_distance.text()):
            out["galcen_distance"] = parse_quantity(self.galcen_distance.text(), u.kpc,
                                                    "galcen_distance")
        if not _blank(self.galcen_v_sun.text()):
            v = _vector(self.galcen_v_sun.text(), u.km / u.s, "Sun velocity")
            out["galcen_v_sun"] = CartesianDifferential(v)
        if not _blank(self.z_sun.text()):
            out["z_sun"] = parse_quantity(self.z_sun.text(), u.pc, "z_sun")
        if not _blank(self.roll.text()):
            out["roll"] = parse_angle(self.roll.text(), u.deg, "roll")
        if not _blank(self.galcen_coord.text()):
            out["galcen_coord"] = parse_skycoord(self.galcen_coord.text(), name="galcen_coord")
        return out


# --------------------------------------------------------------------------- #
# Coordinate input widget
# --------------------------------------------------------------------------- #
TEXT, WS_SKYCOORD, WS_TABLE = "Typed text", "Workspace SkyCoord", "Workspace table"
LON_NAMES = ("ra", "raj2000", "_raj2000", "ra_icrs", "lon", "glon", "l", "elon", "ra_deg")
LAT_NAMES = ("dec", "dej2000", "_dej2000", "de", "dec_icrs", "lat", "glat", "b", "elat",
             "dec_deg")
NAME_COLS = ("name", "id", "target", "object", "main_id", "source", "source_id")
NONE_COL = "(none)"


def _guess(columns: Sequence[str], candidates: Sequence[str]) -> Optional[str]:
    lower = {c.lower(): c for c in columns}
    for cand in candidates:
        if cand in lower:
            return lower[cand]
    return None


def column_quantity(table: Table, name: str, default_unit: Any, *, angle: bool = False
                    ) -> u.Quantity:
    """A table column as Quantity/Angle; masked -> NaN; sexagesimal strings parsed."""
    if name not in table.colnames:
        raise ParseError(f"Column {name!r} not found.")
    col = table[name]
    if isinstance(col, u.Quantity):
        return col
    data = np.ma.asarray(col)
    unit = getattr(col, "unit", None) or default_unit
    if data.dtype.kind in "USO":
        strings = [str(x).strip() for x in np.ma.filled(data, "")]
        try:
            return Angle(strings, unit=unit) if angle else np.array(
                [float(s) for s in strings]) * u.Unit(unit)
        except Exception as exc:  # noqa: BLE001
            raise ParseError(f"Column {name!r} cannot be converted: {exc}") from None
    try:
        arr = data.astype(float).filled(np.nan)
    except (TypeError, ValueError) as exc:
        raise ParseError(f"Column {name!r} is not numeric: {exc}") from None
    return (Angle(arr, unit=unit) if angle else arr * u.Unit(unit))


def _broadcast(q: u.Quantity, n: int, name: str) -> u.Quantity:
    q = np.atleast_1d(q)
    if q.shape == (n,):
        return q
    if q.size == 1:
        return np.broadcast_to(q.value, (n,)).copy() * q.unit
    raise ParseError(f"{name}: expected 1 or {n} values, got {q.size}.")


def _split_numeric(line: str) -> List[str]:
    return line.replace(",", " ").replace(";", " ").split()


class CoordInput(QGroupBox):
    """Sky-coordinate source: typed lines, a workspace SkyCoord or table columns."""

    def __init__(self, ws: Workspace, title: str = "Coordinates", default_text: str = "",
                 default_source: str = TEXT, motion: bool = True,
                 frames: Optional[Sequence[str]] = None, parent: Optional[QWidget] = None) -> None:
        super().__init__(title, parent)
        self.ws = ws
        self.source = QComboBox()
        self.source.addItems([TEXT, WS_SKYCOORD, WS_TABLE])
        self.text = QPlainTextEdit(default_text)
        self.text.setFont(monospace())
        self.text.setFixedHeight(80)
        self.text.setToolTip("One coordinate per line: 'lon lat' in degrees, sexagesimal "
                             "('10:41:00 +41:16:00', '00h42m44s +41d16m09s') or with a unit "
                             "selected below. '#' starts a comment line.")
        self.lon_unit = QComboBox()
        self.lon_unit.addItems(["auto", "deg", "hourangle", "rad"])
        self.lat_unit = QComboBox()
        self.lat_unit.addItems(["auto", "deg", "rad"])
        self.lon_unit.setToolTip("auto: plain numbers are degrees; values with h/m/s or ':' "
                                 "are hours. Table columns use their own unit first.")
        self.sc_combo = QComboBox()
        self.tbl_combo = QComboBox()
        self.cols: Dict[str, QComboBox] = {k: QComboBox() for k in (
            "lon", "lat", "distance", "pm_lon", "pm_lat", "rv")}
        self.distance = QLineEdit()
        self.parallax = QLineEdit()
        self.pm_lon = QLineEdit()
        self.pm_lat = QLineEdit()
        self.rv = QLineEdit()
        for w, t in ((self.distance, "Distance for all rows, e.g. '100 pc' (default unit pc)."),
                     (self.parallax, "Parallax (mas) -> distance, used when distance is blank."),
                     (self.pm_lon, "Proper motion in lon*cos(lat) (default mas/yr)."),
                     (self.pm_lat, "Proper motion in lat (default mas/yr)."),
                     (self.rv, "Radial velocity (default km/s); needs a distance.")):
            w.setToolTip(t)
        self.frame = FrameInput(ws, "Coordinate frame", frames=frames)
        self._form = QFormLayout()
        self._rows: Dict[str, List[QWidget]] = {}
        self._form.addRow("Source", self.source)

        def row(key: str, label: str, widget: QWidget) -> None:
            self._form.addRow(label, widget)
            self._rows.setdefault(key, []).append(widget)

        row("text", "Lines", self.text)
        row("sc", "SkyCoord", self.sc_combo)
        row("table", "Table", self.tbl_combo)
        for k, label in (("lon", "Lon / RA column"), ("lat", "Lat / Dec column")):
            row("table", label, self.cols[k])
        row("units", "Lon unit", self.lon_unit)
        row("units", "Lat unit", self.lat_unit)
        if motion:
            for k, label in (("distance", "Distance column"), ("pm_lon", "PM lon column"),
                             ("pm_lat", "PM lat column"), ("rv", "RV column")):
                row("table", label, self.cols[k])
            row("text", "Distance", self.distance)
            row("text", "Parallax", self.parallax)
            row("text", "PM lon*cos(lat)", self.pm_lon)
            row("text", "PM lat", self.pm_lat)
            row("text", "Radial velocity", self.rv)
        outer = QVBoxLayout(self)
        outer.addLayout(self._form)
        outer.addWidget(self.frame)
        self.source.setCurrentText(default_source)
        self.source.currentTextChanged.connect(self._update_rows)
        self.tbl_combo.currentTextChanged.connect(self._fill_columns)
        ws.changed.connect(self.refresh)
        self.refresh()
        self._update_rows()

    # ---- UI state --------------------------------------------------------- #
    def _update_rows(self) -> None:
        src = self.source.currentText()
        visible = {"text": src == TEXT, "sc": src == WS_SKYCOORD, "table": src == WS_TABLE,
                   "units": src != WS_SKYCOORD}
        for key, widgets in self._rows.items():
            for w in widgets:
                set_row_visible(self._form, w, visible[key])
        self.frame.setVisible(src != WS_SKYCOORD)

    def refresh(self) -> None:
        for combo, kind in ((self.sc_combo, SkyCoord), (self.tbl_combo, Table)):
            keep = combo.currentText()
            combo.blockSignals(True)
            combo.clear()
            combo.addItems(self.ws.names(kind))
            if combo.findText(keep) >= 0:
                combo.setCurrentText(keep)
            combo.blockSignals(False)
        self._fill_columns()

    def _fill_columns(self) -> None:
        cols = self._table_columns()
        for key, combo in self.cols.items():
            keep = combo.currentText()
            combo.clear()
            if key not in ("lon", "lat"):
                combo.addItem(NONE_COL)
            combo.addItems(cols)
            if combo.findText(keep) >= 0:
                combo.setCurrentText(keep)
            elif key == "lon" and _guess(cols, LON_NAMES):
                combo.setCurrentText(_guess(cols, LON_NAMES))
            elif key == "lat" and _guess(cols, LAT_NAMES):
                combo.setCurrentText(_guess(cols, LAT_NAMES))

    def _table_columns(self) -> List[str]:
        name = self.tbl_combo.currentText()
        if name and name in self.ws:
            tbl = self.ws.get(name)
            if isinstance(tbl, Table):
                return list(tbl.colnames)
        return []

    # ---- accessors -------------------------------------------------------- #
    def table(self) -> Optional[Table]:
        """The selected workspace table when the table source is active."""
        if self.source.currentText() == WS_TABLE and self.tbl_combo.currentText():
            obj = self.ws.get(self.tbl_combo.currentText())
            return obj if isinstance(obj, Table) else None
        return None

    def lines(self) -> List[str]:
        return [ln.strip() for ln in self.text.toPlainText().splitlines()
                if ln.strip() and not ln.strip().startswith("#")]

    def labels(self, n: int) -> List[str]:
        """Display label per coordinate (text line, name column or ``#i``)."""
        src = self.source.currentText()
        if src == TEXT and len(self.lines()) == n:
            return self.lines()
        tbl = self.table()
        if tbl is not None and len(tbl) == n:
            col = _guess(tbl.colnames, NAME_COLS)
            if col:
                return [str(x) for x in tbl[col]]
        return [f"#{i + 1}" for i in range(n)]

    # ---- build SkyCoord ---------------------------------------------------- #
    def get(self) -> SkyCoord:
        """Parse the current input into a (possibly array) SkyCoord."""
        try:
            return self._get()
        except ParseError:
            raise
        except Exception as exc:  # noqa: BLE001 - astropy ValueErrors etc.
            raise ParseError(f"Invalid coordinates: {exc}") from None

    def _get(self) -> SkyCoord:
        src = self.source.currentText()
        if src == WS_SKYCOORD:
            name = self.sc_combo.currentText()
            if not name:
                raise ParseError("No SkyCoord in the workspace.")
            return self.ws.get(name)
        template = self.frame.build()
        if src == WS_TABLE:
            tbl = self.table()
            if tbl is None:
                raise ParseError("No table selected in the workspace.")
            lon_unit = self._unit(self.lon_unit, u.deg)
            lat_unit = self._unit(self.lat_unit, u.deg)
            lon = column_quantity(tbl, self.cols["lon"].currentText(), lon_unit, angle=True)
            lat = column_quantity(tbl, self.cols["lat"].currentText(), lat_unit, angle=True)
            n = len(tbl)
            dist = pm1 = pm2 = rv = None
            if self.cols["distance"].currentText() not in ("", NONE_COL):
                dist = column_quantity(tbl, self.cols["distance"].currentText(), u.pc)
            if self.cols["pm_lon"].currentText() not in ("", NONE_COL):
                pm1 = column_quantity(tbl, self.cols["pm_lon"].currentText(), u.mas / u.yr)
            if self.cols["pm_lat"].currentText() not in ("", NONE_COL):
                pm2 = column_quantity(tbl, self.cols["pm_lat"].currentText(), u.mas / u.yr)
            if self.cols["rv"].currentText() not in ("", NONE_COL):
                rv = column_quantity(tbl, self.cols["rv"].currentText(), u.km / u.s)
            if n == 0:
                raise ParseError("The table has no rows.")
        else:
            lon, lat = self._parse_lines()
            n = lon.size
            dist = self._opt(self.distance, u.pc, "distance")
            if dist is None and not _blank(self.parallax.text()):
                plx = parse_quantity(self.parallax.text(), u.mas, "parallax")
                if np.any(np.atleast_1d(plx) <= 0):
                    raise ParseError("parallax must be positive.")
                dist = np.atleast_1d(plx).to(u.pc, u.parallax())
            pm1 = self._opt(self.pm_lon, u.mas / u.yr, "pm lon")
            pm2 = self._opt(self.pm_lat, u.mas / u.yr, "pm lat")
            rv = self._opt(self.rv, u.km / u.s, "radial velocity")
        sc = self._assemble(template, lon, lat, n, dist, pm1, pm2, rv)
        obstime = self.frame.obstime_value()
        if obstime is not None and "obstime" not in frame_attribute_names(self.frame.name()):
            sc = SkyCoord(sc, obstime=obstime)
        return sc

    @staticmethod
    def _unit(combo: QComboBox, default: Any) -> Any:
        text = combo.currentText()
        return default if text == "auto" else u.Unit(text)

    @staticmethod
    def _opt(edit: QLineEdit, unit: Any, name: str) -> Optional[u.Quantity]:
        return None if not edit.text().strip() else parse_quantity(edit.text(), unit, name)

    def _parse_lines(self) -> Tuple[Angle, Angle]:
        lines = self.lines()
        if not lines:
            raise ParseError("Enter at least one coordinate.")
        lon_choice, lat_choice = self.lon_unit.currentText(), self.lat_unit.currentText()
        tokens = [_split_numeric(ln) for ln in lines]
        if all(len(t) == 2 for t in tokens):  # fast path
            lon_s, lat_s = [t[0] for t in tokens], [t[1] for t in tokens]
            try:
                lat_unit = u.deg if lat_choice == "auto" else u.Unit(lat_choice)
                if lon_choice != "auto":
                    return Angle(lon_s, unit=u.Unit(lon_choice)), Angle(lat_s, unit=lat_unit)
                # auto: sexagesimal hours ('10h30m', '10:30:00') vs plain degrees, per row
                is_h = np.array([("h" in s.lower() or ":" in s) for s in lon_s])
                lon_deg = np.empty(len(lon_s))
                for flag, unit in ((False, u.deg), (True, u.hourangle)):
                    sel = is_h == flag
                    if sel.any():
                        lon_deg[sel] = Angle([s for s, k in zip(lon_s, sel) if k],
                                             unit=unit).deg
                return Angle(lon_deg, unit=u.deg), Angle(lat_s, unit=lat_unit)
            except Exception:  # noqa: BLE001 - fall back to the line parser
                pass
        lons, lats = [], []
        lat_unit = u.deg if lat_choice == "auto" else u.Unit(lat_choice)
        for ln, tok in zip(lines, tokens):
            if re.search(r"[A-Za-z]", ln) and not re.search(r"\d\s*[hdms:]", ln):
                raise ParseError(f"{ln!r} is not a coordinate (use the Name resolver page).")
            if lon_choice != "auto":
                lon_unit = u.Unit(lon_choice)
            else:  # sexagesimal RA is conventionally in hours
                lon_unit = u.hourangle if (re.search(r"h|:", tok[0].lower()) or
                                           len(tok) == 6) else u.deg
            c = parse_skycoord(ln, unit=(lon_unit, lat_unit))
            lons.append(c.ra.deg)
            lats.append(c.dec.deg)
        return Angle(lons, unit=u.deg), Angle(lats, unit=u.deg)

    @staticmethod
    def _assemble(template: Any, lon: Angle, lat: Angle, n: int, dist: Any, pm1: Any,
                  pm2: Any, rv: Any) -> SkyCoord:
        lon = Longitude(_broadcast(lon, n, "longitude"))
        lat = Latitude(_broadcast(lat, n, "latitude"))
        if (pm1 is None) != (pm2 is None):
            raise ParseError("Give both proper-motion components or neither.")
        if dist is not None:
            dist = Distance(_broadcast(dist, n, "distance"))
        if rv is not None and dist is None:
            raise ParseError("Radial velocity needs a distance (or parallax).")
        if dist is None:
            rep = UnitSphericalRepresentation(lon, lat)
            if pm1 is not None:
                rep = rep.with_differentials(UnitSphericalCosLatDifferential(
                    _broadcast(pm1, n, "pm"), _broadcast(pm2, n, "pm")))
        else:
            rep = SphericalRepresentation(lon, lat, dist)
            if pm1 is not None or rv is not None:
                zero = np.zeros(n) * u.mas / u.yr
                rep = rep.with_differentials(SphericalCosLatDifferential(
                    _broadcast(pm1, n, "pm") if pm1 is not None else zero,
                    _broadcast(pm2, n, "pm") if pm2 is not None else zero,
                    _broadcast(rv, n, "rv") if rv is not None else np.zeros(n) * u.km / u.s))
        return SkyCoord(template.realize_frame(rep))


# --------------------------------------------------------------------------- #
# Output helpers
# --------------------------------------------------------------------------- #
ANGLE_FORMATS = ("decimal", "hmsdms", "dms", "radians")
REPRESENTATIONS = ("spherical", "unitspherical", "cartesian", "cylindrical", "physicsspherical")


def has_distance(sc: SkyCoord) -> bool:
    """True when ``sc`` carries a physical (length) distance."""
    if isinstance(sc.data, UnitSphericalRepresentation):
        return False
    return sc.spherical.distance.unit.is_equivalent(u.m)


def fmt_angle(a: Angle, fmt: str, *, hours: bool = False, precision: int = 4,
              alwayssign: bool = False) -> Any:
    """Format an Angle array as float column data or sexagesimal strings."""
    a = Angle(np.atleast_1d(a))
    if fmt == "decimal":
        return a.to(u.deg)
    if fmt == "radians":
        return a.to(u.rad)
    unit = u.hourangle if (fmt == "hmsdms" and hours) else u.deg
    out = a.to_string(unit=unit, sep=":", precision=precision, alwayssign=alwayssign
                      or unit == u.deg and fmt == "hmsdms", pad=True)
    return np.atleast_1d(np.asarray(out, dtype=str))


def coord_table(sc: SkyCoord, rep: str = "spherical", fmt: str = "decimal", precision: int = 6,
                alwayssign: bool = False) -> QTable:
    """Tabulate ``sc`` in a chosen representation and angle format."""
    sc = sc.reshape(-1) if sc.isscalar else sc
    names = list(sc.frame.representation_component_names)
    lon_name, lat_name = names[0], names[1]
    out = QTable()
    if rep in ("spherical", "unitspherical"):
        sph = sc.spherical
        out[lon_name] = fmt_angle(sph.lon, fmt, hours=True, precision=precision,
                                  alwayssign=alwayssign)
        out[lat_name] = fmt_angle(sph.lat, fmt, precision=precision, alwayssign=alwayssign)
        if rep == "spherical" and has_distance(sc):
            out["distance"] = sph.distance
    elif rep == "cartesian":
        cart = sc.cartesian
        for key in ("x", "y", "z"):
            out[key] = getattr(cart, key)
    elif rep == "cylindrical":
        cyl = sc.represent_as(CylindricalRepresentation)
        out["rho"], out["phi"], out["z"] = cyl.rho, fmt_angle(
            cyl.phi, fmt, precision=precision, alwayssign=alwayssign), cyl.z
    elif rep == "physicsspherical":
        ph = sc.represent_as(PhysicsSphericalRepresentation)
        out["phi"] = fmt_angle(ph.phi, fmt, precision=precision, alwayssign=alwayssign)
        out["theta"] = fmt_angle(ph.theta, fmt, precision=precision, alwayssign=alwayssign)
        out["r"] = ph.r
    else:
        raise ParseError(f"Unknown representation {rep!r}.")
    return out


def to_plain_table(qt: QTable) -> Table:
    """QTable -> Table (Quantity columns become Columns with units) for the workspace."""
    return Table(qt)


def time_strings(t: Time, offset_hours: float = 0.0, precision: int = 0) -> np.ndarray:
    """ISO strings of ``t`` shifted by a display offset."""
    t = Time(np.atleast_1d(t))
    if offset_hours:
        t = t + offset_hours * u.hour
    old = t.precision
    t.precision = precision
    out = np.atleast_1d(t.iso).astype(str)
    t.precision = old
    return out


def parse_times(text: str, name: str = "time") -> Time:
    """One time per non-empty line."""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip() and not ln.startswith("#")]
    if not lines:
        raise ParseError(f"{name}: enter at least one time.")
    times = [parse_time(ln, name=name) for ln in lines]
    return times[0] if len(times) == 1 else Time(times)


# --------------------------------------------------------------------------- #
# Event finding (rise / set / transit / twilight)
# --------------------------------------------------------------------------- #
def grid_size(hours: float, step_minutes: float) -> int:
    """Number of samples used by the event finders for a window and step."""
    return max(int(np.ceil(hours * 60.0 / step_minutes)) + 1, 2)


def find_crossings(func: Callable[[Time], u.Quantity], start: Time, hours: float,
                   step_minutes: float, level: float = 0.0, iterations: int = 16,
                   values: Optional[np.ndarray] = None) -> Tuple[List[Time], List[Time]]:
    """Times at which ``func`` (altitude, deg) rises through / falls through ``level``.

    Coarse sampling finds sign changes; bisection (vectorised over all brackets)
    refines them. ``values`` may supply ``func`` (in deg) on the coarse grid to save
    a evaluation; it must have ``grid_size(hours, step_minutes)`` entries.
    """
    n = grid_size(hours, step_minutes)
    x = np.linspace(0.0, hours / 24.0, n)
    if values is None:
        values = np.asarray(func(start + x * u.day).to_value(u.deg))
    vals = np.asarray(values) - level
    lo_neg = (vals[:-1] < 0) & (vals[1:] >= 0)
    hi_neg = (vals[:-1] >= 0) & (vals[1:] < 0)
    out: List[List[Time]] = []
    for mask, rising in ((lo_neg, True), (hi_neg, False)):
        idx = np.nonzero(mask)[0]
        if idx.size == 0:
            out.append([])
            continue
        lo, hi = x[idx].copy(), x[idx + 1].copy()
        for _ in range(iterations):
            mid = 0.5 * (lo + hi)
            v = np.asarray(func(start + mid * u.day).to_value(u.deg)) - level
            above = v >= 0
            # rising: root lies below mid when v>=0; falling: root lies above mid
            if rising:
                hi = np.where(above, mid, hi)
                lo = np.where(above, lo, mid)
            else:
                lo = np.where(above, mid, lo)
                hi = np.where(above, hi, mid)
        out.append(list(start + 0.5 * (lo + hi) * u.day))
    return out[0], out[1]


def find_culminations(func: Callable[[Time], u.Quantity], start: Time, hours: float,
                      step_minutes: float, iterations: int = 20,
                      values: Optional[np.ndarray] = None) -> List[Tuple[Time, float]]:
    """Interior local maxima of ``func`` (altitude) as ``(time, value_deg)``."""
    n = max(grid_size(hours, step_minutes), 3)
    x = np.linspace(0.0, hours / 24.0, n)
    if values is None or len(values) != n:
        values = np.asarray(func(start + x * u.day).to_value(u.deg))
    vals = np.asarray(values)
    idx = np.nonzero((vals[1:-1] >= vals[:-2]) & (vals[1:-1] > vals[2:]))[0] + 1
    if idx.size == 0:
        return []
    lo, hi = x[idx - 1].copy(), x[idx + 1].copy()
    for _ in range(iterations):  # ternary search, both probes in one call
        m1 = lo + (hi - lo) / 3.0
        m2 = hi - (hi - lo) / 3.0
        v = np.asarray(func(start + np.concatenate([m1, m2]) * u.day).to_value(u.deg))
        v1, v2 = v[:idx.size], v[idx.size:]
        move_lo = v1 < v2
        lo = np.where(move_lo, m1, lo)
        hi = np.where(move_lo, hi, m2)
    xm = 0.5 * (lo + hi)
    best = np.asarray(func(start + xm * u.day).to_value(u.deg))
    return [(start + xi * u.day, float(vi)) for xi, vi in zip(xm, best)]


def altitude_function(location: EarthLocation, refraction: Optional[Dict[str, Any]],
                      body: Any) -> Callable[[Time], u.Quantity]:
    """Altitude of a fixed SkyCoord (or body name such as 'sun'/'moon') as function of time."""
    def func(t: Time) -> u.Quantity:
        frame = AltAz(obstime=t, location=location, **(refraction or {}))
        if isinstance(body, str):
            return get_body(body, t, location).transform_to(frame).alt
        return body.transform_to(frame).alt
    return func


def moon_illumination(t: Time) -> Dict[str, Any]:
    """Moon illuminated fraction, phase angle and elongation (geocentric)."""
    sun, moon = get_body("sun", t), get_body("moon", t)
    elong = sun.separation(moon)
    phase = np.arctan2(sun.distance * np.sin(elong), moon.distance - sun.distance * np.cos(elong))
    return {"illumination": (1.0 + np.cos(phase)) / 2.0, "phase_angle": phase.to(u.deg),
            "elongation": elong.to(u.deg)}


def dark_intervals(set_times: List[Time], rise_times: List[Time], start: Time, end: Time,
                   initially_dark: bool) -> List[Tuple[Time, Time]]:
    """Intervals where the Sun is below a level, from its falling/rising crossings."""
    events = sorted([(t.jd, True, t) for t in set_times] + [(t.jd, False, t) for t in rise_times],
                    key=lambda e: e[0])
    out: List[Tuple[Time, Time]] = []
    current: Optional[Time] = start if initially_dark else None
    for _, falling, t in events:
        if falling:
            current = t
        elif current is not None:
            out.append((current, t))
            current = None
    if current is not None:
        out.append((current, end))
    return out
