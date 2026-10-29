"""astropy.cosmology tools: calculator, plots, z_at_value, unit equivalencies, compare & I/O."""
from __future__ import annotations

import ast
import warnings
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np
from astropy import cosmology
from astropy import units as u
from astropy.cosmology import Cosmology
from astropy.cosmology import units as cu
from astropy.cosmology.io import convert_registry, readwrite_registry
from astropy.table import Table
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QComboBox, QFormLayout, QLineEdit, QListWidget, QListWidgetItem, QWidget,
)

from ..core.parsing import (
    ParseError, parse_array, parse_float, parse_quantity, parse_unit, safe_eval,
)
from ..core.registry import ModuleSpec
from ..core.widgets import ModulePanel
from ..core.workspace import Workspace

CATEGORY = "Analysis"
u.add_enabled_units([cu.redshift, cu.littleh])  # lets '1 redshift', 'Mpc/littleh' parse

CLASS_NAMES = ["FlatLambdaCDM", "LambdaCDM", "FlatwCDM", "wCDM", "Flatw0waCDM", "w0waCDM",
               "Flatw0wzCDM", "w0wzCDM"]
WS_PREFIX = "ws: "
CUSTOM = "Custom"

# Methods taking a single redshift (array) argument.
Z_NAMES = [
    "H", "scale_factor", "efunc", "inv_efunc", "comoving_distance",
    "comoving_transverse_distance", "comoving_volume", "differential_comoving_volume",
    "luminosity_distance", "angular_diameter_distance", "kpc_proper_per_arcmin",
    "kpc_comoving_per_arcmin", "arcsec_per_kpc_proper", "arcsec_per_kpc_comoving", "distmod",
    "lookback_time", "lookback_distance", "age", "critical_density", "Om", "Ode", "Ogamma",
    "Onu", "Ok", "Odm", "Ob", "Otot", "Tcmb", "Tnu", "nu_relative_density",
    "absorption_distance", "w", "de_density_scale",
]
# Methods of two redshifts: display name -> cosmology method.
Z1Z2 = {"comoving_distance_z1z2": "comoving_distance",
        "angular_diameter_distance_z1z2": "angular_diameter_distance"}
DEFAULT_CHECKED = {"H", "comoving_distance", "luminosity_distance", "angular_diameter_distance",
                   "distmod", "lookback_time", "age"}

# z_at_value targets with the unit shown by default.
SOLVE_FUNCS = {
    "age": "Gyr", "lookback_time": "Gyr", "lookback_distance": "Mpc",
    "comoving_distance": "Mpc", "comoving_transverse_distance": "Mpc",
    "luminosity_distance": "Mpc", "angular_diameter_distance": "Mpc", "distmod": "mag",
    "H": "km / (s Mpc)", "critical_density": "g / cm3", "comoving_volume": "Mpc3",
    "differential_comoving_volume": "Mpc3 / sr", "absorption_distance": "",
    "scale_factor": "", "efunc": "", "Tcmb": "K", "Om": "", "Ode": "",
}


# --------------------------------------------------------------------------- #
# Parsing / validation
# --------------------------------------------------------------------------- #
def parse_redshifts(text: str, name: str = "redshift") -> np.ndarray:
    """Finite redshifts > -1 from a list or expression (e.g. ``linspace(0, 3, 7)``)."""
    z = np.atleast_1d(parse_array(text, name)).astype(float)
    if z.size == 0:
        raise ParseError(f"{name}: no values.")
    if not np.all(np.isfinite(z)):
        raise ParseError(f"{name}: values must be finite.")
    if np.any(z <= -1):
        raise ParseError(f"{name}: values must be greater than -1.")
    return z


def parse_kwargs(text: str) -> Dict[str, Any]:
    """Parse ``H0=70, Om0=0.3, name='x'`` into a dict using the safe evaluator."""
    text = (text or "").strip()
    if not text:
        raise ParseError("Enter at least one parameter, e.g. H0=70, Om0=0.3")
    try:
        call = ast.parse(f"f({text})", mode="eval").body
    except SyntaxError as exc:
        raise ParseError(f"Cannot parse parameters: {exc.msg}") from None
    if not isinstance(call, ast.Call) or call.args or any(k.arg is None for k in call.keywords):
        raise ParseError("Use keyword form: name=value, name=value")
    return {k.arg: safe_eval(ast.unparse(k.value)) for k in call.keywords}


