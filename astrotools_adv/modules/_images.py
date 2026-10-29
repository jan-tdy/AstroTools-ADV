"""Helpers shared by the image-oriented panels (nddata, wcs, convolution, visualization)."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional, Tuple

import numpy as np
from astropy import units as u
from astropy.io import fits
from astropy.nddata import NDData
from astropy.wcs import WCS
from PyQt5.QtWidgets import QHBoxLayout, QPushButton, QWidget

from ..core.parsing import ParseError
from ..core.widgets import WorkspaceCombo, error_box
from ..core.workspace import Workspace

IMAGE_TYPES = (np.ndarray, NDData, u.Quantity)


def unique_name(ws: Workspace, base: str) -> str:
    """``base`` or ``base_2``, ``base_3``... whichever is free in the workspace."""
    base = (base or "result").strip() or "result"
    if base not in ws:
        return base
    i = 2
    while f"{base}_{i}" in ws:
        i += 1
    return f"{base}_{i}"


def as_array(obj: Any) -> np.ndarray:
    """Raw numeric array of an ndarray / Quantity / NDData (mask ignored)."""
    if isinstance(obj, NDData):
        obj = obj.data
    if isinstance(obj, u.Quantity):
        obj = obj.value
    if isinstance(obj, np.ma.MaskedArray):
        obj = obj.filled(np.nan) if obj.dtype.kind == "f" else obj.data
    try:
        return np.asarray(obj)
    except Exception as exc:  # noqa: BLE001
        raise ParseError(f"Cannot interpret {type(obj).__name__} as an array ({exc}).") from None


def image_data(obj: Any, apply_mask: bool = True) -> np.ndarray:
    """Float array; masked pixels of an NDData become NaN when ``apply_mask``."""
    arr = as_array(obj)
    if arr.dtype.kind not in "fc":
        arr = arr.astype(float)
    elif arr.dtype.kind == "c":
        arr = np.abs(arr)
    mask = getattr(obj, "mask", None)
    if apply_mask and mask is not None and np.shape(mask) == arr.shape:
        arr = np.where(np.asarray(mask, dtype=bool), np.nan, arr)
    return arr


def wcs_of(obj: Any) -> Optional[WCS]:
    """The celestial/any WCS attached to an NDData, or ``None``."""
    wcs = getattr(obj, "wcs", None)
    return wcs if isinstance(wcs, WCS) else None


def nice_limits(arr: np.ndarray, lo: float = 1.0, hi: float = 99.0) -> Tuple[float, float]:
    """Percentile display limits that never fail (NaN/empty/constant safe)."""
    finite = np.asarray(arr, dtype=float)
    finite = finite[np.isfinite(finite)]
    if finite.size == 0:
        return 0.0, 1.0
    vmin, vmax = np.percentile(finite, [lo, hi])
    if vmin == vmax:
        vmin, vmax = float(vmin) - 0.5, float(vmax) + 0.5
    return float(vmin), float(vmax)


def synthetic_image(shape: Tuple[int, int] = (128, 128), n_sources: int = 10, noise: float = 3.0,
               background: float = 100.0, seed: int = 0, nan_fraction: float = 0.0) -> np.ndarray:
    """Synthetic frame: background + Gaussian noise + Gaussian "stars" (+ NaN holes)."""
    ny, nx = shape
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:ny, 0:nx]
    img = np.full(shape, float(background))
    for _ in range(max(0, n_sources)):
        x0, y0 = rng.uniform(0, nx), rng.uniform(0, ny)
        amp, sig = rng.uniform(50, 500), rng.uniform(1.2, 3.0)
        img += amp * np.exp(-((xx - x0) ** 2 + (yy - y0) ** 2) / (2 * sig ** 2))
    if noise > 0:
        img += rng.normal(0.0, noise, shape)
    if nan_fraction > 0:
        img[rng.random(shape) < nan_fraction] = np.nan
    return img


def load_fits_image(path: str, ext: Optional[int] = None) -> NDData:
    """First (or ``ext``-th) HDU holding array data -> NDData with WCS/unit/header."""
    with fits.open(path) as hdul:
        if ext is None:
            candidates = [i for i, h in enumerate(hdul)
                          if getattr(h, "data", None) is not None and h.data.ndim >= 1
                          and hasattr(h.data, "dtype") and h.data.dtype.names is None]
            if not candidates:
                raise ParseError(f"{Path(path).name}: no image data found.")
            ext = candidates[0]
        try:
            hdu = hdul[ext]
        except (IndexError, KeyError):
            raise ParseError(f"{Path(path).name}: no HDU {ext!r}.") from None
        if hdu.data is None or hdu.data.dtype.names is not None:
            raise ParseError(f"HDU {ext} does not contain image data.")
        data = np.array(hdu.data)
        data = data.astype(data.dtype.newbyteorder("="), copy=False)
        header = hdu.header.copy()
        wcs: Optional[WCS] = None
        try:
            cand = WCS(header, fobj=hdul)
            if cand.naxis == data.ndim and any(cand.wcs.ctype):
                wcs = cand
        except Exception:  # noqa: BLE001 - a broken WCS must not block loading the data
            wcs = None
    unit = None
    bunit = str(header.get("BUNIT", "")).strip()
    if bunit:
        try:
            parsed = u.Unit(bunit, parse_strict="silent")
            unit = None if isinstance(parsed, u.UnrecognizedUnit) else parsed
        except Exception:  # noqa: BLE001
            unit = None
    return NDData(data, wcs=wcs, unit=unit, meta=header)


class ImageSelector(QWidget):
    """Workspace image picker + "Open FITS" and "Test image" shortcuts."""

    def __init__(self, ws: Workspace, kinds: Tuple[type, ...] = IMAGE_TYPES,
                 with_buttons: bool = True) -> None:
        super().__init__()
        self.ws = ws
        self.combo = WorkspaceCombo(ws, kinds)  # type: ignore[arg-type]
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.combo, 1)
        if with_buttons:
            fits_btn = QPushButton("FITS...")
            fits_btn.setToolTip("Load an image from a FITS file into the workspace")
            fits_btn.clicked.connect(self._open_fits)
            test_btn = QPushButton("Test")
            test_btn.setToolTip("Generate a synthetic noisy star field")
            test_btn.clicked.connect(self.make_test_image)
            lay.addWidget(fits_btn)
            lay.addWidget(test_btn)

    def obj(self) -> Any:
        return self.combo.selected()

    def name(self) -> str:
        return self.combo.currentText()

    def has_selection(self) -> bool:
        return bool(self.combo.currentText())

    def select(self, name: str) -> None:
        idx = self.combo.findText(name)
        if idx >= 0:
            self.combo.setCurrentIndex(idx)

    def load_path(self, path: str) -> str:
        name = self.ws.put(unique_name(self.ws, Path(path).stem), load_fits_image(path))
        self.select(name)
        return name

    def make_test_image(self) -> str:
        name = self.ws.put(unique_name(self.ws, "test_image"), NDData(synthetic_image()))
        self.select(name)
        return name

    def _open_fits(self) -> None:
        from PyQt5.QtWidgets import QFileDialog

        path, _ = QFileDialog.getOpenFileName(self, "Open FITS image", "",
                                              "FITS (*.fits *.fit *.fts *.fz *.gz);;All (*)")
        if path:
            try:
                self.load_path(path)
            except Exception as exc:  # noqa: BLE001
                error_box(self, exc)


def show_array(ax: Any, arr: np.ndarray, title: str = "", cmap: str = "gray", **kwargs: Any):
    """Draw a 1-D line, 2-D image (percentile scaled) or first plane of N-D data."""
    arr = np.asarray(arr)
    if arr.dtype.kind not in "fc":
        arr = arr.astype(float)
    if arr.dtype.kind == "c":
        arr = np.abs(arr)
    if arr.ndim >= 3:
        arr = arr[(0,) * (arr.ndim - 2)]
        title = f"{title} (first plane)".strip()
    artist = None
    if arr.ndim == 0 or arr.size == 0:
        ax.text(0.5, 0.5, "no data", ha="center", va="center", transform=ax.transAxes)
    elif arr.ndim == 1:
        ax.plot(arr, drawstyle="steps-mid")
    else:
        if "vmin" not in kwargs and "vmax" not in kwargs and "norm" not in kwargs:
            kwargs["vmin"], kwargs["vmax"] = nice_limits(arr)
        artist = ax.imshow(arr, origin="lower", cmap=cmap, **kwargs)
    if title:
        ax.set_title(title, fontsize=9)
    return artist


def stats_text(arr: np.ndarray) -> str:
    """Compact robust statistics of the finite values of ``arr``."""
    from astropy.stats import mad_std

    flat = np.asarray(arr, dtype=float).ravel()
    finite = flat[np.isfinite(flat)]
    lines = [f"pixels      : {flat.size}", f"finite      : {finite.size}",
             f"NaN/inf     : {flat.size - finite.size}"]
    if finite.size:
        p = np.percentile(finite, [1, 25, 50, 75, 99])
        lines += [f"min / max   : {finite.min():.6g} / {finite.max():.6g}",
                  f"mean / std  : {finite.mean():.6g} / {finite.std():.6g}",
                  f"median      : {p[2]:.6g}", f"MAD std     : {mad_std(finite):.6g}",
                  f"sum         : {finite.sum():.6g}",
                  "percentiles : 1%={:.6g} 25%={:.6g} 75%={:.6g} 99%={:.6g}".format(
                      p[0], p[1], p[3], p[4])]
    return "\n".join(lines)


def axes_row(canvas: Any, n: int, **subplot_kw: Any) -> list:
    """Clear ``canvas`` and return ``n`` side-by-side axes."""
    canvas.figure.clear()
    return list(canvas.figure.subplots(1, n, squeeze=False, subplot_kw=subplot_kw or None)[0])


_CMP_FUNCS = {"Lt": "less", "LtE": "less_equal", "Gt": "greater", "GtE": "greater_equal",
              "Eq": "equal", "NotEq": "not_equal"}


def array_expr(expr: str, names: dict) -> Any:
    """``safe_eval`` for array expressions: comparisons become element-wise.

    ``core.parsing.safe_eval`` reduces ``a > b`` to a single bool (Python
    chained-comparison semantics), which is wrong for masks such as
    ``data > 60000``. Single comparisons are rewritten to ``np.greater(...)`` etc.
    ``&``/``|``/``~`` combine them as usual.
    """
    import ast

    from ..core.parsing import safe_eval

    try:
        tree = ast.parse(expr.strip(), mode="eval")
    except SyntaxError as exc:
        raise ParseError(f"Syntax error in {expr!r}: {exc.msg}") from None

    class _Rewrite(ast.NodeTransformer):
        def visit_Compare(self, node: ast.Compare) -> ast.AST:
            self.generic_visit(node)
            if len(node.ops) != 1 or type(node.ops[0]).__name__ not in _CMP_FUNCS:
                return node
            func = ast.Attribute(ast.Name("np", ast.Load()), _CMP_FUNCS[type(node.ops[0]).__name__],
                                 ast.Load())
            return ast.Call(func, [node.left, node.comparators[0]], [])

    new = ast.fix_missing_locations(_Rewrite().visit(tree))
    return safe_eval(ast.unparse(new), names)
