"""Generic astroquery browser (every service) + shared query-panel infrastructure.

Nothing here talks to the network on import or while introspecting: services
are imported lazily and their methods are inspected on the *class* so that
properties (some of which open connections) are never evaluated.

``QueryPanel`` (offline switch, timeout, result display, workspace storage) is
reused by ``astroquery_catalogs``.
"""
from __future__ import annotations

import importlib
import importlib.util
import inspect
import pkgutil
import pprint
import traceback
import types
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from astropy.table import Table
from PyQt5.QtCore import QObject, Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QCheckBox, QComboBox, QLabel, QLineEdit, QPushButton, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from ..core.parsing import ParseError, format_exception, safe_eval
from ..core.registry import ModuleSpec
from ..core.widgets import ModulePanel, ParamForm
from ..core.workspace import Workspace

# --------------------------------------------------------------------------- #
# Session-wide offline switch
# --------------------------------------------------------------------------- #
OFFLINE_MESSAGE = ("Offline mode is on - no network access is allowed. "
                   "Untick 'Offline mode' to run queries.")


class OfflineError(RuntimeError):
    """Raised instead of touching the network while offline mode is active."""


class _OfflineState(QObject):
    changed = pyqtSignal(bool)

    def __init__(self) -> None:
        super().__init__()
        self.offline = False


_STATE = _OfflineState()


def is_offline() -> bool:
    return _STATE.offline


def set_offline(flag: bool) -> None:
    flag = bool(flag)
    if flag != _STATE.offline:
        _STATE.offline = flag
        _STATE.changed.emit(flag)


def ensure_online() -> None:
    if _STATE.offline:
        raise OfflineError(OFFLINE_MESSAGE)


def offline_signal():
    """Signal ``changed(bool)`` emitted when the switch flips."""
    return _STATE.changed


# --------------------------------------------------------------------------- #
# Introspection (network free)
# --------------------------------------------------------------------------- #
SKIP_PACKAGES = {"tests", "utils", "template_module", "extern", "_astropy_init"}
SKIP_METHODS = {"login", "logout", "clear_cache", "session_info"}


@dataclass(frozen=True)
class ServiceInfo:
    label: str       # e.g. "ipac.ned"
    module: str      # e.g. "astroquery.ipac.ned"


def discover_services() -> List[ServiceInfo]:
    """All astroquery service packages (those with a ``core`` module), without importing them."""
    import astroquery

    found: List[ServiceInfo] = []

    def walk(path: Sequence[str], prefix: str, depth: int) -> None:
        for info in pkgutil.iter_modules(list(path)):
            if not info.ispkg or info.name in SKIP_PACKAGES or info.name.startswith("_"):
                continue
            full = f"{prefix}{info.name}"
            try:
                spec = importlib.util.find_spec(full)
            except (ImportError, ValueError):
                continue
            sub = list(spec.submodule_search_locations or []) if spec else []
            names = {m.name for m in pkgutil.iter_modules(sub)}
            if "core" in names:
                found.append(ServiceInfo(full[len("astroquery."):], full))
            elif depth < 2:
                walk(sub, full + ".", depth + 1)

    walk(astroquery.__path__, "astroquery.", 0)
    return sorted(found, key=lambda s: s.label)


def load_instances(module_name: str) -> Dict[str, Any]:
    """Import a service module and return its public service objects by name.

    A service object is an instance of a class defined inside the service package
    (``Simbad``, ``Vizier``, ``Gaia``...; ``BaseQuery`` or ``BaseVOQuery`` based).
    Falls back to instantiating public ``*Class`` classes with no arguments.
    Raises whatever the import raises (missing optional dependency etc.).
    """
    from astropy.config import ConfigNamespace

    mod = importlib.import_module(module_name)

    def defined_here(cls: type) -> bool:
        return getattr(cls, "__module__", "").startswith(module_name)

    instances = {n: v for n, v in vars(mod).items()
                 if not n.startswith("_") and not isinstance(v, (type, types.ModuleType))
                 and not isinstance(v, ConfigNamespace) and defined_here(type(v))
                 and any(not m.startswith("_") for m in dir(type(v)) if m.startswith(
                     ("query", "get", "list", "download", "search")))}
    if not instances:
        for n, v in vars(mod).items():
            if not n.startswith("_") and inspect.isclass(v) and n.endswith("Class") \
                    and defined_here(v):
                try:
                    instances[n] = v()
                except Exception:  # noqa: BLE001 - needs arguments; skip
                    continue
    return instances


