"""astropy.nddata: NDData/CCDData, Cutout2D, block ops, bit masks, arithmetic, utils."""
from __future__ import annotations

import re
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

import numpy as np
from astropy import units as u
from astropy.nddata import (
    CCDData, Cutout2D, InverseVariance, NDData, NDDataArray, NDDataRef, StdDevUncertainty,
    UnknownUncertainty, VarianceUncertainty, add_array, bitfield_to_boolean_mask,
    block_reduce, block_replicate, extend_bit_flag_map, extract_array,
    interpret_bit_flags, overlap_slices, subpixel_indices,
)
from astropy.stats import sigma_clipped_stats

from ..core.parsing import (ParseError, parse_array, parse_float, parse_int, parse_quantity,
                            parse_skycoord, parse_unit, safe_eval)
from ..core.registry import ModuleSpec
from ..core.widgets import ModulePanel
from ..core.workspace import Workspace
from ._images import (ImageSelector, array_expr, as_array, axes_row, image_data, show_array, stats_text,
                      unique_name, wcs_of)

CATEGORY = "Images"
UNCERTAINTY_TYPES: Dict[str, Optional[type]] = {
    "none": None, "StdDev": StdDevUncertainty, "Variance": VarianceUncertainty,
    "InverseVariance": InverseVariance, "Unknown": UnknownUncertainty,
}
BLOCK_FUNCS: Dict[str, Callable[..., Any]] = {
    "sum": np.sum, "mean": np.mean, "median": np.median, "min": np.min, "max": np.max,
    "nansum": np.nansum, "nanmean": np.nanmean, "nanmedian": np.nanmedian,
}


# --------------------------------------------------------------------------- #
# Pure helpers (unit-tested without any GUI)
# --------------------------------------------------------------------------- #
def build_nddata(src: Any, kind: str = "NDData", unit_text: str = "", unc_kind: str = "none",
                 unc_text: str = "", mask_text: str = "") -> NDData:
    """Create NDData / NDDataRef / CCDData from an array-like or NDData ``src``."""
    data = as_array(src)
    if data.ndim == 0:
        raise ParseError("Data must have at least one dimension.")
    unit = parse_unit(unit_text) if unit_text.strip() else getattr(src, "unit", None)
    if kind == "CCDData" and unit is None:
        unit = u.adu
    if isinstance(src, u.Quantity) and unit is None:
        unit = src.unit

    uncertainty = None
    cls = UNCERTAINTY_TYPES.get(unc_kind)
    if unc_kind not in UNCERTAINTY_TYPES:
        raise ParseError(f"Unknown uncertainty type {unc_kind!r}.")
    if cls is not None:
        text = unc_text.strip()
        if not text:
            uncertainty = getattr(src, "uncertainty", None)
            if uncertainty is None or not isinstance(uncertainty, cls):
                raise ParseError("Give an uncertainty value, an expression in 'data', or 'poisson'.")
        else:
            if text.lower() == "poisson":
                values = np.sqrt(np.abs(data.astype(float)))
            else:
                values = np.asarray(safe_eval(text, {"data": data.astype(float)}), dtype=float)
            try:
                values = np.broadcast_to(values, data.shape).copy()
            except ValueError:
                raise ParseError(f"Uncertainty shape {values.shape} does not match data "
                                 f"shape {data.shape}.") from None
            uncertainty = cls(values)

    mask = getattr(src, "mask", None) if isinstance(src, NDData) else None
    text = mask_text.strip()
    if text:
        if text.lower() == "nonfinite":
            mask = ~np.isfinite(data.astype(float))
        else:
            mask = np.asarray(array_expr(text, {"data": data}), dtype=bool)
            try:
                mask = np.broadcast_to(mask, data.shape).copy()
            except ValueError:
                raise ParseError("Mask shape does not match the data.") from None
    wcs = wcs_of(src)
    meta = getattr(src, "meta", None) if isinstance(src, NDData) else None
    meta = meta if meta is not None else {}
    cls_out = {"NDData": NDData, "NDDataArray": NDDataArray, "NDDataRef": NDDataRef,
               "CCDData": CCDData}.get(kind)
    if cls_out is None:
        raise ParseError(f"Unknown container type {kind!r}.")
    return cls_out(data, uncertainty=uncertainty, mask=mask, wcs=wcs, meta=meta, unit=unit)


