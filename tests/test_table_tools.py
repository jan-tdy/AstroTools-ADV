import numpy as np
import pytest
from astropy import units as u
from astropy.coordinates import SkyCoord
from astropy.table import MaskedColumn, QTable, Table
from astropy.time import Time

from astrotools_adv.core.parsing import ParseError
from astrotools_adv.modules import table_tools as tt


@pytest.fixture
def errors(monkeypatch):
    """Collect errors instead of opening modal dialogs."""
    seen = []
    monkeypatch.setattr("astrotools_adv.core.widgets.error_box",
                        lambda parent, exc, detail="": seen.append(exc))
    return seen


def make():
    t = Table({"id": [1, 2, 3, 4], "x": [1.0, 2.0, 3.0, 4.0], "name": ["a", "b", "a", "b"]})
    t["x"].unit = u.m
    return t


# ---- pure operations ---------------------------------------------------------- #
def test_add_column_expression_units():
    t = tt.op_add_column(make(), "y", "x * 2")
    assert list(t["y"]) == [2, 4, 6, 8] and t["y"].unit == u.m
    t2 = tt.op_add_column(make(), "km", "x", "km")
    assert t2["km"].unit == u.km and t2["km"][0] == pytest.approx(0.001)
    t3 = tt.op_add_column(make(), "one", "1")
    assert list(t3["one"]) == [1] * 4
    t4 = tt.op_add_column(make(), "id", "id + 10")  # replace
    assert list(t4["id"]) == [11, 12, 13, 14] and t4.colnames == make().colnames
    with pytest.raises(ParseError):
        tt.op_add_column(make(), "z", "nosuch + 1")
    with pytest.raises(ParseError):
        tt.op_add_column(make(), "z", "np.arange(3)")  # wrong length


def test_string_columns_and_odd_names():
    t = make()
    t["odd name"] = [5, 6, 7, 8]
    assert list(tt.op_filter(t, "name == 'a'")["id"]) == [1, 3]
    assert list(tt.op_filter(t, "c['odd name'] > 6")["id"]) == [3, 4]
    with pytest.raises(ParseError):
        tt.op_filter(t, "id")  # not boolean


def test_rename_remove_meta_convert():
    t = tt.op_rename(make(), "id", "ident")
    assert "ident" in t.colnames
    with pytest.raises(ParseError):
        tt.op_rename(make(), "id", "x")
    with pytest.raises(ParseError):
        tt.op_rename(make(), "nope", "q")
    assert tt.op_remove(make(), "id, name").colnames == ["x"]
    with pytest.raises(ParseError):
        tt.op_remove(make(), "id,x,name")
    m = tt.op_set_meta(make(), "id", "s", "%.2f", "ident")
    assert m["id"].unit == u.s and m["id"].description == "ident"
    assert m["id"].pformat()[0].strip() == "id"
    with pytest.raises(ParseError):
        tt.op_set_meta(make(), "id", fmt="%.q")
    assert tt.op_set_meta(m, "id", unit="-")["id"].unit is None
    c = tt.op_convert_unit(make(), "x", "cm")
    assert list(c["x"]) == [100, 200, 300, 400] and c["x"].unit == u.cm
    with pytest.raises(ParseError):
        tt.op_convert_unit(make(), "x", "s")
    with pytest.raises(ParseError):
        tt.op_convert_unit(make(), "id", "s")


def test_mask_unmask_fill():
    t = tt.op_mask(make(), "x", "id > 2")
    assert isinstance(t["x"], MaskedColumn) and list(t["x"].mask) == [False, False, True, True]
    assert t["x"].unit == u.m
    f = tt.op_fill(t, "x", "-1")
    assert list(f["x"]) == [1, 2, -1, -1]
    un = tt.op_unmask(t, "x")
    assert not isinstance(un["x"], MaskedColumn) and un["x"].unit == u.m
    with pytest.raises(ParseError):
        tt.op_fill(make(), "x", "0")
    # numeric ops on masked data still evaluate
    assert len(tt.op_add_column(t, "z", "x + 1 * u.m")) == 4


def test_sort_filter_unique_lookup():
    t = make()
    assert list(tt.op_sort(t, "x", reverse=True)["id"]) == [4, 3, 2, 1]
    assert list(tt.op_filter(t, "(id > 1) & (x < 4 * u.m)")["id"]) == [2, 3]
    assert list(tt.op_unique(t, "name")["name"]) == ["a", "b"]
    assert list(tt.op_unique(t, "name", "last")["id"]) == [3, 4]
    assert list(tt.op_filter(t, "not (id > 2) or name == 'b' and id == 4")["id"]) == [1, 2, 4]
    assert list(tt.op_filter(t, "~(id == 1)")["id"]) == [2, 3, 4]
    assert list(tt.op_filter(t, "1 < id < 4")["id"]) == [2, 3]
    assert list(tt.op_lookup(t, "name", "a")["id"]) == [1, 3]
    assert list(tt.op_lookup(t, "id", "2")["name"]) == ["b"]
    with pytest.raises(ParseError):
        tt.op_lookup(t, "nope", "1")


