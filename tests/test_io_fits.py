import numpy as np
import pytest
from astropy import units as u
from astropy.io import fits
from astropy.nddata import NDData
from astropy.table import Table

from astrotools_adv.core.parsing import ParseError
from astrotools_adv.modules import io_fits as iof


@pytest.fixture
def errors(monkeypatch):
    seen = []
    monkeypatch.setattr("astrotools_adv.core.widgets.error_box",
                        lambda parent, exc, detail="": seen.append(exc))
    return seen


@pytest.fixture
def sample(tmp_path):
    img = np.arange(60, dtype=np.float32).reshape(6, 10)
    cube = np.arange(2 * 3 * 4, dtype=np.int16).reshape(2, 3, 4)
    tab = Table({"a": [1, 2, 3], "b": [0.5, 1.5, 2.5]})
    tab["b"].unit = u.m
    hdul = fits.HDUList([fits.PrimaryHDU(img), fits.ImageHDU(cube, name="CUBE"),
                         fits.table_to_hdu(tab)])
    hdul[0].header["OBJECT"] = "test"
    hdul[2].name = "TAB"
    path = tmp_path / "sample.fits"
    hdul.writeto(path, checksum=True)
    return path, img, cube, tab


@pytest.fixture
def panel(qtbot, ws):
    p = iof.FitsPanel(ws)
    qtbot.addWidget(p)
    return p


# ---- pure helpers ---------------------------------------------------------------- #
def test_parse_header_value():
    p = iof.parse_header_value
    assert p("5") == 5 and p("1.5") == 1.5 and p("T") is True and p("false") is False
    assert p("'12'") == "12" and p("abc") == "abc" and p("nan") == "nan"
    with pytest.raises(ParseError):
        p("")
    assert iof.parse_ext("") == {"ext": 0} and iof.parse_ext("2") == {"ext": 2}
    assert iof.parse_ext("SCI") == {"extname": "SCI"}


def test_stretch_and_limits():
    arr = np.linspace(-1, 10, 100).reshape(10, 10)
    assert iof.display_limits(arr) == (-1.0, 10.0)
    a, b = iof.display_limits(arr, lo=10, hi=90)
    assert -1 < a < b < 10
    assert iof.display_limits(arr, vmin="0", vmax="5") == (0.0, 5.0)
    assert iof.display_limits(np.ones((2, 2))) == (0.5, 1.5)
    with pytest.raises(ParseError):
        iof.display_limits(arr, vmin="7", vmax="5")
    with pytest.raises(ParseError):
        iof.display_limits(np.full((2, 2), np.nan))
    for s in iof.STRETCHES:
        assert iof.make_norm(s, 0.0 if s != "log" else 0.1, 10.0, np.abs(arr) + 0.1)
    with pytest.raises(ParseError):
        iof.make_norm("bogus", 0, 1)


def test_hdu_roundtrips(sample, tmp_path):
    path, img, cube, tab = sample
    with fits.open(path) as hdul:
        ov = iof.hdu_overview(hdul)
        assert list(ov["Name"]) == ["PRIMARY", "CUBE", "TAB"]
        assert ov["Dimensions"][2] == "3R x 2C"
        assert np.array_equal(iof.image_array(hdul[1], "1"), cube[1])
        assert np.array_equal(iof.image_array(hdul[1], ""), cube[0])
        with pytest.raises(ParseError):
            iof.image_array(hdul[1], "5")
        with pytest.raises(ParseError):
            iof.image_array(hdul[2])
        assert "mean" in iof.stats_text(img)
        assert "no finite" in iof.stats_text(np.full((2, 2), np.nan))
        cols = iof.columns_table(hdul[2])
        assert list(cols["name"]) == ["a", "b"]
        nd = iof.hdu_to_ndata(hdul[0])
        assert np.array_equal(nd.data, img) and nd.meta["OBJECT"] == "test"
        with pytest.raises(ParseError):
            iof.hdu_to_ndata(hdul[2])
    assert "OBJECT" in iof.header_text(fits.getheader(path), "obj")
    assert iof.header_text(fits.getheader(path), "zzzzzz").startswith("(no")