def _parse_mnu(text: str) -> u.Quantity:
    text = text.strip()
    if not text:
        return 0.0 * u.eV
    try:
        return np.array([float(x) for x in text.replace(",", " ").split()]) * u.eV
    except ValueError:
        return parse_quantity(text, u.eV, "m_nu")


def build_cosmology(class_name: str, f: Dict[str, str]) -> Cosmology:
    """Construct a custom FLRW cosmology from form strings, validating inputs."""
    cls = getattr(cosmology, class_name)
    params = cls.parameters
    kw: Dict[str, Any] = {}
    kw["H0"] = parse_quantity(f["H0"], "km / (s Mpc)", "H0")
    if not (np.isfinite(kw["H0"].value) and kw["H0"].value > 0):
        raise ParseError("H0 must be positive.")
    kw["Om0"] = parse_float(f["Om0"], "Om0")
    if kw["Om0"] < 0:
        raise ParseError("Om0 must be >= 0.")
    for key in ("Ode0", "w0", "wa", "wz"):
        if key in params:
            kw[key] = parse_float(f[key], key)
    kw["Tcmb0"] = parse_quantity(f["Tcmb0"] or "0 K", "K", "Tcmb0")
    if kw["Tcmb0"].value < 0:
        raise ParseError("Tcmb0 must be >= 0.")
    kw["Neff"] = parse_float(f["Neff"] or "3.04", "Neff")
    if kw["Neff"] < 0:
        raise ParseError("Neff must be >= 0.")
    kw["m_nu"] = _parse_mnu(f["m_nu"])
    if f["Ob0"].strip():
        kw["Ob0"] = parse_float(f["Ob0"], "Ob0")
    if not all(np.all(np.isfinite(np.asarray(getattr(v, "value", v), dtype=float)))
               for v in kw.values()):
        raise ParseError("All parameters must be finite.")
    if f.get("name", "").strip():
        kw["name"] = f["name"].strip()
    try:
        return cls(**kw)
    except (ValueError, TypeError, u.UnitsError) as exc:
        raise ParseError(f"Invalid cosmology: {exc}") from None


def get_realization(name: str) -> Cosmology:
    if name not in cosmology.realizations.available:
        raise ParseError(f"Unknown realization {name!r}.")
    return getattr(cosmology, name)


def describe(c: Cosmology) -> str:
    """Multi-line description: parameters, derived constants, warnings, citation."""
    lines = [repr(c), "", "Parameters:"]
    for key in c.parameters:
        lines.append(f"  {key:<6} = {getattr(c, key)}")
    lines.append("")
    lines.append("Derived (z = 0):")
    for key in ("h", "Ode0", "Ok0", "Ogamma0", "Onu0", "Odm0", "Otot0", "Tnu0",
                "critical_density0", "hubble_distance", "hubble_time", "is_flat", "nonflat",
                "has_massive_nu"):
        try:
            lines.append(f"  {key:<18} = {getattr(c, key)}")
        except Exception as exc:  # noqa: BLE001 - some are undefined for some models
            lines.append(f"  {key:<18} = <{type(exc).__name__}>")
    try:
        lines.append(f"  {'age(0)':<18} = {c.age(0):.6g}")
    except Exception as exc:  # noqa: BLE001
        lines.append(f"  age(0) failed: {exc}")
    warn = []
    if getattr(c, "Ode0", 0) < 0:
        warn.append("Ode0 < 0 (unphysical dark energy density)")
    if getattr(c, "Ok0", 0) != 0 and c.is_flat:
        warn.append("flat model with non-zero curvature")
    if warn:
        lines += ["", "Warnings: " + "; ".join(warn)]
    if c.meta:
        lines += ["", "Metadata:"] + [f"  {k}: {v}" for k, v in c.meta.items()]
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Computation helpers (no Qt)
# --------------------------------------------------------------------------- #
def compute_quantities(c: Cosmology, z: np.ndarray, names: List[str],
                       z2: Optional[np.ndarray] = None) -> Tuple[Table, List[str]]:
    """Table of ``z`` and each requested quantity. Failures go to the notes list."""
    table = Table()
    table["z"] = z
    notes: List[str] = []
    if z2 is not None:
        table["z2"] = np.broadcast_to(z2, z.shape).copy()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        for name in names:
            try:
                if name in Z1Z2:
                    if z2 is None:
                        raise ParseError("needs the second redshift z2")
                    value = getattr(c, Z1Z2[name])(z, z2)
                else:
                    value = getattr(c, name)(z)
                value = u.Quantity(value) if isinstance(value, u.Quantity) else np.asarray(value)
                if value.shape != z.shape:
                    value = np.broadcast_to(value, z.shape).copy()
                table[name] = value
                if not np.all(np.isfinite(np.asarray(getattr(value, "value", value),
                                                      dtype=float))):
                    notes.append(f"{name}: non-finite values (e.g. at z=0 or outside the "
                                 "model's validity)")
            except Exception as exc:  # noqa: BLE001
                notes.append(f"{name}: {type(exc).__name__}: {exc}")
    return table, notes