def test_qtable_and_mixins():
    q = tt.op_to_qtable(make(), True)
    assert isinstance(q, QTable) and isinstance(q["x"], u.Quantity)
    assert list(tt.op_filter(q, "x > 2 * u.m")["id"]) == [3, 4]
    assert not isinstance(tt.op_to_qtable(q, False), QTable)
    c = Table({"ra": [10.0, 20.0], "dec": [-5.0, 5.0]})
    sc = tt.op_skycoord_column(c, "co", "ra", "dec")
    assert isinstance(sc["co"], SkyCoord) and sc["co"][1].dec.deg == 5.0
    disp = tt.display_table(sc)
    assert disp["co"][0].startswith("10")
    tc = tt.op_time_column(Table({"jd": [2451545.0, 2451546.0]}), "t", "jd", "jd", "utc")
    assert isinstance(tc["t"], Time) and tc["t"][1].jd == 2451546.0
    assert tt.display_table(tc)["t"][0].startswith("2000-01-01 12:00")
    with pytest.raises(ParseError):
        tt.op_time_column(Table({"s": ["not a time"]}), "t", "s", "iso", "utc")


def test_group_aggregate_join_stack_setdiff():
    t = make()
    g = tt.op_group_aggregate(t, "name", "sum")
    assert list(g["name"]) == ["a", "b"] and list(g["id"]) == [4, 6]
    assert list(tt.op_group_aggregate(t, "name", "count")["id"]) == [2, 2]
    assert list(tt.op_group_sizes(t, "name")["n_rows"]) == [2, 2]
    left = Table({"k": [1, 2, 3], "l": [10, 20, 30]})
    right = Table({"k": [2, 3, 4], "r": [200, 300, 400]})
    assert list(tt.op_join(left, right, "k", "inner")["k"]) == [2, 3]
    assert list(tt.op_join(left, right, "", "outer")["k"]) == [1, 2, 3, 4]
    assert list(tt.op_join(left, right, "k", "left")["r"].mask) == [True, False, False]
    assert len(tt.op_join(Table({"a": [1, 2]}), Table({"b": [3, 4]}), "", "cartesian")) == 4
    clash = tt.op_join(Table({"k": [1], "v": [1]}), Table({"k": [1], "v": [2]}), "k")
    assert clash.colnames == ["k", "v_1", "v_2"]
    with pytest.raises(ParseError):
        tt.op_join(Table({"a": [1]}), Table({"b": [1]}))
    v = tt.op_stack([left, left], "vstack")
    assert len(v) == 6
    h = tt.op_stack([left, Table({"z": [7, 8, 9]})], "hstack")
    assert h.colnames == ["k", "l", "z"]
    d = tt.op_stack([Table({"a": [1, 2]}), Table({"a": [3, 4]})], "dstack")
    assert d["a"].shape == (2, 2)
    with pytest.raises(ParseError):
        tt.op_stack([left], "vstack")
    assert list(tt.op_setdiff(left, right, "k")["k"]) == [1]


def test_describe_info_row_and_kwargs():
    d = tt.describe_table(make())
    assert d.colnames == ["statistic", "id", "x"] and d["x"][1] == pytest.approx(2.5)
    assert "mean" in tt.info_text(make(), "stats")
    assert "= 2" in tt.row_text(make(), 1)
    with pytest.raises(ParseError):
        tt.row_text(make(), 9)
    assert tt.parse_kwargs("hdu=2; delimiter=','; name=GAIA") == {
        "hdu": 2, "delimiter": ",", "name": "GAIA"}
    with pytest.raises(ParseError):
        tt.parse_kwargs("oops")


def test_read_table_roundtrip_and_failures(tmp_path):
    t = make()
    for ext, kw in [("ecsv", {}), ("fits", {}), ("csv", {}), ("vot", {"format": "votable"})]:
        p = tmp_path / f"t.{ext}"
        t.write(p, overwrite=True, **kw)
        back = tt.read_table(str(p), kw.get("format"))
        assert len(back) == 4 and list(back["id"]) == [1, 2, 3, 4], ext
    assert tt.read_table(str(tmp_path / "t.ecsv"))["x"].unit == u.m
    plain = tmp_path / "plain.dat"
    plain.write_text("a b\n1 2\n3 4\n")
    assert list(tt.read_table(str(plain))["b"]) == [2, 4]  # unknown ext -> ascii guess
    with pytest.raises(Exception):
        tt.read_table(str(tmp_path / "missing.fits"))
    bad = tmp_path / "bad.fits"
    bad.write_bytes(b"garbage" * 100)
    with pytest.raises(Exception):
        tt.read_table(str(bad))
    trunc = tmp_path / "trunc.fits"
    trunc.write_bytes((tmp_path / "t.fits").read_bytes()[:3000])
    with pytest.raises(Exception):
        tt.read_table(str(trunc), "fits")
    with pytest.raises(ParseError):
        tt.read_table("")
    if not tt.module_available("h5py"):
        with pytest.raises(ParseError, match="h5py"):
            tt.read_table(str(plain), "hdf5")


