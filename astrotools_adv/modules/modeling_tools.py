"""astropy.modeling: model browser/builder, 1-D and 2-D fitting, splines and polynomials."""
from __future__ import annotations

import ast
import inspect
import keyword
import warnings
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
from astropy import units as u
from astropy.modeling import Model, custom_model, fitting, models
from astropy.modeling.spline import Spline1D
from astropy.stats import (
    akaike_info_criterion_lsq, bayesian_info_criterion_lsq, sigma_clip,
)
from astropy.table import Table
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QComboBox, QLineEdit, QTableWidget, QTableWidgetItem

from ..core.parsing import ParseError, parse_float, safe_eval
from ..core.registry import ModuleSpec
from ..core.widgets import ModulePanel, WorkspaceCombo
from ..core.workspace import Workspace
from .stats_tools import IMAGE_TYPES, DataInput, fmt, image_from_object, plain_values

CATEGORY = "Analysis"

# --------------------------------------------------------------------------- #
# Model catalogue and expression parsing
# --------------------------------------------------------------------------- #
_BASE_CLASSES = {
    "OrthoPolynomialBase", "PolynomialModel", "Projection", "Pix2SkyProjection",
    "Sky2PixProjection", "Zenithal", "Cylindrical", "PseudoConic", "PseudoCylindrical",
    "QuadCube", "Conic",
}


def model_catalog() -> Dict[str, type]:
    """Every concrete model class exported by ``astropy.modeling.models``, by name."""
    out: Dict[str, type] = {}
    for name in dir(models):
        cls = getattr(models, name)
        if (inspect.isclass(cls) and issubclass(cls, Model) and name[0].isupper()
                and name not in _BASE_CLASSES and not inspect.isabstract(cls)):
            out[name] = cls
    return out


def model_group(cls: type) -> str:
    """Sidebar group for a model class."""
    name = cls.__name__
    if name.startswith(("Pix2Sky", "Sky2Pix")) or cls.__module__.endswith("projections"):
        return "Projections"
    try:
        n_in, n_out = int(cls.n_inputs), int(cls.n_outputs)
    except (TypeError, ValueError):
        return "Mappings / other"
    if n_in == 1 and n_out == 1:
        return "1D"
    if n_in == 2 and n_out == 1:
        return "2D"
    return "Mappings / other"


def required_args(cls: type) -> List[str]:
    sig = inspect.signature(cls.__init__)
    return [p.name for p in sig.parameters.values()
            if p.name != "self" and p.default is p.empty
            and p.kind in (p.POSITIONAL_OR_KEYWORD, p.POSITIONAL_ONLY)]


class _PipeJoin(ast.NodeTransformer):
    """Rewrite ``a | b`` and ``a & b`` into ``pipe(a, b)`` / ``join(a, b)`` calls."""

    def visit_BinOp(self, node: ast.BinOp) -> ast.AST:
        self.generic_visit(node)
        if isinstance(node.op, (ast.BitOr, ast.BitAnd)):
            fn = "pipe" if isinstance(node.op, ast.BitOr) else "join"
            return ast.copy_location(ast.Call(func=ast.Name(id=fn, ctx=ast.Load()),
                                              args=[node.left, node.right], keywords=[]), node)
        return node


def model_namespace(ws: Optional[Workspace] = None) -> Dict[str, Any]:
    """Names usable in model expressions: all model classes + stored workspace models."""
    ns: Dict[str, Any] = dict(model_catalog())
    ns.update({"models": models, "pipe": lambda a, b: a | b, "join": lambda a, b: a & b})
    if ws is not None:
        for name in ws.names(Model):
            if name.isidentifier() and not name.startswith("_") and name not in ns:
                ns[name] = ws.get(name).copy()
    return ns


def parse_model(expr: str, ws: Optional[Workspace] = None) -> Model:
    """Evaluate a model expression such as ``Gaussian1D(1, 0, 1) + Const1D(0.1)``."""
    expr = (expr or "").strip()
    if not expr:
        raise ParseError("Enter a model expression, e.g. Gaussian1D(1, 0, 1).")
    try:
        tree = _PipeJoin().visit(ast.parse(expr, mode="eval"))
        text = ast.unparse(ast.fix_missing_locations(tree))
    except SyntaxError as exc:
        raise ParseError(f"Syntax error in model expression: {exc.msg}") from None
    value = safe_eval(text, model_namespace(ws))
    if inspect.isclass(value) and issubclass(value, Model):
        try:
            value = value()
        except TypeError:
            raise ParseError(f"{value.__name__} needs arguments: "
                             f"{', '.join(required_args(value))}.") from None
    if not isinstance(value, Model):
        raise ParseError("The expression did not produce a model.")
    return value


def make_custom_model(name: str, expression: str, params_text: str, n_inputs: int = 1) -> Model:
    """Instantiate a fittable model from a formula, e.g. ``a*sin(b*x)+c`` with ``a=1, b=2, c=0``."""
    name = (name or "").strip()
    if not name.isidentifier() or keyword.iskeyword(name):
        raise ParseError(f"{name!r} is not a valid model name.")
    if n_inputs not in (1, 2):
        raise ParseError("Custom models support 1 or 2 inputs.")
    inputs = ["x", "y"][:n_inputs]
    pairs: List[Tuple[str, float]] = []
    for item in [s for s in params_text.replace(";", ",").split(",") if s.strip()]:
        key, sep, val = item.partition("=")
        key = key.strip()
        if not sep or not key.isidentifier() or keyword.iskeyword(key) or key.startswith("_"):
            raise ParseError(f"Bad parameter definition {item.strip()!r}; use name=value.")
        if key in inputs or key in dict(pairs):
            raise ParseError(f"Parameter name {key!r} is duplicated or clashes with an input.")
        pairs.append((key, parse_float(val, key)))
    if not pairs:
        raise ParseError("Define at least one parameter, e.g. a=1, b=2.")
    expression = (expression or "").strip()
    if not expression:
        raise ParseError("Enter a formula in terms of " + ", ".join(inputs + [k for k, _ in pairs]) + ".")
    P = inspect.Parameter
    sig = inspect.Signature([P(i, P.POSITIONAL_OR_KEYWORD) for i in inputs]
                            + [P(k, P.POSITIONAL_OR_KEYWORD, default=v) for k, v in pairs])

    def func(*args, **kwargs):  # no annotations: astropy would treat them as input units
        bound = sig.bind(*args, **kwargs)
        bound.apply_defaults()
        return safe_eval(expression, dict(bound.arguments))

    func.__signature__ = sig  # type: ignore[attr-defined]
    func.__name__ = name
    probe = {i: np.array([0.5, 1.0, 1.5]) for i in inputs}
    probe.update(dict(pairs))
    out = safe_eval(expression, probe)  # fail early with a readable error
    if np.shape(out) not in ((3,), ()):
        raise ParseError("The formula must return one value per input point.")
    return custom_model(func)()


