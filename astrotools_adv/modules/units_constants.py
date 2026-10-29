"""Units, quantities and physical constants (astropy.units / astropy.constants)."""
from __future__ import annotations

import importlib
import re
from types import SimpleNamespace
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from astropy import units as u
from astropy.constants import Constant
from astropy.table import Table
from PyQt5.QtWidgets import QWidget

from ..core.parsing import ParseError, parse_quantity, parse_unit, safe_eval, split_lines
from ..core.registry import ModuleSpec
from ..core.widgets import ModulePanel
from ..core.workspace import Workspace

CATEGORY = "Basics"

# name -> (label of parameter 1, label of optional parameter 2); "" = unused
EQUIVALENCY_PARAMS: Dict[str, Tuple[str, str]] = {
    "none": ("", ""),
    "spectral": ("", ""),
    "spectral_density": ("Wavelength or frequency", ""),
    "doppler_radio": ("Rest frequency / wavelength / energy", ""),
    "doppler_optical": ("Rest frequency / wavelength / energy", ""),
    "doppler_relativistic": ("Rest frequency / wavelength / energy", ""),
    "doppler_redshift": ("", ""),
    "parallax": ("", ""),
    "temperature": ("", ""),
    "temperature_energy": ("", ""),
    "brightness_temperature": ("Frequency", "Beam area (optional)"),
    "thermodynamic_temperature": ("Frequency", "T_cmb (optional)"),
    "mass_energy": ("", ""),
    "logarithmic": ("", ""),
    "dimensionless_angles": ("", ""),
    "pixel_scale": ("Pixel scale (e.g. 0.5 arcsec/pix)", ""),
    "plate_scale": ("Plate scale (e.g. 20 arcsec/mm)", ""),
    "molar_mass_amu": ("", ""),
    "beam_angular_area": ("Beam area", ""),
}
PLAIN_EQUIVALENCIES = tuple(n for n, p in EQUIVALENCY_PARAMS.items() if n != "none" and not p[0])

CONSTANT_SETS = ["astropy default", "astropyconst13", "astropyconst20", "astropyconst40",
                 "astropyconst80", "codata2010", "codata2014", "codata2018", "codata2022"]

SI_PREFIXES = [
    ("quetta", "Q"), ("ronna", "R"), ("yotta", "Y"), ("zetta", "Z"), ("exa", "E"),
    ("peta", "P"), ("tera", "T"), ("giga", "G"), ("mega", "M"), ("kilo", "k"),
    ("hecto", "h"), ("deca", "da"), ("deci", "d"), ("centi", "c"), ("milli", "m"),
    ("micro", "u"), ("nano", "n"), ("pico", "p"), ("femto", "f"), ("atto", "a"),
    ("zepto", "z"), ("yocto", "y"), ("ronto", "r"), ("quecto", "q"),
]
BINARY_PREFIXES = [("kibi", "Ki"), ("mebi", "Mi"), ("gibi", "Gi"), ("tebi", "Ti"),
                   ("pebi", "Pi"), ("exbi", "Ei"), ("zebi", "Zi"), ("yobi", "Yi")]

_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_ASSIGNMENT = re.compile(r"^([A-Za-z_]\w*)\s*=(?!=)\s*(.+)$")
MAX_LISTED = 15


# --------------------------------------------------------------------------- #
# Pure helpers (no Qt) -- also used by the tests
# --------------------------------------------------------------------------- #
def read_quantity(text: str, default_unit: Any = None, name: str = "value") -> u.Quantity:
    """:func:`parse_quantity` plus astropy's own string syntax (``'3 m**2'``)."""
    try:
        return parse_quantity(text, default_unit, name)
    except ParseError as first:
        try:
            return u.Quantity((text or "").strip())
        except Exception:  # noqa: BLE001
            raise first from None


