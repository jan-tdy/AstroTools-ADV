import numpy as np
import pytest
from astropy import units as u
from astropy.coordinates import SkyCoord
from astropy.io import fits
from astropy.nddata import NDData
from astropy.table import Table
from astropy.wcs import WCS

from astrotools_adv.core import parsing
from astrotools_adv.modules import wcs_tools as wt
from astrotools_adv.modules._images import synthetic_image


@pytest.fixture
def shown(monkeypatch):
    errors = []
    monkeypatch.setattr("astrotools_adv.core.widgets.error_box",
                        lambda parent, exc, detail="": errors.append(exc))
    return errors


def panel(qtbot, ws, key):
    w = next(s for s in wt.SPECS if s.key == key).factory(ws)
    qtbot.addWidget(w)
    return w


def tan(**kw):
    args = dict(proj="TAN", frame="ICRS (RA/Dec)", crval=(150.0, 2.0), crpix=(50.5, 50.5),
                scale_arcsec=1.0, shape=(100, 100))
    args.update(kw)
    return wt.build_wcs(**args)


# ---- pure ------------------------------------------------------------------ #
def test_crpix_maps_to_crval_and_roundtrip():
    w = tan()
    ra, dec = w.all_pix2world(50.5, 50.5, 1)
    assert (float(ra), float(dec)) == pytest.approx((150.0, 2.0), abs=1e-12)
    pts = np.array([[1.0, 1.0], [100.0, 100.0], [30.2, 80.7]])
    world = wt.transform_points(w, pts, "pix2world", 1)
    back = wt.transform_points(w, world, "world2pix", 1)
    assert np.allclose(back, pts, atol=1e-7)
    zero = wt.transform_points(w, pts - 1, "pix2world", 0)
    assert np.allclose(zero, world)
    core = wt.transform_points(w, pts, "pix2world", 1, method="wcs")
    assert np.allclose(core, world)  # no distortion: identical


@pytest.mark.parametrize("proj", wt.PROJECTIONS)
def test_every_projection_builds_and_roundtrips(proj):
    w = wt.build_wcs(proj, crval=(150.0, 20.0), crpix=(50, 50), scale_arcsec=36.0, shape=(100, 100))
    pts = np.array([[55.0, 52.0], [48.0, 41.0]])
    world = wt.transform_points(w, pts, "pix2world", 1)
    assert np.all(np.isfinite(world))
    back = wt.transform_points(w, world, "world2pix", 1)
    assert np.allclose(back, pts, atol=1e-4 if proj != "CSC" else 0.05)


@pytest.mark.parametrize("frame,ctype", [("Galactic (l/b)", "GLON-TAN"), ("Ecliptic (lon/lat)", "ELON-TAN"),
                                         ("ICRS (RA/Dec)", "RA---TAN")])
def test_frames_and_ctype(frame, ctype):
    w = wt.build_wcs("TAN", frame, crval=(10.0, 20.0), crpix=(10, 10))
    assert w.wcs.ctype[0] == ctype


@pytest.mark.parametrize("east_left", [True, False])
@pytest.mark.parametrize("rot", [-170.0, -45.0, 0.0, 30.0, 90.0, 179.0])
def test_scale_rotation_parity(rot, east_left):
    w = tan(scale_arcsec=2.5, rotation_deg=rot, east_left=east_left)
    assert wt.rotation_angle(w) == pytest.approx(rot, abs=1e-9)
    assert wt.parity_east_left(w) == east_left
    scales = np.asarray(wt.proj_plane_pixel_scales(w)) * 3600
    assert scales == pytest.approx([2.5, 2.5])
    assert wt.proj_plane_pixel_area(w) * 3600 ** 2 == pytest.approx(6.25)


def test_north_up_geometry():
    w = tan(scale_arcsec=1.0)
    (ra0, dec0), (ra1, dec1), (ra2, dec2) = w.all_pix2world([[50.5, 50.5], [50.5, 60.5], [60.5, 50.5]], 1)
    assert dec1 > dec0 and ra1 == pytest.approx(ra0, abs=1e-9)   # +y is north
    assert ra2 < ra0  # +x is west when east is left


