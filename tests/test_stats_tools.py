import numpy as np
import pytest
from astropy import stats as ast
from astropy import units as u
from astropy.io import fits
from astropy.nddata import NDData
from astropy.table import MaskedColumn, QTable, Table

from astrotools_adv.core.parsing import ParseError
from astrotools_adv.modules import stats_tools as st


@pytest.fixture(autouse=True)
def _no_dialogs(monkeypatch):
    def boom(parent, exc, detail=""):
        raise AssertionError(f"unexpected error dialog: {exc!r}")
    monkeypatch.setattr("astrotools_adv.core.widgets.error_box", boom)


@pytest.fixture
def seen(monkeypatch):
    errors = []
    monkeypatch.setattr("astrotools_adv.core.widgets.error_box",
                        lambda parent, exc, detail="": errors.append(exc))
    return errors


def normal(n=500, seed=0, loc=0.0, scale=1.0):
    return np.random.default_rng(seed).normal(loc, scale, n)


# ---- DataInput ------------------------------------------------------------- #
def test_data_input_modes(qtbot, ws):
    d = st.DataInput(ws)
    qtbot.addWidget(d)
    d.set_text("1, 2, 3\n4 5")
    assert list(d.array()) == [1, 2, 3, 4, 5]
    d.set_text("linspace(0, 1, 5) * u.m")
    assert isinstance(d.quantity(), u.Quantity) and d.array().size == 5
    d.set_text("")
    with pytest.raises(ParseError):
        d.array()
    d.set_text("not python !")
    with pytest.raises(ParseError):
        d.array()
    t = Table({"a": [1.0, 2.0, 3.0], "s": ["x", "y", "z"]})
    t["m"] = MaskedColumn([1.0, 2.0, 3.0], mask=[False, True, False], unit="m")
    ws.put("t", t)
    d.use_table("t", "a")
    assert list(d.array()) == [1, 2, 3]
    d.use_table("t", "m")
    assert np.isnan(d.array()[1]) and d.quantity().unit == u.m
    d.use_table("t", "s")
    with pytest.raises(ParseError):
        d.array()
    opt = st.DataInput(ws, optional=True)
    qtbot.addWidget(opt)
    assert opt.array() is None


def test_data_input_multi_and_image(qtbot, ws):
    d = st.DataInput(ws, multi=True, allow_image=True)
    qtbot.addWidget(d)
    d.set_text("1 2 3\n2 4 7")
    assert d.array().shape == (2, 3)
    d.set_text("1 2 3\n2 4")
    with pytest.raises(ParseError):
        d.array()
    ws.put("t", Table({"a": [1.0, 2, 3], "b": [3.0, 2, 1]}))
    d.use_table("t", "a", "b")
    assert d.array().shape == (2, 3)
    ws.put("img", NDData(np.arange(12.0).reshape(3, 4)))
    ws.put("hdul", fits.HDUList([fits.PrimaryHDU(), fits.ImageHDU(np.ones((2, 2)))]))
    d.mode.setCurrentText(st.MODE_IMAGE)
    d.image_box.setCurrentText("img")
    assert d.array().shape == (3, 4)
    d.image_box.setCurrentText("hdul")
    assert d.array().shape == (2, 2)
    with pytest.raises(ParseError):
        st.image_from_object(fits.HDUList([fits.PrimaryHDU()]))
    q = st.column_values(QTable({"v": [1.0, 2.0] * u.km})["v"])
    assert q.unit == u.km


def test_need_finite_and_fmt():
    assert list(st.need_finite(np.array([1, np.nan, 2, np.inf]), 2)) == [1, 2]
    with pytest.raises(ParseError):
        st.need_finite(np.array([np.nan]), 1)
    assert st.fmt(1.5) == "1.5"


