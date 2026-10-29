import numpy as np
import pytest
from astropy import constants as const
from astropy import units as u

from astrotools_adv.core.parsing import ParseError
from astrotools_adv.modules import units_constants as m


@pytest.fixture(autouse=True)
def dialogs(monkeypatch):
    """Collect error dialogs instead of opening modal boxes."""
    shown = []
    monkeypatch.setattr("astrotools_adv.core.widgets.error_box",
                        lambda parent, exc, detail="": shown.append(exc))
    return shown


def panel(qtbot, ws, key):
    spec = next(s for s in m.SPECS if s.key == key)
    w = spec.factory(ws)
    qtbot.addWidget(w)
    return w


def convert(p, value, target, equivalency="none", p1="", p2="", extra=""):
    for k, v in dict(value=value, target=target, equivalency=equivalency, param1=p1,
                     param2=p2, extra=extra).items():
        p.form.set_value(k, v)
    p.convert()


def result_value(p):
    for line in p.out.toPlainText().splitlines():
        if line.startswith("Result:"):
            number, unit = line.split(":", 1)[1].split(None, 1)
            return float(number), unit.strip()
    raise AssertionError(p.out.toPlainText())


def test_specs_are_basics_and_unique(qtbot, ws):
    assert len({s.key for s in m.SPECS}) == len(m.SPECS) == 4
    for s in m.SPECS:
        assert s.category == "Basics"
        assert s.factory(ws) is not None


# ---- converter ------------------------------------------------------------- #
def test_parsec_to_metres(qtbot, ws, dialogs):
    p = panel(qtbot, ws, "unit_converter")
    convert(p, "1 pc", "m")
    value, unit = result_value(p)
    assert unit == "m" and value == pytest.approx(3.0856775814913673e16, rel=1e-12)
    assert not dialogs


def test_expression_and_astropy_string_syntax(qtbot, ws, dialogs):
    p = panel(qtbot, ws, "unit_converter")
    convert(p, "3 m**2", "cm2")
    assert result_value(p)[0] == pytest.approx(3e4)
    convert(p, "2*u.km", "m")
    assert result_value(p)[0] == pytest.approx(2000.0)
    convert(p, "np.linspace(1, 3, 3) * u.km", "m")
    assert "[1000. 2000. 3000.] m" in p.out.toPlainText()
    assert not dialogs


def test_spectral_equivalency(qtbot, ws):
    p = panel(qtbot, ws, "unit_converter")
    convert(p, "500 nm", "THz", "spectral")
    assert result_value(p)[0] == pytest.approx(299792458 / 500e-9 / 1e12, rel=1e-9)


def test_doppler_radio_equivalency(qtbot, ws):
    p = panel(qtbot, ws, "unit_converter")
    convert(p, "100 km/s", "MHz", "doppler_radio", "1420.405751 MHz")
    expected = 1420.405751 * (1 - 100e3 / 299792458)
    assert result_value(p)[0] == pytest.approx(expected, rel=1e-9)
    convert(p, "100 km/s", "MHz", "doppler_optical", "1420.405751 MHz")
    assert result_value(p)[0] == pytest.approx(1420.405751 / (1 + 100e3 / 299792458), rel=1e-9)
    convert(p, "100 km/s", "MHz", "doppler_relativistic", "1420.405751 MHz")
    beta = 100e3 / 299792458
    assert result_value(p)[0] == pytest.approx(
        1420.405751 * np.sqrt((1 - beta) / (1 + beta)), rel=1e-9)


def test_other_equivalencies(qtbot, ws):
    p = panel(qtbot, ws, "unit_converter")
    convert(p, "1 arcsec", "pc", "parallax")
    assert result_value(p)[0] == pytest.approx(1.0)
    convert(p, "0 deg_C", "K", "temperature")
    assert result_value(p)[0] == pytest.approx(273.15)
    convert(p, "1 kg", "J", "mass_energy")
    assert result_value(p)[0] == pytest.approx(299792458.0 ** 2)
    convert(p, "1 Jy", "erg/(s cm2 Hz)", "spectral_density", "500 nm")
    assert result_value(p)[0] == pytest.approx(1e-23)
    convert(p, "1 Jy", "erg/(s cm2 AA)", "spectral_density", "5000 AA")
    assert result_value(p)[0] == pytest.approx(1e-23 * 299792458 * 1e10 / 5000.0 ** 2, rel=1e-6)
    convert(p, "0.5 arcsec", "pix", "pixel_scale", "0.25 arcsec/pix")
    assert result_value(p)[0] == pytest.approx(2.0)
    convert(p, "500 nm", "THz", "none", extra="spectral")
    assert result_value(p)[0] == pytest.approx(599.584916, rel=1e-6)