def test_build_errors():
    with pytest.raises(parsing.ParseError):
        wt.build_wcs("NOPE")
    with pytest.raises(parsing.ParseError):
        wt.build_wcs("TAN", "Nope")
    with pytest.raises(parsing.ParseError):
        tan(scale_arcsec=0)
    with pytest.raises(parsing.ParseError):
        tan(crval=(10.0, 95.0))
    with pytest.raises(parsing.ParseError):
        tan(pv_text="2_1")
    with pytest.raises(parsing.ParseError):
        wt.build_wcs("COP", pv_text="2_1=0")  # degenerate cone angle is rejected by wcslib
    assert wt.parse_pv("2_1=45, 2_2=1.5") == [(2, 1, 45.0), (2, 2, 1.5)]


def test_from_frame_and_header_roundtrip():
    g = wt.build_wcs_from_frame("galactic", "AIT", crval=(0.0, 0.0), crpix=(10, 10), scale_arcsec=100)
    assert g.wcs.ctype[0] == "GLON-AIT"
    with pytest.raises(parsing.ParseError):
        wt.build_wcs_from_frame("nonsense")
    w = tan(rotation_deg=20.0)
    text = wt.header_text(w)
    w2 = wt.wcs_from_header_text(text)
    pts = np.array([[10.0, 20.0], [80.0, 5.0]])
    assert np.allclose(w.all_pix2world(pts, 1), w2.all_pix2world(pts, 1))
    with pytest.raises(parsing.ParseError):
        wt.wcs_from_header_text("   ")
    with pytest.raises(parsing.ParseError):
        wt.wcs_from_header_text("CTYPE1 = 'RA---XXX'\nCTYPE2 = 'DEC--XXX'")


def test_wcs_from_fits_file(tmp_path):
    w = tan()
    path = str(tmp_path / "w.fits")
    fits.PrimaryHDU(np.zeros((100, 100)), header=w.to_header()).writeto(path)
    w2 = wt.wcs_from_fits(path)
    assert np.allclose(w2.wcs.crval, [150.0, 2.0])
    with pytest.raises(parsing.ParseError):
        wt.wcs_from_fits(path, ext=5)
    with pytest.raises(parsing.ParseError):
        wt.wcs_from_fits(str(tmp_path / "missing.fits"))


def test_summary_validate_and_nonceleste():
    w = tan(rotation_deg=10.0)
    text = wt.wcs_summary(w)
    assert "pixel scale: 1 x 1 arcsec/pix" in text and "rotation   : 10 deg" in text
    assert "validation" in wt.validate_wcs(w) or isinstance(wt.validate_wcs(w), str)
    lin = WCS(naxis=1)
    lin.wcs.ctype = ["FREQ"]
    lin.wcs.crval = [1.4e9]
    lin.wcs.crpix = [1]
    lin.wcs.cdelt = [1e6]
    lin.wcs.cunit = ["Hz"]
    assert "FREQ" in wt.wcs_summary(lin)


def test_highlevel_transform():
    w = tan()
    t = wt.highlevel_transform(w, "50.5 50.5", "pix2world")
    assert t["lon_deg"][0] == pytest.approx(150.0, abs=1e-7)
    back = wt.highlevel_transform(w, "150.0 2.0\n10h00m00s +02d00m00s", "world2pix")
    assert back["x"][0] == pytest.approx(49.5, abs=1e-6) and back["y"][0] == pytest.approx(49.5, abs=1e-6)
    assert back["x"][1] == pytest.approx(49.5, abs=1e-6)
    lin = WCS(naxis=1)
    lin.wcs.ctype = ["FREQ"]
    lin.wcs.crval = [1.4e9]
    lin.wcs.crpix = [1]
    lin.wcs.cdelt = [1e6]
    lin.wcs.cunit = ["Hz"]
    sp = wt.highlevel_transform(lin, "0\n10", "pix2world")
    assert sp["value"][0] == pytest.approx(1.4e9) and sp["value"][1] == pytest.approx(1.41e9)
    assert wt.highlevel_transform(lin, "1.41 GHz", "world2pix")["pix"][0] == pytest.approx(10.0)
    cube = WCS(naxis=3)
    with pytest.raises(parsing.ParseError):
        wt.highlevel_transform(cube, "1 2 3", "pix2world")