# ---- sigma clipping ---------------------------------------------------------- #
def test_sigma_clipped_stats_removes_injected_outlier():
    d = normal(1000, seed=1)
    d[10] = 500.0
    r = st.compute_sigma_clip(d, 3, 3, 5, "median", "std", False, None)
    assert r["mask"][10] and r["n_clipped"] >= 1
    assert abs(r["mean"]) < 0.1 and r["std"] == pytest.approx(1.0, abs=0.1)
    assert r["raw_std"] > 10  # unclipped std is dominated by the outlier
    exp = ast.sigma_clipped_stats(d, sigma=3, maxiters=5)
    assert (r["mean"], r["median"], r["std"]) == pytest.approx(exp)


def test_sigma_clip_options_and_edge_cases():
    d = normal(300, seed=2)
    tight = st.compute_sigma_clip(d, 1.0, 1.0, 5, "mean", "mad_std", False, None)
    loose = st.compute_sigma_clip(d, 5.0, 5.0, 5, "mean", "mad_std", False, None)
    assert tight["n_clipped"] > loose["n_clipped"]
    asym = st.compute_sigma_clip(d, 100.0, 1.0, None, "median", "std", False, None)
    assert asym["mask"][d > np.median(d)].sum() == 0 or asym["upper"] > asym["lower"]
    img = np.zeros((20, 20)) + normal(400, seed=3).reshape(20, 20) * 0.01
    img[5, 5] = 100
    g = st.compute_sigma_clip(img, 3, 3, 5, "median", "std", 1.0, None)
    assert g["mask"][5, 5] and g["mask"].sum() > 1  # grow clips neighbours
    ax = st.compute_sigma_clip(img, 3, 3, 5, "median", "std", False, 0)
    assert np.shape(ax["mean"]) == (20,)
    for bad in (dict(data=np.full(5, np.nan)), dict(data=d, sigma_lower=0.0)):
        args = dict(data=d, sigma_lower=3.0, sigma_upper=3.0)
        args.update(bad)
        with pytest.raises(ParseError):
            st.compute_sigma_clip(args["data"], args["sigma_lower"], args["sigma_upper"], 5,
                                  "median", "std", False, None)
    with pytest.raises(ParseError):
        st.compute_sigma_clip(d, 3, 3, 5, "median", "std", False, 3)
    const = st.compute_sigma_clip(np.full(10, 2.0), 3, 3, 5, "median", "std", False, None)
    assert const["std"] == 0 and const["n_clipped"] == 0
    one = st.compute_sigma_clip(np.array([5.0]), 3, 3, 5, "median", "std", False, None)
    assert one["mean"] == 5.0
    nan_mix = st.compute_sigma_clip(np.r_[d, np.nan], 3, 3, 5, "median", "std", False, None)
    assert nan_mix["n_nonfinite"] == 1 and nan_mix["mask"][-1] == False  # noqa: E712


def test_sigma_clip_panel(qtbot, ws):
    p = st.SigmaClipPanel(ws)
    qtbot.addWidget(p)
    d = normal(400, seed=4)
    d[7] = 99
    p.data_in.set_text(" ".join(map(str, d)))
    p.compute()
    assert "clipped" in p.out.toPlainText() and p._result["mask"][7]
    p.store()
    assert ws.get("sigma_clip_result")["clipped"][7]
    ws.put("img", np.random.default_rng(0).normal(size=(10, 10)))
    p.data_in.mode.setCurrentText(st.MODE_IMAGE)
    p.data_in.image_box.setCurrentText("img")
    p.compute()
    p.form.set_value("axis", "0")
    p.compute()


def test_sigma_clip_panel_errors(qtbot, ws, seen):
    p = st.SigmaClipPanel(ws)
    qtbot.addWidget(p)
    p.compute()  # no data
    p.data_in.set_text("1 2 3 4 nan")
    p.form.set_value("axis", "x")
    p.compute()
    p.store.__call__()  # nothing computed yet
    assert len(seen) == 3 and all(isinstance(e, ParseError) for e in seen)


