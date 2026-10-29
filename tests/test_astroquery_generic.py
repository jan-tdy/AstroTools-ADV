"""Tests for the generic astroquery browser; the network layer is always mocked."""
import inspect
import socket

import pytest
import requests
from astropy import units as u
from astropy.io import fits
from astropy.table import Table

from astrotools_adv.core import tasks
from astrotools_adv.core.parsing import ParseError
from astrotools_adv.modules import astroquery_generic as g


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    def deny(*_a, **_k):
        raise OSError("network disabled in tests")

    monkeypatch.setattr(socket.socket, "connect", deny)
    monkeypatch.setattr(socket, "create_connection", deny)
    g.set_offline(False)
    yield
    g.set_offline(False)


class Toy:
    def f(self, a, b=2, *, flag=False, name="x"):
        return a, b, flag, name

    def pos(self, a, b=1, /, c=3):
        return a, b, c

    def va(self, first, *items, **opts):
        return first, items, opts

    @property
    def explode(self):  # introspection must never evaluate properties
        raise AssertionError("property evaluated")

    def _private(self):
        pass


# ---- introspection --------------------------------------------------------- #
def test_discover_services_covers_astroquery():
    labels = {s.label for s in g.discover_services()}
    assert len(labels) >= 50
    assert {"simbad", "vizier", "mast", "ipac.ned", "jplhorizons", "gaia", "sdss"} <= labels
    assert "tests" not in labels and "utils" not in labels


@pytest.mark.parametrize("module,expect", [
    ("astroquery.vizier", {"query_object", "query_region", "find_catalogs"}),
    ("astroquery.simbad", {"query_object", "query_region", "query_tap", "add_votable_fields"}),
    ("astroquery.jplhorizons", {"ephemerides", "elements", "vectors"}),
    ("astroquery.ipac.ned", {"query_object", "get_table"}),
])
def test_services_expose_methods_without_network(module, expect):
    instances = g.load_instances(module)
    assert instances
    names = {m.name for obj in instances.values() for m in g.list_methods(obj)}
    assert expect <= names


def test_mast_has_several_objects():
    inst = g.load_instances("astroquery.mast")
    assert {"Observations", "Catalogs"} <= set(inst)


def test_list_methods_skips_properties_and_private():
    names = [m.name for m in g.list_methods(Toy())]
    assert names == ["f", "pos", "va"]


def test_async_flag():
    class A:
        def q(self):
            ...

        def q_async(self):
            ...

    flags = {m.name: m.is_async for m in g.list_methods(A())}
    assert flags == {"q": False, "q_async": True}


def test_effective_signature_uses_async_for_wrappers():
    inst = g.load_instances("astroquery.vizier")["Vizier"]
    sig = g.effective_signature(inst, "query_object")
    assert "object_name" in sig.parameters and "radius" in sig.parameters
    assert "catalog" in sig.parameters


def test_params_and_collect_call_toy():
    sig = inspect.signature(Toy().f)
    params = g.params_from_signature(sig)
    assert [(p.key, p.required) for p in params] == [
        ("a", True), ("b", False), ("flag", False), ("name", False)]
    assert params[2].is_bool and params[3].is_str
    args, kwargs = g.collect_call(params, {"a": "5", "b": "", "flag": "True", "name": "M31"})
    assert args == [] and kwargs == {"a": 5, "flag": True, "name": "M31"}
    args, kwargs = g.collect_call(params, {"a": "1+1", "flag": "(default)", "name": "'q'"})
    assert kwargs == {"a": 2, "name": "q"}
    with pytest.raises(ParseError):
        g.collect_call(params, {"a": ""})


def test_collect_call_expressions_and_fallback_strings():
    params = g.params_from_signature(inspect.signature(Toy().f))
    _, kwargs = g.collect_call(params, {"a": "5 * u.arcmin", "b": "2 arcmin"})
    assert kwargs["a"] == 5 * u.arcmin
    assert kwargs["b"] == "2 arcmin"          # not an expression -> raw string
    names = {"t1": Table({"x": [1]})}
    _, kwargs = g.collect_call(params, {"a": "t1"}, names)
    assert kwargs["a"] is names["t1"]