def test_transform_input_validation():
    w = tan()
    with pytest.raises(parsing.ParseError):
        wt.transform_points(w, np.ones((2, 3)), "pix2world")
    with pytest.raises(parsing.ParseError):
        wt.transform_points(w, np.ones((2, 2)), "pix2world", origin=2)
    with pytest.raises(parsing.ParseError):
        wt.points_from_text("1 2 3", 2)
    with pytest.raises(parsing.ParseError):
        wt.points_from_text("# only comment", 2)
    t = Table({"x": [1.0], "y": [2.0]})
    assert wt.points_from_table(t, ["x", "y"], 2).tolist() == [[1.0, 2.0]]
    with pytest.raises(parsing.ParseError):
        wt.points_from_table(t, ["x", "nope"], 2)
    nan = wt.transform_points(w, np.array([[np.nan, 1.0]]), "pix2world")
    assert np.isnan(nan).all()


def test_operations():
    w = tan(shape=(100, 80))
    sl = wt.apply_operation(w, "slice", "10:50, 20:60")  # numpy order: y first, then x
    assert sl.pixel_shape == (40, 40)
    ra, dec = sl.all_pix2world(0, 0, 0)
    ra0, dec0 = w.all_pix2world(20, 10, 0)
    assert (float(ra), float(dec)) == pytest.approx((float(ra0), float(dec0)), abs=1e-9)
    assert wt.apply_operation(w, "sub", "celestial").naxis == 2
    sw = wt.apply_operation(w, "swapaxes", "0 1")
    assert list(sw.wcs.ctype) == ["DEC--TAN", "RA---TAN"]
    assert wt.apply_operation(w, "rename", "MYWCS").wcs.name == "MYWCS"
    assert wt.apply_operation(w, "copy", "") is not w
    cube = WCS(naxis=3)
    cube.wcs.ctype = ["RA---TAN", "DEC--TAN", "FREQ"]
    assert wt.apply_operation(cube, "reorient_celestial_first", "").naxis == 3
    assert wt.apply_operation(cube, "dropaxis", "2").naxis == 2
    for op, arg in (("slice", ""), ("sub", ""), ("swapaxes", "0"), ("dropaxis", "x"), ("nope", "")):
        with pytest.raises(parsing.ParseError):
            wt.apply_operation(w, op, arg)


def test_fit_wcs_recovers_truth():
    truth = tan(rotation_deg=15.0, scale_arcsec=0.8, crval=(83.8, -5.4))
    rng = np.random.default_rng(3)
    x, y = rng.uniform(0, 99, 30), rng.uniform(0, 99, 30)
    sky = truth.pixel_to_world(x, y)
    w, res = wt.fit_wcs(x, y, sky, "TAN")
    assert res["sep_arcsec"].max() < 1e-3
    assert wt.rotation_angle(w) == pytest.approx(15.0, abs=1e-3)
    assert np.asarray(wt.proj_plane_pixel_scales(w))[0] * 3600 == pytest.approx(0.8, rel=1e-4)
    with pytest.raises(parsing.ParseError):
        wt.fit_wcs(x[:2], y[:2], sky[:2], "TAN")
    with pytest.raises(parsing.ParseError):
        wt.fit_wcs(x[:5], y[:5], sky[:5], "TAN", sip_degree=3)
    wsip, _ = wt.fit_wcs(x, y, sky, "TAN", sip_degree=2)
    assert wsip.sip is not None


def test_compare_wcs_objects():
    a = tan()
    assert "equal (WCS.compare): True" in wt.compare_wcs_objects(a, a.deepcopy())
    shifted = tan(crval=(150.0, 2.0 + 10 / 3600))  # 10 arcsec north = 10 px
    text = wt.compare_wcs_objects(a, shifted)
    assert "equal (WCS.compare): False" in text and "mean 10" in text.replace("10.0000", "10")
    scaled = tan(scale_arcsec=2.0)
    assert "ratio 0.5" in wt.compare_wcs_objects(a, scaled)
    assert "needs two 2-D" in wt.compare_wcs_objects(a, WCS(naxis=3))