def make_z_grid(zmin: float, zmax: float, n: int, log: bool) -> np.ndarray:
    if not (np.isfinite(zmin) and np.isfinite(zmax)) or zmin <= -1 or zmax <= zmin:
        raise ParseError("Need -1 < z min < z max.")
    if not 2 <= n <= 200_000:
        raise ParseError("Number of points must be between 2 and 200000.")
    if log:
        if zmin <= 0:
            raise ParseError("Log spacing needs z min > 0.")
        return np.logspace(np.log10(zmin), np.log10(zmax), n)
    return np.linspace(zmin, zmax, n)


def solve_z(c: Cosmology, func: str, values: np.ndarray, unit: u.UnitBase,
            kw: Dict[str, Any]) -> Table:
    """Run :func:`z_at_value` and verify by evaluating ``func(z)`` again."""
    fval = values * unit
    method = getattr(c, func)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        z = np.atleast_1d(cosmology.z_at_value(method, fval, **kw))
        back = u.Quantity(method(z))
    z = np.asarray(z.value if isinstance(z, u.Quantity) else z, dtype=float)
    back_v = back.to_value(unit)
    err = np.abs(back_v - values)
    rel = np.where(values != 0, err / np.abs(np.where(values != 0, values, 1)), err)
    t = Table()
    t["target"] = values * unit
    t["z"] = z
    t["func(z)"] = back_v * unit
    t["rel_error"] = rel
    return t


def build_equivalency(kind: str, c: Cosmology, distance: str = "comoving",
                      hubble: bool = True, tcmb: bool = True) -> Any:
    if kind == "redshift_distance":
        return cu.redshift_distance(c, kind=distance)
    if kind == "redshift_hubble":
        return cu.redshift_hubble(c)
    if kind == "redshift_temperature":
        return cu.redshift_temperature(c)
    if kind == "with_redshift":
        return cu.with_redshift(c, distance=distance, hubble=hubble, Tcmb=tcmb)
    if kind == "with_H0":
        return cu.with_H0(c.H0)
    if kind == "dimensionless_redshift":
        return cu.dimensionless_redshift()
    raise ParseError(f"Unknown equivalency {kind!r}.")


FORMAT_KWARGS = {"astropy.model": {"method": "luminosity_distance"}}  # required by to_model
EQUIVALENCIES = ["redshift_distance", "redshift_hubble", "redshift_temperature",
                 "with_redshift", "with_H0", "dimensionless_redshift"]


def registry_formats(registry: Any, direction: str) -> List[str]:
    """Format names of the registry that support ``direction`` ('Read' or 'Write')."""
    tab = registry.get_formats(Cosmology)
    return [str(r["Format"]) for r in tab if str(r[direction]).strip() == "Yes"]