# --------------------------------------------------------------------------- #
# Describing models
# --------------------------------------------------------------------------- #
def param_rows(model: Model) -> List[Dict[str, Any]]:
    rows = []
    for name in model.param_names:
        p = getattr(model, name)
        lo, hi = p.bounds
        rows.append({"name": name, "value": float(np.asarray(p.value).reshape(-1)[0]),
                     "unit": str(p.unit) if p.unit is not None else "",
                     "fixed": bool(p.fixed), "min": lo, "max": hi,
                     "tied": "yes" if p.tied else ""})
    return rows


def model_to_dict(model: Model) -> Dict[str, Any]:
    """JSON-friendly description (class, name, parameters with constraints)."""
    return {
        "class": type(model).__name__, "name": model.name, "n_inputs": model.n_inputs,
        "n_outputs": model.n_outputs, "n_submodels": model.n_submodels,
        "parameters": {r["name"]: {k: r[k] for k in ("value", "unit", "fixed", "min", "max")}
                       for r in param_rows(model)},
    }


def describe_model(model: Model) -> str:
    lines = [f"{type(model).__name__}   name={model.name!r}",
             f"inputs={model.inputs}  outputs={model.outputs}  submodels={model.n_submodels}",
             f"fittable={model.fittable}  linear={getattr(model, 'linear', False)}", ""]
    rows = param_rows(model)
    if rows:
        lines.append(f"{'parameter':<18}{'value':>16} {'unit':<10}{'fixed':<7}{'min':>12}{'max':>12}  tied")
        for r in rows:
            lines.append(f"{r['name']:<18}{r['value']:>16.8g} {r['unit']:<10}{str(r['fixed']):<7}"
                         f"{str(r['min']):>12}{str(r['max']):>12}  {r['tied']}")
    else:
        lines.append("(no parameters)")
    try:
        bbox = model.bounding_box
        lines += ["", f"bounding_box: {bbox if not hasattr(bbox, 'intervals') else dict(bbox.intervals)}"]
    except NotImplementedError:
        lines += ["", "bounding_box: none"]
    except Exception as exc:  # noqa: BLE001
        lines += ["", f"bounding_box: unavailable ({exc})"]
    try:
        inv = model.inverse
        lines += ["", "inverse:", str(inv)]
    except NotImplementedError:
        lines += ["", "inverse: not available"]
    except Exception as exc:  # noqa: BLE001
        lines += ["", f"inverse: unavailable ({exc})"]
    lines += ["", str(model)]
    return "\n".join(lines)


def apply_constraints(model: Model, text: str) -> List[str]:
    """Apply lines like ``mean: fixed``, ``stddev: 0.1..5``, ``amplitude: free``, ``x: ..3``.

    ``free`` only releases a fixed parameter; ``..`` (no limits) removes bounds.

    Returns human-readable descriptions of what was applied.
    """
    applied = []
    for raw in text.replace(";", "\n").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        name, sep, spec = line.partition(":")
        name, spec = name.strip(), spec.strip().lower()
        if not sep or name not in model.param_names:
            raise ParseError(f"Unknown parameter in constraint {line!r}. "
                             f"Parameters: {', '.join(model.param_names)}.")
        p = getattr(model, name)
        if spec == "fixed":
            p.fixed = True
        elif spec == "free":
            p.fixed = False
        elif ".." in spec:
            lo, _, hi = spec.partition("..")
            lo_v = parse_float(lo, f"{name} lower") if lo.strip() else None
            hi_v = parse_float(hi, f"{name} upper") if hi.strip() else None
            if lo_v is not None and hi_v is not None and lo_v > hi_v:
                raise ParseError(f"{name}: lower bound exceeds upper bound.")
            p.bounds = (lo_v, hi_v)
        else:
            raise ParseError(f"Constraint {line!r}: use 'fixed', 'free' or 'lo..hi'.")
        applied.append(f"{name}: {spec}")
    return applied


def n_free_params(model: Model) -> int:
    return sum(1 for n in model.param_names
               if not getattr(model, n).fixed and not getattr(model, n).tied)


# --------------------------------------------------------------------------- #
# Fitting engine
# --------------------------------------------------------------------------- #
FITTERS: Dict[str, type] = {
    "LinearLSQFitter": fitting.LinearLSQFitter, "LevMarLSQFitter": fitting.LevMarLSQFitter,
    "TRFLSQFitter": fitting.TRFLSQFitter, "DogBoxLSQFitter": fitting.DogBoxLSQFitter,
    "SLSQPLSQFitter": fitting.SLSQPLSQFitter, "SimplexLSQFitter": fitting.SimplexLSQFitter,
}
_UNCERTAINTY_FITTERS = ("LinearLSQFitter", "LevMarLSQFitter", "TRFLSQFitter", "DogBoxLSQFitter")


def _values(a: Any) -> np.ndarray:
    return np.asarray(a.value if isinstance(a, u.Quantity) else a, dtype=float)


def make_weights(y: Any, sigma: Any, weights: Any) -> Optional[np.ndarray]:
    """Fit weights from 1-sigma uncertainties and/or explicit weights (both optional)."""
    w = None
    if sigma is not None:
        s = _values(sigma.to(y.unit) if isinstance(sigma, u.Quantity) and isinstance(y, u.Quantity)
                    else sigma)
        if s.shape != np.shape(y):
            raise ParseError("Uncertainties must have the same length as the data.")
        if (s[np.isfinite(s)] <= 0).any():
            raise ParseError("Uncertainties must be positive.")
        w = 1.0 / s
    if weights is not None:
        wt = _values(weights)
        if wt.shape != np.shape(y):
            raise ParseError("Weights must have the same length as the data.")
        w = wt if w is None else w * wt
    return w