def get_conf(module_name: str) -> Any:
    try:
        return getattr(importlib.import_module(module_name), "conf", None)
    except Exception:  # noqa: BLE001
        return None


@dataclass(frozen=True)
class MethodInfo:
    name: str
    is_async: bool


def list_methods(obj: Any) -> List[MethodInfo]:
    """Public callable methods of ``obj`` (class-level inspection; no property access)."""
    cls = type(obj)
    out: List[MethodInfo] = []
    for name in sorted(dir(cls)):
        if name.startswith("_") or name in SKIP_METHODS:
            continue
        try:
            static = inspect.getattr_static(cls, name)
        except AttributeError:
            continue
        if isinstance(static, (property, type)) or not (
                callable(static) or hasattr(static, "__func__") or hasattr(static, "__get__")):
            continue
        try:
            bound = getattr(obj, name)
        except Exception:  # noqa: BLE001
            continue
        if callable(bound) and not inspect.isclass(bound):
            out.append(MethodInfo(name, name.endswith("_async")))
    return out


def effective_signature(obj: Any, name: str) -> inspect.Signature:
    """Signature of ``obj.name``; for ``(*args, **kwargs)`` wrappers use ``name_async``."""
    def sig_of(n: str) -> Optional[inspect.Signature]:
        try:
            return inspect.signature(getattr(obj, n))
        except (TypeError, ValueError, AttributeError):
            return None

    sig = sig_of(name)
    if sig is None or _is_bare_varargs(sig):
        alt = sig_of(name + "_async") if not name.endswith("_async") else None
        if alt is not None:
            return alt
    return sig or inspect.Signature([
        inspect.Parameter("args", inspect.Parameter.VAR_POSITIONAL),
        inspect.Parameter("kwargs", inspect.Parameter.VAR_KEYWORD)])


def _is_bare_varargs(sig: inspect.Signature) -> bool:
    kinds = [p.kind for n, p in sig.parameters.items() if n not in ("self", "cls")]
    return bool(kinds) and all(k in (inspect.Parameter.VAR_POSITIONAL,
                                     inspect.Parameter.VAR_KEYWORD) for k in kinds)


def effective_doc(obj: Any, name: str) -> str:
    doc = inspect.getdoc(getattr(obj, name)) or ""
    if len(doc) < 40 and not name.endswith("_async"):
        doc = inspect.getdoc(getattr(obj, name + "_async", None) or (lambda: None)) or doc
    return doc


@dataclass(frozen=True)
class ParamInfo:
    name: str
    kind: Any                  # inspect.Parameter kind
    default: Any = inspect.Parameter.empty
    annotation: Any = inspect.Parameter.empty

    @property
    def required(self) -> bool:
        return self.default is inspect.Parameter.empty and self.kind in (
            inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD,
            inspect.Parameter.KEYWORD_ONLY)

    @property
    def is_bool(self) -> bool:
        return isinstance(self.default, bool) or self.annotation is bool

    @property
    def is_str(self) -> bool:
        return self.annotation is str or (isinstance(self.default, str) and not self.is_bool)

    @property
    def key(self) -> str:
        if self.kind is inspect.Parameter.VAR_POSITIONAL:
            return "*" + self.name
        if self.kind is inspect.Parameter.VAR_KEYWORD:
            return "**" + self.name
        return self.name


