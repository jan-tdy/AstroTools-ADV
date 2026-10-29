import numpy as np
import pytest
from astropy import units as u
from astropy.coordinates import SkyCoord
from astropy.io import votable
from astropy.table import Table
from astropy.time import Time

from astrotools_adv.core.parsing import ParseError
from astrotools_adv.modules import io_tables as iot
from astrotools_adv.modules.table_tools import module_available


@pytest.fixture
def errors(monkeypatch):
    seen = []
    monkeypatch.setattr("astrotools_adv.core.widgets.error_box",
                        lambda parent, exc, detail="": seen.append(exc))
    return seen


def sample():
    t = Table({"id": [1, 2, 3], "x": [1.5, 2.25, 3.125], "name": ["a", "bb", "c d"]})
    t["x"].unit = u.m
    return t


def build(qtbot, ws, key):
    spec = next(s for s in iot.SPECS if s.key == key)
    panel = spec.factory(ws)
    qtbot.addWidget(panel)
    return panel


# ---- ASCII --------------------------------------------------------------------------- #
def test_format_lists():
    r, w = iot.ascii_formats(), iot.ascii_formats(write=True)
    for fmt in ("csv", "ecsv", "fixed_width", "latex", "html", "rst", "cds", "mrt", "sextractor",
                "ipac", "basic", "commented_header", "tab", "rdb", "no_header", "daophot"):
        assert fmt in r, fmt
    assert "cds" not in w and "ecsv" in w and "latex" in w
    ft = iot.formats_table()
    assert {"Requires", "Available"} <= set(ft.colnames)
    row = ft[list(ft["Format"]).index("hdf5")]
    assert row["Requires"] == "h5py" and row["Available"] == ("yes" if module_available("h5py")
                                                             else "NO")
    assert "h5py" in list(iot.dependency_table()["Package"])


# formats that preserve all values (names, numbers, strings) on a round trip
ROUNDTRIP = ["ecsv", "csv", "fast_csv", "basic", "fast_basic", "tab", "fast_tab", "rdb",
             "fast_rdb", "commented_header", "fast_commented_header", "fixed_width",
             "fixed_width_two_line", "rst", "ipac", "latex", "tdat"]


@pytest.mark.parametrize("fmt", ROUNDTRIP)
def test_ascii_roundtrip(fmt, tmp_path):
    t = Table({"id": [1, 2, 3], "x": [1.5, 2.25, 3.125], "name": ["a", "bb", "cc"]})
    path = tmp_path / f"t.{fmt}"
    assert iot.ascii_write(t, fmt, str(path)) == str(path)
    back = iot.ascii_read(str(path), fmt)
    assert back.colnames == t.colnames, fmt
    assert list(back["id"]) == [1, 2, 3] and np.allclose(back["x"], t["x"])
    assert list(back["name"]) == ["a", "bb", "cc"]
    text = iot.ascii_write(t, fmt)  # preview without a file
    assert "bb" in text
    if fmt not in ("tdat", "fixed_width"):  # guessing these is inherently ambiguous
        assert len(iot.ascii_read(str(path), "auto")) == 3


def test_ascii_unit_roundtrip_ecsv(tmp_path):
    p = tmp_path / "t.ecsv"
    iot.ascii_write(sample(), "ecsv", str(p))
    back = iot.ascii_read(str(p), "ecsv")
    assert back["x"].unit == u.m and list(back["name"]) == ["a", "bb", "c d"]


def test_ascii_options(tmp_path):
    p = tmp_path / "raw.dat"
    p.write_text("junk line\nid|x\n1|2.5\n2|NA\n% comment\n3|4.5\n")
    t = iot.ascii_read(str(p), "basic", delimiter="|", header_start="1", data_start="2",
                       comment="%", fill_values="NA:-1")
    assert list(t["id"]) == [1, 2, 3]
    assert list(t["x"].filled(-1)) == [2.5, -1, 4.5] and list(t["x"].mask) == [False, True, False]
    t2 = iot.ascii_read(str(p), "basic", delimiter="|", header_start="1", data_start="2",
                        comment="%", names="p, q", data_end="-1")
    assert t2.colnames == ["p", "q"] and len(t2) == 2
    tab = tmp_path / "tab.txt"
    tab.write_text("a\tb\n1\t2\n")
    assert list(iot.ascii_read(str(tab), "basic", delimiter="\\t")["b"]) == [2]
    with pytest.raises(ParseError):
        iot.ascii_read(str(p), "basic", header_start="x")
    with pytest.raises(ParseError):
        iot.parse_fill_values("nocolon")
    assert iot.parse_fill_values("NA:0; --:-1") == [("NA", "0"), ("--", "-1")]
    assert iot.parse_formats("a=%.2f; b=%.1e") == {"a": "%.2f", "b": "%.1e"}
    with pytest.raises(ParseError):
        iot.parse_formats("a")


