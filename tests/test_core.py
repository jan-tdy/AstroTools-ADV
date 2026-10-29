import threading

import numpy as np
import pytest
from astropy import units as u
from astropy.table import Table

from astrotools_adv.core import parsing as p
from astrotools_adv.core import registry, tasks
from astrotools_adv.core.widgets import ModulePanel, TableModel, TableView, WorkspaceCombo


# ---- parsing --------------------------------------------------------------- #
def test_safe_eval_basic():
    assert p.safe_eval("1+2*3") == 7
    q = p.safe_eval("np.linspace(0, 1, 3) * u.m")
    assert q.unit == u.m and list(q.value) == [0, 0.5, 1]


@pytest.mark.parametrize("bad", ["__import__('os')", "u.__class__", "np.os", "x", "",
                                 "lambda: 1", "[i for i in range(3)]", "1 +", "2**100000"])
def test_safe_eval_rejects(bad):
    with pytest.raises(p.ParseError):
        p.safe_eval(bad)


def test_quantity_parsing():
    assert p.parse_quantity("3.5 km/s") == 3.5 * u.km / u.s
    assert p.parse_quantity("42", default_unit="m") == 42 * u.m
    assert p.parse_quantity("2*u.pc") == 2 * u.pc
    assert p.parse_quantity("1,5 m") == 1.5 * u.m
    with pytest.raises(p.ParseError):
        p.parse_quantity("42")
    with pytest.raises(p.ParseError):
        p.parse_quantity("3 notaunit")


def test_unit_and_numbers():
    assert p.parse_unit("") == u.dimensionless_unscaled
    assert p.parse_unit("Msun") == u.Msun
    with pytest.raises(p.ParseError):
        p.parse_unit("zzz")
    assert p.parse_float("1,5") == 1.5
    with pytest.raises(p.ParseError):
        p.parse_float("abc")
    assert list(p.parse_float_list("1, 2;3\n4")) == [1, 2, 3, 4]
    assert list(p.parse_array("linspace(0, 1, 3)")) == [0, 0.5, 1]


def test_angle_time_coord():
    assert p.parse_angle("10h30m").deg == pytest.approx(157.5)
    assert p.parse_angle("12.5").deg == 12.5
    with pytest.raises(p.ParseError):
        p.parse_angle("garbage")
    assert p.parse_time("2000-01-01T12:00:00", scale="utc").jd == pytest.approx(2451545.0)
    assert p.parse_time("2451545", fmt="jd").jd == 2451545.0
    assert p.parse_time("J2000").jyear == 2000.0
    assert p.parse_time("now").jd > 2460000
    with pytest.raises(p.ParseError):
        p.parse_time("not a time")
    c = p.parse_skycoord("10.68 41.27")
    assert c.ra.deg == pytest.approx(10.68)
    c2 = p.parse_skycoord("00h42m44s +41d16m09s")
    assert c2.ra.deg == pytest.approx(10.6833, abs=1e-3)
    with pytest.raises(p.ParseError):
        p.parse_skycoord("")


# ---- tasks ----------------------------------------------------------------- #
def test_task_sync_result_and_error():
    got = []
    tasks.submit(lambda x: x * 2, 4, on_result=got.append)
    assert got == [8]
    errs = []
    tasks.submit(lambda: 1 / 0, on_error=lambda e, tb: errs.append(e))
    assert isinstance(errs[0], ZeroDivisionError)


def test_task_runs_off_gui_thread(qtbot):
    tasks.set_synchronous(False)
    main = threading.get_ident()
    seen = {}

    def work():
        seen["worker"] = threading.get_ident()
        return 1

    def done(_v):
        seen["cb"] = threading.get_ident()

    finished = []
    tasks.submit(work, on_result=done, on_finished=lambda: finished.append(1))
    qtbot.waitUntil(lambda: bool(finished), timeout=5000)
    assert seen["worker"] != main and seen["cb"] == main


# ---- widgets --------------------------------------------------------------- #
def test_table_model_and_view(qtbot):
    t = Table({"a": [1.5, 2.5], "b": ["x", "y"]})
    t["a"].unit = u.m
    t["m"] = np.ma.masked_array([1, 2], mask=[True, False])
    model = TableModel(t)
    assert model.rowCount() == 2 and model.columnCount() == 3
    assert model.data(model.index(0, 0)) == "1.5"
    assert model.data(model.index(0, 2)) == "--"
    assert "[m]" in model.headerData(0, 1)
    assert model.to_csv().splitlines()[0] == "a,b,m"
    view = TableView()
    qtbot.addWidget(view)
    view.set_table(t)
    assert "2 rows" in view.summary.text()
    view.set_table(None)
    assert view.model.rowCount() == 0


