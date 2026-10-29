"""astropy.visualization: image viewer, RGB composites, histograms, units/time plotting."""
from __future__ import annotations

import re
from typing import Any, Optional, Tuple

import numpy as np
from astropy import units as u
from astropy.coordinates import SkyCoord
from astropy.stats import calculate_bin_edges
from astropy.time import Time
from astropy.visualization import (
    AsinhStretch, AsymmetricPercentileInterval, BaseInterval, BaseStretch, CompositeStretch,
    ContrastBiasStretch, HistEqStretch, ImageNormalize, LinearStretch, LogStretch,
    LuptonAsinhStretch, LuptonAsinhZscaleStretch, ManualInterval, MinMaxInterval,
    PercentileInterval, PowerDistStretch, PowerStretch, SinhStretch, SqrtStretch,
    SquaredStretch, ZScaleInterval, hist as ap_hist, make_lupton_rgb, make_rgb,
    quantity_support, simple_norm, time_support,
)
from astropy.visualization.wcsaxes import SphericalCircle
from astropy.wcs import WCS

from ..core.parsing import (ParseError, parse_float, parse_quantity, parse_skycoord, safe_eval,
                            split_lines)
from ..core.registry import ModuleSpec
from ..core.widgets import ModulePanel
from ..core.workspace import Workspace
from ._images import ImageSelector, axes_row, image_data, unique_name, wcs_of

CATEGORY = "Images"
INTERVALS = ["ZScale", "MinMax", "Percentile", "AsymmetricPercentile", "Manual"]
STRETCHES = ["Linear", "Sqrt", "Squared", "Log", "Asinh", "Sinh", "Power", "PowerDist",
             "ContrastBias", "HistEq"]
SIMPLE_STRETCHES = ["linear", "sqrt", "power", "log", "asinh", "sinh"]
CMAPS = ["gray", "viridis", "magma", "inferno", "plasma", "cividis", "hot", "coolwarm",
         "RdBu", "Spectral", "twilight", "nipy_spectral"]


# --------------------------------------------------------------------------- #
# Pure helpers
# --------------------------------------------------------------------------- #
def make_interval(kind: str, percent: float = 99.0, lower: float = 1.0, upper: float = 99.0,
                  vmin: Optional[float] = None, vmax: Optional[float] = None) -> BaseInterval:
    if kind == "MinMax":
        return MinMaxInterval()
    if kind == "ZScale":
        return ZScaleInterval()
    if kind == "Percentile":
        if not 0 < percent <= 100:
            raise ParseError("Percentile must be in (0, 100].")
        return PercentileInterval(percent)
    if kind == "AsymmetricPercentile":
        if not 0 <= lower < upper <= 100:
            raise ParseError("Need 0 <= lower < upper <= 100.")
        return AsymmetricPercentileInterval(lower, upper)
    if kind == "Manual":
        if vmin is not None and vmax is not None and vmin >= vmax:
            raise ParseError("vmin must be smaller than vmax.")
        return ManualInterval(vmin, vmax)
    raise ParseError(f"Unknown interval {kind!r}.")


def make_stretch(name: str, a: float = 0.1, power: float = 2.0, contrast: float = 1.0,
                 bias: float = 0.5, data: Optional[np.ndarray] = None) -> BaseStretch:
    """Instantiate a stretch by name; ``a`` is the Log/Asinh/Sinh/PowerDist parameter."""
    if name == "Linear":
        return LinearStretch()
    if name == "Sqrt":
        return SqrtStretch()
    if name == "Squared":
        return SquaredStretch()
    if name in ("Log", "Asinh", "Sinh", "PowerDist"):
        if a <= 0 or (name in ("Log", "PowerDist") and a == 1):
            raise ParseError(f"{name}: parameter 'a' must be > 0 (and != 1 for Log/PowerDist).")
        return {"Log": LogStretch, "Asinh": AsinhStretch, "Sinh": SinhStretch,
                "PowerDist": PowerDistStretch}[name](a)
    if name == "Power":
        if power <= 0:
            raise ParseError("Power must be positive.")
        return PowerStretch(power)
    if name == "ContrastBias":
        return ContrastBiasStretch(contrast, bias)
    if name == "HistEq":
        if data is None:
            raise ParseError("HistEq needs image data.")
        finite = np.asarray(data, dtype=float)
        finite = finite[np.isfinite(finite)]
        if finite.size == 0:
            raise ParseError("HistEq: no finite pixels.")
        return HistEqStretch(finite)
    raise ParseError(f"Unknown stretch {name!r}.")