def test_format_lists():
    r, w = tt.table_formats(), tt.table_formats(write=True)
    assert "ascii.csv" in r and "fits" in r and "votable" in r and "ascii.cds" in r
    assert "ascii.cds" not in w and "ascii.ecsv" in w
    assert "csv" not in r  # deprecated aliases hidden


# ---- panels ------------------------------------------------------------------- #
def build(qtbot, ws, key):
    spec = next(s for s in tt.SPECS if s.key == key)
    panel = spec.factory(ws)
    qtbot.addWidget(panel)
    return panel


def test_manager_open_save_paste(qtbot, ws, tmp_path, errors):
    p = build(qtbot, ws, "table_manager")
    src = tmp_path / "in.csv"
    src.write_text("a,b\n1,2.5\n3,4.5\n")
    sec = p.open_sec
    sec.form.set_value("path", str(src))
    sec.form.set_value("name", "t")
    p.open_file(sec.form)
    assert not errors and list(ws.get("t")["b"]) == [2.5, 4.5]
    assert "2 rows" in p.view.summary.text()
    # paste
    p.create_text(p.findChildren(type(sec))[1].form)
    assert list(ws.get("pasted")["a"]) == [1, 3]
    # inspect
    p.show_info("stats")
    assert "mean" in p.info.toPlainText()
    p.show_describe()
    assert p.view.model.rowCount() == 8
    p.show_pformat()
    assert "a" in p.info.toPlainText()
    p.show_meta()
    # save
    out = tmp_path / "out.ecsv"
    save = [s for s in p.findChildren(type(sec)) if s.title().startswith("Save")][0]
    save.form.set_value("path", str(out))
    save.form.set_value("fmt", "ascii.ecsv")
    p.save_file(save.form)
    assert out.exists()
    p.save_file(save.form)  # exists, no overwrite -> error reported, not raised
    assert errors
    errors.clear()
    save.form.set_value("overwrite", True)
    p.save_file(save.form)
    assert not errors
    # missing file -> error dialog path
    sec.form.set_value("path", str(tmp_path / "nope.csv"))
    p.open_file(sec.form)
    assert errors
    # pandas
    pd_sec = [s for s in p.findChildren(type(sec)) if s.title() == "pandas"][0]
    p.to_pandas(pd_sec.form)
    pd_sec.form.set_value("name", "dataframe")
    p.from_pandas(pd_sec.form)
    assert isinstance(ws.get("dataframe_table"), Table)


def test_editor_panel_flow(qtbot, ws, errors):
    ws.put("t", make())
    p = build(qtbot, ws, "table_edit")
    secs = {s.title(): s for s in p.findChildren(type(p.findChild(tt.Section)))}
    s_new = secs["New / replaced column"]
    s_new.form.set_value("name", "dbl")
    s_new.form.set_value("expr", "id * 2")
    p.add_column(s_new.form)
    assert not errors and list(ws.get("t")["dbl"]) == [2, 4, 6, 8]
    p.form.set_value("out", "filtered")
    s_rows = secs["Rows"]
    s_rows.form.set_value("expr", "dbl > 4")
    p.filter(s_rows.form)
    assert list(ws.get("filtered")["id"]) == [3, 4]
    assert p.src.currentText() == "filtered"
    p.form.set_value("out", "")
    s_rows.form.set_value("expr", "bogus >")
    p.filter(s_rows.form)
    assert errors and isinstance(errors[-1], ParseError)
    errors.clear()
    p.toggle_qtable()
    assert isinstance(ws.get("filtered"), QTable)


def test_combiner_and_plot_panels(qtbot, ws, errors, tmp_path):
    ws.put("a", Table({"k": [1, 2], "u": [1.0, 2.0]}))
    ws.put("b", Table({"k": [2, 3], "w": [5.0, 6.0]}))
    p = build(qtbot, ws, "table_combine")
    p.src.setCurrentIndex(p.src.findText("a"))
    p.right.setCurrentIndex(p.right.findText("b"))
    jsec = [s for s in p.findChildren(tt.Section) if s.title().startswith("Join")][0]
    jsec.form.set_value("keys", "k")
    jsec.form.set_value("how", "outer")
    p.join(jsec.form)
    assert not errors and list(ws.get("a_b_outer")["k"]) == [1, 2, 3]
    ssec = [s for s in p.findChildren(tt.Section) if s.title().startswith("Stack")][0]
    p.picker.selectAll()
    p.stack(ssec.form, "vstack")
    assert len(ws.get("vstack_result")) >= 4
    p.picker.clearSelection()
    p.stack(ssec.form, "vstack")
    assert errors
    errors.clear()

    pl = build(qtbot, ws, "table_plot")
    pl.src.setCurrentIndex(pl.src.findText("a"))
    pl.y.setCurrentIndex(pl.y.findText("u"))
    pl.plot()
    assert pl.canvas.figure.axes and not errors
    pl.form.set_value("kind", "hist")
    pl.plot()
    pl.form.set_value("kind", "errorbar")
    pl.guard(pl.plot)  # no error column -> reported, not raised
    assert errors
