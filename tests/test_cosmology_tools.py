import numpy as np
import pytest
from astropy import cosmology
from astropy import units as u
from astropy.cosmology import FlatLambdaCDM, Planck18
from astropy.table import Table

from astrotools_adv.core.parsing import ParseError
from astrotools_adv.modules import cosmology_tools as ct


@pytest.fixture(autouse=True)
def errors(monkeypatch):
    """Collect errors that panels would show in a dialog; a test must clear expected ones."""
    seen = []
    monkeypatch.setattr("astrotools_adv.core.widgets.error_box",
                        lambda parent, exc, detail="": seen.append(exc))
    yield seen
    assert not seen, f"unexpected error dialogs: {seen!r}"


@pytest.fixture(autouse=True)
def _flush_events(qtbot):
    yield
    from PyQt5.QtWidgets import QApplication
    for _ in range(3):
        QApplication.processEvents()


@pytest.fixture(autouse=True)
def _restore_default():
    yield
    cosmology.default_cosmology.set("Planck18")


def make_panel(qtbot, ws, cls):
    panel = cls(ws)
    qtbot.addWidget(panel)
    return panel


def set_checked(panel, names):
    from PyQt5.QtCore import Qt
    for i in range(panel.qlist.count()):
        item = panel.qlist.item(i)
        item.setCheckState(Qt.Checked if item.text() in names else Qt.Unchecked)


def test_specs():
    assert len(ct.SPECS) == 5 and all(s.category == "Analysis" for s in ct.SPECS)


def test_parse_redshifts_validation():
    assert list(ct.parse_redshifts("0, 1, 2")) == [0, 1, 2]
    assert ct.parse_redshifts("linspace(0, 1, 3)").size == 3
    for bad in ("-1", "nan", "inf", "", "abc", "-2, 1"):
        with pytest.raises(ParseError):
            ct.parse_redshifts(bad)


def test_calculator_known_values(qtbot, ws):
    panel = make_panel(qtbot, ws, ct.CalculatorPanel)
    set_checked(panel, {"luminosity_distance", "age", "comoving_distance"})
    panel.form.set_value("z", "0, 1")
    panel.compute()
    t = ws.get("cosmo_table")
    assert t["luminosity_distance"][1] == pytest.approx(6791.2689, rel=1e-6)  # Mpc
    assert t["luminosity_distance"].unit == u.Mpc
    assert t["age"][0] == pytest.approx(13.786885, rel=1e-6)  # Gyr
    assert t["age"].unit == u.Gyr
    assert t["comoving_distance"][1] == pytest.approx(3395.6345, rel=1e-6)
    assert t["luminosity_distance"][0] == 0


def test_calculator_all_quantities_run_for_all_realizations():
    z = np.array([0.0, 0.5, 2.0])
    for name in cosmology.realizations.available:
        table, notes = ct.compute_quantities(getattr(cosmology, name), z, list(ct.Z_NAMES))
        missing = [n for n in ct.Z_NAMES if n not in table.colnames]
        assert not missing, (name, missing, notes)


def test_z1z2_quantities(qtbot, ws):
    panel = make_panel(qtbot, ws, ct.CalculatorPanel)
    set_checked(panel, {"comoving_distance_z1z2", "angular_diameter_distance_z1z2"})
    panel.form.set_value("z", "0.5, 1")
    with pytest.raises(ParseError):       # no z2
        panel.compute()
    panel.form.set_value("z2", "2")
    panel.compute()
    t = ws.get("cosmo_table")
    assert t["comoving_distance_z1z2"][0] == pytest.approx(
        float((Planck18.comoving_distance(2) - Planck18.comoving_distance(0.5)).value), rel=1e-6)
    panel.form.set_value("z2", "0.1")
    with pytest.raises(ParseError):       # z2 < z
        panel.compute()


def test_calculator_rejects_bad_input(qtbot, ws):
    panel = make_panel(qtbot, ws, ct.CalculatorPanel)
    for bad in ("-1", "-3", "nan", ""):
        panel.form.set_value("z", bad)
        with pytest.raises(ParseError):
            panel.compute()
    panel.form.set_value("z", "1")
    set_checked(panel, set())
    with pytest.raises(ParseError):
        panel.compute()


def test_nonfinite_results_are_reported_not_crashing():
    table, notes = ct.compute_quantities(Planck18, np.array([0.0]), ["distmod"])
    assert "distmod" in table.colnames and any("non-finite" in n for n in notes)
    table, notes = ct.compute_quantities(Planck18, np.array([1.0]), ["Ob", "bogus"])
    assert "Ob" in table.colnames and any(n.startswith("bogus") for n in notes)


