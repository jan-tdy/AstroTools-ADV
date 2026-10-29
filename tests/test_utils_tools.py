import os
import zipfile

import pytest
from astropy import config
from astropy.table import Table
from astropy.utils import data, iers

from astrotools_adv.core.parsing import ParseError
from astrotools_adv.modules import utils_tools as ut


@pytest.fixture
def errors(monkeypatch):
    shown = []
    monkeypatch.setattr("astrotools_adv.core.widgets.error_box",
                        lambda parent, exc, detail="": shown.append(exc))
    return shown


@pytest.fixture
def tmp_cache(tmp_path):
    cache = tmp_path / "cache"
    cfg = tmp_path / "config"
    cache.mkdir()
    cfg.mkdir()
    with config.set_temp_cache(str(cache)), config.set_temp_config(str(cfg)):
        yield cache


@pytest.fixture
def iers_conf_restored():
    names = ut.IERS_CONFIG_ITEMS
    saved = {n: getattr(iers.conf, n) for n in names}
    yield
    for n, v in saved.items():
        setattr(iers.conf, n, v)


# ---- IERS ------------------------------------------------------------------ #
def test_leap_second_table_offline():
    t = ut.leap_second_table()
    assert len(t) > 25 and t["tai_utc"][-1] == 37.0 and "expires" in t.meta


def test_iers_panel_info_lookup_leap(qtbot, ws, iers_conf_restored, errors):
    p = ut.IersPanel(ws)
    qtbot.addWidget(p)
    text = p.info.toPlainText()
    assert "IERS-B (bundled)" in text and "IERS-A (bundled)" in text and "auto_download" in text

    p.form.set_value("time", "2020-06-01 00:00:00")
    p.lookup()
    out = p.info.toPlainText()
    assert "UT1-UTC" in out and "inside the table" in out
    # an actual value check against astropy itself
    from astropy.time import Time
    expected = iers.IERS_B.open().ut1_utc(Time("2020-06-01").jd1, Time("2020-06-01").jd2)
    assert f"{expected.to('s').value:.6f}" in out

    p.form.set_value("time", "garbage")
    p.lookup()
    assert errors and isinstance(errors[-1], ParseError)

    p.show_leap_seconds()
    assert p.table_view.model.rowCount() > 25


def test_iers_config_roundtrip(qtbot, ws, iers_conf_restored, errors):
    p = ut.IersPanel(ws)
    qtbot.addWidget(p)
    orig = (iers.conf.auto_download, iers.conf.iers_degraded_accuracy, iers.conf.remote_timeout)
    p.form.set_value("auto_download", False)
    p.form.set_value("degraded", "warn")
    p.form.set_value("remote_timeout", "3.5")
    p.apply_config()
    assert iers.conf.auto_download is False and iers.conf.iers_degraded_accuracy == "warn"
    assert iers.conf.remote_timeout == 3.5
    assert "auto_download = False" in p.info.toPlainText()
    p.form.set_value("remote_timeout", "abc")
    p.apply_config()
    assert errors and iers.conf.remote_timeout == 3.5  # failed apply changed nothing more
    p.reset_config()
    assert (iers.conf.auto_download, iers.conf.iers_degraded_accuracy,
            iers.conf.remote_timeout) == (True, "error", 10.0)
    assert orig[0] in (True, False)


def test_earth_orientation_table_select_and_restore(qtbot, ws):
    p = ut.IersPanel(ws)
    qtbot.addWidget(p)
    before = iers.earth_orientation_table._value
    p.form.set_value("eop", "IERS-A (bundled)")
    p.select_table()
    assert isinstance(iers.earth_orientation_table._value, iers.IERS_A)
    p.form.set_value("eop", "IERS-B (bundled)")
    p.select_table()
    assert isinstance(iers.earth_orientation_table._value, iers.IERS_B)
    p.restore_table()
    assert iers.earth_orientation_table._value is before


def test_iers_update_is_offline_safe(qtbot, ws, monkeypatch, errors):
    p = ut.IersPanel(ws)
    qtbot.addWidget(p)

    def no_network(*a, **k):
        raise OSError("network unreachable")

    monkeypatch.setattr(iers.IERS_Auto, "open", staticmethod(no_network))
    monkeypatch.setattr(p, "confirm", lambda text: False)
    p.update_online()  # declined: nothing happens
    assert not errors
    monkeypatch.setattr(p, "confirm", lambda text: True)
    p.update_online()
    assert errors and isinstance(errors[-1], OSError)