def build_norm(data: np.ndarray, interval: BaseInterval, stretch: BaseStretch,
               clip: bool = False, invalid: Optional[float] = -1.0) -> ImageNormalize:
    """ImageNormalize with limits computed from the finite pixels of ``data``."""
    finite = np.asarray(data, dtype=float)
    finite = finite[np.isfinite(finite)]
    if finite.size == 0:
        raise ParseError("The image has no finite pixels.")
    try:
        vmin, vmax = interval.get_limits(finite)
    except (ValueError, IndexError) as exc:
        raise ParseError(f"Cannot compute display limits: {exc}") from exc
    if vmin == vmax:
        vmin, vmax = vmin - 0.5, vmax + 0.5
    return ImageNormalize(vmin=vmin, vmax=vmax, stretch=stretch, clip=clip, invalid=invalid)


def stretch_curve(stretch: BaseStretch, n: int = 257) -> Tuple[np.ndarray, np.ndarray]:
    x = np.linspace(0.0, 1.0, n)
    return x, np.asarray(stretch(x))


ASTROPY_BIN_RULES = ("knuth", "freedman", "scott", "blocks")
NUMPY_BIN_RULES = ("auto", "fd", "sturges", "doane", "rice", "sqrt", "stone")


def bin_edges(data: np.ndarray, bins: Any) -> np.ndarray:
    """Edges for an int, an astropy rule (knuth/freedman/scott/blocks) or a numpy rule."""
    try:
        if isinstance(bins, str) and bins in NUMPY_BIN_RULES:
            return np.histogram_bin_edges(data, bins=bins)
        return np.asarray(calculate_bin_edges(data, bins=bins))
    except (ValueError, TypeError) as exc:
        raise ParseError(f"Bin calculation failed: {exc}") from exc


def draw_sky_overlays(ax: Any, points_text: str = "", circle_text: str = "") -> int:
    """Scatter SkyCoord lines and ``ra dec | radius`` circles on a WCSAxes; returns #items."""
    count = 0
    lines = split_lines(points_text)
    if lines:
        coords = SkyCoord([parse_skycoord(ln) for ln in lines])
        ax.scatter(coords.ra.deg, coords.dec.deg, transform=ax.get_transform("icrs"),
                   s=60, facecolors="none", edgecolors="cyan")
        count += len(lines)
    for ln in split_lines(circle_text):
        if "|" not in ln:
            raise ParseError(f"Circle {ln!r}: expected 'ra dec | radius' (e.g. '150 2 | 10 arcsec').")
        centre, radius = (p.strip() for p in ln.split("|", 1))
        circ = SphericalCircle(parse_skycoord(centre), parse_quantity(radius, u.deg, "radius"),
                               edgecolor="yellow", facecolor="none", lw=1.5,
                               transform=ax.get_transform("icrs"))
        ax.add_patch(circ)
        count += 1
    return count


