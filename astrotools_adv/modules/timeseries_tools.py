"""astropy.timeseries tools: build, edit, fold/bin, Lomb-Scargle and BLS periodograms."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from astropy import units as u
from astropy.table import Table
from astropy.time import Time, TimeDelta
from astropy.timeseries import (
    BinnedTimeSeries, BoxLeastSquares, LombScargle, LombScargleMultiband, TimeSeries,
    aggregate_downsample,
)
from PyQt5.QtWidgets import QComboBox

from ..core.parsing import (
    ParseError, parse_array, parse_float_list, parse_quantity, parse_time, safe_eval,
    split_lines,
)
from ..core.registry import ModuleSpec
from ..core.widgets import MplCanvas, ModulePanel, WorkspaceCombo
from ..core.workspace import Workspace

CATEGORY = "Analysis"
TS_TYPES = (TimeSeries, BinnedTimeSeries)
MAX_TRIAL_PERIODS = 3_000_000
TIME_FORMATS = ["auto", "iso", "isot", "jd", "mjd", "unix", "decimalyear", "gps", "cxcsec"]
TIME_SCALES = ["auto", "utc", "tai", "tt", "tdb", "tcb", "tcg", "ut1"]


# --------------------------------------------------------------------------- #
# Data helpers (no Qt, safe for worker threads)
# --------------------------------------------------------------------------- #
def sample_times(ts: Any) -> Any:
    """Per-row time (bin centre for binned series)."""
    return ts.time_bin_center if isinstance(ts, BinnedTimeSeries) else ts.time


def column_floats(col: Any, name: str = "column") -> np.ndarray:
    """1-D float array from a (Masked/Quantity) column; masked values become NaN."""
    values = col.value if isinstance(col, u.Quantity) else col
    if isinstance(values, np.ma.MaskedArray):
        values = values.astype(float).filled(np.nan)
    try:
        arr = np.asarray(values, dtype=float)
    except (TypeError, ValueError):
        raise ParseError(f"Column {name!r} is not numeric.") from None
    if arr.ndim != 1:
        raise ParseError(f"Column {name!r} must be 1-dimensional (got shape {arr.shape}).")
    return arr


@dataclass
class Arrays:
    """Cleaned numeric view of a series used by the periodogram tools."""

    t: u.Quantity            # days since ``t0`` (or TimeDelta days)
    y: np.ndarray
    dy: Optional[np.ndarray]
    bands: Optional[np.ndarray]
    index: np.ndarray        # original row numbers that were kept
    t0: Optional[Time]
    yunit: str
    dropped: int


def extract(ts: Any, ycol: str, ecol: str = "", bcol: str = "", min_points: int = 3) -> Arrays:
    """Pull (t, y, dy[, bands]) out of ``ts`` dropping non-finite rows."""
    if not ycol:
        raise ParseError("Choose a signal column.")
    if ycol not in ts.colnames:
        raise ParseError(f"No column {ycol!r}.")
    tt = sample_times(ts)
    if isinstance(tt, TimeDelta):
        t0, t = None, tt.to(u.day)
    else:
        t0 = tt.min()
        t = (tt - t0).to(u.day)
    y = column_floats(ts[ycol], ycol)
    dy = None
    if ecol:
        if ecol not in ts.colnames:
            raise ParseError(f"No column {ecol!r}.")
        dy = column_floats(ts[ecol], ecol)
    bands = None
    if bcol:
        if bcol not in ts.colnames:
            raise ParseError(f"No column {bcol!r}.")
        bands = np.asarray(ts[bcol]).astype(str)
    ok = np.isfinite(t.value) & np.isfinite(y)
    if dy is not None:
        ok &= np.isfinite(dy) & (dy > 0)
    if ok.sum() < min_points:
        raise ParseError(f"Only {int(ok.sum())} valid points; need at least {min_points}.")
    unit = getattr(ts[ycol], "unit", None)
    return Arrays(
        t=t[ok], y=y[ok], dy=None if dy is None else dy[ok],
        bands=None if bands is None else bands[ok], index=np.flatnonzero(ok), t0=t0,
        yunit="" if unit in (None, "") else str(unit), dropped=int((~ok).sum()))


def absolute_time(a: Arrays, days: float) -> str:
    """``days`` since the series start as an ISO string (or plain days if no epoch)."""
    if a.t0 is None:
        return f"{days:.8g} d"
    return (a.t0 + TimeDelta(days * u.day)).isot


def fold_phase(t_days: np.ndarray, period: float, epoch: float) -> np.ndarray:
    """Phase in days wrapped to [-period/2, period/2)."""
    return (t_days - epoch + 0.5 * period) % period - 0.5 * period


def make_synthetic(kind: str, n: int, duration: float, start: str = "2020-01-01T00:00:00",
                   irregular: bool = False, period: float = 3.7, amplitude: float = 1.0,
                   phase: float = 0.0, depth: float = 0.01, transit_duration: float = 0.2,
                   t_transit: float = 1.0, noise: float = 0.1, seed: int = 0) -> TimeSeries:
    """Synthetic light curve: ``flux = 1 + signal + noise`` with ``flux_err = noise``."""
    kinds = ("sinusoid", "transit", "sinusoid+transit", "noise")
    if kind not in kinds:
        raise ParseError(f"Unknown signal kind {kind!r}; choose one of {kinds}.")
    if n < 3 or n > 5_000_000:
        raise ParseError("Number of points must be between 3 and 5,000,000.")
    if not (np.isfinite(duration) and duration > 0):
        raise ParseError("Duration must be positive.")
    if noise < 0 or not np.isfinite(noise):
        raise ParseError("Noise must be >= 0.")
    if kind != "noise" and not (np.isfinite(period) and period > 0):
        raise ParseError("Period must be positive.")
    if "transit" in kind and not 0 < transit_duration < period:
        raise ParseError("Transit duration must be positive and shorter than the period.")
    rng = np.random.default_rng(int(seed))
    if irregular:
        t = np.sort(rng.uniform(0, duration, n))
    else:
        t = np.linspace(0, duration, n, endpoint=False)
    flux = np.ones(n)
    if kind in ("sinusoid", "sinusoid+transit"):
        flux += amplitude * np.sin(2 * np.pi * (t / period + phase))
    if kind in ("transit", "sinusoid+transit"):
        in_transit = np.abs(fold_phase(t, period, t_transit)) < transit_duration / 2
        flux[in_transit] -= depth
    flux += rng.normal(0.0, noise, n) if noise > 0 else 0.0
    time = parse_time(start, name="start time") + t * u.day
    return TimeSeries(time=time, data={
        "flux": flux, "flux_err": np.full(n, noise if noise > 0 else 1e-6)})


def ts_from_table(table: Table, time_col: str, fmt: str = "auto", scale: str = "auto") -> TimeSeries:
    """Convert a Table with a time column into a :class:`TimeSeries`."""
    if time_col not in table.colnames:
        raise ParseError(f"No column {time_col!r}; columns are {table.colnames}.")
    data = Table(table, copy=True)
    raw = data[time_col]
    if np.ma.is_masked(raw) and np.ma.getmaskarray(raw).any():
        raise ParseError(f"Time column {time_col!r} contains masked values.")
    data.remove_column(time_col)
    if isinstance(raw, (Time, TimeDelta)):
        time = raw
    else:
        kw: Dict[str, Any] = {}
        if fmt != "auto":
            kw["format"] = fmt
        if scale != "auto":
            kw["scale"] = scale
        try:
            time = Time(np.asarray(raw.data if hasattr(raw, "data") else raw), **kw)
        except Exception as exc:  # noqa: BLE001
            raise ParseError(f"Cannot interpret column {time_col!r} as time: {exc}") from None
    return TimeSeries(time=time, data=data if len(data.colnames) else None)


def add_columns_from_text(ts: Any, text: str) -> None:
    """Add columns from lines ``name = expression`` (names ``n`` and ``t`` [days])."""
    n = len(ts)
    tt = sample_times(ts)
    t = (tt - tt.min()).to_value(u.day) if not isinstance(tt, TimeDelta) else tt.to_value(u.day)
    for line in split_lines(text):
        if "=" not in line:
            raise ParseError(f"Expected 'name = expression', got {line!r}.")
        name, expr = (s.strip() for s in line.split("=", 1))
        if not name.isidentifier() or name in ts.colnames:
            raise ParseError(f"Invalid or existing column name {name!r}.")
        value = safe_eval(expr, {"n": n, "t": t})
        arr = np.broadcast_to(value, (n,)) if np.ndim(value) == 0 or np.shape(value) == (n,) \
            else None
        if arr is None:
            raise ParseError(f"{name}: expression must be a scalar or have {n} elements.")
        ts[name] = np.array(arr)


def numeric_columns(ts: Any) -> List[str]:
    out = []
    for name in ts.colnames:
        col = ts[name]
        if isinstance(col, (Time, TimeDelta)) or getattr(col, "ndim", 1) != 1:
            continue
        dtype = getattr(col, "dtype", None)
        if dtype is not None and dtype.kind in "fiub":
            out.append(name)
    return out


# --------------------------------------------------------------------------- #
# Periodogram workers
# --------------------------------------------------------------------------- #
def run_lomb_scargle(a: Arrays, p: Dict[str, Any]) -> Dict[str, Any]:
    """Compute the periodogram and derived products. Keys of ``p`` documented in the panel."""
    notes: List[str] = []
    freq_kw = dict(samples_per_peak=p["spp"], nyquist_factor=p["nyq"],
                   minimum_frequency=p["fmin"], maximum_frequency=p["fmax"])
    if p["multiband"]:
        if a.bands is None:
            raise ParseError("Multiband mode needs a band column.")
        ls = LombScargleMultiband(a.t, a.y, a.bands, a.dy, normalization=p["normalization"],
                                  nterms_base=p["nterms"], nterms_band=p["nterms"],
                                  center_data=p["center_data"], fit_mean=p["fit_mean"])
        method = "fast" if p["method"] == "fast" else "flexible"
        freq, power = ls.autopower(method=method, normalization=p["normalization"], **freq_kw)
    else:
        ls = LombScargle(a.t, a.y, a.dy, fit_mean=p["fit_mean"], center_data=p["center_data"],
                         nterms=p["nterms"], normalization=p["normalization"])
        if p["freq_expr"]:
            freq = p["freq_expr"]
            power = ls.power(freq, method=p["method"])
        else:
            freq, power = ls.autopower(method=p["method"], **freq_kw)
    f = np.asarray(freq.to_value(1 / u.day), dtype=float)
    pw = np.asarray(getattr(power, "value", power), dtype=float)
    if not f.size or not np.isfinite(pw).any():
        raise ParseError("Periodogram is empty or non-finite; check the frequency range.")
    best = int(np.nanargmax(pw))
    out: Dict[str, Any] = {
        "freq": f, "power": pw, "best_f": f[best], "best_power": pw[best],
        "best_period": 1.0 / f[best] if f[best] > 0 else np.inf, "notes": notes,
        "levels": {}, "fap": None, "fap_method": p["fap_method"], "params": None,
        "model": None, "dist": None, "multiband": p["multiband"], "normalization": p["normalization"],
    }
    tab = Table({"frequency": f / u.day, "period": (1.0 / np.where(f > 0, f, np.nan)) * u.day,
                 "power": pw})
    out["table"] = tab
    if p["multiband"]:
        notes.append("False-alarm probability and single-band model are not available "
                     "for multiband periodograms.")
        return out
    grid = dict(samples_per_peak=p["spp"], nyquist_factor=p["nyq"],
                minimum_frequency=f.min() / u.day, maximum_frequency=f.max() / u.day)
    kwds = ({"n_bootstraps": p["n_boot"], "random_seed": 0}
            if p["fap_method"] == "bootstrap" else None)
    try:
        out["fap"] = float(ls.false_alarm_probability(
            out["best_power"], method=p["fap_method"], method_kwds=kwds, **grid))
        if p["levels"]:
            lev = ls.false_alarm_level(np.asarray(p["levels"]), method=p["fap_method"],
                                       method_kwds=kwds, **grid)
            out["levels"] = {float(pr): float(v) for pr, v in zip(p["levels"], np.atleast_1d(lev))}
    except Exception as exc:  # noqa: BLE001
        notes.append(f"False-alarm estimate failed: {exc}")
    try:
        bf = out["best_f"] / u.day
        params = ls.model_parameters(bf)
        out["params"] = np.asarray(getattr(params, "value", params), dtype=float).tolist()
        phase = np.linspace(0, 1, 400)
        period = out["best_period"]
        tmin = float(a.t.min().value)
        model = ls.model((tmin + phase * period) * u.day, bf)
        out["model"] = (phase, np.asarray(getattr(model, "value", model), dtype=float))
        out["tmin"] = tmin
    except Exception as exc:  # noqa: BLE001
        notes.append(f"Model fit failed: {exc}")
    if p["normalization"] == "standard":
        try:
            xs = np.linspace(0.0, 1.0, 400)[1:-1]
            out["dist"] = (xs, np.asarray(ls.distribution(xs), dtype=float))
        except Exception as exc:  # noqa: BLE001
            notes.append(f"Null distribution unavailable: {exc}")
    return out


def run_bls(a: Arrays, p: Dict[str, Any]) -> Dict[str, Any]:
    """Box least squares search; ``p`` keys: durations, periods, pmin, pmax, ..."""
    bls = BoxLeastSquares(a.t, a.y, dy=a.dy)
    durations = p["durations"]
    if p["periods"] is not None:
        periods = p["periods"]
    else:
        periods = bls.autoperiod(durations, minimum_period=p["pmin"], maximum_period=p["pmax"],
                                 minimum_n_transit=p["min_transits"],
                                 frequency_factor=p["freq_factor"])
    if len(periods) == 0:
        raise ParseError("No trial periods: widen the period range or lower 'min transits'.")
    if len(periods) > MAX_TRIAL_PERIODS:
        raise ParseError(f"{len(periods):,} trial periods is too many (limit "
                         f"{MAX_TRIAL_PERIODS:,}); narrow the range or raise frequency factor.")
    res = bls.power(periods, durations, objective=p["objective"], method=p["method"],
                    oversample=p["oversample"])
    power = np.asarray(res.power, dtype=float)
    if not np.isfinite(power).any():
        raise ParseError("BLS power is non-finite everywhere.")
    best = int(np.nanargmax(power))
    period, duration, t_tr = res.period[best], res.duration[best], res.transit_time[best]
    stats = bls.compute_stats(period, duration, t_tr)
    pv, dv, tv = (float(x.to_value(u.day)) for x in (period, duration, t_tr))
    phase = np.linspace(-0.5 * pv, 0.5 * pv, 600)
    model = bls.model(t_tr + phase * u.day, period, duration, t_tr)
    tab = Table({
        "period": res.period, "power": power, "depth": np.asarray(res.depth),
        "depth_err": np.asarray(res.depth_err), "depth_snr": np.asarray(res.depth_snr),
        "duration": res.duration, "transit_time": res.transit_time,
        "log_likelihood": np.asarray(res.log_likelihood)})
    return {
        "table": tab, "best": best, "period": pv, "duration": dv, "transit_time": tv,
        "depth": float(res.depth[best]), "depth_err": float(res.depth_err[best]),
        "depth_snr": float(res.depth_snr[best]), "power": power[best], "stats": stats,
        "model": (phase, np.asarray(model, dtype=float)), "objective": p["objective"],
        "mask": np.asarray(bls.transit_mask(a.t, period, duration, t_tr)),
    }


# --------------------------------------------------------------------------- #
# Plot helpers (GUI thread only)
# --------------------------------------------------------------------------- #
def plot_xy(canvas: MplCanvas, x: np.ndarray, y: np.ndarray, dy: Optional[np.ndarray],
            xlabel: str, ylabel: str, title: str = "", model: Optional[Tuple] = None,
            bands: Optional[np.ndarray] = None) -> Any:
    ax = canvas.axes()
    groups = [(None, slice(None))] if bands is None else \
        [(b, bands == b) for b in np.unique(bands)]
    for label, sel in groups:
        ax.errorbar(x[sel], y[sel], yerr=None if dy is None else dy[sel], fmt=".", ms=3,
                    lw=0.5, alpha=0.8, label=label)
    if model is not None:
        ax.plot(model[0], model[1], "r-", lw=1.5, label="model")
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    if title:
        ax.set_title(title)
    if bands is not None or model is not None:
        ax.legend(loc="best", fontsize="small")
    canvas.redraw()
    return ax


class ColumnCombo(QComboBox):
    """Column chooser for the series currently selected in a :class:`WorkspaceCombo`."""

    def __init__(self, optional: bool, numeric: bool = True, prefer: Tuple[str, ...] = ()) -> None:
        super().__init__()
        self.optional, self.numeric, self.prefer = optional, numeric, prefer

    def fill(self, ts: Any) -> None:
        current = self.currentText()
        self.clear()
        if self.optional:
            self.addItem("(none)", "")
        names = ts.colnames if ts is not None else []
        if ts is not None and self.numeric:
            allowed = set(numeric_columns(ts))
            names = [n for n in names if n in allowed]
        elif ts is not None:
            names = [n for n in names if not isinstance(ts[n], (Time, TimeDelta))]
        for n in names:
            self.addItem(n, n)
        idx = self.findText(current)
        if idx < 0:
            idx = next((self.findText(p) for p in self.prefer if self.findText(p) >= 0), -1)
        if idx < 0 and self.count():
            idx = 0
        if idx >= 0:
            self.setCurrentIndex(idx)

    def column(self) -> str:
        data = self.currentData()
        return "" if data is None else str(data)


class SeriesPanel(ModulePanel):
    """Panel with a series picker plus signal/error column pickers."""

    def __init__(self, ws: Workspace, with_columns: bool = True, with_bands: bool = False) -> None:
        super().__init__(ws)
        self.src = WorkspaceCombo(ws, TS_TYPES)
        self.form.add_widget("series", "Series", self.src)
        self.ycombo = ColumnCombo(False, prefer=("flux", "sap_flux", "pdcsap_flux"))
        self.ecombo = ColumnCombo(True, prefer=("flux_err", "sap_flux_err", "pdcsap_flux_err"))
        self.bcombo = ColumnCombo(True, numeric=False)
        if with_columns:
            self.form.add_widget("y", "Signal column", self.ycombo)
            self.form.add_widget("dy", "Error column", self.ecombo)
        if with_bands:
            self.form.add_widget("band", "Band column", self.bcombo)
        self.src.currentTextChanged.connect(self.sync_columns)
        ws.changed.connect(self.sync_columns)
        self.sync_columns()

    def current_series(self) -> Any:
        return self.src.selected()

    def sync_columns(self, *_: Any) -> None:
        name = self.src.currentText()
        ts = self.ws.get(name) if name in self.ws else None
        for combo in (self.ycombo, self.ecombo, self.bcombo):
            combo.fill(ts)

    def arrays(self, bands: bool = False, min_points: int = 3) -> Arrays:
        return extract(self.current_series(), self.ycombo.column(), self.ecombo.column(),
                       self.bcombo.column() if bands else "", min_points)


def _opt_quantity(text: str, unit: Any, name: str) -> Optional[u.Quantity]:
    return parse_quantity(text, default_unit=unit, name=name) if text.strip() else None


def _info(ts: Any) -> str:
    tt = sample_times(ts)
    lines = [f"{type(ts).__name__}: {len(ts)} rows", f"columns: {ts.colnames}"]
    for name in ts.colnames:
        col = ts[name]
        unit = getattr(col, "unit", None)
        lines.append(f"  {name:<18} {type(col).__name__:<14} unit={unit}")
    if len(ts):
        if isinstance(tt, TimeDelta):
            lines.append(f"time (delta): {tt.min().to(u.day):.8g} .. {tt.max().to(u.day):.8g}")
        else:
            lines.append(f"time: {tt.min().isot} .. {tt.max().isot} (scale={tt.scale}, "
                         f"format={tt.format})")
            lines.append(f"span: {(tt.max() - tt.min()).to(u.day):.8g}")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Panels
# --------------------------------------------------------------------------- #
class CreatePanel(ModulePanel):
    MODES = ["Table with time column", "Regular sampling (start + delta + n)",
             "Binned (bin start + size/end)", "Read from file"]

    def __init__(self, ws: Workspace) -> None:
        super().__init__(ws)
        f = self.form
        f.add_combo("mode", "Mode", self.MODES, "How the series is created.")
        f.add_text("name", "Result name", "series", "Workspace name for the new series.")
        self.table_combo = WorkspaceCombo(ws, Table)
        f.add_widget("table", "Source table", self.table_combo)
        f.add_text("time_col", "Time column", "time", "Table/file column holding times.")
        f.add_combo("fmt", "Time format", TIME_FORMATS, "Format of numeric/string time values.")
        f.add_combo("scale", "Time scale", TIME_SCALES)
        f.add_text("start", "Start time", "2020-01-01T00:00:00", "ISO string, JD via format "
                   "'jd' not needed here (regular/binned modes).")
        f.add_text("delta", "Time delta / bin size", "0.5 day", "Quantity, e.g. '30 s', '0.5 day'.")
        f.add_text("end", "Bin end (binned)", "", "Optional end of the last bin. With n bins > 0 "
                   "the bin size becomes (end - start) / n; with n = 0 the bin size field "
                   "is used and enough bins are created to reach the end.")
        f.add_int("n", "n samples / bins", 100, 0, 10_000_000,
                  "Regular: samples. Binned: bins (0 = derive from bin end).")
        f.add_multiline("data", "Data columns", "flux = 1 + 0*t",
                        "One 'name = expression' per line. Names: n (rows), t (days since "
                        "first sample).")
        f.add_text("path", "File", "", "Path for 'Read from file'.")
        f.add_combo("fileformat", "File format",
                    ["auto", "kepler.fits", "tess.fits", "ascii.ecsv", "ascii.csv",
                     "ascii.basic", "fits"], editable=True,
                    tip="'kepler.fits'/'tess.fits' need no time column.")
        self.add_button("Browse file...", self.browse)
        self.add_button("Create series", lambda: self.guard(self.create_series))
        self.info = self.add_output("Info")
        self.view = self.add_table("Table")

    def browse(self) -> None:
        path = self.ask_open_path("Open time series file")
        if path:
            self.form.set_value("path", path)

    def create_series(self) -> None:
        v = self.form.values()
        mode = self.MODES.index(v["mode"])
        name = v["name"]
        if not name:
            raise ParseError("Enter a result name.")
        if mode == 0:
            ts = ts_from_table(self.table_combo.selected(), v["time_col"], v["fmt"], v["scale"])
        elif mode == 1:
            n = int(v["n"])
            if n < 1:
                raise ParseError("n samples must be >= 1.")
            ts = TimeSeries(time_start=parse_time(v["start"], name="start time"),
                            time_delta=parse_quantity(v["delta"], u.day, "time delta"),
                            n_samples=n)
        elif mode == 2:
            start = parse_time(v["start"], name="start time")
            kw: Dict[str, Any] = {"time_bin_start": start}
            n_bins = int(v["n"])
            if v["end"]:
                span = (parse_time(v["end"], name="bin end") - start).to(u.day)
                if span.value <= 0:
                    raise ParseError("Bin end must be later than the start time.")
                if n_bins > 0:
                    kw["time_bin_size"] = span / n_bins
                else:
                    size = parse_quantity(v["delta"], u.day, "bin size")
                    if size.value <= 0:
                        raise ParseError("Bin size must be positive.")
                    n_bins = int(np.ceil((span / size).decompose().value))
                    kw["time_bin_size"] = size
            else:
                kw["time_bin_size"] = parse_quantity(v["delta"], u.day, "bin size")
                if n_bins < 1:
                    raise ParseError("Enter the number of bins, or a bin end.")
            kw["n_bins"] = n_bins
            ts = BinnedTimeSeries(**kw)
        else:
            if not v["path"]:
                raise ParseError("Enter a file path.")
            kw = {}
            fmt = v["fileformat"]
            if fmt not in ("", "auto"):
                kw["format"] = fmt
            if not fmt.endswith(".fits") or fmt == "fits":
                kw["time_column"] = v["time_col"]
            if v["fmt"] != "auto":
                kw["time_format"] = v["fmt"]
            if v["scale"] != "auto":
                kw["time_scale"] = v["scale"]
            try:
                ts = TimeSeries.read(v["path"], **kw)
            except (OSError, ValueError, TypeError, KeyError) as exc:
                raise ParseError(f"Cannot read {v['path']!r}: {exc}") from None
        if mode in (1, 2) and v["data"]:
            add_columns_from_text(ts, v["data"])
        self.ws.put(name, ts)
        self.info.show_text(_info(ts))
        self.view.set_table(ts)
        self.set_status(f"Stored {type(ts).__name__} '{name}' ({len(ts)} rows)")


class SyntheticPanel(ModulePanel):
    def __init__(self, ws: Workspace) -> None:
        super().__init__(ws)
        f = self.form
        f.add_text("name", "Result name", "synthetic")
        f.add_combo("kind", "Signal", ["sinusoid", "transit", "sinusoid+transit", "noise"])
        f.add_int("n", "Points", 1000, 3, 5_000_000)
        f.add_float("duration", "Duration [d]", 100.0, 1e-6, 1e7, 4)
        f.add_text("start", "Start time", "2020-01-01T00:00:00")
        f.add_check("irregular", "Irregular sampling", True, "Random sorted times.")
        f.add_float("period", "Period [d]", 3.7, 1e-6, 1e7, 6)
        f.add_float("amp", "Sine amplitude", 1.0, 0, 1e9, 4)
        f.add_float("phase", "Sine phase [cycles]", 0.0, -1e6, 1e6, 4)
        f.add_float("depth", "Transit depth", 0.01, 0, 1e9, 5)
        f.add_float("tdur", "Transit duration [d]", 0.2, 1e-6, 1e6, 4)
        f.add_float("t_tr", "Transit epoch [d]", 1.0, -1e6, 1e7, 4)
        f.add_float("noise", "Noise sigma", 0.1, 0, 1e9, 5)
        f.add_int("seed", "Random seed", 0, 0, 2**31 - 1)
        self.add_button("Generate", lambda: self.guard(self.generate))
        self.info = self.add_output("Info")
        self.canvas = self.add_plot("Light curve")

    def generate(self) -> None:
        v = self.form.values()
        if not v["name"]:
            raise ParseError("Enter a result name.")
        ts = make_synthetic(v["kind"], v["n"], v["duration"], v["start"], v["irregular"],
                            v["period"], v["amp"], v["phase"], v["depth"], v["tdur"], v["t_tr"],
                            v["noise"], v["seed"])
        self.ws.put(v["name"], ts)
        self.info.show_text(_info(ts))
        t = (ts.time - ts.time[0]).to_value(u.day)
        plot_xy(self.canvas, t, np.asarray(ts["flux"]), np.asarray(ts["flux_err"]),
                f"t - {ts.time[0].isot} [d]", "flux", v["name"])
        self.set_status(f"Stored TimeSeries '{v['name']}'")


class EditPanel(SeriesPanel):
    def __init__(self, ws: Workspace) -> None:
        super().__init__(ws)
        f = self.form
        f.add_text("newcol", "New column", "", "Name for a computed column.")
        f.add_text("expr", "Expression", "", "Uses column names, n and t [days]; e.g. "
                   "flux / np.nanmedian(flux)")
        f.add_text("dropcols", "Remove columns", "", "Comma-separated names.")
        f.add_text("t_from", "Keep from", "", "ISO time; blank = open.")
        f.add_text("t_to", "Keep until", "", "ISO time; blank = open.")
        f.add_text("out", "Result name", "", "Blank = replace the selected series.")
        self.add_button("Show", lambda: self.guard(self.show_series))
        self.add_button("Add column", lambda: self.guard(self.add_column))
        self.add_button("Remove columns", lambda: self.guard(self.drop))
        self.add_button("Slice by time", lambda: self.guard(self.slice_time))
        self.add_button("Sort by time", lambda: self.guard(self.sort))
        self.add_button("Plot", lambda: self.guard(self.plot))
        self.add_button("Save as file...", lambda: self.guard(self.save))
        self.info = self.add_output("Info")
        self.view = self.add_table("Table")
        self.canvas = self.add_plot("Plot")

    def _store(self, ts: Any) -> None:
        name = self.form.value("out") or self.src.currentText()
        self.ws.put(name, ts)
        self.info.show_text(_info(ts))
        self.view.set_table(ts)
        self.set_status(f"Stored '{name}' ({len(ts)} rows)")

    def show_series(self) -> None:
        ts = self.current_series()
        self.info.show_text(_info(ts))
        self.view.set_table(ts)

    def add_column(self) -> None:
        name, expr = self.form.value("newcol"), self.form.value("expr")
        if not name.isidentifier():
            raise ParseError("Enter a valid column name.")
        ts = self.current_series().copy()
        if name in ts.colnames:
            raise ParseError(f"Column {name!r} already exists.")
        add_columns_from_text_ns(ts, name, expr)
        self._store(ts)

    def drop(self) -> None:
        names = [n.strip() for n in self.form.value("dropcols").split(",") if n.strip()]
        ts = self.current_series().copy()
        bad = [n for n in names if n not in ts.colnames]
        if not names or bad:
            raise ParseError(f"Unknown or empty column list: {bad or names}.")
        if "time" in names or "time_bin_start" in names:
            raise ParseError("The time column cannot be removed.")
        ts.remove_columns(names)
        self._store(ts)

    def slice_time(self) -> None:
        ts = self.current_series()
        times = ts.time_bin_start if isinstance(ts, BinnedTimeSeries) else ts.time
        mask = np.ones(len(ts), dtype=bool)
        if self.form.value("t_from"):
            mask &= times >= parse_time(self.form.value("t_from"), name="start")
        if self.form.value("t_to"):
            mask &= times <= parse_time(self.form.value("t_to"), name="end")
        if not mask.any():
            raise ParseError("The time range contains no rows.")
        self._store(ts[mask])

    def sort(self) -> None:
        ts = self.current_series().copy()
        ts.sort("time_bin_start" if isinstance(ts, BinnedTimeSeries) else "time")
        self._store(ts)

    def plot(self) -> None:
        a = self.arrays(min_points=1)
        plot_xy(self.canvas, a.t.value, a.y, a.dy,
                f"t - {a.t0.isot} [d]" if a.t0 is not None else "time [d]",
                self.ycombo.column() + (f" [{a.yunit}]" if a.yunit else ""),
                self.src.currentText())
        self.tabs.setCurrentWidget(self.canvas)
        if a.dropped:
            self.set_status(f"{a.dropped} non-finite rows skipped")

    def save(self) -> None:
        ts = self.current_series()
        path = self.ask_save_path("Save time series", "ECSV (*.ecsv);;CSV (*.csv);;FITS (*.fits)",
                                  self.src.currentText() + ".ecsv")
        if not path:
            return
        fmt = {"csv": "ascii.csv", "fits": "fits"}.get(path.rsplit(".", 1)[-1].lower(),
                                                       "ascii.ecsv")
        ts.write(path, format=fmt, overwrite=True)
        self.set_status(f"Saved {path}")


def add_columns_from_text_ns(ts: Any, name: str, expr: str) -> None:
    """Add ``name`` = ``expr`` evaluated with the series' columns as variables."""
    n = len(ts)
    tt = sample_times(ts)
    t = (tt - tt.min()).to_value(u.day) if not isinstance(tt, TimeDelta) else tt.to_value(u.day)
    ns: Dict[str, Any] = {"n": n, "t": t}
    for c in ts.colnames:
        col = ts[c]
        if c.isidentifier() and not isinstance(col, (Time, TimeDelta)):
            ns[c] = col.quantity if getattr(col, "unit", None) else np.asarray(col)
    value = safe_eval(expr, ns)
    if np.ndim(value) == 0:
        value = np.full(n, value) if not isinstance(value, u.Quantity) else \
            np.full(n, value.value) * value.unit
    if np.shape(value) != (n,):
        raise ParseError(f"Expression must give a scalar or {n} values (got {np.shape(value)}).")
    ts[name] = value