def test_custom_cosmology_selector(qtbot, ws):
    panel = make_panel(qtbot, ws, ct.CalculatorPanel)
    sel = panel.selector
    sel.set_custom("FlatLambdaCDM", H0="70", Om0="0.3", Tcmb0="0", name="mine")
    c = sel.cosmology()
    assert isinstance(c, FlatLambdaCDM) and c.H0.value == 70 and c.name == "mine"
    assert c.luminosity_distance(1).value == pytest.approx(6607.66, rel=1e-4)
    # inconsistent / invalid parameters give clear errors
    for fields in ({"H0": "-5"}, {"H0": "abc"}, {"Om0": "-1"}, {"Om0": "0.3", "Ob0": "0.9"},
                   {"Ob0": "", "Neff": "-1"}, {"Tcmb0": "-2"}):
        sel.set_custom("FlatLambdaCDM", **{**dict(H0="70", Om0="0.3", Tcmb0="0", Neff="3.04",
                                                  Ob0=""), **fields})
        with pytest.raises(ParseError):
            sel.cosmology()
    sel.set_custom("w0waCDM", H0="70", Om0="0.3", Ode0="0.7", Tcmb0="0", Neff="3.04",
                   Ob0="", w0="-0.9", wa="0.1", name="x")
    c = sel.cosmology()
    assert type(c).__name__ == "w0waCDM" and c.w0 == -0.9 and c.wa == 0.1


def test_selector_shows_preset_and_workspace_entries(qtbot, ws):
    panel = make_panel(qtbot, ws, ct.CalculatorPanel)
    sel = panel.selector
    sel.model.setCurrentText("Planck15")
    assert sel.cosmology() is cosmology.Planck15
    assert float(sel.edits["H0"].text()) == pytest.approx(67.74)
    assert not sel.edits["H0"].isEnabled()
    ws.put("mycosmo", FlatLambdaCDM(H0=72, Om0=0.25))
    assert ct.WS_PREFIX + "mycosmo" in [sel.model.itemText(i) for i in range(sel.model.count())]
    sel.model.setCurrentText(ct.WS_PREFIX + "mycosmo")
    assert sel.cosmology().H0.value == 72
    ws.remove("mycosmo")   # selection falls back gracefully
    assert sel.cosmology() is not None


def test_massive_neutrino_array_input():
    c = ct.build_cosmology("FlatLambdaCDM", dict(H0="67.66", Om0="0.31", Tcmb0="2.7255",
                                                 Neff="3.046", m_nu="0 0 0.06", Ob0="0.049"))
    assert c.has_massive_nu and c.age(0).value == pytest.approx(13.79, abs=0.1)


def test_plot_panel_compares_cosmologies(qtbot, ws):
    panel = make_panel(qtbot, ws, ct.PlotPanel)
    panel.form.set_value("q", "comoving_distance")
    panel.form.set_value("n", 20)
    panel.compare.item(0).setCheckState(2)   # WMAP1
    panel.plot()
    t = ws.get("cosmo_curves")
    assert t.colnames == ["z", "Planck18", "WMAP1"] and len(t) == 20
    assert t["Planck18"][-1] == pytest.approx(
        Planck18.comoving_distance(5.0).value, rel=1e-6)
    panel.form.set_value("logz", True)
    panel.form.set_value("zmin", 0.0)
    with pytest.raises(ParseError):
        panel.plot()
    panel.form.set_value("zmin", 6.0)
    with pytest.raises(ParseError):
        panel.plot()


def test_z_at_value_roundtrip(qtbot, ws):
    panel = make_panel(qtbot, ws, ct.SolverPanel)
    z_true = np.array([0.3, 1.2, 3.0])
    d = Planck18.luminosity_distance(z_true).to_value(u.Mpc)
    panel.form.set_value("func", "luminosity_distance")
    panel.form.set_value("values", ", ".join(f"{x:.10g}" for x in d))
    panel.solve()
    t = ws.get("z_solutions")
    assert np.allclose(t["z"], z_true, rtol=1e-5)
    assert np.all(t["rel_error"] < 1e-6)
    # age with unit change, plus bracket
    panel.form.set_value("func", "age")
    panel.form.set_value("values", "1")
    panel.form.set_value("unit", "Gyr")
    panel.form.set_value("bracket", "1, 10")
    panel.solve()
    assert Planck18.age(ws.get("z_solutions")["z"][0]).value == pytest.approx(1.0, rel=1e-5)


def test_z_at_value_errors(qtbot, ws, errors):
    panel = make_panel(qtbot, ws, ct.SolverPanel)
    panel.form.set_value("values", "5 Gyr")
    with pytest.raises(ParseError):
        panel.solve()
    panel.form.set_value("values", "1000")
    panel.form.set_value("unit", "Gyr")           # wrong dimensions for luminosity_distance
    panel.solve()
    assert isinstance(errors.pop(), u.UnitConversionError)
    panel.form.set_value("unit", "Mpc")
    panel.form.set_value("bracket", "1")
    with pytest.raises(ParseError):
        panel.solve()
    panel.form.set_value("bracket", "")
    panel.form.set_value("values", "1e12")          # beyond zmax
    panel.solve()
    assert len(errors) == 1
    errors.clear()