def run_fit(model: Model, coords: Sequence[Any], data: Any, sigma: Any = None, weights: Any = None,
            fitter: str = "TRFLSQFitter", maxiter: int = 100, acc: float = 1e-7,
            calc_uncertainties: bool = True, outliers: bool = False, niter: int = 3,
            clip_sigma: float = 3.0) -> Dict[str, Any]:
    """Fit ``model`` to ``data`` at ``coords`` (1 or 2 coordinate arrays).

    Pure function (no Qt): returns the fitted model with statistics. Non-finite points
    are dropped before fitting; the number dropped is reported.
    """
    if fitter not in FITTERS:
        raise ParseError(f"Unknown fitter {fitter!r}.")
    if len(coords) != model.n_inputs:
        raise ParseError(f"Model has {model.n_inputs} input(s) but {len(coords)} coordinate array(s) were given.")
    shape = np.shape(data)
    if any(np.shape(c) != shape for c in coords):
        raise ParseError("Coordinates and data must have the same shape.")
    if fitter == "LinearLSQFitter" and not getattr(model, "linear", False):
        raise ParseError("LinearLSQFitter needs a linear model (e.g. a polynomial); pick a non-linear fitter.")
    for name in model.param_names:
        p = getattr(model, name)
        lo, hi = p.bounds
        val = float(np.asarray(p.value).reshape(-1)[0])
        if (lo is not None and val < lo) or (hi is not None and val > hi):
            raise ParseError(f"Initial value of {name} ({val:g}) lies outside its bounds ({lo}, {hi}).")
    w = make_weights(data, sigma, weights)
    good = np.isfinite(_values(data))
    for c in coords:
        good &= np.isfinite(_values(c))
    if w is not None:
        good &= np.isfinite(w)
    n_dropped = int((~good).sum())
    n_free = n_free_params(model)
    if n_free == 0:
        raise ParseError("All model parameters are fixed - nothing to fit.")
    if good.sum() < n_free:
        raise ParseError(f"Only {int(good.sum())} finite data point(s) for {n_free} free parameter(s).")
    flat = lambda a: a[good]  # noqa: E731
    fcoords = [flat(c) for c in coords]
    fdata = flat(data)
    fw = flat(w) if w is not None else None

    cls = FITTERS[fitter]
    fit_inst = cls(calc_uncertainties=calc_uncertainties) if fitter in _UNCERTAINTY_FITTERS else cls()
    kwargs: Dict[str, Any] = {}
    if fitter not in ("LinearLSQFitter",):
        kwargs.update(maxiter=maxiter, acc=acc)
    init = model.copy()
    mask = None
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        if outliers:
            runner = fitting.FittingWithOutlierRemoval(fit_inst, sigma_clip, niter=niter,
                                                       sigma=clip_sigma)
            fitted, omask = runner(model, *fcoords, fdata, weights=fw, **kwargs)
            mask = np.zeros(shape, dtype=bool)
            mask[np.flatnonzero(good)] = np.asarray(omask, dtype=bool)
            info = getattr(runner, "fit_info", None) or getattr(fit_inst, "fit_info", {})
        else:
            fitted = fit_inst(model, *fcoords, fdata, weights=fw, **kwargs)
            info = getattr(fit_inst, "fit_info", {})
    used = good if mask is None else good & ~mask
    model_vals = fitted(*[c for c in coords])
    if isinstance(data, u.Quantity) and isinstance(model_vals, u.Quantity):
        model_vals = model_vals.to(data.unit)
    resid = _values(data) - _values(model_vals)
    n_used = int(used.sum())
    dof = n_used - n_free
    ssr = float(np.sum(resid[used] ** 2))
    stats: Dict[str, Any] = {"n_used": n_used, "n_dropped": n_dropped, "n_free": n_free,
                             "dof": dof, "ssr": ssr, "rms": float(np.sqrt(ssr / max(n_used, 1)))}
    if sigma is not None:
        s = _values(sigma.to(data.unit) if isinstance(sigma, u.Quantity) and isinstance(data, u.Quantity)
                    else sigma)
        chi2 = float(np.sum((resid[used] / s[used]) ** 2))
        stats["chi2"] = chi2
        stats["reduced_chi2"] = chi2 / dof if dof > 0 else float("nan")
    if ssr > 0 and n_used > 0:
        try:
            stats["aic"] = float(akaike_info_criterion_lsq(ssr, n_free, n_used))
            stats["bic"] = float(bayesian_info_criterion_lsq(ssr, n_free, n_used))
        except Exception:  # noqa: BLE001  - e.g. too few samples for the AICc correction
            pass
    stds = getattr(fitted, "stds", None)
    cov = getattr(fitted, "cov_matrix", None)
    msgs = sorted({str(wm.message) for wm in caught})
    note = ""
    if isinstance(info, dict) and info.get("message"):
        note = str(info["message"]).strip()
    return {
        "init": init, "fit": fitted, "coords": [c for c in coords], "data": data, "sigma": sigma,
        "residual": resid, "good": good, "mask": mask, "stats": stats, "note": note,
        "stds": {n: (float(stds[n]) if n in stds.param_names and stds[n] is not None else float("nan"))
                 for n in fitted.param_names} if stds is not None else None,
        "cov": np.asarray(cov.cov_matrix) if cov is not None else None, "warnings": msgs,
        "fitter": fitter,
    }


