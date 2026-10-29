"""astropy.stats: robust statistics, resampling, intervals, binning, circular statistics."""
from __future__ import annotations

import warnings
from typing import Any, Callable, Dict, List, Optional, Sequence

import numpy as np
from astropy import stats as ast_stats
from astropy import units as u
from astropy.nddata import NDData
from astropy.io.fits import CompImageHDU, HDUList, ImageHDU, PrimaryHDU
from astropy.table import Table
from PyQt5.QtWidgets import (
    QComboBox, QHBoxLayout, QListWidget, QAbstractItemView, QPlainTextEdit, QVBoxLayout, QWidget,
)

from ..core.parsing import (
    ParseError, parse_float, parse_float_list, parse_int, safe_eval,
)
from ..core.registry import ModuleSpec
from ..core.widgets import ModulePanel, WorkspaceCombo, monospace
from ..core.workspace import Workspace

CATEGORY = "Analysis"
IMAGE_TYPES = (np.ndarray, NDData, HDUList, PrimaryHDU, ImageHDU, CompImageHDU)
INTERVALS = ("wilson", "jeffreys", "flat", "wald")
MODE_TEXT, MODE_TABLE, MODE_IMAGE = "Numbers / expression", "Workspace table", "Workspace image"


# --------------------------------------------------------------------------- #
# Data helpers (shared with modeling_tools)
# --------------------------------------------------------------------------- #
def column_values(col: Any, name: str = "column") -> Any:
    """Float values of a table column; masked entries become NaN. Quantity if it has a unit."""
    unit = getattr(col, "unit", None)
    try:
        if isinstance(col, u.Quantity):
            col = col.filled(np.nan) if hasattr(col, "filled") else col
            vals = np.asarray(col.value, dtype=float)
        else:
            if hasattr(col, "filled"):  # MaskedColumn
                col = col.astype(float).filled(np.nan)
            vals = np.asarray(col, dtype=float)
    except (TypeError, ValueError):
        raise ParseError(f"{name}: column is not numeric.") from None
    return vals * u.Unit(unit) if unit not in (None, "") else vals


def image_from_object(obj: Any, name: str = "image") -> np.ndarray:
    """2-D (or N-D) float array from an ndarray / NDData / HDU / HDUList."""
    if isinstance(obj, HDUList):
        for hdu in obj:
            if getattr(hdu, "data", None) is not None and np.ndim(hdu.data) >= 2:
                obj = hdu
                break
        else:
            raise ParseError(f"{name}: no image HDU in the FITS file.")
    if isinstance(obj, (PrimaryHDU, ImageHDU, CompImageHDU)):
        obj = obj.data
    elif isinstance(obj, NDData):
        obj = obj.data
    if obj is None:
        raise ParseError(f"{name}: object has no image data.")
    try:
        return np.asarray(np.ma.filled(obj.astype(float), np.nan) if isinstance(obj, np.ma.MaskedArray)
                          else obj, dtype=float)
    except (TypeError, ValueError):
        raise ParseError(f"{name}: data are not numeric.") from None


class DataInput(QWidget):
    """Numbers from pasted text/expression, a workspace table column, or a workspace image.

    ``multi`` returns a 2-D matrix (one variable per line / selected column).
    ``optional`` makes empty input return ``None`` instead of raising.
    """

    def __init__(self, ws: Workspace, optional: bool = False, multi: bool = False,
                 allow_image: bool = False, default: str = "", parent: Optional[QWidget] = None
                 ) -> None:
        super().__init__(parent)
        self.ws, self.optional, self.multi = ws, optional, multi
        self.mode = QComboBox()
        self.mode.addItems([MODE_TEXT, MODE_TABLE] + ([MODE_IMAGE] if allow_image else []))
        self.text = QPlainTextEdit(default)
        self.text.setFont(monospace())
        self.text.setFixedHeight(70)
        self.text.setPlaceholderText("one variable per line" if multi else
                                     "numbers, or e.g. np.random.normal(0,1,100)  /  linspace(0,1,50)")
        self.table_box = QWidget()
        tl = QHBoxLayout(self.table_box)
        tl.setContentsMargins(0, 0, 0, 0)
        self.tables = WorkspaceCombo(ws, Table)
        self.column = QComboBox()
        self.columns = QListWidget()
        self.columns.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.columns.setFixedHeight(80)
        tl.addWidget(self.tables)
        tl.addWidget(self.columns if multi else self.column, 1)
        self.image_box = WorkspaceCombo(ws, IMAGE_TYPES)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        for w in (self.mode, self.text, self.table_box, self.image_box):
            lay.addWidget(w)
        self.mode.currentIndexChanged.connect(self._sync)
        self.tables.currentIndexChanged.connect(self._fill_columns)
        ws.changed.connect(self._fill_columns)
        self._fill_columns()
        self._sync()

    def _sync(self) -> None:
        mode = self.mode.currentText()
        self.text.setVisible(mode == MODE_TEXT)
        self.table_box.setVisible(mode == MODE_TABLE)
        self.image_box.setVisible(mode == MODE_IMAGE)

    def _fill_columns(self) -> None:
        names: List[str] = []
        if self.tables.currentText():
            try:
                names = list(self.ws.get(self.tables.currentText()).colnames)
            except KeyError:
                names = []
        old = self.column.currentText()
        self.column.clear()
        self.column.addItems(names)
        if old in names:
            self.column.setCurrentText(old)
        self.columns.clear()
        self.columns.addItems(names)

    # ---- API ------------------------------------------------------------- #
    def set_text(self, text: str) -> None:
        self.mode.setCurrentText(MODE_TEXT)
        self.text.setPlainText(text)

    def use_table(self, table_name: str, *columns: str) -> None:
        self.mode.setCurrentText(MODE_TABLE)
        self.tables.setCurrentText(table_name)
        self._fill_columns()
        if self.multi:
            for i in range(self.columns.count()):
                self.columns.item(i).setSelected(self.columns.item(i).text() in columns)
        else:
            self.column.setCurrentText(columns[0])

    def quantity(self) -> Any:
        """ndarray (or Quantity when a unit is available); ``None`` if optional and empty."""
        mode = self.mode.currentText()
        if mode == MODE_TEXT:
            return self._from_text(self.text.toPlainText())
        if mode == MODE_IMAGE:
            return image_from_object(self.ws.get(self._name(self.image_box)))
        table = self.ws.get(self._name(self.tables))
        if self.multi:
            cols = [i.text() for i in self.columns.selectedItems()]
            if not cols:
                if self.optional:
                    return None
                raise ParseError("Select at least one table column.")
            arrays = [column_values(table[c], c) for c in cols]
            return np.vstack([np.asarray(a.value if isinstance(a, u.Quantity) else a) for a in arrays])
        name = self.column.currentText()
        if not name:
            if self.optional:
                return None
            raise ParseError("Select a table column.")
        return column_values(table[name], name)

    def array(self) -> Optional[np.ndarray]:
        q = self.quantity()
        if q is None:
            return None
        return np.asarray(q.value if isinstance(q, u.Quantity) else q, dtype=float)

    @staticmethod
    def _name(combo: QComboBox) -> str:
        if not combo.currentText():
            raise ParseError("Nothing selected in the workspace - load or create an object first.")
        return combo.currentText()

    def _from_text(self, text: str) -> Any:
        text = text.strip()
        if not text:
            if self.optional:
                return None
            raise ParseError("No data given.")
        if self.multi:
            lines = [ln for ln in text.splitlines() if ln.strip() and not ln.strip().startswith("#")]
            try:
                rows = [parse_float_list(ln) for ln in lines]
            except ParseError:
                rows = None
            if rows is not None:
                if len({len(r) for r in rows}) != 1:
                    raise ParseError("All lines must contain the same number of values.")
                return np.vstack(rows)
        else:
            try:
                return parse_float_list(text)
            except ParseError:
                pass
        value = safe_eval(text.replace("\n", " ") if not self.multi else text)
        if isinstance(value, u.Quantity):
            return value
        try:
            return np.asarray(value, dtype=float)
        except (TypeError, ValueError):
            raise ParseError("Expression did not produce numeric data.") from None


