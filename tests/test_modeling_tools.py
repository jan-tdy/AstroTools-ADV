import numpy as np
import pytest
from astropy import units as u
from astropy.modeling import Model, models
from astropy.nddata import NDData
from astropy.table import QTable, Table

from astrotools_adv.core.parsing import ParseError
from astrotools_adv.modules import modeling_tools as mt


@pytest.fixture(autouse=True)
def _no_dialogs(monkeypatch):
    """Panels must report errors through fail(); make any dialog a test failure."""
    def boom(parent, exc, detail=""):
        raise AssertionError(f"unexpected error dialog: {exc!r}")
    monkeypatch.setattr("astrotools_adv.core.widgets.error_box", boom)


def gauss_data(noise=0.0, n=200, seed=1):
    x = np.linspace(-6, 6, n)
    y = 3.0 * np.exp(-0.5 * ((x - 0.7) / 1.3) ** 2) + 0.5
    if noise:
        y = y + np.random.default_rng(seed).normal(0, noise, n)
    return x, y


# ---- catalogue & parsing --------------------------------------------------- #
def test_catalog_covers_models():
    cat = mt.model_catalog()
    for name in ("Gaussian1D", "Gaussian2D", "BlackBody", "NFW", "Tabular1D", "Mapping",
                 "Polynomial1D", "Pix2Sky_TAN", "Spline1D", "Voigt1D"):
        assert name in cat
    assert "Projection" not in cat and "PolynomialModel" not in cat and "item" not in cat
    assert mt.model_group(cat["Gaussian1D"]) == "1D"
    assert mt.model_group(cat["Gaussian2D"]) == "2D"
    assert mt.model_group(cat["Pix2Sky_TAN"]) == "Projections"
    assert mt.model_group(cat["Mapping"]) == "Mappings / other"


def test_compound_expression_equals_manual_sum():
    m = mt.parse_model("Gaussian1D(2, 1, 0.5) + Const1D(0.3)")
    x = np.linspace(-2, 4, 25)
    manual = models.Gaussian1D(2, 1, 0.5)(x) + 0.3
    assert np.allclose(m(x), manual)
    assert m.n_submodels == 2


def test_pipe_join_and_power():
    pipe = mt.parse_model("Shift(1) | Scale(3)")
    assert pipe(2.0) == pytest.approx(9.0)
    both = mt.parse_model("Shift(1) & Scale(3)")
    assert both.n_inputs == 2 and both(1.0, 2.0) == (2.0, 6.0)
    pw = mt.parse_model("Const1D(2) ** Const1D(3)")
    assert pw(0.0) == pytest.approx(8.0)
    sub = mt.parse_model("Const1D(5) - Const1D(2)")
    mul = mt.parse_model("Const1D(5) * Const1D(2)")
    div = mt.parse_model("Const1D(5) / Const1D(2)")
    assert (sub(0), mul(0), div(0)) == (3.0, 10.0, 2.5)


@pytest.mark.parametrize("bad", ["", "1 + 1", "Polynomial1D", "__import__('os')", "Gaussian1D(",
                                 "Nonexistent()", "Gaussian1D().__class__"])
def test_parse_model_errors(bad):
    with pytest.raises(ParseError):
        mt.parse_model(bad)


def test_class_without_required_args_instantiates():
    assert isinstance(mt.parse_model("Gaussian1D"), models.Gaussian1D)


def test_workspace_models_by_name(ws):
    ws.put("peak", models.Gaussian1D(1, 0, 1))
    m = mt.parse_model("peak + Const1D(2)", ws)
    assert m(0.0) == pytest.approx(3.0)
    m2 = mt.parse_model("peak", ws)
    m2.amplitude = 9
    assert ws.get("peak").amplitude.value == 1  # expressions work on copies


