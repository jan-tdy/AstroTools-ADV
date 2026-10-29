"""Catalog cross-matching, space motion and concatenation of coordinates."""
from __future__ import annotations

from typing import Dict, List, Optional

import numpy as np
from astropy import units as u
from astropy.coordinates import SkyCoord
from astropy.table import MaskedColumn, Table
from astropy.time import Time
from PyQt5.QtWidgets import QAbstractItemView, QListWidget, QWidget

from ..core.parsing import ParseError, parse_angle, parse_quantity, parse_time
from ..core.registry import ModuleSpec
from ..core.widgets import ModulePanel
from ..core.workspace import Workspace
from .coordinates_common import (
    CATEGORY, WS_TABLE, CoordInput, has_distance, offline_iers, time_strings,
)

MATCH_OPS = ("match_to_catalog_sky (nearest on sky)", "match_to_catalog_3d (nearest in 3D)",
             "search_around_sky (all pairs within angle)",
             "search_around_3d (all pairs within distance)")


def _prefixed(table: Table, prefix: str, idx: np.ndarray, mask: Optional[np.ndarray] = None
              ) -> Dict[str, object]:
    """Columns of ``table`` at ``idx`` (masked where ``mask`` is False)."""
    out: Dict[str, object] = {}
    for name in table.colnames:
        col = table[name][idx]
        if mask is not None and not mask.all() and not isinstance(col, u.Quantity):
            col = MaskedColumn(col, mask=~mask)
        out[f"{prefix}{name}"] = col
    return out


def cross_match(op: str, a: SkyCoord, b: SkyCoord, table_a: Optional[Table],
                table_b: Optional[Table], limit: Optional[u.Quantity], nth: int = 1,
                keep_unmatched: bool = True) -> Table:
    """Cross-match ``a`` against catalogue ``b``; see :data:`MATCH_OPS`."""
    a, b = (x.reshape(-1) if x.isscalar else x for x in (a, b))
    three_d = "3d" in op
    if three_d and not (has_distance(a) and has_distance(b)):
        raise ParseError("3D matching needs a distance column/value for both A and B.")
    res = Table()
    with offline_iers():
        if op.startswith("match_to_catalog"):
            if nth < 1 or nth > len(b):
                raise ParseError(f"nthneighbor must be between 1 and {len(b)}.")
            if three_d:
                idx, sep2d, d3d = a.match_to_catalog_3d(b, nthneighbor=nth)
            else:
                idx, sep2d, d3d = a.match_to_catalog_sky(b, nthneighbor=nth)
            matched = np.ones(len(a), dtype=bool)
            if limit is not None:
                if three_d:
                    matched = d3d <= limit
                else:
                    matched = sep2d <= limit
            res["idx_a"] = np.arange(len(a))
            res["idx_b"] = np.asarray(idx)
            res["sep_arcsec"] = sep2d.arcsec
            if three_d:
                res["sep3d_pc"] = d3d.to(u.pc)
            res["matched"] = matched
            if table_a is not None:
                for k, v in _prefixed(table_a, "a_", np.arange(len(a))).items():
                    res[k] = v
            if table_b is not None:
                for k, v in _prefixed(table_b, "b_", np.asarray(idx), matched).items():
                    res[k] = v
            if not keep_unmatched:
                res = res[matched]
        else:
            if limit is None:
                raise ParseError("A search radius / distance limit is required.")
            if three_d:
                i1, i2, sep2d, d3d = a.search_around_3d(b, limit)
            else:
                i1, i2, sep2d, d3d = a.search_around_sky(b, limit)
            res["idx_a"], res["idx_b"] = np.asarray(i1), np.asarray(i2)
            res["sep_arcsec"] = sep2d.arcsec
            if three_d:
                res["sep3d_pc"] = d3d.to(u.pc)
            if table_a is not None:
                for k, v in _prefixed(table_a, "a_", np.asarray(i1)).items():
                    res[k] = v
            if table_b is not None:
                for k, v in _prefixed(table_b, "b_", np.asarray(i2)).items():
                    res[k] = v
    return res