def render_image(canvas: Any, data: np.ndarray, norm: Any, cmap: str, colorbar: bool,
                 wcs: Optional[WCS] = None, grid: bool = False, title: str = "",
                 overlays: Tuple[str, str] = ("", "")) -> None:
    """Draw ``data`` on ``canvas`` (GUI thread); WCSAxes when ``wcs`` is a 2-D celestial WCS."""
    use_wcs = wcs is not None and wcs.naxis == 2
    canvas.figure.clear()
    ax = canvas.figure.add_subplot(111, projection=wcs) if use_wcs else canvas.figure.add_subplot(111)
    im = ax.imshow(data, origin="lower", norm=norm, cmap=cmap, interpolation="nearest")
    if use_wcs:
        if grid:
            ax.coords.grid(True, color="white", ls=":", alpha=0.7)
        if any(overlays):
            draw_sky_overlays(ax, *overlays)
    if title:
        ax.set_title(title, fontsize=9)
    if colorbar:
        canvas.figure.colorbar(im, ax=ax)
    canvas.redraw()


# --------------------------------------------------------------------------- #
# Panels
# --------------------------------------------------------------------------- #
class ScaleMixin:
    """Adds interval/stretch fields to a panel's form and builds the objects from them."""

    form: Any

    def add_scale_fields(self, with_cmap: bool = True) -> None:
        f = self.form
        f.add_combo("interval", "Interval", INTERVALS, "how vmin/vmax are chosen")
        f.add_float("percent", "Percentile", 99.0, 0.0, 100.0, 3, "Percentile interval (centered)")
        f.add_float("lower", "Lower %", 1.0, 0.0, 100.0, 3, "AsymmetricPercentile lower")
        f.add_float("upper", "Upper %", 99.0, 0.0, 100.0, 3, "AsymmetricPercentile upper")
        f.add_text("vmin", "vmin", "", "Manual interval (empty: data minimum)")
        f.add_text("vmax", "vmax", "", "Manual interval (empty: data maximum)")
        f.add_combo("stretch", "Stretch", STRETCHES)
        f.add_combo("stretch2", "Then stretch", ["none"] + STRETCHES,
                    "CompositeStretch: applied after the first stretch")
        f.add_float("a", "a", 0.1, 1e-6, 1e9, 6, "Log (a>1 typical 1000), Asinh, Sinh, PowerDist")
        f.add_float("power", "Power", 2.0, 1e-3, 100.0, 4, "PowerStretch exponent")
        f.add_float("contrast", "Contrast", 1.0, 0.0, 100.0, 4, "ContrastBiasStretch")
        f.add_float("bias", "Bias", 0.5, -10.0, 10.0, 4, "ContrastBiasStretch")
        f.add_check("clip", "Clip", False, "clip output to [0, 1]")
        if with_cmap:
            f.add_combo("cmap", "Colormap", CMAPS)
            f.add_check("invert", "Invert colormap", False)
            f.add_check("colorbar", "Colorbar", True)

    def _opt(self, key: str) -> Optional[float]:
        text = self.form.value(key)
        return parse_float(text, key) if text else None

    def interval(self) -> BaseInterval:
        v = self.form
        return make_interval(v.value("interval"), v.value("percent"), v.value("lower"),
                             v.value("upper"), self._opt("vmin"), self._opt("vmax"))

    def stretch(self, data: Optional[np.ndarray] = None) -> BaseStretch:
        v = self.form
        kw = dict(a=v.value("a"), power=v.value("power"), contrast=v.value("contrast"),
                  bias=v.value("bias"), data=data)
        first = make_stretch(v.value("stretch"), **kw)
        second = v.value("stretch2")
        return first if second == "none" else CompositeStretch(first, make_stretch(second, **kw))


