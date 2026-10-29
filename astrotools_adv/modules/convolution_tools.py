"""astropy.convolution: kernels, convolve / convolve_fft, NaN interpolation, model convolution."""
from __future__ import annotations

import time
from typing import Any, Dict, Optional, Tuple

import numpy as np
from astropy import units as u
from astropy.convolution import (
    AiryDisk2DKernel, Box1DKernel, Box2DKernel, CustomKernel, Gaussian1DKernel,
    Gaussian2DKernel, Kernel, KernelError, Model1DKernel, Model2DKernel,
    Moffat2DKernel, RickerWavelet1DKernel, RickerWavelet2DKernel, Ring2DKernel, Tophat2DKernel,
    Trapezoid1DKernel, TrapezoidDisk2DKernel, convolve, convolve_fft, convolve_models,
    convolve_models_fft, interpolate_replace_nans,
)
from astropy.modeling import models as apmodels
from astropy.nddata import NDData
from PyQt5.QtWidgets import QComboBox, QDoubleSpinBox, QHBoxLayout, QWidget

from ..core.parsing import ParseError, parse_float, parse_float_list, safe_eval
from ..core.registry import ModuleSpec
from ..core.widgets import ModulePanel, WorkspaceCombo
from ..core.workspace import Workspace
from ._images import ImageSelector, as_array, axes_row, image_data, show_array, unique_name

CATEGORY = "Images"

# name -> (class, ndim, default parameter text)
KERNELS: Dict[str, Tuple[Any, int, str]] = {
    "Gaussian1DKernel": (Gaussian1DKernel, 1, "stddev=2"),
    "Gaussian2DKernel": (Gaussian2DKernel, 2, "x_stddev=2, y_stddev=2, theta=0"),
    "Box1DKernel": (Box1DKernel, 1, "width=5"),
    "Box2DKernel": (Box2DKernel, 2, "width=5"),
    "Tophat2DKernel": (Tophat2DKernel, 2, "radius=3"),
    "Ring2DKernel": (Ring2DKernel, 2, "radius_in=3, width=2"),
    "Trapezoid1DKernel": (Trapezoid1DKernel, 1, "width=5, slope=1"),
    "TrapezoidDisk2DKernel": (TrapezoidDisk2DKernel, 2, "radius=4, slope=1"),
    "RickerWavelet1DKernel (Mexican hat)": (RickerWavelet1DKernel, 1, "width=3"),
    "RickerWavelet2DKernel (Mexican hat)": (RickerWavelet2DKernel, 2, "width=3"),
    "AiryDisk2DKernel": (AiryDisk2DKernel, 2, "radius=3"),
    "Moffat2DKernel": (Moffat2DKernel, 2, "gamma=3, alpha=2.5"),
    "Model1DKernel": (Model1DKernel, 1, "models.Gaussian1D(1, 0, 2)"),
    "Model2DKernel": (Model2DKernel, 2, "models.Gaussian2D(1, 0, 0, 2, 2)"),
    "CustomKernel": (CustomKernel, 0, "(uses the workspace array below)"),
}
CONVOLVE_BOUNDARIES = ["fill", "wrap", "extend", "None"]
FFT_BOUNDARIES = ["fill", "wrap"]
MODEL_NAMES = {"models": apmodels, "dict": dict}


# --------------------------------------------------------------------------- #
# Pure helpers
# --------------------------------------------------------------------------- #
def build_kernel(name: str, params: str, x_size: int = 0, y_size: int = 0, mode: str = "center",
                 factor: int = 10, array: Any = None, normalize: str = "as built") -> Kernel:
    """Create a kernel from a name in :data:`KERNELS` and a ``key=value`` parameter string."""
    if name not in KERNELS:
        raise ParseError(f"Unknown kernel {name!r}.")
    cls, ndim, _ = KERNELS[name]
    try:
        if cls is CustomKernel:
            if array is None:
                raise ParseError("CustomKernel needs a workspace array.")
            arr = np.asarray(as_array(array), dtype=float)
            if arr.ndim not in (1, 2):
                raise ParseError("CustomKernel supports 1-D and 2-D arrays.")
            kernel: Kernel = CustomKernel(arr)
        else:
            kwargs: Dict[str, Any] = {}
            for key, val in (("x_size", x_size), ("y_size", y_size)):
                if val:
                    if val < 1 or val % 2 == 0:
                        raise ParseError(f"{key} must be a positive odd integer.")
                    if key == "y_size" and ndim != 2:
                        continue
                    kwargs[key] = int(val)
            kwargs["mode"] = mode
            if mode == "oversample":
                kwargs["factor"] = int(factor)
            if cls in (Model1DKernel, Model2DKernel):
                model = safe_eval(params, MODEL_NAMES)
                kwargs.setdefault("x_size", 25)
                if ndim == 2:
                    kwargs.setdefault("y_size", kwargs["x_size"])
                kernel = cls(model, **kwargs)
            else:
                values = safe_eval(f"dict({params})", MODEL_NAMES) if params.strip() else {}
                kernel = cls(**values, **kwargs)
    except ParseError:
        raise
    except (TypeError, ValueError, ZeroDivisionError, KernelError) as exc:
        raise ParseError(f"Cannot build {name}: {exc}") from exc
    if np.asarray(kernel.array).size == 0 or not np.all(np.isfinite(kernel.array)):
        raise ParseError("These parameters produce an empty or non-finite kernel.")
    if normalize != "as built":
        kernel.normalize(normalize)
    return kernel