# ---- robust statistics --------------------------------------------------------- #
def test_biweight_symmetric_and_outlier_resistant():
    d = np.r_[np.linspace(-5, 5, 101)]
    r = st.compute_robust(d, 6.0, 9.0, None, False, None)
    assert r["biweight_location"] == pytest.approx(0.0, abs=1e-12)
    assert r["biweight_scale"] == pytest.approx(ast.biweight_scale(d))
    dirty = np.r_[normal(300, seed=5), 1e4]
    rd = st.compute_robust(dirty, 6.0, 9.0, None, False, None)
    assert abs(rd["biweight_location"]) < 0.2 and rd["mean"] > 20
    assert rd["mad_std"] == pytest.approx(ast.mad_std(dirty))
    assert rd["mad"] == pytest.approx(ast.median_absolute_deviation(dirty))


def test_biweight_matrix_and_edge_cases():
    rng = np.random.default_rng(6)
    a = rng.normal(size=200)
    mat = np.vstack([a, 2 * a + rng.normal(scale=0.1, size=200), rng.normal(size=200)])
    r = st.compute_robust(a, 6.0, 9.0, None, True, mat)
    assert r["midcov"].shape == (3, 3) and r["midcorr"] > 0.99
    assert r["midcov"][0, 1] == pytest.approx(ast.biweight_midcovariance(mat, modify_sample_size=True)[0, 1])
    with pytest.raises(ParseError):
        st.compute_robust(a, 6.0, 9.0, None, False, mat[:1])
    with pytest.raises(ParseError):
        st.compute_robust(a, 6.0, 9.0, None, False, np.where(mat > 3, np.nan, mat) + np.nan)
    with pytest.raises(ParseError):
        st.compute_robust(np.array([np.nan, np.inf]), 6.0, 9.0, None, False, None)
    single = st.compute_robust(np.array([3.0]), 6.0, 9.0, None, False, None)
    assert single["biweight_location"] == 3.0
    const = st.compute_robust(np.full(10, 2.0), 6.0, 9.0, None, False, None)
    assert const["biweight_location"] == 2.0 and const["biweight_scale"] == 0.0
    withnan = st.compute_robust(np.r_[a, np.nan], 6.0, 9.0, None, False, None)
    assert np.isfinite(withnan["biweight_location"])


def test_robust_panel(qtbot, ws):
    p = st.RobustPanel(ws)
    qtbot.addWidget(p)
    p.data_in.set_text("linspace(-5, 5, 101)")
    p.matrix_in.set_text("1 2 3 4 5 6\n2 4 6 8 10 13")
    p.compute()
    assert "biweight_location" in p.out.toPlainText() and "midcorrelation" in p.out.toPlainText()
    p.form.set_value("M", "0.5")
    p.compute()


# ---- resampling ---------------------------------------------------------------- #
def test_bootstrap_jackknife_match_theory():
    d = normal(400, seed=7, loc=10.0, scale=2.0)
    r = st.compute_resampling(d, np.mean, 800, 42, 0.95)
    se = 2.0 / np.sqrt(400)
    assert r["boot_std"] == pytest.approx(se, rel=0.2)
    assert r["stderr"] == pytest.approx(d.std(ddof=1) / np.sqrt(400), rel=0.01)  # jackknife SE of the mean
    assert r["bias"] == pytest.approx(0.0, abs=1e-10)
    lo, hi = r["boot_ci"]
    assert lo < d.mean() < hi and r["jack_shape"] == (400, 399)
    r2 = st.compute_resampling(d, np.mean, 800, 42, 0.95)
    assert np.array_equal(r["boot"], r2["boot"])  # seed reproducible
    custom = st.make_statistic("custom", "np.percentile(x, 90)")
    r3 = st.compute_resampling(d, custom, 100, 1, 0.9)
    assert r3["value"] == pytest.approx(np.percentile(d, 90))


def test_resampling_errors():
    with pytest.raises(ParseError):
        st.compute_resampling(np.array([1.0]), np.mean, 10, 1, 0.95)
    with pytest.raises(ParseError):
        st.compute_resampling(normal(10), np.mean, 10, 1, 1.5)
    with pytest.raises(ParseError):
        st.compute_resampling(normal(10), np.mean, 0, 1, 0.95)
    with pytest.raises(ParseError):
        st.make_statistic("custom", "")
    with pytest.raises(ParseError):
        st.make_statistic("custom", "foo(x)")


