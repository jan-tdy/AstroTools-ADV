"""Frame converter, name resolver, distance and angle calculators."""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from astropy import units as u
from astropy.coordinates import (
    Angle, Distance, Latitude, Longitude, SkyCoord, get_constellation,
)
from astropy.table import Table
from PyQt5.QtWidgets import QWidget

from ..core.parsing import (
    ParseError, parse_angle, parse_array, parse_float, parse_unit, split_lines,
)
from ..core.registry import ModuleSpec
from ..core.widgets import ModulePanel
from ..core.workspace import Workspace
from .coordinates_common import (
    ANGLE_FORMATS, CATEGORY, REPRESENTATIONS, CoordInput, FrameInput, coord_table, fmt_angle,
    offline_iers, to_plain_table,
)


# --------------------------------------------------------------------------- #
# Frame converter
# --------------------------------------------------------------------------- #
def convert_coords(sc: SkyCoord, frame: Any, rep: str = "spherical", fmt: str = "decimal",
                   precision: int = 6, alwayssign: bool = False) -> Tuple[SkyCoord, Table, str]:
    """Transform ``sc`` to ``frame``; returns ``(SkyCoord, display table, info text)``."""
    with offline_iers():
        out = sc.transform_to(frame)
        table = coord_table(out, rep, fmt, precision, alwayssign)
        info = [repr(out.frame).splitlines()[0], f"Rows: {out.size}"]
        if out.data.differentials:
            info.append("Proper motion / radial velocity are carried through the transform.")
        flat = out.reshape(-1) if out.isscalar else out
        shown = flat[:50]
        try:
            strings = shown.to_string("hmsdms", precision=min(precision, 6))
            strings = [strings] if isinstance(strings, str) else list(strings)
            info.append("\nSkyCoord.to_string('hmsdms'):")
            info.extend(strings)
        except Exception:  # noqa: BLE001 - e.g. cartesian-only frames (Galactocentric)
            pass
        try:
            names = np.atleast_1d(get_constellation(shown, short_name=False))
            info.append("\nConstellation: " + ", ".join(dict.fromkeys(map(str, names))))
        except Exception:  # noqa: BLE001 - frames that cannot be mapped to ICRS directions
            pass
    return out, to_plain_table(table), "\n".join(info)


class ConverterPanel(ModulePanel):
    def __init__(self, ws: Workspace) -> None:
        super().__init__(ws)
        self.inp = CoordInput(ws, "Input", default_text="10.684 41.269")
        self.target = FrameInput(ws, "Target frame", default="Galactic")
        self.controls_layout.insertWidget(0, self.inp)
        self.controls_layout.insertWidget(1, self.target)
        self.form.add_combo("rep", "Representation", REPRESENTATIONS,
                            tip="How the result is expressed (needs distances for cartesian).")
        self.form.add_combo("fmt", "Angle format", ANGLE_FORMATS,
                            tip="decimal degrees, h:m:s / d:m:s, d:m:s only, or radians.")
        self.form.add_int("prec", "Precision", 4, 0, 12, "Digits after the decimal point "
                          "of sexagesimal seconds.")
        self.form.add_check("sign", "Always show sign", False)
        self.form.add_text("name", "Workspace name", "converted")
        self.table_view = self.add_table("Result")
        self.info = self.add_output("Info")
        self.add_button("Convert", self.convert)
        self.add_button("Store SkyCoord in workspace", self.store)
        self.result: Optional[SkyCoord] = None
        self.table: Optional[Table] = None

    def convert(self) -> None:
        def prepare() -> None:
            sc, frame = self.inp.get(), self.target.build()
            v = self.form.values()
            self.run(convert_coords, self._done, sc, frame, v["rep"], v["fmt"], v["prec"],
                     v["sign"], busy_text="Converting...")
        self.guard(prepare)

    def _done(self, res: Tuple[SkyCoord, Table, str]) -> None:
        self.result, self.table, info = res
        self.table_view.set_table(self.table)
        self.info.show_text(info)
        self.set_status(f"Converted {self.result.size} coordinate(s)")

    def store(self) -> None:
        def go() -> None:
            if self.result is None:
                raise ParseError("Convert something first.")
            name = self.ws.put(self.form.value("name"), self.result)
            self.ws.put(name + "_table", self.table)
            self.ws.log(f"Stored {name} (SkyCoord) and {name}_table")
        self.guard(go)