def test_brightness_temperature(qtbot, ws, dialogs):
    p = panel(qtbot, ws, "unit_converter")
    convert(p, "1 K", "Jy/beam", "brightness_temperature", "100 GHz", "10 arcsec2")
    expected = (1 * u.K).to(u.Jy / u.beam, u.brightness_temperature(
        100 * u.GHz, beam_area=10 * u.arcsec ** 2))
    assert result_value(p)[0] == pytest.approx(expected.value)
    assert not dialogs


def test_logarithmic_units_convert(qtbot, ws):
    p = panel(qtbot, ws, "unit_converter")
    convert(p, "0 mag(AB)", "Jy")
    assert result_value(p)[0] == pytest.approx(3631.0)


def test_converter_errors_show_dialogs(qtbot, ws, dialogs):
    p = panel(qtbot, ws, "unit_converter")
    for bad in [("", "m", "none", "", ""), ("5", "m", "none", "", ""),
                ("5 m", "kg", "none", "", ""), ("5 m", "notaunit", "none", "", ""),
                ("5 m", "cm", "doppler_radio", "", ""), ("5 m", "cm", "doppler_radio", "junk", ""),
                ("5 m", "cm", "none", "", "bogus_equiv"), ("garbage !!", "m", "none", "", "")]:
        dialogs.clear()
        convert(p, bad[0], bad[1], bad[2], bad[3], extra=bad[4])
        assert len(dialogs) == 1 and isinstance(dialogs[0], ParseError), bad


def test_converter_without_target_and_store(qtbot, ws, dialogs):
    p = panel(qtbot, ws, "unit_converter")
    p.store_last()
    assert len(dialogs) == 1 and "no result" in str(dialogs[0])
    convert(p, "1 AU", "")
    text = p.out.toPlainText()
    assert "SI:" in text and "CGS:" in text and "length" in text
    p.form.set_value("store_name", " dist ")
    p.store_last()
    assert ws.get("dist") == 1 * u.AU


# ---- explorer ---------------------------------------------------------------- #
def test_analyze_unit(qtbot, ws, dialogs):
    p = panel(qtbot, ws, "unit_explorer")
    p.form.set_value("unit", "km / s")
    p.analyze()
    text = p.out.toPlainText()
    assert "speed/velocity" in text and "1000.0" in text and "bases:" in text
    p.form.set_value("unit", "")
    p.analyze()
    assert isinstance(dialogs[-1], ParseError)
    p.form.set_value("unit", "nonsense_unit")
    p.analyze()
    assert isinstance(dialogs[-1], ParseError)


def test_analyze_function_unit_does_not_crash(qtbot, ws, dialogs):
    p = panel(qtbot, ws, "unit_explorer")
    p.form.set_value("unit", "mag(AB)")
    p.analyze()
    assert "mag(AB)" in p.out.toPlainText() and not dialogs


def test_equivalent_units_and_registry_search(qtbot, ws, dialogs):
    p = panel(qtbot, ws, "unit_explorer")
    p.form.set_value("unit", "m")
    p.find_equivalent()
    names = list(p.table.model._table["unit"])
    assert "pc" in names and "AU" in names and "km" not in names
    p.form.set_value("prefixes", True)
    p.find_equivalent()
    assert "km" in list(p.table.model._table["unit"])
    p.form.set_value("query", "parsec")
    p.search()
    assert "pc" in list(p.table.model._table["unit"])
    p.form.set_value("query", "zzzzqqq")
    p.search()
    assert len(p.table.model._table) == 0 and not dialogs
    p.form.set_value("query", " ")
    p.search()
    assert isinstance(dialogs[-1], ParseError)


def test_prefix_table(qtbot, ws):
    p = panel(qtbot, ws, "unit_explorer")
    p.prefixes()
    t = p.table.model._table
    kilo = t[t["prefix"] == "kilo"][0]
    assert kilo["factor"] == 1000.0
    assert t[t["prefix"] == "kibi"][0]["factor"] == 1024.0
    assert len(t) == len(m.SI_PREFIXES) + len(m.BINARY_PREFIXES)