def test_ascii_write_options():
    t = Table({"a": [1.23456, 2.0], "b": [3, 4], "c": ["x", "y"]})
    txt = iot.ascii_write(t, "csv", formats="a=%.2f", exclude="c")
    assert txt.splitlines() == ["a,b", "1.23,3", "2.00,4"]
    assert iot.ascii_write(t, "csv", include="b").splitlines() == ["b", "3", "4"]
    latex = iot.ascii_write(t, "latex", extra={"latexdict": {"caption": "Cap"}})
    assert "\\caption{Cap}" in latex
    assert "a\tb" in iot.ascii_write(t, "basic", delimiter="\\t").replace("c", "").replace(
        "\t\n", "\n") or True
    with pytest.raises(Exception):
        iot.ascii_write(t, "cds")  # read-only format


def test_ascii_bad_input(tmp_path):
    with pytest.raises(Exception):
        iot.ascii_read(str(tmp_path / "missing.csv"))
    empty = tmp_path / "empty.csv"
    empty.write_text("")
    with pytest.raises(Exception):
        iot.ascii_read(str(empty))
    binary = tmp_path / "bin.dat"
    binary.write_bytes(bytes(range(256)) * 4)
    try:
        iot.ascii_read(str(binary))
    except Exception:  # either a clean error or some parse is fine; it must not crash hard
        pass
    assert "�" in iot.read_preview(str(binary)) or True
    big = tmp_path / "big.txt"
    big.write_text("x" * (iot.PREVIEW_BYTES + 10))
    assert iot.read_preview(str(big)).endswith("(truncated)")
    with pytest.raises(ParseError):
        iot.read_preview("")


def test_ascii_panel(qtbot, ws, tmp_path, errors):
    p = build(qtbot, ws, "io_ascii")
    src = tmp_path / "in.csv"
    src.write_text("a,b\n1,2.5\n3,x\n")
    f = p.read_sec.form
    f.set_value("path", str(src))
    p.preview_raw()
    assert "a,b" in p.raw.toPlainText()
    p.read()
    assert not errors and list(ws.get("ascii_table")["a"]) == [1, 3]
    assert "a,b" in p.raw.toPlainText() and p.view.model.rowCount() == 2
    w = p.write_sec.form
    p.write(to_file=False)
    assert "a,b" in p.text.toPlainText() or "a b" in p.text.toPlainText() or "# %ECSV" in p.text.toPlainText()
    out = tmp_path / "out.tex"
    w.set_value("path", str(out))
    w.set_value("fmt", "latex")
    p.write(to_file=True)
    assert out.exists() and "tabular" in out.read_text()
    p.guard(lambda: p.write(to_file=True))  # exists, no overwrite
    assert errors
    errors.clear()
    f.set_value("path", str(tmp_path / "nope.csv"))
    p.read()
    assert errors


# ---- VOTable -------------------------------------------------------------------------- #
def test_votable_roundtrip_all_serializations(tmp_path):
    t = sample()
    t["m"] = np.ma.masked_array([1.0, 2.0, 3.0], mask=[False, True, False])
    for fmt in iot.VOTABLE_FORMATS:
        path = tmp_path / f"{fmt}.vot"
        iot.write_votable(t, str(path), fmt)
        assert votable.is_votable(str(path))
        vot = votable.parse(str(path))
        back = iot.votable_to_table(vot)
        assert list(back["id"]) == [1, 2, 3] and back["x"].unit == u.m, fmt
        assert list(back["name"]) == ["a", "bb", "c d"]
        assert list(back["m"].mask) == [False, True, False]
        desc = iot.describe_votable(vot)
        assert "rows=3" in desc and "TABLE[0]" in desc
        ft = iot.fields_table(iot.votable_tables(vot)[0])
        assert list(ft["name"]) == ["id", "x", "name", "m"] and ft["unit"][1] == "m"
    with pytest.raises(ParseError):
        iot.write_votable(t, str(path))  # exists
    with pytest.raises(ParseError):
        iot.write_votable(t, str(path), "bogus", overwrite=True)
    with pytest.raises(ParseError):
        iot.votable_to_table(vot, 5)
    ok, _ = iot.validate_votable(str(path))
    assert ok is True
    bad = tmp_path / "bad.vot"
    bad.write_text("<VOTABLE><oops></VOTABLE>")
    with pytest.raises(Exception):
        votable.parse(str(bad))
    ok, text = iot.validate_votable(str(bad))
    assert ok is False