def describe_nd(nd: Any) -> str:
    """Multi-line human summary of an NDData-like (or array) object."""
    if not isinstance(nd, NDData):
        arr = as_array(nd)
        return f"{type(nd).__name__} shape={arr.shape} dtype={arr.dtype}\n\n{stats_text(arr)}"
    unc = nd.uncertainty
    lines = [f"type        : {type(nd).__name__}",
             f"shape/dtype : {nd.data.shape} / {nd.data.dtype}",
             f"unit        : {nd.unit if nd.unit is not None else '-'}",
             f"uncertainty : {type(unc).__name__ if unc is not None else '-'}"
             + (f" (unit {unc.unit})" if unc is not None and unc.unit is not None else ""),
             f"mask        : {'-' if nd.mask is None else f'{int(np.count_nonzero(nd.mask))} masked'}",
             f"wcs         : {'yes, ' + str(nd.wcs.naxis) + ' axes' if nd.wcs is not None else '-'}",
             f"meta keys   : {len(nd.meta)}", "", stats_text(image_data(nd))]
    return "\n".join(lines)


def to_ccd(nd: NDData) -> CCDData:
    if isinstance(nd, CCDData):
        return nd
    return CCDData(nd.data, unit=nd.unit or u.adu, uncertainty=nd.uncertainty, mask=nd.mask,
                   wcs=nd.wcs, meta=nd.meta)


def save_fits(nd: NDData, path: str) -> None:
    to_ccd(nd).write(path, overwrite=True)


def parse_size(text: str) -> Union[int, Tuple[int, ...], u.Quantity, Tuple[u.Quantity, ...]]:
    """``'50'``, ``'30, 20'`` (ny, nx) or angular ``'30 arcsec'`` / ``'1 arcmin, 2 arcmin'``."""
    tokens = [t.strip() for t in text.split(",") if t.strip()]
    if not tokens or len(tokens) > 2:
        raise ParseError("Size needs one or two values (ny, nx).")
    out: List[Any] = []
    for tok in tokens:
        if re.fullmatch(r"\d+", tok):
            out.append(int(tok))
        else:
            q = parse_quantity(tok, u.pix, "size")
            if q.value <= 0:
                raise ParseError("Size must be positive.")
            out.append(q)
    if any(isinstance(v, int) and v <= 0 for v in out):
        raise ParseError("Size must be positive.")
    if all(isinstance(v, int) for v in out):
        return out[0] if len(out) == 1 else tuple(out)
    out = [v if isinstance(v, u.Quantity) else v * u.pix for v in out]
    return out[0] if len(out) == 1 else tuple(out)


def parse_block_size(text: str) -> Union[int, Tuple[int, ...]]:
    tokens = [t for t in re.split(r"[\s,;x]+", text.strip()) if t]
    if not tokens:
        raise ParseError("Block size is empty.")
    vals = tuple(parse_int(t, "block size") for t in tokens)
    if any(v < 1 for v in vals):
        raise ParseError("Block size must be >= 1.")
    return vals[0] if len(vals) == 1 else vals