def format_fit(r: Dict[str, Any]) -> str:
    fit, init, st = r["fit"], r["init"], r["stats"]
    lines = [f"Fitter: {r['fitter']}   points used: {st['n_used']}   non-finite dropped: {st['n_dropped']}"
             + (f"   outliers rejected: {int(r['mask'].sum())}" if r["mask"] is not None else ""),
             "", f"{'parameter':<18}{'initial':>16}{'fitted':>18}{'std. dev.':>16}"]
    for name in fit.param_names:
        p, p0 = getattr(fit, name), getattr(init, name)
        sd = r["stds"][name] if r["stds"] else float("nan")
        tag = "  (fixed)" if p.fixed else ""
        lines.append(f"{name:<18}{float(np.asarray(p0.value).reshape(-1)[0]):>16.8g}"
                     f"{float(np.asarray(p.value).reshape(-1)[0]):>18.10g}{sd:>16.4g}{tag}")
    lines += ["", f"free parameters: {st['n_free']}   dof: {st['dof']}",
              f"sum of squared residuals: {st['ssr']:.8g}   rms: {st['rms']:.8g}"]
    if "chi2" in st:
        lines.append(f"chi2: {st['chi2']:.8g}   reduced chi2: {st['reduced_chi2']:.6g}")
    if "aic" in st:
        lines.append(f"AIC (lsq): {st['aic']:.6g}   BIC (lsq): {st['bic']:.6g}")
    if r["note"]:
        lines.append(f"optimizer: {r['note']}")
    if r["cov"] is not None:
        lines += ["", "covariance matrix:", fmt(r["cov"])]
    if r["warnings"]:
        lines += ["", "Warnings:"] + [f"  {m}" for m in r["warnings"]]
    return "\n".join(lines)


def guess_gaussian2d(img: np.ndarray, offset: Tuple[int, int] = (0, 0)) -> str:
    """Moment-based starting model for a 2-D Gaussian on a constant background.

    ``offset`` = (x0, y0) of the image's first pixel in the full frame.
    """
    z = np.asarray(img, dtype=float)
    fin = np.isfinite(z)
    if z.ndim != 2 or not fin.any():
        raise ParseError("Need a 2-D image with finite pixels.")
    bg = float(np.nanmedian(z))
    w = np.where(fin, np.clip(z - bg, 0, None), 0.0)
    tot = w.sum()
    ny, nx = z.shape
    yy, xx = np.mgrid[:ny, :nx]
    if tot <= 0:
        cx, cy, sx, sy = nx / 2, ny / 2, max(nx / 6, 1), max(ny / 6, 1)
        amp = 1.0
    else:
        cx, cy = float((w * xx).sum() / tot), float((w * yy).sum() / tot)
        sx = float(np.sqrt((w * (xx - cx) ** 2).sum() / tot))
        sy = float(np.sqrt((w * (yy - cy) ** 2).sum() / tot))
        sx, sy = max(sx, 0.5), max(sy, 0.5)
        amp = float(np.nanmax(z) - bg)
    cx, cy = cx + offset[0], cy + offset[1]
    return (f"Gaussian2D(amplitude={amp:.6g}, x_mean={cx:.4f}, y_mean={cy:.4f}, "
            f"x_stddev={sx:.4f}, y_stddev={sy:.4f}) + Const2D({bg:.6g})")


# --------------------------------------------------------------------------- #
# Panels
# --------------------------------------------------------------------------- #
def _as_plain(a: Any) -> np.ndarray:
    return _values(a)