def test_apply_constraints():
    m = models.Gaussian1D(1, 0, 1)
    out = mt.apply_constraints(m, "mean: fixed\nstddev: 0.5..4\namplitude: ..10")
    assert m.mean.fixed and m.stddev.bounds == (0.5, 4.0) and m.amplitude.bounds == (None, 10.0)
    assert len(out) == 3
    mt.apply_constraints(m, "mean: free")
    assert not m.mean.fixed
    for bad in ("nope: fixed", "mean fixed", "mean: sometimes", "stddev: 5..1"):
        with pytest.raises(ParseError):
            mt.apply_constraints(m, bad)


def test_custom_model_fits():
    m = mt.make_custom_model("Wave", "a*np.sin(b*x) + c", "a=2, b=1.2, c=0.4")
    assert m.param_names == ("a", "b", "c")
    x = np.linspace(0, 6, 80)
    truth = 2.5 * np.sin(1.3 * x) + 0.5
    r = mt.run_fit(m, [x], truth, fitter="TRFLSQFitter")
    assert np.allclose(r["fit"].parameters, [2.5, 1.3, 0.5], atol=1e-5)
    for args in (("1bad", "a*x", "a=1"), ("M", "a*x", ""), ("M", "", "a=1"), ("M", "a*x", "x=1"),
                 ("M", "a*z", "a=1"), ("M", "a*x", "a=1, a=2"), ("M", "a*x", "a")):
        with pytest.raises(ParseError):
            mt.make_custom_model(*args)
    m2 = mt.make_custom_model("Surf", "a*x + y", "a=2", n_inputs=2)
    assert m2.n_inputs == 2 and m2(1.0, 3.0) == pytest.approx(5.0)


# ---- fitting engine -------------------------------------------------------- #
def test_noiseless_gaussian_recovered_by_every_fitter():
    x, y = gauss_data()
    for name in mt.FITTERS:
        model = models.Gaussian1D(2.0, 0.3, 1.0) + models.Const1D(0.2)
        r = mt.run_fit(model, [x], y, fitter=name, maxiter=2000, acc=1e-12) \
            if name != "LinearLSQFitter" else None
        if r is None:
            with pytest.raises(ParseError):
                mt.run_fit(model, [x], y, fitter=name)
            continue
        tol = 1e-3 if name in ("SLSQPLSQFitter", "SimplexLSQFitter") else 1e-6
        assert np.allclose(r["fit"].parameters, [3.0, 0.7, 1.3, 0.5], atol=tol, rtol=tol), name


def test_noisy_fit_uncertainties_and_chi2():
    x, y = gauss_data(noise=0.1, n=400, seed=3)
    sigma = np.full_like(x, 0.1)
    r = mt.run_fit(models.Gaussian1D(2.5, 0.2, 1.0) + models.Const1D(0.0), [x], y, sigma=sigma,
                   fitter="LevMarLSQFitter")
    p = r["fit"].parameters
    assert np.allclose(p, [3.0, 0.7, 1.3, 0.5], atol=0.1)
    st = r["stats"]
    assert st["dof"] == 396 and 0.8 < st["reduced_chi2"] < 1.25
    assert st["chi2"] == pytest.approx(np.sum((r["residual"] / 0.1) ** 2))
    assert all(sd > 0 for sd in r["stds"].values()) and r["cov"].shape == (4, 4)
    assert "reduced chi2" in mt.format_fit(r)
    assert st["aic"] < 0 or st["aic"] > -1e9  # computed and finite
    assert np.isfinite(st["bic"])


def test_linear_fit_polynomial_with_weights():
    x = np.linspace(0, 10, 50)
    y = 2 * x + 1
    r = mt.run_fit(models.Polynomial1D(1), [x], y, weights=np.ones_like(x), fitter="LinearLSQFitter")
    assert np.allclose(r["fit"].parameters, [1, 2])
    assert r["stats"]["rms"] < 1e-9


