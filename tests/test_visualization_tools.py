import numpy as np
import pytest
from astropy import units as u
from astropy.nddata import NDData
from astropy.visualization import (AsinhStretch, CompositeStretch, HistEqStretch, LinearStretch,
                                   LogStretch, SqrtStretch)
from astropy.wcs import WCS

from astrotools_adv.core import parsing
from astrotools_adv.modules import visualization_tools as vt
from astrotools_adv.modules._images import synthetic_image


@pytest.fixture
def shown(monkeypatch):
    errors = []
    monkeypatch.setattr("astrotools_adv.core.widgets.error_box",
                        lambda parent, exc, detail="": errors.append(exc))
    return errors


def panel(qtbot, ws, key):
    w = next(s for s in vt.SPECS if s.key == key).factory(ws)
    qtbot.addWidget(w)
    return w


def sky_wcs(n=64):
    w = WCS(naxis=2)
    w.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    w.wcs.crval = [150.0, 2.0]
    w.wcs.crpix = [n / 2, n / 2]
    w.wcs.cdelt = [-1 / 3600, 1 / 3600]
    return w


# ---- pure ------------------------------------------------------------------ #
def test_intervals_match_formulas():
    data = np.arange(101.0)
    assert vt.make_interval("MinMax").get_limits(data) == (0.0, 100.0)
    assert vt.make_interval("Percentile", percent=90).get_limits(data) == pytest.approx((5.0, 95.0))
    assert vt.make_interval("AsymmetricPercentile", lower=10, upper=60).get_limits(data) \
        == pytest.approx((10.0, 60.0))
    assert vt.make_interval("Manual", vmin=2, vmax=3).get_limits(data) == (2, 3)
    assert vt.make_interval("Manual", vmin=20).get_limits(data) == (20, 100.0)
    lo, hi = vt.make_interval("ZScale").get_limits(data)
    assert lo >= 0 and hi <= 100
    for bad in (("Percentile", {"percent": 0}), ("AsymmetricPercentile", {"lower": 50, "upper": 10}),
                ("Manual", {"vmin": 5, "vmax": 1}), ("Nope", {})):
        with pytest.raises(parsing.ParseError):
            vt.make_interval(bad[0], **bad[1])


def test_stretch_formulas():
    x = np.linspace(0, 1, 11)
    assert np.allclose(vt.make_stretch("Linear")(x), x)
    assert np.allclose(vt.make_stretch("Sqrt")(x), np.sqrt(x))
    assert np.allclose(vt.make_stretch("Squared")(x), x ** 2)
    assert np.allclose(vt.make_stretch("Power", power=3)(x), x ** 3)
    assert np.allclose(vt.make_stretch("Log", a=1000)(x), np.log(1000 * x + 1) / np.log(1001))
    assert np.allclose(vt.make_stretch("Asinh", a=0.1)(x),
                       np.arcsinh(x / 0.1) / np.arcsinh(1 / 0.1))
    assert np.allclose(vt.make_stretch("ContrastBias", contrast=2, bias=0.5)(x),
                       np.clip((x - 0.5) * 2 + 0.5, 0, 1))
    data = np.random.default_rng(1).normal(size=500)
    heq = vt.make_stretch("HistEq", data=data)
    assert isinstance(heq, HistEqStretch)
    y = heq(np.linspace(0, 1, 5))
    assert np.all(np.diff(y) >= 0)
    for name, kw in (("Log", {"a": 1.0}), ("Asinh", {"a": 0}), ("Power", {"power": -1}),
                     ("HistEq", {}), ("Nope", {})):
        with pytest.raises(parsing.ParseError):
            vt.make_stretch(name, **kw)


def test_composite_order_and_norm():
    x = np.linspace(0, 1, 9)
    comp = CompositeStretch(SqrtStretch(), LogStretch(10))
    assert np.allclose(comp(x), LogStretch(10)(SqrtStretch()(x)))
    data = np.linspace(10, 20, 101).reshape(101, 1)
    norm = vt.build_norm(data, vt.make_interval("MinMax"), vt.make_stretch("Linear"))
    assert (norm.vmin, norm.vmax) == (10.0, 20.0)
    assert norm(15.0) == pytest.approx(0.5)
    flat = vt.build_norm(np.full((3, 3), 7.0), vt.make_interval("MinMax"), LinearStretch())
    assert flat.vmax > flat.vmin
    nan_img = np.full((3, 3), np.nan)
    with pytest.raises(parsing.ParseError):
        vt.build_norm(nan_img, vt.make_interval("ZScale"), LinearStretch())
    one = vt.build_norm(np.array([[2.0]]), vt.make_interval("Percentile"), AsinhStretch())
    assert one.vmin < one.vmax
    xs, ys = vt.stretch_curve(SqrtStretch(), 5)
    assert np.allclose(ys, np.sqrt(xs))


