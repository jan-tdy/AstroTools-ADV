import numpy as np
import pytest
from astropy import units as u
from astropy.nddata import (CCDData, NDData, NDDataRef, StdDevUncertainty,
                            VarianceUncertainty)
from astropy.wcs import WCS

from astrotools_adv.core import parsing
from astrotools_adv.modules import _images as im
from astrotools_adv.modules import nddata_tools as nt


@pytest.fixture
def shown(monkeypatch):
    """Collect error dialogs instead of blocking on them."""
    errors = []
    monkeypatch.setattr("astrotools_adv.core.widgets.error_box",
                        lambda parent, exc, detail="": errors.append(exc))
    return errors


def panel(qtbot, ws, key):
    spec = next(s for s in nt.SPECS if s.key == key)
    w = spec.factory(ws)
    qtbot.addWidget(w)
    return w


def sky_wcs(n=100):
    w = WCS(naxis=2)
    w.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    w.wcs.crval = [150.0, 2.0]
    w.wcs.crpix = [n / 2, n / 2]
    w.wcs.cdelt = [-1 / 3600, 1 / 3600]
    return w


# ---- pure helpers ---------------------------------------------------------- #
def test_build_nddata_uncertainty_mask_unit():
    data = np.arange(1.0, 7.0).reshape(2, 3) * 100
    nd = nt.build_nddata(data, "NDDataRef", "adu", "StdDev", "poisson", "data > 400")
    assert isinstance(nd, NDDataRef) and nd.unit == u.adu
    assert np.allclose(nd.uncertainty.array, np.sqrt(data))
    assert nd.mask.sum() == 2
    ccd = nt.build_nddata(data, "CCDData")
    assert isinstance(ccd, CCDData) and ccd.unit == u.adu
    var = nt.build_nddata(data, "NDData", "", "Variance", "4")
    assert isinstance(var.uncertainty, VarianceUncertainty) and np.all(var.uncertainty.array == 4)
    with pytest.raises(parsing.ParseError):
        nt.build_nddata(data, "NDData", "", "StdDev", "")
    with pytest.raises(parsing.ParseError):
        nt.build_nddata(data, "NDData", "", "StdDev", "np.ones(5)")
    with pytest.raises(parsing.ParseError):
        nt.build_nddata(np.float64(3.0))


def test_describe_and_fits_roundtrip(tmp_path):
    nd = nt.build_nddata(np.ones((4, 5)), "CCDData", "electron", "StdDev", "0.5")
    text = nt.describe_nd(nd)
    assert "electron" in text and "StdDevUncertainty" in text
    path = str(tmp_path / "x.fits")
    nt.save_fits(nd, path)
    back = im.load_fits_image(path)
    assert back.data.shape == (4, 5) and back.unit == u.electron
    nt.save_fits(NDData(np.zeros((3, 3))), path)  # plain NDData is converted (adu)
    assert im.load_fits_image(path).unit == u.adu


def test_parse_size_and_blocks():
    assert nt.parse_size("40") == 40
    assert nt.parse_size("30, 20") == (30, 20)
    q = nt.parse_size("30 arcsec")
    assert q.unit == u.arcsec
    mixed = nt.parse_size("10, 5 arcsec")
    assert mixed[0].unit == u.pix and mixed[1].unit == u.arcsec
    for bad in ("", "0", "1,2,3", "-3"):
        with pytest.raises(parsing.ParseError):
            nt.parse_size(bad)
    assert nt.parse_block_size("2x3") == (2, 3)
    with pytest.raises(parsing.ParseError):
        nt.parse_block_size("0")