class ViewerPanel(ModulePanel, ScaleMixin):
    def __init__(self, ws: Workspace) -> None:
        super().__init__(ws)
        f = self.form
        self.src = ImageSelector(ws)
        f.add_widget("src", "Image", self.src)
        f.add_combo("mode", "Normalization", ["ImageNormalize (interval + stretch)", "simple_norm"],
                    "simple_norm uses the Percentile and 'a'/'Power' fields")
        self.add_scale_fields()
        f.add_combo("simple", "simple_norm stretch", SIMPLE_STRETCHES)
        f.add_check("use_wcs", "WCS axes", True, "use WCSAxes when the image has a 2-D WCS")
        f.add_check("grid", "Coordinate grid", True)
        f.add_multiline("points", "Sky points", "", "one coordinate per line, e.g. '150.0 2.0'")
        f.add_multiline("circles", "Sky circles", "", "'ra dec | radius' per line, e.g. '150 2 | 10 arcsec'", 60)
        self.image = self.add_plot("Image")
        self.curve = self.add_plot("Stretch")
        self.out = self.add_output("Info")
        self.add_button("Show image", self.show)
        self.add_button("Save PNG...", self.save)

    def show(self) -> None:
        self.guard(self._show)

    def _show(self) -> None:
        v, src = self.form, self.src.obj()
        data = image_data(src)
        if data.ndim != 2:
            raise ParseError(f"The viewer needs a 2-D image, got {data.ndim}-D.")
        simple = v.value("mode") == "simple_norm"
        interval = None if simple else self.interval()
        stretch = None if simple else self.stretch(data)
        sargs = dict(stretch=v.value("simple"), power=v.value("power"), asinh_a=v.value("a"),
                     sinh_a=v.value("a"), log_a=max(v.value("a"), 1.0 + 1e-6), percent=v.value("percent"),
                     clip=v.value("clip"))

        def work() -> ImageNormalize:
            if simple:
                finite = data[np.isfinite(data)]
                if finite.size == 0:
                    raise ParseError("The image has no finite pixels.")
                return simple_norm(finite, **sargs)
            return build_norm(data, interval, stretch, clip=v.value("clip"))

        cmap = v.value("cmap") + ("_r" if v.value("invert") else "")
        wcs = wcs_of(src) if v.value("use_wcs") else None
        overlays = (v.value("points"), v.value("circles"))

        def done(norm: ImageNormalize) -> None:
            render_image(self.image, data, norm, cmap, v.value("colorbar"), wcs,
                         v.value("grid"), self.src.name(), overlays)
            self.out.show_text(f"vmin = {norm.vmin:.8g}\nvmax = {norm.vmax:.8g}\n"
                               f"stretch = {type(norm.stretch).__name__}\ncmap = {cmap}\n"
                               f"WCS axes = {wcs is not None and wcs.naxis == 2}")
            ax = axes_row(self.curve, 2)
            x, y = stretch_curve(norm.stretch)
            ax[0].plot(x, y)
            ax[0].plot(x, x, ls=":", c="gray")
            ax[0].set_title("Stretch curve", fontsize=9)
            finite = data[np.isfinite(data)]
            ax[1].hist(finite, bins=100, range=(norm.vmin, norm.vmax))
            ax[1].set_yscale("log")
            ax[1].set_title("Histogram within limits", fontsize=9)
            self.curve.redraw()

        self.run(work, done)

    def save(self) -> None:
        def go() -> None:
            path = self.ask_save_path("Save PNG", "PNG (*.png)", "image.png")
            if path:
                self.image.save(path)
                self.set_status(f"Saved {path}")
        self.guard(go)