def params_from_signature(sig: inspect.Signature) -> List[ParamInfo]:
    return [ParamInfo(p.name, p.kind, p.default, p.annotation) for p in sig.parameters.values()
            if p.name != "self"]


def _default_text(p: ParamInfo) -> str:
    if p.default is inspect.Parameter.empty:
        return ""
    return repr(p.default)


def parse_param_value(text: str, param: ParamInfo, names: Optional[Dict[str, Any]] = None) -> Any:
    """Field text -> value. String parameters stay strings; everything else is a
    safe expression, falling back to the raw string (so ``M31`` or ``2 arcmin`` work)."""
    text = text.strip()
    if param.is_str:
        try:
            value = safe_eval(text, names)
            return value if isinstance(value, str) else text
        except ParseError:
            return text
    try:
        return safe_eval(text, names)
    except ParseError:
        return text


def collect_call(params: Sequence[ParamInfo], values: Dict[str, str],
                 names: Optional[Dict[str, Any]] = None) -> Tuple[list, dict]:
    """Turn raw field texts into ``(args, kwargs)``. Empty optional fields are omitted;
    empty required ones raise :class:`ParseError`."""
    K = inspect.Parameter
    args: list = []
    kwargs: dict = {}
    var_pos: list = []
    given: Dict[str, Any] = {}
    for p in params:
        text = (values.get(p.key) or "").strip()
        if p.kind is K.VAR_POSITIONAL:
            if text:
                var_pos = list(safe_eval(f"[{text}]", names))
            continue
        if p.kind is K.VAR_KEYWORD:
            if text:
                kwargs.update(safe_eval(f"dict({text})", dict(names or {}, dict=dict)))
            continue
        if not text or text == "(default)":
            if p.required:
                raise ParseError(f"Parameter '{p.name}' is required.")
            continue
        given[p.name] = parse_param_value(text, p, names)
    positional_needed = bool(var_pos)
    omitted_before = False
    for p in params:
        if p.kind in (K.VAR_POSITIONAL, K.VAR_KEYWORD):
            continue
        if p.kind is K.KEYWORD_ONLY:
            if p.name in given:
                kwargs[p.name] = given[p.name]
            continue
        # positional(-or-keyword)
        if p.kind is K.POSITIONAL_ONLY or positional_needed:
            if p.name in given:
                if omitted_before:
                    raise ParseError(f"Parameter '{p.name}' needs earlier parameters to be set.")
                args.append(given[p.name])
            elif p.default is not K.empty and positional_needed:
                args.append(p.default)
            else:
                omitted_before = True
        elif p.name in given:
            kwargs[p.name] = given[p.name]
    return args + var_pos, kwargs


# --------------------------------------------------------------------------- #
# Result normalisation
# --------------------------------------------------------------------------- #
@dataclass
class ResultSet:
    tables: List[Tuple[str, Table]] = field(default_factory=list)
    objects: List[Tuple[str, Any]] = field(default_factory=list)  # HDULists etc.
    text: str = ""


def _as_table(obj: Any) -> Optional[Table]:
    if isinstance(obj, Table):
        return obj
    for attr in ("to_table", "get_results"):
        fn = getattr(obj, attr, None)
        if callable(fn) and not isinstance(obj, (str, bytes, dict, list, tuple)):
            try:
                res = fn()
            except Exception:  # noqa: BLE001
                continue
            if isinstance(res, Table):
                return res
            if hasattr(res, "to_table"):
                return res.to_table()
    return None