def plain_values(form: Any) -> Dict[str, Any]:
    """``ParamForm.values()`` that skips :class:`DataInput` rows (read those directly)."""
    return {k: form.value(k) for k, w in form.fields.items() if not isinstance(w, DataInput)}


def need_finite(a: np.ndarray, n_min: int = 1, what: str = "data") -> np.ndarray:
    """Finite values of ``a`` (flattened); ParseError if fewer than ``n_min`` remain."""
    if a is None:
        raise ParseError(f"No {what} given.")
    good = np.asarray(a, dtype=float).ravel()
    good = good[np.isfinite(good)]
    if good.size < n_min:
        raise ParseError(f"Need at least {n_min} finite value(s) in {what}; got {good.size}.")
    return good


def fmt(x: Any) -> str:
    """Compact scalar/array formatting for result text."""
    return np.array2string(np.asarray(x), precision=8, suppress_small=False, separator=", ",
                           threshold=60, floatmode="maxprec")


def fvalue(x: Any) -> float:
    return float(np.asarray(x).reshape(-1)[0]) if np.size(x) else float("nan")


def _optional_float(text: str, name: str) -> Optional[float]:
    return parse_float(text, name) if text.strip() else None


def _caught(fn: Callable[[], Any]) -> Any:
    """Run ``fn`` collecting warnings; returns ``(value, [messages])``."""
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        value = fn()
    return value, sorted({str(w.message) for w in caught})


def _warn_text(msgs: Sequence[str]) -> str:
    return "\n\nWarnings:\n  " + "\n  ".join(msgs) if msgs else ""


# --------------------------------------------------------------------------- #
# Sigma clipping
# --------------------------------------------------------------------------- #
def compute_sigma_clip(data: np.ndarray, sigma_lower: float, sigma_upper: float,
                       maxiters: Optional[int], cenfunc: str, stdfunc: str,
                       grow: Any, axis: Optional[int], std_ddof: int = 0) -> Dict[str, Any]:
    if sigma_lower <= 0 or sigma_upper <= 0:
        raise ParseError("Sigma limits must be positive.")
    if not np.isfinite(data).any():
        raise ParseError("Data contain no finite values.")
    if axis is not None and not (-data.ndim <= axis < data.ndim):
        raise ParseError(f"Axis {axis} is invalid for {data.ndim}-D data.")
    kw = dict(sigma_lower=sigma_lower, sigma_upper=sigma_upper, maxiters=maxiters,
              cenfunc=cenfunc, stdfunc=stdfunc)
    clipper = ast_stats.SigmaClip(grow=grow, **kw)
    (clipped, lo, hi), msgs = _caught(
        lambda: clipper(data, axis=axis, masked=True, return_bounds=True))
    (stats3), msgs2 = _caught(lambda: ast_stats.sigma_clipped_stats(
        data, axis=axis, grow=grow, std_ddof=std_ddof, **kw))
    mask = np.ma.getmaskarray(clipped)
    finite = np.isfinite(data)
    return {
        "data": data, "mask": mask & finite, "lower": lo, "upper": hi,
        "mean": stats3[0], "median": stats3[1], "std": stats3[2],
        "n_total": int(data.size), "n_nonfinite": int((~finite).sum()),
        "n_clipped": int((mask & finite).sum()), "axis": axis,
        "raw_mean": np.nanmean(data, axis=axis), "raw_median": np.nanmedian(data, axis=axis),
        "raw_std": np.nanstd(data, axis=axis),
        "mad_std": ast_stats.mad_std(data, axis=axis, ignore_nan=True),
        "warnings": sorted(set(msgs + msgs2)),
    }