# --------------------------------------------------------------------------- #
# Cosmology selector widget
# --------------------------------------------------------------------------- #
class CosmologySelector(QWidget):
    """Pick a registered realization, a workspace cosmology, or define a custom FLRW model."""

    changed = pyqtSignal()
    FIELDS = [("H0", "H0 [km/s/Mpc]", "70"), ("Om0", "Om0", "0.3"), ("Ode0", "Ode0", "0.7"),
              ("Tcmb0", "Tcmb0 [K]", "0"), ("Neff", "Neff", "3.04"),
              ("m_nu", "m_nu [eV]", "0"), ("Ob0", "Ob0", ""), ("w0", "w0", "-1"),
              ("wa", "wa", "0"), ("wz", "wz", "0"), ("name", "name", "Custom")]

    def __init__(self, ws: Workspace, default: str = "Planck18") -> None:
        super().__init__()
        self.ws = ws
        self.model = QComboBox()
        self.klass = QComboBox()
        self.klass.addItems(CLASS_NAMES)
        self.edits: Dict[str, QLineEdit] = {}
        lay = QFormLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addRow("Model", self.model)
        lay.addRow("Class", self.klass)
        for key, label, default_text in self.FIELDS:
            edit = QLineEdit(default_text)
            self.edits[key] = edit
            lay.addRow(label, edit)
            edit.textChanged.connect(lambda *_: self.changed.emit())
        self.edits["m_nu"].setToolTip("One value or several (eV), e.g. '0 0 0.06'.")
        self.edits["Ob0"].setToolTip("Blank = not specified.")
        self.model.setToolTip("Registered realization, workspace cosmology, or Custom.")
        self.refresh(default)
        self.model.currentTextChanged.connect(self._model_changed)
        self.klass.currentTextChanged.connect(self._class_changed)
        ws.changed.connect(lambda: self.refresh())
        self._model_changed()

    def refresh(self, select: Optional[str] = None) -> None:
        current = select or self.model.currentText()
        self.model.blockSignals(True)
        self.model.clear()
        self.model.addItems(list(cosmology.realizations.available))
        self.model.addItem(CUSTOM)
        self.model.addItems([WS_PREFIX + n for n in self.ws.names(Cosmology)])
        idx = self.model.findText(current)
        self.model.setCurrentIndex(max(idx, 0))
        self.model.blockSignals(False)
        if self.model.currentText() != current:
            self._model_changed()

    def _class_changed(self, *_: Any) -> None:
        params = getattr(cosmology, self.klass.currentText()).parameters
        custom = self.model.currentText() == CUSTOM
        for key, edit in self.edits.items():
            edit.setEnabled(custom and (key in params or key in ("name",)))
        self.changed.emit()

    def _model_changed(self, *_: Any) -> None:
        text = self.model.currentText()
        custom = text == CUSTOM
        self.klass.setEnabled(custom)
        if not custom:
            try:
                self._fill(self._lookup(text))
            except Exception:  # noqa: BLE001 - stale workspace entry; shown on use
                pass
        self._class_changed()

    def _lookup(self, text: str) -> Cosmology:
        if text.startswith(WS_PREFIX):
            obj = self.ws.get(text[len(WS_PREFIX):])
            if not isinstance(obj, Cosmology):
                raise ParseError(f"{text!r} is not a cosmology.")
            return obj
        return get_realization(text)

    def _fill(self, c: Cosmology) -> None:
        self.klass.blockSignals(True)
        self.klass.setCurrentText(type(c).__name__ if type(c).__name__ in CLASS_NAMES
                                  else self.klass.currentText())
        self.klass.blockSignals(False)
        for key in self.edits:
            if key == "name":
                self.edits[key].setText(c.name or "")
            elif key in c.parameters:
                val = getattr(c, key)
                if val is None:
                    txt = ""
                elif isinstance(val, u.Quantity):
                    arr = np.atleast_1d(val.value)
                    txt = " ".join(f"{x:.10g}" for x in arr)
                else:
                    txt = f"{val:.10g}"
                self.edits[key].setText(txt)

    def set_custom(self, class_name: str, **fields: str) -> None:
        """Programmatic helper (used by tests): switch to Custom and set field texts."""
        self.model.setCurrentText(CUSTOM)
        self.klass.setCurrentText(class_name)
        for k, v in fields.items():
            self.edits[k].setText(v)

    def cosmology(self) -> Cosmology:
        text = self.model.currentText()
        if text != CUSTOM:
            return self._lookup(text)
        return build_cosmology(self.klass.currentText(),
                               {k: e.text() for k, e in self.edits.items()})


class _CosmoPanel(ModulePanel):
    """Panel with a leading cosmology selector."""

    def __init__(self, ws: Workspace) -> None:
        super().__init__(ws)
        self.selector = CosmologySelector(ws)
        self.form.add_widget("cosmo", "Cosmology", self.selector)

    def cosmo(self) -> Cosmology:
        return self.selector.cosmology()

    def values(self) -> Dict[str, Any]:
        """Form values for plain fields (the selector and list widgets are read directly)."""
        return {k: self.form.value(k) for k, w in self.form.fields.items()
                if not isinstance(w, (CosmologySelector, QListWidget))}