def test_resampling_panel(qtbot, ws):
    p = st.ResamplingPanel(ws)
    qtbot.addWidget(p)
    p.data_in.set_text(" ".join(map(str, normal(60, seed=8))))
    p.form.set_value("n", 50)
    p.form.set_value("seed", "3")
    for name in list(st.STATISTICS) + ["custom"]:
        p.form.set_value("stat", name)
        p.compute()
        assert "Jackknife" in p.out.toPlainText(), name


# ---- intervals ----------------------------------------------------------------- #
def test_binomial_known_values():
    t = st.compute_binomial(np.array([5.0]), np.array([10.0]), 0.95, "wilson")
    assert t["wilson_lower"][0] == pytest.approx(0.2366, abs=2e-4)
    assert t["wilson_upper"][0] == pytest.approx(0.7634, abs=2e-4)
    t = st.compute_binomial(np.array([0.0]), np.array([10.0]), 0.95, "jeffreys")
    assert t["jeffreys_lower"][0] == 0.0
    from scipy.stats import beta
    t = st.compute_binomial(np.array([3.0]), np.array([10.0]), 0.9, "jeffreys")
    assert t["jeffreys_lower"][0] == pytest.approx(beta.ppf(0.05, 3.5, 7.5), abs=1e-9)
    assert t["jeffreys_upper"][0] == pytest.approx(beta.ppf(0.95, 3.5, 7.5), abs=1e-9)
    allm = st.compute_binomial(np.array([2.0, 7.0]), np.array([10.0]), 0.68269, "all")
    assert len(allm) == 2 and all(f"{m}_lower" in allm.colnames for m in st.INTERVALS)
    wald = st.compute_binomial(np.array([50.0]), np.array([100.0]), 0.68269, "wald")
    assert wald["wald_upper"][0] - 0.5 == pytest.approx(np.sqrt(0.25 / 100), rel=2e-3)


@pytest.mark.parametrize("k,n,conf", [([5], [3], 0.9), ([-1], [3], 0.9), ([1], [0], 0.9),
                                      ([1, 2], [3, 4, 5], 0.9), ([1], [3], 1.2), ([np.nan], [3], 0.5)])
def test_binomial_errors(k, n, conf):
    with pytest.raises(ParseError):
        st.compute_binomial(np.array(k, float), np.array(n, float), conf, "wilson")


def test_poisson_intervals():
    t = st.compute_poisson(np.array([0.0, 4.0, 100.0]), "root-n", 1.0, 0.0, None)
    assert t["upper"][1] == pytest.approx(6.0) and t["lower"][1] == pytest.approx(2.0)
    f = st.compute_poisson(np.array([0.0, 1.0, 5.0]), "frequentist-confidence", 1.0, 0.0, None)
    assert f["lower"][0] == 0.0 and f["upper"][0] == pytest.approx(1.84, abs=0.05)  # Gehrels 1986
    kbn = st.compute_poisson(np.array([3.0]), "kraft-burrows-nousek", 1.0, 0.5, 0.9)
    assert kbn["lower"][0] == pytest.approx(0.443, abs=0.01) and kbn["upper"][0] > kbn["lower"][0]
    for interval in ("root-n-0", "pearson", "sherpagehrels"):
        assert len(st.compute_poisson(np.array([1.0, 9.0]), interval, 1.0, 0.0, None)) == 2
    for args in ((np.array([-1.0]), "root-n", 1.0, 0.0, None),
                 (np.array([1.0, 2.0]), "kraft-burrows-nousek", 1.0, 0.5, 0.9),
                 (np.array([1.0]), "kraft-burrows-nousek", 1.0, 0.5, None),
                 (np.array([1.0]), "root-n", 1.0, 0.5, None),
                 (np.array([1.0]), "root-n", 1.0, 0.0, 0.9),
                 (np.array([np.nan]), "root-n", 1.0, 0.0, None)):
        with pytest.raises(ParseError):
            st.compute_poisson(*args)