def test_hdu_from_object_and_compression(tmp_path):
    data = (np.random.default_rng(1).normal(size=(40, 30)) * 100).astype(np.float32)
    ints = np.arange(1200, dtype=np.int32).reshape(30, 40)
    small = (ints % 1000).astype(np.int32)  # PLIO needs 0 <= value < 2**24
    for ctype in iof.COMPRESSIONS:
        # float data is only lossless with the GZIP types; RICE/HCOMPRESS/PLIO get integers
        d = data if ctype.startswith("GZIP") else small
        hdu = iof.hdu_from_object(d, "C", ctype, quantize=0.0)
        path = tmp_path / f"{ctype}.fits"
        fits.HDUList([fits.PrimaryHDU(), hdu]).writeto(path)
        with fits.open(path) as back:
            assert isinstance(back[1], fits.CompImageHDU), ctype
            assert back[1].name == "C" and np.array_equal(back[1].data, d), ctype
    q = iof.hdu_from_object(np.ones((2, 2)) * u.Jy, "Q")
    assert q.header["BUNIT"] == "Jy"
    nd = iof.hdu_from_object(NDData(np.ones((2, 2)), unit=u.m, meta={"FOO": 1}))
    assert nd.header["FOO"] == 1 and nd.header["BUNIT"] == "m"
    assert isinstance(iof.hdu_from_object(Table({"a": [1]}), "T"), fits.BinTableHDU)
    with pytest.raises(ParseError):
        iof.hdu_from_object(Table({"a": [1]}), primary=True)
    with pytest.raises(ParseError):
        iof.hdu_from_object("text")
    with pytest.raises(ParseError):
        iof.hdu_from_object(np.array(["a", "b"]))


def test_save_checksum_and_tamper(sample, tmp_path):
    path, img, _, _ = sample
    ok = iof.verify_checksums(str(path))
    assert set(ok["DATASUM"]) == {"ok"} and set(ok["CHECKSUM"]) == {"ok"}
    raw = bytearray(path.read_bytes())
    raw[2880 + 5] ^= 0xFF  # first data block (the header is one block)
    bad = tmp_path / "tampered.fits"
    bad.write_bytes(bytes(raw))
    res = iof.verify_checksums(str(bad))
    assert res["DATASUM"][0] == "FAILED" and res["CHECKSUM"][0] == "FAILED"
    plain = tmp_path / "nosum.fits"
    fits.PrimaryHDU(img).writeto(plain)
    assert iof.verify_checksums(str(plain))["DATASUM"][0] == "absent"


def test_save_hdulist_safe_overwrite(sample, tmp_path):
    path, img, _, _ = sample
    with fits.open(path, memmap=True) as hdul:
        hdul[0].header["NEWKEY"] = 7
        with pytest.raises(ParseError):
            iof.save_hdulist(hdul, str(path))  # exists, no overwrite
        iof.save_hdulist(hdul, str(path), overwrite=True, checksum=True)
    assert fits.getheader(path)["NEWKEY"] == 7
    assert np.array_equal(fits.getdata(path), img)
    assert not [p for p in tmp_path.iterdir() if p.name.startswith(".atadv")]
    assert set(iof.verify_checksums(str(path))["CHECKSUM"]) == {"ok"}


def test_fitsdiff(sample, tmp_path):
    path, img, _, _ = sample
    other = tmp_path / "other.fits"
    h = fits.open(path)
    h[0].data = img + 1
    h.writeto(other)
    h.close()
    same, rep = iof.fitsdiff_report(str(path), str(path))
    assert same
    same, rep = iof.fitsdiff_report(str(path), str(other))
    assert not same and "differ" in rep.lower()
    same, _ = iof.fitsdiff_report(str(path), str(other), atol=2.0, ignore_keywords="CHECKSUM,DATASUM")
    assert same


def test_open_bad_files(tmp_path):
    garbage = tmp_path / "g.fits"
    garbage.write_bytes(b"not fits at all" * 50)
    with pytest.raises(Exception):
        iof.open_fits(str(garbage), True, True)
    empty = tmp_path / "e.fits"
    empty.write_bytes(b"")
    with pytest.raises(Exception):
        iof.open_fits(str(empty), True, True)
    with pytest.raises(Exception):
        iof.open_fits(str(tmp_path / "missing.fits"), True, True)
    good = tmp_path / "ok.fits"
    fits.PrimaryHDU(np.zeros((50, 50))).writeto(good)
    trunc = tmp_path / "t.fits"
    trunc.write_bytes(good.read_bytes()[:3000])
    with pytest.raises(Exception):
        h, _ = iof.open_fits(str(trunc), False, False)
        np.asarray(h[0].data).sum()