# --------------------------------------------------------------------------- #
# Panels
# --------------------------------------------------------------------------- #
class CalculatorPanel(_CosmoPanel):
    def __init__(self, ws: Workspace) -> None:
        super().__init__(ws)
        f = self.form
        f.add_text("z", "Redshift z", "0.1, 0.5, 1, 2, 5", "List or expression, e.g. "
                   "linspace(0, 3, 13). Must be > -1.")
        f.add_text("z2", "z2 (for z1-z2)", "", "Second redshift for the *_z1z2 columns "
                   "(scalar or same length as z; z2 >= z).")
        self.qlist = QListWidget()
        self.qlist.setMinimumHeight(220)
        for name in list(Z_NAMES) + list(Z1Z2):
            item = QListWidgetItem(name)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if name in DEFAULT_CHECKED else Qt.Unchecked)
            self.qlist.addItem(item)
        f.add_widget("quantities", "Quantities", self.qlist)
        f.add_text("out", "Table name", "cosmo_table")
        f.add_text("cname", "Cosmology name", "cosmo", "Workspace name for 'Store cosmology'.")
        self.add_button("Compute table", lambda: self.guard(self.compute))
        self.add_button("Select all / none", self.toggle_all)
        self.add_button("Store cosmology in workspace", lambda: self.guard(self.store))
        self.add_button("Show cosmology details", lambda: self.guard(self.details))
        self.view = self.add_table("Table")
        self.info = self.add_output("Details")
        self.notes = self.add_output("Notes")

    def toggle_all(self) -> None:
        states = [self.qlist.item(i).checkState() == Qt.Checked for i in range(self.qlist.count())]
        new = Qt.Unchecked if all(states) else Qt.Checked
        for i in range(self.qlist.count()):
            self.qlist.item(i).setCheckState(new)

    def checked(self) -> List[str]:
        return [self.qlist.item(i).text() for i in range(self.qlist.count())
                if self.qlist.item(i).checkState() == Qt.Checked]

    def details(self) -> None:
        self.info.show_text(describe(self.cosmo()))
        self.tabs.setCurrentWidget(self.info)

    def store(self) -> None:
        name = self.form.value("cname")
        if not name:
            raise ParseError("Enter a cosmology name.")
        self.ws.put(name, self.cosmo())
        self.set_status(f"Stored cosmology '{name}'")

    def compute(self) -> None:
        c = self.cosmo()
        z = parse_redshifts(self.form.value("z"))
        z2 = None
        names = self.checked()
        if not names:
            raise ParseError("Select at least one quantity.")
        if self.form.value("z2"):
            z2 = parse_redshifts(self.form.value("z2"), "z2")
            if z2.size not in (1, z.size):
                raise ParseError("z2 must be a single value or have the same length as z.")
            if np.any(z2 < z):
                raise ParseError("z2 must be >= z.")
        elif any(n in Z1Z2 for n in names):
            raise ParseError("The *_z1z2 quantities need z2.")
        out = self.form.value("out")

        def done(res: Tuple[Table, List[str]]) -> None:
            table, notes = res
            if out:
                self.ws.put(out, table)
            self.view.set_table(table)
            self.notes.show_text("\n".join(notes) if notes else "No problems.")
            self.info.show_text(describe(c))
            self.tabs.setCurrentWidget(self.view)

        self.run(compute_quantities, done, c, z, names, z2, busy_text="Computing...")