def test_binned_binomial():
    rng = np.random.default_rng(9)
    x = rng.uniform(0, 1, 5000)
    ok = rng.uniform(size=5000) < x  # success probability = x
    t = st.compute_binned_binomial(x, ok.astype(float), 5, (0, 1), 0.68269, "wilson")
    assert len(t) == 5
    assert np.allclose(t["fraction"], t["bin_center"], atol=0.06)
    assert (t["err_lower"] >= 0).all() and (t["err_upper"] >= 0).all()
    with pytest.raises(ParseError):
        st.compute_binned_binomial(x, ok[:-1].astype(float), 5, None, 0.68, "wilson")
    with pytest.raises(ParseError):
        st.compute_binned_binomial(np.array([np.nan]), np.array([1.0]), 5, None, 0.68, "wilson")


def test_interval_panels(qtbot, ws, seen):
    b = st.BinomialPanel(ws)
    qtbot.addWidget(b)
    b.compute()
    assert len(ws.get("binomial_intervals")) == 3 and b.table.model.rowCount() == 3
    b.form.set_value("method", "wald")
    b.compute()
    b.form.set_value("k", "11")
    b.compute()  # k > n
    pz = st.PoissonPanel(ws)
    qtbot.addWidget(pz)
    pz.compute()
    assert pz.table.model.rowCount() == 5
    pz.form.set_value("interval", "kraft-burrows-nousek")
    pz.compute()  # needs confidence level -> error
    pz.form.set_value("conf", "0.9")
    pz.form.set_value("bkg", 0.5)
    pz.form.set_value("n", "3")
    pz.compute()
    assert pz.table.model.rowCount() == 1
    bb = st.BinnedBinomialPanel(ws)
    qtbot.addWidget(bb)
    bb.x_in.set_text("0.1 0.2 0.3 0.6 0.7 0.9")
    bb.s_in.set_text("0 0 1 0 1 1")
    bb.form.set_value("bins", "3")
    bb.compute()
    assert bb.table.model.rowCount() == 3
    bb.form.set_value("bins", "0, 0.5, 1")
    bb.compute()
    assert bb.table.model.rowCount() == 2
    bb.form.set_value("bins", "2.5")
    bb.compute()  # invalid
    assert [type(e) for e in seen] == [ParseError] * 3


# ---- histograms and blocks ------------------------------------------------------ #
def test_histogram_methods():
    d = normal(2000, seed=10)
    for method in ("knuth", "scott", "freedman", "blocks"):
        r = st.compute_histogram(d, method, 10, None, None)
        assert r["counts"].sum() == 2000 and len(r["edges"]) == len(r["counts"]) + 1
    k = st.compute_histogram(d, "scott", 10, None, None)
    assert k["width"] == pytest.approx(ast.scott_bin_width(d))
    assert st.compute_histogram(d, "number", 7, None, None)["counts"].size == 7
    e = st.compute_histogram(d, "edges", 0, np.array([-10.0, 0.0, 10.0]), None)
    assert e["counts"].sum() == 2000 and e["counts"].size == 2
    r = st.compute_histogram(d, "number", 5, None, (-1.0, 1.0))
    assert r["edges"][0] == -1.0 and r["edges"][-1] == 1.0
    for bad in (("knuth", np.full(10, 3.0)), ("number", np.array([1.0]))):
        with pytest.raises(ParseError):
            st.compute_histogram(bad[1], bad[0], 5, None, None)
    with pytest.raises(ParseError):
        st.compute_histogram(d, "edges", 0, np.array([2.0, 1.0]), None)
    with pytest.raises(ParseError):
        st.compute_histogram(d, "number", 0, None, None)


def test_bayesian_blocks_events_use_counts():
    t = np.arange(100.0)
    counts = np.r_[np.full(40, 1.0), np.full(30, 6.0), np.full(30, 1.0)]
    r = st.compute_blocks(t, counts, None, "events", 0.05, None, None)
    assert list(r["edges"]) == pytest.approx([0.0, 39.5, 69.5, 99.0])
    with pytest.raises(ParseError):  # non-integer counts are rejected with a readable message
        st.compute_blocks(t, counts * 0.5, None, "events", 0.05, None, None)