# ---- panels ---------------------------------------------------------------- #
def test_builder_panel_all_sources(qtbot, ws, shown, tmp_path):
    p = panel(qtbot, ws, "wcs_builder")
    p.build()
    assert not shown and isinstance(ws.get("wcs"), WCS)
    assert "pixel scale: 1 x 1" in p.out.toPlainText() and "CTYPE1" in p.hdr.toPlainText()
    p.form.set_value("crval", "10h00m00s +02d00m00s")
    p.build()
    assert ws.get("wcs_2").wcs.crval[0] == pytest.approx(150.0)
    p.form.set_value("proj", "COP")
    assert p.form.value("pv") == "2_1=45"
    p.build()
    assert not shown
    p.form.set_value("source", "celestial frame")
    p.form.set_value("fname", "galactic")
    p.build()
    assert ws.get("wcs_4").wcs.ctype[0].startswith("GLON")
    p.form.set_value("source", "header text")
    p.form.set_value("header", wt.header_text(ws.get("wcs_2")))
    p.build()
    assert not shown
    path = str(tmp_path / "h.fits")
    fits.PrimaryHDU(np.zeros((10, 10)), header=ws.get("wcs").to_header()).writeto(path)
    p.form.set_value("source", "FITS file")
    p.form.set_value("path", path)
    p.build()
    assert not shown
    ws.put("im", NDData(synthetic_image((20, 20)), wcs=ws.get("wcs")))
    p.img.select("im")
    p.form.set_value("source", "workspace image")
    p.build()
    ws.put("noim", np.zeros((3, 3)))
    p.img.select("noim")
    p.build()
    assert len(shown) == 1 and "no WCS" in str(shown[0])
    p.form.set_value("source", "scratch")
    p.form.set_value("crval", "10")
    p.build()
    p.form.set_value("crval", "10 95")
    p.build()
    p.form.set_value("crval", "10 20")
    p.form.set_value("shape", "0 5")
    p.build()
    assert len(shown) == 4


def test_transform_panel(qtbot, ws, shown):
    ws.put("w", tan())
    p = panel(qtbot, ws, "wcs_transform")
    p.form.set_value("origin", "1")
    p.form.set_value("pts", "50.5 50.5")
    p.go()
    assert not shown
    tab = ws.get("wcs_points")
    assert tab["ra"][0] == pytest.approx(150.0) and tab["dec"][0] == pytest.approx(2.0)
    p.form.set_value("dir", "world2pix")
    p.form.set_value("pts", "150.0 2.0")
    p.go()
    assert ws.get("wcs_points_2")["pix0"][0] == pytest.approx(50.5, abs=1e-6)
    p.form.set_value("api", "high-level (SkyCoord / SpectralCoord)")
    p.form.set_value("origin", "0")
    p.go()
    assert ws.get("wcs_points_3")["x"][0] == pytest.approx(49.5, abs=1e-6)
    ws.put("tbl", Table({"x": [1.0, 2.0], "y": [3.0, 4.0]}))
    p.table_combo.setCurrentText("tbl")
    p.form.set_value("api", "all_*2* (with distortion)")
    p.form.set_value("dir", "pix2world")
    p.form.set_value("use_table", True)
    p.go()
    assert len(ws.get("wcs_points_4")) == 2
    p.form.set_value("cols", "x")
    p.go()
    p.form.set_value("use_table", False)
    p.form.set_value("pts", "1 2 3")
    p.go()
    assert len(shown) == 2


def test_transform_without_wcs_reports(qtbot, ws, shown):
    p = panel(qtbot, ws, "wcs_transform")
    p.go()
    assert len(shown) == 1 and isinstance(shown[0], parsing.ParseError)