def make_cutout(nd: Any, pos_text: str, sky: bool, size_text: str, mode: str,
                fill_text: str = "nan") -> Cutout2D:
    data = as_array(nd)
    if data.ndim != 2:
        raise ParseError(f"Cutout2D needs a 2-D image, got {data.ndim}-D data.")
    wcs = wcs_of(nd)
    if sky:
        if wcs is None:
            raise ParseError("Sky positions need an image with a WCS.")
        position: Any = parse_skycoord(pos_text)
    else:
        nums = [t for t in re.split(r"[\s,;]+", pos_text.strip()) if t]
        if len(nums) != 2:
            raise ParseError("Pixel position needs 'x y'.")
        position = (parse_float(nums[0], "x"), parse_float(nums[1], "y"))
    size = parse_size(size_text)
    if not sky and not isinstance(size, (int, tuple)):
        if any(isinstance(s, u.Quantity) and s.unit != u.pix for s in np.atleast_1d(size)) \
                and wcs is None:
            raise ParseError("Angular sizes need an image with a WCS.")
    return Cutout2D(data, position, size, wcs=wcs, mode=mode,
                    fill_value=parse_float(fill_text, "fill value"), copy=True)


# --------------------------------------------------------------------------- #
# Panels
# --------------------------------------------------------------------------- #
class _Base(ModulePanel):
    def __init__(self, ws: Workspace) -> None:
        super().__init__(ws)
        self.src = ImageSelector(ws)
        self.form.add_widget("src", "Image", self.src)

    def store(self, obj: Any, name: str, base: str) -> str:
        final = self.ws.put(unique_name(self.ws, name or base), obj)
        self.ws.log(f"stored {final} ({type(obj).__name__})")
        return final


class NDDataPanel(_Base):
    def __init__(self, ws: Workspace) -> None:
        super().__init__(ws)
        f = self.form
        f.add_combo("kind", "Container", ["NDData", "NDDataRef", "NDDataArray", "CCDData"],
                    "CCDData requires a unit (defaults to adu)")
        f.add_text("unit", "Unit", "", "e.g. adu, electron, Jy/beam; empty keeps the source unit")
        f.add_combo("unc", "Uncertainty", list(UNCERTAINTY_TYPES), "Uncertainty class")
        f.add_text("unc_val", "Unc. value", "poisson",
                   "number, expression in 'data' (e.g. 0.1*data), or 'poisson' (sqrt|data|)")
        f.add_text("mask", "Mask", "", "empty: none, 'nonfinite', or expression like data > 60000")
        f.add_text("name", "Store as", "nddata", "workspace name")
        self.out = self.add_output("Summary")
        self.plot = self.add_plot("Image")
        self.add_button("Build && store", self.build)
        self.add_button("Describe selected image", self.describe)
        self.add_button("Save as FITS...", self.save)
        self.last: Optional[NDData] = None

    def build(self) -> None:
        self.guard(self._build)

    def _build(self) -> None:
        v = self.form
        nd = build_nddata(self.src.obj(), v.value("kind"), v.value("unit"), v.value("unc"),
                          v.value("unc_val"), v.value("mask"))
        self.last = nd
        self.store(nd, v.value("name"), "nddata")
        self._show(nd)

    def describe(self) -> None:
        self.guard(lambda: self._show(self.src.obj()))

    def _show(self, nd: Any) -> None:
        self.out.show_text(describe_nd(nd))
        ax = axes_row(self.plot, 1)[0]
        show_array(ax, image_data(nd), type(nd).__name__)
        self.plot.redraw()

    def save(self) -> None:
        def go() -> None:
            nd = self.last or self.src.obj()
            if not isinstance(nd, NDData):
                nd = build_nddata(nd)
            path = self.ask_save_path("Save FITS", "FITS (*.fits)", "image.fits")
            if path:
                save_fits(nd, path)
                self.set_status(f"Saved {path}")
        self.guard(go)