class FoldBinPanel(SeriesPanel):
    AGG = {"mean": np.nanmean, "median": np.nanmedian, "sum": np.nansum, "min": np.nanmin,
           "max": np.nanmax, "std": np.nanstd}

    def __init__(self, ws: Workspace) -> None:
        super().__init__(ws)
        f = self.form
        f.add_text("period", "Fold period", "3.7 day", "Quantity.")
        f.add_text("epoch", "Epoch time", "", "ISO time of phase zero (blank = first sample).")
        f.add_text("epoch_phase", "Epoch phase", "0", "Phase at epoch: days or cycles if "
                   "normalised.")
        f.add_text("wrap", "Wrap phase", "", "Upper wrap bound (blank = default).")
        f.add_check("normalize", "Normalise phase", False, "Phase in cycles [-0.5, 0.5).")
        f.add_text("fold_out", "Folded name", "folded")
        f.add_text("bin_size", "Bin size", "1 day", "Quantity.")
        f.add_text("bin_start", "Bin start", "", "ISO time, blank = series start.")
        f.add_text("bin_end", "Bin end", "", "ISO time, blank = series end.")
        f.add_int("n_bins", "n bins", 0, 0, 10_000_000, "0 = from bin size.")
        f.add_combo("agg", "Aggregate", list(self.AGG), "NaN-aware reduction per bin.")
        f.add_text("bin_out", "Binned name", "binned")
        self.add_button("Fold", lambda: self.guard(self.fold))
        self.add_button("Bin (aggregate_downsample)", lambda: self.guard(self.bin))
        self.info = self.add_output("Info")
        self.view = self.add_table("Table")
        self.canvas = self.add_plot("Plot")

    def fold(self) -> None:
        ts = self.current_series()
        if not isinstance(ts, TimeSeries):
            raise ParseError("Folding needs a TimeSeries, not a BinnedTimeSeries.")
        v = self.form.values()
        period = parse_quantity(v["period"], u.day, "period")
        if not (np.isfinite(period.value) and period.value > 0):
            raise ParseError("Period must be positive.")
        norm = v["normalize"]
        kw: Dict[str, Any] = {"period": period, "normalize_phase": norm}
        if v["epoch"]:
            kw["epoch_time"] = parse_time(v["epoch"], name="epoch time")
        if v["epoch_phase"]:
            kw["epoch_phase"] = (float(v["epoch_phase"]) if norm else
                                 parse_quantity(v["epoch_phase"], u.day, "epoch phase"))
        if v["wrap"]:
            kw["wrap_phase"] = (float(v["wrap"]) if norm else
                                parse_quantity(v["wrap"], u.day, "wrap phase"))
        try:
            folded = ts.fold(**kw)
        except (ValueError, TypeError, u.UnitsError) as exc:
            raise ParseError(f"Fold failed: {exc}") from None
        if not v["fold_out"]:
            raise ParseError("Enter a folded name.")
        self.ws.put(v["fold_out"], folded)
        ph = folded["time"]
        x = ph.to_value(u.day) if isinstance(ph, TimeDelta) else np.asarray(ph.value)
        y = column_floats(folded[self.ycombo.column()])
        e = self.ecombo.column()
        plot_xy(self.canvas, x, y, column_floats(folded[e]) if e else None,
                "phase [cycles]" if norm else "phase [d]", self.ycombo.column(),
                f"{self.src.currentText()} folded at {period}")
        self.view.set_table(folded)
        self.info.show_text(f"Folded series stored as '{v['fold_out']}'.\n"
                            f"phase range: {np.nanmin(x):.6g} .. {np.nanmax(x):.6g}")
        self.tabs.setCurrentWidget(self.canvas)

    def bin(self) -> None:
        ts = self.current_series()
        v = self.form.values()
        kw: Dict[str, Any] = {"aggregate_func": self.AGG[v["agg"]]}
        if v["bin_start"]:
            kw["time_bin_start"] = parse_time(v["bin_start"], name="bin start")
        if v["bin_end"]:
            kw["time_bin_end"] = parse_time(v["bin_end"], name="bin end")
        if int(v["n_bins"]) > 0:
            kw["n_bins"] = int(v["n_bins"])
        if "time_bin_end" not in kw:
            kw["time_bin_size"] = parse_quantity(v["bin_size"], u.day, "bin size")
        if not v["bin_out"]:
            raise ParseError("Enter a binned name.")
        if not isinstance(ts, TimeSeries):
            raise ParseError("Binning needs a TimeSeries.")
        src = ts
        out_name = v["bin_out"]

        def work() -> Any:
            return aggregate_downsample(src, **kw)

        def done(binned: Any) -> None:
            self.ws.put(out_name, binned)
            self.view.set_table(binned)
            self.info.show_text(f"Binned series '{out_name}': {len(binned)} bins "
                                f"(from {len(src)} rows).")
            y = self.ycombo.column()
            if y in binned.colnames:
                centers = (binned.time_bin_center - src.time.min()).to_value(u.day)
                e = self.ecombo.column()
                plot_xy(self.canvas, centers, column_floats(binned[y]),
                        column_floats(binned[e]) if e and e in binned.colnames else None,
                        f"t - {src.time.min().isot} [d]", y, out_name)
                self.tabs.setCurrentWidget(self.canvas)

        self.run(work, done, busy_text="Binning...")


