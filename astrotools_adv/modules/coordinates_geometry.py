"""Separations, position angles, offsets, great circles, random sphere samples."""
from __future__ import annotations

from typing import Callable, Dict, Optional, Tuple

import numpy as np
from astropy import units as u
from astropy.coordinates import (
    Angle, SkyCoord, UnitSphericalRepresentation, angular_separation, golden_spiral_grid, offset_by, position_angle,
    uniform_spherical_random_surface,
)
from astropy.table import Table
from PyQt5.QtWidgets import QWidget

from ..core.parsing import ParseError, parse_angle
from ..core.registry import ModuleSpec
from ..core.widgets import ModulePanel
from ..core.workspace import Workspace
from .coordinates_common import CATEGORY, CoordInput, has_distance, offline_iers


# --------------------------------------------------------------------------- #
# Pure operations (A, B are SkyCoord; return (Table, optional SkyCoord))
# --------------------------------------------------------------------------- #
Result = Tuple[Table, Optional[SkyCoord]]


def _flat(sc: SkyCoord) -> SkyCoord:
    return sc.reshape(-1) if sc.isscalar else sc


def _check_pair(a: SkyCoord, b: Optional[SkyCoord]) -> SkyCoord:
    if b is None:
        raise ParseError("Coordinate B is required for this operation.")
    a_n, b_n = a.size, b.size
    if a_n != b_n and 1 not in (a_n, b_n):
        raise ParseError(f"A has {a_n} rows but B has {b_n}; they must match or one must be 1.")
    return b


def op_separation(a: SkyCoord, b: Optional[SkyCoord], **_: object) -> Result:
    b = _check_pair(a, b)
    sep, pa = a.separation(b), a.position_angle(b)
    t = Table()
    t["sep_deg"], t["sep_arcmin"], t["sep_arcsec"] = (np.atleast_1d(sep.deg),
                                                      np.atleast_1d(sep.arcmin),
                                                      np.atleast_1d(sep.arcsec))
    t["pa_deg"] = np.atleast_1d(pa.wrap_at(360 * u.deg).deg)
    return t, None


def op_separation_3d(a: SkyCoord, b: Optional[SkyCoord], **_: object) -> Result:
    b = _check_pair(a, b)
    if not (has_distance(a) and has_distance(b)):
        raise ParseError("3D separation needs distances for both A and B.")
    d = np.atleast_1d(a.separation_3d(b))
    t = Table()
    t["sep3d_pc"], t["sep3d_AU"] = d.to(u.pc), d.to(u.AU)
    return t, None


def op_position_angle(a: SkyCoord, b: Optional[SkyCoord], **_: object) -> Result:
    b = _check_pair(a, b)
    t = Table()
    t["pa_deg"] = np.atleast_1d(a.position_angle(b).wrap_at(360 * u.deg).deg)
    return t, None


def op_offset_by(a: SkyCoord, b: Optional[SkyCoord], pa: u.Quantity, sep: u.Quantity,
                 **_: object) -> Result:
    new = _flat(a.directional_offset_by(pa, sep))
    return _table_of(new), new


def op_offsets_to(a: SkyCoord, b: Optional[SkyCoord], **_: object) -> Result:
    b = _check_pair(a, b)
    dlon, dlat = a.spherical_offsets_to(b)
    t = Table()
    t["dlon_deg"], t["dlat_deg"] = np.atleast_1d(dlon.deg), np.atleast_1d(dlat.deg)
    t["dlon_arcsec"], t["dlat_arcsec"] = np.atleast_1d(dlon.arcsec), np.atleast_1d(dlat.arcsec)
    return t, None


def op_offsets_by(a: SkyCoord, b: Optional[SkyCoord], dlon: u.Quantity, dlat: u.Quantity,
                  **_: object) -> Result:
    new = _flat(a.spherical_offsets_by(dlon, dlat))
    return _table_of(new), new


def op_skyoffset(a: SkyCoord, b: Optional[SkyCoord], **_: object) -> Result:
    """Express B in the offset frame centred on (the first) A."""
    if b is None:
        raise ParseError("Coordinate B is required for this operation.")
    origin = _flat(a)[0]
    with offline_iers():
        off = _flat(b).transform_to(origin.skyoffset_frame())
    t = Table()
    t["lon_deg"], t["lat_deg"] = off.lon.deg, off.lat.deg
    t["lon_arcsec"], t["lat_arcsec"] = off.lon.wrap_at(180 * u.deg).arcsec, off.lat.arcsec
    return t, None