class ModelBuilderPanel(ModulePanel):
    """Browse models, compose expressions, edit parameters, evaluate, render, export."""

    COLS = ["Parameter", "Value", "Unit", "Fixed", "Min", "Max", "Tied"]

    def __init__(self, ws: Workspace) -> None:
        super().__init__(ws)
        self.model: Optional[Model] = None
        self._built_expr = ""
        self.catalog = model_catalog()
        f = self.form
        self.group = QComboBox()
        self.group.addItems(["1D", "2D", "Mappings / other", "Projections"])
        self.search = QLineEdit()
        self.search.setPlaceholderText("filter...")
        self.cls_combo = QComboBox()
        f.add_widget("group", "Group", self.group)
        f.add_widget("search", "Filter", self.search)
        f.add_widget("cls", "Model class", self.cls_combo)
        self.add_button("Insert class into expression", self.insert_class)
        f.add_multiline("expr", "Model expression", "Gaussian1D(1, 0, 1) + Const1D(0.1)",
                        "Operators + - * / ** | (pipe) & (join); workspace models can be used by name",
                        height=70)
        f.add_text("xmin", "Grid x min", "-5")
        f.add_text("xmax", "Grid x max", "5")
        f.add_text("ymin", "Grid y min (2-D)", "-5")
        f.add_text("ymax", "Grid y max (2-D)", "5")
        f.add_int("n", "Grid points / axis", 400, 2, 5000)
        f.add_text("unit", "Input unit", "", "Optional unit for x (and y), e.g. Hz or AA", "none")
        f.add_text("save", "Workspace name", "model")
        self.add_button("Build / describe", self.build)
        self.add_button("Evaluate & plot", self.evaluate)
        self.add_button("Render (bounding box)", self.render)
        self.add_button("Save model to workspace", self.save_model)
        self.add_button("Save inverse to workspace", self.save_inverse)
        self.add_button("Apply parameter edits", self.apply_edits)
        f.add_text("cname", "Custom: name", "MyModel")
        f.add_text("cexpr", "Custom: formula", "a*np.sin(b*x) + c", "Variables x (and y) plus the parameters")
        f.add_text("cparams", "Custom: parameters", "a=1, b=2, c=0")
        f.add_combo("cin", "Custom: inputs", [("1 (x)", 1), ("2 (x, y)", 2)])
        self.add_button("Create custom model", self.create_custom)
        self.out = self.add_output("Description")
        self.table = QTableWidget(0, len(self.COLS))
        self.table.setHorizontalHeaderLabels(self.COLS)
        self.tabs.addTab(self.table, "Parameters")
        self.info = self.add_output("Class info")
        self.canvas = self.add_plot("Evaluation")
        self.render_canvas = self.add_plot("Render")
        self.group.currentTextChanged.connect(self.fill_classes)
        self.search.textChanged.connect(self.fill_classes)
        self.cls_combo.currentTextChanged.connect(self.show_class_info)
        self.fill_classes()

    # ---- catalogue ------------------------------------------------------- #
    def fill_classes(self) -> None:
        needle = self.search.text().strip().lower()
        names = [n for n, c in self.catalog.items()
                 if model_group(c) == self.group.currentText() and needle in n.lower()]
        self.cls_combo.clear()
        self.cls_combo.addItems(sorted(names))

    def show_class_info(self, name: str) -> None:
        cls = self.catalog.get(name)
        if cls is None:
            self.info.show_text("")
            return
        try:
            sig = str(inspect.signature(cls.__init__)).replace("(self, ", "(").replace("(self)", "()")
        except (TypeError, ValueError):
            sig = "(...)"
        doc = inspect.getdoc(cls) or ""
        self.info.show_text(f"{name}{sig}\nparameters: {getattr(cls, 'param_names', ())}\n"
                            f"inputs: {cls.n_inputs}  outputs: {cls.n_outputs}  "
                            f"fittable: {cls.fittable}\n\n{doc}")

    def insert_class(self) -> None:
        def go() -> None:
            name = self.cls_combo.currentText()
            if not name:
                raise ParseError("No model class selected.")
            req = required_args(self.catalog[name])
            call = f"{name}({', '.join(req)})"
            box = self.form.fields["expr"]
            cur = box.toPlainText().strip()
            box.setPlainText(f"{cur} + {call}" if cur else call)
            if req:
                self.set_status(f"Replace the required argument(s): {', '.join(req)}")
        self.guard(go)

    # ---- model actions ----------------------------------------------------- #
    def current(self) -> Model:
        """The built model, keeping parameter edits while the expression is unchanged."""
        expr = self.form.value("expr")
        if self.model is None or expr != self._built_expr:
            self.model = parse_model(expr, self.ws)
            self._built_expr = expr
        return self.model

    def build(self) -> None:
        def go() -> None:
            self.model = None  # force a fresh parse (discard edits)
            m = self.current()
            self.out.show_text(describe_model(m))
            self.fill_param_table(m)
            self.tabs.setCurrentWidget(self.out)
        self.guard(go)

    def fill_param_table(self, m: Model) -> None:
        rows = param_rows(m)
        self.table.setRowCount(len(rows))
        for i, r in enumerate(rows):
            cells = [r["name"], f"{r['value']:.12g}", r["unit"], "", "" if r["min"] is None else str(r["min"]),
                     "" if r["max"] is None else str(r["max"]), r["tied"]]
            for j, text in enumerate(cells):
                item = QTableWidgetItem(text)
                if j in (0, 2, 6):
                    item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                if j == 3:
                    item.setFlags((item.flags() | Qt.ItemIsUserCheckable) & ~Qt.ItemIsEditable)
                    item.setCheckState(Qt.Checked if r["fixed"] else Qt.Unchecked)
                self.table.setItem(i, j, item)
        self.table.resizeColumnsToContents()

    def apply_edits(self) -> None:
        def go() -> None:
            if self.model is None:
                raise ParseError("Build a model first.")
            if self.table.rowCount() != len(self.model.param_names):
                raise ParseError("Build the model again before applying edits.")
            for i, name in enumerate(self.model.param_names):
                p = getattr(self.model, name)
                p.value = parse_float(self.table.item(i, 1).text(), name)
                p.fixed = self.table.item(i, 3).checkState() == Qt.Checked
                lo, hi = self.table.item(i, 4).text().strip(), self.table.item(i, 5).text().strip()
                p.bounds = (parse_float(lo, f"{name} min") if lo else None,
                            parse_float(hi, f"{name} max") if hi else None)
            self.out.show_text(describe_model(self.model))
            self.fill_param_table(self.model)
            self.set_status("Parameter edits applied (use Save to keep them in the workspace).")
        self.guard(go)

    def save_model(self) -> None:
        def go() -> None:
            m = self.current()
            name = self.ws.put(self.form.value("save"), m.copy())
            self.ws.log(f"Stored model '{name}': {type(m).__name__}")
        self.guard(go)

    def save_inverse(self) -> None:
        def go() -> None:
            m = self.current()
            try:
                inv = m.inverse
            except NotImplementedError:
                raise ParseError("This model has no analytical inverse.") from None
            name = self.ws.put(self.form.value("save") + "_inverse", inv.copy())
            self.ws.log(f"Stored inverse model '{name}'.")
        self.guard(go)

    def create_custom(self) -> None:
        def go() -> None:
            v = plain_values(self.form)
            m = make_custom_model(v["cname"], v["cexpr"], v["cparams"], int(v["cin"]))
            self.ws.put(v["cname"], m)
            self.form.set_value("expr", v["cname"])
            self.model, self._built_expr = m, v["cname"]
            self.out.show_text(describe_model(m))
            self.fill_param_table(m)
            self.set_status(f"Custom model {v['cname']} stored in the workspace.")
        self.guard(go)

    # ---- evaluation ------------------------------------------------------ #
    def _grid(self, m: Model) -> List[Any]:
        v = plain_values(self.form)
        if m.n_inputs not in (1, 2):
            raise ParseError(f"Evaluation supports models with 1 or 2 inputs (this has {m.n_inputs}).")
        n = v["n"] if m.n_inputs == 1 else min(v["n"], 400)
        unit = u.Unit(v["unit"]) if v["unit"] else None

        def axis(lo: str, hi: str) -> np.ndarray:
            a, b = parse_float(v[lo], lo), parse_float(v[hi], hi)
            if not a < b:
                raise ParseError(f"{lo} must be smaller than {hi}.")
            return np.linspace(a, b, n)

        xs = [axis("xmin", "xmax")]
        if m.n_inputs == 2:
            xs = list(np.meshgrid(xs[0], axis("ymin", "ymax")))
        return [x * unit if unit else x for x in xs]

    def evaluate(self) -> None:
        def go() -> None:
            m = self.current()
            self.fill_param_table(m)
            grid = self._grid(m)
            self.run(lambda: m(*grid), lambda out: self._plot_eval(m, grid, out),
                     busy_text="Evaluating model...")
        self.guard(go)

    def _plot_eval(self, m: Model, grid: List[Any], out: Any) -> None:
        ax = self.canvas.axes()
        outs = out if isinstance(out, tuple) else (out,)
        if m.n_inputs == 1:
            x = _as_plain(grid[0])
            for k, o in enumerate(outs):
                ax.plot(x, _as_plain(o), label=m.outputs[k] if len(outs) > 1 else None)
            ax.set_xlabel(m.inputs[0] + (f" [{grid[0].unit}]" if isinstance(grid[0], u.Quantity) else ""))
            ax.set_ylabel("model" + (f" [{outs[0].unit}]" if isinstance(outs[0], u.Quantity) else ""))
            if len(outs) > 1:
                ax.legend()
        else:
            x, y = _as_plain(grid[0]), _as_plain(grid[1])
            im = ax.pcolormesh(x, y, _as_plain(outs[0]), shading="auto")
            self.canvas.figure.colorbar(im, ax=ax)
            ax.set_xlabel(m.inputs[0])
            ax.set_ylabel(m.inputs[1])
        self.canvas.redraw()
        self.tabs.setCurrentWidget(self.canvas)

    def render(self) -> None:
        def go() -> None:
            m = self.current()
            n = self.form.value("n")
            if m.n_inputs == 1:
                out = np.zeros(n)
            elif m.n_inputs == 2:
                out = np.zeros((min(n, 400),) * 2)
            else:
                raise ParseError("Render supports 1- and 2-input models.")
            m2 = m.copy()
            try:
                img = m2.render(out.copy())
            except Exception:  # noqa: BLE001  - bounding box larger than the canvas / absent
                try:
                    m2.bounding_box = None
                    img = m2.render(out.copy())
                except Exception as exc:  # noqa: BLE001
                    raise ParseError(f"Cannot render this model: {exc}") from None
            ax = self.render_canvas.axes()
            if img.ndim == 1:
                ax.plot(img)
            else:
                ax.imshow(img, origin="lower")
            ax.set_title("Model.render() on a pixel grid")
            self.render_canvas.redraw()
            self.tabs.setCurrentWidget(self.render_canvas)
        self.guard(go)