class SigmaClipPanel(ModulePanel):
    def __init__(self, ws: Workspace) -> None:
        super().__init__(ws)
        self.data_in = DataInput(ws, allow_image=True)
        self.form.add_widget("data", "Data", self.data_in)
        f = self.form
        f.add_float("sl", "Sigma lower", 3.0, 0.01, 1000, 3, "Clip values below center - sigma_lower*std")
        f.add_float("su", "Sigma upper", 3.0, 0.01, 1000, 3, "Clip values above center + sigma_upper*std")
        f.add_int("maxiters", "Max iterations", 5, 0, 10000, "0 = iterate until convergence")
        f.add_combo("cen", "Center function", ["median", "mean"])
        f.add_combo("std", "Deviation function", ["std", "mad_std"])
        f.add_float("grow", "Grow radius", 0.0, 0.0, 1000, 2, "Also clip neighbours within this radius (0 = off)")
        f.add_text("axis", "Axis", "", "Empty = whole array; integer axis for N-D data", "all")
        f.add_int("ddof", "Std ddof", 0, 0, 100, "Delta degrees of freedom for the clipped std")
        self.add_button("Compute", self.compute)
        self.add_button("Store clipped data in workspace", self.store, "Saves a Table of values and clip flags")
        self.out = self.add_output("Statistics")
        self.canvas = self.add_plot("Plot")
        self._result: Optional[Dict[str, Any]] = None

    def compute(self) -> None:
        self.guard(self._compute)

    def _compute(self) -> None:
        v = plain_values(self.form)
        data = self.data_in.array()
        axis = parse_int(v["axis"], "axis") if v["axis"] else None
        args = (data, v["sl"], v["su"], v["maxiters"] or None, v["cen"], v["std"],
                v["grow"] or False, axis, v["ddof"])
        self.run(compute_sigma_clip, self._show, *args, busy_text="Sigma clipping...")

    def _show(self, r: Dict[str, Any]) -> None:
        self._result = r
        lines = [
            f"Values: {r['n_total']}   non-finite: {r['n_nonfinite']}   clipped: {r['n_clipped']}",
            f"Clip bounds: lower = {fmt(r['lower'])}   upper = {fmt(r['upper'])}", "",
            "                 clipped            unclipped",
            f"mean      {fmt(r['mean'])!s:>18}  {fmt(r['raw_mean'])!s:>18}",
            f"median    {fmt(r['median'])!s:>18}  {fmt(r['raw_median'])!s:>18}",
            f"std       {fmt(r['std'])!s:>18}  {fmt(r['raw_std'])!s:>18}",
            f"mad_std (unclipped)  {fmt(r['mad_std'])}",
        ]
        self.out.show_text("\n".join(lines) + _warn_text(r["warnings"]))
        fig = self.canvas.figure
        fig.clear()
        data, mask = r["data"], r["mask"]
        if data.ndim == 2 and r["axis"] is None:
            ax1, ax2 = fig.subplots(1, 2)
            ax1.imshow(data, origin="lower", cmap="viridis")
            ax1.set_title("Data")
            ax2.imshow(mask, origin="lower", cmap="gray_r")
            ax2.set_title("Clipped pixels")
        else:
            flat, m = data.ravel(), mask.ravel()
            ax1, ax2 = fig.subplots(1, 2)
            idx = np.arange(flat.size)
            ax1.plot(idx[~m], flat[~m], ".", ms=3, label="kept")
            ax1.plot(idx[m], flat[m], "r.", ms=5, label="clipped")
            for b in (np.ravel(r["lower"]), np.ravel(r["upper"])):
                if b.size == 1:
                    ax1.axhline(b[0], color="k", ls="--", lw=0.8)
            ax1.set_xlabel("index")
            ax1.set_ylabel("value")
            ax1.legend()
            fin = flat[np.isfinite(flat)]
            if fin.size:
                bins = np.histogram_bin_edges(fin, bins=min(50, max(5, fin.size // 2)))
                ax2.hist(fin[~m[np.isfinite(flat)]], bins=bins, alpha=0.7, label="kept")
                ax2.hist(fin[m[np.isfinite(flat)]], bins=bins, color="r", alpha=0.7, label="clipped")
                ax2.legend()
            ax2.set_xlabel("value")
        self.canvas.redraw()

    def store(self) -> None:
        def go() -> None:
            if self._result is None:
                raise ParseError("Compute first.")
            r = self._result
            t = Table({"value": r["data"].ravel(), "clipped": r["mask"].ravel()})
            self.ws.put("sigma_clip_result", t)
            self.ws.log("Stored table 'sigma_clip_result'.")
        self.guard(go)


# --------------------------------------------------------------------------- #
# Robust statistics (biweight, MAD)
# --------------------------------------------------------------------------- #
def compute_robust(data: np.ndarray, c_loc: float, c_scale: float, M: Optional[float],
                   modify: bool, matrix: Optional[np.ndarray]) -> Dict[str, Any]:
    data = need_finite(data, 1)  # NaN/inf are dropped
    ignore_nan = False
    res: Dict[str, Any] = {"data": data}
    res["biweight_location"] = ast_stats.biweight_location(data, c=c_loc, M=M, ignore_nan=ignore_nan)
    res["biweight_scale"] = ast_stats.biweight_scale(data, c=c_scale, M=M, modify_sample_size=modify,
                                                     ignore_nan=ignore_nan)
    res["biweight_midvariance"] = ast_stats.biweight_midvariance(
        data, c=c_scale, M=M, modify_sample_size=modify, ignore_nan=ignore_nan)
    res["mad_std"] = ast_stats.mad_std(data, ignore_nan=ignore_nan)
    res["mad"] = ast_stats.median_absolute_deviation(data, ignore_nan=ignore_nan)
    res["mean"], res["median"], res["std"] = (np.nanmean(data), np.nanmedian(data), np.nanstd(data))
    if matrix is not None:
        if matrix.ndim != 2 or matrix.shape[0] < 2:
            raise ParseError("Covariance/correlation needs at least two variables.")
        if not np.isfinite(matrix).all():
            raise ParseError("Matrix input must not contain NaN/inf.")
        res["midcov"] = ast_stats.biweight_midcovariance(matrix, c=c_scale, M=None,
                                                         modify_sample_size=modify)
        res["midcorr"] = ast_stats.biweight_midcorrelation(matrix[0], matrix[1], c=c_scale,
                                                           modify_sample_size=modify)
    return res


class RobustPanel(ModulePanel):
    def __init__(self, ws: Workspace) -> None:
        super().__init__(ws)
        self.data_in = DataInput(ws)
        self.form.add_widget("data", "Data", self.data_in)
        f = self.form
        f.add_float("c_loc", "c (location)", 6.0, 0.1, 1000, 2, "Tuning constant for biweight_location")
        f.add_float("c_scale", "c (scale)", 9.0, 0.1, 1000, 2, "Tuning constant for scale/midvariance/covariance")
        f.add_text("M", "M (center)", "", "Initial center; empty = median", "median")
        f.add_check("modify", "Modify sample size", False, "Use only points inside the biweight window for n")
        self.matrix_in = DataInput(ws, optional=True, multi=True)
        f.add_widget("matrix", "Matrix (optional)", self.matrix_in)
        self.add_button("Compute", self.compute)
        self.out = self.add_output("Statistics")
        self.canvas = self.add_plot("Histogram")

    def compute(self) -> None:
        self.guard(self._compute)

    def _compute(self) -> None:
        v = plain_values(self.form)
        args = (self.data_in.array(), v["c_loc"], v["c_scale"], _optional_float(v["M"], "M"),
                v["modify"], self.matrix_in.array())
        self.run(compute_robust, self._show, *args, busy_text="Computing robust statistics...")

    def _show(self, r: Dict[str, Any]) -> None:
        keys = ["biweight_location", "biweight_scale", "biweight_midvariance", "mad_std", "mad",
                "mean", "median", "std"]
        text = "\n".join(f"{k:22s} {fmt(r[k])}" for k in keys)
        if "midcov" in r:
            text += f"\n\nbiweight_midcovariance:\n{fmt(r['midcov'])}\n\nbiweight_midcorrelation (rows 1, 2): {fmt(r['midcorr'])}"
        self.out.show_text(text)
        ax = self.canvas.axes()
        d = r["data"][np.isfinite(r["data"])]
        ax.hist(d, bins=min(60, max(5, d.size // 2)), color="0.75")
        for key, color in (("biweight_location", "r"), ("median", "b"), ("mean", "g")):
            ax.axvline(float(r[key]), color=color, label=key)
        ax.legend()
        ax.set_xlabel("value")
        self.canvas.redraw()


# --------------------------------------------------------------------------- #
# Bootstrap / jackknife
# --------------------------------------------------------------------------- #
STATISTICS: Dict[str, Callable[[np.ndarray], Any]] = {
    "mean": np.mean, "median": np.median, "std": np.std,
    "biweight_location": ast_stats.biweight_location, "biweight_scale": ast_stats.biweight_scale,
    "mad_std": ast_stats.mad_std,
}


def make_statistic(name: str, expr: str) -> Callable[[np.ndarray], Any]:
    if name != "custom":
        return STATISTICS[name]
    if not expr:
        raise ParseError("Enter an expression in x for the custom statistic.")
    safe_eval(expr, {"x": np.arange(1.0, 6.0)})  # fail early on syntax/name errors

    def stat(x: np.ndarray) -> Any:
        return safe_eval(expr, {"x": x})
    return stat


def compute_resampling(data: np.ndarray, statistic: Callable[[np.ndarray], Any], nboot: int,
                       seed: Optional[int], conf: float) -> Dict[str, Any]:
    data = need_finite(data, 2, "data")
    if not 0 < conf < 1:
        raise ParseError("Confidence level must be between 0 and 1.")
    if nboot < 1:
        raise ParseError("Number of resamples must be >= 1.")
    if seed is not None:
        np.random.seed(seed)  # astropy.stats.bootstrap draws from the global generator
    boot = np.asarray(ast_stats.bootstrap(data, bootnum=nboot, bootfunc=statistic), dtype=float)
    est, bias, err, ci = ast_stats.jackknife_stats(data, statistic, confidence_level=conf)
    resamples = ast_stats.jackknife_resampling(data)
    lo, hi = np.percentile(boot, [50 * (1 - conf), 50 * (1 + conf)], axis=0)
    return {"data": data, "boot": boot, "estimate": est, "bias": bias, "stderr": err, "jack_ci": ci,
            "value": statistic(data), "boot_ci": (lo, hi), "boot_mean": boot.mean(axis=0),
            "boot_std": boot.std(axis=0, ddof=1) if len(boot) > 1 else np.zeros(boot.shape[1:]),
            "jack_shape": resamples.shape, "conf": conf}


class ResamplingPanel(ModulePanel):
    def __init__(self, ws: Workspace) -> None:
        super().__init__(ws)
        self.data_in = DataInput(ws)
        self.form.add_widget("data", "Data", self.data_in)
        f = self.form
        f.add_combo("stat", "Statistic", list(STATISTICS) + ["custom"])
        f.add_text("expr", "Custom (in x)", "np.percentile(x, 90)", "Used when Statistic = custom; x is the sample")
        f.add_int("n", "Bootstrap samples", 1000, 1, 1_000_000)
        f.add_text("seed", "Random seed", "", "Empty = non-reproducible", "random")
        f.add_float("conf", "Confidence level", 0.95, 0.001, 0.999999, 4)
        self.add_button("Run bootstrap + jackknife", self.compute)
        self.out = self.add_output("Result")
        self.canvas = self.add_plot("Bootstrap distribution")

    def compute(self) -> None:
        self.guard(self._compute)

    def _compute(self) -> None:
        v = plain_values(self.form)
        stat = make_statistic(v["stat"], v["expr"])
        seed = parse_int(v["seed"], "seed") if v["seed"] else None
        self.run(compute_resampling, self._show, self.data_in.array(), stat, v["n"], seed, v["conf"],
                 busy_text="Resampling...")

    def _show(self, r: Dict[str, Any]) -> None:
        lo, hi = r["boot_ci"]
        self.out.show_text("\n".join([
            f"Statistic on full sample : {fmt(r['value'])}",
            f"Bootstrap mean / std     : {fmt(r['boot_mean'])} / {fmt(r['boot_std'])}",
            f"Bootstrap {r['conf']:.1%} interval  : [{fmt(lo)}, {fmt(hi)}]",
            "",
            f"Jackknife estimate (bias-corrected): {fmt(r['estimate'])}",
            f"Jackknife bias           : {fmt(r['bias'])}",
            f"Jackknife std. error     : {fmt(r['stderr'])}",
            f"Jackknife {r['conf']:.1%} interval  : {fmt(r['jack_ci'])}",
            f"Jackknife resamples      : {r['jack_shape'][0]} x {r['jack_shape'][1]}",
        ]))
        ax = self.canvas.axes()
        boot = r["boot"]
        if boot.ndim == 1:
            ax.hist(boot, bins=min(60, max(5, boot.size // 10)), color="0.7")
            ax.axvline(float(r["value"]), color="k", label="sample")
            ax.axvspan(float(lo), float(hi), color="C0", alpha=0.2, label="bootstrap CI")
            ax.legend()
        else:
            ax.plot(boot, ".", ms=2)
        ax.set_xlabel("statistic")
        self.canvas.redraw()


# --------------------------------------------------------------------------- #
# Binomial / Poisson intervals
# --------------------------------------------------------------------------- #
def compute_binomial(k: np.ndarray, n: np.ndarray, conf: float, method: str) -> Table:
    k, n = np.atleast_1d(k).astype(float), np.atleast_1d(n).astype(float)
    if k.size != n.size:
        if n.size == 1:
            n = np.full_like(k, n[0])
        elif k.size == 1:
            k = np.full_like(n, k[0])
        else:
            raise ParseError("k and n must have the same length (or one of them a single value).")
    if not (np.isfinite(k).all() and np.isfinite(n).all()):
        raise ParseError("k and n must be finite.")
    if (n < 1).any() or (k < 0).any() or (k > n).any():
        raise ParseError("Require n >= 1 and 0 <= k <= n.")
    if not 0 < conf < 1:
        raise ParseError("Confidence level must be between 0 and 1.")
    t = Table({"k": k, "n": n, "k/n": k / n})
    for m in (INTERVALS if method == "all" else (method,)):
        ci = ast_stats.binom_conf_interval(k, n, confidence_level=conf, interval=m)
        t[f"{m}_lower"], t[f"{m}_upper"] = ci[0], ci[1]
    return t


def _plot_errorbars(canvas: Any, x: np.ndarray, y: np.ndarray, lo: np.ndarray, hi: np.ndarray,
                    label: str, xlabel: str, ylabel: str) -> None:
    ax = canvas.axes()
    ax.errorbar(x, y, yerr=[np.clip(y - lo, 0, None), np.clip(hi - y, 0, None)], fmt="o",
                capsize=3, label=label)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.legend()
    canvas.redraw()


class BinomialPanel(ModulePanel):
    def __init__(self, ws: Workspace) -> None:
        super().__init__(ws)
        f = self.form
        f.add_text("k", "k (successes)", "3, 10, 50", "Comma/space separated")
        f.add_text("n", "n (trials)", "10, 20, 100", "Same length as k, or a single value")
        f.add_float("conf", "Confidence level", 0.68269, 0.0001, 0.999999, 6)
        f.add_combo("method", "Interval", ["all"] + list(INTERVALS))
        self.add_button("Compute", self.compute)
        self.table = self.add_table("Intervals")
        self.canvas = self.add_plot("Plot")

    def compute(self) -> None:
        self.guard(self._compute)

    def _compute(self) -> None:
        v = plain_values(self.form)
        self.run(compute_binomial, self._show, parse_float_list(v["k"], "k"),
                 parse_float_list(v["n"], "n"), v["conf"], v["method"])

    def _show(self, t: Table) -> None:
        self.table.set_table(t)
        self.ws.put("binomial_intervals", t)
        ax = self.canvas.axes()
        x = np.arange(len(t))
        p = np.asarray(t["k/n"])
        names = [c[:-6] for c in t.colnames if c.endswith("_lower")]
        for i, m in enumerate(names):
            off = (i - (len(names) - 1) / 2) * 0.12
            ax.errorbar(x + off, p, yerr=[p - t[f"{m}_lower"], t[f"{m}_upper"] - p], fmt="o",
                        capsize=3, label=m)
        ax.set_xlabel("row")
        ax.set_ylabel("k / n")
        ax.legend()
        self.canvas.redraw()


def compute_poisson(n: np.ndarray, interval: str, sigma: float, background: float,
                    conf: Optional[float]) -> Table:
    n = np.atleast_1d(n).astype(float)
    if (n < 0).any() or not np.isfinite(n).all():
        raise ParseError("Counts must be finite and >= 0.")
    if conf is not None and not 0 < conf < 1:
        raise ParseError("Confidence level must be between 0 and 1.")
    if interval == "kraft-burrows-nousek":
        if conf is None or n.size != 1:
            raise ParseError("kraft-burrows-nousek needs a single count and a confidence level.")
        lo, hi = ast_stats.poisson_conf_interval(n[0], interval, background=background,
                                                 confidence_level=conf)
        lo, hi = np.atleast_1d(lo), np.atleast_1d(hi)
    else:
        if background != 0 or conf is not None:
            raise ParseError("Background and confidence level are only supported by "
                             "kraft-burrows-nousek; use sigma for the other intervals.")
        lo, hi = ast_stats.poisson_conf_interval(n, interval, sigma=sigma)
    return Table({"n": n, "lower": np.asarray(lo, float), "upper": np.asarray(hi, float)})


class PoissonPanel(ModulePanel):
    def __init__(self, ws: Workspace) -> None:
        super().__init__(ws)
        f = self.form
        f.add_text("n", "Counts", "0, 1, 5, 20, 100", "Observed counts, separated by commas/spaces")
        f.add_combo("interval", "Interval", ["root-n", "root-n-0", "pearson", "sherpagehrels",
                                             "frequentist-confidence", "kraft-burrows-nousek"])
        f.add_float("sigma", "Sigma", 1.0, 0.01, 50, 3, "Number of sigma (all intervals except kraft-burrows-nousek)")
        f.add_float("bkg", "Background", 0.0, 0.0, 1e9, 4, "Expected background counts (kraft-burrows-nousek only)")
        f.add_text("conf", "Confidence level", "", "Required for kraft-burrows-nousek (single count), e.g. 0.9", "optional")
        self.add_button("Compute", self.compute)
        self.table = self.add_table("Intervals")
        self.canvas = self.add_plot("Plot")

    def compute(self) -> None:
        self.guard(self._compute)

    def _compute(self) -> None:
        v = plain_values(self.form)
        self.run(compute_poisson, self._show, parse_float_list(v["n"], "counts"), v["interval"],
                 v["sigma"], v["bkg"], _optional_float(v["conf"], "confidence level"))

    def _show(self, t: Table) -> None:
        self.table.set_table(t)
        self.ws.put("poisson_intervals", t)
        _plot_errorbars(self.canvas, np.arange(len(t)), np.asarray(t["n"]), np.asarray(t["lower"]),
                        np.asarray(t["upper"]), "interval", "row", "counts")


def compute_binned_binomial(x: np.ndarray, success: np.ndarray, bins: Any, rng: Any,
                            conf: float, method: str) -> Table:
    if x.size != success.size:
        raise ParseError("x and success must have the same length.")
    ok = np.isfinite(x) & np.isfinite(success)
    if not ok.any():
        raise ParseError("No finite data.")
    x, success = x[ok], success[ok].astype(bool)
    ctr, half, p, perr = ast_stats.binned_binom_proportion(x, success, bins=bins, range=rng,
                                                           confidence_level=conf, interval=method)
    return Table({"bin_center": ctr, "bin_halfwidth": half, "fraction": p,
                  "err_lower": perr[0], "err_upper": perr[1]})


class BinnedBinomialPanel(ModulePanel):
    def __init__(self, ws: Workspace) -> None:
        super().__init__(ws)
        self.x_in, self.s_in = DataInput(ws), DataInput(ws)
        self.form.add_widget("x", "x values", self.x_in)
        self.form.add_widget("s", "Success (0/1)", self.s_in)
        f = self.form
        f.add_text("bins", "Bins", "10", "Number of bins, or a list of edges")
        f.add_text("range", "Range", "", "lo, hi (only with a bin count)", "auto")
        f.add_float("conf", "Confidence level", 0.68269, 0.0001, 0.999999, 6)
        f.add_combo("method", "Interval", list(INTERVALS))
        self.add_button("Compute", self.compute)
        self.table = self.add_table("Binned proportions")
        self.canvas = self.add_plot("Plot")

    def compute(self) -> None:
        self.guard(self._compute)

    def _compute(self) -> None:
        v = plain_values(self.form)
        edges = parse_float_list(v["bins"], "bins")
        bins: Any = int(edges[0]) if edges.size == 1 else edges
        if edges.size == 1 and (edges[0] < 1 or edges[0] != int(edges[0])):
            raise ParseError("Bins must be a positive integer or a list of edges.")
        rng = tuple(parse_float_list(v["range"], "range")) if v["range"] else None
        if rng is not None and len(rng) != 2:
            raise ParseError("Range needs exactly two numbers.")
        self.run(compute_binned_binomial, self._show, self.x_in.array(), self.s_in.array(), bins,
                 rng, v["conf"], v["method"])

    def _show(self, t: Table) -> None:
        self.table.set_table(t)
        ax = self.canvas.axes()
        ax.errorbar(t["bin_center"], t["fraction"], xerr=t["bin_halfwidth"],
                    yerr=[t["err_lower"], t["err_upper"]], fmt="o", capsize=3)
        ax.set_xlabel("x")
        ax.set_ylabel("success fraction")
        self.canvas.redraw()


# --------------------------------------------------------------------------- #
# Histograms and Bayesian blocks
# --------------------------------------------------------------------------- #
def compute_histogram(data: np.ndarray, method: str, nbins: int, edges: Optional[np.ndarray],
                      rng: Optional[tuple]) -> Dict[str, Any]:
    d = need_finite(data, 2, "data")
    if method == "edges":
        if edges is None or edges.size < 2 or (np.diff(edges) <= 0).any():
            raise ParseError("Bin edges must be at least two strictly increasing numbers.")
        bins: Any = edges
    elif method == "number":
        if nbins < 1:
            raise ParseError("Number of bins must be >= 1.")
        bins = nbins
    else:
        if np.ptp(d) == 0:
            raise ParseError("All values are identical - cannot choose bin widths.")
        bins = method
    (counts, edges_out), msgs = _caught(lambda: ast_stats.histogram(d, bins=bins, range=rng))
    res = {"data": d, "counts": counts, "edges": edges_out, "method": method, "warnings": msgs}
    if method in ("knuth", "scott", "freedman"):
        fn = {"knuth": ast_stats.knuth_bin_width, "scott": ast_stats.scott_bin_width,
              "freedman": ast_stats.freedman_bin_width}[method]
        res["width"] = fn(d)
    return res


class HistogramPanel(ModulePanel):
    def __init__(self, ws: Workspace) -> None:
        super().__init__(ws)
        self.data_in = DataInput(ws)
        self.form.add_widget("data", "Data", self.data_in)
        f = self.form
        f.add_combo("method", "Binning", ["knuth", "scott", "freedman", "blocks", "number", "edges"],
                    "blocks = Bayesian blocks (events)")
        f.add_int("nbins", "Number of bins", 10, 1, 100000, "Used when Binning = number")
        f.add_text("edges", "Bin edges", "", "Used when Binning = edges", "e.g. 0, 1, 2.5, 10")
        f.add_text("range", "Range", "", "lo, hi (optional)", "auto")
        self.add_button("Compute", self.compute)
        self.table = self.add_table("Bins")
        self.out = self.add_output("Summary")
        self.canvas = self.add_plot("Histogram")

    def compute(self) -> None:
        self.guard(self._compute)

    def _compute(self) -> None:
        v = plain_values(self.form)
        edges = parse_float_list(v["edges"], "edges") if v["method"] == "edges" else None
        rng = tuple(parse_float_list(v["range"], "range")) if v["range"] else None
        if rng is not None and (len(rng) != 2 or rng[0] >= rng[1]):
            raise ParseError("Range needs two numbers lo < hi.")
        self.run(compute_histogram, self._show, self.data_in.array(), v["method"], v["nbins"],
                 edges, rng)

    def _show(self, r: Dict[str, Any]) -> None:
        e, c = r["edges"], r["counts"]
        t = Table({"left": e[:-1], "right": e[1:], "width": np.diff(e), "count": c})
        self.table.set_table(t)
        self.ws.put("histogram_bins", t)
        extra = f"\nbin width ({r['method']}): {fmt(r['width'])}" if "width" in r else ""
        self.out.show_text(f"{len(c)} bins, {int(c.sum())} values in range{extra}\n"
                           f"edges: {fmt(e)}" + _warn_text(r["warnings"]))
        ax = self.canvas.axes()
        ax.stairs(c, e, fill=True, alpha=0.5)
        ax.stairs(c, e, color="C0")
        ax.set_xlabel("value")
        ax.set_ylabel("count")
        self.canvas.redraw()


def compute_blocks(t: np.ndarray, x: Optional[np.ndarray], sigma: Any, fitness: str,
                   p0: float, gamma: Optional[float], ncp_prior: Optional[float],
                   dt: Optional[float] = None) -> Dict[str, Any]:
    t = np.asarray(t, float)
    if not np.isfinite(t).all():
        raise ParseError("t contains NaN/inf.")
    if t.size < 2:
        raise ParseError("Need at least two points.")
    if fitness == "measures":
        if x is None or sigma is None:
            raise ParseError("Fitness 'measures' needs x (values) and sigma.")
    if x is not None and x.size != t.size:
        raise ParseError("t and x must have the same length.")
    if fitness == "events" and np.unique(t).size < 2:
        raise ParseError("All event times are identical.")
    kw: Dict[str, Any] = {}
    if fitness == "regular_events":
        if dt is None or dt <= 0:
            raise ParseError("Fitness 'regular_events' needs a positive dt (event spacing).")
        kw["dt"] = dt
    if gamma is not None:
        kw["gamma"] = gamma
    elif ncp_prior is not None:
        kw["ncp_prior"] = ncp_prior
    else:
        kw["p0"] = p0
    edges = ast_stats.bayesian_blocks(t, x=x if fitness != "events" else None,
                                      sigma=sigma if fitness == "measures" else None,
                                      fitness=fitness, **kw)
    return {"t": t, "x": x, "edges": edges, "fitness": fitness}


class BayesianBlocksPanel(ModulePanel):
    def __init__(self, ws: Workspace) -> None:
        super().__init__(ws)
        self.t_in = DataInput(ws)
        self.x_in = DataInput(ws, optional=True)
        self.s_in = DataInput(ws, optional=True)
        self.form.add_widget("t", "t (times / values)", self.t_in)
        f = self.form
        f.add_combo("fitness", "Fitness", ["events", "regular_events", "measures"])
        f.add_widget("x", "x (counts/measurements)", self.x_in)
        f.add_widget("s", "sigma (measures only)", self.s_in)
        f.add_text("dt", "dt", "", "Time spacing (regular_events only)", "optional")
        f.add_float("p0", "p0 (false alarm)", 0.05, 1e-9, 0.999, 4)
        f.add_text("gamma", "gamma", "", "Overrides p0 when set", "optional")
        f.add_text("ncp", "ncp_prior", "", "Overrides p0 when set (gamma unset)", "optional")
        self.add_button("Compute blocks", self.compute)
        self.out = self.add_output("Edges")
        self.canvas = self.add_plot("Blocks")

    def compute(self) -> None:
        self.guard(self._compute)

    def _compute(self) -> None:
        v = plain_values(self.form)
        sig = self.s_in.array()
        if sig is not None and sig.size == 1:
            sig = float(sig[0])
        self.run(compute_blocks, self._show, self.t_in.array(), self.x_in.array(), sig, v["fitness"],
                 v["p0"], _optional_float(v["gamma"], "gamma"), _optional_float(v["ncp"], "ncp_prior"),
                 _optional_float(v["dt"], "dt"))

    def _show(self, r: Dict[str, Any]) -> None:
        e = r["edges"]
        self.out.show_text(f"{len(e) - 1} block(s)\nedges: {fmt(e)}")
        ax = self.canvas.axes()
        t, x = r["t"], r["x"]
        if r["fitness"] == "events":
            ax.hist(t, bins=min(100, max(10, t.size // 5)), color="0.8", density=True)
            counts, _ = np.histogram(t, e)
            ax.stairs(counts / np.diff(e) / t.size, e, color="r", lw=2, label="blocks")
            ax.legend()
        else:
            ax.plot(t, x, ".", color="0.5")
            idx = np.clip(np.searchsorted(e, t, side="right") - 1, 0, len(e) - 2)
            means = np.array([x[idx == i].mean() if (idx == i).any() else np.nan
                              for i in range(len(e) - 1)])
            ax.stairs(means, e, color="r", lw=2)
        for edge in e:
            ax.axvline(edge, color="r", lw=0.5, alpha=0.5)
        self.canvas.redraw()


# --------------------------------------------------------------------------- #
# Circular statistics and Kuiper test
# --------------------------------------------------------------------------- #
ANGLE_UNITS = {"degrees": u.deg, "radians": u.rad, "hours (hourangle)": u.hourangle}


def compute_circular(alpha: np.ndarray, unit: Any, weights: Optional[np.ndarray], mu: float,
                     p: float, beta: Optional[np.ndarray]) -> Dict[str, Any]:
    a = np.asarray(alpha, float)
    if a.size == 0 or not np.isfinite(a).all():
        raise ParseError("Angles must be a non-empty list of finite numbers.")
    if weights is not None:
        weights = np.asarray(weights, float)
        if weights.size != a.size or (weights < 0).any() or not weights.sum() > 0:
            raise ParseError("Weights must be non-negative, same length as the data, with a positive sum.")
    rad = (a * unit).to_value(u.rad)
    mu_rad = (mu * unit).to_value(u.rad)
    cmean = float(ast_stats.circmean(rad, weights=weights))
    kappa_mu = ast_stats.vonmisesmle(rad, weights=weights)
    mp, rp = ast_stats.circmoment(rad, p=p, weights=weights)
    res: Dict[str, Any] = {
        "rad": rad, "weights": weights, "unit": unit,
        "circmean": (cmean * u.rad).to_value(unit) % (360 if unit == u.deg else 2 * np.pi
                                                      if unit == u.rad else 24),
        "circmean_rad": cmean,
        "circvar": float(ast_stats.circvar(rad, weights=weights)),
        "circstd_angular": (float(ast_stats.circstd(rad, weights=weights, method="angular")) * u.rad
                            ).to_value(unit),
        "circstd_circular": float(ast_stats.circstd(rad, weights=weights, method="circular")),
        "moment_p": p, "moment_angle": (float(mp) * u.rad).to_value(unit), "moment_length": float(rp),
        "rayleigh_p": float(ast_stats.rayleightest(rad, weights=weights)),
        "vtest_p": float(ast_stats.vtest(rad, mu=mu_rad, weights=weights)),
        "vonmises_mu": (float(kappa_mu[0]) * u.rad).to_value(unit), "vonmises_kappa": float(kappa_mu[1]),
        "R": float(np.hypot(np.average(np.cos(rad), weights=weights),
                            np.average(np.sin(rad), weights=weights))),
    }
    if beta is not None:
        b = (np.asarray(beta, float) * unit).to_value(u.rad)
        if b.size != rad.size:
            raise ParseError("Second angle set must have the same length as the first.")
        res["circcorrcoef"] = float(ast_stats.circcorrcoef(rad, b))
    return res


class CircularPanel(ModulePanel):
    def __init__(self, ws: Workspace) -> None:
        super().__init__(ws)
        self.a_in = DataInput(ws)
        self.w_in = DataInput(ws, optional=True)
        self.b_in = DataInput(ws, optional=True)
        self.form.add_widget("a", "Angles", self.a_in)
        f = self.form
        f.add_combo("unit", "Angle unit", list(ANGLE_UNITS))
        f.add_widget("w", "Weights (optional)", self.w_in)
        f.add_widget("b", "Second angles (for circcorrcoef)", self.b_in)
        f.add_float("mu", "V-test direction mu", 0.0, -1e6, 1e6, 4, "Hypothesised mean direction, in the chosen unit")
        f.add_float("p", "Moment order p", 1.0, 0.1, 100, 2)
        self.add_button("Compute", self.compute)
        self.out = self.add_output("Statistics")
        self.canvas = self.add_plot("Polar plot")

    def compute(self) -> None:
        self.guard(self._compute)

    def _compute(self) -> None:
        v = plain_values(self.form)
        self.run(compute_circular, self._show, self.a_in.array(), ANGLE_UNITS[v["unit"]],
                 self.w_in.array(), v["mu"], v["p"], self.b_in.array())

    def _show(self, r: Dict[str, Any]) -> None:
        name = {u.deg: "deg", u.rad: "rad", u.hourangle: "h"}[r["unit"]]
        lines = [
            f"circular mean          : {r['circmean']:.8g} {name}",
            f"mean resultant length R: {r['R']:.8g}",
            f"circular variance      : {r['circvar']:.8g}",
            f"circular std (angular) : {r['circstd_angular']:.8g} {name}",
            f"circular std (circular): {r['circstd_circular']:.8g}",
            f"moment p={r['moment_p']:g}: angle {r['moment_angle']:.8g} {name}, length {r['moment_length']:.8g}",
            f"Rayleigh test p-value  : {r['rayleigh_p']:.6g}",
            f"V-test p-value         : {r['vtest_p']:.6g}",
            f"von Mises MLE          : mu = {r['vonmises_mu']:.8g} {name}, kappa = {r['vonmises_kappa']:.6g}",
        ]
        if "circcorrcoef" in r:
            lines.append(f"circular correlation   : {r['circcorrcoef']:.8g}")
        self.out.show_text("\n".join(lines))
        fig = self.canvas.figure
        fig.clear()
        ax = fig.add_subplot(111, projection="polar")
        rad = r["rad"]
        ax.plot(rad, np.ones_like(rad), "o", alpha=0.5)
        ax.annotate("", xy=(r["circmean_rad"], r["R"]), xytext=(0, 0),
                    arrowprops={"arrowstyle": "->", "color": "r", "lw": 2})
        ax.set_ylim(0, 1.1)
        self.canvas.redraw()


def compute_kuiper(data: np.ndarray, data2: Optional[np.ndarray], period: float) -> Dict[str, Any]:
    if period <= 0:
        raise ParseError("Period must be positive.")
    d = need_finite(data, 2, "data") / period % 1.0
    if data2 is None:
        stat, fpp = ast_stats.kuiper(d)
        return {"stat": stat, "fpp": fpp, "n": d.size, "two": False}
    d2 = need_finite(data2, 2, "second data set") / period % 1.0
    stat, fpp = ast_stats.kuiper_two(d, d2)
    return {"stat": stat, "fpp": fpp, "n": d.size, "n2": d2.size, "two": True}


class KuiperPanel(ModulePanel):
    def __init__(self, ws: Workspace) -> None:
        super().__init__(ws)
        self.a_in, self.b_in = DataInput(ws), DataInput(ws, optional=True)
        self.form.add_widget("a", "Data / phases", self.a_in)
        self.form.add_widget("b", "Second sample (optional)", self.b_in)
        self.form.add_float("period", "Period", 1.0, 1e-12, 1e12, 6,
                            "Values are folded as (x / period) mod 1; 1 means data already are phases")
        self.add_button("Run Kuiper test", self.compute)
        self.out = self.add_output("Result")

    def compute(self) -> None:
        self.guard(lambda: self.run(compute_kuiper, self._show, self.a_in.array(), self.b_in.array(),
                                    self.form.value("period")))

    def _show(self, r: Dict[str, Any]) -> None:
        kind = "two-sample" if r["two"] else "one-sample (uniform)"
        self.out.show_text(f"Kuiper test, {kind}\nV statistic = {r['stat']:.8g}\n"
                           f"false-positive probability = {r['fpp']:.6g}\nsample size = {r['n']}")


# --------------------------------------------------------------------------- #
# Small calculators
# --------------------------------------------------------------------------- #
def compute_info_criteria(mode: str, value_a: float, k_a: int, n: int,
                          value_b: Optional[float] = None, k_b: Optional[int] = None) -> Dict[str, Any]:
    if n < 1 or k_a < 1 or (k_b is not None and k_b < 1):
        raise ParseError("Number of samples and parameters must be >= 1.")
    if not np.isfinite(value_a) or (value_b is not None and not np.isfinite(value_b)):
        raise ParseError("Likelihood / SSR must be finite.")
    if mode == "lsq" and (value_a <= 0 or (value_b is not None and value_b <= 0)):
        raise ParseError("The sum of squared residuals must be positive.")
    aic_f, bic_f = ((ast_stats.akaike_info_criterion_lsq, ast_stats.bayesian_info_criterion_lsq)
                    if mode == "lsq" else
                    (ast_stats.akaike_info_criterion, ast_stats.bayesian_info_criterion))
    res = {"A": (aic_f(value_a, k_a, n), bic_f(value_a, k_a, n))}
    if value_b is not None:
        kb = k_b if k_b is not None else k_a
        res["B"] = (aic_f(value_b, kb, n), bic_f(value_b, kb, n))
        d_aic = res["B"][0] - res["A"][0]
        d_bic = res["B"][1] - res["A"][1]
        res["delta_aic"], res["delta_bic"] = d_aic, d_bic
        res["relative_likelihood"] = float(np.exp(min(d_aic / 2, 700)))  # exp((AIC_B-AIC_A)/2)
    return res


class InfoCriteriaPanel(ModulePanel):
    def __init__(self, ws: Workspace) -> None:
        super().__init__(ws)
        f = self.form
        f.add_combo("mode", "Input", [("Log-likelihood", "ll"), ("Sum of squared residuals", "lsq")])
        f.add_float("va", "Model A: logL / SSR", -50.0, -1e300, 1e300, 6)
        f.add_int("ka", "Model A: parameters", 3, 1, 100000)
        f.add_check("cmp", "Compare with model B", False)
        f.add_float("vb", "Model B: logL / SSR", -45.0, -1e300, 1e300, 6)
        f.add_int("kb", "Model B: parameters", 5, 1, 100000)
        f.add_int("n", "Samples", 100, 1, 10**9)
        self.add_button("Compute", self.compute)
        self.out = self.add_output("Criteria")

    def compute(self) -> None:
        def go() -> None:
            v = plain_values(self.form)
            cmp = v["cmp"]
            r = compute_info_criteria(v["mode"], v["va"], v["ka"], v["n"],
                                      v["vb"] if cmp else None, v["kb"] if cmp else None)
            lines = [f"Model A: AIC = {r['A'][0]:.6f}   BIC = {r['A'][1]:.6f}"]
            if "B" in r:
                lines += [f"Model B: AIC = {r['B'][0]:.6f}   BIC = {r['B'][1]:.6f}", "",
                          f"dAIC (B - A) = {r['delta_aic']:.6f}   dBIC (B - A) = {r['delta_bic']:.6f}",
                          f"exp((AIC_B - AIC_A)/2) = {r['relative_likelihood']:.6g}"
                          "   (relative likelihood of model A over B)"]
            self.out.show_text("\n".join(lines))
        self.guard(go)


def compute_snr(t: np.ndarray, source_eps: float, sky_eps: float, dark_eps: float, rd: float,
                npix: float, gain: float) -> Table:
    t = np.atleast_1d(np.asarray(t, float))
    if (t <= 0).any() or not np.isfinite(t).all():
        raise ParseError("Exposure times must be positive.")
    if min(source_eps, sky_eps, dark_eps, rd) < 0 or npix <= 0 or gain <= 0:
        raise ParseError("Rates/read noise must be >= 0 and npix, gain > 0.")
    snr = np.atleast_1d(ast_stats.signal_to_noise_oir_ccd(t, source_eps, sky_eps, dark_eps, rd,
                                                          npix, gain))
    return Table({"t": t, "snr": snr})


class SnrPanel(ModulePanel):
    def __init__(self, ws: Workspace) -> None:
        super().__init__(ws)
        f = self.form
        self.t_in = DataInput(ws, default="linspace(1, 600, 60)")
        f.add_widget("t", "Exposure times (s)", self.t_in)
        f.add_float("src", "Source (e-/s)", 10.0, 0, 1e12, 4)
        f.add_float("sky", "Sky (e-/s/pix)", 1.0, 0, 1e12, 4)
        f.add_float("dark", "Dark (e-/s/pix)", 0.1, 0, 1e12, 4)
        f.add_float("rd", "Read noise (e-)", 5.0, 0, 1e6, 3)
        f.add_float("npix", "Pixels in aperture", 20.0, 1e-6, 1e9, 3)
        f.add_float("gain", "Gain (e-/ADU)", 1.0, 1e-6, 1e6, 4)
        self.add_button("Compute", self.compute)
        self.table = self.add_table("S/N")
        self.canvas = self.add_plot("S/N vs time")

    def compute(self) -> None:
        def go() -> None:
            v = plain_values(self.form)
            t = compute_snr(self.t_in.array(), v["src"], v["sky"], v["dark"], v["rd"], v["npix"], v["gain"])
            self.table.set_table(t)
            ax = self.canvas.axes()
            ax.plot(t["t"], t["snr"], "o-" if len(t) < 30 else "-")
            ax.set_xlabel("exposure time [s]")
            ax.set_ylabel("S/N")
            self.canvas.redraw()
        self.guard(go)


class GaussianWidthPanel(ModulePanel):
    def __init__(self, ws: Workspace) -> None:
        super().__init__(ws)
        self.form.add_text("v", "Value", "1.0")
        self.form.add_combo("dir", "Convert", [("FWHM -> sigma", "f2s"), ("sigma -> FWHM", "s2f")])
        self.add_button("Convert", self.compute)
        self.out = self.add_output("Result")
        self.compute()

    def compute(self) -> None:
        def go() -> None:
            x = parse_float(self.form.value("v"), "value")
            f2s = self.form.value("dir") == "f2s"
            res = x * ast_stats.gaussian_fwhm_to_sigma if f2s else x * ast_stats.gaussian_sigma_to_fwhm
            self.out.show_text(
                f"{'FWHM' if f2s else 'sigma'} = {x:.12g}  ->  {'sigma' if f2s else 'FWHM'} = {res:.12g}\n\n"
                f"gaussian_fwhm_to_sigma = {ast_stats.gaussian_fwhm_to_sigma!r}\n"
                f"gaussian_sigma_to_fwhm = {ast_stats.gaussian_sigma_to_fwhm!r}")
        self.guard(go)


# --------------------------------------------------------------------------- #
# Ripley's K
# --------------------------------------------------------------------------- #
RIPLEY_MODES = ("none", "translation", "ohser", "var-width", "ripley")


def compute_ripley(x: np.ndarray, y: np.ndarray, region: Optional[tuple], radii: np.ndarray,
                   mode: str) -> Dict[str, Any]:
    if x.size != y.size:
        raise ParseError("x and y must have the same length.")
    ok = np.isfinite(x) & np.isfinite(y)
    x, y = x[ok], y[ok]
    if x.size < 3:
        raise ParseError("Need at least 3 finite points.")
    x0, x1, y0, y1 = region if region else (x.min(), x.max(), y.min(), y.max())
    if not (x1 > x0 and y1 > y0):
        raise ParseError("Study region must have positive width and height.")
    inside = (x >= x0) & (x <= x1) & (y >= y0) & (y <= y1)
    if inside.sum() < 3:
        raise ParseError("Fewer than 3 points inside the study region.")
    if (radii < 0).any() or radii.size == 0 or not np.isfinite(radii).all():
        raise ParseError("Radii must be finite and >= 0.")
    est = ast_stats.RipleysKEstimator(area=(x1 - x0) * (y1 - y0), x_min=x0, x_max=x1,
                                      y_min=y0, y_max=y1)
    pts = np.column_stack([x[inside], y[inside]])
    (k, l), msgs = _caught(lambda: (est(pts, radii, mode=mode), est.Lfunction(pts, radii, mode=mode)))
    return {"radii": radii, "K": k, "L": l, "poisson": est.poisson(radii), "n": len(pts),
            "pts": pts, "region": (x0, x1, y0, y1), "mode": mode, "warnings": msgs}


class RipleyPanel(ModulePanel):
    def __init__(self, ws: Workspace) -> None:
        super().__init__(ws)
        self.x_in, self.y_in = DataInput(ws), DataInput(ws)
        self.r_in = DataInput(ws, default="linspace(0.01, 0.25, 25)")
        self.form.add_widget("x", "x", self.x_in)
        self.form.add_widget("y", "y", self.y_in)
        f = self.form
        f.add_text("region", "Region x0,x1,y0,y1", "", "Empty = bounding box of the points", "auto")
        f.add_widget("r", "Radii", self.r_in)
        f.add_combo("mode", "Edge correction", list(RIPLEY_MODES))
        self.add_button("Compute K and L", self.compute)
        self.out = self.add_output("Summary")
        self.canvas = self.add_plot("K / L")

    def compute(self) -> None:
        self.guard(self._compute)

    def _compute(self) -> None:
        v = plain_values(self.form)
        region = tuple(parse_float_list(v["region"], "region")) if v["region"] else None
        if region is not None and len(region) != 4:
            raise ParseError("Region needs four numbers: x0, x1, y0, y1.")
        self.run(compute_ripley, self._show, self.x_in.array(), self.y_in.array(), region,
                 self.r_in.array(), v["mode"])

    def _show(self, r: Dict[str, Any]) -> None:
        self.out.show_text(f"{r['n']} points, region {fmt(r['region'])}, mode {r['mode']}\n"
                           f"max |L(r) - r| = {np.nanmax(np.abs(r['L'] - r['radii'])):.6g}"
                           + _warn_text(r["warnings"]))
        fig = self.canvas.figure
        fig.clear()
        ax1, ax2 = fig.subplots(1, 2)
        ax1.plot(r["radii"], r["K"], label="K(r)")
        ax1.plot(r["radii"], r["poisson"], "--", label="Poisson")
        ax1.legend()
        ax1.set_xlabel("r")
        ax2.plot(r["radii"], r["L"] - r["radii"], label="L(r) - r")
        ax2.axhline(0, color="k", ls="--", lw=0.8)
        ax2.legend()
        ax2.set_xlabel("r")
        self.canvas.redraw()


# --------------------------------------------------------------------------- #
SPECS = [
    ModuleSpec("stats_sigmaclip", "Sigma Clipping", CATEGORY, SigmaClipPanel,
               "sigma_clip, SigmaClip and sigma_clipped_stats"),
    ModuleSpec("stats_robust", "Robust Statistics", CATEGORY, RobustPanel,
               "Biweight estimators, MAD, midcovariance/midcorrelation"),
    ModuleSpec("stats_resampling", "Bootstrap & Jackknife", CATEGORY, ResamplingPanel,
               "Resampling errors for any statistic"),
    ModuleSpec("stats_binomial", "Binomial Intervals", CATEGORY, BinomialPanel,
               "binom_conf_interval: wilson, jeffreys, flat, wald"),
    ModuleSpec("stats_binned_binomial", "Binned Binomial Proportion", CATEGORY, BinnedBinomialPanel,
               "binned_binom_proportion"),
    ModuleSpec("stats_poisson", "Poisson Intervals", CATEGORY, PoissonPanel,
               "poisson_conf_interval, all interval types"),
    ModuleSpec("stats_histogram", "Histogram Binning", CATEGORY, HistogramPanel,
               "Knuth, Scott, Freedman, Bayesian blocks, fixed bins"),
    ModuleSpec("stats_blocks", "Bayesian Blocks", CATEGORY, BayesianBlocksPanel,
               "bayesian_blocks with events / regular_events / measures"),
    ModuleSpec("stats_circular", "Circular Statistics", CATEGORY, CircularPanel,
               "circmean, circvar, Rayleigh, V-test, von Mises MLE, correlation"),
    ModuleSpec("stats_kuiper", "Kuiper Test", CATEGORY, KuiperPanel, "kuiper and kuiper_two"),
    ModuleSpec("stats_ripley", "Ripley's K", CATEGORY, RipleyPanel,
               "RipleysKEstimator: K and L functions"),
    ModuleSpec("stats_infocrit", "Information Criteria", CATEGORY, InfoCriteriaPanel,
               "AIC / BIC from log-likelihood or least squares"),
    ModuleSpec("stats_snr", "CCD Signal-to-Noise", CATEGORY, SnrPanel,
               "signal_to_noise_oir_ccd"),
    ModuleSpec("stats_gauss_width", "Gaussian FWHM / Sigma", CATEGORY, GaussianWidthPanel,
               "gaussian_fwhm_to_sigma and gaussian_sigma_to_fwhm"),
]
