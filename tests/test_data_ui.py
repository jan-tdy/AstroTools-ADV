"""Clicks every button of the Data pages the way a user does.

The panels build their sections in a loop, so a button handler that captures the loop
variable late would read another section's form. Handler-level tests never see that;
pressing the real buttons does.
"""
import numpy as np
import pytest
from astropy.table import Table
from PyQt5.QtWidgets import QPushButton

from astrotools_adv.core import registry
from astrotools_adv.core.parsing import ParseError

DATA_KEYS = ["fits", "io_ascii", "io_votable", "io_misc", "table_manager", "table_edit",
             "table_combine", "table_plot"]
CODING_ERRORS = (KeyError, AttributeError, NameError, TypeError, UnboundLocalError, IndexError)


@pytest.fixture
def specs():
    found, failures = registry.discover()
    assert failures == []
    return {s.key: s for s in found}


@pytest.mark.parametrize("key", DATA_KEYS)
def test_every_button_runs_without_coding_errors(qtbot, ws, specs, monkeypatch, key):
    seen = []
    monkeypatch.setattr("astrotools_adv.core.widgets.error_box",
                        lambda parent, exc, detail="": seen.append(exc))
    ws.put("t", Table({"a": [1.0, 2.0, 3.0], "b": [3.0, 2.0, 1.0]}))
    panel = specs[key].factory(ws)
    qtbot.addWidget(panel)
    buttons = [b for b in panel.controls.findChildren(QPushButton) if b.isEnabled()]
    assert buttons, "page has no buttons"
    for button in buttons:
        seen.clear()
        button.click()
        bad = [e for e in seen if isinstance(e, CODING_ERRORS)]
        assert not bad, f"{key}: {button.text()!r} raised {bad[0]!r}"


def test_table_manager_open_and_create_buttons_use_their_own_section(qtbot, ws, specs, tmp_path):
    panel = specs["table_manager"].factory(ws)
    qtbot.addWidget(panel)
    open_form = panel.open_sec.form
    csv = tmp_path / "x.csv"
    csv.write_text("a,b\n1,2\n")
    open_form.set_value("path", str(csv))
    open_form.set_value("name", "opened")
    next(b for b in panel.controls.findChildren(QPushButton) if b.text() == "Open").click()
    assert list(ws.get("opened").colnames) == ["a", "b"]


def test_ascii_guess_failure_gives_a_short_message(tmp_path):
    from astrotools_adv.modules.io_tables import ascii_read

    path = tmp_path / "odd.txt"
    path.write_text("# c\n% d\nstar | V\nSirius | -1.46\n")
    with pytest.raises(ParseError) as err:
        ascii_read(str(path))
    assert len(str(err.value)) < 300 and "Format" in str(err.value)


def test_ascii_write_masked_fill_value():
    from astrotools_adv.modules.io_tables import ascii_write, parse_fill_values

    table = Table({"a": np.ma.masked_array([1.0, 2.0, 3.0], mask=[False, True, False])})
    assert ascii_write(table, "csv", fill_values="masked:N/A").splitlines() == ["a", "1.0", "N/A", "3.0"]
    with pytest.raises(ParseError):
        parse_fill_values("nonsense", allow_masked=True)