class _FitBase(ModulePanel):
    """Shared fitter controls."""

    def add_fit_controls(self) -> None:
        f = self.form
        f.add_combo("fitter", "Fitter", list(FITTERS), current="TRFLSQFitter")
        f.add_int("maxiter", "Max iterations", 100, 1, 1_000_000)
        f.add_float("acc", "Tolerance (acc)", 1e-7, 1e-15, 1.0, 12)
        f.add_check("unc", "Parameter uncertainties", True, "Covariance / std. dev. (Linear, LevMar, TRF, DogBox)")
        f.add_check("outl", "Sigma-clip outliers", False, "FittingWithOutlierRemoval(sigma_clip)")
        f.add_int("niter", "Outlier iterations", 3, 1, 100)
        f.add_float("csig", "Clip sigma", 3.0, 0.1, 100, 2)
        f.add_multiline("cons", "Constraints", "", "Lines: 'mean: fixed' | 'stddev: 0.1..5' | 'amplitude: free'", 60)

    def fit_kwargs(self) -> Dict[str, Any]:
        v = plain_values(self.form)
        return dict(fitter=v["fitter"], maxiter=v["maxiter"], acc=v["acc"], calc_uncertainties=v["unc"],
                    outliers=v["outl"], niter=v["niter"], clip_sigma=v["csig"])


class Fit1DPanel(_FitBase):
    def __init__(self, ws: Workspace) -> None:
        super().__init__(ws)
        self.x_in, self.y_in = DataInput(ws), DataInput(ws)
        self.s_in, self.w_in = DataInput(ws, optional=True), DataInput(ws, optional=True)
        f = self.form
        f.add_widget("x", "x", self.x_in)
        f.add_widget("y", "y", self.y_in)
        f.add_widget("s", "y uncertainty (sigma)", self.s_in)
        f.add_widget("w", "Extra weights", self.w_in)
        f.add_multiline("model", "Initial model", "Gaussian1D(1, 0, 1)",
                        "Expression; workspace models can be used by name", 60)
        self.add_fit_controls()
        f.add_check("units", "Units-aware (use column units)", False,
                    "Pass Quantity data (needs a model with units)")
        f.add_check("init", "Plot initial model", True)
        f.add_text("save", "Save fitted model as", "fitted_model")
        self.add_button("Fit", self.fit)
        self.add_button("Save fitted model", self.save_fit)
        self.add_button("Save residual table", self.save_residuals)
        self.out = self.add_output("Fit result")
        self.canvas = self.add_plot("Fit")
        self._result: Optional[Dict[str, Any]] = None

    def fit(self) -> None:
        def go() -> None:
            v = plain_values(self.form)
            model = parse_model(v["model"], self.ws)
            if model.n_inputs != 1:
                raise ParseError("This panel fits 1-input models; use Image Fitting for 2-D.")
            apply_constraints(model, v["cons"])
            get = (lambda d: d.quantity()) if v["units"] else (lambda d: d.array())
            x, y, s, w = get(self.x_in), get(self.y_in), get(self.s_in), get(self.w_in)
            if x.shape != y.shape or x.ndim != 1:
                raise ParseError("x and y must be 1-D arrays of the same length.")
            self.run(run_fit, self._show, model, [x], y, s, w, **self.fit_kwargs(),
                     busy_text="Fitting...")
        self.guard(go)

    def _show(self, r: Dict[str, Any]) -> None:
        self._result = r
        self.out.show_text(format_fit(r))
        x = _as_plain(r["coords"][0])
        y = _as_plain(r["data"])
        good = r["good"]
        fig = self.canvas.figure
        fig.clear()
        ax, axr = fig.subplots(2, 1, sharex=True, gridspec_kw={"height_ratios": [3, 1]})
        sig = _as_plain(r["sigma"]) if r["sigma"] is not None else None
        keep = good if r["mask"] is None else good & ~r["mask"]
        if sig is not None:
            ax.errorbar(x[keep], y[keep], yerr=sig[keep], fmt=".", color="k", label="data")
        else:
            ax.plot(x[keep], y[keep], "k.", label="data")
        if r["mask"] is not None and r["mask"].any():
            ax.plot(x[r["mask"]], y[r["mask"]], "rx", label="outliers")
        if good.any():
            xf = np.linspace(np.min(x[good]), np.max(x[good]), 1000)
            xq = xf * r["coords"][0].unit if isinstance(r["coords"][0], u.Quantity) else xf
            if self.form.value("init"):
                ax.plot(xf, _as_plain(r["init"](xq)), "--", color="0.6", label="initial")
            ax.plot(xf, _as_plain(r["fit"](xq)), "r-", label="fit")
        ax.legend()
        axr.plot(x[keep], r["residual"][keep], "k.")
        axr.axhline(0, color="r", lw=0.8)
        axr.set_ylabel("residual")
        axr.set_xlabel("x")
        self.canvas.redraw()
        self.tabs.setCurrentWidget(self.out)

    def save_fit(self) -> None:
        def go() -> None:
            if self._result is None:
                raise ParseError("Run a fit first.")
            name = self.ws.put(self.form.value("save"), self._result["fit"].copy())
            self.ws.log(f"Stored fitted model '{name}'.")
        self.guard(go)

    def save_residuals(self) -> None:
        def go() -> None:
            r = self._result
            if r is None:
                raise ParseError("Run a fit first.")
            x, y = _as_plain(r["coords"][0]), _as_plain(r["data"])
            t = Table({"x": x, "y": y, "model": y - r["residual"], "residual": r["residual"]})
            if r["mask"] is not None:
                t["outlier"] = r["mask"]
            self.ws.put("fit_residuals", t)
            self.ws.log("Stored table 'fit_residuals'.")
        self.guard(go)