class PlotPanel(_CosmoPanel):
    def __init__(self, ws: Workspace) -> None:
        super().__init__(ws)
        f = self.form
        f.add_combo("q", "Quantity", Z_NAMES, current="luminosity_distance")
        f.add_float("zmin", "z min", 0.01, -0.99, 1e6, 4)
        f.add_float("zmax", "z max", 5.0, -0.98, 1e6, 4)
        f.add_int("n", "Points", 200, 2, 200_000)
        f.add_check("logz", "Log-spaced z", False, "Requires z min > 0.")
        f.add_check("logx", "Log x axis", False)
        f.add_check("logy", "Log y axis", False)
        self.compare = QListWidget()
        self.compare.setMaximumHeight(150)
        for name in cosmology.realizations.available:
            item = QListWidgetItem(name)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Unchecked)
            self.compare.addItem(item)
        f.add_widget("compare", "Overlay", self.compare)
        f.add_text("out", "Table name", "cosmo_curves")
        self.add_button("Plot", lambda: self.guard(self.plot))
        self.canvas = self.add_plot("Plot")
        self.view = self.add_table("Data")

    def plot(self) -> None:
        v = self.values()
        main = self.cosmo()
        z = make_z_grid(v["zmin"], v["zmax"], v["n"], v["logz"])
        cosmos: List[Tuple[str, Cosmology]] = [(main.name or "selected", main)]
        for i in range(self.compare.count()):
            item = self.compare.item(i)
            if item.checkState() == Qt.Checked and item.text() != main.name:
                cosmos.append((item.text(), get_realization(item.text())))
        qname, out = v["q"], v["out"]

        def work() -> Tuple[Table, str]:
            table = Table()
            table["z"] = z
            unit = None
            for label, c in cosmos:
                tab, notes = compute_quantities(c, z, [qname])
                if qname not in tab.colnames:
                    raise ParseError(notes[0] if notes else f"{qname} failed")
                col = tab[qname]
                if unit is None:
                    unit = col.unit
                elif col.unit is not None:
                    col = u.Quantity(col).to(unit)
                key = label
                while key in table.colnames:
                    key += "_"
                table[key] = col
            return table, str(unit) if unit not in (None, "") else ""

        def done(res: Tuple[Table, str]) -> None:
            table, unit = res
            ax = self.canvas.axes()
            for name in table.colnames[1:]:
                ax.plot(table["z"], np.asarray(table[name], dtype=float), label=name)
            ax.set_xlabel("redshift z")
            ax.set_ylabel(f"{qname} [{unit}]" if unit else qname)
            if v["logx"]:
                ax.set_xscale("log")
            if v["logy"]:
                ax.set_yscale("log")
            ax.legend(fontsize="small")
            ax.grid(alpha=0.3)
            self.canvas.redraw()
            self.view.set_table(table)
            if out:
                self.ws.put(out, table)

        self.run(work, done, busy_text="Computing curves...")


class SolverPanel(_CosmoPanel):
    def __init__(self, ws: Workspace) -> None:
        super().__init__(ws)
        f = self.form
        f.add_combo("func", "Quantity", list(SOLVE_FUNCS), current="luminosity_distance")
        f.add_text("values", "Target value(s)", "1000, 5000", "Numbers or expression.")
        f.add_text("unit", "Unit", SOLVE_FUNCS["luminosity_distance"],
                   "Unit of the target values (blank = dimensionless).")
        f.add_float("zmin", "z min", 1e-8, -0.99, 1e9, 9)
        f.add_float("zmax", "z max", 1000.0, -0.98, 1e9, 3)
        f.add_float("ztol", "z tolerance", 1e-8, 1e-15, 1.0, 12)
        f.add_int("maxfun", "Max evaluations", 500, 10, 1_000_000)
        f.add_combo("method", "Method", ["Brent", "Golden", "Bounded"],
                    "Bracket only applies to Brent/Golden.")
        f.add_text("bracket", "Bracket", "", "Optional 'a, b' or 'a, b, c' starting points.")
        f.add_text("out", "Table name", "z_solutions")
        f.fields["func"].currentTextChanged.connect(
            lambda name: f.set_value("unit", SOLVE_FUNCS.get(name, "")))
        self.add_button("Solve z_at_value", lambda: self.guard(self.solve))
        self.view = self.add_table("Solutions")
        self.notes = self.add_output("Notes")

    def solve(self) -> None:
        v = self.values()
        c = self.cosmo()
        values = np.atleast_1d(parse_array(v["values"], "target values")).astype(float)
        if not np.all(np.isfinite(values)):
            raise ParseError("Target values must be finite.")
        unit = parse_unit(v["unit"])
        if v["zmax"] <= v["zmin"]:
            raise ParseError("z max must exceed z min.")
        kw: Dict[str, Any] = dict(zmin=v["zmin"], zmax=v["zmax"], ztol=v["ztol"],
                                  maxfun=v["maxfun"], method=v["method"])
        if v["bracket"]:
            br = tuple(float(x) for x in v["bracket"].replace(",", " ").split())
            if len(br) not in (2, 3):
                raise ParseError("Bracket needs 2 or 3 numbers.")
            kw["bracket"] = br
        func, out = v["func"], v["out"]

        def done(table: Table) -> None:
            if out:
                self.ws.put(out, table)
            self.view.set_table(table)
            bad = np.asarray(table["rel_error"]) > 1e-4
            self.notes.show_text(
                "Round-trip check func(z) vs target: OK." if not bad.any() else
                f"{int(bad.sum())} solution(s) did not round-trip; the function may be "
                "non-monotonic here - restrict z min/z max or give a bracket.")

        self.run(solve_z, done, c, func, values, unit, kw, busy_text="Solving...")