class CutoutPanel(_Base):
    def __init__(self, ws: Workspace) -> None:
        super().__init__(ws)
        f = self.form
        f.add_combo("space", "Position in", ["pixel", "sky"], "pixel: 'x y' (0-based); sky: any SkyCoord text")
        f.add_text("pos", "Position", "64 64", "e.g. '64 64' or '10.68 41.27' or '00h42m44s +41d16m'")
        f.add_text("size", "Size", "40", "'n' square, 'ny, nx', or angular '30 arcsec' (needs WCS)")
        f.add_combo("mode", "Mode", ["trim", "partial", "strict"],
                    "trim: cut at edges; partial: fill outside; strict: error if outside")
        f.add_text("fill", "Fill value", "nan", "used by partial mode")
        f.add_text("name", "Store as", "cutout")
        self.out = self.add_output("Cutout info")
        self.plot = self.add_plot("Plot")
        self.add_button("Make cutout", self.make)

    def make(self) -> None:
        self.guard(self._make)

    def _make(self) -> None:
        v, nd = self.form, self.src.obj()
        cut = make_cutout(nd, v.value("pos"), v.value("space") == "sky", v.value("size"),
                          v.value("mode"), v.value("fill"))
        self.store(NDData(cut.data, wcs=cut.wcs, unit=getattr(nd, "unit", None)),
                   v.value("name"), "cutout")
        self.out.show_text(
            f"shape                 : {cut.shape}\n"
            f"center (original px)  : {cut.center_original}\n"
            f"center (cutout px)    : {cut.center_cutout}\n"
            f"input pos in cutout   : {cut.input_position_cutout}\n"
            f"bbox original (y,x)   : {cut.bbox_original}\n"
            f"origin original (x,y) : {cut.origin_original}\n"
            f"slices original       : {cut.slices_original}\n"
            f"WCS propagated        : {cut.wcs is not None}")
        a0, a1 = axes_row(self.plot, 2)
        show_array(a0, image_data(nd), "Original")
        cut.plot_on_original(ax=a0, color="red")
        show_array(a1, cut.data, "Cutout")
        self.plot.redraw()


class BlockPanel(_Base):
    def __init__(self, ws: Workspace) -> None:
        super().__init__(ws)
        f = self.form
        f.add_combo("op", "Operation", ["block_reduce", "block_replicate"])
        f.add_text("block", "Block size", "2", "'n' or per-axis 'ny, nx' (numpy axis order)")
        f.add_combo("func", "Function", list(BLOCK_FUNCS), "block_reduce only")
        f.add_check("conserve", "Conserve sum", True, "block_replicate: divide by block area")
        f.add_text("name", "Store as", "blocked")
        self.out = self.add_output("Result")
        self.plot = self.add_plot("Plot")
        self.add_button("Apply", self.apply)

    def apply(self) -> None:
        self.guard(self._apply)

    def _apply(self) -> None:
        v, nd = self.form, self.src.obj()
        data = image_data(nd)
        block = parse_block_size(v.value("block"))
        if isinstance(block, tuple) and len(block) != data.ndim:
            raise ParseError(f"Block size needs {data.ndim} values for {data.ndim}-D data.")
        op, func, conserve = v.value("op"), BLOCK_FUNCS[v.value("func")], v.value("conserve")

        def work() -> np.ndarray:
            if op == "block_reduce":
                return block_reduce(data, block, func=func)
            return block_replicate(data, block, conserve_sum=conserve)

        def done(res: np.ndarray) -> None:
            self.store(NDData(res, unit=getattr(nd, "unit", None)), v.value("name"), "blocked")
            self.out.show_text(f"{op}: {data.shape} -> {res.shape}\n"
                               f"sum before : {np.nansum(data):.8g}\nsum after  : {np.nansum(res):.8g}")
            a0, a1 = axes_row(self.plot, 2)
            show_array(a0, data, "Input")
            show_array(a1, res, "Output")
            self.plot.redraw()

        self.run(work, done)