# --------------------------------------------------------------------------- #
# Name resolver
# --------------------------------------------------------------------------- #
def resolve_names(names: List[str], timeout: float = 10.0) -> Tuple[Optional[SkyCoord], List[str], List[str]]:
    """Resolve names with Sesame. Returns ``(coords, resolved_names, error_messages)``.

    Network failures are reported per name instead of raised.
    """
    from astropy.utils.data import conf as data_conf

    ok_names: List[str] = []
    coords: List[SkyCoord] = []
    errors: List[str] = []
    with data_conf.set_temp("remote_timeout", timeout):
        for name in names:
            try:
                coords.append(SkyCoord.from_name(name))
                ok_names.append(name)
            except Exception as exc:  # noqa: BLE001 - NameResolveError, URLError, timeouts
                msg = str(exc).strip().splitlines()[0] if str(exc).strip() else type(exc).__name__
                errors.append(f"{name}: {msg}")
    return (SkyCoord(coords) if coords else None), ok_names, errors


class NameResolverPanel(ModulePanel):
    def __init__(self, ws: Workspace) -> None:
        super().__init__(ws)
        self.form.add_multiline("names", "Object names", "M31\nVega",
                                "One object per line. Queries the CDS Sesame service - "
                                "needs internet access.")
        self.form.add_text("name", "Workspace name", "resolved")
        self.table_view = self.add_table("Resolved")
        self.out = self.add_output("Messages")
        self.add_button("Resolve", self.resolve)
        self.result: Optional[SkyCoord] = None
        self._names: List[str] = []

    def resolve(self) -> None:
        def prepare() -> None:
            names = split_lines(self.form.value("names"))
            if not names:
                raise ParseError("Enter at least one object name.")
            self.run(resolve_names, self._done, names, busy_text="Querying Sesame...")
        self.guard(prepare)

    def _done(self, res: Tuple[Optional[SkyCoord], List[str], List[str]]) -> None:
        sc, names, errors = res
        self.result, self._names = sc, names
        lines: List[str] = []
        if sc is None:
            self.table_view.set_table(None)
            lines.append("Nothing could be resolved. This needs internet access to the CDS "
                         "Sesame service; check the object names and your connection.")
        else:
            sc = sc.reshape(-1) if sc.isscalar else sc
            table = Table()
            table["name"] = names
            table["ra_deg"], table["dec_deg"] = sc.ra.deg, sc.dec.deg
            table["ra_hms"] = fmt_angle(sc.ra, "hmsdms", hours=True, precision=2)
            table["dec_dms"] = fmt_angle(sc.dec, "hmsdms", precision=1)
            cart = sc.cartesian
            table["x"], table["y"], table["z"] = cart.x.value, cart.y.value, cart.z.value
            self.table_view.set_table(table)
            self.ws.put(self.form.value("name"), sc)
            lines.append(f"Resolved {len(names)} name(s); stored as {self.form.value('name')!r}.")
        lines += [f"FAILED  {e}" for e in errors]
        self.out.show_text("\n".join(lines))


# --------------------------------------------------------------------------- #
# Distance / parallax / distance modulus
# --------------------------------------------------------------------------- #
def distance_table(kind: str, values: np.ndarray, unit: Any, apparent_mag: Optional[float] = None
                   ) -> Table:
    """All equivalent distance measures for ``values`` of ``kind``."""
    if values.size == 0 or not np.all(np.isfinite(values)):
        raise ParseError("Values must be finite numbers.")
    q = values * u.Unit(unit)
    if kind in ("distance", "parallax") and np.any(values <= 0):
        raise ParseError(f"{kind} values must be positive.")
    try:
        if kind == "distance":
            dist = Distance(q)
        elif kind == "parallax":
            dist = Distance(parallax=q)
        elif kind == "distmod":
            dist = Distance(distmod=q)
        else:
            raise ParseError(f"Unknown kind {kind!r}.")
    except (ValueError, u.UnitsError) as exc:
        raise ParseError(str(exc)) from None
    out = Table()
    out["pc"] = dist.to(u.pc)
    out["kpc"] = dist.to(u.kpc)
    out["Mpc"] = dist.to(u.Mpc)
    out["ly"] = dist.to(u.lyr)
    out["AU"] = dist.to(u.AU)
    out["m"] = dist.to(u.m)
    out["parallax_mas"] = (1.0 / dist.to_value(u.pc)) * 1000.0 * u.mas
    out["distmod_mag"] = dist.distmod.to(u.mag)
    if apparent_mag is not None:
        out["abs_mag"] = apparent_mag - dist.distmod.value
    return out


