import numpy as np
import pytest
from astropy import units as u
from astropy.table import Table
from astropy.time import Time, TimeDelta
from astropy.timeseries import BinnedTimeSeries, TimeSeries

from astrotools_adv.core.parsing import ParseError
from astrotools_adv.modules import timeseries_tools as tt


@pytest.fixture(autouse=True)
def errors(monkeypatch):
    """Collect errors that panels would show in a dialog; a test must clear expected ones."""
    seen = []
    monkeypatch.setattr("astrotools_adv.core.widgets.error_box",
                        lambda parent, exc, detail="": seen.append(exc))
    yield seen
    assert not seen, f"unexpected error dialogs: {seen!r}"


@pytest.fixture(autouse=True)
def _flush_events(qtbot):
    """Run queued canvas redraws while the widgets still exist."""
    yield
    from PyQt5.QtWidgets import QApplication
    for _ in range(3):
        QApplication.processEvents()


def make_panel(qtbot, ws, cls):
    panel = cls(ws)
    qtbot.addWidget(panel)
    return panel


def test_specs_are_analysis():
    assert {s.key for s in tt.SPECS} >= {"ts_create", "ts_bls", "ts_lombscargle"}
    assert all(s.category == "Analysis" for s in tt.SPECS)


def test_make_synthetic_deterministic_and_validated():
    a = tt.make_synthetic("sinusoid", 200, 50, seed=3)
    b = tt.make_synthetic("sinusoid", 200, 50, seed=3)
    assert np.array_equal(a["flux"], b["flux"]) and len(a) == 200
    with pytest.raises(ParseError):
        tt.make_synthetic("bogus", 10, 5)
    with pytest.raises(ParseError):
        tt.make_synthetic("transit", 100, 10, period=1.0, transit_duration=2.0)
    with pytest.raises(ParseError):
        tt.make_synthetic("sinusoid", 2, 10)


def test_extract_drops_nonfinite_and_checks_columns():
    ts = tt.make_synthetic("sinusoid", 50, 10)
    ts["flux"][3] = np.nan
    a = tt.extract(ts, "flux", "flux_err")
    assert len(a.y) == 49 and a.dropped == 1 and 3 not in a.index
    with pytest.raises(ParseError):
        tt.extract(ts, "nope")
    with pytest.raises(ParseError):
        tt.extract(ts, "")
    ts["flux"][:] = np.nan
    with pytest.raises(ParseError):
        tt.extract(ts, "flux")


def test_lomb_scargle_recovers_injected_period():
    ts = tt.make_synthetic("sinusoid", 600, 100, irregular=True, period=3.7, noise=0.3, seed=1)
    a = tt.extract(ts, "flux", "flux_err")
    res = tt.run_lomb_scargle(a, dict(
        multiband=False, normalization="standard", method="auto", nterms=1, fit_mean=True,
        center_data=True, spp=10, nyq=5, freq_expr=None, fmin=None, fmax=None,
        fap_method="baluev", n_boot=20, levels=[0.01]))
    assert res["best_period"] == pytest.approx(3.7, abs=0.05)
    assert res["fap"] < 1e-10
    assert 0.01 in res["levels"] and res["model"] is not None and res["dist"] is not None
    assert res["table"].colnames == ["frequency", "period", "power"]


def test_lomb_scargle_panel_end_to_end(qtbot, ws):
    ws.put("lc", tt.make_synthetic("sinusoid", 400, 60, irregular=True, period=3.7,
                                   noise=0.2, seed=2))
    panel = make_panel(qtbot, ws, tt.LombScarglePanel)
    panel.form.set_value("fmin", "0.05")
    panel.form.set_value("fmax", "1")
    panel.compute()
    assert "periodogram" in ws
    best = panel._last[1]["best_period"]
    assert best == pytest.approx(3.7, abs=0.1)
    assert "best period" in panel.result.toPlainText()
    panel.form.set_value("xaxis", "period")
    panel.form.set_value("logx", True)
    panel.form.set_value("fap_method", "bootstrap")
    panel.form.set_value("n_boot", 10)
    panel.compute()


def test_lomb_scargle_input_errors(qtbot, ws):
    panel = make_panel(qtbot, ws, tt.LombScarglePanel)
    with pytest.raises(ParseError):       # nothing in workspace
        panel.compute()
    ws.put("lc", tt.make_synthetic("sinusoid", 100, 10))
    panel.form.set_value("levels", "2")
    with pytest.raises(ParseError):
        panel.compute()
    panel.form.set_value("levels", "0.01")
    panel.form.set_value("fmin", "5")
    panel.form.set_value("fmax", "1")
    with pytest.raises(ParseError):
        panel.compute()


