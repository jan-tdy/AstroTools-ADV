import numpy as np
import pytest
from astropy import units as u
from astropy.convolution import CustomKernel, Gaussian1DKernel, Gaussian2DKernel, Kernel
from astropy.nddata import NDData

from astrotools_adv.core import parsing
from astrotools_adv.modules import convolution_tools as ct
from astrotools_adv.modules._images import synthetic_image


@pytest.fixture
def shown(monkeypatch):
    errors = []
    monkeypatch.setattr("astrotools_adv.core.widgets.error_box",
                        lambda parent, exc, detail="": errors.append(exc))
    return errors


def panel(qtbot, ws, key):
    w = next(s for s in ct.SPECS if s.key == key).factory(ws)
    qtbot.addWidget(w)
    return w


# ---- pure ------------------------------------------------------------------ #
@pytest.mark.parametrize("name", list(ct.KERNELS))
def test_every_kernel_builds_and_is_finite(name):
    cls, ndim, default = ct.KERNELS[name]
    arr = np.ones((5, 5)) if ndim == 2 else np.ones(5)
    k = ct.build_kernel(name, default, array=arr if cls is CustomKernel else None)
    assert np.all(np.isfinite(k.array)) and k.dimension == (ndim or arr.ndim)
    assert "class" in ct.kernel_info(k)


@pytest.mark.parametrize("name", ["Gaussian1DKernel", "Gaussian2DKernel", "Box2DKernel",
                                  "Tophat2DKernel", "Ring2DKernel", "Moffat2DKernel",
                                  "AiryDisk2DKernel", "Trapezoid1DKernel"])
def test_standard_kernels_sum_to_one(name):
    k = ct.build_kernel(name, ct.KERNELS[name][2])
    assert k.array.sum() == pytest.approx(1.0, abs=1e-3 if "Airy" in name else 1e-6)


def test_wavelet_integrates_to_zero_and_normalize_modes():
    k = ct.build_kernel("RickerWavelet2DKernel (Mexican hat)", "width=3")
    assert abs(k.array.sum()) < 1e-2
    g = ct.build_kernel("Gaussian2DKernel", "x_stddev=2", normalize="peak")
    assert g.array.max() == pytest.approx(1.0)
    g = ct.build_kernel("Gaussian1DKernel", "stddev=2", x_size=11)
    assert g.array.size == 11


def test_build_kernel_errors():
    for args in (("Nope", ""), ("Gaussian1DKernel", "bogus=1"), ("Gaussian1DKernel", "stddev=-2"),
                 ("Gaussian1DKernel", "stddev=2", 4), ("CustomKernel", "", 0, 0, "center", 10, None),
                 ("CustomKernel", "", 0, 0, "center", 10, np.ones((4, 4))),
                 ("Model1DKernel", "models.NotAModel()")):
        with pytest.raises(parsing.ParseError):
            ct.build_kernel(*args)


def test_build_kernel_zero_width_is_a_parse_error():
    with pytest.raises(parsing.ParseError):
        ct.build_kernel("Box2DKernel", "width=0")


def test_kernel_arithmetic():
    a, b = Gaussian2DKernel(2), ct.build_kernel("Box2DKernel", "width=3")
    assert ct.kernel_arithmetic(a, b, "add").array.sum() == pytest.approx(2.0)
    assert ct.kernel_arithmetic(a, b, "subtract").array.sum() == pytest.approx(0.0, abs=1e-12)
    assert ct.kernel_arithmetic(a, None, "scale", 3.0).array.sum() == pytest.approx(3.0)
    conv = ct.kernel_arithmetic(a, b, "convolve")
    assert conv.array.shape == (a.shape[0] + 2, a.shape[1] + 2)
    assert conv.array.sum() == pytest.approx(a.array.sum() * b.array.sum())
    with pytest.raises(parsing.ParseError):
        ct.kernel_arithmetic(a, Gaussian1DKernel(2), "add")
    with pytest.raises(parsing.ParseError):
        ct.kernel_arithmetic(a, None, "add")


def test_delta_kernel_is_identity_for_both_methods():
    img = synthetic_image((32, 32), noise=1.0)
    delta = np.zeros((3, 3))
    delta[1, 1] = 1.0
    for method in ("convolve", "convolve_fft"):
        out = ct.run_convolution(img, CustomKernel(delta), method)
        assert np.allclose(out, img)


def test_convolve_preserves_flux_and_nan_handling():
    img = np.zeros((41, 41))
    img[20, 20] = 100.0
    out = ct.run_convolution(img, Gaussian2DKernel(2), "convolve")
    assert out.sum() == pytest.approx(100.0, rel=1e-3)
    assert out.argmax() == 20 * 41 + 20
    nan_img = img.copy()
    nan_img[5, 5] = np.nan
    interp = ct.run_convolution(nan_img, Gaussian2DKernel(1), "convolve", nan_treatment="interpolate")
    assert np.isfinite(interp[5, 5])
    kept = ct.run_convolution(nan_img, Gaussian2DKernel(1), "convolve", preserve_nan=True)
    assert np.isnan(kept[5, 5])
    fft = ct.run_convolution(img, Gaussian2DKernel(2), "convolve_fft")
    assert np.allclose(fft, out, atol=1e-6)
    wrap = ct.run_convolution(img, Gaussian2DKernel(2), "convolve", boundary="wrap")
    assert wrap.sum() == pytest.approx(100.0, rel=1e-3)
    mask = np.zeros_like(img, bool)
    mask[20, 20] = True
    assert np.nansum(ct.run_convolution(img, Gaussian2DKernel(2), "convolve", mask=mask)) \
        == pytest.approx(0.0, abs=1e-9)