def test_workspace_combo(qtbot, ws):
    combo = WorkspaceCombo(ws, Table)
    qtbot.addWidget(combo)
    ws.put("t1", Table({"a": [1]}))
    ws.put("not_a_table", 5)
    assert [combo.itemText(i) for i in range(combo.count())] == ["t1"]
    assert isinstance(combo.selected(), Table)
    ws.remove("t1")
    with pytest.raises(p.ParseError):
        combo.selected()


def test_panel_run_reports_errors(qtbot, ws, monkeypatch):
    shown = []
    monkeypatch.setattr("astrotools_adv.core.widgets.error_box",
                        lambda parent, exc, detail="": shown.append(exc))
    panel = ModulePanel(ws)
    qtbot.addWidget(panel)
    panel.run(lambda: 1 / 0, lambda v: None)
    panel.run(lambda: 1, lambda v: (_ for _ in ()).throw(ValueError("cb")))
    assert [type(e) for e in shown] == [ZeroDivisionError, ValueError]
    ok = []
    panel.run(lambda: 5, ok.append)
    assert ok == [5]


def test_workspace():
    from astrotools_adv.core.workspace import Workspace
    w = Workspace()
    w.put(" x ", 1)
    assert w.get("x") == 1 and "x" in w
    with pytest.raises(KeyError):
        w.get("nope")
    with pytest.raises(ValueError):
        w.put("  ", 1)


# ---- registry / app -------------------------------------------------------- #
def test_discover_has_no_failures_and_unique_keys():
    specs, failures = registry.discover()
    assert failures == []
    assert len({s.key for s in specs}) == len(specs)


def test_every_module_opens(qtbot, monkeypatch):
    from astrotools_adv import app
    from astrotools_adv.app import MainWindow

    def boom(parent, exc, detail=""):
        raise AssertionError(f"module failed to open: {exc!r}")

    monkeypatch.setattr(app, "error_box", boom)
    specs, failures = registry.discover()
    win = MainWindow(specs, failures)
    qtbot.addWidget(win)
    for spec in specs:
        page = win.open_module(spec.key)
        assert page is not None, spec.key


def test_safe_eval_comparisons_are_elementwise():
    x = np.array([1, 3, 5])
    assert list(p.safe_eval("x > 2", {"x": x})) == [False, True, True]
    assert list(p.safe_eval("0 < x < 4", {"x": x})) == [True, True, False]
    assert p.safe_eval("1 < 2 < 3") is True
    assert p.safe_eval("3 < 2") is False


def test_parse_quantity_composite_units():
    assert p.parse_quantity("3 m**2") == 3 * u.m ** 2
    assert p.parse_quantity("0 mag(AB)").unit == u.mag(u.AB)
    assert p.parse_quantity("2*u.pc") == 2 * u.pc
    with pytest.raises(p.ParseError):
        p.parse_quantity("3 notaunit")


def test_safe_eval_bitwise_masks():
    x = np.array([1, 3, 5])
    assert list(p.safe_eval("(x > 1) & (x < 5)", {"x": x})) == [False, True, False]
    assert list(p.safe_eval("~(x > 2)", {"x": x})) == [True, False, False]


def test_button_exceptions_are_reported(qtbot, ws, monkeypatch):
    shown = []
    monkeypatch.setattr("astrotools_adv.core.widgets.error_box",
                        lambda parent, exc, detail="": shown.append(exc))
    panel = ModulePanel(ws)
    qtbot.addWidget(panel)
    btn = panel.add_button("boom", lambda: 1 / 0)
    btn.click()
    assert isinstance(shown[0], ZeroDivisionError)


def test_paramform_values_skip_custom_widgets(qtbot):
    from PyQt5.QtWidgets import QLabel

    from astrotools_adv.core.widgets import ParamForm
    form = ParamForm()
    qtbot.addWidget(form)
    form.add_text("a", "A", "x")
    form.add_widget("custom", "C", QLabel("hi"))
    assert form.values() == {"a": "x"}