def test_multiband_runs():
    ts = tt.make_synthetic("sinusoid", 300, 40, irregular=True, period=2.5, noise=0.1, seed=4)
    ts["band"] = np.where(np.arange(300) % 2 == 0, "g", "r")
    a = tt.extract(ts, "flux", "flux_err", "band")
    res = tt.run_lomb_scargle(a, dict(
        multiband=True, normalization="standard", method="auto", nterms=1, fit_mean=True,
        center_data=True, spp=5, nyq=5, freq_expr=None, fmin=None, fmax=None,
        fap_method="baluev", n_boot=10, levels=[]))
    assert res["best_period"] == pytest.approx(2.5, abs=0.1)
    assert res["fap"] is None and res["notes"]


def test_bls_recovers_transit_period(qtbot, ws):
    ts = tt.make_synthetic("transit", 3000, 40, irregular=True, period=5.3, depth=0.01,
                           transit_duration=0.2, t_transit=1.0, noise=0.002, seed=5)
    ws.put("lc", ts)
    panel = make_panel(qtbot, ws, tt.BlsPanel)
    panel.form.set_value("durations", "0.1, 0.2")
    panel.form.set_value("pmin", "2")
    panel.form.set_value("pmax", "10")
    panel.form.set_value("freq_factor", 4.0)
    panel.compute()
    r = panel._last[1]
    assert r["period"] == pytest.approx(5.3, abs=0.05)
    assert r["depth"] == pytest.approx(0.01, rel=0.2)
    assert "bls" in ws
    n_in = int(r["mask"].sum())
    assert n_in > 0
    panel.mask_transits()
    assert len(ws.get("masked")) == 3000 - n_in


def test_bls_errors(qtbot, ws):
    ws.put("lc", tt.make_synthetic("transit", 200, 20, period=3.0, seed=1))
    panel = make_panel(qtbot, ws, tt.BlsPanel)
    with pytest.raises(ParseError):
        panel.mask_transits()
    panel.form.set_value("durations", "-1")
    with pytest.raises(ParseError):
        panel.compute()
    panel.form.set_value("durations", "5")
    panel.form.set_value("pmin", "1")
    with pytest.raises(ParseError):
        panel.compute()


def test_fold_phase_range_and_panel(qtbot, ws):
    ws.put("lc", tt.make_synthetic("sinusoid", 300, 30, irregular=True, period=3.7, seed=6))
    panel = make_panel(qtbot, ws, tt.FoldBinPanel)
    panel.form.set_value("period", "3.7 day")
    panel.form.set_value("normalize", True)
    panel.fold()
    ph = np.asarray(ws.get("folded")["time"].value)
    assert ph.min() >= -0.5 and ph.max() < 0.5
    panel.form.set_value("normalize", False)
    panel.fold()
    ph = ws.get("folded")["time"].to_value(u.day)
    assert ph.min() >= -1.85 and ph.max() < 1.85
    panel.form.set_value("period", "-1 day")
    with pytest.raises(ParseError):
        panel.fold()
    ws.put("b", BinnedTimeSeries(time_bin_start="2020-01-01", time_bin_size=1 * u.day, n_bins=3))
    panel.src.setCurrentText("b")
    panel.form.set_value("period", "1 day")
    with pytest.raises(ParseError):
        panel.fold()


def test_aggregate_downsample_bin_counts(qtbot, ws):
    ts = TimeSeries(time_start="2020-01-01", time_delta=1 * u.day, n_samples=20)
    ts["ones"] = np.ones(20)
    ws.put("lc", ts)
    panel = make_panel(qtbot, ws, tt.FoldBinPanel)
    panel.src.setCurrentText("lc")
    panel.ycombo.setCurrentText("ones")
    panel.form.set_value("bin_size", "5 day")
    panel.form.set_value("bin_start", "2019-12-31T12:00:00")  # edges between samples
    panel.form.set_value("agg", "sum")
    panel.bin()
    b = ws.get("binned")
    assert isinstance(b, BinnedTimeSeries) and len(b) == 4
    assert list(b["ones"]) == [5, 5, 5, 5]


def test_create_panel_modes(qtbot, ws, tmp_path):
    panel = make_panel(qtbot, ws, tt.CreatePanel)
    f = panel.form
    f.set_value("mode", panel.MODES[1])
    f.set_value("n", 10)
    f.set_value("delta", "30 s")
    f.set_value("data", "flux = t * 2\nconst = 5")
    panel.create_series()
    ts = ws.get("series")
    assert isinstance(ts, TimeSeries) and len(ts) == 10
    assert ts["flux"][1] == pytest.approx(2 * 30 / 86400)
    assert list(ts["const"]) == [5] * 10
    f.set_value("mode", panel.MODES[2])
    f.set_value("name", "binned")
    f.set_value("delta", "1 day")
    f.set_value("n", 4)
    f.set_value("data", "x = n")
    panel.create_series()
    assert isinstance(ws.get("binned"), BinnedTimeSeries)
    # from table with numeric JD times
    ws.put("tab", Table({"jd": [2458849.5, 2458850.5, 2458851.5], "v": [1.0, 2.0, 3.0]}))
    f.set_value("mode", panel.MODES[0])
    f.set_value("name", "fromtab")
    f.set_value("time_col", "jd")
    f.set_value("fmt", "jd")
    panel.table_combo.setCurrentText("tab")
    panel.create_series()
    t = ws.get("fromtab")
    assert t.time[0].isot.startswith("2020-01-01") and list(t["v"]) == [1, 2, 3]
    f.set_value("time_col", "missing")
    with pytest.raises(ParseError):
        panel.create_series()
    f.set_value("mode", panel.MODES[3])
    f.set_value("path", str(tmp_path / "nope.ecsv"))
    with pytest.raises(ParseError):
        panel.create_series()