class Fit2DPanel(_FitBase):
    def __init__(self, ws: Workspace) -> None:
        super().__init__(ws)
        self.img = WorkspaceCombo(ws, IMAGE_TYPES)
        f = self.form
        f.add_widget("img", "Image", self.img)
        f.add_text("roi", "Region x0:x1, y0:y1", "", "Pixel slice, e.g. 10:60, 20:80 (empty = whole image)", "all")
        f.add_multiline("model", "Initial model", "Gaussian2D(1, 10, 10, 3, 3)", "", 60)
        self.add_button("Estimate Gaussian2D + background", self.guess)
        self.add_fit_controls()
        f.add_text("save", "Save fitted model as", "fitted_model_2d")
        self.add_button("Fit", self.fit)
        self.add_button("Save fitted model", self.save_fit)
        self.out = self.add_output("Fit result")
        self.canvas = self.add_plot("Image / model / residual")
        self._result: Optional[Dict[str, Any]] = None
        self._offset = (0, 0)

    def _image(self) -> Tuple[np.ndarray, Tuple[int, int]]:
        if not self.img.currentText():
            raise ParseError("Load an image into the workspace first.")
        data = image_from_object(self.ws.get(self.img.currentText()))
        if data.ndim != 2:
            raise ParseError(f"Need a 2-D image; got {data.ndim}-D data.")
        roi = self.form.value("roi")
        if not roi:
            return data, (0, 0)
        try:
            xs, ys = [p.strip() for p in roi.split(",")]
            x0, x1 = [int(t) for t in xs.split(":")]
            y0, y1 = [int(t) for t in ys.split(":")]
        except ValueError:
            raise ParseError("Region must look like '10:60, 20:80'.") from None
        if not (0 <= x0 < x1 <= data.shape[1] and 0 <= y0 < y1 <= data.shape[0]):
            raise ParseError(f"Region outside the image (shape {data.shape[::-1]} as x, y).")
        return data[y0:y1, x0:x1], (x0, y0)

    def guess(self) -> None:
        def go() -> None:
            data, (x0, y0) = self._image()
            self.form.set_value("model", guess_gaussian2d(data, (x0, y0)))
        self.guard(go)

    def fit(self) -> None:
        def go() -> None:
            v = plain_values(self.form)
            model = parse_model(v["model"], self.ws)
            if model.n_inputs != 2:
                raise ParseError("Image fitting needs a model with two inputs (x, y).")
            apply_constraints(model, v["cons"])
            data, off = self._image()
            self._offset = off
            yy, xx = np.mgrid[:data.shape[0], :data.shape[1]]
            xx, yy = xx + off[0], yy + off[1]
            self.run(run_fit, self._show, model, [xx.astype(float), yy.astype(float)], data,
                     **self.fit_kwargs(), busy_text="Fitting image...")
        self.guard(go)

    def _show(self, r: Dict[str, Any]) -> None:
        self._result = r
        self.out.show_text(format_fit(r) + (f"\n\n(pixel coordinates include region offset {self._offset})"
                                            if self._offset != (0, 0) else ""))
        data = _as_plain(r["data"])
        model_img = data - r["residual"]
        fig = self.canvas.figure
        fig.clear()
        axes = fig.subplots(1, 3)
        vmin, vmax = np.nanmin(data), np.nanmax(data)
        for ax, im, title in zip(axes, (data, model_img, r["residual"]), ("Data", "Model", "Residual")):
            show = ax.imshow(im, origin="lower", vmin=None if title == "Residual" else vmin,
                             vmax=None if title == "Residual" else vmax)
            ax.set_title(title)
            fig.colorbar(show, ax=ax, fraction=0.046)
        self.canvas.redraw()

    def save_fit(self) -> None:
        def go() -> None:
            if self._result is None:
                raise ParseError("Run a fit first.")
            name = self.ws.put(self.form.value("save"), self._result["fit"].copy())
            self.ws.log(f"Stored fitted model '{name}'.")
        self.guard(go)


# --------------------------------------------------------------------------- #
# Splines, interpolation and polynomial fits
# --------------------------------------------------------------------------- #
SPLINE_FITTERS = {
    "Spline: interpolate": fitting.SplineInterpolateFitter,
    "Spline: smoothing": fitting.SplineSmoothingFitter,
    "Spline: exact knots": fitting.SplineExactKnotsFitter,
    "Spline: splrep": fitting.SplineSplrepFitter,
}
POLY_MODELS = {"Polynomial1D": models.Polynomial1D, "Chebyshev1D": models.Chebyshev1D,
               "Legendre1D": models.Legendre1D, "Hermite1D": models.Hermite1D}
CURVE_METHODS = list(SPLINE_FITTERS) + ["Tabular1D: linear", "Tabular1D: nearest"] + [
    f"Polynomial: {n}" for n in POLY_MODELS]