class MatchPanel(ModulePanel):
    def __init__(self, ws: Workspace) -> None:
        super().__init__(ws)
        self.a = CoordInput(ws, "Catalog A (sources)", default_source=WS_TABLE)
        self.b = CoordInput(ws, "Catalog B (reference)", default_source=WS_TABLE)
        self.controls_layout.insertWidget(0, self.a)
        self.controls_layout.insertWidget(1, self.b)
        self.form.add_combo("op", "Operation", MATCH_OPS)
        self.form.add_text("limit", "Limit", "1 arcsec",
                           "Max separation: angle for sky ('1 arcsec'), length for 3D ('10 pc'). "
                           "Required for search_around_*; optional match filter otherwise.")
        self.form.add_int("nth", "n-th neighbour", 1, 1, 10_000, "1 = nearest.")
        self.form.add_check("keep", "Keep unmatched rows", True,
                            "match_to_*: keep A rows whose nearest B is beyond the limit.")
        self.form.add_text("name", "Workspace name", "matched")
        self.table_view = self.add_table("Matches")
        self.out = self.add_output("Summary")
        self.add_button("Match", self.match)
        self.add_button("Store table in workspace", self.store)
        self.result: Optional[Table] = None

    def match(self) -> None:
        def prepare() -> None:
            v = self.form.values()
            op = v["op"]
            a, b = self.a.get(), self.b.get()
            limit: Optional[u.Quantity] = None
            if v["limit"].strip():
                limit = (parse_quantity(v["limit"], u.pc, "limit") if "3d" in op
                         else parse_angle(v["limit"], u.arcsec, "limit"))
            self.run(cross_match, self._done, op, a, b, self.a.table(), self.b.table(),
                     limit, v["nth"], v["keep"], busy_text="Matching...")
        self.guard(prepare)

    def _done(self, res: Table) -> None:
        self.result = res
        self.table_view.set_table(res)
        text = f"{len(res)} row(s)."
        if "matched" in res.colnames:
            text += f" {int(np.sum(res['matched']))} within the limit."
        self.out.show_text(text)

    def store(self) -> None:
        def go() -> None:
            if self.result is None:
                raise ParseError("Run a match first.")
            self.ws.put(self.form.value("name"), self.result)
        self.guard(go)


# --------------------------------------------------------------------------- #
# Space motion
# --------------------------------------------------------------------------- #
def space_motion(sc: SkyCoord, new_obstime: Optional[Time], dt: Optional[u.Quantity]
                 ) -> SkyCoord:
    """Propagate positions with proper motion (and RV when a distance is known)."""
    if (new_obstime is None) == (dt is None):
        raise ParseError("Give exactly one of: new epoch, time step dt.")
    if getattr(sc, "obstime", None) is None:
        raise ParseError("The coordinates need an epoch: set 'Obstime' of the input frame.")
    if not sc.data.differentials:
        raise ParseError("Proper motion is required (enter PM values or table columns).")
    with offline_iers():
        return sc.apply_space_motion(new_obstime=new_obstime, dt=dt)