def test_circular_mean_wraps_noise_to_zero():
    r = st.compute_circular(np.array([350.0, 355.0, 5.0, 10.0]), u.deg, None, 0.0, 1.0, None)
    assert r["circmean"] == 0.0
    h = st.compute_circular(np.array([23.0, 23.5, 0.5, 1.0]), u.hourangle, None, 0.0, 1.0, None)
    assert h["circmean"] == 0.0


def test_bayesian_blocks_finds_step():
    rng = np.random.default_rng(11)
    t = np.sort(np.r_[rng.uniform(0, 5, 100), rng.uniform(5, 10, 600)])
    r = st.compute_blocks(t, None, None, "events", 0.01, None, None)
    inner = r["edges"][1:-1]
    assert (np.abs(inner - 5.0) < 0.3).any()
    # measures: a clean step in noisy-free data
    tt = np.arange(50.0)
    x = np.r_[np.zeros(25), np.ones(25)]
    m = st.compute_blocks(tt, x, 0.1, "measures", 0.05, None, None)
    assert len(m["edges"]) == 3 and m["edges"][1] == pytest.approx(24.5)
    g = st.compute_blocks(tt, x, 0.1, "measures", 0.05, 0.01, None)
    assert len(g["edges"]) >= 3
    reg = st.compute_blocks(tt, x, None, "regular_events", 0.05, None, None, dt=1.0)
    assert len(reg["edges"]) >= 2
    for args in (dict(t=np.array([1.0]), x=None, sigma=None, fitness="events"),
                 dict(t=tt, x=None, sigma=None, fitness="measures"),
                 dict(t=tt, x=x[:5], sigma=0.1, fitness="measures"),
                 dict(t=np.full(5, 2.0), x=None, sigma=None, fitness="events"),
                 dict(t=np.array([1.0, np.nan]), x=None, sigma=None, fitness="events"),
                 dict(t=tt, x=x, sigma=None, fitness="regular_events")):
        with pytest.raises(ParseError):
            st.compute_blocks(args["t"], args["x"], args["sigma"], args["fitness"], 0.05, None, None)


def test_histogram_and_blocks_panels(qtbot, ws):
    h = st.HistogramPanel(ws)
    qtbot.addWidget(h)
    h.data_in.set_text(" ".join(map(str, normal(300, seed=12))))
    for method in ("knuth", "scott", "freedman", "blocks", "number"):
        h.form.set_value("method", method)
        h.compute()
        assert h.table.model.rowCount() >= 1, method
    h.form.set_value("method", "edges")
    h.form.set_value("edges", "-5, 0, 5")
    h.compute()
    assert h.table.model.rowCount() == 2
    b = st.BayesianBlocksPanel(ws)
    qtbot.addWidget(b)
    b.t_in.set_text("linspace(0, 50, 50)")
    b.x_in.set_text("array([0]*25 + [1]*25)")
    b.s_in.set_text("0.1")
    b.form.set_value("fitness", "measures")
    b.compute()
    assert "block" in b.out.toPlainText()
    b.form.set_value("fitness", "events")
    b.compute()


# ---- circular ------------------------------------------------------------------ #
def test_circular_statistics_values():
    r = st.compute_circular(np.array([350.0, 10.0]), u.deg, None, 0.0, 1.0, None)
    assert r["circmean"] % 360 == pytest.approx(0.0, abs=1e-9) or r["circmean"] == pytest.approx(360.0)
    assert r["R"] == pytest.approx(np.cos(np.deg2rad(10)))
    assert r["circvar"] == pytest.approx(1 - np.cos(np.deg2rad(10)))
    assert r["vonmises_kappa"] > 10
    r = st.compute_circular(np.array([90.0, 100.0, 80.0, 95.0, 85.0]), u.deg, None, 90.0, 1.0, None)
    assert r["circmean"] == pytest.approx(90.0, abs=1.0)
    assert r["rayleigh_p"] < 0.05 and r["vtest_p"] < 0.05
    uni = st.compute_circular(np.linspace(0, 360, 360, endpoint=False), u.deg, None, 0.0, 1.0, None)
    assert uni["R"] < 1e-9 and uni["rayleigh_p"] > 0.9
    h = st.compute_circular(np.array([23.0, 1.0]), u.hourangle, None, 0.0, 1.0, None)
    assert h["circmean"] == pytest.approx(0.0, abs=1e-9) or h["circmean"] == pytest.approx(24.0)
    a = np.linspace(0, 6, 50)
    c = st.compute_circular(a, u.rad, np.ones(50), 0.0, 2.0, a + 0.3)
    assert c["circcorrcoef"] == pytest.approx(1.0, abs=1e-6)
    assert st.compute_circular(a, u.rad, None, 0.0, 1.0, np.sin(a))["circcorrcoef"] < 1
    for args in ((np.array([np.nan]), None, None), (np.array([]), None, None),
                 (np.array([1.0, 2.0]), np.array([1.0]), None), (np.array([1.0, 2.0]), np.array([-1.0, 1.0]), None),
                 (np.array([1.0, 2.0]), np.array([0.0, 0.0]), None), (np.array([1.0, 2.0]), None, np.array([1.0]))):
        with pytest.raises(ParseError):
            st.compute_circular(args[0], u.rad, args[1], 0.0, 1.0, args[2])


