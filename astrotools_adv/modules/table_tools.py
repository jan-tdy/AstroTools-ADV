"""astropy.table tools: open/create, inspect, edit, combine, group, plot, save."""
from __future__ import annotations

import ast
import operator
import warnings
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np
from astropy import units as u
from astropy.coordinates import SkyCoord
from astropy.io import ascii as aascii
from astropy.io import registry
from astropy.table import (
    Column, MaskedColumn, QTable, Row, Table, dstack, hstack, join, setdiff, unique, vstack,
)
from astropy.time import Time
from astropy.utils.masked import Masked
from PyQt5.QtWidgets import (
    QAbstractItemView, QComboBox, QGroupBox, QLineEdit, QListWidget, QPushButton, QStyle,
    QVBoxLayout, QWidget, QFileDialog,
)

from ..core.parsing import (
    ParseError, default_namespace, parse_float, parse_unit, safe_eval,
)
from ..core.registry import ModuleSpec
from ..core.widgets import ModulePanel, ParamForm, WorkspaceCombo
from ..core.workspace import Workspace

CATEGORY = "Data"

# optional dependency needed per I/O format (prefix match on the format name)
OPTIONAL_DEPS = {"hdf5": "h5py", "parquet": "pyarrow", "asdf": "asdf", "pandas": "pandas",
                 "pyarrow": "pyarrow"}


# --------------------------------------------------------------------------- #
# Pure helpers (no Qt) -- also used by the other I/O modules and the tests
# --------------------------------------------------------------------------- #
def module_available(name: str) -> bool:
    import importlib.util
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def check_optional_format(fmt: Optional[str]) -> None:
    """Raise :class:`ParseError` with an install hint if ``fmt`` needs a missing package."""
    for prefix, dep in OPTIONAL_DEPS.items():
        if fmt and (fmt == prefix or fmt.startswith(prefix + ".")) and not module_available(dep):
            raise ParseError(f"Format {fmt!r} needs the optional package {dep!r}, which is not "
                             f"installed (pip install {dep}).")