class RgbPanel(ModulePanel, ScaleMixin):
    def __init__(self, ws: Workspace) -> None:
        super().__init__(ws)
        f = self.form
        self.sel = {c: ImageSelector(ws, with_buttons=False) for c in "rgb"}
        for c, label in zip("rgb", ("Red", "Green", "Blue")):
            f.add_widget(c, label, self.sel[c])
        f.add_combo("method", "Method", ["Lupton (make_lupton_rgb)", "make_rgb"])
        f.add_combo("lstretch", "Lupton stretch", ["LuptonAsinhStretch", "LuptonAsinhZscaleStretch"])
        f.add_float("lw", "Stretch width", 5.0, 1e-6, 1e9, 4, "LuptonAsinhStretch 'stretch'")
        f.add_float("Q", "Q", 8.0, 1e-6, 1e6, 4, "softening")
        f.add_text("minimum", "Minimum", "0", "black level (Lupton)")
        self.add_scale_fields(with_cmap=False)
        f.add_text("name", "Store as", "rgb")
        self.plot = self.add_plot("RGB")
        self.out = self.add_output("Info")
        self.add_button("Compose", self.compose)
        self.add_button("Save PNG...", self.save)

    def compose(self) -> None:
        self.guard(self._compose)

    def _compose(self) -> None:
        v = self.form
        chans = [np.nan_to_num(image_data(self.sel[c].obj()), nan=0.0, posinf=0.0, neginf=0.0)
                 for c in "rgb"]
        if any(c.ndim != 2 for c in chans):
            raise ParseError("RGB channels must be 2-D images.")
        if not (chans[0].shape == chans[1].shape == chans[2].shape):
            raise ParseError(f"Channel shapes differ: {[c.shape for c in chans]}.")
        lupton = v.value("method").startswith("Lupton")
        minimum = parse_float(v.value("minimum"), "minimum") if lupton else 0.0
        if lupton:
            lstretch, lw, q = v.value("lstretch"), v.value("lw"), v.value("Q")
            interval = None
            stretch = None
        else:
            interval, stretch = self.interval(), self.stretch(chans[0])

        def work() -> np.ndarray:
            try:
                if lupton:
                    obj = (LuptonAsinhZscaleStretch(chans, Q=q) if lstretch.endswith("Zscale")
                           else LuptonAsinhStretch(stretch=lw, Q=q))
                    return make_lupton_rgb(*chans, minimum=minimum, stretch_object=obj)
                return make_rgb(*chans, interval=interval, stretch=stretch)
            except (ValueError, TypeError) as exc:
                raise ParseError(f"RGB composition failed: {exc}") from exc

        def done(rgb: np.ndarray) -> None:
            self.ws.put(unique_name(self.ws, v.value("name") or "rgb"), rgb)
            self.plot.figure.clear()
            ax = self.plot.figure.add_subplot(111)
            ax.imshow(rgb, origin="lower")
            ax.set_axis_off()
            self.plot.redraw()
            self.out.show_text(f"RGB image {rgb.shape} {rgb.dtype}, stored in the workspace.")

        self.run(work, done)

    def save(self) -> None:
        def go() -> None:
            path = self.ask_save_path("Save PNG", "PNG (*.png)", "rgb.png")
            if path:
                self.plot.save(path)
        self.guard(go)


class HistogramPanel(ModulePanel):
    MAX_ADAPTIVE = 200_000

    def __init__(self, ws: Workspace) -> None:
        super().__init__(ws)
        f = self.form
        self.src = ImageSelector(ws)
        f.add_widget("src", "Data", self.src)
        f.add_combo("bins", "Bins", [*ASTROPY_BIN_RULES, *NUMPY_BIN_RULES, "10", "50", "100"], "rule or integer", editable=True)
        f.add_float("lo", "Lower %", 0.0, 0.0, 100.0, 2, "clip data range")
        f.add_float("hi", "Upper %", 100.0, 0.0, 100.0, 2)
        f.add_check("log", "Log y", False)
        f.add_check("density", "Density", False)
        self.plot = self.add_plot("Histogram")
        self.out = self.add_output("Info")
        self.add_button("Plot histogram", self.go)

    def go(self) -> None:
        self.guard(self._go)

    def _go(self) -> None:
        v = self.form
        flat = image_data(self.src.obj()).ravel()
        flat = flat[np.isfinite(flat)]
        if flat.size == 0:
            raise ParseError("No finite values to histogram.")
        lo, hi = v.value("lo"), v.value("hi")
        if lo >= hi:
            raise ParseError("Lower % must be below Upper %.")
        bins_text = v.value("bins").strip()
        bins: Any = int(bins_text) if re.fullmatch(r"\d+", bins_text) else bins_text
        if isinstance(bins, int) and bins < 1:
            raise ParseError("Bins must be >= 1.")

        def work() -> Tuple[np.ndarray, np.ndarray, str]:
            vmin, vmax = np.percentile(flat, [lo, hi])
            data = flat[(flat >= vmin) & (flat <= vmax)]
            note = ""
            if bins in ("knuth", "blocks") and data.size > self.MAX_ADAPTIVE:
                data = np.random.default_rng(0).choice(data, self.MAX_ADAPTIVE, replace=False)
                note = f" (bin edges from a random sample of {self.MAX_ADAPTIVE})"
            edges = bin_edges(data, bins)
            return flat[(flat >= vmin) & (flat <= vmax)], edges, note

        def done(res: Tuple[np.ndarray, np.ndarray, str]) -> None:
            data, edges, note = res
            ax = axes_row(self.plot, 1)[0]
            ap_hist(data, bins=edges, ax=ax, histtype="stepfilled", alpha=0.6, density=v.value("density"))
            if v.value("log"):
                ax.set_yscale("log")
            self.plot.redraw()
            self.out.show_text(f"{data.size} values, {len(edges) - 1} bins{note}\n"
                               f"range {edges[0]:.6g} .. {edges[-1]:.6g}")

        self.run(work, done)