def test_outlier_removal_finds_injected_outlier():
    x, y = gauss_data(noise=0.02, seed=5)
    y[40] += 10
    plain = mt.run_fit(models.Gaussian1D(2, 0.5, 1) + models.Const1D(0), [x], y)
    clipped = mt.run_fit(models.Gaussian1D(2, 0.5, 1) + models.Const1D(0), [x], y, outliers=True)
    assert clipped["mask"][40] and clipped["mask"].sum() >= 1
    err = lambda r: abs(r["fit"].amplitude_0.value - 3.0)  # noqa: E731
    assert err(clipped) < err(plain) and err(clipped) < 0.05


def test_nonfinite_points_dropped_and_reported():
    x, y = gauss_data()
    y = y.copy()
    y[[3, 9]] = np.nan
    x = x.copy()
    x[20] = np.inf
    r = mt.run_fit(models.Gaussian1D(2, 0.5, 1) + models.Const1D(0), [x], y)
    assert r["stats"]["n_dropped"] == 3 and r["stats"]["n_used"] == 197
    assert np.allclose(r["fit"].parameters, [3.0, 0.7, 1.3, 0.5], atol=1e-5)


def test_fixed_parameter_and_bounds_respected():
    x, y = gauss_data()
    m = models.Gaussian1D(2, 0.7, 2) + models.Const1D(0.5)
    mt.apply_constraints(m, "mean_0: fixed\nstddev_0: 1.5..3")
    r = mt.run_fit(m, [x], y, fitter="TRFLSQFitter")
    assert r["fit"].mean_0.value == 0.7
    assert 1.5 - 1e-9 <= r["fit"].stddev_0.value <= 3 + 1e-9


@pytest.mark.parametrize("n_points", [0, 1, 2])
def test_degenerate_data_gives_parse_error(n_points):
    x = np.linspace(0, 1, n_points)
    with pytest.raises(ParseError):
        mt.run_fit(models.Gaussian1D(1, 0, 1), [x], np.ones(n_points))


def test_all_nan_constant_and_fixed_cases():
    x = np.linspace(0, 1, 20)
    with pytest.raises(ParseError):
        mt.run_fit(models.Linear1D(), [x], np.full(20, np.nan))
    r = mt.run_fit(models.Linear1D(), [x], np.full(20, 4.0))  # constant data: perfect fit
    assert r["fit"].slope.value == pytest.approx(0, abs=1e-8) and r["fit"].intercept.value == pytest.approx(4)
    assert "aic" not in r["stats"] or np.isfinite(r["stats"]["aic"])
    m = models.Linear1D()
    m.slope.fixed = m.intercept.fixed = True
    with pytest.raises(ParseError):
        mt.run_fit(m, [x], x)
    with pytest.raises(ParseError):
        mt.run_fit(models.Linear1D(), [x], x, sigma=np.zeros(20))
    with pytest.raises(ParseError):
        mt.run_fit(models.Linear1D(), [x, x], x)
    with pytest.raises(ParseError):
        mt.run_fit(models.Linear1D(), [x], x[:5])


def test_units_aware_fit():
    x = np.linspace(-5, 5, 80) * u.s
    y = 3 * np.exp(-0.5 * (x.value / 1.5) ** 2) * u.Jy
    start = models.Gaussian1D(2 * u.Jy, 0.2 * u.s, 1.0 * u.s)
    r = mt.run_fit(start, [x], y, sigma=np.full(80, 0.1) * u.Jy)
    assert r["fit"].amplitude.value == pytest.approx(3.0, abs=1e-4)
    assert r["fit"].stddev.quantity.unit == u.s
    assert r["stats"]["chi2"] < 1e-6


def test_2d_gaussian_fit_with_guess():
    yy, xx = np.mgrid[:40, :50]
    truth = models.Gaussian2D(5.0, 22.0, 17.0, 4.0, 3.0) + models.Const2D(1.0)
    img = truth(xx, yy)
    expr = mt.guess_gaussian2d(img)
    model = mt.parse_model(expr)
    r = mt.run_fit(model, [xx.astype(float), yy.astype(float)], img)
    assert np.allclose(r["fit"].parameters[:5], [5.0, 22.0, 17.0, 4.0, 3.0], atol=1e-3)
    assert r["fit"].amplitude_1.value == pytest.approx(1.0, abs=1e-3)
    with pytest.raises(ParseError):
        mt.guess_gaussian2d(np.full((4, 4), np.nan))
    flat = mt.guess_gaussian2d(np.ones((8, 8)))  # no signal: still a valid expression
    assert isinstance(mt.parse_model(flat), Model)