class DistancePanel(ModulePanel):
    def __init__(self, ws: Workspace) -> None:
        super().__init__(ws)
        self.form.add_combo("kind", "Input is", ["distance", "parallax", "distmod"],
                            tip="What the numbers below are.")
        self.form.add_multiline("values", "Values", "10\n100\n1000",
                                "Numbers separated by spaces/commas/newlines, or an expression "
                                "such as logspace(0, 3, 4).")
        self.form.add_combo("unit", "Unit", ["pc", "kpc", "Mpc", "ly", "AU", "m", "km", "mas",
                                             "arcsec", "uas", "mag"], editable=True,
                            tip="Unit of the values (distance units, angle for parallax, mag for "
                                "distance modulus).")
        self.form.add_text("mag", "Apparent magnitude", "", "Optional: also gives absolute magnitude.")
        self.table_view = self.add_table("Distances")
        self.add_button("Calculate", self.calculate)
        self.add_button("Store table in workspace", self.store)
        self.form.set_value("kind", "distance")
        self.form.fields["kind"].currentTextChanged.connect(self._kind_changed)
        self._table: Optional[Table] = None

    def _kind_changed(self, kind: str) -> None:
        self.form.set_value("unit", {"distance": "pc", "parallax": "mas", "distmod": "mag"}[kind])

    def calculate(self) -> None:
        def go() -> None:
            v = self.form.values()
            vals = parse_array(v["values"], "values")
            unit = parse_unit(v["unit"])
            mag = parse_float(v["mag"], "magnitude") if v["mag"] else None
            self._table = distance_table(v["kind"], vals, unit, mag)
            self.table_view.set_table(self._table)
        self.guard(go)

    def store(self) -> None:
        def go() -> None:
            if self._table is None:
                raise ParseError("Calculate first.")
            self.ws.put("distances", self._table)
        self.guard(go)


# --------------------------------------------------------------------------- #
# Angle calculator
# --------------------------------------------------------------------------- #
ANGLE_OPS = ("Convert / format", "A + B", "A - B", "A * k", "A / k", "Wrap at 180 (-180..180)",
             "Wrap at 360 (0..360)", "Validate as Latitude", "Wrap as Longitude",
             "Circular mean of A", "sin / cos / tan of A")


def _angles(text: str, unit: Any, name: str) -> Angle:
    lines = split_lines(text) or ([] if not text.strip() else [text.strip()])
    if not lines:
        raise ParseError(f"{name}: enter at least one angle.")
    return Angle([parse_angle(ln, unit, name).rad for ln in lines], unit=u.rad)


def angle_table(a: Angle, extra: Optional[Dict[str, Any]] = None) -> Table:
    """Angle in several units plus sexagesimal strings and tuples."""
    a = Angle(np.atleast_1d(a))
    t = Table()
    t["deg"] = a.to(u.deg)
    t["hourangle"] = a.to(u.hourangle)
    t["rad"] = a.to(u.rad)
    t["arcmin"] = a.to(u.arcmin)
    t["arcsec"] = a.to(u.arcsec)
    t["hms"] = fmt_angle(a, "hmsdms", hours=True, precision=3)
    t["dms"] = fmt_angle(a, "dms", precision=3, alwayssign=True)
    t["hms_tuple"] = [str(tuple(float(x) for x in r)) for r in np.array(a.hms).T]
    t["signed_dms"] = [f"({'+' if sg >= 0 else '-'}, {int(d)}, {int(m)}, {s:.4f})"
                       for sg, d, m, s in zip(*[np.atleast_1d(x) for x in a.signed_dms])]
    for k, v in (extra or {}).items():
        t[k] = v
    return t