def test_collect_call_positional_only_and_varargs():
    pos = g.params_from_signature(inspect.signature(Toy().pos))
    args, kwargs = g.collect_call(pos, {"a": "1", "b": "2", "c": "4"})
    assert args == [1, 2] and kwargs == {"c": 4}
    args, kwargs = g.collect_call(pos, {"a": "1"})
    assert args == [1] and kwargs == {}
    with pytest.raises(ParseError):
        g.collect_call(pos, {"b": "2"})
    va = g.params_from_signature(inspect.signature(Toy().va))
    args, kwargs = g.collect_call(va, {"first": "'a'", "*items": "1, 2", "**opts": "k=3, z='s'"})
    assert args == ["a", 1, 2] and kwargs == {"k": 3, "z": "s"}


# ---- results --------------------------------------------------------------- #
def test_normalize_result_kinds():
    t = Table({"a": [1, 2]})
    rs = g.normalize_result(t, "x")
    assert rs.tables[0][0] == "x" and "2 rows" in rs.text
    assert "no rows" in g.normalize_result(Table({"a": []})).text
    assert [n for n, _ in g.normalize_result({"cat1": t, "cat2": t}).tables] == ["cat1", "cat2"]
    assert len(g.normalize_result([t, t], "r").tables) == 2
    assert g.normalize_result(["u1", "u2"]).tables[0][1]["value"][1] == "u2"
    assert "None" in g.normalize_result(None).text
    assert "empty" in g.normalize_result([]).text
    assert "'k'" in g.normalize_result({"k": {"n": 1}}).text

    class Resp:
        status_code, url = 200, "https://example.org/x"

    assert "HTTP 200" in g.normalize_result(Resp()).text
    hdul = fits.HDUList([fits.PrimaryHDU()])
    rs = g.normalize_result([hdul], "img")
    assert rs.objects[0][0] == "img_0" and "PrimaryHDU" in rs.text

    class Job:
        def get_results(self):
            return t

    assert g.normalize_result(Job()).tables[0][1] is t


def test_describe_error():
    assert "Offline" in g.describe_error(g.OfflineError(g.OFFLINE_MESSAGE))
    assert g.describe_error(ParseError("bad")).startswith("Input error")
    assert "Network error" in g.describe_error(requests.exceptions.Timeout("slow"))
    assert "Network error" in g.describe_error(ConnectionError("down"))
    assert g.describe_error(ValueError("x")) == "Error: ValueError: x"


def test_set_timeout():
    class S:
        TIMEOUT = 1

    s = S()
    g.set_timeout(s, 9)
    assert s.TIMEOUT == 9
    g.set_timeout(object(), 5)  # no attribute: silently ignored


# ---- config ---------------------------------------------------------------- #
def test_conf_items_roundtrip():
    import astroquery.vizier as vz

    items = {n: (v, t) for n, v, t, _d in g.conf_items(vz.conf)}
    assert "timeout" in items
    old = vz.conf.timeout
    try:
        assert g.set_conf_item(vz.conf, "timeout", "77") == 77
        assert vz.conf.timeout == 77
        with pytest.raises(ParseError):
            g.set_conf_item(vz.conf, "timeout", "abc")
        with pytest.raises(ParseError):
            g.set_conf_item(vz.conf, "nope", "1")
    finally:
        vz.conf.timeout = old


# ---- panel ----------------------------------------------------------------- #
@pytest.fixture
def browser(qtbot, ws):
    panel = g.GenericBrowser(ws)
    qtbot.addWidget(panel)
    return panel


def _select(panel, service, instance, method):
    panel.service_combo.setCurrentIndex(panel.service_combo.findText(service))
    panel.instance_combo.setCurrentIndex(panel.instance_combo.findText(instance))
    panel.method_combo.setCurrentIndex(panel.method_combo.findData(method))


def test_panel_runs_mocked_method_and_stores_result(browser, ws, monkeypatch):
    _select(browser, "vizier", "Vizier", "query_object")
    inst = browser.current_instance()
    calls = []

    def fake(*args, **kwargs):
        calls.append((args, kwargs, inst.TIMEOUT))
        return Table({"RAJ2000": [10.68], "Vmag": [3.4]})

    monkeypatch.setattr(inst, "query_object", fake, raising=False)
    browser.on_method()  # re-read the (now patched) signature -> falls back to async one
    form = browser._param_form
    form.set_value("object_name", "M31")
    form.set_value("radius", "5 arcmin")
    browser.timeout_box.setValue(12)
    browser.run_method()
    (args, kwargs, timeout), = calls
    assert args == () and kwargs == {"object_name": "M31", "radius": "5 arcmin"}
    assert timeout == 12
    assert browser.table_view.model.rowCount() == 1
    assert browser.store_table() == "aq_result"
    assert isinstance(ws.get("aq_result"), Table)