def format_value(value: Any) -> str:
    """Full-precision text for scalars/quantities; ``str`` for everything else."""
    if isinstance(value, u.Quantity) and value.isscalar:
        raw = value.value
        raw = raw.item() if hasattr(raw, "item") else raw
        return f"{raw!r} {value.unit}".strip()
    return str(value)


def build_equivalency(name: str, p1: str = "", p2: str = "") -> List[Any]:
    """Equivalency list for ``name`` with the user's parameter texts."""
    if name not in EQUIVALENCY_PARAMS:
        raise ParseError(f"Unknown equivalency {name!r}.")
    if name == "none":
        return []
    label1, label2 = EQUIVALENCY_PARAMS[name]
    if label1 and not (p1 or "").strip():
        raise ParseError(f"{name} needs parameter 1: {label1}.")
    args = [read_quantity(text, name=label)
            for text, label in ((p1, label1), (p2, label2)) if label and (text or "").strip()]
    return list(getattr(u, name)(*args))


def parse_extra_equivalencies(text: str) -> List[Any]:
    """Comma/space separated parameter-free equivalency names."""
    out: List[Any] = []
    for part in re.split(r"[\s,;]+", (text or "").strip()):
        if not part:
            continue
        if part not in PLAIN_EQUIVALENCIES:
            raise ParseError(f"{part!r} is not a parameter-free equivalency "
                             f"({', '.join(PLAIN_EQUIVALENCIES)}).")
        out.extend(getattr(u, part)())
    return out


def convert_quantity(v: Dict[str, Any]) -> Tuple[str, u.Quantity]:
    """Convert per the converter form values; returns ``(report, result)``."""
    q = read_quantity(v["value"], name="value")
    eq = build_equivalency(v["equivalency"], v["param1"], v["param2"])
    eq += parse_extra_equivalencies(v["extra"])
    lines = [f"Input:         {format_value(q)}"]
    if v["equivalency"] != "none" or eq:
        lines.append(f"Equivalencies: {v['equivalency']}"
                     + (f" + {v['extra']}" if v["extra"] else ""))
    result = q
    if v["target"]:
        target = parse_unit(v["target"], "target unit")
        try:
            result = q.to(target, equivalencies=eq)
        except u.UnitsError as exc:
            raise ParseError(f"Cannot convert {q.unit} to {target}: {exc}") from exc
        lines.append(f"Result:        {format_value(result)}")
    for label, attr in (("SI", "si"), ("CGS", "cgs")):
        try:
            lines.append(f"{label}:{' ' * (13 - len(label))}{format_value(getattr(result, attr))}")
        except Exception:  # noqa: BLE001 - function units have no si/cgs
            pass
    try:
        lines.append(f"Physical type: {result.unit.physical_type}")
    except Exception:  # noqa: BLE001
        pass
    return "\n".join(lines), result


def _safe(fn: Any) -> str:
    try:
        return str(fn())
    except Exception as exc:  # noqa: BLE001
        return f"n/a ({type(exc).__name__}: {exc})"


def _limited(items: List[Any], n: int = MAX_LISTED) -> str:
    text = ", ".join(str(i) for i in items[:n]) or "(none)"
    return text + (f", ... (+{len(items) - n} more)" if len(items) > n else "")


def analyze_unit(text: str) -> str:
    """Multi-section description of a unit expression."""
    if not (text or "").strip():
        raise ParseError("Enter a unit, e.g. 'km / s' or 'erg s-1 cm-2 AA-1'.")
    unit = parse_unit(text)

    def row(label: str, value: str) -> str:
        return f"{label:<20}{value}"

    lines = [row("Unit:", repr(unit)), row("Physical type:", _safe(lambda: unit.physical_type))]
    for fmt in ("generic", "latex", "unicode", "fits", "ogip", "vounit", "cds"):
        lines.append(row(f"{fmt}:", _safe(lambda: unit.to_string(fmt))))
    lines += [row("Decomposed (SI):", _safe(lambda: unit.decompose())),
              row("  scale:", _safe(lambda: unit.decompose().scale)),
              row("  bases:", _safe(lambda: [str(b) for b in unit.decompose().bases])),
              row("  powers:", _safe(lambda: unit.decompose().powers)),
              row("Decomposed (CGS):", _safe(lambda: unit.decompose(bases=u.cgs.bases))),
              row("to_system SI:", _safe(lambda: _limited(unit.to_system(u.si)))),
              row("to_system CGS:", _safe(lambda: _limited(unit.to_system(u.cgs)))),
              row("Compose:", _safe(lambda: _limited(unit.compose())))]
    for label, system in (("SI", u.si), ("CGS", u.cgs), ("astrophys", u.astrophys)):
        lines.append(row(f"Compose {label}:", _safe(lambda: _limited(unit.compose(units=system)))))
    return "\n".join(lines)