def test_make_cutout_pixel_and_sky():
    data = np.arange(100 * 100, dtype=float).reshape(100, 100)
    wcs = sky_wcs()
    nd = NDData(data, wcs=wcs)
    cut = nt.make_cutout(nd, "50 40", False, "10, 20", "trim")
    assert cut.shape == (10, 20)
    assert np.array_equal(cut.data, data[35:45, 40:60])
    assert cut.wcs is not None
    pix = wcs.world_to_pixel_values(150.0, 2.0)  # == CRPIX-1
    sky = nt.make_cutout(nd, "150.0 2.0", True, "11", "strict")
    assert sky.center_original == pytest.approx((float(pix[0]), float(pix[1])), abs=1e-6)
    ang = nt.make_cutout(nd, "150.0 2.0", True, "10 arcsec", "trim")
    assert ang.shape[0] in (10, 11)  # 1"/pixel
    with pytest.raises(parsing.ParseError):
        nt.make_cutout(NDData(data), "150 2", True, "10", "trim")
    with pytest.raises(parsing.ParseError):
        nt.make_cutout(NDData(np.ones(5)), "1 1", False, "2", "trim")
    part = nt.make_cutout(nd, "0 0", False, "10", "partial", "-1")
    assert part.shape == (10, 10) and part.data[0, 0] == -1


# ---- panels ---------------------------------------------------------------- #
def test_nddata_panel(qtbot, ws, shown):
    p = panel(qtbot, ws, "nddata")
    p.src.make_test_image()
    p.form.set_value("kind", "NDDataArray")
    p.build()
    assert type(ws.get("nddata")).__name__ == "NDDataArray"
    p.form.set_value("kind", "CCDData")
    p.form.set_value("unc", "StdDev")
    p.build()
    assert not shown
    assert isinstance(ws.get("nddata_2"), CCDData)
    assert "StdDevUncertainty" in p.out.toPlainText()
    p.form.set_value("unc_val", "")
    p.form.set_value("unc", "Variance")
    p.build()
    assert shown and isinstance(shown[0], parsing.ParseError)


def test_cutout_panel_and_edge_cases(qtbot, ws, shown):
    p = panel(qtbot, ws, "cutout2d")
    p.src.make_test_image()
    p.form.set_value("pos", "64 64")
    p.form.set_value("size", "20")
    p.make()
    assert not shown and ws.get("cutout").data.shape == (20, 20)
    p.form.set_value("pos", "1000 1000")  # fully outside: NoOverlapError reported, no crash
    p.make()
    assert len(shown) == 1
    p.form.set_value("pos", "abc")
    p.make()
    assert len(shown) == 2


def test_block_panel_conserves_sum(qtbot, ws, shown):
    p = panel(qtbot, ws, "blocks")
    ws.put("img", np.arange(64.0).reshape(8, 8))
    p.src.select("img")
    p.form.set_value("block", "2")
    p.apply()
    red = ws.get("blocked").data
    assert red.shape == (4, 4) and red.sum() == np.arange(64.0).sum()
    ws.put("small", np.arange(16.0).reshape(4, 4))
    p.src.select("small")
    p.form.set_value("op", "block_replicate")
    p.form.set_value("conserve", True)
    p.apply()
    rep = ws.get("blocked_2").data
    assert rep.shape == (8, 8) and rep.sum() == pytest.approx(120.0)
    p.form.set_value("block", "2, 3, 4")
    p.apply()
    assert shown


def test_bitmask_panel(qtbot, ws, shown):
    p = panel(qtbot, ws, "bitmask")
    p.form.set_value("bits", "0, 1, 2, 4, 5")
    p.form.set_value("ignore", "1")
    p.make()
    mask = ws.get("bitmask")
    assert list(mask) == [False, False, True, True, True]
    p.form.set_value("ignore", "CR")
    p.form.set_value("names", "CR=1, HOT=4")
    p.make()
    assert list(ws.get("bitmask_2")) == [False, False, True, True, True]
    p.form.set_value("ignore", "NOPE")
    p.make()
    assert shown
    p.form.set_value("ignore", "1,4")
    p.interpret()
    assert "-> 5" in p.out.toPlainText()