def angle_operation(op: str, a: Angle, b: Optional[Angle], k: float) -> Table:
    """Apply one of :data:`ANGLE_OPS`; ``b`` is needed for A+B / A-B."""
    if op == "Convert / format":
        return angle_table(a)
    if op in ("A + B", "A - B"):
        if b is None:
            raise ParseError("Angle B is required.")
        if b.size not in (1, a.size):
            raise ParseError(f"A has {a.size} values but B has {b.size}.")
        return angle_table(a + b if op == "A + B" else a - b)
    if op == "A * k":
        return angle_table(a * k)
    if op == "A / k":
        if k == 0:
            raise ParseError("k must not be zero.")
        return angle_table(a / k)
    if op.startswith("Wrap at 180"):
        return angle_table(a.wrap_at(180 * u.deg))
    if op.startswith("Wrap at 360"):
        return angle_table(a.wrap_at(360 * u.deg))
    if op == "Validate as Latitude":
        try:
            return angle_table(Latitude(a))
        except ValueError as exc:
            raise ParseError(str(exc)) from None
    if op == "Wrap as Longitude":
        return angle_table(Longitude(a))
    if op == "Circular mean of A":
        mean = Angle(np.arctan2(np.sin(a).sum(), np.cos(a).sum()), unit=u.rad).wrap_at(360 * u.deg)
        resultant = float(np.hypot(np.sin(a).sum(), np.cos(a).sum()) / a.size)
        return angle_table(mean, {"resultant_length": [resultant]})
    if op.startswith("sin"):
        return angle_table(a, {"sin": np.sin(a).value, "cos": np.cos(a).value,
                               "tan": np.tan(a).value})
    raise ParseError(f"Unknown operation {op!r}.")


class AnglePanel(ModulePanel):
    def __init__(self, ws: Workspace) -> None:
        super().__init__(ws)
        self.form.add_combo("op", "Operation", ANGLE_OPS)
        self.form.add_multiline("a", "Angle A", "10h30m\n-5d12m3s\n12.5",
                                "One angle per line: '12.5', '10h30m', '-5d12m3s', '0.2 rad'.")
        self.form.add_multiline("b", "Angle B", "", "Second operand (one value or one per A).",
                                height=60)
        self.form.add_text("k", "Factor k", "2", "Number for A * k and A / k.")
        self.form.add_combo("unit", "Plain numbers are", ["deg", "hourangle", "rad", "arcmin",
                                                          "arcsec"],
                            tip="Unit for values written without a unit.")
        self.table_view = self.add_table("Result")
        self.add_button("Calculate", self.calculate)

    def calculate(self) -> None:
        def go() -> None:
            v = self.form.values()
            unit = u.Unit(v["unit"])
            a = _angles(v["a"], unit, "A")
            b = _angles(v["b"], unit, "B") if v["b"] else None
            k = parse_float(v["k"], "k") if v["op"] in ("A * k", "A / k") else 1.0
            self.table_view.set_table(angle_operation(v["op"], a, b, k))
        self.guard(go)


def _converter(ws: Workspace) -> QWidget:
    return ConverterPanel(ws)


def _resolver(ws: Workspace) -> QWidget:
    return NameResolverPanel(ws)


def _distance(ws: Workspace) -> QWidget:
    return DistancePanel(ws)


def _angles_panel(ws: Workspace) -> QWidget:
    return AnglePanel(ws)


SPECS = [
    ModuleSpec("coord_convert", "Frame converter", CATEGORY, _converter,
               "Transform sky coordinates between all astropy frames"),
    ModuleSpec("coord_resolver", "Name resolver", CATEGORY, _resolver,
               "SkyCoord.from_name via CDS Sesame (needs internet)"),
    ModuleSpec("coord_distance", "Distance / parallax", CATEGORY, _distance,
               "Distance, parallax and distance modulus"),
    ModuleSpec("coord_angles", "Angle calculator", CATEGORY, _angles_panel,
               "Angle arithmetic, wrapping, hms/dms conversion"),
]