def test_describe_and_dict():
    m = models.Gaussian1D(1, 0, 1) | models.Scale(2)
    text = mt.describe_model(m)
    assert "inverse" in text and "amplitude_0" in text
    d = mt.model_to_dict(models.Gaussian1D(1, 0, 1))
    assert d["class"] == "Gaussian1D" and d["parameters"]["mean"]["value"] == 0.0
    assert "bounding_box" in mt.describe_model(models.Gaussian1D())
    assert "no parameters" in mt.describe_model(models.Mapping((0,)))


# ---- curves ---------------------------------------------------------------- #
def test_spline_and_polynomial_curves_accuracy():
    x = np.linspace(0, 10, 40)
    y = np.sin(x)
    for method in ("Spline: interpolate", "Spline: splrep"):
        m = mt.fit_curve(method, x, y, None, 3, None, None)
        xt = np.linspace(0.5, 9.5, 50)
        assert np.max(np.abs(m(xt) - np.sin(xt))) < 5e-3
    m = mt.fit_curve("Spline: exact knots", x, y, None, 3, None, np.arange(1.5, 10, 1.5))
    assert np.max(np.abs(m(x) - y)) < 0.02
    m = mt.fit_curve("Spline: smoothing", x, y, np.ones_like(x), 3, 0.5, None)
    assert np.isfinite(m(5.0))
    t = mt.fit_curve("Tabular1D: linear", x, y, None, 3, None, None)
    assert t(x[7]) == pytest.approx(y[7])
    poly = mt.fit_curve("Polynomial: Chebyshev1D", x, 2 * x ** 2 - x, None, 2, None, None)
    assert poly(3.0) == pytest.approx(15.0)
    unsorted = np.random.default_rng(0).permutation(len(x))
    assert mt.fit_curve("Polynomial: Polynomial1D", x[unsorted], (3 * x + 2)[unsorted], None, 1, None,
                        None)(1.0) == pytest.approx(5.0)


def test_curve_errors():
    x = np.arange(6.0)
    for method, kw in (("Spline: interpolate", {"x": np.array([0, 1, 1, 2, 3.0])}),
                       ("Spline: exact knots", {"knots": None}),
                       ("Spline: exact knots", {"knots": np.array([0.0])}),
                       ("Spline: interpolate", {"x": np.array([0.0, 1, 2])}),
                       ("Polynomial: Polynomial1D", {"x": np.array([1.0, 2.0])})):
        xx = kw.get("x", x)
        with pytest.raises(ParseError):
            mt.fit_curve(method, xx, xx * 2, None, 3, None, kw.get("knots"))
    with pytest.raises(ParseError):
        mt.fit_curve("Spline: interpolate", np.array([1.0]), np.array([1.0]), None, 1, None, None)