def test_arithmetic_uncertainty_propagation(qtbot, ws, shown):
    p = panel(qtbot, ws, "ndarith")
    ws.put("a", NDData(np.full((3, 3), 10.0), uncertainty=StdDevUncertainty(np.full((3, 3), 3.0))))
    ws.put("b", NDData(np.full((3, 3), 4.0), uncertainty=StdDevUncertainty(np.full((3, 3), 4.0))))
    p.a.select("a")
    p.b.select("b")
    for op, value in (("add", 14.0), ("subtract", 6.0), ("multiply", 40.0), ("divide", 2.5)):
        p.form.set_value("op", op)
        p.form.set_value("name", f"r_{op}")
        p.compute()
        assert ws.get(f"r_{op}").data[0, 0] == pytest.approx(value)
    assert not shown
    assert np.allclose(ws.get("r_add").uncertainty.array, 5.0)  # sqrt(3^2 + 4^2)
    assert np.allclose(ws.get("r_subtract").uncertainty.array, 5.0)
    # relative errors add in quadrature for multiply: 40*sqrt(0.3^2+1^2)
    assert np.allclose(ws.get("r_multiply").uncertainty.array, 40 * np.hypot(0.3, 1.0))
    p.form.set_value("bmode", "constant")
    p.form.set_value("const", "2")
    p.form.set_value("op", "multiply")
    p.form.set_value("name", "r_const")
    p.compute()
    assert np.allclose(ws.get("r_const").uncertainty.array, 6.0)
    p.form.set_value("const", "2 m")  # unit-less data times metres is fine
    p.compute()
    assert not shown
    p.form.set_value("op", "add")
    p.compute()  # dimensionless + metre -> unit error is reported, not raised
    assert shown


def test_arithmetic_wcs_mismatch_reports(qtbot, ws, shown):
    p = panel(qtbot, ws, "ndarith")
    ws.put("a", NDData(np.ones((100, 100)), wcs=sky_wcs()))
    other = sky_wcs()
    other.wcs.crval = [10.0, 10.0]
    ws.put("b", NDData(np.ones((100, 100)), wcs=other))
    p.a.select("a")
    p.b.select("b")
    p.compute()
    assert not shown  # first_found keeps the first WCS without comparing
    p.form.set_value("wcs", "strict")
    p.compute()
    assert shown and "WCS" in str(shown[0])
    shown.clear()
    p.form.set_value("wcs", "none")
    p.compute()
    assert not shown and ws.get("nd_result_2").wcs is None


def test_array_utils_panel(qtbot, ws, shown):
    p = panel(qtbot, ws, "nd_utils")
    ws.put("big", NDData(np.arange(100.0).reshape(10, 10),
                         mask=np.zeros((10, 10), bool), uncertainty=StdDevUncertainty(np.ones((10, 10)))))
    p.src.select("big")
    p.form.set_value("slice", "2:5, ::3")
    p.apply()
    res = ws.get("util_result")
    assert res.data.shape == (3, 4) and res.mask.shape == (3, 4) and res.uncertainty.array.shape == (3, 4)
    p.form.set_value("op", "overlap_slices")
    p.form.set_value("pos", "0, 0")
    p.form.set_value("shape", "4, 4")
    p.apply()
    assert "slice(0, 2" in p.out.toPlainText() and "slice(2, 4" in p.out.toPlainText()
    p.form.set_value("op", "extract_array")
    p.form.set_value("pos", "5, 5")
    p.form.set_value("shape", "3, 3")
    p.apply()
    assert np.array_equal(ws.get("util_result_2").data, np.arange(100.0).reshape(10, 10)[4:7, 4:7])
    ws.put("patch", np.ones((3, 3)))
    p.small.select("patch")
    p.form.set_value("op", "add_array")
    p.apply()
    added = ws.get("util_result_3").data
    assert added[5, 5] == 56.0 and added.sum() == np.arange(100.0).sum() + 9
    p.form.set_value("op", "subpixel_indices")
    p.form.set_value("pos", "4.3, 5.5")
    p.form.set_value("fill", "2")
    p.apply()
    assert "subpixel_indices" in p.out.toPlainText() and not shown
    for bad in ("nan", "0", "2.5"):  # nan is the field's default for other operations
        p.form.set_value("fill", bad)
        p.apply()
        assert "whole number" in str(shown[-1])
    shown.clear()
    p.form.set_value("shape", "3")
    p.form.set_value("op", "extract_array")
    p.apply()
    assert shown