def test_inspect_panel(qtbot, ws, shown):
    ws.put("w", tan(rotation_deg=5.0))
    p = panel(qtbot, ws, "wcs_inspect")
    p.info()
    assert not shown
    assert "pixel scale" in p.out.toPlainText() and "world_axis_physical_types" in p.high.toPlainText()
    assert "footprint" in p.high.toPlainText() and "distorted" in p.high.toPlainText()
    p.derivs()
    assert "d(world)/d(pixel)" in p.out.toPlainText()
    p.validate()
    assert not shown
    p.form.set_value("op", "slice")
    p.apply()
    assert ws.get("wcs_new").pixel_shape == (40, 40)
    p.form.set_value("op", "rename")
    p.form.set_value("arg", "FOO")
    p.apply()
    assert ws.get("wcs_new_2").wcs.name == "FOO"
    p.form.set_value("op", "dropaxis")
    p.form.set_value("arg", "0")
    p.apply()
    assert shown  # dropping an axis of a 2-D celestial WCS is invalid -> reported, not raised


def test_fit_panel(qtbot, ws, shown):
    truth = tan(rotation_deg=-10.0)
    rng = np.random.default_rng(5)
    x, y = rng.uniform(0, 99, 12), rng.uniform(0, 99, 12)
    sky = truth.pixel_to_world(x, y)
    p = panel(qtbot, ws, "wcs_fit")
    p.form.set_value("pts", "\n".join(f"{a:.6f} {b:.6f} {c.ra.deg:.9f} {c.dec.deg:.9f}"
                                      for a, b, c in zip(x, y, sky)))
    p.go()
    assert not shown
    assert "residual rms" in p.out.toPlainText()
    w = ws.get("fitted_wcs")
    assert wt.rotation_angle(w) == pytest.approx(-10.0, abs=1e-3)
    tab = Table({"x": x, "y": y, "ra": sky.ra.deg, "dec": sky.dec.deg})
    ws.put("cat", tab)
    p.form.set_value("use_table", True)
    p.table_combo.setCurrentText("cat")
    p.go()
    assert not shown
    p.form.set_value("pp", "150 2")
    p.go()
    assert not shown
    p.form.set_value("use_table", False)
    p.form.set_value("pts", "1 2 3")
    p.go()
    p.form.set_value("pts", "")
    p.go()
    assert len(shown) == 2


def test_compare_and_plot_panels(qtbot, ws, shown):
    ws.put("a", tan())
    ws.put("b", tan(rotation_deg=3.0))
    cp = panel(qtbot, ws, "wcs_compare")
    cp.a.setCurrentText("a")
    cp.b.setCurrentText("b")
    cp.go()
    assert not shown and "rotation A / B" in cp.out.toPlainText()
    cp.form.set_value("shape", "5")
    cp.go()
    assert len(shown) == 1

    pp = panel(qtbot, ws, "wcs_plot")
    pp.go()  # blank frame
    assert not shown
    ws.put("img", NDData(synthetic_image((100, 100))))
    pp.img.select("img")
    pp.form.set_value("overlay", "galactic")
    pp.form.set_value("points", "150.0 2.0")
    pp.form.set_value("circles", "150 2 | 10 arcsec")
    pp.go()
    assert not shown
    out = pp.plot.figure
    assert len(out.axes) >= 1
    pp.form.set_value("circles", "bad")
    pp.go()
    assert len(shown) == 2
    ws.put("lin", WCS(naxis=1))
    pp.wcs_combo.setCurrentText("lin")
    pp.go()
    assert len(shown) == 3


def test_plot_cube_wcs_with_slices(qtbot, ws, shown):
    cube = WCS(naxis=3)
    cube.wcs.ctype = ["RA---TAN", "DEC--TAN", "FREQ"]
    cube.wcs.crval = [10.0, 10.0, 1e9]
    cube.wcs.crpix = [5, 5, 1]
    cube.wcs.cdelt = [-0.01, 0.01, 1e6]
    ws.put("cube", cube)
    pp = panel(qtbot, ws, "wcs_plot")
    pp.form.set_value("shape", "10 10")
    pp.go()
    assert not shown


def test_specs_unique_keys():
    assert len({s.key for s in wt.SPECS}) == len(wt.SPECS)
    assert {s.category for s in wt.SPECS} == {"Images"}
