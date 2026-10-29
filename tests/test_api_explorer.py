import numpy as np
import pytest
from astropy import units as u
from astropy.coordinates import SkyCoord
from astropy.table import Table

from astrotools_adv.core.parsing import ParseError
from astrotools_adv.modules import api_explorer as ax


@pytest.fixture(scope="module")
def index():
    return ax.collect_api()


# ---- pure helpers ---------------------------------------------------------- #
def test_index_contains_core_api(index):
    entries, _failures = index
    names = {e.qualname for e in entries}
    for q in ("astropy.units.Quantity", "astropy.coordinates.SkyCoord", "astropy.stats.sigma_clip",
              "astropy.table.Table", "astropy.io.fits.open", "astropy.time.Time",
              "astropy.wcs.WCS", "astropy.cosmology.FlatLambdaCDM"):
        assert q in names, q
    # shallowest public path wins, no duplicate object exported twice
    assert "astropy.units.quantity.Quantity" not in names
    assert all(e.resolve() is not None for e in entries[:50])
    assert len(entries) > 1000


def test_filter_entries(index):
    entries, _ = index
    hits = ax.filter_entries(entries, "sigma_clip")
    assert hits and all("sigma_clip" in e.qualname.lower() for e in hits)
    assert len(hits) < len(entries) / 10
    narrowed = ax.filter_entries(entries, "stats sigma_clip")
    assert any(e.qualname == "astropy.stats.sigma_clip" for e in narrowed)
    assert ax.filter_entries(entries, "zzzz_nothing_matches") == []


def test_param_specs_and_binding():
    def f(a, b=2, /, c=3, *rest, d, e=5, **kw): ...

    specs = ax.param_specs(ax.safe_signature(f))
    assert [s.name for s in specs] == ["a", "b", "c", "rest", "d", "e", "kw"]
    assert specs[0].required and not specs[1].required and specs[4].required
    ns = {"x": 10}
    args, kwargs = ax.evaluate_arguments(
        specs, {"a": "x", "b": "3", "c": "4", "rest": "5, 6", "d": "x+1", "kw": "z=7"}, ns)
    assert args == [10, 3, 4, 5, 6] and kwargs == {"d": 11, "z": 7}
    with pytest.raises(ParseError, match="Missing required argument 'a'"):
        ax.evaluate_arguments(specs, {"d": "1"}, ns)
    with pytest.raises(ParseError, match="Missing required argument 'd'"):
        ax.evaluate_arguments(specs, {"a": "1"}, ns)
    with pytest.raises(ParseError):  # positional-only gap
        ax.evaluate_arguments(specs, {"a": "1", "c": "2", "rest": "9", "d": "1"}, ns)
    with pytest.raises(ParseError):
        ax.evaluate_arguments(specs, {"a": "1", "d": "1", "kw": "1, 2"}, ns)
    code = ax.format_call("f", specs, {"a": "x", "d": "1", "e": "2"})
    assert code == "f(x, d=1, e=2)"


def test_str_parameter_accepts_bare_text():
    def g(filename: str, *, mode="r"): ...

    specs = ax.param_specs(ax.safe_signature(g))
    args, kwargs = ax.evaluate_arguments(specs, {"filename": "data/file.fits", "mode": "w"}, {})
    assert kwargs == {"filename": "data/file.fits", "mode": "w"} and args == []
    # non-text parameter does not get the fallback
    def h(n): ...
    with pytest.raises(ParseError):
        ax.evaluate_arguments(ax.param_specs(ax.safe_signature(h)), {"n": "bare"}, {})


def test_missing_signature_falls_back_to_varargs():
    specs = ax.param_specs(None)
    assert [s.kind for s in specs] == [ax._P.VAR_POSITIONAL, ax._P.VAR_KEYWORD]


def test_class_members():
    members = {m.name: m.kind for m in ax.class_members(SkyCoord)}
    assert members["from_name"] == "classmethod"
    assert "separation" not in members  # resolved dynamically on instances only
    c = SkyCoord(1 * u.deg, 2 * u.deg)
    dyn = {m.name: m.kind for m in ax.class_members(SkyCoord, c)}
    assert dyn["separation"] == dyn["ra"] == "dynamic"
    sep = ax.Member("separation", "dynamic")
    assert list(ax.member_signature(SkyCoord, sep, c).parameters)[0] == "other"
    assert not ax.is_value_member(SkyCoord, sep, c)
    assert ax.is_value_member(SkyCoord, ax.Member("ra", "dynamic"), c)
    t = ax.class_members(Table)
    assert {"colnames": "property", "add_row": "method"}.items() <= {m.name: m.kind for m in t}.items()