def test_calibration_panel(qtbot, ws, shown):
    p = panel(qtbot, ws, "ccd_calib")
    raw = np.full((8, 8), 1100.0)
    ws.put("raw", NDData(raw, unit=u.adu, uncertainty=StdDevUncertainty(np.full((8, 8), 3.0))))
    ws.put("bias", NDData(np.full((8, 8), 100.0), unit=u.adu, uncertainty=StdDevUncertainty(np.full((8, 8), 4.0))))
    flat = np.full((8, 8), 2.0)
    flat[0, 0] = 4.0
    ws.put("flat", NDData(flat, unit=u.adu))
    p.src.select("raw")
    p.bias.select("bias")
    p.flat.select("flat")
    p.form.set_value("use_bias", True)
    p.calibrate()
    res = ws.get("calibrated")
    assert not shown and np.allclose(res.data, 1000.0)
    assert np.allclose(res.uncertainty.array, 5.0)
    p.form.set_value("use_flat", True)
    p.calibrate()
    mean = flat.mean()
    out = ws.get("calibrated_2").data
    assert out[1, 1] == pytest.approx(1000.0 / (2.0 / mean))
    p.statistics()
    assert "clipped" in p.out.toPlainText()
    p.form.set_value("use_bias", False)
    p.form.set_value("use_flat", False)
    p.calibrate()
    assert shown


def test_all_nan_and_tiny_inputs_do_not_crash(qtbot, ws, shown):
    ws.put("nan", np.full((4, 4), np.nan))
    ws.put("one", np.array([[5.0]]))
    for key in ("nddata", "ccd_calib", "blocks"):
        p = panel(qtbot, ws, key)
        for name in ("nan", "one"):
            p.src.select(name)
            if key == "nddata":
                p.form.set_value("unc", "none")
                p.build()
            elif key == "ccd_calib":
                p.statistics()
            else:
                p.form.set_value("block", "1")
                p.apply()
    assert not shown


def test_specs_are_images_category():
    assert {s.category for s in nt.SPECS} == {"Images"}
    assert len({s.key for s in nt.SPECS}) == len(nt.SPECS)


def test_poisson_uncertainty_follows_the_selected_class():
    data = np.array([[0.0, 4.0], [16.0, 25.0]])
    std = nt.build_nddata(data, "NDDataRef", "adu", "StdDev", "poisson")
    var = nt.build_nddata(data, "NDDataRef", "adu", "Variance", "poisson")
    inv = nt.build_nddata(data, "NDDataRef", "adu", "InverseVariance", "poisson")
    assert np.allclose(std.uncertainty.array, [[0, 2], [4, 5]])
    assert np.allclose(var.uncertainty.array, [[0, 4], [16, 25]])
    assert np.allclose(inv.uncertainty.array, [[0, 0.25], [1 / 16, 0.04]])


def test_wcs_strictly_equal_ignores_unset_state():
    w1 = WCS(naxis=2)
    w1.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    w1.wcs.crval = [10, 41]
    w1.wcs.crpix = [1, 1]
    w1.wcs.cdelt = [-0.001, 0.001]
    same = w1.deepcopy()
    other = w1.deepcopy()
    other.wcs.crval = [11, 41]
    assert nt.wcs_strictly_equal(w1, same)
    assert not nt.wcs_strictly_equal(w1, other)
    assert nt.wcs_strictly_equal(None, None)
    assert not nt.wcs_strictly_equal(w1, None)