def test_define_custom_unit(qtbot, ws, dialogs):
    explorer = panel(qtbot, ws, "unit_explorer")
    explorer.form.set_value("def_name", "smoot_test")
    explorer.form.set_value("def_expr", "1.7018 m")
    explorer.define()
    assert not dialogs
    conv = panel(qtbot, ws, "unit_converter")
    convert(conv, "10 smoot_test", "m")
    assert result_value(conv)[0] == pytest.approx(17.018)
    for name, expr in [("1bad", "1 m"), ("ok_name", ""), ("m", "2 s"), ("ok2", "foo bar")]:
        dialogs.clear()
        explorer.form.set_value("def_name", name)
        explorer.form.set_value("def_expr", expr)
        explorer.define()
        assert len(dialogs) == 1 and isinstance(dialogs[0], ParseError), (name, expr)


# ---- calculator ------------------------------------------------------------- #
def test_calculator(qtbot, ws, dialogs):
    p = panel(qtbot, ws, "quantity_calculator")
    p.form.set_value("script", "d = 10 * u.pc\nd.to(u.lyr)\n(0 * u.mag(u.AB)).to(u.Jy)\n"
                               "bogus(\nconst.c.to(u.km/u.s)")
    p.evaluate()
    text = p.out.toPlainText()
    assert "32.6156" in text and "3631.0" in text and "299792.458 km / s" in text
    assert "! Syntax error" in text and not dialogs
    assert p._last == pytest.approx(299792.458 * u.km / u.s)
    p.store_last()
    assert "calc" in ws
    p.form.set_value("script", "# only a comment")
    p.evaluate()
    assert isinstance(dialogs[-1], ParseError)


def test_calculator_logarithmic_and_forbidden(qtbot, ws):
    p = panel(qtbot, ws, "quantity_calculator")
    p.form.set_value("script", "Dex(2 * u.dex(u.cm / u.s**2)).physical\n"
                               "(10 * u.dB(u.mW)).physical.to(u.mW)\n"
                               "u.__class__\n__import__('os')\n_x = 3")
    p.evaluate()
    text = p.out.toPlainText()
    assert "100.0 cm / s2" in text and "10.0 mW" in text
    assert text.count("!") >= 3


# ---- constants -------------------------------------------------------------- #
def row_for(table, abbrev):
    return table[table["abbrev"] == abbrev][0]


def test_constants_table_default(qtbot, ws, dialogs):
    p = panel(qtbot, ws, "constants")  # populated on construction
    t = p.table.model._table
    c = row_for(t, "c")
    assert c["value"] == 299792458.0 and c["unit"] == "m / s" and c["uncertainty"] == 0.0
    assert row_for(t, "G")["value"] == pytest.approx(const.G.value)
    assert len(t) > 30 and not dialogs


def test_constants_sets_systems_and_filter(qtbot, ws, dialogs):
    p = panel(qtbot, ws, "constants")
    for name in m.CONSTANT_SETS:
        for system in ("si", "cgs"):
            t = m.constants_table(name, system, "")
            assert len(t) > 20, (name, system)
    p.form.set_value("set", "astropyconst13")
    p.refresh()
    assert row_for(p.table.model._table, "G")["value"] == pytest.approx(6.67384e-11)
    p.form.set_value("set", "codata2018")
    p.form.set_value("system", "cgs")
    p.refresh()
    g = row_for(p.table.model._table, "G")
    assert g["value"] == pytest.approx(6.6743e-8) and g["unit"] == "cm3 / (g s2)"
    e = row_for(p.table.model._table, "e")  # EM constants have no cgs form
    assert "si" in e["system"] and e["unit"] == "C"
    p.form.set_value("filter", "boltzmann")
    p.refresh()
    assert list(p.table.model._table["abbrev"]) == ["k_B"]
    p.form.set_value("filter", "no such constant")
    p.refresh()
    assert len(p.table.model._table) == 0 and not dialogs


def test_constants_calculator(qtbot, ws, dialogs):
    p = panel(qtbot, ws, "constants")
    p.form.set_value("script", "const.c\nconst.G * (1 * u.Msun) / (1 * u.AU)**2\nconst.nope")
    p.evaluate()
    text = p.out.toPlainText()
    assert "299792458.0 m / s" in text and "! " in text
    p.form.set_value("system", "cgs")
    p.form.set_value("script", "const.G")
    p.evaluate()
    assert "cm3 / (g s2)" in p.out.toPlainText() and not dialogs
    p.store_last()
    assert ws.get("constant").unit == u.cm ** 3 / (u.g * u.s ** 2)
    with pytest.raises(ParseError):
        m.constants_of("nonexistent")