# ---- panels ---------------------------------------------------------------- #
def test_viewer_plain_and_wcs(qtbot, ws, shown):
    p = panel(qtbot, ws, "viz_viewer")
    ws.put("star", NDData(synthetic_image((64, 64)), wcs=sky_wcs()))
    p.src.select("star")
    p.show()
    assert not shown and "WCS axes = True" in p.out.toPlainText()
    for interval in vt.INTERVALS:
        for stretch in vt.STRETCHES:
            p.form.set_value("interval", interval)
            p.form.set_value("stretch", stretch)
            p.form.set_value("a", 10.0)
            p.show()
    assert not shown
    p.form.set_value("stretch2", "Sqrt")
    p.form.set_value("invert", True)
    p.form.set_value("points", "150.0 2.0\n150.001 2.001")
    p.form.set_value("circles", "150 2 | 10 arcsec")
    p.show()
    assert not shown and p.out.toPlainText().endswith("True")
    p.form.set_value("mode", "simple_norm")
    p.form.set_value("simple", "asinh")
    p.show()
    assert not shown and "vmin" in p.out.toPlainText()
    p.form.set_value("circles", "150 2")  # missing '|'
    p.show()
    assert len(shown) == 1


def test_viewer_degenerate_inputs(qtbot, ws, shown):
    p = panel(qtbot, ws, "viz_viewer")
    ws.put("one", np.array([[3.0]]))
    ws.put("nan", np.full((5, 5), np.nan))
    ws.put("line", np.arange(10.0))
    p.src.select("one")
    p.show()
    assert not shown
    p.src.select("nan")
    p.show()
    assert len(shown) == 1 and "finite" in str(shown[0])
    p.src.select("line")
    p.show()
    assert len(shown) == 2
    p.src.select("one")
    p.form.set_value("interval", "Manual")
    p.form.set_value("vmin", "x")
    p.show()
    assert len(shown) == 3


def test_viewer_save_png(qtbot, ws, shown, tmp_path):
    p = panel(qtbot, ws, "viz_viewer")
    p.src.make_test_image()
    p.show()
    out = tmp_path / "v.png"
    p.image.save(str(out))
    assert out.stat().st_size > 1000 and not shown


def test_rgb_panel(qtbot, ws, shown):
    p = panel(qtbot, ws, "viz_rgb")
    r = synthetic_image((32, 32), seed=1)
    for name, seed in (("r", 1), ("g", 2), ("b", 3)):
        ws.put(name, synthetic_image((32, 32), seed=seed, nan_fraction=0.01))
        p.sel[name].select(name)
    p.compose()
    rgb = ws.get("rgb")
    assert not shown and rgb.shape == (32, 32, 3) and rgb.dtype == np.uint8
    p.form.set_value("lstretch", "LuptonAsinhZscaleStretch")
    p.compose()
    assert not shown
    p.form.set_value("method", "make_rgb")
    p.form.set_value("interval", "Percentile")
    p.compose()
    assert not shown and ws.get("rgb_3").shape == (32, 32, 3)
    ws.put("b", np.ones((5, 5)))
    p.sel["b"].select("b")
    p.compose()
    assert shown and "shapes differ" in str(shown[0])
    del r


def test_histogram_panel(qtbot, ws, shown):
    p = panel(qtbot, ws, "viz_hist")
    ws.put("g", np.random.default_rng(0).normal(0, 1, (100, 100)))
    p.src.select("g")
    for rule in ("knuth", "freedman", "scott", "blocks", "auto", "30"):
        p.form.set_value("bins", rule)
        p.go()
    assert not shown
    p.form.set_value("bins", "30")
    p.go()
    assert "30 bins" in p.out.toPlainText()
    p.form.set_value("bins", "bogus")
    p.go()
    assert shown
    shown.clear()
    p.form.set_value("bins", "10")
    p.form.set_value("lo", 90.0)
    p.form.set_value("hi", 10.0)
    p.go()
    assert shown
    ws.put("nan", np.full((4, 4), np.nan))
    p.src.select("nan")
    p.form.set_value("lo", 0.0)
    p.form.set_value("hi", 100.0)
    p.go()
    assert len(shown) == 2


def test_quantity_time_panel(qtbot, ws, shown):
    p = panel(qtbot, ws, "viz_units")
    p.go()
    assert not shown and "Time" in p.out.toPlainText() and "[m]" in p.out.toPlainText()
    p.form.set_value("tformat", "mjd")
    p.go()
    assert not shown
    p.form.set_value("x", "linspace(0, 10, 5) * u.s")
    p.form.set_value("y", "x.to(u.ms)")
    p.go()
    assert not shown
    p.form.set_value("y", "x.value ** 2")
    p.go()
    assert not shown
    p.form.set_value("y", "linspace(0, 1, 3)")
    p.go()
    assert shown and "values" in str(shown[0])
    p.form.set_value("x", "bogus")
    p.go()
    assert len(shown) == 2


def test_specs_category():
    assert {s.category for s in vt.SPECS} == {"Images"}
