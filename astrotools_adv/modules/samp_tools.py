"""SAMP: run a hub, connect a client, exchange tables/images/coordinates with other apps.

astropy.samp is deprecated since astropy 8.0 in favour of ``pyvo.samp`` (same API),
so ``pyvo.samp`` is preferred and ``astropy.samp`` is the fallback.
"""
from __future__ import annotations

import importlib
import os
import shutil
import tempfile
import threading
import warnings
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Sequence

from astropy.table import Table
from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import QApplication, QLabel, QWidget

from ..core.parsing import ParseError, format_exception, parse_skycoord, safe_eval
from ..core.registry import ModuleSpec
from ..core.widgets import ModulePanel, WorkspaceCombo
from ..core.workspace import Workspace

STANDARD_MTYPES = ("samp.app.ping", "table.load.votable", "table.load.fits",
                   "image.load.fits", "coord.pointAt.sky")
MESSAGE_TYPES = ("table.load.votable", "image.load.fits", "coord.pointAt.sky", "custom")
CALL_TIMEOUT_S = 10


class SampError(RuntimeError):
    """User-presentable SAMP failure."""


def samp_api() -> Any:
    """The SAMP implementation module (``pyvo.samp`` or the deprecated ``astropy.samp``)."""
    try:
        import pyvo.samp as samp
        return samp
    except ImportError:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            import astropy.samp as samp
        return samp


def _coerce_samp_value(value: Any, path: str = "params") -> Any:
    """SAMP values are strings, lists and maps only; numbers are sent as strings."""
    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, (int, float)) or hasattr(value, "item") and getattr(value, "ndim", 1) == 0:
        return str(value.item() if hasattr(value, "item") else value)
    if isinstance(value, (list, tuple)):
        return [_coerce_samp_value(v, path) for v in value]
    if isinstance(value, dict):
        return {str(k): _coerce_samp_value(v, f"{path}.{k}") for k, v in value.items()}
    raise ParseError(f"{path}: {type(value).__name__} cannot be sent over SAMP "
                     "(use strings, numbers, lists or dicts).")


def parse_params(text: str) -> Dict[str, Any]:
    """``"url='file:///x', n=3"`` or ``"{'a': 1}"`` -> SAMP-safe dict."""
    text = (text or "").strip()
    if not text:
        return {}
    value = safe_eval(text if text.startswith("{") else f"dict({text})", {"dict": dict})
    if not isinstance(value, dict):
        raise ParseError("Parameters must be name=value pairs or a dict.")
    return _coerce_samp_value(value)