def normalize_result(value: Any, label: str = "result") -> ResultSet:
    """Classify whatever a query returned into tables / objects / text."""
    rs = ResultSet()
    if value is None:
        rs.text = "The query returned no result (None)."
        return rs
    tbl = _as_table(value)
    if tbl is not None:
        rs.tables.append((label, tbl))
    elif hasattr(value, "status_code") and hasattr(value, "url"):  # requests.Response
        rs.text = f"HTTP {value.status_code}\n{value.url}"
    elif hasattr(value, "info") and hasattr(value, "writeto"):      # HDUList
        rs.objects.append((label, value))
    elif isinstance(value, dict):
        subs = [(str(k), _as_table(v)) for k, v in value.items()]
        if value and all(t is not None for _, t in subs):
            rs.tables.extend(subs)  # type: ignore[arg-type]
        else:
            rs.text = pprint.pformat(_plain(value), width=100, sort_dicts=False)
    elif isinstance(value, (list, tuple)) and value:
        subs = [_as_table(v) for v in value]
        if all(t is not None for t in subs):
            rs.tables.extend((f"{label}_{i}", t) for i, t in enumerate(subs))  # type: ignore[misc]
        elif all(hasattr(v, "writeto") for v in value):
            rs.objects.extend((f"{label}_{i}", v) for i, v in enumerate(value))
        elif all(isinstance(v, (str, int, float)) for v in value):
            t = Table({"value": list(value)})
            rs.tables.append((label, t))
        else:
            rs.text = pprint.pformat(value, width=100)
    elif isinstance(value, (list, tuple)):
        rs.text = "The query returned an empty list."
    else:
        rs.text = value if isinstance(value, str) else repr(value)
    lines: List[str] = []
    for name, t in rs.tables:
        lines.append(f"{name}: {len(t)} rows x {len(t.colnames)} columns")
        lines.append("  columns: " + ", ".join(t.colnames))
        if len(t) == 0:
            lines.append("  (no rows returned)")
    for name, o in rs.objects:
        try:
            lines.append(f"{name}: {type(o).__name__}")
            lines.extend("  " + ln for ln in str(_hdu_summary(o)).splitlines())
        except Exception:  # noqa: BLE001
            pass
    if rs.text:
        lines.append(rs.text)
    rs.text = "\n".join(lines)
    return rs