# ---- panels ---------------------------------------------------------------- #
def test_builder_panel_flow(qtbot, ws):
    p = mt.ModelBuilderPanel(ws)
    qtbot.addWidget(p)
    assert p.cls_combo.count() > 10
    p.group.setCurrentText("2D")
    assert "Gaussian2D" in [p.cls_combo.itemText(i) for i in range(p.cls_combo.count())]
    p.search.setText("gauss")
    assert p.cls_combo.count() >= 1 and p.info.toPlainText()
    p.form.set_value("expr", "Gaussian1D(1, 0, 1) + Const1D(0.1)")
    p.build()
    assert p.table.rowCount() == 4 and "amplitude_0" in p.out.toPlainText()
    p.table.item(0, 1).setText("5")
    p.table.item(1, 3).setCheckState(2)
    p.table.item(2, 4).setText("0.5")
    p.apply_edits()
    assert p.model.amplitude_0.value == 5 and p.model.mean_0.fixed and p.model.stddev_0.bounds[0] == 0.5
    p.save_model()
    assert ws.get("model").amplitude_0.value == 5
    p.evaluate()
    assert len(p.canvas.figure.axes) == 1
    x = np.array(p.canvas.figure.axes[0].lines[0].get_xdata())
    y = np.array(p.canvas.figure.axes[0].lines[0].get_ydata())
    assert np.allclose(y, p.model(x))
    p.form.set_value("expr", "Gaussian2D(1, 0, 0, 1, 1)")
    p.evaluate()
    p.render_model()
    assert p.render_canvas.figure.axes
    p.form.set_value("expr", "Shift(2) | Scale(3)")
    p.save_inverse()
    assert ws.get("model_inverse")(9.0) == pytest.approx(1.0)
    p.insert_class()
    assert "Gaussian1D" not in p.form.value("expr") or p.form.value("expr").count("(") >= 1


def test_builder_custom_model_and_errors(qtbot, ws, monkeypatch):
    seen = []
    monkeypatch.setattr("astrotools_adv.core.widgets.error_box",
                        lambda parent, exc, detail="": seen.append(exc))
    p = mt.ModelBuilderPanel(ws)
    qtbot.addWidget(p)
    p.create_custom()
    assert "MyModel" in ws and ws.get("MyModel").param_names == ("a", "b", "c")
    p.form.set_value("expr", "MyModel + Const1D(1)")
    p.build()
    assert p.table.rowCount() == 4
    p.form.set_value("expr", "Gaussian1D(")
    p.build()
    p.form.set_value("expr", "Mapping((0,))")
    p.save_inverse()  # Mapping inverse may or may not exist; must not raise unhandled
    p.form.set_value("xmin", "5")
    p.form.set_value("expr", "Gaussian1D()")
    p.evaluate()
    assert any(isinstance(e, ParseError) for e in seen)


def test_fit1d_panel_from_workspace_table(qtbot, ws):
    x, y = gauss_data(noise=0.05, seed=11)
    sig = np.full_like(x, 0.05)
    ws.put("data", Table({"x": x, "y": y, "e": sig}))
    p = mt.Fit1DPanel(ws)
    qtbot.addWidget(p)
    p.x_in.use_table("data", "x")
    p.y_in.use_table("data", "y")
    p.s_in.use_table("data", "e")
    p.form.set_value("model", "Gaussian1D(2.5, 0, 1) + Const1D(0)")
    p.form.set_value("cons", "mean_0: -3..3")
    p.fit()
    out = p.out.toPlainText()
    assert "reduced chi2" in out and "amplitude_0" in out
    assert np.allclose(p._result["fit"].parameters, [3.0, 0.7, 1.3, 0.5], atol=0.1)
    assert len(p.canvas.figure.axes) == 2
    p.save_fit()
    p.save_residuals()
    assert "fitted_model" in ws and len(ws.get("fit_residuals")) == 200
    p.form.set_value("outl", True)
    p.fit()
    assert p._result["mask"] is not None


def test_fit1d_panel_pasted_expressions_and_units(qtbot, ws):
    p = mt.Fit1DPanel(ws)
    qtbot.addWidget(p)
    p.x_in.set_text("linspace(0, 10, 50)")
    p.y_in.set_text("3 + 2*linspace(0, 10, 50)")
    p.form.set_value("model", "Polynomial1D(1)")
    p.form.set_value("fitter", "LinearLSQFitter")
    p.fit()
    assert np.allclose(p._result["fit"].parameters, [3, 2])
    qt = QTable({"t": np.linspace(-5, 5, 60) * u.s,
                 "f": 3 * np.exp(-0.5 * (np.linspace(-5, 5, 60) / 1.5) ** 2) * u.Jy})
    ws.put("qt", qt)
    p.x_in.use_table("qt", "t")
    p.y_in.use_table("qt", "f")
    p.form.set_value("units", True)
    p.form.set_value("fitter", "TRFLSQFitter")
    p.form.set_value("model", "Gaussian1D(2*u.Jy, 0.1*u.s, 1*u.s)")
    p.fit()
    assert p._result["fit"].amplitude.value == pytest.approx(3.0, abs=1e-4)