def test_unit_equivalencies(qtbot, ws, errors):
    panel = make_panel(qtbot, ws, ct.UnitsPanel)
    f = panel.form
    f.set_value("equiv", "redshift_distance")
    f.set_value("distance", "comoving")
    f.set_value("value", "1")
    panel.convert()
    assert "3395.63" in panel.out.toPlainText()
    f.set_value("equiv", "redshift_temperature")
    f.set_value("target", "K")
    panel.convert()
    assert "5.451" in panel.out.toPlainText()
    f.set_value("equiv", "with_H0")
    f.set_value("value", "1")
    f.set_value("unit", "Mpc / littleh")
    f.set_value("target", "Mpc")
    panel.convert()
    assert "1.4779" in panel.out.toPlainText()    # 1 / h with h = 0.6766
    f.set_value("target", "kg")
    panel.convert()
    assert isinstance(errors.pop(), u.UnitConversionError)


def test_compare_clone_default(qtbot, ws):
    panel = make_panel(qtbot, ws, ct.CompareIOPanel)
    panel.compare()
    assert len(panel.view.model._table) >= 6
    assert "A == B:            False" in panel.result.toPlainText()
    panel.other.model.setCurrentText("Planck18")
    panel.compare()
    assert "A == B:            True" in panel.result.toPlainText()
    panel.form.set_value("changes", "H0=70, name='fast'")
    panel.clone()
    c = ws.get("edited")
    assert c.H0.value == 70 and c.name == "fast" and not c.is_equivalent(Planck18)
    for bad in ("", "bogus=1", "H0 70", "1, 2"):
        panel.form.set_value("changes", bad)
        with pytest.raises(ParseError):
            panel.clone()
    for bad in ("Om0=-3", "H0=-5", "H0=0"):
        panel.form.set_value("changes", bad)
        with pytest.raises(ParseError):
            panel.clone()
    panel.selector.model.setCurrentText("WMAP9")
    panel.set_default()
    assert cosmology.default_cosmology.get().name == "WMAP9"
    panel.reset_default()
    assert cosmology.default_cosmology.get().name == "Planck18"


def test_io_roundtrip_and_formats(qtbot, ws, tmp_path, monkeypatch):
    panel = make_panel(qtbot, ws, ct.CompareIOPanel)
    assert "ascii.ecsv" in ct.registry_formats(ct.readwrite_registry, "Write")
    assert "ascii.latex" not in ct.registry_formats(ct.readwrite_registry, "Read")
    path = str(tmp_path / "c.ecsv")
    monkeypatch.setattr(panel, "ask_save_path", lambda *a, **k: path)
    monkeypatch.setattr(panel, "ask_open_path", lambda *a, **k: path)
    panel.form.set_value("wfmt", "ascii.ecsv")
    panel.write()
    panel.form.set_value("rfmt", "ascii.ecsv")
    panel.form.set_value("cname", "back")
    panel.read()
    assert ws.get("back").is_equivalent(Planck18)
    for fmt in ct.registry_formats(ct.convert_registry, "Write"):
        panel.form.set_value("tfmt", fmt)
        panel.to_format()
        assert fmt in panel.result.toPlainText()
    panel.form.set_value("tfmt", "yaml")
    panel.to_format()
    yaml_text = Planck18.to_format("yaml")
    panel.form.set_value("text", yaml_text)
    panel.form.set_value("cname", "from_yaml")
    panel.from_text()
    assert ws.get("from_yaml").is_equivalent(Planck18)
    panel.form.set_value("text", "{'cosmology': 'FlatLambdaCDM', 'H0': 70, 'Om0': 0.3}")
    panel.form.set_value("cname", "from_map")
    panel.from_text()
    assert ws.get("from_map").Om0 == 0.3
    panel.form.set_value("text", "not valid : [")
    with pytest.raises(ParseError):
        panel.from_text()
    monkeypatch.setattr(panel, "ask_open_path", lambda *a, **k: str(tmp_path / "missing.ecsv"))
    with pytest.raises(ParseError):
        panel.read()


def test_describe_flags_unphysical():
    c = FlatLambdaCDM(H0=70, Om0=2)
    assert "Warnings" in ct.describe(c)
    assert "Planck" in ct.describe(Planck18)


def test_background_threads_end_to_end(qtbot, ws):
    from astrotools_adv.core import tasks
    tasks.set_synchronous(False)
    panel = make_panel(qtbot, ws, ct.CalculatorPanel)
    panel.form.set_value("z", "1")
    panel.compute()
    qtbot.waitUntil(lambda: "cosmo_table" in ws, timeout=20000)
    qtbot.waitUntil(lambda: panel._busy == 0, timeout=20000)
    assert ws.get("cosmo_table")["luminosity_distance"][0] == pytest.approx(6791.2689, rel=1e-6)