def kernel_info(k: Kernel) -> str:
    arr = np.asarray(k.array)
    return "\n".join([
        f"class      : {type(k).__name__}",
        f"dimension  : {k.dimension}",
        f"shape      : {arr.shape}",
        f"sum        : {arr.sum():.10g}",
        f"min / max  : {arr.min():.6g} / {arr.max():.6g}",
        f"center     : {k.center}",
        f"separable  : {k.separable}",
        f"truncation : {k.truncation:.3g}",
        f"is_bool    : {k.is_bool}",
        f"model      : {getattr(k, 'model', None)!r}",
    ])


def kernel_arithmetic(a: Kernel, b: Optional[Kernel], op: str, scalar: float = 1.0) -> Kernel:
    """``add`` / ``subtract`` / ``convolve`` two kernels or ``scale`` one by ``scalar``."""
    try:
        if op == "scale":
            return a * scalar
        if b is None:
            raise ParseError("A second kernel is required.")
        if a.dimension != b.dimension:
            raise ParseError("Kernels must have the same dimensionality.")
        if op == "add":
            return a + b
        if op == "subtract":
            return a - b
        if op == "convolve":
            pad = [(s // 2, s // 2) for s in b.array.shape]
            full = convolve(np.pad(a.array, pad), b.array, normalize_kernel=False,
                            boundary="fill", fill_value=0.0)
            return CustomKernel(full)
    except ParseError:
        raise
    except (ValueError, KernelError) as exc:
        raise ParseError(f"Kernel arithmetic failed: {exc}") from exc
    raise ParseError(f"Unknown kernel operation {op!r}.")


def run_convolution(data: np.ndarray, kernel: Any, method: str = "convolve",
                    boundary: str = "fill", fill_value: float = 0.0,
                    nan_treatment: str = "interpolate", normalize_kernel: bool = True,
                    preserve_nan: bool = False, mask: Optional[np.ndarray] = None,
                    fft_pad: Optional[bool] = None, psf_pad: Optional[bool] = None,
                    allow_huge: bool = False, crop: bool = True) -> np.ndarray:
    """Thin validated wrapper over ``convolve`` / ``convolve_fft``."""
    karr = np.asarray(kernel.array if isinstance(kernel, Kernel) else kernel)
    if data.ndim != karr.ndim:
        raise ParseError(f"Image is {data.ndim}-D but kernel is {karr.ndim}-D.")
    if data.size == 0:
        raise ParseError("Image is empty.")
    try:
        if method == "convolve":
            return convolve(data, kernel, boundary=None if boundary == "None" else boundary,
                            fill_value=fill_value, nan_treatment=nan_treatment,
                            normalize_kernel=normalize_kernel, mask=mask, preserve_nan=preserve_nan)
        return convolve_fft(data, kernel, boundary=boundary, fill_value=fill_value,
                            nan_treatment=nan_treatment, normalize_kernel=normalize_kernel,
                            preserve_nan=preserve_nan, mask=mask, crop=crop, fft_pad=fft_pad,
                            psf_pad=psf_pad, allow_huge=allow_huge)
    except (ValueError, KernelError, MemoryError) as exc:
        raise ParseError(f"Convolution failed: {exc}") from exc


def quick_gaussian(ndim: int, sigma: float) -> Kernel:
    if sigma <= 0:
        raise ParseError("Sigma must be positive.")
    if ndim == 1:
        return Gaussian1DKernel(sigma)
    if ndim == 2:
        return Gaussian2DKernel(sigma)
    raise ParseError("Only 1-D and 2-D data are supported.")


# --------------------------------------------------------------------------- #
# Widgets / panels
# --------------------------------------------------------------------------- #
class KernelPicker(QWidget):
    """Workspace kernel/array, or a quick Gaussian of given sigma."""

    def __init__(self, ws: Workspace) -> None:
        super().__init__()
        self.mode = QComboBox()
        self.mode.addItems(["Gaussian (quick)", "workspace kernel"])
        self.sigma = QDoubleSpinBox()
        self.sigma.setRange(0.1, 1000)
        self.sigma.setValue(2.0)
        self.sigma.setPrefix("sigma ")
        self.sigma.setToolTip("Standard deviation in pixels")
        self.combo = WorkspaceCombo(ws, (Kernel, np.ndarray))
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        for w in (self.mode, self.sigma, self.combo):
            lay.addWidget(w)

    def kernel(self, ndim: int) -> Any:
        if self.mode.currentText().startswith("Gaussian"):
            return quick_gaussian(ndim, self.sigma.value())
        return self.combo.selected()


class KernelPanel(ModulePanel):
    def __init__(self, ws: Workspace) -> None:
        super().__init__(ws)
        f = self.form
        f.add_combo("kernel", "Kernel", list(KERNELS), "Kernel class")
        f.add_text("params", "Parameters", KERNELS["Gaussian2DKernel"][2],
                   "key=value list; Model kernels: a model expression, e.g. models.Gaussian1D(1,0,2)")
        f.add_int("x_size", "x_size", 0, 0, 10001, "odd size in x; 0 = automatic (8 sigma)")
        f.add_int("y_size", "y_size", 0, 0, 10001, "odd size in y (2-D); 0 = automatic")
        f.add_combo("mode", "Discretization", ["center", "linear_interp", "oversample", "integrate"])
        f.add_int("factor", "Oversample factor", 10, 1, 1000)
        self.arr = ImageSelector(ws, (np.ndarray, u.Quantity, NDData), with_buttons=False)
        f.add_widget("array", "CustomKernel array", self.arr)
        f.add_combo("norm", "Normalize", ["as built", "integral", "peak"])
        f.add_text("name", "Store as", "kernel")
        self.a_combo = WorkspaceCombo(ws, Kernel)
        f.add_widget("a", "Kernel A", self.a_combo)
        self.k2 = WorkspaceCombo(ws, Kernel)
        f.add_widget("k2", "Kernel B", self.k2)
        f.add_combo("op", "Arithmetic", ["add", "subtract", "convolve", "scale"],
                    "A op B; scale multiplies A by the scalar")
        f.add_float("scalar", "Scalar", 2.0, -1e9, 1e9, 6, "scale: multiply A by this")
        self.out = self.add_output("Kernel")
        self.plot = self.add_plot("Preview")
        self.add_button("Build kernel", self.build)
        self.add_button("Kernel arithmetic (A op B)", self.arith)
        f.fields["kernel"].currentTextChanged.connect(self._defaults)
        self.last: Optional[Kernel] = None

    def _defaults(self, name: str) -> None:
        self.form.set_value("params", KERNELS[name][2])

    def build(self) -> None:
        self.guard(self._build)

    def _build(self) -> None:
        v = self.form
        custom = v.value("kernel") == "CustomKernel"
        k = build_kernel(v.value("kernel"), v.value("params"), v.value("x_size"), v.value("y_size"),
                         v.value("mode"), v.value("factor"),
                         self.arr.obj() if custom else None, v.value("norm"))
        self.last = k
        self._publish(k, v.value("name") or "kernel")

    def _publish(self, k: Kernel, name: str) -> None:
        self.ws.put(unique_name(self.ws, name), k)
        self.out.show_text(kernel_info(k))
        ax = axes_row(self.plot, 1)[0]
        arr = np.asarray(k.array)
        if arr.ndim == 1:
            ax.plot(np.arange(arr.size) - arr.size // 2, arr, drawstyle="steps-mid")
            ax.set_xlabel("offset (px)")
        else:
            im = ax.imshow(arr, origin="lower", cmap="viridis")
            self.plot.figure.colorbar(im, ax=ax)
        ax.set_title(type(k).__name__, fontsize=9)
        self.plot.redraw()

    def arith(self) -> None:
        def go() -> None:
            v = self.form
            a = self.a_combo.selected()
            b = self.k2.selected() if v.value("op") != "scale" else None
            res = kernel_arithmetic(a, b, v.value("op"), v.value("scalar"))
            self._publish(res, f"{v.value('op')}_kernel")
        self.guard(go)


class ConvolvePanel(ModulePanel):
    def __init__(self, ws: Workspace) -> None:
        super().__init__(ws)
        f = self.form
        self.img = ImageSelector(ws, (np.ndarray, u.Quantity, NDData))
        f.add_widget("img", "Image", self.img)
        self.kp = KernelPicker(ws)
        f.add_widget("kp", "Kernel", self.kp)
        f.add_combo("method", "Method", ["convolve", "convolve_fft"], "direct vs FFT convolution")
        f.add_combo("boundary", "Boundary", CONVOLVE_BOUNDARIES)
        f.add_text("fill", "Fill value", "0")
        f.add_combo("nan", "NaN treatment", ["interpolate", "fill"])
        f.add_check("norm", "Normalize kernel", True)
        f.add_check("preserve", "Preserve NaN", False, "keep NaN where the input was NaN")
        f.add_check("use_mask", "Use NDData mask", True)
        f.add_combo("fft_pad", "fft_pad", ["auto", "True", "False"], "convolve_fft only")
        f.add_combo("psf_pad", "psf_pad", ["auto", "True", "False"], "convolve_fft only")
        f.add_check("huge", "allow_huge", False, "allow arrays > 1 GB (convolve_fft)")
        f.add_check("crop", "crop", True, "convolve_fft: crop padding")
        f.add_text("name", "Store as", "convolved")
        self.out = self.add_output("Result")
        self.plot = self.add_plot("Before / after")
        self.add_button("Convolve", self.go)
        f.fields["method"].currentTextChanged.connect(self._method_changed)

    def _method_changed(self, method: str) -> None:
        combo = self.form.fields["boundary"]
        combo.clear()
        combo.addItems(FFT_BOUNDARIES if method == "convolve_fft" else CONVOLVE_BOUNDARIES)

    @staticmethod
    def _tri(text: str) -> Optional[bool]:
        return None if text == "auto" else text == "True"

    def go(self) -> None:
        self.guard(self._go)

    def _go(self) -> None:
        v, src = self.form, self.img.obj()
        data = image_data(src, apply_mask=False)
        kernel = self.kp.kernel(data.ndim)
        mask = None
        if v.value("use_mask") and getattr(src, "mask", None) is not None:
            mask = np.asarray(src.mask, dtype=bool)
        opts = dict(method=v.value("method"), boundary=v.value("boundary"),
                    fill_value=parse_float(v.value("fill"), "fill value"),
                    nan_treatment=v.value("nan"), normalize_kernel=v.value("norm"),
                    preserve_nan=v.value("preserve"), mask=mask,
                    fft_pad=self._tri(v.value("fft_pad")), psf_pad=self._tri(v.value("psf_pad")),
                    allow_huge=v.value("huge"), crop=v.value("crop"))
        unit = getattr(src, "unit", None)

        def work() -> Tuple[np.ndarray, float]:
            t0 = time.perf_counter()
            return run_convolution(data, kernel, **opts), time.perf_counter() - t0

        def done(res: Tuple[np.ndarray, float]) -> None:
            out, dt = res
            self.ws.put(unique_name(self.ws, v.value("name") or "convolved"),
                        NDData(out, unit=unit, wcs=getattr(src, "wcs", None)))
            karr = np.asarray(kernel.array if isinstance(kernel, Kernel) else kernel)
            self.out.show_text(
                f"{opts['method']} finished in {dt * 1e3:.1f} ms\n"
                f"shape {out.shape}, NaN count {int(np.isnan(out).sum())}\n"
                f"kernel shape {karr.shape}, kernel sum {karr.sum():.8g}\n"
                f"flux before {np.nansum(data):.8g}   after {np.nansum(out):.8g}")
            a0, a1, a2 = axes_row(self.plot, 3)
            show_array(a0, data, "Input")
            show_array(a1, karr, "Kernel", cmap="viridis")
            show_array(a2, out, "Convolved")
            self.plot.redraw()

        self.run(work, done)


class NanPanel(ModulePanel):
    def __init__(self, ws: Workspace) -> None:
        super().__init__(ws)
        f = self.form
        self.img = ImageSelector(ws, (np.ndarray, u.Quantity, NDData))
        f.add_widget("img", "Image", self.img)
        self.kp = KernelPicker(ws)
        f.add_widget("kp", "Kernel", self.kp)
        f.add_combo("func", "Convolution", ["convolve", "convolve_fft"])
        f.add_float("inject", "Inject NaN fraction", 0.0, 0.0, 0.9, 3,
                    "testing aid: set this fraction of pixels to NaN first")
        f.add_text("name", "Store as", "nan_filled")
        self.out = self.add_output("Result")
        self.plot = self.add_plot("Before / after")
        self.add_button("Interpolate NaNs", self.go)

    def go(self) -> None:
        self.guard(self._go)

    def _go(self) -> None:
        v, src = self.form, self.img.obj()
        data = image_data(src).copy()
        frac = v.value("inject")
        if frac > 0:
            data[np.random.default_rng(0).random(data.shape) < frac] = np.nan
        kernel = self.kp.kernel(data.ndim)
        fn = convolve if v.value("func") == "convolve" else convolve_fft

        def work() -> np.ndarray:
            try:
                return interpolate_replace_nans(data, kernel, convolve=fn)
            except (ValueError, KernelError) as exc:
                raise ParseError(f"Interpolation failed: {exc}") from exc

        def done(out: np.ndarray) -> None:
            self.ws.put(unique_name(self.ws, v.value("name") or "nan_filled"), NDData(out))
            self.out.show_text(f"NaN before: {int(np.isnan(data).sum())}\n"
                               f"NaN after : {int(np.isnan(out).sum())}\n"
                               "(NaNs wider than the kernel cannot be filled in one pass)")
            a0, a1 = axes_row(self.plot, 2)
            show_array(a0, data, "With NaNs")
            show_array(a1, out, "Interpolated")
            self.plot.redraw()

        self.run(work, done)


class ConvolveModelsPanel(ModulePanel):
    def __init__(self, ws: Workspace) -> None:
        super().__init__(ws)
        f = self.form
        f.add_text("model", "Model", "models.Gaussian1D(10, 0, 1)", "astropy.modeling model expression")
        f.add_text("kernel", "Kernel model", "models.Box1D(1, 0, 2)", "model used as kernel")
        f.add_combo("mode", "Mode", ["convolve_fft", "convolve", "convolve_models_fft"])
        f.add_text("grid", "x grid", "-10 10 201", "'xmin xmax N' (uniform; kernel sampled on it)")
        f.add_check("norm", "Normalize kernel", True, "convolve / convolve_fft only")
        self.out = self.add_output("Result")
        self.plot = self.add_plot("Plot")
        self.add_button("Convolve models", self.go)

    def go(self) -> None:
        self.guard(self._go)

    def _go(self) -> None:
        v = self.form
        model = safe_eval(v.value("model"), MODEL_NAMES)
        kernel = safe_eval(v.value("kernel"), MODEL_NAMES)
        parts = parse_float_list(v.value("grid"), "grid")
        if len(parts) != 3 or parts[2] < 3 or parts[1] <= parts[0]:
            raise ParseError("Grid must be 'xmin xmax N' with xmax > xmin and N >= 3.")
        x = np.linspace(parts[0], parts[1], int(parts[2]))
        mode, norm = v.value("mode"), v.value("norm")

        def work() -> np.ndarray:
            try:
                if mode == "convolve_models_fft":
                    conv = convolve_models_fft(model, kernel, (x[0], x[-1]), float(x[1] - x[0]))
                else:
                    conv = convolve_models(model, kernel, mode=mode, normalize_kernel=norm)
                return np.asarray(conv(x), dtype=float)
            except (ValueError, TypeError, KernelError) as exc:
                raise ParseError(f"Model convolution failed: {exc}") from exc

        def done(y: np.ndarray) -> None:
            self.ws.put(unique_name(self.ws, "convolved_model"), np.vstack([x, y]))
            self.out.show_text(f"peak {np.max(y):.6g} at x = {x[int(np.argmax(y))]:.6g}\n"
                               f"integral {np.trapezoid(y, x):.6g}")
            ax = axes_row(self.plot, 1)[0]
            ax.plot(x, model(x), label="model")
            ax.plot(x, kernel(x), label="kernel")
            ax.plot(x, y, label="convolved", lw=2)
            ax.legend()
            self.plot.redraw()

        self.run(work, done)


def _spec(key: str, title: str, cls: type, desc: str) -> ModuleSpec:
    return ModuleSpec(key, title, CATEGORY, lambda ws: cls(ws), desc)


SPECS = [
    _spec("conv_kernels", "Convolution kernels", KernelPanel, "Build, preview and combine kernels"),
    _spec("convolve", "Convolve image", ConvolvePanel, "convolve / convolve_fft with full options"),
    _spec("conv_nans", "Interpolate NaNs", NanPanel, "interpolate_replace_nans"),
    _spec("conv_models", "Convolve models", ConvolveModelsPanel, "convolve_models and convolve_models_fft"),
]