# ---- panel ------------------------------------------------------------------------ #
def open_in_panel(panel, path):
    panel.open_path.setText(str(path))
    panel.open_file(panel.file_sec.form)


def test_panel_open_header_edit_save(panel, sample, tmp_path, errors):
    path, img, cube, tab = sample
    open_in_panel(panel, path)
    assert not errors and panel.hdul is not None and panel.hdu_combo.count() == 3
    assert "OBJECT" in panel.header_view.toPlainText()
    f = panel.header_sec.form
    f.set_value("key", "myKey")
    f.set_value("value", "42")
    f.set_value("comment", "my comment")
    panel.set_card(f)
    assert panel.dirty and "MYKEY" in panel.header_view.toPlainText()
    assert "my comment" in panel.header_view.toPlainText()
    f.set_value("value", "'forty two'")
    panel.set_card(f)
    assert panel.hdul[0].header["MYKEY"] == "forty two"
    f.set_value("value", "history line")
    panel.add_text_card(f, "HISTORY")
    panel.add_text_card(f, "COMMENT")
    assert "HISTORY" in panel.header_view.toPlainText()
    f.set_value("key", "nosuchkey")
    panel.guard(lambda: panel.delete_card(f))
    assert errors
    errors.clear()
    f.set_value("key", "mykey")
    panel.delete_card(f)
    assert "MYKEY" not in panel.hdul[0].header
    f.set_value("key", "KEEP")
    f.set_value("value", "T")
    panel.set_card(f)
    # search filter
    f.set_value("search", "keep")
    panel.show_header()
    assert panel.header_view.toPlainText().count("\n") == 0 and "KEEP" in panel.header_view.toPlainText()
    # save as, reload, compare
    out = tmp_path / "edited.fits"
    s = panel.save_sec.form
    s.set_value("path", str(out))
    s.set_value("checksum", True)
    panel.save_as(s)
    assert not errors and out.exists() and panel.path == str(out) and not panel.dirty
    assert fits.getheader(out)["KEEP"] is True
    assert np.array_equal(fits.getdata(out), img)
    assert set(iof.verify_checksums(str(out))["CHECKSUM"]) == {"ok"}
    panel.guard(lambda: panel.save_as(s))  # exists -> reported
    assert errors and isinstance(errors[-1], ParseError)


def test_panel_write_back_preserves_data(panel, sample, errors):
    path, img, cube, tab = sample
    open_in_panel(panel, path)
    panel.hdul[0].header["BACK"] = "yes"
    panel.write_back(panel.save_sec.form)
    assert not errors
    assert fits.getheader(path)["BACK"] == "yes"
    assert np.array_equal(fits.getdata(path, ext=1), cube)
    assert panel.hdul is not None and panel.hdul[0].header["BACK"] == "yes" and not panel.dirty


def test_panel_image_stats_and_data_transfer(panel, ws, sample, errors):
    path, img, cube, tab = sample
    open_in_panel(panel, path)
    panel.preview(panel.image_sec.form)
    assert not errors and panel.canvas.figure.axes
    for stretch in iof.STRETCHES:
        panel.image_sec.form.set_value("stretch", stretch)
        panel.preview(panel.image_sec.form)
    assert not errors
    panel.hdu_combo.setCurrentIndex(1)
    panel.image_sec.form.set_value("plane", "1")
    panel.pixel_stats(panel.image_sec.form)
    assert "shape      (3, 4)" in panel.log.toPlainText()
    panel.hdu_combo.setCurrentIndex(2)
    panel.guard(lambda: panel.pixel_stats(panel.image_sec.form))  # table HDU -> error
    assert errors
    errors.clear()
    d = panel.data_sec.form
    d.set_value("name", "tab")
    panel.hdu_to_table(d)
    t = ws.get("tab")
    assert list(t["a"]) == [1, 2, 3] and t["b"].unit == u.m
    panel.show_columns()
    assert panel.data_view.model.rowCount() == 2
    panel.hdu_combo.setCurrentIndex(1)
    d.set_value("name", "nd")
    panel.hdu_to_nddata(d)
    assert np.array_equal(ws.get("nd").data, cube)
    d.set_value("name", "arr")
    panel.hdu_to_array(d)
    assert np.array_equal(ws.get("arr"), cube)
    panel.hdu_combo.setCurrentIndex(2)
    panel.guard(lambda: panel.hdu_to_array(d))
    assert errors


