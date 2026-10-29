import os
import threading
import time

import pytest
from astropy.io import fits
from astropy.table import Table

from astrotools_adv.core.parsing import ParseError
from astrotools_adv.modules import samp_tools as st


def _samp_threads():
    return [t for t in threading.enumerate() if t is not threading.main_thread()
            and not t.daemon and t.is_alive()]


def wait_for(cond, timeout=8.0):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.05)
    return False


@pytest.fixture
def lockfile(tmp_path):
    return str(tmp_path / "samp-hub")


@pytest.fixture
def local_hub(lockfile):
    """A session owning a hub bound to a temporary lockfile (never touches ~/.samp)."""
    sess = st.SampSession()
    try:
        sess.start_hub(lockfile)
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"sandbox does not allow a local SAMP hub: {exc}")
    yield sess
    sess.close()


def test_parse_params():
    assert st.parse_params("") == {}
    assert st.parse_params("a='x', n=3, f=1.5, l=[1, 2]") == {"a": "x", "n": "3", "f": "1.5",
                                                               "l": ["1", "2"]}
    assert st.parse_params("{'k': True}") == {"k": "true"}
    with pytest.raises(ParseError):
        st.parse_params("a=Table()")  # unsupported value
    with pytest.raises(ParseError):
        st.parse_params("a=")  # syntax error


def test_file_url_to_path(tmp_path):
    f = tmp_path / "my table.xml"
    assert st.file_url_to_path(f.as_uri()) == str(f)
    with pytest.raises(st.SampError):
        st.file_url_to_path("http://example.org/x.xml")


def test_no_hub_gives_clear_error(tmp_path):
    sess = st.SampSession()
    with pytest.raises(st.SampError, match="No SAMP hub"):
        sess.connect("x", lockfile=str(tmp_path / "does-not-exist"))
    with pytest.raises(st.SampError, match="Not connected"):
        sess.clients()
    with pytest.raises(st.SampError, match="Not connected"):
        sess.send("coord.pointAt.sky", {})
    sess.close()


def test_hub_roundtrip_and_messages(local_hub, lockfile):
    got = []
    receiver = st.SampSession(on_message=lambda m, p, s, i: got.append((m, p, s, i)))
    receiver.connect("receiver", lockfile=lockfile, extra_mtypes=["my.custom.type"])
    local_hub.connect("sender")
    assert os.path.exists(lockfile) and local_hub.hub_running and local_hub.connected

    names = list(local_hub.clients()["name"])
    assert "receiver" in names and "sender" in names
    with pytest.raises(st.SampError):
        local_hub.start_hub(lockfile)  # already running

    # notification to everyone, then targeted, then a custom type
    local_hub.send("coord.pointAt.sky", {"ra": "10.5", "dec": "-3"})
    assert wait_for(lambda: got)
    assert got[0][0] == "coord.pointAt.sky" and got[0][1] == {"ra": "10.5", "dec": "-3"}
    rid = [r["id"] for r in local_hub.clients() if r["name"] == "receiver"][0]
    local_hub.send("my.custom.type", {"x": "1"}, target=rid)
    assert wait_for(lambda: len(got) == 2) and got[1][0] == "my.custom.type"

    # call-and-wait returns the receiver's automatic reply
    reply = local_hub.send("samp.app.ping", {}, target=rid, wait=True)
    assert "replied" in reply and "samp.ok" in reply
    with pytest.raises(ParseError):
        local_hub.send("samp.app.ping", {}, wait=True)  # needs a target

    receiver.close()
    local_hub.close()
    assert not local_hub.hub_running and not local_hub.connected
    assert wait_for(lambda: not _samp_threads()), _samp_threads()
    local_hub.close()  # idempotent


def test_table_and_image_messages(tmp_path):
    sess = st.SampSession()
    t = Table({"a": [1, 2]})
    msg = sess.table_message(t, "my table")
    path = st.file_url_to_path(msg["url"])
    assert Table.read(path, format="votable")["a"].tolist() == [1, 2]
    hdul = fits.HDUList([fits.PrimaryHDU([[1, 2], [3, 4]])])
    img = sess.image_message(hdul, "img")
    assert fits.getdata(st.file_url_to_path(img["url"])).shape == (2, 2)
    with pytest.raises(ParseError):
        sess.image_message(42, "x")
    tmpdir = os.path.dirname(path)
    sess.close()
    assert not os.path.exists(tmpdir)