def test_kuiper_and_panels(qtbot, ws, seen):
    rng = np.random.default_rng(13)
    uni = st.compute_kuiper(rng.uniform(size=300), None, 1.0)
    assert uni["fpp"] > 0.01
    clustered = st.compute_kuiper(rng.normal(0.5, 0.05, 300) % 1, None, 1.0)
    assert clustered["fpp"] < 1e-6
    two = st.compute_kuiper(rng.uniform(size=100), rng.uniform(size=120), 1.0)
    assert two["two"] and 0 <= two["fpp"] <= 1
    folded = st.compute_kuiper(np.arange(100) * 2.0, None, 2.0)  # all phase 0
    assert folded["fpp"] < 1e-6
    with pytest.raises(ParseError):
        st.compute_kuiper(np.array([0.1]), None, 1.0)
    with pytest.raises(ParseError):
        st.compute_kuiper(np.array([0.1, 0.2]), None, 0.0)
    k = st.KuiperPanel(ws)
    qtbot.addWidget(k)
    k.a_in.set_text("0.1 0.2 0.3 0.4 0.9")
    k.compute()
    assert "false-positive" in k.out.toPlainText()
    c = st.CircularPanel(ws)
    qtbot.addWidget(c)
    c.a_in.set_text("350 10 5 355")
    c.compute()
    assert "circular mean" in c.out.toPlainText() and c.canvas.figure.axes
    c.b_in.set_text("1 2 3")
    c.compute()  # length mismatch
    assert len(seen) == 1 and isinstance(seen[0], ParseError)


# ---- information criteria, S/N, widths, Ripley ------------------------------------- #
def test_information_criteria_values():
    r = st.compute_info_criteria("ll", -50.0, 3, 100)
    assert r["A"][0] == pytest.approx(ast.akaike_info_criterion(-50.0, 3, 100))
    assert r["A"][1] == pytest.approx(3 * np.log(100) + 100.0)
    cmp = st.compute_info_criteria("lsq", 10.0, 2, 50, 12.0, 3)
    assert cmp["delta_aic"] == pytest.approx(cmp["B"][0] - cmp["A"][0])
    assert cmp["relative_likelihood"] == pytest.approx(np.exp(cmp["delta_aic"] / 2))
    assert cmp["A"][1] == pytest.approx(ast.bayesian_info_criterion_lsq(10.0, 2, 50))
    for args in (("ll", np.nan, 3, 100), ("ll", -5.0, 0, 100), ("lsq", -1.0, 2, 50), ("lsq", 0.0, 2, 50),
                 ("ll", -5.0, 3, 0)):
        with pytest.raises(ParseError):
            st.compute_info_criteria(*args)