def test_panel_error_paths_do_not_crash(browser, monkeypatch):
    _select(browser, "vizier", "Vizier", "query_object")
    inst = browser.current_instance()
    browser.run_method()  # required 'object_name' missing
    assert "Input error" in browser.info.toPlainText()

    browser._param_form.set_value("object_name", "M31")
    for exc, text in [(requests.exceptions.ConnectTimeout("t"), "Network error"),
                      (ValueError("boom"), "Error: ValueError: boom")]:
        def fake(*a, _e=exc, **k):
            raise _e

        monkeypatch.setattr(inst, "query_object", fake, raising=False)
        browser.run_method()
        assert text in browser.info.toPlainText()

    monkeypatch.setattr(inst, "query_object", lambda *a, **k: Table({"a": []}), raising=False)
    browser.run_method()
    assert "no rows" in browser.info.toPlainText()
    monkeypatch.setattr(inst, "query_object", lambda *a, **k: None, raising=False)
    browser.run_method()
    assert "no result" in browser.info.toPlainText()


def test_offline_switch_blocks_calls(browser, monkeypatch):
    _select(browser, "vizier", "Vizier", "query_object")
    inst = browser.current_instance()
    called = []
    monkeypatch.setattr(inst, "query_object", lambda *a, **k: called.append(1), raising=False)
    browser._param_form.set_value("object_name", "M31")
    browser.offline_box.setChecked(True)
    assert g.is_offline()
    browser.run_method()
    assert not called and "Offline mode" in browser.info.toPlainText()
    with pytest.raises(g.OfflineError):
        g.ensure_online()
    browser.offline_box.setChecked(False)
    browser.run_method()
    assert called == [1]


def test_offline_switch_is_shared_between_panels(qtbot, ws):
    a, b = g.GenericBrowser(ws), g.GenericBrowser(ws)
    qtbot.addWidget(a)
    qtbot.addWidget(b)
    a.offline_box.setChecked(True)
    assert b.offline_box.isChecked()


def test_late_result_of_superseded_query_is_ignored(browser, qtbot):
    tasks.set_synchronous(False)
    import threading
    gate = threading.Event()

    def slow(_t):
        gate.wait(5)
        return Table({"late": [1]})

    assert browser.execute(slow)
    browser._gen += 1          # a newer query (or panel reset) supersedes it
    gate.set()
    tasks.wait_all()
    qtbot.wait(50)
    assert browser.current_table() is None


def test_result_after_panel_destroyed_is_ignored(browser, qtbot):
    tasks.set_synchronous(False)
    import threading
    gate = threading.Event()
    assert browser.execute(lambda _t: (gate.wait(5), Table({"a": [1]}))[1])
    browser._alive["v"] = False  # what the destroyed() hook does
    gate.set()
    tasks.wait_all()
    qtbot.wait(50)
    assert browser.current_table() is None


def test_config_tab_applies_values(browser):
    _select(browser, "vizier", "Vizier", "query_object")
    import astroquery.vizier as vz

    old = vz.conf.timeout
    try:
        for row in range(browser.conf_table.rowCount()):
            if browser.conf_table.item(row, 0).text() == "timeout":
                browser.conf_table.item(row, 1).setText("45")
        browser.apply_conf()
        assert vz.conf.timeout == 45
        assert "1 setting" in browser.info.toPlainText()
    finally:
        vz.conf.timeout = old


def test_every_service_loads_or_reports(browser):
    """No service may crash the browser; failures are shown as text."""
    for i in range(browser.service_combo.count()):
        browser.service_combo.setCurrentIndex(i)
        loaded = browser.instance_combo.count() > 0 and browser.method_combo.count() > 0
        reported = "Cannot load" in browser.docs.toPlainText()
        assert loaded or reported, browser.service_combo.currentText()


def test_specs_category():
    assert [s.category for s in g.SPECS] == ["Online"]