class UnitsPanel(_CosmoPanel):
    def __init__(self, ws: Workspace) -> None:
        super().__init__(ws)
        f = self.form
        f.add_combo("equiv", "Equivalency", EQUIVALENCIES,
                    "astropy.cosmology.units equivalency to enable.")
        f.add_combo("distance", "Distance kind", ["comoving", "lookback", "luminosity"],
                    "For redshift_distance / with_redshift.")
        f.add_check("hubble", "Include Hubble (with_redshift)", True)
        f.add_check("tcmb", "Include Tcmb (with_redshift)", True)
        f.add_text("value", "Value", "1", "Number or array.")
        f.add_text("unit", "Unit", "redshift", "e.g. redshift, Mpc, K, Mpc/littleh")
        f.add_text("target", "Convert to", "Mpc")
        self.add_button("Convert", lambda: self.guard(self.convert))
        self.out = self.add_output("Result")

    def convert(self) -> None:
        v = self.values()
        c = self.cosmo()
        value = np.atleast_1d(parse_array(v["value"], "value")) * parse_unit(v["unit"])
        target = parse_unit(v["target"], "target unit")
        eq = build_equivalency(v["equiv"], c, v["distance"], v["hubble"], v["tcmb"])

        def work() -> u.Quantity:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                return value.to(target, eq)

        def done(res: u.Quantity) -> None:
            self.out.show_text(f"{value} -> {res}\n\nequivalency: {v['equiv']}\n"
                               f"cosmology: {c.name}")

        self.run(work, done, busy_text="Converting...")