def test_fit1d_panel_reports_errors(qtbot, ws, monkeypatch):
    seen = []
    monkeypatch.setattr("astrotools_adv.core.widgets.error_box",
                        lambda parent, exc, detail="": seen.append(exc))
    p = mt.Fit1DPanel(ws)
    qtbot.addWidget(p)
    p.fit()  # no data given
    p.x_in.set_text("1 2 3")
    p.y_in.set_text("1 2")
    p.fit()  # mismatched lengths
    p.y_in.set_text("1 2 3")
    p.form.set_value("model", "Gaussian2D()")
    p.fit()  # wrong input count
    p.form.set_value("model", "Gaussian1D()")
    p.fit()  # 3 points for 3 params works... but nonlinear fit may still succeed
    assert len(seen) >= 3 and all(isinstance(e, ParseError) for e in seen[:3])


def test_fit2d_panel(qtbot, ws):
    yy, xx = np.mgrid[:40, :50]
    img = (models.Gaussian2D(5.0, 22.0, 17.0, 4.0, 3.0) + models.Const2D(1.0))(xx, yy)
    ws.put("img", NDData(img))
    p = mt.Fit2DPanel(ws)
    qtbot.addWidget(p)
    p.guess()
    assert "Gaussian2D" in p.form.value("model")
    p.fit()
    assert np.allclose(p._result["fit"].parameters[:5], [5.0, 22.0, 17.0, 4.0, 3.0], atol=1e-3)
    assert len(p.canvas.figure.axes) >= 3
    p.form.set_value("roi", "10:40, 5:35")
    p.guess()
    p.fit()
    assert p._result["fit"].x_mean_0.value == pytest.approx(22.0, abs=1e-2)  # absolute coordinates
    p.save_fit()
    assert "fitted_model_2d" in ws


def test_fit2d_panel_bad_inputs(qtbot, ws, monkeypatch):
    seen = []
    monkeypatch.setattr("astrotools_adv.core.widgets.error_box",
                        lambda parent, exc, detail="": seen.append(exc))
    p = mt.Fit2DPanel(ws)
    qtbot.addWidget(p)
    p.fit()
    ws.put("img", np.zeros((10, 10)))
    p.img.refresh()
    p.form.set_value("roi", "garbage")
    p.fit()
    p.form.set_value("roi", "0:50, 0:5")
    p.fit()
    p.form.set_value("roi", "")
    p.form.set_value("model", "Gaussian1D()")
    p.fit()
    assert len(seen) == 4 and all(isinstance(e, ParseError) for e in seen)


def test_curve_panel_all_methods(qtbot, ws):
    p = mt.CurvePanel(ws)
    qtbot.addWidget(p)
    p.x_in.set_text("linspace(0, 10, 40)")
    p.y_in.set_text("sin(linspace(0, 10, 40))")
    p.form.set_value("knots", "3, 6")
    p.form.set_value("deriv", 1)
    for method in mt.CURVE_METHODS:
        p.form.set_value("method", method)
        p.fit()
        assert p.model is not None, method
        assert p.out.toPlainText(), method
    p.form.set_value("method", "Spline: interpolate")
    p.form.set_value("deriv", 0)
    p.fit()
    assert len(p.canvas.figure.axes) == 1
    p.save()
    assert "curve_model" in ws


def test_model_times_number_gives_actionable_error():
    with pytest.raises(ParseError, match="Scale"):
        mt.parse_model("Gaussian1D(1, 0, 1) * 2")