def equivalent_units_table(text: str, include_prefix: bool) -> Table:
    if not (text or "").strip():
        raise ParseError("Enter a unit first.")
    unit = parse_unit(text)
    rows = []
    for cand in unit.find_equivalent_units(include_prefix_units=include_prefix):
        try:
            scale = float(cand.to(unit))
        except Exception:  # noqa: BLE001
            scale = float("nan")
        rows.append((cand.name or str(cand), ", ".join(getattr(cand, "long_names", []) or []),
                     scale, _safe(lambda: cand.physical_type)))
    rows.sort(key=lambda r: (np.isnan(r[2]), r[2]))
    return _table(rows, ["unit", "long names", f"1 unit in [{unit}]", "physical type"],
                  (str, str, float, str))


def search_registry(query: str, include_prefix: bool) -> Table:
    """Units in the current registry whose name/alias/long name contains ``query``."""
    needle = (query or "").strip().casefold()
    if not needle:
        raise ParseError("Enter a search text, e.g. 'parsec' or 'Jy'.")
    reg = u.get_current_unit_registry()
    pool = reg.all_units if include_prefix else reg.non_prefix_units
    rows = []
    for unit in pool:
        names = [unit.name, *getattr(unit, "aliases", []), *getattr(unit, "long_names", [])]
        if not any(needle in str(n).casefold() for n in names):
            continue
        try:
            scale = float(unit.decompose().scale)
        except Exception:  # noqa: BLE001
            scale = float("nan")
        represents = getattr(unit, "represents", None)
        rows.append((unit.name, ", ".join(getattr(unit, "long_names", []) or []),
                     _safe(lambda: unit.physical_type), scale,
                     str(represents) if represents is not None else "(irreducible)"))
    rows.sort(key=lambda r: r[0].casefold())
    return _table(rows, ["unit", "long names", "physical type", "SI scale", "definition"],
                  (str, str, str, float, str))


def prefix_table() -> Table:
    rows = []
    for kind, prefixes, base in (("SI", SI_PREFIXES, "m"), ("binary", BINARY_PREFIXES, "bit")):
        for name, symbol in prefixes:
            try:
                factor = float(u.Unit(symbol + base).to(u.Unit(base)))
            except Exception:  # noqa: BLE001
                factor = float("nan")
            rows.append((kind, name, symbol, factor))
    return _table(rows, ["kind", "prefix", "symbol", "factor"], (str, str, str, float))


def _table(rows: List[tuple], names: List[str], dtypes: tuple) -> Table:
    if not rows:
        return Table(names=names, dtype=dtypes)
    cols = list(zip(*rows))
    return Table([np.array(c, dtype=d) for c, d in zip(cols, dtypes)], names=names)


def define_unit(name: str, expression: str) -> u.UnitBase:
    """Create a custom unit and enable it for the rest of the session."""
    name = (name or "").strip()
    if not _IDENTIFIER.match(name):
        raise ParseError("Unit name must be an identifier (letters, digits, '_').")
    represents = read_quantity(expression, name="definition")
    try:
        unit = u.def_unit(name, represents)
        u.add_enabled_units([unit])
    except ValueError as exc:
        raise ParseError(f"Cannot define {name!r}: {exc}") from exc
    return unit