def op_great_circle(a: SkyCoord, b: Optional[SkyCoord], n: int = 11, **_: object) -> Result:
    if b is None:
        raise ParseError("Coordinate B is required for this operation.")
    if n < 2 or n > 100_000:
        raise ParseError("Number of points must be between 2 and 100000.")
    a0, b0 = _flat(a)[0], _flat(b)[0]
    sep, pa = a0.separation(b0), a0.position_angle(b0)
    frac = np.linspace(0.0, 1.0, n)
    pts = _flat(a0.directional_offset_by(pa, sep * frac))
    t = _table_of(pts)
    t["fraction"] = frac
    t["from_A_deg"] = (sep * frac).deg
    return t, pts


def op_uniform_sphere(a: SkyCoord, b: Optional[SkyCoord], n: int = 100, seed: int = 0,
                      **_: object) -> Result:
    if n < 1 or n > 1_000_000:
        raise ParseError("Number of points must be between 1 and 1,000,000.")
    state = np.random.get_state()
    try:
        np.random.seed(seed % 2**32)
        lon, lat = _lonlat(uniform_spherical_random_surface(n))
    finally:
        np.random.set_state(state)
    sc = SkyCoord(lon, lat, frame="icrs")
    return _table_of(sc), sc


def op_golden_spiral(a: SkyCoord, b: Optional[SkyCoord], n: int = 100, **_: object) -> Result:
    if n < 1 or n > 1_000_000:
        raise ParseError("Number of points must be between 1 and 1,000,000.")
    sc = SkyCoord(*_lonlat(golden_spiral_grid(n)), frame="icrs")
    return _table_of(sc), sc


def _lonlat(rep) -> Tuple[u.Quantity, u.Quantity]:
    sph = rep.represent_as(UnitSphericalRepresentation)
    return sph.lon, sph.lat


def op_raw_angle_utils(a: SkyCoord, b: Optional[SkyCoord], pa: u.Quantity, sep: u.Quantity,
                       **_: object) -> Result:
    """Plain spherical trigonometry on the raw lon/lat of A and B (no frame handling)."""
    b = _check_pair(a, b)
    la, ba = a.spherical.lon, a.spherical.lat
    lb, bb = b.spherical.lon, b.spherical.lat
    t = Table()
    t["angular_separation_deg"] = np.atleast_1d(Angle(angular_separation(la, ba, lb, bb)).deg)
    t["position_angle_deg"] = np.atleast_1d(
        Angle(position_angle(la, ba, lb, bb)).wrap_at(360 * u.deg).deg)
    lon2, lat2 = offset_by(la, ba, pa, sep)
    t["offset_by_lon_deg"] = np.atleast_1d(Angle(lon2).wrap_at(360 * u.deg).deg)
    t["offset_by_lat_deg"] = np.atleast_1d(Angle(lat2).deg)
    return t, None


def _table_of(sc: SkyCoord) -> Table:
    t = Table()
    sph = _flat(sc).spherical
    t["lon_deg"], t["lat_deg"] = sph.lon.deg, sph.lat.deg
    return t


# operation name -> (function, needs B, parameter keys used)
OPERATIONS: Dict[str, Tuple[Callable[..., Result], bool, Tuple[str, ...]]] = {
    "Separation + position angle (A to B)": (op_separation, True, ()),
    "3D separation (needs distances)": (op_separation_3d, True, ()),
    "Position angle (A to B)": (op_position_angle, True, ()),
    "Offset A by position angle + separation": (op_offset_by, False, ("pa", "sep")),
    "Spherical offsets A to B (dlon, dlat)": (op_offsets_to, True, ()),
    "Spherical offsets: A by (dlon, dlat)": (op_offsets_by, False, ("dlon", "dlat")),
    "B in sky-offset frame centred on A": (op_skyoffset, True, ()),
    "Great circle A to B": (op_great_circle, True, ("n",)),
    "Uniform random points on sphere": (op_uniform_sphere, False, ("n", "seed")),
    "Golden-spiral grid on sphere": (op_golden_spiral, False, ("n",)),
    "Raw lon/lat trigonometry (angle utilities)": (op_raw_angle_utils, True, ("pa", "sep")),
}
NO_INPUT_OPS = ("Uniform random points on sphere", "Golden-spiral grid on sphere")