class BitMaskPanel(ModulePanel):
    def __init__(self, ws: Workspace) -> None:
        super().__init__(ws)
        f = self.form
        f.add_text("bits", "Bit field", "0, 1, 2, 3, 4, 5, 8, 16, 17",
                   "integers or expression such as arange(0, 33)")
        self.src = ImageSelector(ws)
        f.add_widget("src", "...or workspace", self.src)
        f.add_check("use_ws", "Use workspace image", False, "mask a DQ image instead of the text")
        f.add_text("ignore", "Ignore flags", "1, 4",
                   "int, comma/'+'-separated ints, names (with map), '~' prefix flips; empty: none")
        f.add_check("flip", "Flip bits", False, "ignore_flags: treat listed flags as the ones to *keep*")
        f.add_check("good", "good_mask_value = True", False,
                    "value of unmasked (good) pixels in the output mask")
        f.add_text("names", "Flag names", "CR=1, HOT=4, DEAD=16",
                   "NAME=bit pairs; usable in 'Ignore flags'")
        f.add_text("name", "Store as", "bitmask")
        self.out = self.add_output("Result")
        self.add_button("Make boolean mask", self.make)
        self.add_button("Interpret flags only", self.interpret)

    def _flag_map(self) -> Any:
        text = self.form.value("names")
        if not text:
            return None
        pairs: Dict[str, int] = {}
        for tok in re.split(r"[,;\s]+", text):
            if not tok:
                continue
            m = re.fullmatch(r"([A-Za-z_]\w*)=(\d+)", tok)
            if not m:
                raise ParseError(f"Flag name {tok!r}: expected NAME=power_of_two.")
            pairs[m.group(1)] = int(m.group(2))
        return extend_bit_flag_map("UserFlags", **pairs) if pairs else None

    def _ignore(self) -> Any:
        text = self.form.value("ignore")
        return int(text) if re.fullmatch(r"-?\d+", text) else (text or 0)

    def interpret(self) -> None:
        def go() -> None:
            try:
                value = interpret_bit_flags(self._ignore() or None, flip_bits=self.form.value("flip") or None,
                                            flag_name_map=self._flag_map())
            except Exception as exc:  # noqa: BLE001
                raise ParseError(f"Cannot interpret flags: {exc}") from exc
            self.out.show_text(f"interpret_bit_flags -> {value}  (binary {bin(value) if value else '0'})")
        self.guard(go)

    def make(self) -> None:
        self.guard(self._make)

    def _make(self) -> None:
        v = self.form
        field = as_array(self.src.obj()) if v.value("use_ws") else parse_array(v.value("bits"))
        field = np.asarray(field)
        if field.dtype.kind == "f":
            if not np.all(np.isfinite(field)) or np.any(field != np.round(field)):
                raise ParseError("Bit field must contain finite integers.")
            field = field.astype(np.int64)
        flag_map, ignore = self._flag_map(), self._ignore()
        flip, good = v.value("flip") or None, v.value("good")

        def work() -> np.ndarray:
            try:
                return bitfield_to_boolean_mask(field, ignore_flags=ignore, flip_bits=flip,
                                                good_mask_value=good, flag_name_map=flag_map)
            except (ValueError, TypeError) as exc:
                raise ParseError(f"Bit mask error: {exc}") from exc

        def done(mask: np.ndarray) -> None:
            self.ws.put(unique_name(self.ws, v.value("name") or "bitmask"), mask)
            lines = [f"mask dtype={mask.dtype} shape={mask.shape} true={int(mask.sum())}/{mask.size}"]
            if field.size <= 64:
                lines += [f"{int(b):>8d}  {int(b):>12b}  -> {bool(m)}"
                          for b, m in zip(field.ravel(), mask.ravel())]
            self.out.show_text("\n".join(lines))

        self.run(work, done)


def wcs_strictly_equal(a: Any, b: Any) -> bool:
    """compare_wcs callable: equal WCS (or both absent) pass, anything else is an error."""
    if a is None and b is None:
        return True
    return a is not None and b is not None and bool(a.wcs.compare(b.wcs))


