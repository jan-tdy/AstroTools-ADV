"""Turn user-typed text into astropy/numpy objects.

All GUI input goes through this module so every panel accepts the same syntax
and reports the same errors (:class:`ParseError`).
"""
from __future__ import annotations

import ast
import operator
import re
import types
from typing import Any, Dict, Iterable, List, Optional, Sequence

import numpy as np
from astropy import units as u
from astropy.coordinates import Angle, SkyCoord
from astropy.time import Time


class ParseError(ValueError):
    """Raised for any unparsable user input; the message is safe to show."""


# --------------------------------------------------------------------------- #
# Safe expression evaluation
# --------------------------------------------------------------------------- #
_BIN_OPS = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
    ast.Div: operator.truediv, ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod, ast.Pow: operator.pow, ast.MatMult: operator.matmul,
    ast.BitAnd: operator.and_, ast.BitOr: operator.or_, ast.BitXor: operator.xor,
}
_UNARY_OPS = {ast.UAdd: operator.pos, ast.USub: operator.neg, ast.Invert: operator.invert}
_MAX_POW = 10_000
_MAX_NODES = 2_000
_ALLOWED_MODULE_ROOTS = ("numpy", "astropy")


def default_namespace() -> Dict[str, Any]:
    """Names available inside expressions (``u``, ``np``, ``pi``, ...)."""
    import astropy.constants as const

    return {
        "u": u, "np": np, "const": const, "pi": np.pi, "e": np.e,
        "inf": np.inf, "nan": np.nan, "True": True, "False": False, "None": None,
        "Angle": Angle, "SkyCoord": SkyCoord, "Time": Time,
        "sqrt": np.sqrt, "exp": np.exp, "log": np.log, "log10": np.log10,
        "sin": np.sin, "cos": np.cos, "tan": np.tan, "abs": abs,
        "arange": np.arange, "linspace": np.linspace, "logspace": np.logspace,
        "array": np.array, "zeros": np.zeros, "ones": np.ones,
        "float": float, "int": int, "len": len, "min": min, "max": max,
        "sum": sum, "round": round,
    }


def safe_eval(expr: str, names: Optional[Dict[str, Any]] = None) -> Any:
    """Evaluate a Python *expression* restricted to a whitelisted namespace.

    Supports literals, arithmetic, attribute access (no ``_``-prefixed names),
    calls, indexing, slicing, lists/tuples/dicts and comparisons -- enough for
    ``np.linspace(0, 1, 5) * u.m`` -- but no imports, comprehensions, lambdas
    or dunder access. It is a convenience sandbox for a *local* desktop tool,
    not a security boundary against hostile input.
    """
    if expr is None or not str(expr).strip():
        raise ParseError("Empty expression.")
    ns = default_namespace()
    if names:
        ns.update(names)
    try:
        tree = ast.parse(str(expr).strip(), mode="eval")
    except SyntaxError as exc:
        raise ParseError(f"Syntax error in {expr!r}: {exc.msg}") from None
    if sum(1 for _ in ast.walk(tree)) > _MAX_NODES:
        raise ParseError("Expression is too large.")
    try:
        return _eval(tree.body, ns)
    except ParseError:
        raise
    except Exception as exc:  # noqa: BLE001 - surface astropy/numpy errors cleanly
        raise ParseError(f"Cannot evaluate {expr!r}: {exc}") from exc