def test_invoke_captures_everything():
    import warnings

    def noisy():
        print("hello")
        warnings.warn("careful")
        return 5

    out = ax.invoke(noisy)
    assert out.value == 5 and "hello" in out.stdout and "careful" in out.warnings[0]
    bad = ax.invoke(lambda: 1 / 0)
    assert isinstance(bad.error, ZeroDivisionError) and "ZeroDivisionError" in bad.detail


def test_explorer_namespace_has_ws_names(ws):
    ws.put("my data", 5)
    ns = ax.explorer_namespace(ws)
    assert ns["ws_my_data"] == 5 and ns["ws"]["my data"] == 5 and ns["astropy"].__name__ == "astropy"


# ---- panel ------------------------------------------------------------------ #
@pytest.fixture
def panel(qtbot, ws):
    p = ax.ApiExplorer(ws)
    qtbot.addWidget(p)
    return p


def test_panel_indexes_and_searches(panel):
    assert len(panel.entries) > 1000
    everything = len(panel.visible_qualnames())
    panel.search.setText("sigma_clip")
    narrowed = panel.visible_qualnames()
    assert 0 < len(narrowed) < everything and "astropy.stats.sigma_clip" in narrowed
    panel.search.setText("")
    assert len(panel.visible_qualnames()) == everything


def test_call_sigma_clip_with_workspace_data(panel, ws):
    data = np.array([1.0, 2.0, 3.0, 2.0, 1.0, 100.0])
    ws.put("data", data)
    panel.select_qualname("astropy.stats.sigma_clip")
    assert "sigma_clip" in panel.docs.toPlainText()
    panel.call_form.edits["data"].setText("ws_data")
    panel.call_form.edits["sigma"].setText("2")
    panel.gui_thread.setChecked(False)
    panel.on_run()
    assert panel._has_result
    result = panel._last_value
    assert isinstance(result, np.ma.MaskedArray)
    assert list(result.mask) == [False] * 5 + [True]
    assert "sigma_clip" in panel.result.toPlainText()
    panel.store_name.setText("clipped")
    panel.on_store_result()
    assert "clipped" in ws
    assert "ws_data" in panel.python_code()


def test_construct_and_call_method(panel, ws):
    panel.select_qualname("astropy.coordinates.SkyCoord")
    assert panel.run_btn.text() == "Construct"
    panel.call_form.edits["args"].setText("10*u.deg, 20*u.deg")
    panel.on_run()
    names = ws.names(SkyCoord)
    assert len(names) == 1
    name = names[0]
    assert panel._history[name].lines[-1].startswith(f"{name} = SkyCoord(")
    panel.search.setText("")
    idx = panel.member_combo.findText("separation  (dynamic)")
    assert idx > 0
    panel.member_combo.setCurrentIndex(idx)
    panel.call_form.edits["other"].setText("SkyCoord(10*u.deg, 21*u.deg)")
    panel.on_run()
    assert panel._last_value.deg == pytest.approx(1.0)
    code = panel.python_code()
    compile(code, "<generated>", "exec")
    assert "from astropy.coordinates import SkyCoord" in code
    assert f"result = {name}.separation(other=SkyCoord(10*u.deg, 21*u.deg))" in code
    ns = {}
    exec(code, ns)  # the copied snippet is self-contained and reproduces the answer
    assert ns["result"].deg == pytest.approx(1.0)