def calculator_names() -> Dict[str, Any]:
    return {"Quantity": u.Quantity, "Unit": u.Unit, "Magnitude": u.Magnitude,
            "Dex": u.Dex, "Decibel": u.Decibel}


def evaluate_script(text: str, names: Optional[Dict[str, Any]] = None) -> Tuple[str, Any]:
    """Evaluate expression lines (``name = expr`` assigns); returns ``(report, last)``."""
    lines = split_lines(text)
    if not lines:
        raise ParseError("Nothing to evaluate.")
    env = calculator_names()
    env.update(names or {})
    out: List[str] = []
    last: Any = None
    for line in lines:
        target, expr = None, line
        m = _ASSIGNMENT.match(line)
        if m:
            target, expr = m.group(1), m.group(2)
            if target.startswith("_"):
                out.append(f"{line}\n  ! names must not start with '_'")
                continue
        try:
            value = safe_eval(expr, env)
        except ParseError as exc:
            out.append(f"{line}\n  ! {exc}")
            continue
        if target:
            env[target] = value
        last = value
        extra = ""
        if isinstance(value, u.Quantity):
            try:
                extra = f"   [{value.unit.physical_type}]"
            except Exception:  # noqa: BLE001
                pass
        out.append(f"{line}\n  = {format_value(value)}{extra}")
    return "\n".join(out), last


def constants_of(set_name: str) -> Dict[str, Constant]:
    """All constants of a set keyed by attribute name (e.g. ``'G'``, ``'M_sun'``)."""
    if set_name not in CONSTANT_SETS:
        raise ParseError(f"Unknown constants set {set_name!r}.")
    module = importlib.import_module(
        "astropy.constants" if set_name == "astropy default" else f"astropy.constants.{set_name}")
    found = {n: v for n, v in vars(module).items() if isinstance(v, Constant)}
    return dict(sorted(found.items(), key=lambda kv: kv[0].casefold()))


def in_system(const: Constant, system: str) -> Tuple[u.Quantity, str]:
    """``const`` expressed in ``system``; electromagnetic constants stay SI."""
    if system == "cgs":
        try:
            return const.cgs, "cgs"
        except (TypeError, u.UnitsError):
            return const, "si (no cgs form)"
    return const, "si"


def constants_table(set_name: str, system: str, query: str) -> Table:
    needle = (query or "").strip().casefold()
    rows = []
    for key, const in constants_of(set_name).items():
        if needle and not any(needle in str(s).casefold()
                              for s in (key, const.name, const.abbrev, const.reference)):
            continue
        qty, label = in_system(const, system)
        factor = float(const.unit.to(qty.unit))
        value, unc = float(qty.value), float(const.uncertainty) * factor
        rows.append((const.name, const.abbrev or key, value, str(qty.unit), unc,
                     abs(unc / value) if value else 0.0, const.reference or "", label))
    return _table(rows, ["name", "abbrev", "value", "unit", "uncertainty", "rel. uncertainty",
                         "reference", "system"], (str, str, float, str, float, float, str, str))


def constants_namespace(set_name: str, system: str) -> SimpleNamespace:
    """``const`` object for calculator expressions."""
    return SimpleNamespace(**{k: in_system(c, system)[0]
                              for k, c in constants_of(set_name).items()})


# --------------------------------------------------------------------------- #
# Panels
# --------------------------------------------------------------------------- #
class StoringPanel(ModulePanel):
    """Panel that can push its last result into the workspace."""

    default_store_name = "quantity"

    def __init__(self, ws: Workspace) -> None:
        super().__init__(ws)
        self._last: Any = None

    def add_store_controls(self) -> None:
        self.form.add_text("store_name", "Store as", self.default_store_name,
                           "Workspace name for the last result")
        self.add_button("Store result in workspace", self.store_last)

    def store_last(self) -> None:
        def go() -> None:
            if self._last is None:
                raise ParseError("There is no result to store yet.")
            name = self.ws.put(self.form.value("store_name"), self._last)
            self.ws.log(f"Stored {type(self._last).__name__} as {name!r}")
            self.set_status(f"Stored as {name}")
        self.guard(go)