def capture_warnings(fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Tuple[Any, List[str]]:
    """Call ``fn`` and return ``(result, [warning messages])``."""
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        result = fn(*args, **kwargs)
    return result, [f"{w.category.__name__}: {w.message}" for w in caught]


def parse_kwargs(text: str) -> Dict[str, Any]:
    """Parse ``'hdu=2; delimiter=","; guess=False'`` into a dict (``;``/newline separated)."""
    out: Dict[str, Any] = {}
    for part in (text or "").replace("\n", ";").split(";"):
        part = part.strip()
        if not part:
            continue
        key, sep, raw = part.partition("=")
        key = key.strip()
        if not sep or not key.isidentifier():
            raise ParseError(f"Bad option {part!r}; expected key=value.")
        raw = raw.strip()
        try:
            out[key] = safe_eval(raw)
        except ParseError:
            out[key] = raw
    return out


def split_names(text: str) -> List[str]:
    return [p.strip() for p in (text or "").replace(";", ",").split(",") if p.strip()]


def check_columns(table: Table, names: Sequence[str], what: str = "column") -> List[str]:
    missing = [n for n in names if n not in table.colnames]
    if missing:
        raise ParseError(f"No such {what}(s): {', '.join(missing)}. "
                         f"Available: {', '.join(table.colnames) or '(none)'}")
    return list(names)


def need(text: str, what: str) -> str:
    text = (text or "").strip()
    if not text:
        raise ParseError(f"Please give {what}.")
    return text


def table_formats(write: bool = False) -> List[str]:
    """Names of readable (or writable) Table formats, without deprecated aliases."""
    fmts = registry.get_formats(Table)
    key = "Write" if write else "Read"
    names = sorted({str(r["Format"]) for r in fmts
                    if str(r[key]).strip().lower() == "yes"
                    and str(r["Deprecated"]).strip().lower() != "yes"})
    return names


_TYPED_SUFFIXES = (".fits", ".fit", ".fts", ".fits.gz", ".fz", ".h5", ".hdf5", ".parquet",
                   ".vot", ".xml", ".votable", ".asdf")


def read_table(path: str, fmt: Optional[str] = None, **kwargs: Any) -> Table:
    """Read any table file; unidentifiable text files fall back to guessed ASCII."""
    path = need(path, "a file path")
    fmt = None if fmt in (None, "", "auto") else fmt
    check_optional_format(fmt)
    try:
        return Table.read(path, format=fmt, **kwargs)
    except registry.IORegistryError:
        # unknown extension: try guessed ASCII, but never for files named like a typed format
        if fmt is not None or path.lower().endswith(_TYPED_SUFFIXES):
            raise
        return Table.read(path, format="ascii", **kwargs)


def _numeric_values(col: Any) -> Optional[np.ndarray]:
    """1-D float array (NaN where masked) or ``None`` if not numeric / not 1-D."""
    if isinstance(col, (Time, SkyCoord)):
        return None
    raw = col.value if isinstance(col, u.Quantity) else col
    if hasattr(raw, "filled"):
        try:
            raw = raw.astype(float).filled(np.nan)
        except (TypeError, ValueError):
            return None
    try:
        arr = np.asarray(raw, dtype=float)
    except (TypeError, ValueError):
        return None
    return arr if arr.ndim == 1 else None


def column_values(table: Table, name: str) -> Tuple[np.ndarray, str]:
    """Plot-ready float values and an axis label for ``table[name]``."""
    check_columns(table, [name])
    col = table[name]
    if isinstance(col, Time):
        return np.asarray(col.mjd, dtype=float), f"{name} [MJD]"
    arr = _numeric_values(col)
    if arr is None:
        raise ParseError(f"Column {name!r} is not a numeric 1-D column.")
    unit = getattr(col, "unit", None)
    return arr, f"{name} [{unit}]" if unit not in (None, "") else name


def display_table(table: Optional[Table]) -> Optional[Table]:
    """Copy of ``table`` where SkyCoord/Time/other mixins are turned into strings."""
    if table is None:
        return None
    out = Table(masked=False)
    for name in table.colnames:
        col = table[name]
        if isinstance(col, SkyCoord):
            out[name] = np.asarray(col.to_string("decimal"), dtype=str)
        elif isinstance(col, Time):
            out[name] = np.asarray(col.iso, dtype=str)
        elif isinstance(col, (Column, u.Quantity)):
            out[name] = col
        else:
            out[name] = [str(v) for v in col]
    return out


def column_namespace(table: Table) -> Dict[str, Any]:
    """Names usable in expressions: each column (Quantity when it has a unit) and ``c[...]``."""
    protected = set(default_namespace()) | set(_EXPR_FUNCS) | {"c"}
    cols: Dict[str, Any] = {}
    for name in table.colnames:
        col = table[name]
        if isinstance(col, (Time, SkyCoord, u.Quantity)):
            val = col
        else:
            data = col.filled(np.nan) if isinstance(col, MaskedColumn) and col.dtype.kind == "f" \
                else col.data
            if getattr(data, "dtype", None) is not None and data.dtype.kind == "S":
                data = np.char.decode(data, "utf-8")
            unit = getattr(col, "unit", None)
            val = u.Quantity(data, unit, copy=False) if unit is not None and \
                data.dtype.kind in "fiu" and not isinstance(data, np.ma.MaskedArray) else data
        cols[name] = val
    ns = {k: v for k, v in cols.items() if k.isidentifier() and not k.startswith("_")
          and k not in protected}
    ns["c"] = cols
    return ns


_CMP_FUNCS = {ast.Lt: operator.lt, ast.LtE: operator.le, ast.Gt: operator.gt,
              ast.GtE: operator.ge, ast.Eq: operator.eq, ast.NotEq: operator.ne}
_BIT_FUNCS = {ast.BitAnd: "bit_and", ast.BitOr: "bit_or", ast.BitXor: "bit_xor"}
_BOOL_FUNCS = {ast.And: "bit_and", ast.Or: "bit_or"}
_EXPR_FUNCS: Dict[str, Callable[..., Any]] = {
    **{f"cmp_{f.__name__}": f for f in _CMP_FUNCS.values()},
    "bit_and": np.logical_and, "bit_or": np.logical_or, "bit_xor": np.logical_xor,
    "bit_not": np.logical_not,
}


def _call(name: str, *args: ast.expr) -> ast.Call:
    return ast.Call(ast.Name(name, ast.Load()), list(args), [])


class _ElementwiseLogic(ast.NodeTransformer):
    """Make comparisons and boolean logic element-wise for array operands.

    ``core.parsing.safe_eval`` has no ``& | ^ ~`` and reduces comparisons to a
    single bool, so ``a < b`` becomes ``cmp_lt(a, b)``, ``a < b < c`` becomes
    ``cmp_lt(a, b) & cmp_lt(b, c)``, ``x & y`` / ``x and y`` become
    ``bit_and(x, y)`` and ``~x`` / ``not x`` become ``bit_not(x)``.
    """

    def visit_Compare(self, node: ast.Compare) -> ast.AST:
        self.generic_visit(node)
        if any(type(op) not in _CMP_FUNCS for op in node.ops):
            return node
        calls, left = [], node.left
        for op, right in zip(node.ops, node.comparators):
            calls.append(_call(f"cmp_{_CMP_FUNCS[type(op)].__name__}", left, right))
            left = right
        out = calls[0]
        for call in calls[1:]:
            out = _call("bit_and", out, call)
        return out

    def visit_BinOp(self, node: ast.BinOp) -> ast.AST:
        self.generic_visit(node)
        name = _BIT_FUNCS.get(type(node.op))
        return _call(name, node.left, node.right) if name else node

    def visit_BoolOp(self, node: ast.BoolOp) -> ast.AST:
        self.generic_visit(node)
        out = node.values[0]
        for value in node.values[1:]:
            out = _call(_BOOL_FUNCS[type(node.op)], out, value)
        return out

    def visit_UnaryOp(self, node: ast.UnaryOp) -> ast.AST:
        self.generic_visit(node)
        return _call("bit_not", node.operand) if isinstance(node.op, (ast.Invert, ast.Not)) \
            else node


def _elementwise(expr: str) -> str:
    try:
        tree = ast.parse(expr.strip(), mode="eval")
    except SyntaxError:
        return expr  # let safe_eval report the syntax error
    return ast.unparse(ast.fix_missing_locations(_ElementwiseLogic().visit(tree)))


def eval_on_table(table: Table, expr: str) -> Any:
    """Evaluate ``expr`` with the table's columns as variables (element-wise comparisons)."""
    ns = column_namespace(table)
    ns.update(_EXPR_FUNCS)
    return safe_eval(_elementwise(need(expr, "an expression")), ns)


def _per_row(value: Any, n: int, what: str = "Expression") -> Any:
    """Make ``value`` a length-``n`` array-like (scalars are broadcast)."""
    if isinstance(value, (Time, SkyCoord)):
        if value.isscalar:
            raise ParseError(f"{what} must give one value per row.")
    elif np.ndim(value) == 0:
        if isinstance(value, u.Quantity):
            return np.full(n, value.value) * value.unit
        return np.full(n, value)
    if len(value) != n:
        raise ParseError(f"{what} gives {len(value)} values but the table has {n} rows.")
    return value


def row_mask(table: Table, expr: str) -> np.ndarray:
    value = eval_on_table(table, expr)
    value = _per_row(value, len(table), "Condition")
    mask = np.ma.filled(value, False) if isinstance(value, np.ma.MaskedArray) else value
    mask = np.asarray(getattr(mask, "unmasked", mask))
    if mask.dtype != bool or mask.ndim != 1:
        raise ParseError("Condition must evaluate to one True/False per row.")
    return mask


def _coerce_like(col: Any, text: str) -> Any:
    """Convert user text to the dtype of ``col`` (for lookups / fill values)."""
    kind = getattr(getattr(col, "dtype", None), "kind", "O")
    text = text.strip()
    if kind in "US":
        return text.strip("'\"")
    if kind == "b":
        return text.lower() in ("1", "true", "t", "yes")
    if kind in "iu":
        try:
            return int(text)
        except ValueError:
            return int(parse_float(text))
    return parse_float(text)


# ---- editing operations: each takes a table, returns a NEW table --------------- #
def op_add_column(table: Table, name: str, expr: str, unit: str = "") -> Table:
    name = need(name, "a column name")
    value = _per_row(eval_on_table(table, expr), len(table))
    if unit.strip():
        unit_obj = parse_unit(unit)
        if isinstance(value, u.Quantity):
            value = value.to(unit_obj)
    t = table.copy()
    if name in t.colnames:
        t.replace_column(name, value)
    else:
        t[name] = value
    if unit.strip() and not isinstance(value, u.Quantity) and not isinstance(t[name], u.Quantity):
        t[name].unit = unit_obj
    return t


def op_rename(table: Table, old: str, new: str) -> Table:
    check_columns(table, [old])
    new = need(new, "the new name")
    if new in table.colnames and new != old:
        raise ParseError(f"Column {new!r} already exists.")
    t = table.copy()
    t.rename_column(old, new)
    return t


def op_remove(table: Table, names: str) -> Table:
    cols = check_columns(table, split_names(need(names, "column names")))
    if len(cols) >= len(table.colnames):
        raise ParseError("Refusing to remove every column.")
    t = table.copy()
    t.remove_columns(cols)
    return t


def op_set_meta(table: Table, col: str, unit: str = "", fmt: str = "",
                description: str = "") -> Table:
    """Blank fields are left alone; ``-`` clears the unit/format/description."""
    check_columns(table, [col])
    t = table.copy()
    c = t[col]
    if unit.strip():
        if isinstance(c, u.Quantity):
            raise ParseError("Quantity columns carry their unit; use 'Convert unit' instead.")
        c.unit = None if unit.strip() == "-" else parse_unit(unit)
    if fmt.strip():
        old = c.info.format
        try:
            c.info.format = None if fmt.strip() == "-" else fmt.strip()
            t[col].pformat()
        except (ValueError, TypeError, KeyError) as exc:
            c.info.format = old
            raise ParseError(f"Invalid format {fmt!r}: {exc}") from None
    if description.strip():
        c.info.description = None if description.strip() == "-" else description.strip()
    return t


def op_convert_unit(table: Table, col: str, unit: str) -> Table:
    check_columns(table, [col])
    target = parse_unit(need(unit, "a target unit"))
    t = table.copy()
    c = t[col]
    if getattr(c, "unit", None) is None:
        raise ParseError(f"Column {col!r} has no unit to convert from.")
    try:
        if isinstance(c, u.Quantity):
            t.replace_column(col, c.to(target))
        else:
            c.convert_unit_to(target)
    except u.UnitConversionError as exc:
        raise ParseError(str(exc)) from None
    return t


def op_mask(table: Table, cols: str, expr: str) -> Table:
    names = check_columns(table, split_names(need(cols, "column names")))
    mask = row_mask(table, expr)
    t = table.copy()
    for n in names:
        c = t[n]
        if isinstance(c, u.Quantity):
            t.replace_column(n, Masked(c, mask=mask | np.asarray(getattr(c, "mask", False))))
        elif isinstance(c, (Time, SkyCoord)):
            raise ParseError(f"Cannot mask mixin column {n!r}.")
        else:
            old = np.asarray(c.mask) if isinstance(c, MaskedColumn) else False
            t.replace_column(n, MaskedColumn(c, name=n, mask=mask | old))
    return t


def op_unmask(table: Table, cols: str) -> Table:
    names = check_columns(table, split_names(need(cols, "column names")))
    t = table.copy()
    for n in names:
        c = t[n]
        if isinstance(c, MaskedColumn):
            t.replace_column(n, Column(np.ma.getdata(c), name=n, unit=c.unit, format=c.format,
                                       description=c.description, meta=c.meta))
    return t


def op_fill(table: Table, cols: str, value: str) -> Table:
    names = check_columns(table, split_names(need(cols, "column names")))
    t = table.copy()
    for n in names:
        c = t[n]
        if isinstance(c, MaskedColumn):
            t.replace_column(n, c.filled(_coerce_like(c, need(value, "a fill value"))))
        elif isinstance(c, Masked):
            t.replace_column(n, c.filled(parse_float(value) * c.unit))
        else:
            raise ParseError(f"Column {n!r} has no mask to fill.")
    return t


def op_sort(table: Table, keys: str, reverse: bool = False) -> Table:
    cols = check_columns(table, split_names(need(keys, "sort keys")))
    t = table.copy()
    t.sort(cols, reverse=reverse)
    return t


def op_filter(table: Table, expr: str) -> Table:
    return table[row_mask(table, expr)]


def op_unique(table: Table, keys: str = "", keep: str = "first") -> Table:
    cols = check_columns(table, split_names(keys)) if keys.strip() else None
    return unique(table, keys=cols, keep=keep)


def op_lookup(table: Table, col: str, value: str, add_index: bool = True) -> Table:
    """Rows where ``col == value`` through an astropy table index (``Table.loc``)."""
    check_columns(table, [col])
    t = table.copy()
    t.add_index(col)
    res = t.loc[_coerce_like(t[col], need(value, "a value"))]
    if isinstance(res, Row):
        res = t[[res.index]]
    return Table(res, copy=True)


def op_to_qtable(table: Table, quantity: bool) -> Table:
    return QTable(table) if quantity else Table(table)


def op_skycoord_column(table: Table, name: str, ra: str, dec: str, ra_unit: str = "deg",
                       dec_unit: str = "deg", frame: str = "icrs") -> Table:
    check_columns(table, [ra, dec])
    name = need(name, "a column name")

    def as_q(col_name: str, default: str) -> u.Quantity:
        col = table[col_name]
        if isinstance(col, u.Quantity):
            return col
        arr = _numeric_values(col)
        if arr is None:
            raise ParseError(f"Column {col_name!r} is not numeric.")
        return u.Quantity(arr, getattr(col, "unit", None) or parse_unit(default))

    sc = SkyCoord(as_q(ra, ra_unit), as_q(dec, dec_unit), frame=frame)
    t = table.copy()
    t[name] = sc
    return t


def op_time_column(table: Table, name: str, col: str, fmt: str = "iso",
                   scale: str = "utc") -> Table:
    check_columns(table, [col])
    name = need(name, "a column name")
    c = table[col]
    data = np.asarray(c.data if hasattr(c, "data") else c)
    if data.dtype.kind == "S":
        data = np.char.decode(data, "utf-8")
    try:
        tm = Time(data, format=fmt, scale=scale)
    except Exception as exc:  # noqa: BLE001 - astropy raises several types
        raise ParseError(f"Cannot build Time column: {exc}") from None
    t = table.copy()
    t[name] = tm
    return t


AGGREGATORS: Dict[str, Callable[[Any], Any]] = {
    "mean": np.mean, "sum": np.sum, "min": np.min, "max": np.max, "median": np.median,
    "std": np.std, "count": len, "first": lambda x: x[0], "last": lambda x: x[-1],
}


def op_group_aggregate(table: Table, keys: str, func: str) -> Table:
    cols = check_columns(table, split_names(need(keys, "grouping keys")))
    if func not in AGGREGATORS:
        raise ParseError(f"Unknown aggregation {func!r}.")
    return table.group_by(cols).groups.aggregate(AGGREGATORS[func])


def op_group_sizes(table: Table, keys: str) -> Table:
    cols = check_columns(table, split_names(need(keys, "grouping keys")))
    g = table.group_by(cols)
    out = g.groups.keys.copy()
    out["n_rows"] = np.diff(g.groups.indices)
    return out


def op_join(left: Table, right: Table, keys: str = "", join_type: str = "inner",
            suffixes: str = "_1,_2") -> Table:
    names = split_names(keys)
    if names:
        check_columns(left, names)
        check_columns(right, names)
    elif join_type != "cartesian":
        common = [n for n in left.colnames if n in right.colnames]
        if not common:
            raise ParseError("The tables share no column names; give join keys.")
    sfx = split_names(suffixes)
    if len(sfx) != 2:
        raise ParseError("Suffixes must be two comma-separated strings, e.g. _1,_2")
    return join(left, right, keys=names or None, join_type=join_type, table_names=sfx,
                uniq_col_name="{col_name}{table_name}", metadata_conflicts="silent")


def op_stack(tables: Sequence[Table], how: str, join_type: str = "outer") -> Table:
    if len(tables) < 2:
        raise ParseError("Select at least two tables.")
    fn = {"vstack": vstack, "hstack": hstack, "dstack": dstack}[how]
    return fn(list(tables), join_type=join_type, metadata_conflicts="silent")


def op_setdiff(t1: Table, t2: Table, keys: str = "") -> Table:
    names = split_names(keys)
    if names:
        check_columns(t1, names)
        check_columns(t2, names)
    return setdiff(t1, t2, keys=names or None)


def describe_table(table: Table) -> Table:
    """pandas-like summary of the numeric columns."""
    out = Table()
    out["statistic"] = ["count", "mean", "std", "min", "25%", "50%", "75%", "max"]
    for name in table.colnames:
        arr = _numeric_values(table[name])
        if arr is None:
            continue
        fin = arr[np.isfinite(arr)]
        if fin.size:
            q = np.percentile(fin, [25, 50, 75])
            vals = [float(fin.size), fin.mean(), fin.std(), fin.min(), *q, fin.max()]
        else:
            vals = [0.0] + [np.nan] * 7
        out[name] = vals
    return out


def row_text(table: Table, index: int) -> str:
    if not 0 <= index < len(table):
        raise ParseError(f"Row index {index} out of range (0..{len(table) - 1}).")
    width = max((len(n) for n in table.colnames), default=0)
    lines = []
    for n in table.colnames:
        unit = getattr(table[n], "unit", None)
        lines.append(f"{n:<{width}} = {table[n][index]}" + (f"  [{unit}]" if unit else ""))
    return "\n".join(lines)


def info_text(table: Table, option: str) -> str:
    info = table.info(option, out=None)
    return "\n".join(info.pformat(max_lines=-1, max_width=-1, show_dtype=False)) if info is not None else ""


def plot_table(canvas: Any, table: Table, kind: str, x: str, y: str = "", yerr: str = "",
               bins: int = 30, logx: bool = False, logy: bool = False, title: str = "") -> None:
    """Draw into a :class:`MplCanvas` (GUI thread only)."""
    xv, xlabel = column_values(table, x)
    ax = canvas.axes()
    if kind == "hist":
        data = xv[np.isfinite(xv)]
        if data.size == 0:
            raise ParseError("No finite values to histogram.")
        ax.hist(data, bins=max(1, bins))
        ax.set_xlabel(xlabel)
        ax.set_ylabel("count")
    else:
        yv, ylabel = column_values(table, need(y, "a Y column"))
        if kind == "scatter":
            ax.scatter(xv, yv, s=12)
        elif kind == "line":
            order = np.argsort(xv)
            ax.plot(xv[order], yv[order], marker=".")
        elif kind == "errorbar":
            ev, _ = column_values(table, need(yerr, "an error column"))
            ax.errorbar(xv, yv, yerr=ev, fmt=".")
        else:
            raise ParseError(f"Unknown plot kind {kind!r}.")
        ax.set_xlabel(xlabel)
        ax.set_ylabel(ylabel)
    if logx:
        ax.set_xscale("log")
    if logy:
        ax.set_yscale("log")
    if title:
        ax.set_title(title)
    ax.grid(alpha=0.3)
    canvas.redraw()


# --------------------------------------------------------------------------- #
# Qt helpers
# --------------------------------------------------------------------------- #
class PathEdit(QLineEdit):
    """Line edit with a trailing browse button. ``mode``: 'open' or 'save'."""

    def __init__(self, mode: str = "open", filters: str = "All files (*)",
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.mode, self.filters = mode, filters
        icon = self.style().standardIcon(QStyle.SP_DirOpenIcon)
        act = self.addAction(icon, QLineEdit.TrailingPosition)
        act.setToolTip("Browse...")
        act.triggered.connect(self.browse)

    def browse(self) -> None:
        if self.mode == "save":
            path, _ = QFileDialog.getSaveFileName(self, "Save as", self.text(), self.filters)
        else:
            path, _ = QFileDialog.getOpenFileName(self, "Open", self.text(), self.filters)
        if path:
            self.setText(path)


class ColumnCombo(QComboBox):
    """Combo of the column names of the table chosen in ``table_combo``."""

    NONE = "(none)"

    def __init__(self, ws: Workspace, table_combo: QComboBox, allow_none: bool = False) -> None:
        super().__init__()
        self.ws, self.table_combo, self.allow_none = ws, table_combo, allow_none
        self.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        self.setMinimumContentsLength(10)
        table_combo.currentIndexChanged.connect(self.refresh)
        ws.changed.connect(self.refresh)
        self.refresh()

    def refresh(self, *_: Any) -> None:
        current = self.currentText()
        self.blockSignals(True)
        self.clear()
        if self.allow_none:
            self.addItem(self.NONE)
        name = self.table_combo.currentText()
        if name and name in self.ws:
            obj = self.ws.get(name)
            if isinstance(obj, Table):
                self.addItems(obj.colnames)
        idx = self.findText(current)
        if idx >= 0:
            self.setCurrentIndex(idx)
        self.blockSignals(False)

    def column(self) -> str:
        text = self.currentText()
        return "" if text == self.NONE else text


class TablePicker(QListWidget):
    """Multi-selection list of workspace tables (selection order = list order)."""

    def __init__(self, ws: Workspace) -> None:
        super().__init__()
        self.ws = ws
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setMaximumHeight(110)
        ws.changed.connect(self.refresh)
        self.refresh()

    def refresh(self) -> None:
        chosen = set(self.selected_names())
        self.clear()
        self.addItems(self.ws.names(Table))
        for i in range(self.count()):
            if self.item(i).text() in chosen:
                self.item(i).setSelected(True)

    def selected_names(self) -> List[str]:
        return [self.item(i).text() for i in range(self.count()) if self.item(i).isSelected()]

    def selected_tables(self) -> List[Table]:
        return [self.ws.get(n) for n in self.selected_names()]


class Section(QGroupBox):
    """Titled group with its own form and error-guarded buttons."""

    def __init__(self, panel: ModulePanel, title: str) -> None:
        super().__init__(title)
        self.panel = panel
        lay = QVBoxLayout(self)
        self.form = ParamForm()
        lay.addWidget(self.form)
        self.btns = QVBoxLayout()
        lay.addLayout(self.btns)
        panel.controls_layout.insertWidget(panel.controls_layout.count() - 1, self)

    def add_button(self, text: str, slot: Callable[[], None], tip: str = "") -> QPushButton:
        btn = QPushButton(text)
        btn.setToolTip(tip)
        btn.clicked.connect(lambda _c=False: self.panel.guard(slot))
        self.btns.addWidget(btn)
        return btn


class TablePanel(ModulePanel):
    """Base: a source-table picker, output-name field and Table/Info result tabs."""

    def __init__(self, ws: Workspace, with_source: bool = True) -> None:
        super().__init__(ws)
        self.src = WorkspaceCombo(ws, Table)
        if with_source:
            self.form.add_widget("table", "Table", self.src)
        self.form.add_text("out", "Output name", tip="Workspace name for the result. "
                           "Blank: keep the source name (or '<source>_result').")
        self.view = self.add_table("Table")
        self.info = self.add_output("Info")
        self.src.currentIndexChanged.connect(lambda _i=0: self.show_current())

    def table(self) -> Table:
        return self.src.selected()

    def show_current(self) -> None:
        name = self.src.currentText()
        self.view.set_table(display_table(self.ws.get(name)) if name in self.ws else None)

    def out_name(self, default: str) -> str:
        return self.form.value("out") or default

    def publish(self, name: str, table: Table, note: str = "") -> None:
        name = self.ws.put(name, table)
        self.src.refresh()
        self.src.setCurrentIndex(max(0, self.src.findText(name)))
        self.view.set_table(display_table(table))
        self.info.show_text(note or f"Stored table {name!r}: {len(table)} rows x "
                            f"{len(table.colnames)} columns")
        self.tabs.setCurrentWidget(self.view)
        self.ws.log(f"table {name!r}: {len(table)} rows, {len(table.colnames)} columns")
        self.set_status(f"Table {name!r} ready")

    def run_op(self, fn: Callable[[], Table], name: str) -> None:
        """Run a table-producing function in the background and publish it as ``name``."""
        def done(res: Tuple[Table, List[str]]) -> None:
            table, warns = res
            note = f"Stored table {name!r}: {len(table)} rows x {len(table.colnames)} columns"
            if warns:
                note += "\n\nWarnings:\n" + "\n".join(sorted(set(warns)))
            self.publish(name, table, note)

        self.run(lambda: capture_warnings(fn), done)


# --------------------------------------------------------------------------- #
# Panel 1: open / create / inspect / save
# --------------------------------------------------------------------------- #
class TableManager(TablePanel):
    def __init__(self, ws: Workspace) -> None:
        super().__init__(ws)
        # -- open
        sec = Section(self, "Open table")
        self.open_path = PathEdit("open")
        sec.form.add_widget("path", "File", self.open_path)
        sec.form.add_combo("fmt", "Format", ["auto"] + table_formats(), editable=False,
                           tip="'auto' identifies the format from the file; plain text "
                               "files fall back to guessed ASCII.")
        sec.form.add_text("opts", "Options", tip="key=value; key=value  (e.g. hdu=2; "
                          "delimiter=','; path='data' for HDF5)")
        sec.form.add_text("name", "Store as", "table1")
        sec.add_button("Open", lambda: self.open_file(sec.form))
        self.open_sec = sec
        # -- paste
        sec = Section(self, "Create from pasted text")
        sec.form.add_multiline("text", "Text", "a,b\n1,2\n3,4", height=100,
                               tip="CSV or any text astropy.io.ascii can guess")
        sec.form.add_text("name", "Store as", "pasted")
        sec.add_button("Create", lambda: self.create_text(sec.form))
        # -- inspect
        sec = Section(self, "Inspect selected table")
        sec.form.add_int("row", "Row", 0, 0, 10**9)
        sec.add_button("Column info", lambda: self.show_info("attributes"))
        sec.add_button("Column statistics (info)", lambda: self.show_info("stats"))
        sec.add_button("Describe", self.show_describe)
        sec.add_button("Formatted text (pformat)", self.show_pformat)
        sec.add_button("Row detail", lambda: self.show_row(sec.form))
        sec.add_button("Table metadata", self.show_meta)
        # -- pandas
        sec = Section(self, "pandas")
        sec.form.add_text("name", "Store as", "dataframe")
        sec.add_button("Table -> pandas DataFrame", lambda: self.to_pandas(sec.form))
        sec.add_button("Workspace DataFrame -> Table", lambda: self.from_pandas(sec.form))
        # -- save
        sec = Section(self, "Save selected table")
        self.save_path = PathEdit("save")
        sec.form.add_widget("path", "File", self.save_path)
        sec.form.add_combo("fmt", "Format", ["auto"] + table_formats(write=True),
                           tip="'auto' picks the format from the file extension")
        sec.form.add_text("opts", "Options", tip="key=value; key=value (e.g. path='t' for HDF5)")
        sec.form.add_check("overwrite", "Overwrite", False)
        sec.add_button("Save", lambda: self.save_file(sec.form))

    # ---- open / create ------------------------------------------------------- #
    def open_file(self, form: ParamForm) -> None:
        path, fmt, name = form.value("path"), form.value("fmt"), need(form.value("name"),
                                                                       "a workspace name")
        kwargs = parse_kwargs(form.value("opts"))
        self.run(lambda: capture_warnings(read_table, path, fmt, **kwargs),
                 lambda res: self._opened(name, res), busy_text=f"Reading {path}...")

    def _opened(self, name: str, res: Tuple[Table, List[str]]) -> None:
        table, warns = res
        note = f"Read {len(table)} rows x {len(table.colnames)} columns"
        if warns:
            note += "\n\nWarnings:\n" + "\n".join(sorted(set(warns)))
        self.publish(name, table, note)

    def create_text(self, form: ParamForm) -> None:
        text, name = need(form.value("text"), "some text"), need(form.value("name"),
                                                                  "a workspace name")
        self.run(lambda: capture_warnings(aascii.read, text),
                 lambda res: self._opened(name, res))

    # ---- inspect ---------------------------------------------------------------- #
    def _show_text(self, text: str) -> None:
        self.info.show_text(text)
        self.tabs.setCurrentWidget(self.info)

    def show_info(self, option: str) -> None:
        t = self.table()
        self.run(lambda: info_text(t, option), self._show_text)

    def show_describe(self) -> None:
        t = self.table()
        self.run(lambda: describe_table(t), self._show_described)

    def _show_described(self, d: Table) -> None:
        self.view.set_table(d)
        self.info.show_text("\n".join(d.pformat(max_lines=-1, max_width=-1)))
        self.tabs.setCurrentWidget(self.view)

    def show_pformat(self) -> None:
        t = self.table()
        self.run(lambda: "\n".join(t.pformat(max_lines=-1, show_unit=True, show_dtype=True, max_width=-1)),
                 self._show_text)

    def show_row(self, form: ParamForm) -> None:
        self._show_text(row_text(self.table(), form.value("row")))

    def show_meta(self) -> None:
        t = self.table()
        lines = [f"{k}: {v!r}" for k, v in t.meta.items()] or ["(no metadata)"]
        self._show_text("\n".join(lines))

    # ---- pandas -------------------------------------------------------------- #
    def to_pandas(self, form: ParamForm) -> None:
        if not module_available("pandas"):
            raise ParseError("pandas is not installed (pip install pandas).")
        t, name = self.table(), need(form.value("name"), "a workspace name")
        df = t.to_pandas()
        self.ws.put(name, df)
        self._show_text(f"Stored DataFrame {name!r}\n\n{df.head(30)}\n\n{df.dtypes}")

    def from_pandas(self, form: ParamForm) -> None:
        if not module_available("pandas"):
            raise ParseError("pandas is not installed (pip install pandas).")
        import pandas as pd
        names = [n for n in self.ws.names() if isinstance(self.ws.get(n), pd.DataFrame)]
        name = need(form.value("name"), "the DataFrame's workspace name")
        if name not in names:
            raise ParseError(f"No DataFrame named {name!r} in the workspace "
                             f"(have: {', '.join(names) or 'none'}).")
        out = self.out_name(name + "_table")
        self.publish(out, Table.from_pandas(self.ws.get(name)))

    # ---- save ---------------------------------------------------------------- #
    def save_file(self, form: ParamForm) -> None:
        t = self.table()
        path, fmt = need(form.value("path"), "an output path"), form.value("fmt")
        fmt = None if fmt == "auto" else fmt
        check_optional_format(fmt)
        kwargs = parse_kwargs(form.value("opts"))
        overwrite = form.value("overwrite")

        def work() -> str:
            _, warns = capture_warnings(t.write, path, format=fmt, overwrite=overwrite, **kwargs)
            return path + ("\n" + "\n".join(sorted(set(warns))) if warns else "")

        self.run(work, lambda p: self._show_text(f"Saved {p}"), busy_text=f"Writing {path}...")


# --------------------------------------------------------------------------- #
# Panel 2: editing
# --------------------------------------------------------------------------- #
class TableEditor(TablePanel):
    def __init__(self, ws: Workspace) -> None:
        super().__init__(ws)
        self.cols = ColumnCombo(ws, self.src)
        self.form.add_widget("col", "Column", self.cols)
        self.info.show_text(
            "Expressions use column names as variables (Quantity if the column has a unit), "
            "`c['odd name']` for other names, plus u, np, const, sqrt, log10, ...\n"
            "Examples:  a * 2 + 1      flux / flux.max()      (a > 3) & (b < 2)\n"
            "Boolean logic: & | ~ (or and / or / not) work element-wise.")

        sec = Section(self, "New / replaced column")
        sec.form.add_text("name", "Column name")
        sec.form.add_text("expr", "Expression", tip="e.g. a * u.m, sqrt(x**2 + y**2)")
        sec.form.add_text("unit", "Unit", tip="optional; converts a Quantity result, or "
                          "declares the unit of a plain result")
        sec.add_button("Add / replace column", lambda: self.add_column(sec.form))

        sec = Section(self, "Selected column")
        sec.form.add_text("new", "New name")
        sec.form.add_text("unit", "Unit", tip="Set unit ('-' clears)")
        sec.form.add_text("fmt", "Format", tip="e.g. %.3f or {:.3e} ('-' clears)")
        sec.form.add_text("desc", "Description", tip="'-' clears")
        sec.form.add_text("to", "Convert to unit", tip="e.g. km/s")
        sec.form.add_text("rm", "Remove columns", tip="comma-separated; blank = selected column")
        sec.add_button("Rename", lambda: self.rename(sec.form))
        sec.add_button("Set unit / format / description", lambda: self.set_meta(sec.form))
        sec.add_button("Convert unit", lambda: self.convert(sec.form))
        sec.add_button("Remove column(s)", lambda: self.remove(sec.form))

        sec = Section(self, "Masks")
        sec.form.add_text("cols", "Columns", tip="comma-separated; blank = selected column")
        sec.form.add_text("expr", "Mask where", tip="boolean expression, e.g. a < 0")
        sec.form.add_text("fill", "Fill value")
        sec.add_button("Mask rows", lambda: self.mask_rows(sec.form))
        sec.add_button("Unmask", lambda: self.unmask(sec.form))
        sec.add_button("Fill masked values", lambda: self.fill(sec.form))

        sec = Section(self, "Rows")
        sec.form.add_text("keys", "Keys", tip="comma-separated column names")
        sec.form.add_check("reverse", "Reverse sort")
        sec.form.add_combo("keep", "Unique: keep", ["first", "last", "none"])
        sec.form.add_text("expr", "Filter where", tip="boolean expression, e.g. (a > 3) & (b < 9)")
        sec.form.add_text("value", "Lookup value", tip="Rows where the selected column equals "
                          "this value (uses an astropy table index, Table.loc)")
        sec.add_button("Sort", lambda: self.sort(sec.form))
        sec.add_button("Filter rows", lambda: self.filter(sec.form))
        sec.add_button("Unique rows", lambda: self.unique(sec.form))
        sec.add_button("Lookup via index (loc)", lambda: self.lookup(sec.form))

        sec = Section(self, "Column types")
        sec.form.add_text("name", "New column", "coord")
        sec.form.add_text("ra", "RA column")
        sec.form.add_text("dec", "Dec column")
        sec.form.add_combo("ra_unit", "RA unit", ["deg", "hourangle", "rad"])
        sec.form.add_combo("frame", "Frame", ["icrs", "fk5", "galactic"])
        sec.form.add_combo("tfmt", "Time format", ["iso", "isot", "jd", "mjd", "unix", "jyear",
                                                  "decimalyear", "fits"])
        sec.form.add_combo("tscale", "Time scale", ["utc", "tai", "tt", "tdb", "ut1"])
        sec.add_button("Table <-> QTable", lambda: self.toggle_qtable())
        sec.add_button("Make SkyCoord column (RA/Dec)", lambda: self.skycoord(sec.form))
        sec.add_button("Make Time column from selected", lambda: self.timecol(sec.form))

    # helpers
    def _col(self) -> str:
        return need(self.cols.currentText(), "a column (select a table first)")

    def _go(self, fn: Callable[[Table], Table], suffix: str = "") -> None:
        src = self.src.currentText()
        t = self.table()
        self.run_op(lambda: fn(t), self.out_name(src + suffix))

    def add_column(self, f: ParamForm) -> None:
        name, expr, unit = f.value("name"), f.value("expr"), f.value("unit")
        self._go(lambda t: op_add_column(t, name, expr, unit))

    def rename(self, f: ParamForm) -> None:
        col, new = self._col(), f.value("new")
        self._go(lambda t: op_rename(t, col, new))

    def set_meta(self, f: ParamForm) -> None:
        col, u_, fm, d = self._col(), f.value("unit"), f.value("fmt"), f.value("desc")
        self._go(lambda t: op_set_meta(t, col, u_, fm, d))

    def convert(self, f: ParamForm) -> None:
        col, to = self._col(), f.value("to")
        self._go(lambda t: op_convert_unit(t, col, to))

    def remove(self, f: ParamForm) -> None:
        names = f.value("rm") or self._col()
        self._go(lambda t: op_remove(t, names))

    def _cols_or_selected(self, f: ParamForm) -> str:
        return f.value("cols") or self._col()

    def mask_rows(self, f: ParamForm) -> None:
        cols, expr = self._cols_or_selected(f), f.value("expr")
        self._go(lambda t: op_mask(t, cols, expr))

    def unmask(self, f: ParamForm) -> None:
        cols = self._cols_or_selected(f)
        self._go(lambda t: op_unmask(t, cols))

    def fill(self, f: ParamForm) -> None:
        cols, value = self._cols_or_selected(f), f.value("fill")
        self._go(lambda t: op_fill(t, cols, value))

    def sort(self, f: ParamForm) -> None:
        keys, rev = f.value("keys") or self._col(), f.value("reverse")
        self._go(lambda t: op_sort(t, keys, rev))

    def filter(self, f: ParamForm) -> None:
        expr = f.value("expr")
        self._go(lambda t: op_filter(t, expr), "_filtered")

    def unique(self, f: ParamForm) -> None:
        keys, keep = f.value("keys"), f.value("keep")
        self._go(lambda t: op_unique(t, keys, keep), "_unique")

    def lookup(self, f: ParamForm) -> None:
        col, val = self._col(), f.value("value")
        self._go(lambda t: op_lookup(t, col, val), "_lookup")

    def toggle_qtable(self) -> None:
        is_q = isinstance(self.table(), QTable)
        self._go(lambda t: op_to_qtable(t, not is_q))

    def skycoord(self, f: ParamForm) -> None:
        name, ra, dec = f.value("name"), f.value("ra"), f.value("dec")
        ru, frame = f.value("ra_unit"), f.value("frame")
        self._go(lambda t: op_skycoord_column(t, name, ra, dec, ru, "deg", frame))

    def timecol(self, f: ParamForm) -> None:
        name, col, fmt, scale = f.value("name"), self._col(), f.value("tfmt"), f.value("tscale")
        self._go(lambda t: op_time_column(t, name, col, fmt, scale))


# --------------------------------------------------------------------------- #
# Panel 3: group / join / stack
# --------------------------------------------------------------------------- #
class TableCombiner(TablePanel):
    def __init__(self, ws: Workspace) -> None:
        super().__init__(ws)
        sec = Section(self, "Group by")
        sec.form.add_text("keys", "Keys", tip="comma-separated column names")
        sec.form.add_combo("func", "Aggregate", list(AGGREGATORS))
        sec.add_button("Aggregate groups", lambda: self.aggregate(sec.form),
                       "Non-numeric columns are dropped (reported as warnings)")
        sec.add_button("Group sizes", lambda: self.sizes(sec.form))

        sec = Section(self, "Join (selected table = left)")
        self.right = WorkspaceCombo(ws, Table)
        sec.form.add_widget("right", "Right table", self.right)
        sec.form.add_text("keys", "Keys", tip="blank = all common column names")
        sec.form.add_combo("how", "Join type", ["inner", "outer", "left", "right", "cartesian"])
        sec.form.add_text("sfx", "Suffixes", "_1,_2", tip="for clashing column names")
        sec.add_button("Join", lambda: self.join(sec.form))
        sec.add_button("Set difference (left - right)", lambda: self.setdiff(sec.form))

        sec = Section(self, "Stack (select tables below)")
        self.picker = TablePicker(ws)
        sec.form.add_widget("tables", "Tables", self.picker)
        sec.form.add_combo("how", "Join type", ["outer", "inner", "exact"],
                           tip="'exact' requires identical columns / row counts")
        sec.add_button("vstack (append rows)", lambda: self.stack(sec.form, "vstack"))
        sec.add_button("hstack (side by side)", lambda: self.stack(sec.form, "hstack"))
        sec.add_button("dstack (new axis)", lambda: self.stack(sec.form, "dstack"))

    def _go(self, fn: Callable[[Table], Table], suffix: str) -> None:
        t = self.table()
        self.run_op(lambda: fn(t), self.out_name(self.src.currentText() + suffix))

    def aggregate(self, f: ParamForm) -> None:
        keys, func = f.value("keys"), f.value("func")
        self._go(lambda t: op_group_aggregate(t, keys, func), "_grouped")

    def sizes(self, f: ParamForm) -> None:
        keys = f.value("keys")
        self._go(lambda t: op_group_sizes(t, keys), "_sizes")

    def join(self, f: ParamForm) -> None:
        right = self.right.selected()
        keys, how, sfx = f.value("keys"), f.value("how"), f.value("sfx")
        name = self.out_name(f"{self.src.currentText()}_{self.right.currentText()}_{how}")
        left = self.table()
        self.run_op(lambda: op_join(left, right, keys, how, sfx), name)

    def setdiff(self, f: ParamForm) -> None:
        right, keys = self.right.selected(), f.value("keys")
        left = self.table()
        self.run_op(lambda: op_setdiff(left, right, keys),
                    self.out_name(self.src.currentText() + "_diff"))

    def stack(self, f: ParamForm, how: str) -> None:
        tables, jt = self.picker.selected_tables(), f.value("how")
        self.run_op(lambda: op_stack(tables, how, jt), self.out_name(f"{how}_result"))


# --------------------------------------------------------------------------- #
# Panel 4: plotting
# --------------------------------------------------------------------------- #
class TablePlotter(TablePanel):
    def __init__(self, ws: Workspace) -> None:
        super().__init__(ws)
        self.canvas = self.add_plot("Plot")
        self.x = ColumnCombo(ws, self.src)
        self.y = ColumnCombo(ws, self.src, allow_none=True)
        self.err = ColumnCombo(ws, self.src, allow_none=True)
        self.form.add_combo("kind", "Kind", ["scatter", "line", "errorbar", "hist"])
        self.form.add_widget("x", "X column", self.x)
        self.form.add_widget("y", "Y column", self.y)
        self.form.add_widget("err", "Y error column", self.err)
        self.form.add_int("bins", "Histogram bins", 30, 1, 100000)
        self.form.add_check("logx", "Log X")
        self.form.add_check("logy", "Log Y")
        self.form.add_text("title", "Title")
        self.add_button("Plot", lambda: self.guard(self.plot))
        self.add_button("Save figure...", lambda: self.guard(self.save_fig))
        self.tabs.setCurrentWidget(self.canvas)

    def plot(self) -> None:
        f = self.form
        plot_table(self.canvas, self.table(), f.value("kind"), self.x.column(), self.y.column(),
                   self.err.column(), f.value("bins"), f.value("logx"), f.value("logy"),
                   f.value("title"))
        self.tabs.setCurrentWidget(self.canvas)

    def save_fig(self) -> None:
        path = self.ask_save_path("Save figure", "PNG (*.png);;PDF (*.pdf);;SVG (*.svg)")
        if path:
            self.canvas.save(path)


SPECS = [
    ModuleSpec("table_manager", "Tables: Open / Inspect / Save", CATEGORY,
               lambda ws: TableManager(ws), "Open, create, inspect and save astropy Tables"),
    ModuleSpec("table_edit", "Tables: Edit", CATEGORY, lambda ws: TableEditor(ws),
               "Columns, units, masks, sorting, filtering, indices, QTable, SkyCoord/Time columns"),
    ModuleSpec("table_combine", "Tables: Group / Join / Stack", CATEGORY,
               lambda ws: TableCombiner(ws), "group_by, join, vstack, hstack, dstack, setdiff"),
    ModuleSpec("table_plot", "Tables: Plot", CATEGORY, lambda ws: TablePlotter(ws),
               "Scatter, line, error-bar and histogram plots of table columns"),
]