def _eval(node: ast.AST, ns: Dict[str, Any]) -> Any:  # noqa: C901 - flat dispatcher
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        if node.id.startswith("_") or node.id not in ns:
            raise ParseError(f"Unknown name {node.id!r}.")
        return ns[node.id]
    if isinstance(node, ast.Attribute):
        if node.attr.startswith("_"):
            raise ParseError(f"Access to {node.attr!r} is not allowed.")
        value = getattr(_eval(node.value, ns), node.attr)
        if isinstance(value, types.ModuleType) and not value.__name__.startswith(
                _ALLOWED_MODULE_ROOTS):
            raise ParseError(f"Access to module {value.__name__!r} is not allowed.")
        return value
    if isinstance(node, ast.BinOp):
        op = _BIN_OPS.get(type(node.op))
        if op is None:
            raise ParseError("Unsupported operator.")
        left, right = _eval(node.left, ns), _eval(node.right, ns)
        if isinstance(node.op, ast.Pow) and np.ndim(right) == 0:
            try:
                if abs(float(getattr(right, "value", right))) > _MAX_POW:
                    raise ParseError("Exponent too large.")
            except TypeError:
                pass
        return op(left, right)
    if isinstance(node, ast.UnaryOp):
        op = _UNARY_OPS.get(type(node.op))
        if op is None:
            raise ParseError("Unsupported unary operator.")
        return op(_eval(node.operand, ns))
    if isinstance(node, ast.Call):
        func = _eval(node.func, ns)
        args = [_eval(a, ns) for a in node.args]
        kwargs = {}
        for kw in node.keywords:
            if kw.arg is None:
                raise ParseError("** arguments are not allowed.")
            kwargs[kw.arg] = _eval(kw.value, ns)
        return func(*args, **kwargs)
    if isinstance(node, (ast.Tuple, ast.List)):
        items = [_eval(e, ns) for e in node.elts]
        return tuple(items) if isinstance(node, ast.Tuple) else items
    if isinstance(node, ast.Dict):
        if any(k is None for k in node.keys):
            raise ParseError("** unpacking is not allowed.")
        return {_eval(k, ns): _eval(v, ns) for k, v in zip(node.keys, node.values)}
    if isinstance(node, ast.Subscript):
        return _eval(node.value, ns)[_eval(node.slice, ns)]
    if isinstance(node, ast.Slice):
        return slice(*(None if p is None else _eval(p, ns)
                       for p in (node.lower, node.upper, node.step)))
    if isinstance(node, ast.Compare):
        left = _eval(node.left, ns)
        cmp_ops = {ast.Lt: operator.lt, ast.LtE: operator.le, ast.Gt: operator.gt,
                   ast.GtE: operator.ge, ast.Eq: operator.eq, ast.NotEq: operator.ne}
        result: Any = True
        for op, comp in zip(node.ops, node.comparators):
            fn = cmp_ops.get(type(op))
            if fn is None:
                raise ParseError("Unsupported comparison.")
            right = _eval(comp, ns)
            result = np.logical_and(result, fn(left, right))  # element-wise for arrays
            left = right
        return bool(result) if np.ndim(result) == 0 else result
    raise ParseError(f"Unsupported syntax: {type(node).__name__}.")


# --------------------------------------------------------------------------- #
# Scalars, arrays, quantities
# --------------------------------------------------------------------------- #
def parse_float(text: str, name: str = "value") -> float:
    try:
        value = float(str(text).strip().replace(",", "."))
    except (TypeError, ValueError):
        raise ParseError(f"{name}: {text!r} is not a number.") from None
    return value


def parse_int(text: str, name: str = "value") -> int:
    try:
        return int(str(text).strip())
    except (TypeError, ValueError):
        raise ParseError(f"{name}: {text!r} is not an integer.") from None


def parse_unit(text: str, name: str = "unit") -> u.UnitBase:
    """Parse ``'km / s'``, ``'Msun'``, ``'mag(AB)'``; empty string is dimensionless."""
    text = (text or "").strip()
    if not text or text.lower() in ("none", "dimensionless"):
        return u.dimensionless_unscaled
    try:
        return u.Unit(text)
    except (ValueError, TypeError) as exc:
        raise ParseError(f"{name}: unknown unit {text!r} ({exc}).") from None


_NUM_UNIT = re.compile(r"^\s*([+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)\s*(.*)$")


def parse_quantity(text: str, default_unit: Optional[Any] = None,
                   name: str = "value") -> u.Quantity:
    """Parse ``'3.5 km/s'``, ``'1e-3 m'``, ``'42'`` (needs ``default_unit``).

    Falls back to :func:`safe_eval` for expressions such as ``'2*u.pc'``.
    """
    text = (text or "").strip()
    if not text:
        raise ParseError(f"{name}: empty value.")
    m = _NUM_UNIT.match(text.replace(",", "."))
    if m:
        number, unit_txt = float(m.group(1)), m.group(2).strip()
        if not unit_txt:
            if default_unit is None:
                raise ParseError(f"{name}: {text!r} needs a unit (e.g. '{text} m').")
            return number * u.Unit(default_unit)
        try:  # 'km/s', 'm**2', 'mag(AB)'; anything else may be an expression
            return number * u.Unit(unit_txt)
        except (ValueError, TypeError):
            pass
    value = safe_eval(text)
    if isinstance(value, u.Quantity):
        return value
    if isinstance(value, (int, float, np.ndarray, list, tuple)) and default_unit is not None:
        return np.asarray(value, dtype=float) * u.Unit(default_unit)
    raise ParseError(f"{name}: {text!r} is not a quantity.")