class UnitConverterPanel(StoringPanel):
    default_store_name = "converted"

    def __init__(self, ws: Workspace) -> None:
        super().__init__(ws)
        f = self.form
        f.add_text("value", "Value", "100 km/s",
                   "Quantity: '3.5 km/s', '2*u.pc', or an array such as 'np.linspace(1, 5, 5) * u.m'")
        f.add_text("target", "Convert to", "m/s", "Target unit; empty = only show SI / CGS forms")
        f.add_combo("equivalency", "Equivalency", list(EQUIVALENCY_PARAMS),
                    "Main equivalency (astropy.units.equivalencies)", current="none")
        f.add_text("param1", "Parameter 1", "", "Rest frequency, wavelength, beam, ... (see equivalency)")
        f.add_text("param2", "Parameter 2", "", "Optional second parameter (beam area, T_cmb)")
        f.add_text("extra", "Always-on", "",
                   "Extra parameter-free equivalencies, comma separated "
                   f"({', '.join(PLAIN_EQUIVALENCIES)})")
        self.add_store_controls()
        self.add_button("Convert", self.convert)
        self.out = self.add_output("Result")
        f.fields["equivalency"].currentTextChanged.connect(self._update_tips)
        self._update_tips()

    def _update_tips(self) -> None:
        label1, label2 = EQUIVALENCY_PARAMS[self.form.value("equivalency")]
        self.form.fields["param1"].setToolTip(label1 or "Not used by this equivalency")
        self.form.fields["param2"].setToolTip(label2 or "Not used by this equivalency")

    def convert(self) -> None:
        values = self.form.values()

        def show(res: Tuple[str, u.Quantity]) -> None:
            self.out.show_text(res[0])
            self._last = res[1]

        self.run(lambda: convert_quantity(values), show, busy_text="Converting...")


class UnitExplorerPanel(ModulePanel):
    def __init__(self, ws: Workspace) -> None:
        super().__init__(ws)
        f = self.form
        f.add_text("unit", "Unit", "erg / (s cm2 Angstrom)", "Any unit expression")
        f.add_check("prefixes", "Include prefixed units", False,
                    "Also search/list prefixed units such as km, MHz, uJy")
        f.add_text("query", "Registry search", "parsec", "Substring of a unit name, alias or long name")
        f.add_text("def_name", "New unit name", "", "Identifier for a custom unit, e.g. smoot")
        f.add_text("def_expr", "New unit =", "", "Definition, e.g. 1.7018 m")
        self.add_button("Analyze unit", self.analyze)
        self.add_button("Find equivalent units", self.find_equivalent)
        self.add_button("Search unit registry", self.search)
        self.add_button("List prefixes", self.prefixes)
        self.add_button("Define custom unit", self.define)
        self.out = self.add_output("Analysis")
        self.table = self.add_table("Units")

    def analyze(self) -> None:
        text = self.form.value("unit")
        self.run(lambda: analyze_unit(text), self.out.show_text, busy_text="Analyzing...")

    def _show_table(self, table: Table) -> None:
        self.table.set_table(table)
        self.tabs.setCurrentWidget(self.table)
        self.set_status(f"{len(table)} units")

    def find_equivalent(self) -> None:
        text, prefix = self.form.value("unit"), self.form.value("prefixes")
        self.run(lambda: equivalent_units_table(text, prefix), self._show_table,
                 busy_text="Searching equivalent units...")

    def search(self) -> None:
        text, prefix = self.form.value("query"), self.form.value("prefixes")
        self.run(lambda: search_registry(text, prefix), self._show_table,
                 busy_text="Searching registry...")

    def prefixes(self) -> None:
        self.run(prefix_table, self._show_table)

    def define(self) -> None:
        def go() -> None:
            unit = define_unit(self.form.value("def_name"), self.form.value("def_expr"))
            self.out.show_text(f"Defined {unit.name} = {unit.represents}\n"
                               f"It can now be used in every unit field this session.")
            self.tabs.setCurrentWidget(self.out)
            self.ws.log(f"Custom unit {unit.name!r} defined")
        self.guard(go)