def fit_curve(method: str, x: np.ndarray, y: np.ndarray, w: Optional[np.ndarray], degree: int,
              smoothing: Optional[float], knots: Optional[np.ndarray]) -> Model:
    """Fit a spline / tabular interpolant / polynomial family and return the model."""
    order = np.argsort(x)
    x, y = x[order], y[order]
    w = w[order] if w is not None else None
    ok = np.isfinite(x) & np.isfinite(y)
    x, y = x[ok], y[ok]
    w = w[ok] if w is not None else None
    if x.size < 2:
        raise ParseError("Need at least two finite points.")
    if method.startswith("Spline") or method.startswith("Tabular"):
        if (np.diff(x) <= 0).any():
            raise ParseError("x values must be strictly increasing (duplicates found).")
    if method.startswith("Spline"):
        if x.size <= degree:
            raise ParseError(f"A degree-{degree} spline needs more than {degree} points.")
        kwargs: Dict[str, Any] = {}
        if w is not None:
            kwargs["weights"] = w
        if method == "Spline: smoothing" and smoothing is not None:
            kwargs["s"] = smoothing
        if method == "Spline: splrep" and smoothing is not None:
            kwargs["s"] = smoothing
        if method == "Spline: exact knots":
            if knots is None or knots.size == 0:
                raise ParseError("Exact-knots fitting needs interior knots.")
            if (knots <= x[0]).any() or (knots >= x[-1]).any():
                raise ParseError("Interior knots must lie strictly inside the data range.")
            kwargs["t"] = np.sort(knots)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            return SPLINE_FITTERS[method]()(Spline1D(degree=degree), x, y, **kwargs)
    if method.startswith("Tabular1D"):
        kind = method.split(": ")[1]
        return models.Tabular1D(points=(x,), lookup_table=y, method=kind, bounds_error=False,
                                fill_value=np.nan)
    cls = POLY_MODELS[method.split(": ")[1]]
    if x.size <= degree:
        raise ParseError(f"A degree-{degree} polynomial needs more than {degree} points.")
    return fitting.LinearLSQFitter()(cls(degree), x, y, weights=w)


class CurvePanel(ModulePanel):
    def __init__(self, ws: Workspace) -> None:
        super().__init__(ws)
        self.x_in, self.y_in = DataInput(ws), DataInput(ws)
        self.w_in = DataInput(ws, optional=True)
        f = self.form
        f.add_widget("x", "x", self.x_in)
        f.add_widget("y", "y", self.y_in)
        f.add_widget("w", "Weights (optional)", self.w_in)
        f.add_combo("method", "Method", CURVE_METHODS)
        f.add_int("deg", "Degree", 3, 1, 25, "Spline degree (1-5) or polynomial degree")
        f.add_text("s", "Smoothing s", "", "Smoothing/splrep factor; empty = automatic", "auto")
        f.add_text("knots", "Interior knots", "", "Exact-knots only, e.g. 3, 6", "")
        f.add_int("deriv", "Derivative order", 0, 0, 5, "Spline only: plot this derivative below")
        f.add_int("npts", "Curve points", 500, 10, 100000)
        f.add_text("save", "Save model as", "curve_model")
        self.add_button("Fit / interpolate", self.fit)
        self.add_button("Save model", self.save)
        self.out = self.add_output("Result")
        self.canvas = self.add_plot("Curve")
        self.model: Optional[Model] = None

    def fit(self) -> None:
        def go() -> None:
            v = plain_values(self.form)
            x, y, w = self.x_in.array(), self.y_in.array(), self.w_in.array()
            if x.ndim != 1 or x.shape != y.shape:
                raise ParseError("x and y must be 1-D arrays of the same length.")
            if w is not None and w.shape != x.shape:
                raise ParseError("Weights must have the same length as x.")
            if v["method"].startswith("Spline") and not 1 <= v["deg"] <= 5:
                raise ParseError("Spline degree must be between 1 and 5.")
            s = parse_float(v["s"], "s") if v["s"] else None
            knots = np.array([parse_float(t, "knot") for t in v["knots"].replace(";", ",").split(",")
                              if t.strip()]) if v["knots"] else None
            self.run(fit_curve, lambda m: self._show(m, x, y), v["method"], x, y, w, v["deg"], s, knots,
                     busy_text="Fitting curve...")
        self.guard(go)

    def _show(self, m: Model, x: np.ndarray, y: np.ndarray) -> None:
        self.model = m
        v = plain_values(self.form)
        good = np.isfinite(x) & np.isfinite(y)
        xf = np.linspace(np.min(x[good]), np.max(x[good]), v["npts"])
        yf = m(xf)
        resid = y[good] - m(x[good])
        lines = [f"{type(m).__name__}: {v['method']}"]
        if isinstance(m, Spline1D):
            lines += [f"degree: {m.degree}", f"interior knots ({len(m.t_interior)}): {fmt(m.t_interior)}",
                      f"coefficients: {fmt(m.c)}"]
        elif not isinstance(m, models.Tabular1D):
            lines += [f"{n} = {float(getattr(m, n).value):.10g}" for n in m.param_names]
        lines.append(f"rms residual at data points: {np.sqrt(np.nanmean(resid ** 2)):.6g}")
        self.out.show_text("\n".join(lines))
        fig = self.canvas.figure
        fig.clear()
        nu = v["deriv"] if isinstance(m, Spline1D) else 0
        if nu > getattr(m, "degree", 0):
            raise ParseError(f"Derivative order must not exceed the degree ({m.degree}).")
        axes = fig.subplots(2, 1, sharex=True) if nu else [fig.add_subplot(111)]
        axes[0].plot(x[good], y[good], "k.", label="data")
        axes[0].plot(xf, yf, "r-", label="model")
        axes[0].legend()
        if nu:
            axes[1].plot(xf, m.derivative(nu)(xf))
            axes[1].set_ylabel(f"d{nu}/dx{nu}")
        axes[-1].set_xlabel("x")
        self.canvas.redraw()

    def save(self) -> None:
        def go() -> None:
            if self.model is None:
                raise ParseError("Fit a curve first.")
            name = self.ws.put(self.form.value("save"), self.model.copy())
            self.ws.log(f"Stored model '{name}'.")
        self.guard(go)


# --------------------------------------------------------------------------- #
SPECS = [
    ModuleSpec("model_builder", "Model Builder", CATEGORY, ModelBuilderPanel,
               "Browse astropy.modeling models, compose, edit constraints, evaluate, render, export"),
    ModuleSpec("model_fit1d", "Model Fitting (1-D)", CATEGORY, Fit1DPanel,
               "Fit models to x/y data with any fitter, uncertainties, outlier removal"),
    ModuleSpec("model_fit2d", "Image Fitting (2-D)", CATEGORY, Fit2DPanel,
               "Fit 2-D models to workspace images"),
    ModuleSpec("model_curves", "Splines & Polynomials", CATEGORY, CurvePanel,
               "Spline1D fitters, Tabular1D interpolation, Chebyshev/Legendre/Hermite fits"),
]