class CompareIOPanel(_CosmoPanel):
    def __init__(self, ws: Workspace) -> None:
        super().__init__(ws)
        self.other = CosmologySelector(ws, "Planck15")
        f = self.form
        f.add_widget("other", "Compare with", self.other)
        f.add_text("changes", "Edit (clone) A", "H0=70", "Keyword changes, e.g. H0=70, Om0=0.3, "
                   "name='mine'.")
        f.add_text("cname", "Store as", "edited", "Workspace name for clone/read results.")
        f.add_combo("wfmt", "Write format", registry_formats(readwrite_registry, "Write"))
        f.add_combo("rfmt", "Read format", registry_formats(readwrite_registry, "Read"))
        f.add_combo("tfmt", "Convert to", registry_formats(convert_registry, "Write"))
        f.add_multiline("text", "From text (YAML or mapping)", "", "YAML text, or a Python dict "
                        "with a 'cosmology' class name key.", 110)
        self.add_button("Compare A with B", lambda: self.guard(self.compare))
        self.add_button("Clone A with changes", lambda: self.guard(self.clone))
        self.add_button("Write A to file...", lambda: self.guard(self.write))
        self.add_button("Read file...", lambda: self.guard(self.read))
        self.add_button("Convert A to format", lambda: self.guard(self.to_format))
        self.add_button("Create from text", lambda: self.guard(self.from_text))
        self.add_button("Set A as default cosmology", lambda: self.guard(self.set_default))
        self.add_button("Reset default (Planck18)", lambda: self.guard(self.reset_default))
        self.result = self.add_output("Result")
        self.view = self.add_table("Parameters")

    def compare(self) -> None:
        a, b = self.cosmo(), self.other.cosmology()
        keys = list(dict.fromkeys(list(a.parameters) + list(b.parameters)))

        def same(x: Any, y: Any) -> str:
            try:
                return "yes" if np.all(np.asarray(x == y)) else "no"
            except Exception:  # noqa: BLE001
                return "n/a"

        def val(c: Cosmology, k: str) -> str:
            return str(getattr(c, k)) if k in c.parameters else "-"

        rows = [(k, val(a, k), val(b, k),
                 same(getattr(a, k), getattr(b, k)) if k in a.parameters and k in b.parameters
                 else "no") for k in keys]
        self.view.set_table(Table(rows=rows, names=["parameter", "A", "B", "same"],
                                  dtype=["U40"] * 4))
        self.result.show_text(
            f"A = {a.name or type(a).__name__}   B = {b.name or type(b).__name__}\n"
            f"A == B:            {a == b}\n"
            f"A.is_equivalent(B): {a.is_equivalent(b)}  (same physics, names ignored)\n"
            f"same class:        {type(a) is type(b)}")
        self.tabs.setCurrentWidget(self.result)

    def clone(self) -> None:
        a = self.cosmo()
        kw = parse_kwargs(self.form.value("changes"))
        bad = [k for k in kw if k not in a.parameters and k not in ("name", "meta")]
        if bad:
            raise ParseError(f"Not parameters of {type(a).__name__}: {bad}")
        try:
            new = a.clone(**kw)
        except (ValueError, TypeError, u.UnitsError) as exc:
            raise ParseError(f"Invalid change: {exc}") from None
        name = self.form.value("cname")
        if not name:
            raise ParseError("Enter a 'Store as' name.")
        self.ws.put(name, new)
        self.result.show_text(f"Stored '{name}':\n\n{describe(new)}")
        self.tabs.setCurrentWidget(self.result)

    def write(self) -> None:
        c = self.cosmo()
        fmt = self.form.value("wfmt")
        path = self.ask_save_path("Write cosmology", "All files (*)", f"{c.name or 'cosmology'}.ecsv")
        if path:
            c.write(path, format=fmt, overwrite=True)
            self.set_status(f"Wrote {path}")

    def read(self) -> None:
        path = self.ask_open_path("Read cosmology")
        if not path:
            return
        try:
            c = Cosmology.read(path, format=self.form.value("rfmt"))
        except Exception as exc:  # noqa: BLE001
            raise ParseError(f"Cannot read {path!r}: {exc}") from None
        name = self.form.value("cname") or "cosmology"
        self.ws.put(name, c)
        self.result.show_text(f"Stored '{name}':\n\n{describe(c)}")

    def to_format(self) -> None:
        c, fmt = self.cosmo(), self.form.value("tfmt")
        res = c.to_format(fmt, **FORMAT_KWARGS.get(fmt, {}))
        self.result.show_text(f"format: {fmt}\n\n{res if isinstance(res, str) else repr(res)}")
        self.tabs.setCurrentWidget(self.result)

    def from_text(self) -> None:
        text = self.form.value("text")
        if not text:
            raise ParseError("Paste YAML text or a mapping first.")
        try:
            if text.lstrip().startswith("{"):
                data = safe_eval(text, {k: k for k in CLASS_NAMES})
                if not isinstance(data, dict):
                    raise ParseError("Mapping must be a dict.")
                if isinstance(data.get("cosmology"), str):
                    data["cosmology"] = get_class(data["cosmology"])
                c = Cosmology.from_format(data, format="mapping")
            else:
                c = Cosmology.from_format(text, format="yaml")
        except ParseError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise ParseError(f"Cannot create cosmology: {exc}") from None
        name = self.form.value("cname") or "cosmology"
        self.ws.put(name, c)
        self.result.show_text(f"Stored '{name}':\n\n{describe(c)}")

    def set_default(self) -> None:
        c = self.cosmo()
        cosmology.default_cosmology.set(c)
        self.result.show_text(f"default_cosmology is now:\n{cosmology.default_cosmology.get()!r}\n\n"
                              "(applies to this session only)")

    def reset_default(self) -> None:
        cosmology.default_cosmology.set("Planck18")
        self.result.show_text(f"default_cosmology reset:\n{cosmology.default_cosmology.get()!r}")


def get_class(name: str) -> type:
    if name not in CLASS_NAMES:
        raise ParseError(f"Unknown cosmology class {name!r}; choose from {CLASS_NAMES}.")
    return getattr(cosmology, name)


def _spec(key: str, title: str, cls: type, desc: str) -> ModuleSpec:
    return ModuleSpec(key, title, CATEGORY, lambda ws, c=cls: c(ws), desc)


SPECS = [
    _spec("cosmo_calc", "Cosmology: Calculator", CalculatorPanel,
          "Distances, ages, densities for any FLRW cosmology"),
    _spec("cosmo_plot", "Cosmology: Plots", PlotPanel,
          "Plot a quantity versus redshift and compare cosmologies"),
    _spec("cosmo_zatvalue", "Cosmology: z_at_value", SolverPanel,
          "Solve for the redshift that gives a distance, age, ..."),
    _spec("cosmo_units", "Cosmology: Unit equivalencies", UnitsPanel,
          "astropy.cosmology.units: redshift, littleh, with_H0, with_redshift"),
    _spec("cosmo_io", "Cosmology: Compare & I/O", CompareIOPanel,
          "Compare, clone, read/write, convert formats and set the default cosmology"),
]