class LombScarglePanel(SeriesPanel):
    NORMS = ["standard", "model", "log", "psd"]

    def __init__(self, ws: Workspace) -> None:
        super().__init__(ws, with_bands=True)
        f = self.form
        f.add_check("multiband", "Multiband", False, "Use LombScargleMultiband with the band "
                    "column; no FAP/model.")
        f.add_combo("norm", "Normalization", self.NORMS)
        methods = ["auto"] + [m for m in LombScargle.available_methods if m != "auto"]
        f.add_combo("method", "Method", methods, "'fast' also selects the fast multiband "
                    "algorithm.")
        f.add_int("nterms", "n terms", 1, 1, 50, ">1 needs chi2/fastchi2.")
        f.add_check("fit_mean", "Fit mean", True)
        f.add_check("center", "Center data", True)
        f.add_float("spp", "Samples per peak", 5, 0.1, 1000, 2)
        f.add_float("nyq", "Nyquist factor", 5, 0.01, 1000, 2)
        f.add_text("fmin", "Min frequency", "", "Quantity, default 1/day; blank = auto.")
        f.add_text("fmax", "Max frequency", "", "Quantity, default 1/day; blank = auto.")
        f.add_text("freq", "Manual frequencies", "", "Expression e.g. linspace(0.01, 1, 5000) "
                    "(1/day); overrides the auto grid.")
        f.add_combo("fap_method", "FAP method", ["baluev", "davies", "naive", "bootstrap"])
        f.add_int("n_boot", "Bootstraps", 100, 10, 100000)
        f.add_text("levels", "FAP levels", "0.1, 0.05, 0.01", "Probabilities for threshold lines.")
        f.add_combo("xaxis", "Plot x axis", ["frequency", "period"])
        f.add_check("logx", "Log x axis", False)
        f.add_text("out", "Result name", "periodogram")
        self.add_button("Compute periodogram", lambda: self.guard(self.compute))
        self.result = self.add_output("Result")
        self.pg_canvas = self.add_plot("Periodogram")
        self.fold_canvas = self.add_plot("Folded + model")
        self.dist_canvas = self.add_plot("Null distribution")
        self.view = self.add_table("Table")
        self._last: Optional[Tuple[Arrays, Dict[str, Any]]] = None
        self.form.fields["xaxis"].currentTextChanged.connect(lambda *_: self._replot())
        self.form.fields["logx"].toggled.connect(lambda *_: self._replot())

    def compute(self) -> None:
        v = self.form.values()
        multi = v["multiband"]
        a = self.arrays(bands=multi, min_points=4)
        levels = [] if not v["levels"] else [float(x) for x in parse_float_list(v["levels"])]
        if any(not 0 < x < 1 for x in levels):
            raise ParseError("FAP levels must lie in (0, 1).")
        if v["nterms"] > 1 and not multi and v["method"] not in ("auto", "chi2", "fastchi2"):
            raise ParseError("n terms > 1 requires method auto, chi2 or fastchi2.")
        freq_expr = None
        if v["freq"]:
            arr = parse_array(v["freq"], "frequencies")
            if arr.size < 2 or np.any(arr <= 0):
                raise ParseError("Manual frequencies must be >= 2 positive values.")
            freq_expr = arr / u.day
        p = {
            "multiband": multi, "normalization": v["norm"], "method": v["method"],
            "nterms": v["nterms"], "fit_mean": v["fit_mean"], "center_data": v["center"],
            "spp": v["spp"], "nyq": v["nyq"], "freq_expr": freq_expr,
            "fmin": _opt_quantity(v["fmin"], 1 / u.day, "min frequency"),
            "fmax": _opt_quantity(v["fmax"], 1 / u.day, "max frequency"),
            "fap_method": v["fap_method"], "n_boot": v["n_boot"],
            "levels": levels,
        }
        for key in ("fmin", "fmax"):
            if p[key] is not None and not p[key].unit.is_equivalent(1 / u.day):
                raise ParseError("Frequencies need units of 1/time.")
            if p[key] is not None and p[key].value <= 0:
                raise ParseError("Frequency limits must be positive.")
        if p["fmin"] is not None and p["fmax"] is not None and p["fmin"] >= p["fmax"]:
            raise ParseError("Min frequency must be below max frequency.")
        out_name = v["out"]

        def work() -> Dict[str, Any]:
            return run_lomb_scargle(a, p)

        def done(res: Dict[str, Any]) -> None:
            self._last = (a, res)
            if out_name:
                self.ws.put(out_name, res["table"])
            self.view.set_table(res["table"])
            self.result.show_text(self._summary(a, res))
            self._replot()
            self.tabs.setCurrentWidget(self.pg_canvas)

        self.run(work, done, busy_text="Computing periodogram...")

    @staticmethod
    def _summary(a: Arrays, r: Dict[str, Any]) -> str:
        lines = [f"points used: {len(a.y)} (skipped {a.dropped})",
                 f"frequencies: {len(r['freq'])}  [{r['freq'].min():.6g}, {r['freq'].max():.6g}] 1/d",
                 f"normalization: {r['normalization']}",
                 f"best frequency: {r['best_f']:.8g} 1/d",
                 f"best period:    {r['best_period']:.8g} d",
                 f"peak power:     {r['best_power']:.8g}"]
        if r["fap"] is not None:
            lines.append(f"false-alarm probability ({r['fap_method']}): {r['fap']:.4g}")
        for pr, lvl in r["levels"].items():
            lines.append(f"  FAP {pr:g} level: power {lvl:.6g}")
        if r["params"] is not None:
            lines.append(f"model parameters: {np.array2string(np.asarray(r['params']), precision=6)}")
        lines += [f"note: {n}" for n in r["notes"]]
        return "\n".join(lines)

    def _replot(self) -> None:
        if self._last is None:
            return
        a, r = self._last
        use_period = self.form.value("xaxis") == "period"
        x = 1.0 / r["freq"] if use_period else r["freq"]
        ax = self.pg_canvas.axes()
        order = np.argsort(x)
        ax.plot(x[order], r["power"][order], "k-", lw=0.8)
        best = r["best_period"] if use_period else r["best_f"]
        ax.axvline(best, color="C3", ls=":", lw=1, label=f"peak {best:.6g}")
        for pr, lvl in r["levels"].items():
            ax.axhline(lvl, ls="--", lw=0.8, color="gray")
            ax.annotate(f"FAP {pr:g}", (x.min(), lvl), fontsize=7, va="bottom")
        ax.set_xlabel("period [d]" if use_period else "frequency [1/d]")
        ax.set_ylabel(f"power ({r['normalization']})")
        if self.form.value("logx"):
            ax.set_xscale("log")
        ax.legend(loc="best", fontsize="small")
        self.pg_canvas.redraw()
        # folded data + model
        period = r["best_period"]
        if np.isfinite(period) and period > 0:
            ph = ((a.t.value - a.t.value.min()) / period) % 1.0
            plot_xy(self.fold_canvas, ph, a.y, a.dy, "phase [cycles]",
                    self.ycombo.column(), f"folded at P = {period:.6g} d",
                    model=r["model"], bands=a.bands if r["multiband"] else None)
        if r["dist"] is not None:
            ax = self.dist_canvas.axes()
            ax.plot(*r["dist"], "k-")
            ax.axvline(r["best_power"], color="C3", ls=":", label="observed peak")
            ax.set_xlabel("power")
            ax.set_ylabel("null probability density")
            ax.legend(fontsize="small")
            self.dist_canvas.redraw()
        else:
            self.dist_canvas.clear()