class SampSession:
    """Hub + integrated client with deterministic cleanup. GUI-free."""

    def __init__(self, on_message: Optional[Callable[[str, Dict[str, Any], str, Optional[str]], None]] = None,
                 on_log: Optional[Callable[[str], None]] = None) -> None:
        self.samp = samp_api()
        self.hub: Any = None
        self.client: Any = None
        self.on_message = on_message
        self.on_log = on_log or (lambda _t: None)
        self._tmpdir: Optional[str] = None
        self._lock = threading.RLock()

    # ---- state ----------------------------------------------------------- #
    @property
    def hub_running(self) -> bool:
        return self.hub is not None and bool(self.hub.is_running)

    @property
    def connected(self) -> bool:
        return self.client is not None and bool(self.client.is_connected)

    # ---- hub -------------------------------------------------------------- #
    def start_hub(self, lockfile: Optional[str] = None) -> None:
        with self._lock:
            if self.hub_running:
                raise SampError("The hub is already running.")
            kwargs: Dict[str, Any] = {"web_profile": False, "addr": "127.0.0.1", "pool_size": 8}
            if lockfile:
                kwargs["lockfile"] = str(lockfile)
            hub = self.samp.SAMPHubServer(**kwargs)
            try:
                hub.start()
            except Exception as exc:  # noqa: BLE001 - e.g. another hub already running
                self._safe_stop_hub(hub)
                raise SampError(f"Cannot start the hub: {format_exception(exc)}") from exc
            self.hub = hub
            self.on_log(f"Hub started (id {hub.id}).")

    @staticmethod
    def _safe_stop_hub(hub: Any) -> None:
        try:
            if hub.is_running:
                hub.stop()
        except Exception:  # noqa: BLE001 - best effort during cleanup
            pass

    def stop_hub(self) -> None:
        with self._lock:
            if self.hub is None:
                return
            self.disconnect()
            self._safe_stop_hub(self.hub)
            self.hub = None
            self.on_log("Hub stopped.")

    # ---- client ----------------------------------------------------------- #
    def connect(self, name: str = "AstroTools-ADV", lockfile: Optional[str] = None,
                extra_mtypes: Sequence[str] = ()) -> None:
        with self._lock:
            if self.connected:
                raise SampError("The client is already connected.")
            client = self.samp.SAMPIntegratedClient(
                name=name or "AstroTools-ADV",
                description="AstroTools-ADV (astropy GUI)", addr="127.0.0.1")
            try:
                if lockfile and not self.hub_running:
                    helpers = importlib.import_module(self.samp.__name__ + ".lockfile_helpers")
                    client.connect(hub_params=helpers.read_lockfile(lockfile))
                elif self.hub_running:
                    client.connect(hub=self.hub)
                else:
                    client.connect()
            except Exception as exc:  # noqa: BLE001 - SAMP/XML-RPC/OS errors vary
                self._safe_disconnect(client)
                raise SampError(
                    "No SAMP hub could be reached. Start the built-in hub, or start a "
                    f"hub in another application (Aladin, TOPCAT, ...). ({format_exception(exc)})"
                ) from exc
            self.client = client
            for mtype in dict.fromkeys([*STANDARD_MTYPES, *extra_mtypes]):
                client.bind_receive_notification(mtype, self._notification)
                client.bind_receive_call(mtype, self._call)
            self.on_log(f"Client connected as {client.get_public_id()}.")

    @staticmethod
    def _safe_disconnect(client: Any) -> None:
        try:
            if client.is_connected:
                client.disconnect()
        except Exception:  # noqa: BLE001 - hub may already be gone
            pass

    def disconnect(self) -> None:
        with self._lock:
            if self.client is None:
                return
            self._safe_disconnect(self.client)
            self.client = None
            self.on_log("Client disconnected.")

    # ---- receiving -------------------------------------------------------- #
    def _notification(self, private_key: str, sender_id: str, mtype: str,
                      params: Dict[str, Any], extra: Any) -> None:
        if self.on_message:
            self.on_message(mtype, dict(params), sender_id, None)

    def _call(self, private_key: str, sender_id: str, msg_id: str, mtype: str,
              params: Dict[str, Any], extra: Any) -> None:
        if self.on_message:
            self.on_message(mtype, dict(params), sender_id, msg_id)
        try:
            self.client.ereply(msg_id, "samp.ok", result={})
        except Exception as exc:  # noqa: BLE001 - sender may have left
            self.on_log(f"Reply failed: {format_exception(exc)}")

    # ---- querying / sending ------------------------------------------------ #
    def require_client(self) -> Any:
        if not self.connected:
            raise SampError("Not connected to a SAMP hub. Connect the client first.")
        return self.client

    def clients(self) -> Table:
        """Registered clients with name, description and subscribed message types."""
        client = self.require_client()
        me = client.get_public_id()
        rows = []
        # the hub never lists the caller itself, so add this application explicitly
        for cid in [me, *client.get_registered_clients()]:
            try:
                meta = client.get_metadata(cid)
            except Exception:  # noqa: BLE001 - client vanished meanwhile
                meta = {}
            try:
                subs = ", ".join(sorted(client.get_subscriptions(cid)))
            except Exception:  # noqa: BLE001
                subs = ""
            rows.append((cid + (" (this app)" if cid == me else ""),
                         str(meta.get("samp.name", "")),
                         str(meta.get("samp.description.text", "")), subs))
        cols = list(zip(*rows)) if rows else [(), (), (), ()]
        return Table([list(c) for c in cols], names=("id", "name", "description", "subscriptions"),
                     dtype=[str] * 4)

    def send(self, mtype: str, params: Dict[str, Any], target: Optional[str] = None,
             wait: bool = False) -> str:
        """Notify ``target`` (or everyone); with ``wait`` a call is made and answered."""
        client = self.require_client()
        if not mtype.strip():
            raise ParseError("Message type is empty.")
        params = _coerce_samp_value(params)
        target = str(target) if target else None
        try:
            if wait:
                if not target:
                    raise ParseError("Choose a specific client to call and wait for a reply.")
                resp = client.call_and_wait(target, {"samp.mtype": mtype, "samp.params": params},
                                            str(CALL_TIMEOUT_S))
                return f"{target} replied: {dict(resp)}"
            if target:
                client.enotify(target, mtype, **params)
                return f"Sent {mtype} to {target}."
            recipients = client.enotify_all(mtype, **params)
            return f"Sent {mtype} to {len(recipients)} client(s): {', '.join(recipients) or '-'}"
        except ParseError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise SampError(f"Sending {mtype} failed: {format_exception(exc)}") from exc

    # ---- files ----------------------------------------------------------- #
    def tmp_path(self, filename: str) -> str:
        if self._tmpdir is None:
            self._tmpdir = tempfile.mkdtemp(prefix="astrotools_samp_")
        return os.path.join(self._tmpdir, filename)

    def table_message(self, table: Table, name: str) -> Dict[str, str]:
        path = self.tmp_path(f"{_slug(name)}.xml")
        table.write(path, format="votable", overwrite=True)
        return {"url": Path(path).as_uri(), "table-id": name, "name": name}

    def image_message(self, obj: Any, name: str) -> Dict[str, str]:
        from astropy.io import fits

        path = self.tmp_path(f"{_slug(name)}.fits")
        if isinstance(obj, fits.HDUList):
            obj.writeto(path, overwrite=True)
        elif isinstance(obj, (fits.PrimaryHDU, fits.ImageHDU)):
            fits.HDUList([fits.PrimaryHDU(obj.data, obj.header)]).writeto(path, overwrite=True)
        elif hasattr(obj, "write") and hasattr(obj, "data") and hasattr(obj, "unit"):  # CCDData
            obj.write(path, overwrite=True)
        elif hasattr(obj, "data"):  # NDData-like
            hdr = getattr(getattr(obj, "wcs", None), "to_header", lambda: None)()
            fits.PrimaryHDU(obj.data, hdr).writeto(path, overwrite=True)
        else:
            raise ParseError(f"{name!r} ({type(obj).__name__}) is not an image object.")
        return {"url": Path(path).as_uri(), "image-id": name, "name": name}

    # ---- cleanup ---------------------------------------------------------- #
    def close(self) -> None:
        """Idempotent: disconnect, stop the hub, delete temporary files."""
        try:
            self.stop_hub()
            self.disconnect()
        finally:
            if self._tmpdir:
                shutil.rmtree(self._tmpdir, ignore_errors=True)
                self._tmpdir = None


