"""Shared test helpers for the coordinates tests."""
import pytest


@pytest.fixture(autouse=True)
def errors(monkeypatch):
    """Collect error dialogs instead of opening them.

    Tests that expect dialogs assert on the list and then ``errors.clear()``;
    anything left over at teardown fails the test.
    """
    shown = []
    monkeypatch.setattr("astrotools_adv.core.widgets.error_box",
                        lambda parent, exc, detail="": shown.append(exc))
    yield shown
    assert not shown, f"unexpected error dialog(s): {shown!r}"