def test_panel_build_new_file_from_workspace(panel, ws, tmp_path, errors):
    data = np.arange(100, dtype=np.int32).reshape(10, 10)
    ws.put("img", data)
    ws.put("tbl", Table({"x": [1.0, 2.0]}))
    panel.new_file()
    d = panel.data_sec.form
    panel.obj_combo.setCurrentIndex(panel.obj_combo.findText("img"))
    d.set_value("hduname", "IMG")
    d.set_value("compress", "RICE_1")
    panel.append_hdu(d)
    panel.obj_combo.setCurrentIndex(panel.obj_combo.findText("tbl"))
    d.set_value("hduname", "TBL")
    d.set_value("compress", "none")
    panel.append_hdu(d)
    assert not errors and len(panel.hdul) == 3
    out = tmp_path / "new.fits"
    s = panel.save_sec.form
    s.set_value("path", str(out))
    panel.save_as(s)
    assert not errors
    with fits.open(out) as back:
        assert isinstance(back[1], fits.CompImageHDU) and np.array_equal(back[1].data, data)
        assert list(Table.read(back[2])["x"]) == [1.0, 2.0]
    # replace & delete
    panel.hdu_combo.setCurrentIndex(0)
    panel.obj_combo.setCurrentIndex(panel.obj_combo.findText("img"))
    panel.replace_hdu(d)
    assert isinstance(panel.hdul[0], fits.PrimaryHDU) and np.array_equal(panel.hdul[0].data, data)
    panel.obj_combo.setCurrentIndex(panel.obj_combo.findText("tbl"))
    panel.guard(lambda: panel.replace_hdu(d))  # table as primary -> error
    assert errors
    errors.clear()
    panel.hdu_combo.setCurrentIndex(2)
    panel.delete_hdu()
    assert len(panel.hdul) == 2 and panel.dirty
    panel.close_file()
    assert panel.hdul is None
    panel.guard(lambda: panel.preview(panel.image_sec.form))  # nothing open -> reported
    assert errors


def test_panel_integrity_and_quick_functions(panel, ws, sample, tmp_path, errors):
    path, img, cube, tab = sample
    open_in_panel(panel, path)
    i = panel.int_sec.form
    panel.verify_memory(i)
    assert "passed" in panel.log.toPlainText()
    panel.add_checksum(i)
    assert panel.hdul[0].header["CHECKSUM"]
    panel.verify_disk()
    assert panel.data_view.model.rowCount() == 3
    other = tmp_path / "other.fits"
    fits.PrimaryHDU(img + 5).writeto(other)
    i.set_value("other", str(other))
    panel.diff(i)
    assert panel.log.toPlainText().startswith("DIFFERENT")
    q = panel.quick_sec.form
    q.set_value("key", "OBJECT")
    panel.getval(q)
    assert "'test'" in panel.log.toPlainText()
    q.set_value("key", "QKEY")
    q.set_value("value", "3.5")
    panel.setval(q)
    assert fits.getheader(path)["QKEY"] == 3.5 and panel.hdul[0].header["QKEY"] == 3.5
    q.set_value("ext", "TAB")
    q.set_value("name", "got")
    panel.getdata(q)
    assert isinstance(ws.get("got"), Table)
    q.set_value("ext", "0")
    panel.getdata(q)
    assert np.array_equal(ws.get("got"), img)
    panel.getheader(q)
    assert "QKEY" in panel.header_view.toPlainText()
    assert not errors
    q.set_value("ext", "99")
    panel.getval(q)
    assert errors


def test_panel_garbage_file_does_not_crash(panel, tmp_path, errors):
    g = tmp_path / "g.fits"
    g.write_bytes(b"\x00\x01garbage" * 200)
    open_in_panel(panel, g)
    assert errors and panel.hdul is None