def test_snr_calculation():
    t = st.compute_snr(np.array([100.0]), 10.0, 1.0, 0.1, 5.0, 20.0, 1.0)
    expected = 10 * 100 / np.sqrt(10 * 100 + 20 * (1 * 100 + 0.1 * 100 + 25))
    assert t["snr"][0] == pytest.approx(expected)
    curve = st.compute_snr(np.linspace(1, 1000, 10), 10.0, 0.0, 0.0, 0.0, 1.0, 1.0)
    assert curve["snr"][-1] == pytest.approx(np.sqrt(10 * 1000))  # source-limited: sqrt(N)
    for args in ((np.array([0.0]), 1, 1, 1, 1, 1, 1), (np.array([1.0]), -1, 1, 1, 1, 1, 1),
                 (np.array([1.0]), 1, 1, 1, 1, 0, 1), (np.array([1.0]), 1, 1, 1, 1, 1, 0),
                 (np.array([np.nan]), 1, 1, 1, 1, 1, 1)):
        with pytest.raises(ParseError):
            st.compute_snr(*args)


def test_small_calculator_panels(qtbot, ws):
    ic = st.InfoCriteriaPanel(ws)
    qtbot.addWidget(ic)
    ic.compute()
    assert "AIC" in ic.out.toPlainText()
    ic.form.set_value("cmp", True)
    ic.compute()
    assert "Model B" in ic.out.toPlainText()
    snr = st.SnrPanel(ws)
    qtbot.addWidget(snr)
    snr.compute()
    assert snr.table.model.rowCount() == 60
    gw = st.GaussianWidthPanel(ws)
    qtbot.addWidget(gw)
    gw.form.set_value("v", "2.3548200450309493")
    gw.compute()
    assert "sigma = 1" in gw.out.toPlainText()
    gw.form.set_value("dir", "sigma -> FWHM")
    gw.form.set_value("v", "1")
    gw.compute()
    assert "FWHM = 2.35482" in gw.out.toPlainText()


def test_ripley_k_poisson_vs_clustered():
    rng = np.random.default_rng(14)
    x, y = rng.uniform(size=400), rng.uniform(size=400)
    radii = np.linspace(0.01, 0.1, 10)
    r = st.compute_ripley(x, y, (0, 1, 0, 1), radii, "translation")
    assert np.allclose(r["K"], np.pi * radii ** 2, rtol=0.35)
    assert np.allclose(r["poisson"], np.pi * radii ** 2)
    cx = np.r_[rng.normal(0.3, 0.02, 200), rng.normal(0.7, 0.02, 200)]
    cy = np.r_[rng.normal(0.3, 0.02, 200), rng.normal(0.7, 0.02, 200)]
    c = st.compute_ripley(cx, cy, (0, 1, 0, 1), radii, "none")
    assert (c["K"] > 3 * np.pi * radii ** 2).all()
    auto = st.compute_ripley(x, y, None, radii, "ripley")
    assert auto["n"] == 400
    for args in ((x[:2], y[:2], None, radii, "none"), (x, y[:-1], None, radii, "none"),
                 (x, y, (0, 0, 0, 1), radii, "none"), (x, y, (5, 6, 5, 6), radii, "none"),
                 (x, y, None, np.array([-1.0]), "none"), (x, y, None, np.array([]), "none"),
                 (np.full(10, np.nan), np.full(10, np.nan), None, radii, "none")):
        with pytest.raises(ParseError):
            st.compute_ripley(*args)


def test_ripley_panel(qtbot, ws, seen):
    p = st.RipleyPanel(ws)
    qtbot.addWidget(p)
    rng = np.random.default_rng(15)
    p.x_in.set_text(" ".join(map(str, rng.uniform(size=60))))
    p.y_in.set_text(" ".join(map(str, rng.uniform(size=60))))
    p.r_in.set_text("linspace(0.02, 0.2, 8)")
    for mode in st.RIPLEY_MODES:
        p.form.set_value("mode", mode)
        p.compute()
        assert "points" in p.out.toPlainText(), mode
    p.form.set_value("region", "0, 1, 0")
    p.compute()
    assert len(seen) == 1


def test_all_specs_open(qtbot, ws):
    assert {s.category for s in st.SPECS} == {"Analysis"}
    assert len({s.key for s in st.SPECS}) == len(st.SPECS)
    for spec in st.SPECS:
        w = spec.factory(ws)
        qtbot.addWidget(w)