class ArithmeticPanel(ModulePanel):
    HANDLE_MASK = {"logical_or": np.logical_or, "logical_and": np.logical_and,
                   "bitwise_or": np.bitwise_or, "first_found": "first_found", "none": None}

    def __init__(self, ws: Workspace) -> None:
        super().__init__(ws)
        f = self.form
        self.a = ImageSelector(ws, (NDData, np.ndarray, u.Quantity), with_buttons=True)
        self.b = ImageSelector(ws, (NDData, np.ndarray, u.Quantity), with_buttons=False)
        f.add_widget("a", "Operand A", self.a)
        f.add_combo("op", "Operation", ["add", "subtract", "multiply", "divide"])
        f.add_combo("bmode", "Operand B is", ["workspace object", "constant"])
        f.add_widget("b", "B (workspace)", self.b)
        f.add_text("const", "B (constant)", "1", "number or quantity e.g. '2.5 adu'")
        f.add_check("prop", "Propagate uncertainty", True)
        f.add_float("corr", "Correlation", 0.0, -1.0, 1.0, 3, "uncertainty correlation (0..1)")
        f.add_combo("mask", "handle_mask", list(self.HANDLE_MASK), "how masks combine")
        f.add_combo("meta", "handle_meta", ["first_found", "none"])
        f.add_combo("wcs", "compare_wcs", ["first_found", "strict", "none"],
                    "first_found: keep the first WCS; strict: operands must have equal WCS; "
                    "none: no check, result has no WCS")
        f.add_text("name", "Store as", "nd_result")
        self.out = self.add_output("Result")
        self.plot = self.add_plot("Plot")
        self.add_button("Compute", self.compute)

    def compute(self) -> None:
        self.guard(self._compute)

    @staticmethod
    def _wrap(obj: Any) -> NDDataRef:
        if isinstance(obj, NDData):
            return NDDataRef(obj)
        return NDDataRef(as_array(obj), unit=obj.unit if isinstance(obj, u.Quantity) else None)

    def _compute(self) -> None:
        v = self.form
        a = self._wrap(self.a.obj())
        if v.value("bmode") == "constant":
            text = v.value("const")
            try:
                operand: Any = float(text)
            except ValueError:
                operand = parse_quantity(text, name="constant")
        else:
            operand = self._wrap(self.b.obj())
        kwargs = dict(propagate_uncertainties=v.value("prop"), uncertainty_correlation=v.value("corr"),
                      handle_mask=self.HANDLE_MASK[v.value("mask")],
                      handle_meta=None if v.value("meta") == "none" else "first_found",
                      compare_wcs={"none": None, "strict": wcs_strictly_equal,
                                   "first_found": "first_found"}[v.value("wcs")])
        op = getattr(a, v.value("op"))

        def work() -> NDDataRef:
            try:
                return op(operand, **kwargs)
            except u.UnitConversionError as exc:
                raise ParseError(f"Unit mismatch: {exc}") from exc

        def done(res: NDDataRef) -> None:
            self.ws.put(unique_name(self.ws, v.value("name") or "nd_result"), res)
            self.out.show_text(describe_nd(res))
            ax0, ax1 = axes_row(self.plot, 2)
            show_array(ax0, image_data(res), "Result")
            if res.uncertainty is not None:
                show_array(ax1, np.asarray(res.uncertainty.array),
                           f"{type(res.uncertainty).__name__}")
            else:
                ax1.axis("off")
            self.plot.redraw()

        self.run(work, done)