# ---- data cache -------------------------------------------------------------- #
def test_cache_roundtrip(qtbot, ws, tmp_cache, tmp_path, errors, monkeypatch):
    p = ut.DataCachePanel(ws)
    qtbot.addWidget(p)
    assert p.listing.model.rowCount() == 0 and "Entries: 0" in p.info.toPlainText()

    src = tmp_path / "payload.txt"
    src.write_text("hello cache")
    p.form.set_value("url", "http://example.invalid/payload.txt")
    p.import_file(str(src))
    assert p.listing.model.rowCount() == 1
    assert data.is_url_in_cache("http://example.invalid/payload.txt")
    table = ut.cache_table()
    assert table["size"][0] == len("hello cache") and table["url"][0].endswith("payload.txt")

    p.check_url()
    assert "in cache: True" in p.info.toPlainText()
    p.verify()
    assert "verified" in p.info.toPlainText()

    zpath = str(tmp_path / "export.zip")
    p.export_cache(zpath)
    assert zipfile.is_zipfile(zpath)

    p.clear_entry()
    assert p.listing.model.rowCount() == 0
    p.import_zip(zpath)
    assert p.listing.model.rowCount() == 1

    monkeypatch.setattr(p, "confirm", lambda t: False)
    p.clear_all()
    assert p.listing.model.rowCount() == 1  # declined
    monkeypatch.setattr(p, "confirm", lambda t: True)
    p.clear_all()
    assert p.listing.model.rowCount() == 0
    assert not errors


def test_cache_download_offline_reports_error(qtbot, ws, tmp_cache, errors):
    p = ut.DataCachePanel(ws)
    qtbot.addWidget(p)
    p.form.set_value("url", "http://127.0.0.1:9/nothing.fits")  # closed port
    p.form.set_value("timeout", 2.0)
    p.download()
    assert errors  # reported, not raised
    p.form.set_value("url", "")
    p.download()
    assert isinstance(errors[-1], ParseError)


# ---- configuration -------------------------------------------------------------- #
def test_collect_config_and_parse():
    entries = ut.collect_config()
    keys = {e.key for e in entries}
    assert "astropy.utils.iers.iers.auto_download" in keys
    assert len(entries) > 15
    e = next(x for x in entries if x.name == "auto_download")
    assert ut.parse_config_value(e, "yes") is True and ut.parse_config_value(e, "off") is False
    with pytest.raises(ParseError):
        ut.parse_config_value(e, "maybe")
    f = next(x for x in entries if x.name == "remote_timeout")
    assert ut.parse_config_value(f, "2.5") == 2.5


def test_config_panel_set_and_reset(qtbot, ws, errors, iers_conf_restored):
    p = ut.ConfigPanel(ws)
    qtbot.addWidget(p)
    assert p.item_combo.count() > 15 and p.listing.model.rowCount() == p.item_combo.count()
    p.item_combo.setCurrentIndex(p.item_combo.findText("astropy.utils.iers.iers.remote_timeout"))
    assert "remote_timeout" in p.detail.toPlainText()
    p.form.set_value("value", "7")
    p.set_value()
    assert iers.conf.remote_timeout == 7.0 and "7.0" in p.detail.toPlainText()
    p.form.set_value("value", "not a number")
    p.set_value()
    assert errors and iers.conf.remote_timeout == 7.0
    p.reset_item()
    assert iers.conf.remote_timeout == 10.0
    p.show_paths()
    assert "Config directory" in p.paths.toPlainText()
    p.show_default_file()
    assert "[" in p.paths.toPlainText()


# ---- utilities / about --------------------------------------------------------------- #
def test_tool_pages(qtbot, ws):
    panel = ut.UtilsPanel(ws)
    qtbot.addWidget(panel)
    pg = panel.pages["Masked"]
    pg.run()
    assert "2.5 m" in pg.output.toPlainText()  # mean of 0, 2, 3, 5: masked entries ignored
    pg.form.set_value("mask", "garbage(")
    pg.run()
    assert pg.output.toPlainText().startswith("Error:")

    pg = panel.pages["Metadata merge"]
    pg.run()
    out = pg.output.toPlainText()
    assert "{'a': 1, 'b': 3, 'c': 4}" in out and "warnings" in out
    pg.form.set_value("conflicts", "error")
    pg.run()
    assert pg.output.toPlainText().startswith("Error:")

    pg = panel.pages["Introspection"]
    pg.run()
    assert "Quantity" in pg.output.toPlainText() and "-> True" in pg.output.toPlainText()

    pg = panel.pages["Formatting"]
    pg.run()
    assert "'118M'" in pg.output.toPlainText() and "1h 2m" in pg.output.toPlainText()

    pg = panel.pages["JSON encoder"]
    pg.run()
    assert '"unit": "m"' in pg.output.toPlainText()


def test_about_panel(qtbot, ws):
    p = ut.AboutPanel(ws)
    qtbot.addWidget(p)
    t = ut.version_table()
    names = list(t["component"])
    for n in ("Python", "astropy", "astroquery", "numpy", "scipy", "matplotlib", "PyQt5", "pyerfa"):
        assert n in names
    import astropy
    assert str(t["version"][names.index("astropy")]) == astropy.__version__
    assert "astropy" in p.citation.toPlainText() and "ARTICLE" in p.citation.toPlainText()
    assert "astropy" in p.system.toPlainText().lower()
    p.copy_bibtex()
    from PyQt5.QtGui import QGuiApplication
    assert "astropy" in QGuiApplication.clipboard().text()