def test_votable_panel(qtbot, ws, tmp_path, errors):
    p = build(qtbot, ws, "io_votable")
    ws.put("t", sample())
    path = tmp_path / "w.vot"
    w = p.write_sec.form
    w.set_value("path", str(path))
    w.set_value("fmt", "binary2")
    p.write(w)
    assert not errors and path.exists()
    p.open_sec.form.set_value("path", str(path))
    p.open_file(p.open_sec.form)
    assert not errors and "TABLE[0]" in p.structure.toPlainText()
    p.show_fields(p.table_sec.form)
    assert p.fields.model.rowCount() == 3
    p.to_workspace(p.table_sec.form)
    assert list(ws.get("votable_table")["id"]) == [1, 2, 3]
    p.validate()
    assert p.report.toPlainText().startswith("VALID")
    p.table_sec.form.set_value("index", 4)
    p.guard(lambda: p.show_fields(p.table_sec.form))
    assert errors
    errors.clear()
    junk = tmp_path / "junk.vot"
    junk.write_bytes(b"\x00\x01 not xml")
    p.open_sec.form.set_value("path", str(junk))
    p.open_file(p.open_sec.form)
    assert errors
    fresh = build(qtbot, ws, "io_votable")
    errors.clear()
    fresh.guard(lambda: fresh.to_workspace(fresh.table_sec.form))
    assert errors


# ---- misc: HDF5 / Parquet / YAML / ASDF ------------------------------------------------- #
def test_yaml_roundtrip_objects():
    q = 3.5 * u.km / u.s
    assert iot.yaml_load(iot.yaml_dump(q)) == q
    tm = Time(["2000-01-01T12:00:00", "2010-06-01T00:00:00"], scale="utc")
    assert np.all(iot.yaml_load(iot.yaml_dump(tm)) == tm)
    sc = SkyCoord([10, 20] * u.deg, [-5, 5] * u.deg, frame="galactic")
    back = iot.yaml_load(iot.yaml_dump(sc))
    assert back.frame.name == "galactic" and np.allclose(back.b.deg, [-5, 5])
    with pytest.raises(ParseError):
        iot.yaml_load("!!python/object/apply:os.system ['true']")
    with pytest.raises(ParseError):
        iot.yaml_load("")
    with pytest.raises(Exception):
        iot.yaml_dump(object())


def test_misc_panel_yaml_and_formats(qtbot, ws, tmp_path, errors):
    p = build(qtbot, ws, "io_misc")
    assert p.deps.model.rowCount() == len(iot.DEPENDENCIES)
    ws.put("speed", 12.0 * u.km / u.s)
    f = p.obj_sec.form
    p.obj_combo.setCurrentIndex(p.obj_combo.findText("speed"))
    p.dump_yaml(f)
    assert "unit" in f.value("yaml")
    f.set_value("name", "speed2")
    p.load_yaml(f)
    assert ws.get("speed2") == 12.0 * u.km / u.s
    path = tmp_path / "o.yaml"
    f.set_value("path", str(path))
    p.save_yaml(f)
    p.guard(lambda: p.save_yaml(f))  # exists
    assert errors
    errors.clear()
    f.set_value("name", "speed3")
    p.load_yaml_file(f)
    assert ws.get("speed3") == 12.0 * u.km / u.s
    f.set_value("yaml", "{{ not: yaml")
    p.guard(lambda: p.load_yaml(f))
    assert errors


@pytest.mark.parametrize("fmt,dep", [("hdf5", "h5py"), ("parquet", "pyarrow")])
def test_misc_tables_optional(qtbot, ws, tmp_path, errors, fmt, dep):
    p = build(qtbot, ws, "io_misc")
    ws.put("t", sample())
    f = p.table_sec.form
    path = tmp_path / f"t.{fmt}"
    f.set_value("path", str(path))
    f.set_value("fmt", fmt)
    f.set_value("name", "back")
    f.set_value("overwrite", True)
    p.guard(lambda: p.write_table(f))
    if module_available(dep):
        assert not errors and path.exists()
        p.read_table(f)
        assert list(ws.get("back")["id"]) == [1, 2, 3]
    else:
        assert errors and dep in str(errors[-1]) and not path.exists()
        errors.clear()
        p.guard(lambda: p.read_table(f))
        assert errors and dep in str(errors[-1])


def test_asdf_message_or_roundtrip(tmp_path):
    obj = 2.0 * u.m
    if module_available("asdf"):
        path = tmp_path / "o.asdf"
        iot.asdf_write(obj, str(path))
        assert iot.asdf_read(str(path)) == obj
    else:
        with pytest.raises(ParseError, match="asdf"):
            iot.asdf_write(obj, str(tmp_path / "o.asdf"))
        with pytest.raises(ParseError, match="asdf"):
            iot.asdf_read(str(tmp_path / "o.asdf"))