def _slug(name: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in name) or "object"


def file_url_to_path(url: str) -> str:
    """``file://`` URL -> local path; anything else is refused (no automatic downloads)."""
    from urllib.parse import unquote, urlparse

    parsed = urlparse(url)
    if parsed.scheme != "file":
        raise SampError(f"Only file:// URLs are loaded automatically (got {url!r}).")
    return unquote(parsed.path)


# --------------------------------------------------------------------------- #
# Panel
# --------------------------------------------------------------------------- #
class SampPanel(ModulePanel):
    message_received = pyqtSignal(str, object, str, object)
    log_line = pyqtSignal(str)

    def __init__(self, ws: Workspace) -> None:
        super().__init__(ws)
        self.session = SampSession(on_message=self._emit_message, on_log=self._session_log)
        self.message_received.connect(self._on_message)
        self.log_line.connect(self._on_log)

        f = self.form
        f.add_text("lockfile", "Lockfile", "", "Blank = standard ~/.samp (what Aladin/TOPCAT use).",
                   placeholder="default (~/.samp)")
        f.add_text("name", "Client name", "AstroTools-ADV")
        f.add_multiline("extra", "Extra listen types", "",
                        "Additional message types to receive, one per line.", height=50)
        f.add_check("autoload", "Load received tables into workspace", True,
                    "Only local file:// URLs are loaded.")
        f.add_combo("target", "Send to", ["(all clients)"])
        f.add_combo("mtype", "Message", MESSAGE_TYPES)
        self.object_combo = WorkspaceCombo(ws)
        f.add_widget("object", "Workspace object", self.object_combo)
        f.add_text("url", "File / URL", "", "Image file path or URL for image.load.fits. "
                   "When filled in, it is sent instead of the workspace object.")
        f.add_text("coord", "Coordinate", "10.68 41.27", "For coord.pointAt.sky, e.g. '10.68 41.27' "
                   "or '00h42m44s +41d16m09s'.")
        f.add_text("custom", "Custom type", "", "Message type when Message = custom.")
        f.add_text("params", "Parameters", "", "name=value, ... or {'a': 'b'} (custom messages).")
        f.add_check("wait", "Call and wait for reply", False,
                    "Needs a specific client; times out after 10 s.")

        self.state_label = QLabel()
        self.controls_layout.insertWidget(0, self.state_label)
        self.add_button("Start hub", self.start_hub, "Run a SAMP hub inside this app.")
        self.add_button("Stop hub", self.stop_hub)
        self.add_button("Connect client", self.connect_client)
        self.add_button("Disconnect client", self.disconnect_client)
        self.add_button("Refresh clients", self.refresh_clients)
        self.add_button("Send message", self.send_message)
        self.log = self.add_output("Log")
        self.clients_view = self.add_table("Clients")
        self._update_state()
        app = QApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(self.session.close)
        self.destroyed.connect(self.session.close)  # session is a plain object: safe

    def closeEvent(self, event: Any) -> None:  # noqa: N802 - Qt API
        self.session.close()
        super().closeEvent(event)

    # ---- helpers --------------------------------------------------------- #
    def _lockfile(self) -> Optional[str]:
        return self.form.value("lockfile") or None

    def _update_state(self) -> None:
        self.state_label.setText(
            f"Hub: {'running' if self.session.hub_running else 'stopped'}  |  "
            f"Client: {'connected' if self.session.connected else 'disconnected'}")

    def _session_log(self, text: str) -> None:
        try:
            self.log_line.emit(text)
        except (RuntimeError, AttributeError):
            pass  # panel already destroyed (interpreter shutdown): nothing left to show

    def _emit_message(self, mtype: str, params: Dict[str, Any], sender: str,
                      msg_id: Optional[str]) -> None:
        try:
            self.message_received.emit(mtype, params, sender, msg_id)  # SAMP thread -> GUI
        except (RuntimeError, AttributeError):
            pass

    def _on_log(self, text: str) -> None:
        self.log.append_text(text)
        self._update_state()

    def _on_message(self, mtype: str, params: Dict[str, Any], sender: str, msg_id: Any) -> None:
        kind = "call" if msg_id else "notification"
        self.log.append_text(f"<- {mtype} from {sender} ({kind}): {params}")
        if self.form.value("autoload") and mtype in ("table.load.votable", "table.load.fits"):
            self.guard(lambda: self._load_table(mtype, params))

    def _load_table(self, mtype: str, params: Dict[str, Any]) -> None:
        path = file_url_to_path(str(params.get("url", "")))
        fmt = "votable" if mtype.endswith("votable") else "fits"
        name = str(params.get("name") or params.get("table-id") or "samp_table")

        def read() -> Table:
            return Table.read(path, format=fmt)

        def done(table: Table) -> None:
            stored = self.ws.put(_slug(name), table)
            self.log.append_text(f"   loaded {len(table)} rows into workspace as {stored!r}")

        self.run(read, done, busy_text="Loading received table ...")

    # ---- actions ----------------------------------------------------------- #
    def _do(self, fn: Callable[[], None]) -> None:
        def wrapped() -> None:
            try:
                fn()
            except (SampError, ParseError) as exc:
                self.log.append_text(f"! {exc}")
                self.set_status(str(exc))
            finally:
                self._update_state()
        self.guard(wrapped)

    def start_hub(self) -> None:
        self._do(lambda: self.session.start_hub(self._lockfile()))

    def stop_hub(self) -> None:
        self._do(self.session.stop_hub)

    def connect_client(self) -> None:
        extra = [ln.strip() for ln in self.form.value("extra").splitlines() if ln.strip()]
        self._do(lambda: (self.session.connect(self.form.value("name"), self._lockfile(), extra),
                          self.refresh_clients()))

    def disconnect_client(self) -> None:
        self._do(self.session.disconnect)

    def refresh_clients(self) -> None:
        def go() -> None:
            table = self.session.clients()
            self.clients_view.set_table(table)
            combo = self.form.fields["target"]
            keep = combo.currentData()
            combo.clear()
            combo.addItem("(all clients)", None)
            me = self.session.client.get_public_id()
            for row in table:
                cid = str(row["id"]).replace(" (this app)", "")
                if cid != me and cid != "cli#hub":
                    combo.addItem(f"{cid}  {row['name']}", cid)
            idx = combo.findData(keep) if keep else -1
            combo.setCurrentIndex(max(idx, 0))
        self._do(go)

    def build_message(self) -> tuple:
        """``(mtype, params)`` for the Send form."""
        v = self.form.values()
        kind = v["mtype"]
        if kind == "table.load.votable":
            table = self.object_combo.selected()
            if not isinstance(table, Table):
                raise ParseError("Select a table in 'Workspace object'.")
            return kind, self.session.table_message(table, self.object_combo.currentText())
        if kind == "image.load.fits":
            if v["url"]:  # an explicit path/URL wins; the workspace combo is never empty-valued
                url = v["url"] if "://" in v["url"] else Path(v["url"]).resolve().as_uri()
                return kind, {"url": url}
            if not self.object_combo.currentText():
                raise ParseError("Enter a file path / URL or choose a workspace image.")
            return kind, self.session.image_message(self.object_combo.selected(),
                                                    self.object_combo.currentText())
        if kind == "coord.pointAt.sky":
            c = parse_skycoord(v["coord"]).icrs
            return kind, {"ra": repr(float(c.ra.deg)), "dec": repr(float(c.dec.deg))}
        return v["custom"], parse_params(v["params"])

    def send_message(self) -> None:
        def go() -> None:
            self.session.require_client()  # fail early with the "connect first" message
            mtype, params = self.build_message()
            target = self.form.fields["target"].currentData()
            result = self.session.send(mtype, params, target, wait=self.form.value("wait"))
            self.log.append_text(f"-> {result}")
        self._do(go)


def _make(ws: Workspace) -> QWidget:
    return SampPanel(ws)


SPECS = [ModuleSpec("samp", "SAMP", "Online", _make,
                    "Run a SAMP hub and exchange tables, images and coordinates with other apps")]