class QuantityTimePanel(ModulePanel):
    def __init__(self, ws: Workspace) -> None:
        super().__init__(ws)
        f = self.form
        f.add_text("x", "x", "Time('2024-01-01') + linspace(0, 30, 31) * u.day",
                   "Quantity or Time expression (u, np, Time, linspace... available)")
        f.add_text("y", "y", "(x - x[0]).to(u.hr) ** 0.5 * 10 * u.m / u.hr ** 0.5",
                   "expression; the name x refers to the x values")
        f.add_combo("tformat", "Time format", ["default", "iso", "isot", "jd", "mjd", "decimalyear",
                                               "datetime"], "time_support(format=...)")
        f.add_combo("style", "Style", ["line", "markers", "line+markers"])
        self.plot = self.add_plot("Plot")
        self.out = self.add_output("Info")
        self.add_button("Plot", self.go)

    def go(self) -> None:
        self.guard(self._go)

    def _go(self) -> None:
        v = self.form
        x = safe_eval(v.value("x"))
        if isinstance(x, (list, tuple)):
            x = np.asarray(x)
        y = safe_eval(v.value("y"), {"x": x})
        if np.size(x) != np.size(y):
            raise ParseError(f"x has {np.size(x)} values but y has {np.size(y)}.")
        if np.size(x) == 0:
            raise ParseError("Nothing to plot.")
        fmt = None if v.value("tformat") == "default" else v.value("tformat")
        fmt_style = {"line": "-", "markers": "o", "line+markers": "o-"}[v.value("style")]
        self.plot.figure.clear()
        ax = self.plot.figure.add_subplot(111)
        try:
            with quantity_support(), time_support(format=fmt):
                ax.plot(x, y, fmt_style)
                if isinstance(x, Time):
                    self.plot.figure.autofmt_xdate()
                self.plot.canvas.draw()  # inside the context so the converters are active
        except (u.UnitConversionError, TypeError, ValueError) as exc:
            raise ParseError(f"Cannot plot: {exc}") from exc
        self.out.show_text(f"x: {type(x).__name__}"
                           + (f" [{x.unit}]" if isinstance(x, u.Quantity) else "")
                           + f"\ny: {type(y).__name__}"
                           + (f" [{y.unit}]" if isinstance(y, u.Quantity) else "")
                           + f"\nn = {np.size(x)}")


def _spec(key: str, title: str, cls: type, desc: str) -> ModuleSpec:
    return ModuleSpec(key, title, CATEGORY, lambda ws: cls(ws), desc)


SPECS = [
    _spec("viz_viewer", "Image viewer", ViewerPanel,
          "Intervals, stretches, colormaps, WCSAxes with overlays"),
    _spec("viz_rgb", "RGB composites", RgbPanel, "make_lupton_rgb and make_rgb"),
    _spec("viz_hist", "Histogram", HistogramPanel, "astropy.visualization.hist with adaptive bins"),
    _spec("viz_units", "Quantity & time plots", QuantityTimePanel, "quantity_support / time_support"),
]