class BlsPanel(SeriesPanel):
    def __init__(self, ws: Workspace) -> None:
        super().__init__(ws)
        f = self.form
        f.add_text("durations", "Durations", "0.05, 0.1, 0.2", "Trial transit durations in days "
                   "(numbers, or an expression with units).")
        f.add_text("periods", "Manual periods", "", "Expression/list in days (e.g. linspace(1, "
                   "10, 5000)); blank = autoperiod.")
        f.add_text("pmin", "Min period", "", "Quantity, default day; blank = auto.")
        f.add_text("pmax", "Max period", "", "Quantity, default day; blank = auto.")
        f.add_int("min_transits", "Min transits", 3, 1, 1000)
        f.add_float("freq_factor", "Frequency factor", 1.0, 0.01, 1000, 3,
                    "Larger = coarser period grid.")
        f.add_combo("objective", "Objective", ["likelihood", "snr"])
        f.add_combo("method", "Method", ["fast", "slow"])
        f.add_int("oversample", "Oversample", 10, 1, 1000)
        f.add_text("out", "Result name", "bls")
        f.add_text("masked_out", "Masked series name", "masked", "For 'Mask transits'.")
        self.add_button("Run BLS", lambda: self.guard(self.compute))
        self.add_button("Mask transits -> new series", lambda: self.guard(self.mask_transits))
        self.result = self.add_output("Result")
        self.pg_canvas = self.add_plot("Periodogram")
        self.fold_canvas = self.add_plot("Folded + model")
        self.stats_view = self.add_table("Stats")
        self.view = self.add_table("Table")
        self._last: Optional[Tuple[Arrays, Dict[str, Any], str]] = None

    def compute(self) -> None:
        v = self.form.values()
        a = self.arrays(min_points=5)
        dur = parse_array(v["durations"], "durations") if v["durations"] else None
        if dur is None or np.any(dur <= 0):
            raise ParseError("Durations must be positive numbers (days).")
        periods = None
        if v["periods"]:
            periods = parse_array(v["periods"], "periods")
            if periods.size == 0 or np.any(periods <= 0):
                raise ParseError("Manual periods must be positive.")
            periods = periods * u.day
        p = {
            "durations": dur * u.day, "periods": periods,
            "pmin": _opt_quantity(v["pmin"], u.day, "min period"),
            "pmax": _opt_quantity(v["pmax"], u.day, "max period"),
            "min_transits": v["min_transits"], "freq_factor": v["freq_factor"],
            "objective": v["objective"], "method": v["method"], "oversample": v["oversample"],
        }
        if periods is not None and periods.min().value <= dur.max():
            raise ParseError("All trial periods must exceed the longest duration.")
        if p["pmin"] is not None and p["pmin"].to_value(u.day) <= dur.max():
            raise ParseError("Min period must exceed the longest duration.")
        out_name, src_name = v["out"], self.src.currentText()

        def work() -> Dict[str, Any]:
            return run_bls(a, p)

        def done(res: Dict[str, Any]) -> None:
            self._last = (a, res, src_name)
            if out_name:
                self.ws.put(out_name, res["table"])
            self.view.set_table(res["table"])
            self._show(a, res)
            self.tabs.setCurrentWidget(self.pg_canvas)

        self.run(work, done, busy_text="Running BLS...")

    def _show(self, a: Arrays, r: Dict[str, Any]) -> None:
        st = r["stats"]
        lines = [f"points used: {len(a.y)} (skipped {a.dropped})",
                 f"trial periods: {len(r['table'])}",
                 f"best period:   {r['period']:.8g} d",
                 f"duration:      {r['duration']:.6g} d",
                 f"transit time:  {absolute_time(a, r['transit_time'])}",
                 f"depth:         {r['depth']:.6g} +/- {r['depth_err']:.3g}  "
                 f"(SNR {r['depth_snr']:.3g})",
                 f"power ({r['objective']}): {r['power']:.6g}",
                 f"odd/even depth: {st['depth_odd'][0]:.6g} / {st['depth_even'][0]:.6g}",
                 f"transits observed: {int(np.sum(np.asarray(st['per_transit_count']) > 0))}",
                 f"in-transit points: {int(r['mask'].sum())}"]
        self.result.show_text("\n".join(lines))
        stats = Table({
            "transit_time": [absolute_time(a, float(x.to_value(u.day)))
                             for x in np.atleast_1d(st["transit_times"])],
            "points": np.asarray(st["per_transit_count"]),
            "log_likelihood": np.asarray(st["per_transit_log_likelihood"], dtype=float)})
        self.stats_view.set_table(stats)
        ax = self.pg_canvas.axes()
        per = np.asarray(r["table"]["period"], dtype=float)  # days
        order = np.argsort(per)
        ax.plot(per[order], np.asarray(r["table"]["power"])[order], "k-", lw=0.7)
        ax.axvline(r["period"], color="C3", ls=":", label=f"P = {r['period']:.6g} d")
        ax.set_xlabel("period [d]")
        ax.set_ylabel(f"BLS power ({r['objective']})")
        ax.legend(fontsize="small")
        self.pg_canvas.redraw()
        ph = fold_phase(a.t.value, r["period"], r["transit_time"])
        plot_xy(self.fold_canvas, ph, a.y, a.dy, "phase from mid-transit [d]",
                self.ycombo.column(), "folded at best period", model=r["model"])

    def mask_transits(self) -> None:
        if self._last is None:
            raise ParseError("Run BLS first.")
        a, r, src_name = self._last
        if src_name not in self.ws:
            raise ParseError(f"Series {src_name!r} is no longer in the workspace.")
        name = self.form.value("masked_out")
        if not name:
            raise ParseError("Enter a name for the masked series.")
        ts = self.ws.get(src_name)
        keep = np.ones(len(ts), dtype=bool)
        keep[a.index[r["mask"]]] = False
        self.ws.put(name, ts[keep])
        self.set_status(f"Stored '{name}' without {int((~keep).sum())} in-transit rows")


def _spec(key: str, title: str, cls: type, desc: str) -> ModuleSpec:
    return ModuleSpec(key, title, CATEGORY, lambda ws, c=cls: c(ws), desc)


SPECS = [
    _spec("ts_create", "Time Series: Create", CreatePanel,
          "TimeSeries / BinnedTimeSeries from tables, regular sampling, bins or files"),
    _spec("ts_synthetic", "Time Series: Synthetic data", SyntheticPanel,
          "Generate sinusoid / transit test light curves"),
    _spec("ts_edit", "Time Series: Edit & Plot", EditPanel,
          "Inspect, add/remove columns, slice, sort, plot, save"),
    _spec("ts_fold_bin", "Time Series: Fold & Bin", FoldBinPanel,
          "TimeSeries.fold and aggregate_downsample"),
    _spec("ts_lombscargle", "Time Series: Lomb-Scargle", LombScarglePanel,
          "LombScargle / LombScargleMultiband periodograms with false-alarm levels"),
    _spec("ts_bls", "Time Series: Box Least Squares", BlsPanel,
          "BoxLeastSquares transit search with statistics and masking"),
]