def test_panel_end_to_end(qtbot, ws, lockfile, monkeypatch):
    shown = []
    monkeypatch.setattr("astrotools_adv.core.widgets.error_box",
                        lambda parent, exc, detail="": shown.append(exc))
    panel = st.SampPanel(ws)
    qtbot.addWidget(panel)
    panel.form.set_value("lockfile", lockfile)
    panel.form.set_value("name", "gui")
    panel.send_message()  # not connected -> logged, no dialog
    assert "Not connected" in panel.log.toPlainText()

    panel.start_hub()
    if not panel.session.hub_running:
        pytest.skip("sandbox does not allow a local SAMP hub")
    panel.connect_client()
    assert panel.session.connected and "connected" in panel.state_label.text()
    assert panel.clients_view.model.rowCount() >= 2

    got = []
    other = st.SampSession(on_message=lambda m, p, s, i: got.append((m, p)))
    other.connect("other", lockfile=lockfile)
    panel.refresh_clients()
    combo = panel.form.fields["target"]
    assert combo.count() == 2 and "other" in combo.itemText(1)

    # coord message built from the form reaches the other app
    panel.form.set_value("mtype", "coord.pointAt.sky")
    panel.form.set_value("coord", "00h42m44s +41d16m09s")
    panel.send_message()
    assert wait_for(lambda: got)
    assert float(got[0][1]["ra"]) == pytest.approx(10.6833, abs=1e-3)

    # a table in the workspace is exported as a VOTable the other app can read
    ws.put("cat", Table({"x": [1.0, 2.0]}))
    panel.object_combo.setCurrentIndex(panel.object_combo.findText("cat"))
    panel.form.set_value("mtype", "table.load.votable")
    panel.send_message()
    assert wait_for(lambda: len(got) == 2)
    assert Table.read(st.file_url_to_path(got[1][1]["url"]), format="votable")["x"].tolist() == [1.0, 2.0]

    # incoming table.load.votable is loaded into the workspace
    other_msg = other.table_message(Table({"y": [5, 6, 7]}), "from_other")
    my_id = panel.session.client.get_public_id()
    other.send("table.load.votable", other_msg, target=my_id)
    qtbot.waitUntil(lambda: "from_other" in ws, timeout=8000)
    assert len(ws.get("from_other")) == 3

    # bad inputs are shown in the log, never raised
    panel.form.set_value("mtype", "custom")
    panel.send_message()
    assert "Message type is empty" in panel.log.toPlainText()
    assert not shown

    other.close()
    panel.session.close()
    assert not panel.session.hub_running
    assert wait_for(lambda: not _samp_threads()), _samp_threads()


def test_image_message_prefers_explicit_url_over_workspace_object(qtbot, ws, tmp_path):
    """The workspace combo always has a current item, so it must not shadow the path field."""
    ws.put("a_table", Table({"x": [1.0]}))          # not an image: would raise if it were used
    panel = st.SampPanel(ws)
    qtbot.addWidget(panel)
    img = tmp_path / "m.fits"
    fits.PrimaryHDU([[1, 2], [3, 4]]).writeto(img)
    panel.form.set_value("mtype", "image.load.fits")
    panel.form.set_value("url", str(img))
    mtype, params = panel.build_message()
    assert mtype == "image.load.fits" and params == {"url": img.resolve().as_uri()}
    panel.form.set_value("url", "")
    with pytest.raises(ParseError):                 # falls back to the (non-image) workspace object
        panel.build_message()
    panel.session.close()


def test_session_close_after_panel_destroyed_does_not_raise(qtbot, ws, lockfile):
    """At interpreter exit the session may be closed after the panel's C++ object is gone."""
    from PyQt5 import sip

    panel = st.SampPanel(ws)
    try:
        panel.session.start_hub(lockfile)
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"sandbox does not allow a local SAMP hub: {exc}")
    session = panel.session
    sip.delete(panel)
    session.close()                 # used to raise AttributeError from on_log -> abort
    assert not session.hub_running