def test_run_convolution_rejects_bad_input():
    with pytest.raises(parsing.ParseError):
        ct.run_convolution(np.ones(10), Gaussian2DKernel(1))
    with pytest.raises(parsing.ParseError):
        ct.run_convolution(np.ones((0, 4)), np.ones((0, 3)))
    with pytest.raises(parsing.ParseError):
        ct.quick_gaussian(3, 1.0)
    with pytest.raises(parsing.ParseError):
        ct.quick_gaussian(2, 0)


# ---- panels ---------------------------------------------------------------- #
def test_kernel_panel_opens_ready_to_build(qtbot, ws, shown):
    """Fresh page: the selected kernel and its default parameters must match."""
    p = panel(qtbot, ws, "conv_kernels")
    assert p.form.value("kernel") == "Gaussian2DKernel"
    p.build()
    assert not shown and ws.get("kernel").dimension == 2


def test_kernel_panel_build_and_arithmetic(qtbot, ws, shown):
    p = panel(qtbot, ws, "conv_kernels")
    p.form.set_value("kernel", "Box2DKernel")
    assert p.form.value("params") == "width=5"  # defaults follow the selection
    p.build()
    assert not shown and isinstance(ws.get("kernel"), Kernel)
    p.form.set_value("kernel", "Gaussian1DKernel")
    p.build()
    assert ws.get("kernel_2").dimension == 1
    p.form.set_value("params", "stddev=oops")
    p.build()
    assert len(shown) == 1
    ws.put("g", Gaussian2DKernel(1.5))
    p.a_combo.setCurrentText("g")
    p.k2.setCurrentText("kernel_2")
    p.form.set_value("op", "add")
    p.arith()
    assert len(shown) == 2  # 2-D + 1-D
    p.form.set_value("op", "scale")
    p.form.set_value("scalar", 4.0)
    p.arith()
    assert ws.get("scale_kernel").array.sum() == pytest.approx(4.0)
    p.form.set_value("kernel", "CustomKernel")
    ws.put("arr", np.ones((3, 3)))
    p.arr.select("arr")
    p.build()
    assert isinstance(ws.get("kernel_3"), CustomKernel)


def test_convolve_panel_end_to_end(qtbot, ws, shown):
    p = panel(qtbot, ws, "convolve")
    img = np.zeros((31, 31))
    img[15, 15] = 50.0
    ws.put("img", NDData(img, unit=u.adu))
    p.img.select("img")
    p.kp.sigma.setValue(2.0)
    p.go()
    assert not shown
    res = ws.get("convolved")
    assert res.unit == u.adu and res.data.sum() == pytest.approx(50.0, rel=1e-3)
    assert "flux before 50" in p.out.toPlainText()
    p.form.set_value("method", "convolve_fft")
    assert [p.form.fields["boundary"].itemText(i) for i in range(p.form.fields["boundary"].count())] \
        == ["fill", "wrap"]
    p.go()
    assert np.allclose(ws.get("convolved_2").data, res.data, atol=1e-6)
    ws.put("line", np.arange(10.0))  # 1-D data with default 1-D gaussian works too
    p.img.select("line")
    p.go()
    assert not shown
    ws.put("k2d", Gaussian2DKernel(1))
    p.kp.mode.setCurrentText("workspace kernel")
    p.kp.combo.setCurrentText("k2d")
    p.go()
    assert shown and isinstance(shown[0], parsing.ParseError)  # 1-D data vs 2-D kernel


def test_convolve_panel_nan_and_empty(qtbot, ws, shown):
    p = panel(qtbot, ws, "convolve")
    ws.put("allnan", np.full((8, 8), np.nan))
    p.img.select("allnan")
    p.go()
    assert not shown  # all-NaN in, NaN out, no crash
    ws.put("single", np.array([[3.0]]))
    p.img.select("single")
    p.kp.sigma.setValue(0.5)
    p.go()
    assert shown or ws.get("convolved_2") is not None


def test_nan_panel(qtbot, ws, shown):
    p = panel(qtbot, ws, "conv_nans")
    img = np.ones((20, 20))
    ws.put("flat", img)
    p.img.select("flat")
    p.form.set_value("inject", 0.05)
    p.go()
    assert not shown
    out = ws.get("nan_filled").data
    assert not np.isnan(out).any()
    assert np.allclose(out[6:-6, 6:-6], 1.0, atol=5e-3)  # interior; the fill boundary only darkens edges
    assert "NaN before" in p.out.toPlainText()


def test_convolve_models_panel(qtbot, ws, shown):
    p = panel(qtbot, ws, "conv_models")
    p.form.set_value("model", "models.Gaussian1D(10, 0, 1)")
    p.form.set_value("kernel", "models.Gaussian1D(1, 0, 1)")
    p.form.set_value("grid", "-12 12 481")
    p.go()
    assert not shown
    x, y = ws.get("convolved_model")
    # sigma_total = sqrt(2); normalised-kernel peak = 10 * 1 / sqrt(2)
    assert y.max() == pytest.approx(10 / np.sqrt(2), rel=2e-2)
    assert x[y.argmax()] == pytest.approx(0.0, abs=0.06)
    p.form.set_value("mode", "convolve_models_fft")
    p.go()
    assert not shown
    p.form.set_value("grid", "1 0 5")
    p.go()
    p.form.set_value("model", "models.Nope()")
    p.go()
    assert len(shown) == 2