def test_property_and_missing_instance(panel, ws, monkeypatch):
    shown = []
    monkeypatch.setattr("astrotools_adv.core.widgets.error_box",
                        lambda parent, exc, detail="": shown.append(exc))
    panel.select_qualname("astropy.table.Table")
    panel.member_combo.setCurrentIndex(panel.member_combo.findText("colnames  (property)"))
    panel.on_run()  # no instance yet
    assert shown and isinstance(shown[-1], ParseError)
    ws.put("tbl", Table({"q": [1]}))
    panel.on_run()
    assert panel._last_value == ["q"]
    panel.select_qualname("astropy.coordinates.SkyCoord")
    ws.put("c", SkyCoord(1 * u.deg, 2 * u.deg))
    panel.instance_combo.setCurrentIndex(panel.instance_combo.findText("c"))
    assert panel.member_combo.findText("separation  (dynamic)") > 0
    panel.member_combo.setCurrentIndex(panel.member_combo.findText("ra  (dynamic)"))
    assert panel.run_btn.text() == "Get"
    panel.on_run()
    assert panel._last_value.deg == pytest.approx(1.0)
    assert "c.ra" in panel.python_code()


def test_bad_input_is_reported_not_raised(panel, monkeypatch):
    shown = []
    monkeypatch.setattr("astrotools_adv.core.widgets.error_box",
                        lambda parent, exc, detail="": shown.append(exc))
    panel.select_qualname("astropy.stats.sigma_clip")
    panel.on_run()  # required 'data' missing
    assert isinstance(shown[-1], ParseError)
    panel.call_form.edits["data"].setText("__import__('os')")
    panel.on_run()
    assert isinstance(shown[-1], ParseError)
    panel.call_form.edits["data"].setText("'not numbers'")  # runtime error inside astropy
    panel.gui_thread.setChecked(False)
    panel.on_run()
    assert len(shown) == 2  # runtime errors go to the Result tab, no modal dialog
    assert "Error in astropy.stats.sigma_clip" in panel.result.toPlainText()
    assert not panel._has_result


def test_table_and_figure_results(panel, ws):
    panel.select_qualname("astropy.table.Table")
    panel.call_form.edits["data"].setText("{'a': [1, 2, 3]}")
    panel.on_run()
    assert ws.names(Table) and panel.table_view.model.rowCount() == 3
    assert panel.tabs.currentIndex() == panel.TAB_TABLE

    panel.select_qualname("astropy.visualization.hist")
    assert panel.gui_thread.isChecked()
    panel.call_form.edits["x"].setText("np.arange(100)")
    panel.call_form.edits["bins"].setText("'knuth'")
    panel.on_run()
    assert panel.figure_holder.figure is not None
    assert panel.tabs.currentIndex() == panel.TAB_FIGURE


def test_blocked_and_confirmed(panel, monkeypatch):
    shown = []
    monkeypatch.setattr("astrotools_adv.core.widgets.error_box",
                        lambda parent, exc, detail="": shown.append(exc))
    assert ax.is_blocked("hub_script") and not ax.is_blocked("sigma_clip")
    blocked = [e for e in panel.entries if ax.is_blocked(e.name)]
    assert blocked, "expected at least one interactive entry (e.g. hub_script)"
    panel.select_qualname(blocked[0].qualname)
    panel.on_run()
    assert isinstance(shown[-1], ParseError) and "not available" in str(shown[-1])

    asked = []
    monkeypatch.setattr(panel, "confirm", lambda text: asked.append(text) or False)
    panel.select_qualname("astropy.utils.data.clear_download_cache")
    panel.on_run()  # declined -> nothing executed
    assert asked and not panel._has_result


def test_code_is_valid_python_for_all_kinds(panel, ws):
    panel.select_qualname("astropy.units.Quantity")
    panel.call_form.edits["value"].setText("[1, 2]")
    panel.call_form.edits["unit"].setText("u.m")
    code = panel.python_code()
    compile(code, "<generated>", "exec")
    assert "import astropy.units as u" in code


def test_call_in_worker_thread(qtbot, ws):
    """Real thread pool (no synchronous shortcut): result arrives on the GUI thread."""
    from astrotools_adv.core import tasks

    tasks.set_synchronous(False)
    p = ax.ApiExplorer(ws)
    qtbot.addWidget(p)
    qtbot.waitUntil(lambda: bool(p.entries), timeout=20000)
    ws.put("d", np.array([1.0, 2.0, 3.0, 1000.0]))
    p.select_qualname("astropy.stats.sigma_clip")
    p.call_form.edits["data"].setText("ws_d")
    p.call_form.edits["sigma"].setText("1")
    p.gui_thread.setChecked(False)
    p.on_run()
    qtbot.waitUntil(lambda: p._has_result, timeout=20000)
    assert list(p._last_value.mask) == [False, False, False, True]
    tasks.wait_all()