class SpaceMotionPanel(ModulePanel):
    def __init__(self, ws: Workspace) -> None:
        super().__init__(ws)
        self.inp = CoordInput(ws, "Coordinates with proper motion",
                              default_text="269.45 4.69")
        self.controls_layout.insertWidget(0, self.inp)
        self.inp.distance.setText("1.83 pc")
        self.inp.pm_lon.setText("-798.58")
        self.inp.pm_lat.setText("10328.12")
        self.inp.rv.setText("-110.51")
        self.inp.frame.obstime.setText("J2000")
        self.form.add_text("new_obstime", "New epoch", "J2025.0",
                           "Target epoch (e.g. J2025.5, 2030-01-01). Leave blank to use dt.")
        self.form.add_text("dt", "or dt", "", "Time step, e.g. '10 yr' (when no new epoch).")
        self.form.add_text("name", "Workspace name", "moved")
        self.table_view = self.add_table("Positions")
        self.add_button("Apply space motion", self.apply)
        self.result: Optional[SkyCoord] = None

    def apply(self) -> None:
        def prepare() -> None:
            sc = self.inp.get()
            v = self.form.values()
            new = parse_time(v["new_obstime"], name="new epoch") if v["new_obstime"] else None
            dt = parse_quantity(v["dt"], u.yr, "dt") if v["dt"] else None
            self.run(space_motion, lambda r: self._done(sc, r), sc, new, dt,
                     busy_text="Propagating...")
        self.guard(prepare)

    def _done(self, before: SkyCoord, after: SkyCoord) -> None:
        self.result = after
        b = before.reshape(-1) if before.isscalar else before
        a = after.reshape(-1) if after.isscalar else after
        t = Table()
        t["lon_before_deg"], t["lat_before_deg"] = b.spherical.lon.deg, b.spherical.lat.deg
        t["lon_after_deg"], t["lat_after_deg"] = a.spherical.lon.deg, a.spherical.lat.deg
        t["shift_arcsec"] = b.separation(a).arcsec
        eps = time_strings(a.obstime)
        t["epoch_after"] = np.repeat(eps, len(a)) if len(eps) == 1 else eps
        self.table_view.set_table(t)
        self.ws.put(self.form.value("name"), after)


# --------------------------------------------------------------------------- #
# Concatenate
# --------------------------------------------------------------------------- #
class ConcatPanel(ModulePanel):
    def __init__(self, ws: Workspace) -> None:
        super().__init__(ws)
        self.list = QListWidget()
        self.list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.list.setToolTip("Select two or more SkyCoord objects from the workspace.")
        self.form.add_widget("list", "SkyCoords", self.list)
        self.form.add_text("name", "Result name", "combined")
        self.out = self.add_output("Result")
        self.add_button("Concatenate", self.concat)
        ws.changed.connect(self.refresh)
        self.refresh()

    def refresh(self) -> None:
        chosen = {i.text() for i in self.list.selectedItems()}
        self.list.clear()
        for name in self.ws.names(SkyCoord):
            self.list.addItem(name)
            if name in chosen:
                self.list.item(self.list.count() - 1).setSelected(True)

    def concat(self) -> None:
        def go() -> None:
            names: List[str] = [i.text() for i in self.list.selectedItems()]
            if len(names) < 2:
                raise ParseError("Select at least two SkyCoord objects.")
            parts = [self.ws.get(n) for n in names]
            parts = [p.reshape(-1) if p.isscalar else p for p in parts]
            with offline_iers():
                parts = [p if p.frame.is_equivalent_frame(parts[0].frame)
                         else p.transform_to(parts[0].frame) for p in parts]
                combined = np.concatenate(parts)
            name = self.ws.put(self.form.value("name"), combined)
            self.out.show_text(f"{name}: {len(combined)} coordinates in "
                               f"{type(combined.frame).__name__} from {', '.join(names)}")
        self.guard(go)


def _match(ws: Workspace) -> QWidget:
    return MatchPanel(ws)


def _motion(ws: Workspace) -> QWidget:
    return SpaceMotionPanel(ws)


def _concat(ws: Workspace) -> QWidget:
    return ConcatPanel(ws)


SPECS = [
    ModuleSpec("coord_match", "Catalog matching", CATEGORY, _match,
               "match_to_catalog_sky/3d and search_around_sky/3d on workspace tables"),
    ModuleSpec("coord_motion", "Space motion", CATEGORY, _motion,
               "SkyCoord.apply_space_motion with proper motion and radial velocity"),
    ModuleSpec("coord_concat", "Concatenate coordinates", CATEGORY, _concat,
               "Join workspace SkyCoord objects"),
]