class ArrayUtilsPanel(_Base):
    def __init__(self, ws: Workspace) -> None:
        super().__init__(ws)
        f = self.form
        f.add_combo("op", "Operation", ["slice (NDSlicingMixin)", "overlap_slices", "extract_array",
                                        "add_array", "subpixel_indices"])
        f.add_text("slice", "Slice", "10:50, 20:60", "numpy-style, e.g. '10:50, ::2' (slice op)")
        f.add_text("shape", "Small shape", "20, 20", "'ny, nx' of the small array (overlap/extract)")
        f.add_text("pos", "Position", "5, 5", "'y, x' of the small array centre in the large array")
        f.add_combo("mode", "Mode", ["partial", "trim", "strict"])
        f.add_text("fill", "Fill value", "nan", "extract_array, partial mode")
        self.small = ImageSelector(ws, with_buttons=False)
        f.add_widget("small", "Small array (add)", self.small)
        f.add_text("name", "Store as", "util_result")
        self.out = self.add_output("Result")
        self.plot = self.add_plot("Plot")
        self.add_button("Apply", self.apply)

    @staticmethod
    def _ints(text: str, name: str, n: int) -> Tuple[float, ...]:
        parts = [p for p in re.split(r"[\s,;]+", text.strip()) if p]
        if len(parts) != n:
            raise ParseError(f"{name}: expected {n} values.")
        return tuple(parse_float(p, name) for p in parts)

    def apply(self) -> None:
        self.guard(self._apply)

    def _apply(self) -> None:
        v, nd = self.form, self.src.obj()
        op = v.value("op")
        data = as_array(nd)
        name = v.value("name") or "util_result"
        if op.startswith("slice"):
            text = v.value("slice").strip()
            if not text:
                raise ParseError("Slice is empty.")
            slc = safe_eval(f"s_[{text}]", {"s_": np.s_})
            wrapped = NDDataRef(nd) if isinstance(nd, NDData) else NDDataRef(data)
            res = wrapped[slc]
            self.ws.put(unique_name(self.ws, name), res)
            self.out.show_text(describe_nd(res))
            show = image_data(res)
        else:
            pos = self._ints(v.value("pos"), "position", data.ndim)
            mode = v.value("mode")
            if op == "subpixel_indices":
                sub = int(parse_float(v.value("fill"), "subsampling")) if v.value("fill") else 1
                if sub < 1:
                    raise ParseError("Subsampling (use the Fill value field) must be >= 1.")
                self.out.show_text(f"subpixel_indices({pos}, {sub}) = {subpixel_indices(pos, sub)}")
                return
            shape = tuple(int(s) for s in self._ints(v.value("shape"), "shape", data.ndim))
            if op == "overlap_slices":
                big, small = overlap_slices(data.shape, shape, pos, mode=mode)
                self.out.show_text(f"slices_large = {big}\nslices_small = {small}")
                return
            if op == "extract_array":
                res = extract_array(data, shape, pos, mode=mode,
                                    fill_value=parse_float(v.value("fill"), "fill"))
            else:
                small_arr = as_array(self.small.obj())
                if small_arr.ndim != data.ndim:
                    raise ParseError("Small array must have the same dimensionality.")
                res = add_array(np.array(data, dtype=float), small_arr, pos)
            self.ws.put(unique_name(self.ws, name), NDData(res))
            self.out.show_text(f"{op}: result shape {res.shape}\n\n{stats_text(res)}")
            show = res
        ax = axes_row(self.plot, 1)[0]
        show_array(ax, show, "Result")
        self.plot.redraw()