def run_operation(name: str, a: Optional[SkyCoord], b: Optional[SkyCoord],
                  params: Dict[str, object]) -> Result:
    func, _needs_b, _keys = OPERATIONS[name]
    if a is None and name not in NO_INPUT_OPS:
        raise ParseError("Coordinate A is required for this operation.")
    with offline_iers():
        return func(a, b, **params)


class GeometryPanel(ModulePanel):
    def __init__(self, ws: Workspace) -> None:
        super().__init__(ws)
        self.a = CoordInput(ws, "Coordinate A", default_text="0 0", motion=True)
        self.b = CoordInput(ws, "Coordinate B", default_text="0 90", motion=True)
        self.controls_layout.insertWidget(0, self.a)
        self.controls_layout.insertWidget(1, self.b)
        self.form.add_combo("op", "Operation", list(OPERATIONS))
        self.form.add_text("pa", "Position angle", "45 deg",
                           "Position angle east of north (e.g. '45', '90 deg').")
        self.form.add_text("sep", "Separation", "1 deg", "e.g. '1 deg', '30 arcmin'.")
        self.form.add_text("dlon", "dlon", "1 deg", "Longitude offset (on the sky, along lon).")
        self.form.add_text("dlat", "dlat", "0.5 deg", "Latitude offset.")
        self.form.add_int("n", "Points", 11, 1, 1_000_000, "Number of generated points.")
        self.form.add_int("seed", "Random seed", 0, 0, 2**31 - 1, "Seed for random points.")
        self.form.add_text("name", "Workspace name", "geometry")
        self.table_view = self.add_table("Result")
        self.out = self.add_output("Notes")
        self.add_button("Compute", self.compute)
        self.add_button("Store result coordinates", self.store)
        self.result_sc: Optional[SkyCoord] = None
        self.table: Optional[Table] = None
        self.form.fields["op"].currentTextChanged.connect(self._update_fields)
        self._update_fields()

    def _update_fields(self) -> None:
        op = self.form.value("op")
        func, needs_b, keys = OPERATIONS[op]
        for k in ("pa", "sep", "dlon", "dlat", "n", "seed"):
            self.form.fields[k].setEnabled(k in keys)
        self.b.setEnabled(needs_b)
        self.a.setEnabled(op not in NO_INPUT_OPS)

    def _params(self, op: str) -> Dict[str, object]:
        keys = OPERATIONS[op][2]
        v = self.form.values()
        out: Dict[str, object] = {}
        if "pa" in keys:
            out["pa"] = parse_angle(v["pa"], u.deg, "position angle")
        if "sep" in keys:
            out["sep"] = parse_angle(v["sep"], u.deg, "separation")
        if "dlon" in keys:
            out["dlon"] = parse_angle(v["dlon"], u.deg, "dlon")
        if "dlat" in keys:
            out["dlat"] = parse_angle(v["dlat"], u.deg, "dlat")
        if "n" in keys:
            out["n"] = int(v["n"])
        if "seed" in keys:
            out["seed"] = int(v["seed"])
        return out

    def compute(self) -> None:
        def prepare() -> None:
            op = self.form.value("op")
            _func, needs_b, _keys = OPERATIONS[op]
            a = None if op in NO_INPUT_OPS else self.a.get()
            b = self.b.get() if needs_b else None
            params = self._params(op)
            self.run(run_operation, self._done, op, a, b, params, busy_text="Computing...")
        self.guard(prepare)

    def _done(self, res: Result) -> None:
        self.table, self.result_sc = res
        self.table_view.set_table(self.table)
        self.out.show_text(f"{len(self.table)} row(s)." + (
            "\nResulting coordinates can be stored in the workspace." if self.result_sc is not None
            else ""))
        self.set_status("Done")

    def store(self) -> None:
        def go() -> None:
            if self.table is None:
                raise ParseError("Compute something first.")
            name = self.form.value("name")
            self.ws.put(name + "_table", self.table)
            if self.result_sc is not None:
                self.ws.put(name, self.result_sc)
        self.guard(go)


def _factory(ws: Workspace) -> QWidget:
    return GeometryPanel(ws)


SPECS = [ModuleSpec("coord_geometry", "Separations & geometry", CATEGORY, _factory,
                    "Separation, position angle, offsets, great circles, sphere samples")]