def parse_float_list(text: str, name: str = "values") -> np.ndarray:
    """Parse numbers separated by commas/whitespace/semicolons/newlines."""
    parts = [p for p in re.split(r"[\s,;]+", (text or "").strip()) if p]
    if not parts:
        raise ParseError(f"{name}: no numbers given.")
    try:
        return np.array([float(p) for p in parts])
    except ValueError as exc:
        raise ParseError(f"{name}: {exc}.") from None


def parse_array(text: str, name: str = "values") -> np.ndarray:
    """Number list *or* expression such as ``linspace(0, 1, 11)``."""
    text = (text or "").strip()
    if not text:
        raise ParseError(f"{name}: empty.")
    try:
        return parse_float_list(text, name)
    except ParseError:
        pass
    value = safe_eval(text)
    arr = np.asarray(value.value if isinstance(value, u.Quantity) else value, dtype=float)
    return arr


# --------------------------------------------------------------------------- #
# Astronomy objects
# --------------------------------------------------------------------------- #
def parse_angle(text: str, default_unit: Any = u.deg, name: str = "angle") -> Angle:
    """Parse ``'10.5'`` (``default_unit``), ``'10h30m'``, ``'-5d12m3s'``, ``'1.2 rad'``."""
    text = (text or "").strip()
    if not text:
        raise ParseError(f"{name}: empty value.")
    try:
        return Angle(text, unit=default_unit)
    except Exception:  # noqa: BLE001
        pass
    try:
        return Angle(text.replace(",", "."), unit=default_unit)
    except Exception as exc:  # noqa: BLE001
        raise ParseError(f"{name}: cannot parse {text!r} as an angle ({exc}).") from None


_NUMERIC_TIME_FORMATS = ("jd", "mjd", "unix", "jyear", "byear", "decimalyear", "gps",
                         "cxcsec", "plot_date")


def parse_time(text: str, fmt: Optional[str] = None, scale: Optional[str] = None,
               name: str = "time") -> Time:
    """Parse ISO strings, ``'now'``, ``'J2000'``-style epochs, JD/MJD (with ``fmt``)."""
    text = (text or "").strip()
    if not text:
        raise ParseError(f"{name}: empty value.")
    kwargs: Dict[str, Any] = {}
    if fmt and fmt != "auto":
        kwargs["format"] = fmt
    if scale and scale != "auto":
        kwargs["scale"] = scale
    try:
        if text.lower() == "now":
            return Time.now()
        if fmt in (None, "auto") and re.fullmatch(r"[JB]\d{4}(\.\d+)?", text):
            return Time(text, format="jyear_str" if text[0] == "J" else "byear_str", **{
                k: v for k, v in kwargs.items() if k != "format"})
        if fmt in _NUMERIC_TIME_FORMATS:
            return Time(float(text.replace(",", ".")), **kwargs)
        return Time(text, **kwargs)
    except Exception as exc:  # noqa: BLE001
        raise ParseError(f"{name}: cannot parse {text!r} ({exc}).") from None


def parse_skycoord(text: str, frame: str = "icrs", unit: Any = None,
                   name: str = "coordinate") -> SkyCoord:
    """Parse ``'10.68 41.27'``, ``'00h42m44s +41d16m09s'`` or a resolvable name.

    Names (``'M31'``) need network access via astropy's Sesame resolver and are
    only tried when the text contains letters that cannot be a sexagesimal.
    """
    text = (text or "").strip()
    if not text:
        raise ParseError(f"{name}: empty value.")
    attempts: List[Exception] = []
    for kwargs in ({"unit": unit} if unit is not None else {"unit": (u.deg, u.deg)},
                   {"unit": (u.hourangle, u.deg)}, {}):
        try:
            return SkyCoord(text.replace(",", " "), frame=frame, **kwargs)
        except Exception as exc:  # noqa: BLE001
            attempts.append(exc)
    if re.search(r"[A-Za-z]{2,}", text) and not re.search(r"\d+\s*[hdms:]", text):
        try:
            return SkyCoord.from_name(text, frame=frame)
        except Exception as exc:  # noqa: BLE001
            raise ParseError(f"{name}: cannot resolve {text!r} ({exc}).") from None
    raise ParseError(f"{name}: cannot parse {text!r} ({attempts[-1]}).")


def split_lines(text: str) -> List[str]:
    """Non-empty, stripped, non-comment lines."""
    return [ln.strip() for ln in (text or "").splitlines()
            if ln.strip() and not ln.strip().startswith("#")]


def format_exception(exc: BaseException) -> str:
    """One readable line for dialogs."""
    msg = str(exc).strip()
    return f"{type(exc).__name__}: {msg}" if msg else type(exc).__name__