def _plain(obj: Any) -> Any:
    """Make nested astropy/numpy values printable and readable."""
    if isinstance(obj, dict):
        return {k: _plain(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_plain(v) for v in obj]
    return obj


def _hdu_summary(hdul: Any) -> str:
    try:
        return "\n".join(f"[{i}] {h.name} {type(h).__name__} {getattr(h, 'shape', '')}"
                         for i, h in enumerate(hdul))
    except Exception:  # noqa: BLE001
        return repr(hdul)


def describe_error(exc: BaseException) -> str:
    """User-facing one-paragraph explanation for a failed query."""
    if isinstance(exc, OfflineError):
        return OFFLINE_MESSAGE
    if isinstance(exc, ParseError):
        return f"Input error: {exc}"
    import socket

    network_types: Tuple[type, ...] = (socket.timeout, TimeoutError, ConnectionError)
    try:
        import requests

        network_types += (requests.exceptions.RequestException,)
    except ImportError:  # pragma: no cover
        pass
    try:
        from pyvo.dal.exceptions import DALServiceError

        network_types += (DALServiceError,)
    except ImportError:  # pragma: no cover
        pass
    if isinstance(exc, network_types):
        return (f"Network error: the service could not be reached or timed out.\n"
                f"Check your internet connection and the timeout setting.\n\n"
                f"Details: {format_exception(exc)[:600]}")
    return f"Error: {format_exception(exc)}"


def set_timeout(obj: Any, seconds: float) -> None:
    """Best-effort: apply a timeout to an astroquery service object."""
    for attr in ("TIMEOUT", "timeout"):
        if hasattr(obj, attr):
            try:
                setattr(obj, attr, seconds)
            except Exception:  # noqa: BLE001
                pass


# --------------------------------------------------------------------------- #
# Panel base
# --------------------------------------------------------------------------- #
class QueryPanel(ModulePanel):
    """Offline switch, timeout, safe worker execution and result viewer/storage."""

    def __init__(self, ws: Workspace, store_prefix: str = "query") -> None:
        super().__init__(ws)
        self._alive = {"v": True}
        self.destroyed.connect(lambda *_a, a=self._alive: a.update(v=False))
        self._gen = 0
        self._result = ResultSet()
        self._prefix = store_prefix

        self.offline_box = QCheckBox("Offline mode (block all network access)")
        self.offline_box.setChecked(is_offline())
        self.offline_box.setToolTip("Applies to every online tool until switched off.")
        self.offline_box.toggled.connect(set_offline)
        offline_signal().connect(self._sync_offline)
        self.form.add_widget("offline", "Network", self.offline_box)
        self.timeout_box = self.form.add_int("timeout", "Timeout (s)", 30, 1, 3600,
                                             "Maximum time to wait for the server.")
        self.table_view = self.add_table("Table")
        self.info = self.add_output("Info")

        self.result_combo = QComboBox()
        self.result_combo.setToolTip("Choose which returned table to display.")
        self.result_combo.currentIndexChanged.connect(self._show_selected)
        self.store_edit = QLineEdit(store_prefix)
        self.store_edit.setToolTip("Workspace name for the stored object.")
        self.store_btn = QPushButton("Store table in workspace")
        self.store_btn.clicked.connect(self.store_table)
        self.objects_btn = QPushButton("Store images/objects in workspace")
        self.objects_btn.clicked.connect(self.store_objects)
        self.save_btn = QPushButton("Save table to file...")
        self.save_btn.clicked.connect(self.save_table)
        lay = self.buttons_layout
        lay.addWidget(QLabel("Result table:"))
        lay.addWidget(self.result_combo)
        lay.addWidget(QLabel("Store as:"))
        lay.addWidget(self.store_edit)
        for b in (self.store_btn, self.objects_btn, self.save_btn):
            lay.addWidget(b)
        self._update_buttons()

    # ---- offline ------------------------------------------------------------ #
    def _sync_offline(self, flag: bool) -> None:
        if not self._alive["v"]:
            return
        self.offline_box.blockSignals(True)
        self.offline_box.setChecked(flag)
        self.offline_box.blockSignals(False)

    # ---- running ------------------------------------------------------------ #
    def execute(self, job: Callable[[float], Any], label: str = "result",
                busy_text: str = "Querying...") -> bool:
        """Run ``job(timeout_seconds)`` off the GUI thread and display its result.

        Errors become messages in the Info tab; results arriving after the panel
        was destroyed, or superseded by a newer query, are ignored.
        """
        if is_offline():
            self._message(OFFLINE_MESSAGE)
            self.set_status("Offline mode")
            return False
        self._gen += 1
        gen, timeout = self._gen, float(self.timeout_box.value())

        def work() -> Tuple[Any, ...]:
            try:
                ensure_online()
                return ("ok", normalize_result(job(timeout), label))
            except BaseException as exc:  # noqa: BLE001 - reported, never raised
                return ("err", exc, traceback.format_exc())

        def done(payload: Tuple[Any, ...]) -> None:
            if not self._alive["v"] or gen != self._gen:
                return
            if payload[0] == "ok":
                self.show_result(payload[1])
                self.set_status("Done")
            else:
                self._message(describe_error(payload[1]))
                self.set_status("Query failed")

        self.run(work, done, busy_text=busy_text)
        return True

    # ---- results ------------------------------------------------------------ #
    def _message(self, text: str) -> None:
        self._result = ResultSet(text=text)
        self.table_view.set_table(None)
        self.result_combo.blockSignals(True)
        self.result_combo.clear()
        self.result_combo.blockSignals(False)
        self.info.show_text(text)
        self.tabs.setCurrentWidget(self.info)
        self._update_buttons()

    def show_result(self, rs: ResultSet) -> None:
        self._result = rs
        self.result_combo.blockSignals(True)
        self.result_combo.clear()
        self.result_combo.addItems([n for n, _ in rs.tables])
        self.result_combo.blockSignals(False)
        self.info.show_text(rs.text or "(no output)")
        if rs.tables:
            self.result_combo.setCurrentIndex(0)
            self._show_selected()
            self.tabs.setCurrentWidget(self.table_view)
        else:
            self.table_view.set_table(None)
            self.tabs.setCurrentWidget(self.info)
        self._update_buttons()

    def _show_selected(self) -> None:
        i = self.result_combo.currentIndex()
        if 0 <= i < len(self._result.tables):
            self.table_view.set_table(self._result.tables[i][1])

    def current_table(self) -> Optional[Table]:
        i = self.result_combo.currentIndex()
        return self._result.tables[i][1] if 0 <= i < len(self._result.tables) else None

    def _update_buttons(self) -> None:
        has_table = bool(self._result.tables)
        self.store_btn.setEnabled(has_table)
        self.save_btn.setEnabled(has_table)
        self.objects_btn.setEnabled(bool(self._result.objects))

    def _store_name(self) -> str:
        name = self.store_edit.text().strip() or self._prefix
        return name

    def store_table(self) -> Optional[str]:
        table = self.current_table()
        if table is None:
            return None
        name = self.ws.put(self._store_name(), table)
        self.ws.log(f"Stored table '{name}' ({len(table)} rows).")
        self.set_status(f"Stored '{name}'")
        return name

    def store_objects(self) -> List[str]:
        stored = []
        base = self._store_name()
        for i, (label, obj) in enumerate(self._result.objects):
            name = self.ws.put(base if len(self._result.objects) == 1 else f"{base}_{i}", obj)
            stored.append(name)
        if stored:
            self.ws.log("Stored: " + ", ".join(stored))
            self.set_status(f"Stored {len(stored)} object(s)")
        return stored

    def save_table(self) -> None:
        table = self.current_table()
        if table is None:
            return
        path = self.ask_save_path("Save table", "ECSV (*.ecsv);;CSV (*.csv);;FITS (*.fits);;"
                                  "VOTable (*.xml);;HTML (*.html)", self._prefix + ".ecsv")
        if not path:
            return
        try:
            table.write(path, overwrite=True)
            self.set_status(f"Saved {path}")
        except Exception as exc:  # noqa: BLE001
            self._message(f"Could not save table: {format_exception(exc)}")


# --------------------------------------------------------------------------- #
# Generic browser
# --------------------------------------------------------------------------- #
_CFG_PARSERS = {
    "boolean": lambda s: s.strip().lower() in ("1", "true", "yes", "on"),
    "integer": int, "float": float, "string": str,
    "string_list": lambda s: [x.strip() for x in s.split(",") if x.strip()],
}


def conf_items(conf: Any) -> List[Tuple[str, Any, str, str]]:
    """``(name, value, cfgtype, description)`` for every ConfigItem of a ``conf`` object."""
    from astropy.config import ConfigItem

    items = []
    for name in sorted(dir(type(conf))):
        item = getattr(type(conf), name, None)
        if isinstance(item, ConfigItem):
            try:
                value = getattr(conf, name)
            except Exception:  # noqa: BLE001
                continue
            items.append((name, value, str(item.cfgtype), str(item.description or "")))
    return items


def set_conf_item(conf: Any, name: str, text: str) -> Any:
    """Parse ``text`` according to the item's type and assign it. Returns the new value."""
    from astropy.config import ConfigItem

    item = getattr(type(conf), name, None)
    if not isinstance(item, ConfigItem):
        raise ParseError(f"'{name}' is not a configuration item.")
    parser = _CFG_PARSERS.get(str(item.cfgtype), str)
    try:
        value = parser(text)
    except ValueError:
        raise ParseError(f"Cannot convert {text!r} for '{name}' ({item.cfgtype}).") from None
    try:
        setattr(conf, name, value)
    except Exception as exc:  # noqa: BLE001
        raise ParseError(f"Invalid value for '{name}': {exc}") from None
    return value


class GenericBrowser(QueryPanel):
    def __init__(self, ws: Workspace) -> None:
        super().__init__(ws, "aq_result")
        self._services = discover_services()
        self._instances: Dict[str, Any] = {}
        self._param_form: Optional[ParamForm] = None
        self._params: List[ParamInfo] = []
        self._load_error = ""
        self._conf: Any = None

        self.service_combo = QComboBox()
        self.service_combo.addItems([s.label for s in self._services])
        self.service_combo.setToolTip("Any astroquery service package.")
        self.instance_combo = QComboBox()
        self.method_combo = QComboBox()
        self.form.add_widget("service", "Service", self.service_combo)
        self.form.add_widget("instance", "Object", self.instance_combo)
        self.form.add_widget("method", "Method", self.method_combo)
        self.params_holder = QWidget()
        self.params_layout = QVBoxLayout(self.params_holder)
        self.params_layout.setContentsMargins(0, 0, 0, 0)
        self.controls_layout.insertWidget(1, self.params_holder)

        self.docs = self.add_output("Docs")
        self.conf_table = QTableWidget(0, 3)
        self.conf_table.setHorizontalHeaderLabels(["Setting", "Value (editable)", "Description"])
        self.conf_table.horizontalHeader().setStretchLastSection(True)
        conf_page = QWidget()
        cl = QVBoxLayout(conf_page)
        cl.addWidget(self.conf_table)
        apply_btn = QPushButton("Apply configuration")
        apply_btn.setToolTip("Changes apply for this session only (not written to disk).")
        apply_btn.clicked.connect(self.apply_conf)
        cl.addWidget(apply_btn)
        self.tabs.addTab(conf_page, "Config")

        self.add_button("Run", self.run_method, "Call the selected method")
        self.service_combo.currentIndexChanged.connect(self.on_service)
        self.instance_combo.currentIndexChanged.connect(self.on_instance)
        self.method_combo.currentIndexChanged.connect(self.on_method)
        if self._services:
            self.on_service()
        else:
            self.info.show_text("astroquery services could not be found.")

    # ---- navigation --------------------------------------------------------- #
    def current_service(self) -> Optional[ServiceInfo]:
        i = self.service_combo.currentIndex()
        return self._services[i] if 0 <= i < len(self._services) else None

    def on_service(self) -> None:
        svc = self.current_service()
        self.instance_combo.blockSignals(True)
        self.instance_combo.clear()
        self.instance_combo.blockSignals(False)
        self.method_combo.clear()
        self._clear_params()
        if svc is None:
            return
        try:
            self._instances = load_instances(svc.module)
            self._load_error = ""
        except Exception as exc:  # noqa: BLE001 - missing optional dependency etc.
            self._instances = {}
            self._load_error = (f"Cannot load '{svc.module}': {format_exception(exc)}\n"
                                "An optional dependency may be missing.")
            self.docs.show_text(self._load_error)
            self.info.show_text(self._load_error)
            self._fill_conf(None)
            return
        self.instance_combo.addItems(sorted(self._instances))
        self._fill_conf(get_conf(svc.module))
        if not self._instances:
            self.docs.show_text(f"{svc.module} exposes no query objects.")
        # addItems on a signal-enabled combo already triggered on_instance

    def current_instance(self) -> Optional[Any]:
        return self._instances.get(self.instance_combo.currentText())

    def on_instance(self) -> None:
        obj = self.current_instance()
        self.method_combo.blockSignals(True)
        self.method_combo.clear()
        if obj is not None:
            for m in list_methods(obj):
                self.method_combo.addItem(m.name + ("  (returns raw response)" if m.is_async else ""),
                                          m.name)
        self.method_combo.blockSignals(False)
        self.on_method()

    def current_method(self) -> Optional[str]:
        data = self.method_combo.currentData()
        return data if data else None

    def _clear_params(self) -> None:
        if self._param_form is not None:
            self.params_layout.removeWidget(self._param_form)
            self._param_form.deleteLater()
            self._param_form = None
        self._params = []

    def on_method(self) -> None:
        self._clear_params()
        obj, name = self.current_instance(), self.current_method()
        if obj is None or name is None:
            self.docs.show_text(self._load_error or "")
            return
        sig = effective_signature(obj, name)
        self._params = params_from_signature(sig)
        form = ParamForm()
        for p in self._params:
            label = p.key + (" *" if p.required else "")
            tip = f"default: {_default_text(p) or 'required'}"
            if p.is_bool and not p.required:
                form.add_combo(p.key, label, ["(default)", "True", "False"], tip)
            else:
                form.add_text(p.key, label, "", tip, placeholder=_default_text(p) or (
                    "e.g. 1, 'a'" if p.kind is inspect.Parameter.VAR_POSITIONAL else
                    "key=value, ..." if p.kind is inspect.Parameter.VAR_KEYWORD else "required"))
        self._param_form = form
        self.params_layout.addWidget(form)
        self.docs.show_text(f"{type(obj).__name__}.{name}{sig}\n\n{effective_doc(obj, name)}")

    # ---- running ------------------------------------------------------------- #
    def build_call(self) -> Tuple[Any, str, list, dict]:
        obj, name = self.current_instance(), self.current_method()
        if obj is None or name is None or self._param_form is None:
            raise ParseError("Choose a service, object and method first.")
        names = {n: self.ws.get(n) for n in self.ws.names() if n.isidentifier()}
        args, kwargs = collect_call(self._params, self._param_form.values(), names)
        return obj, name, args, kwargs

    def run_method(self) -> None:
        try:
            obj, name, args, kwargs = self.build_call()
        except ParseError as exc:
            self._message(describe_error(exc))
            return

        def job(timeout: float) -> Any:
            set_timeout(obj, timeout)
            return getattr(obj, name)(*args, **kwargs)

        self.execute(job, label=name)

    # ---- configuration ------------------------------------------------------- #
    def _fill_conf(self, conf: Any) -> None:
        self.conf_table.setRowCount(0)
        self._conf = conf
        if conf is None:
            return
        for row, (name, value, _type, desc) in enumerate(conf_items(conf)):
            self.conf_table.insertRow(row)
            key_item = QTableWidgetItem(name)
            key_item.setFlags(key_item.flags() & ~Qt.ItemIsEditable)
            self.conf_table.setItem(row, 0, key_item)
            self.conf_table.setItem(row, 1, QTableWidgetItem(
                ", ".join(map(str, value)) if isinstance(value, list) else str(value)))
            desc_item = QTableWidgetItem(desc)
            desc_item.setFlags(desc_item.flags() & ~Qt.ItemIsEditable)
            self.conf_table.setItem(row, 2, desc_item)
        self.conf_table.resizeColumnsToContents()

    def apply_conf(self) -> None:
        conf = self._conf
        if conf is None:
            return
        errors, changed = [], 0
        current = {n: v for n, v, _t, _d in conf_items(conf)}
        for row in range(self.conf_table.rowCount()):
            name = self.conf_table.item(row, 0).text()
            text = self.conf_table.item(row, 1).text()
            old = current.get(name)
            old_text = ", ".join(map(str, old)) if isinstance(old, list) else str(old)
            if text == old_text:
                continue
            try:
                set_conf_item(conf, name, text)
                changed += 1
            except ParseError as exc:
                errors.append(str(exc))
        msg = f"{changed} setting(s) changed."
        if errors:
            msg += "\n" + "\n".join(errors)
        self.info.show_text(msg)
        self.set_status(msg.splitlines()[0])
        svc = self.current_service()
        if svc:
            self._fill_conf(get_conf(svc.module))


def _make_generic(ws: Workspace) -> QWidget:
    return GenericBrowser(ws)


SPECS = [ModuleSpec(
    "astroquery_browser", "Astroquery Browser", "Online", _make_generic,
    "Call any method of any astroquery service; edit service configuration")]