def test_edit_panel_roundtrip(qtbot, ws, tmp_path, monkeypatch):
    ws.put("lc", tt.make_synthetic("sinusoid", 40, 4, seed=1))
    panel = make_panel(qtbot, ws, tt.EditPanel)
    panel.form.set_value("newcol", "norm")
    panel.form.set_value("expr", "flux / np.nanmedian(flux)")
    panel.add_column()
    assert "norm" in ws.get("lc").colnames
    panel.form.set_value("newcol", "norm")
    with pytest.raises(ParseError):
        panel.add_column()
    panel.form.set_value("dropcols", "norm")
    panel.drop()
    assert "norm" not in ws.get("lc").colnames
    panel.form.set_value("dropcols", "time")
    with pytest.raises(ParseError):
        panel.drop()
    panel.form.set_value("t_from", "2020-01-02T00:00:00")
    panel.form.set_value("out", "sliced")
    panel.slice_time()
    assert 0 < len(ws.get("sliced")) < 40
    panel.form.set_value("t_from", "2021-01-01")
    with pytest.raises(ParseError):
        panel.slice_time()
    panel.plot()
    path = tmp_path / "x.ecsv"
    monkeypatch.setattr(panel, "ask_save_path", lambda *a, **k: str(path))
    panel.save()
    back = TimeSeries.read(str(path), format="ascii.ecsv", time_column="time")
    assert len(back) == 40


def test_synthetic_panel(qtbot, ws):
    panel = make_panel(qtbot, ws, tt.SynthPanel if hasattr(tt, "SynthPanel") else tt.SyntheticPanel)
    panel.generate()
    assert len(ws.get("synthetic")) == 1000


def _write_kepler(path):
    import warnings
    from astropy.io import fits
    t = 1000.0 + np.arange(10) * 0.0204
    cols = [fits.Column(name="TIME", format="D", array=t),
            fits.Column(name="SAP_FLUX", format="E", array=np.ones(10)),
            fits.Column(name="SAP_FLUX_ERR", format="E", array=np.full(10, 0.1))]
    hdu = fits.BinTableHDU.from_columns(cols)
    hdu.header.update({"EXTVER": 1, "EXTNAME": "LIGHTCURVE", "TIMEREF": "SOLARSYSTEM",
                       "TIMESYS": "TDB", "BJDREFI": 2454833, "BJDREFF": 0.0, "TIMEUNIT": "d",
                       "TSTART": t[0], "TSTOP": t[-1], "TIMEDEL": 0.0204})
    primary = fits.PrimaryHDU()
    primary.header["TELESCOP"] = "KEPLER"
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        fits.HDUList([primary, hdu]).writeto(path, overwrite=True)


def test_read_kepler_and_ecsv_files(qtbot, ws, tmp_path):
    panel = make_panel(qtbot, ws, tt.CreatePanel)
    f = panel.form
    f.set_value("mode", panel.MODES[3])
    kfile = str(tmp_path / "k.fits")
    _write_kepler(kfile)
    f.set_value("path", kfile)
    f.set_value("fileformat", "kepler.fits")
    f.set_value("name", "kepler")
    panel.create_series()
    ts = ws.get("kepler")
    assert ts.colnames == ["time", "sap_flux", "sap_flux_err"] and len(ts) == 10
    # round trip through ECSV
    efile = str(tmp_path / "s.ecsv")
    ts.write(efile, format="ascii.ecsv")
    f.set_value("path", efile)
    f.set_value("fileformat", "ascii.ecsv")
    f.set_value("name", "from_ecsv")
    panel.create_series()
    assert len(ws.get("from_ecsv")) == 10
    # the other panels see the new series
    lomb = make_panel(qtbot, ws, tt.LombScarglePanel)
    assert lomb.ycombo.column() == "sap_flux" and lomb.ecombo.column() == "sap_flux_err"


def test_background_threads_end_to_end(qtbot, ws):
    """Same flow with the real thread pool: callbacks must arrive on the GUI thread."""
    from astrotools_adv.core import tasks
    tasks.set_synchronous(False)
    ws.put("lc", tt.make_synthetic("sinusoid", 300, 40, irregular=True, period=3.7, seed=9))
    panel = make_panel(qtbot, ws, tt.LombScarglePanel)
    panel.compute()
    qtbot.waitUntil(lambda: "periodogram" in ws, timeout=20000)
    qtbot.waitUntil(lambda: panel._busy == 0, timeout=20000)
    assert panel._last[1]["best_period"] == pytest.approx(3.7, abs=0.15)