class CalibrationPanel(_Base):
    """bias / dark / flat arithmetic with uncertainty propagation + image statistics."""

    def __init__(self, ws: Workspace) -> None:
        super().__init__(ws)
        f = self.form
        f.add_check("use_bias", "Subtract bias", False)
        self.bias = ImageSelector(ws, with_buttons=False)
        f.add_widget("bias", "Bias frame", self.bias)
        f.add_check("use_dark", "Subtract dark", False)
        self.dark = ImageSelector(ws, with_buttons=False)
        f.add_widget("dark", "Dark frame", self.dark)
        f.add_float("scale", "Dark scale", 1.0, 0.0, 1e9, 6, "exposure(raw)/exposure(dark)")
        f.add_check("use_flat", "Divide by flat", False)
        self.flat = ImageSelector(ws, with_buttons=False)
        f.add_widget("flat", "Flat frame", self.flat)
        f.add_check("clip", "Sigma-clipped stats", True, "statistics: 3-sigma clipped mean/median/std")
        f.add_text("name", "Store as", "calibrated")
        self.out = self.add_output("Result")
        self.plot = self.add_plot("Plot")
        self.add_button("Calibrate", self.calibrate)
        self.add_button("Statistics", self.statistics)

    def calibrate(self) -> None:
        self.guard(self._calibrate)

    def _calibrate(self) -> None:
        v = self.form
        raw = ArithmeticPanel._wrap(self.src.obj())
        bias = ArithmeticPanel._wrap(self.bias.obj()) if v.value("use_bias") else None
        dark = ArithmeticPanel._wrap(self.dark.obj()) if v.value("use_dark") else None
        flat = ArithmeticPanel._wrap(self.flat.obj()) if v.value("use_flat") else None
        scale = v.value("scale")
        if not (bias or dark or flat):
            raise ParseError("Select at least one calibration frame.")

        def work() -> NDDataRef:
            res = raw
            kw = dict(compare_wcs=None, handle_meta="first_found")
            if bias is not None:
                res = res.subtract(bias, **kw)
            if dark is not None:
                d = dark
                if bias is not None:
                    d = d.subtract(bias, **kw)
                res = res.subtract(d.multiply(scale, **kw), **kw)
            if flat is not None:
                fdata = image_data(flat)
                norm = float(np.nanmean(fdata))
                if not np.isfinite(norm) or norm == 0:
                    raise ParseError("Flat field has a zero or non-finite mean.")
                nflat = flat.divide(norm * flat.unit if flat.unit is not None else norm, **kw)
                res = res.divide(nflat, **kw)
            return res

        def done(res: NDDataRef) -> None:
            self.ws.put(unique_name(self.ws, v.value("name") or "calibrated"), res)
            self.out.show_text(describe_nd(res))
            self._plot(image_data(res), "Calibrated")

        self.run(work, done)

    def statistics(self) -> None:
        self.guard(self._statistics)

    def _statistics(self) -> None:
        nd = self.src.obj()
        data, clip = image_data(nd), self.form.value("clip")

        def work() -> str:
            text = stats_text(data)
            if clip and np.isfinite(data).any():
                mean, med, std = sigma_clipped_stats(data, sigma=3.0)
                text += f"\n\n3-sigma clipped: mean={mean:.6g} median={med:.6g} std={std:.6g}"
            return text

        def done(text: str) -> None:
            self.out.show_text(text)
            self._plot(data, "Image")

        self.run(work, done)

    def _plot(self, data: np.ndarray, title: str) -> None:
        a0, a1 = axes_row(self.plot, 2)
        show_array(a0, data, title)
        finite = data[np.isfinite(data)]
        if finite.size:
            a1.hist(finite.ravel(), bins=100)
            a1.set_yscale("log")
        a1.set_title("Histogram", fontsize=9)
        self.plot.redraw()


def _spec(key: str, title: str, cls: type, desc: str) -> ModuleSpec:
    return ModuleSpec(key, title, CATEGORY, lambda ws: cls(ws), desc)


SPECS = [
    _spec("nddata", "NDData / CCDData", NDDataPanel, "Build NDData, NDDataRef or CCDData; save FITS"),
    _spec("cutout2d", "Cutout2D", CutoutPanel, "Cut sub-images by pixel or sky position"),
    _spec("blocks", "Block reduce / replicate", BlockPanel, "Rebin or upsample images"),
    _spec("bitmask", "Bit masks", BitMaskPanel, "bitfield_to_boolean_mask and interpret_bit_flags"),
    _spec("ndarith", "NDData arithmetic", ArithmeticPanel,
          "Add/subtract/multiply/divide with uncertainty propagation"),
    _spec("nd_utils", "Slice / extract / add", ArrayUtilsPanel,
          "NDData slicing, overlap_slices, extract_array, add_array"),
    _spec("ccd_calib", "Calibration & statistics", CalibrationPanel,
          "Bias/dark/flat arithmetic and image statistics"),
]