class QuantityCalculatorPanel(StoringPanel):
    default_store_name = "calc"

    def __init__(self, ws: Workspace) -> None:
        super().__init__(ws)
        self.form.add_multiline(
            "script", "Expressions",
            "# one expression per line; 'name = expr' assigns\n"
            "d = 10 * u.pc\nd.to(u.lyr)\n"
            "m = Magnitude(5 * u.mag(u.AB))\nm.to(u.Jy)\n"
            "(1 * u.Msun * const.G / (1 * u.AU)).to(u.km**2 / u.s**2)",
            "Names: u, np, const, Quantity, Magnitude, Dex, Decibel, sqrt, exp, log10, ...",
            height=220)
        self.add_store_controls()
        self.add_button("Evaluate", self.evaluate)
        self.out = self.add_output("Result")

    def evaluate(self) -> None:
        text = self.form.value("script")

        def show(res: Tuple[str, Any]) -> None:
            self.out.show_text(res[0])
            self._last = res[1]

        self.run(lambda: evaluate_script(text), show, busy_text="Evaluating...")


class ConstantsPanel(StoringPanel):
    default_store_name = "constant"

    def __init__(self, ws: Workspace) -> None:
        super().__init__(ws)
        f = self.form
        f.add_combo("set", "Constants set", CONSTANT_SETS,
                    "astropy default = the version astropy.constants currently exposes")
        f.add_combo("system", "System", ["si", "cgs"],
                    "CGS conversion; electromagnetic constants stay SI (esu/emu are ambiguous)")
        f.add_text("filter", "Filter", "", "Substring of name, abbreviation or reference")
        f.add_multiline("script", "Calculator", "const.G * (1 * u.Msun) / (1 * u.AU)**2",
                        "Use const.<abbrev>, e.g. const.c, const.k_B, const.M_sun, and u.<unit>",
                        height=90)
        self.add_store_controls()
        self.add_button("List constants", self.refresh)
        self.add_button("Evaluate", self.evaluate)
        self.table = self.add_table("Constants")
        self.out = self.add_output("Calculator")
        self.refresh()

    def refresh(self) -> None:
        v = self.form.values()
        self.run(lambda: constants_table(v["set"], v["system"], v["filter"]), self._show_table,
                 busy_text="Loading constants...")

    def _show_table(self, table: Table) -> None:
        self.table.set_table(table)
        self.tabs.setCurrentWidget(self.table)

    def evaluate(self) -> None:
        v = self.form.values()

        def work() -> Tuple[str, Any]:
            return evaluate_script(v["script"],
                                   {"const": constants_namespace(v["set"], v["system"])})

        def show(res: Tuple[str, Any]) -> None:
            self.out.show_text(res[0])
            self._last = res[1]
            self.tabs.setCurrentWidget(self.out)

        self.run(work, show, busy_text="Evaluating...")


def _spec(key: str, title: str, cls: type, description: str) -> ModuleSpec:
    def make(ws: Workspace) -> QWidget:
        return cls(ws)
    return ModuleSpec(key, title, CATEGORY, make, description)


SPECS = [
    _spec("unit_converter", "Unit converter", UnitConverterPanel,
          "Convert quantities with astropy equivalencies"),
    _spec("unit_explorer", "Unit explorer", UnitExplorerPanel,
          "Decompose, compose, search and define units"),
    _spec("quantity_calculator", "Quantity calculator", QuantityCalculatorPanel,
          "Evaluate Quantity expressions incl. magnitudes, dex and dB"),
    _spec("constants", "Physical constants", ConstantsPanel,
          "Browse astropy.constants sets and compute with them"),
]
