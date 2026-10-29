"""API Explorer: call any public astropy function or class from a generated form.

This page guarantees that *every* public astropy callable is reachable, even
when no dedicated panel exists. The pure helpers (index, signature handling,
argument binding, code generation) are GUI-free and unit-tested separately.
"""
from __future__ import annotations

import ast
import contextlib
import functools
import importlib
import inspect
import io
import keyword
import pkgutil
import re
import sys
import traceback
import warnings
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QCheckBox, QComboBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
    QPushButton, QScrollArea, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from ..core.parsing import ParseError, default_namespace, format_exception, safe_eval
from ..core.registry import ModuleSpec
from ..core.widgets import ModulePanel, OutputPane, TableView
from ..core.workspace import Workspace

_EMPTY = inspect.Parameter.empty
_P = inspect.Parameter

# Sub-trees that are not public API (or are only test/support code).
_SKIP_PARTS = {"tests", "extern", "conftest", "testing", "benchmarks", "setup_package"}
# Names that are interactive/blocking by design and make no sense in a GUI.
BLOCKED_NAMES = {"hub_script", "web_profile_text_dialog", "test", "main", "Getch", "getch"}
# Callables that are allowed but destructive: the user must confirm.
CONFIRM_QUALNAMES = {
    "astropy.utils.data.clear_download_cache": "This deletes cached download data.",
    "astropy.utils.data.import_download_cache": "This copies data into the astropy cache.",
    "astropy.config.create_config_file": "This writes a configuration file.",
    "astropy.config.configuration.create_config_file": "This writes a configuration file.",
}
MAX_TEXT = 200_000


# --------------------------------------------------------------------------- #
# API index
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ApiEntry:
    module: str
    name: str
    kind: str  # "function" | "class"

    @property
    def qualname(self) -> str:
        return f"{self.module}.{self.name}"

    def resolve(self) -> Any:
        return getattr(importlib.import_module(self.module), self.name)


_INDEX_CACHE: Optional[Tuple[List[ApiEntry], List[Tuple[str, str]]]] = None


def collect_api() -> Tuple[List[ApiEntry], List[Tuple[str, str]]]:
    """Index public functions/classes of ``astropy``. Returns ``(entries, failures)``.

    Every module is imported in isolation (failures are listed, not raised) and
    an object exported from several modules appears once, under its shallowest
    public path (``astropy.units.Quantity``, not ``astropy.units.quantity.Quantity``).
    """
    global _INDEX_CACHE
    if _INDEX_CACHE is not None:
        return _INDEX_CACHE
    import astropy

    failures: List[Tuple[str, str]] = []
    names: List[str] = ["astropy"]
    with warnings.catch_warnings(), contextlib.redirect_stdout(io.StringIO()), \
            contextlib.redirect_stderr(io.StringIO()):
        warnings.simplefilter("ignore")
        for info in pkgutil.walk_packages(
                astropy.__path__, "astropy.",
                onerror=lambda n: failures.append((n, "import error"))):
            parts = info.name.split(".")
            if any(p.startswith("_") or p in _SKIP_PARTS for p in parts):
                continue
            names.append(info.name)
        seen: Dict[int, ApiEntry] = {}
        for modname in sorted(names, key=lambda n: (n.count("."), n)):
            try:
                mod = importlib.import_module(modname)
            except BaseException as exc:  # noqa: BLE001 - optional deps may be missing
                failures.append((modname, f"{type(exc).__name__}: {exc}"))
                continue
            exported = getattr(mod, "__all__", None)
            if exported is None:
                # no __all__: take what the module defines or re-exports from within itself
                exported = [n for n, v in vars(mod).items()
                            if str(getattr(v, "__module__", "")).startswith(modname)]
            for attr in exported:
                if not isinstance(attr, str) or attr.startswith("_"):
                    continue
                try:
                    obj = getattr(mod, attr)
                except Exception:  # noqa: BLE001 - lazy attributes may fail
                    continue
                if inspect.isclass(obj):
                    kind = "class"
                elif inspect.isroutine(obj):
                    kind = "function"
                else:
                    continue
                seen.setdefault(id(obj), ApiEntry(modname, attr, kind))
    entries = sorted(seen.values(), key=lambda e: (e.module, e.name.lower()))
    _INDEX_CACHE = (entries, failures)
    return _INDEX_CACHE


def filter_entries(entries: Sequence[ApiEntry], text: str) -> List[ApiEntry]:
    """Case-insensitive substring match on the qualified name (all words must match)."""
    words = text.lower().split()
    return [e for e in entries if all(w in e.qualname.lower() for w in words)]


# --------------------------------------------------------------------------- #
# Signatures and arguments
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ParamSpec:
    name: str
    kind: Any
    default: Any = _EMPTY
    annotation: str = ""

    @property
    def required(self) -> bool:
        return self.default is _EMPTY and self.kind not in (_P.VAR_POSITIONAL, _P.VAR_KEYWORD)

    @property
    def wants_text(self) -> bool:
        """Parameters documented as ``str`` accept bare text (e.g. file names)."""
        return isinstance(self.default, str) or bool(re.search(r"\bstr\b", self.annotation))


def safe_signature(obj: Any, drop_first: bool = False) -> Optional[inspect.Signature]:
    try:
        sig = inspect.signature(obj)
    except (TypeError, ValueError):
        return None
    if drop_first:
        params = list(sig.parameters.values())[1:]
        sig = sig.replace(parameters=params)
    return sig


def param_specs(sig: Optional[inspect.Signature]) -> List[ParamSpec]:
    """Parameters of ``sig``; a missing signature becomes ``*args, **kwargs``."""
    if sig is None:
        return [ParamSpec("args", _P.VAR_POSITIONAL), ParamSpec("kwargs", _P.VAR_KEYWORD)]
    out = []
    for p in sig.parameters.values():
        ann = "" if p.annotation is _EMPTY else (
            p.annotation if isinstance(p.annotation, str) else getattr(
                p.annotation, "__name__", str(p.annotation)))
        out.append(ParamSpec(p.name, p.kind, p.default, str(ann)))
    return out


def split_call_args(text: str) -> Tuple[List[str], List[Tuple[str, str]]]:
    """Split ``"a, b+1, k=v"`` into source segments ``(["a", "b+1"], [("k", "v")])``."""
    src = f"f({text})"
    try:
        call = ast.parse(src, mode="eval").body
    except SyntaxError as exc:
        raise ParseError(f"Syntax error in {text!r}: {exc.msg}") from None
    assert isinstance(call, ast.Call)

    def seg(node: ast.AST) -> str:
        return ast.get_source_segment(src, node) or ""

    if any(isinstance(a, ast.Starred) for a in call.args) or any(
            k.arg is None for k in call.keywords):
        raise ParseError("* and ** unpacking are not supported here.")
    return [seg(a) for a in call.args], [(k.arg, seg(k.value)) for k in call.keywords]  # type: ignore[misc]


Convert = Callable[[ParamSpec, str], Any]


def bind_arguments(specs: Sequence[ParamSpec], raw: Dict[str, str],
                   convert: Convert) -> Tuple[List[Any], Dict[str, Any]]:
    """Turn the form's text fields into ``(args, kwargs)``.

    Empty optional fields are omitted (the callee's default applies). With
    ``convert = lambda spec, text: text`` the result is the call's source text.
    """
    var_pos = next((s for s in specs if s.kind == _P.VAR_POSITIONAL), None)
    has_var_pos = bool(var_pos and raw.get(var_pos.name, "").strip())
    args: List[Any] = []
    kwargs: Dict[str, Any] = {}
    gap = False
    for s in specs:
        text = (raw.get(s.name) or "").strip()
        if s.kind == _P.VAR_POSITIONAL:
            if text:
                pos, named = split_call_args(text)
                if named:
                    raise ParseError(f"*{s.name}: use only positional values here.")
                args.extend(convert(s, seg) for seg in pos)
            continue
        if s.kind == _P.VAR_KEYWORD:
            if text:
                pos, named = split_call_args(text)
                if pos:
                    raise ParseError(f"**{s.name}: use name=value pairs here.")
                for key, seg in named:
                    if key in kwargs:
                        raise ParseError(f"Argument {key!r} given twice.")
                    kwargs[key] = convert(s, seg)
            continue
        if not text:
            if s.required:
                raise ParseError(f"Missing required argument {s.name!r}.")
            gap = True
            continue
        value = convert(s, text)
        if s.kind == _P.POSITIONAL_ONLY or (s.kind == _P.POSITIONAL_OR_KEYWORD and has_var_pos):
            if gap:
                raise ParseError(f"Argument {s.name!r} cannot be given while an earlier "
                                 "positional argument is empty.")
            args.append(value)
        else:
            kwargs[s.name] = value
    return args, kwargs


def format_call(target: str, specs: Sequence[ParamSpec], raw: Dict[str, str]) -> str:
    """Source text of ``target(...)`` for the current form contents."""
    args, kwargs = bind_arguments(specs, raw, lambda _s, text: text)
    parts = [str(a) for a in args] + [f"{k}={v}" for k, v in kwargs.items()]
    return f"{target}({', '.join(parts)})"


# --------------------------------------------------------------------------- #
# Evaluation namespace and code generation
# --------------------------------------------------------------------------- #
_IMPORTS = {
    "u": "import astropy.units as u", "np": "import numpy as np",
    "const": "import astropy.constants as const", "astropy": "import astropy",
    "Angle": "from astropy.coordinates import Angle",
    "SkyCoord": "from astropy.coordinates import SkyCoord",
    "EarthLocation": "from astropy.coordinates import EarthLocation",
    "ICRS": "from astropy.coordinates import ICRS", "Galactic": "from astropy.coordinates import Galactic",
    "FK5": "from astropy.coordinates import FK5", "AltAz": "from astropy.coordinates import AltAz",
    "Time": "from astropy.time import Time", "Table": "from astropy.table import Table",
    "QTable": "from astropy.table import QTable", "Column": "from astropy.table import Column",
    "Quantity": "from astropy.units import Quantity", "Masked": "from astropy.utils.masked import Masked",
}
for _n in ("pi", "e", "inf", "nan", "sqrt", "exp", "log", "log10", "sin", "cos", "tan",
           "arange", "linspace", "logspace", "array", "zeros", "ones"):
    _IMPORTS[_n] = f"from numpy import {_n}"


def _safe_ident(name: str, prefix: str = "x") -> str:
    ident = re.sub(r"\W", "_", name.strip()) or prefix
    if ident[0].isdigit() or keyword.iskeyword(ident):
        ident = f"{prefix}_{ident}"
    return ident


def explorer_namespace(ws: Optional[Workspace]) -> Dict[str, Any]:
    """Names available in argument expressions (on top of the core namespace)."""
    import astropy
    from astropy.coordinates import FK5, ICRS, AltAz, EarthLocation, Galactic
    from astropy.table import Column, QTable, Table
    from astropy.utils.masked import Masked

    ns: Dict[str, Any] = {
        "astropy": astropy, "Table": Table, "QTable": QTable, "Column": Column,
        "Masked": Masked, "EarthLocation": EarthLocation, "ICRS": ICRS,
        "Galactic": Galactic, "FK5": FK5, "AltAz": AltAz, "Quantity": default_namespace()["u"].Quantity,
        "dict": dict, "list": list, "tuple": tuple, "str": str, "bool": bool,
        "complex": complex, "set": set, "range": range, "slice": slice,
    }
    if ws is not None:
        objects = {n: ws.get(n) for n in ws.names()}
        ns["ws"] = objects
        for name, obj in objects.items():
            ns[f"ws_{_safe_ident(name)}"] = obj
    return ns


def evaluate_arguments(specs: Sequence[ParamSpec], raw: Dict[str, str],
                       names: Dict[str, Any]) -> Tuple[List[Any], Dict[str, Any]]:
    """Parse the form contents with the restricted evaluator."""

    def convert(spec: ParamSpec, text: str) -> Any:
        try:
            return safe_eval(text, names)
        except ParseError as exc:
            if spec.wants_text and spec.kind not in (_P.VAR_POSITIONAL, _P.VAR_KEYWORD) \
                    and not re.search(r"[()\[\]{}=]", text):
                return text  # bare words/paths for str parameters
            raise ParseError(f"{spec.name}: {exc}") from None

    return bind_arguments(specs, raw, convert)


@dataclass
class CodeBlock:
    """Imports, notes and statements; combine blocks to replay an object's history."""

    imports: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)
    lines: List[str] = field(default_factory=list)

    def merged(self, other: "CodeBlock") -> "CodeBlock":
        def uniq(items: List[str]) -> List[str]:
            return list(dict.fromkeys(items))
        return CodeBlock(uniq(self.imports + other.imports), uniq(self.notes + other.notes),
                         self.lines + other.lines)

    def render(self) -> str:
        out = sorted(self.imports, key=lambda s: (not s.startswith("import"), s))
        if self.notes:
            out += [""] + [f"# {n}" for n in self.notes]
        return "\n".join(out + [""] + self.lines) + "\n"


def code_block(expression: str, assign_to: str, imports: Sequence[str]) -> CodeBlock:
    """``assign_to = expression`` plus the imports the expression's names need."""
    block = CodeBlock(imports=list(imports))
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError:
        tree = None
    if tree is not None:
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                if node.id.startswith("ws_"):
                    block.notes.append(f"{node.id}: object from the AstroTools-ADV workspace")
                elif node.id in _IMPORTS:
                    block.imports.append(_IMPORTS[node.id])
                elif node.id == "ws":
                    block.notes.append("ws: dict of AstroTools-ADV workspace objects")
    block.lines.append(f"{assign_to} = {expression}")
    return block


# --------------------------------------------------------------------------- #
# Class members
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Member:
    """``kind``: method | classmethod | static | property | dynamic.

    ``dynamic`` members only exist on instances (e.g. ``SkyCoord`` resolves frame
    attributes and ``separation`` through ``__getattr__``); whether they are
    callable is decided when selected, never while listing, because merely
    reading them can trigger coordinate transformations.
    """

    name: str
    kind: str

    @property
    def label(self) -> str:
        return f"{self.name}  ({self.kind})"


def class_members(cls: type, instance: Any = None) -> List[Member]:
    """Public members of ``cls`` (statically inspected) plus dynamic ones of ``instance``."""
    out = []
    static_names = set()
    for name in dir(cls):
        if name.startswith("_"):
            continue
        static_names.add(name)
        try:
            attr = inspect.getattr_static(cls, name)
        except AttributeError:
            continue
        if isinstance(attr, classmethod):
            out.append(Member(name, "classmethod"))
        elif isinstance(attr, staticmethod):
            out.append(Member(name, "static"))
        elif isinstance(attr, (property, functools.cached_property)):
            out.append(Member(name, "property"))
        elif inspect.isroutine(attr):
            out.append(Member(name, "method"))
    if instance is not None:
        try:
            names = dir(instance)
        except Exception:  # noqa: BLE001 - exotic __dir__
            names = []
        out.extend(Member(n, "dynamic") for n in names
                   if not n.startswith("_") and n not in static_names)
    return sorted(out, key=lambda m: m.name.lower())


def member_signature(cls: type, member: Member, instance: Any = None) -> Optional[inspect.Signature]:
    """Signature of ``member`` without ``self``; ``None`` if it cannot be introspected."""
    if member.kind == "property":
        return inspect.Signature([])
    if member.kind == "dynamic":
        if instance is None:
            return inspect.Signature([])
        attr = getattr(instance, member.name)
        return safe_signature(attr) if callable(attr) else inspect.Signature([])
    return safe_signature(getattr(cls, member.name), drop_first=member.kind == "method")


def is_value_member(cls: type, member: Member, instance: Any = None) -> bool:
    """True when running ``member`` just reads an attribute (no call)."""
    if member.kind == "property":
        return True
    if member.kind == "dynamic":
        return instance is None or not callable(getattr(instance, member.name))
    return False


# --------------------------------------------------------------------------- #
# Invocation
# --------------------------------------------------------------------------- #
@dataclass
class Outcome:
    value: Any = None
    stdout: str = ""
    warnings: List[str] = field(default_factory=list)
    error: Optional[BaseException] = None
    detail: str = ""
    new_figures: List[Any] = field(default_factory=list)


def invoke(call: Callable[[], Any]) -> Outcome:
    """Run ``call`` capturing stdout/stderr, warnings, exceptions and new pyplot figures."""
    out = Outcome()
    buf = io.StringIO()
    before = _pyplot_figures()
    with warnings.catch_warnings(record=True) as caught, contextlib.redirect_stdout(buf), \
            contextlib.redirect_stderr(buf):
        warnings.simplefilter("always")
        try:
            out.value = call()
        except BaseException as exc:  # noqa: BLE001 - shown to the user
            out.error, out.detail = exc, traceback.format_exc()
    out.stdout = buf.getvalue()
    out.warnings = [f"{w.category.__name__}: {w.message}" for w in caught]
    out.new_figures = [f for f in _pyplot_figures() if f not in before]
    return out


def _pyplot_figures() -> list:
    plt = sys.modules.get("matplotlib.pyplot")
    return [plt.figure(n) for n in plt.get_fignums()] if plt else []


def default_gui_thread(module: str, name: str) -> bool:
    """Plotting code must run on the GUI thread."""
    return module.startswith("astropy.visualization") or bool(
        re.search(r"plot|imshow|show|hist|draw|figure", name, re.I))


def is_blocked(name: str) -> bool:
    return name in BLOCKED_NAMES


def describe_value(value: Any) -> str:
    """Plain-text rendering of a result."""
    from astropy.io.fits import HDUList

    with np.printoptions(threshold=1000, linewidth=110):
        if isinstance(value, HDUList):
            text = "\n".join(str(row) for row in value.info(output=False))
        else:
            text = repr(value)
    if len(text) > MAX_TEXT:
        text = text[:MAX_TEXT] + "\n... (truncated)"
    return f"<{type(value).__module__}.{type(value).__qualname__}>\n{text}"


# --------------------------------------------------------------------------- #
# Widgets
# --------------------------------------------------------------------------- #
class CallForm(QWidget):
    """One line edit per parameter; empty optional fields use the callee's default."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.specs: List[ParamSpec] = []
        self.edits: Dict[str, QLineEdit] = {}
        self._layout = QFormLayout(self)
        self._layout.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)

    def set_specs(self, specs: Sequence[ParamSpec]) -> None:
        while self._layout.rowCount():
            self._layout.removeRow(0)
        self.edits.clear()
        self.specs = list(specs)
        for s in self.specs:
            edit = QLineEdit()
            if s.kind == _P.VAR_POSITIONAL:
                label, hint = f"*{s.name}", "comma-separated expressions"
            elif s.kind == _P.VAR_KEYWORD:
                label, hint = f"**{s.name}", "name=expression, name=expression"
            elif s.required:
                label, hint = f"{s.name} *", "required"
            else:
                label, hint = s.name, f"default: {s.default!r}"
            edit.setPlaceholderText(hint)
            tip = [f"kind: {str(s.kind).lower()}"]
            if s.annotation:
                tip.append(f"type: {s.annotation}")
            if s.required:
                tip.append("required")
            else:
                tip.append("leave empty to use the default")
            tip.append("Expressions: u, np, astropy, Table, Time, SkyCoord ...; "
                       "workspace objects are ws_<name> (or ws['name']).")
            if s.wants_text:
                tip.append("Text parameter: bare words (e.g. a file name) are accepted.")
            edit.setToolTip("\n".join(tip))
            self.edits[s.name] = edit
            self._layout.addRow(label, edit)

    def raw(self) -> Dict[str, str]:
        return {k: e.text().strip() for k, e in self.edits.items()}


class FigureHolder(QWidget):
    """Shows an existing matplotlib ``Figure`` (replacing the previous one)."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._widgets: List[QWidget] = []
        self.figure: Any = None

    def show_figure(self, fig: Any) -> None:
        from matplotlib.backends.backend_qt5agg import (
            FigureCanvasQTAgg, NavigationToolbar2QT)

        for w in self._widgets:
            self._layout.removeWidget(w)
            w.deleteLater()
        canvas = FigureCanvasQTAgg(fig)
        toolbar = NavigationToolbar2QT(canvas, self)
        self._widgets = [toolbar, canvas]
        self._layout.addWidget(toolbar)
        self._layout.addWidget(canvas, 1)
        self.figure = fig
        canvas.draw_idle()


class ApiExplorer(ModulePanel):
    TAB_CALL, TAB_DOCS, TAB_RESULT, TAB_TABLE, TAB_FIGURE = range(5)

    def __init__(self, ws: Workspace) -> None:
        super().__init__(ws)
        self.entries: List[ApiEntry] = []
        self.failures: List[Tuple[str, str]] = []
        self.entry: Optional[ApiEntry] = None
        self.obj: Any = None
        self._members: List[Member] = []
        self._last_value: Any = None
        self._has_result = False
        self._pending_code = CodeBlock()
        self._history: Dict[str, CodeBlock] = {}
        self._items: Dict[Tuple[str, str], QTreeWidgetItem] = {}

        # ---- left: search + tree ----
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search API (e.g. sigma_clip, SkyCoord, fits.open)")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self.apply_filter)
        self.count_label = QLabel("Indexing astropy ...")
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setMinimumHeight(480)
        self.tree.currentItemChanged.connect(self._on_tree_select)
        self.controls_layout.insertWidget(0, self.search)
        self.controls_layout.insertWidget(1, self.count_label)
        self.controls_layout.insertWidget(2, self.tree, 1)

        # ---- right: tabs ----
        self.title = QLabel("Select a function or class on the left.")
        self.title.setWordWrap(True)
        self.title.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.signature = QLabel("")
        self.signature.setWordWrap(True)
        self.signature.setTextInteractionFlags(Qt.TextSelectableByMouse)

        self.instance_combo = QComboBox()
        self.member_combo = QComboBox()
        self.member_combo.currentIndexChanged.connect(self._on_member_changed)
        self.instance_combo.currentIndexChanged.connect(lambda _i: self._rebuild_members())
        self.ws.changed.connect(self._refresh_instances)
        self.call_form = CallForm()
        form_scroll = QScrollArea()
        form_scroll.setWidgetResizable(True)
        form_scroll.setWidget(self.call_form)

        self.store_name = QLineEdit()
        self.store_name.setPlaceholderText("workspace name (auto if empty)")
        self.store_name.setToolTip("Name under which the result / new object is stored.")
        self.gui_thread = QCheckBox("Run on GUI thread")
        self.gui_thread.setToolTip("Needed for plotting code; blocks the window while running.")
        self.run_btn = QPushButton("Run")
        self.run_btn.clicked.connect(self.on_run)
        self.code_btn = QPushButton("Copy as Python code")
        self.code_btn.clicked.connect(self.on_copy_code)
        self.store_btn = QPushButton("Store result")
        self.store_btn.clicked.connect(self.on_store_result)
        self.store_btn.setEnabled(False)

        self.member_row = QWidget()
        mrow = QFormLayout(self.member_row)
        mrow.setContentsMargins(0, 0, 0, 0)
        mrow.addRow("Instance", self.instance_combo)
        mrow.addRow("Member", self.member_combo)
        self.member_row.hide()

        buttons = QHBoxLayout()
        for w in (self.run_btn, self.code_btn, self.store_btn):
            buttons.addWidget(w)
        opts = QHBoxLayout()
        opts.addWidget(QLabel("Store as"))
        opts.addWidget(self.store_name, 1)
        opts.addWidget(self.gui_thread)

        call_page = QWidget()
        cl = QVBoxLayout(call_page)
        cl.addWidget(self.title)
        cl.addWidget(self.signature)
        cl.addWidget(self.member_row)
        cl.addWidget(form_scroll, 1)
        cl.addLayout(opts)
        cl.addLayout(buttons)

        self.docs = OutputPane()
        self.docs.setLineWrapMode(OutputPane.WidgetWidth)
        self.result = OutputPane()
        self.table_view = TableView()
        self.figure_holder = FigureHolder()
        self.tabs.addTab(call_page, "Call")
        self.tabs.addTab(self.docs, "Docs")
        self.tabs.addTab(self.result, "Result")
        self.tabs.addTab(self.table_view, "Table")
        self.tabs.addTab(self.figure_holder, "Figure")

        self.run(collect_api, self._on_index, busy_text="Indexing astropy ...")

    # ---- index / tree --------------------------------------------------- #
    def _on_index(self, value: Tuple[List[ApiEntry], List[Tuple[str, str]]]) -> None:
        self.entries, self.failures = value
        groups: Dict[str, QTreeWidgetItem] = {}
        self.tree.setUpdatesEnabled(False)
        for e in self.entries:
            parent = groups.get(e.module)
            if parent is None:
                parent = QTreeWidgetItem(self.tree, [e.module])
                parent.setFlags(parent.flags() & ~Qt.ItemIsSelectable)
                groups[e.module] = parent
            item = QTreeWidgetItem(parent, [e.name if e.kind == "class" else f"{e.name}()"])
            item.setData(0, Qt.UserRole, e)
            item.setToolTip(0, e.qualname)
            self._items[(e.module, e.name)] = item
        self.tree.setUpdatesEnabled(True)
        if self.failures:
            self.result.show_text("Modules that could not be indexed:\n" + "\n".join(
                f"  {m}: {err}" for m, err in self.failures))
        self.apply_filter(self.search.text())

    def apply_filter(self, text: str = "") -> None:
        matches = {e.qualname for e in filter_entries(self.entries, text)}
        shown = 0
        for i in range(self.tree.topLevelItemCount()):
            top = self.tree.topLevelItem(i)
            visible = 0
            for j in range(top.childCount()):
                child = top.child(j)
                e = child.data(0, Qt.UserRole)
                hide = e.qualname not in matches
                child.setHidden(hide)
                visible += not hide
            top.setHidden(visible == 0)
            top.setExpanded(bool(text.strip()) and visible > 0)
            shown += visible
        self.count_label.setText(f"{shown} of {len(self.entries)} callables")

    def select_qualname(self, qualname: str) -> None:
        """Select an indexed entry programmatically (clears the filter)."""
        self.search.setText("")
        for (mod, name), item in self._items.items():
            if f"{mod}.{name}" == qualname:
                self.tree.setCurrentItem(item)
                return
        raise KeyError(qualname)

    def visible_qualnames(self) -> List[str]:
        out = []
        for i in range(self.tree.topLevelItemCount()):
            top = self.tree.topLevelItem(i)
            for j in range(top.childCount()):
                child = top.child(j)
                if not child.isHidden():
                    out.append(child.data(0, Qt.UserRole).qualname)
        return out

    def _on_tree_select(self, item: Optional[QTreeWidgetItem], _prev=None) -> None:
        entry = item.data(0, Qt.UserRole) if item is not None else None
        if isinstance(entry, ApiEntry):
            self.select_entry(entry)

    # ---- selection ------------------------------------------------------ #
    def select_entry(self, entry: ApiEntry) -> None:
        try:
            self.obj = entry.resolve()
        except Exception as exc:  # noqa: BLE001
            self.entry = None
            self.title.setText(entry.qualname)
            self.signature.setText(f"Cannot import: {format_exception(exc)}")
            return
        self.entry = entry
        is_class = entry.kind == "class"
        self.title.setText(f"<b>{entry.qualname}</b> &nbsp; <i>{entry.kind}</i>")
        doc = inspect.getdoc(self.obj) or "(no documentation)"
        self.docs.show_text(f"{entry.qualname}\n\n{doc}")
        self.member_row.setVisible(is_class)
        self.instance_combo.blockSignals(True)
        self.instance_combo.clear()
        self.instance_combo.blockSignals(False)
        self._refresh_instances()
        self._rebuild_members()
        self.gui_thread.setChecked(default_gui_thread(entry.module, entry.name))
        self.store_name.clear()
        self._update_form()

    def _current_member(self) -> Optional[Member]:
        data = self.member_combo.currentData() if self.member_combo.count() else None
        return data if isinstance(data, Member) else None

    def _on_member_changed(self, _index: int = 0) -> None:
        self._update_form()
        if self.entry is None:
            return
        member = self._current_member()
        if member is None:
            self.docs.show_text(f"{self.entry.qualname}\n\n{inspect.getdoc(self.obj) or ''}")
            return
        try:
            holder = self._selected_instance() if member.kind == "dynamic" else self.obj
            doc = inspect.getdoc(getattr(holder, member.name)) or "(no documentation)"
        except Exception as exc:  # noqa: BLE001
            doc = f"(documentation unavailable: {format_exception(exc)})"
        self.docs.show_text(f"{self.entry.qualname}.{member.name}\n\n{doc}")

    def _selected_instance(self) -> Any:
        name = self.instance_combo.currentData()
        return self.ws.get(name) if name is not None and name in self.ws else None

    def _rebuild_members(self) -> None:
        """List class members (+ dynamic ones of the selected instance), keeping the choice."""
        if self.entry is None or self.entry.kind != "class":
            return
        keep = self.member_combo.currentText()
        self.member_combo.blockSignals(True)
        self.member_combo.clear()
        self._members = class_members(self.obj, self._selected_instance())
        self.member_combo.addItem("<constructor>", None)
        for m in self._members:
            self.member_combo.addItem(m.label, m)
        idx = self.member_combo.findText(keep)
        self.member_combo.setCurrentIndex(max(idx, 0))
        self.member_combo.blockSignals(False)
        self._update_form()

    def _refresh_instances(self) -> None:
        if self.entry is None or self.entry.kind != "class":
            return
        current = self.instance_combo.currentData()
        self.instance_combo.blockSignals(True)
        self.instance_combo.clear()
        self.instance_combo.addItem("(none / class)", None)
        for name in self.ws.names(self.obj):
            self.instance_combo.addItem(name, name)
        idx = self.instance_combo.findData(current) if current is not None else -1
        self.instance_combo.setCurrentIndex(idx if idx >= 0 else min(1, self.instance_combo.count() - 1))
        self.instance_combo.blockSignals(False)
        self._rebuild_members()

    def _update_form(self) -> None:
        if self.entry is None:
            return
        member = self._current_member()
        if self.entry.kind == "class" and member is not None:
            instance = self._selected_instance()
            try:
                sig = member_signature(self.obj, member, instance)
                value_only = is_value_member(self.obj, member, instance)
            except Exception as exc:  # noqa: BLE001 - dynamic attribute failed to resolve
                sig, value_only = inspect.Signature([]), True
                self.set_status(f"{member.name}: {format_exception(exc)}")
            self.run_btn.setText("Get" if value_only else "Run")
        else:
            sig = safe_signature(self.obj)
            self.run_btn.setText("Construct" if self.entry.kind == "class" else "Run")
        self.signature.setText(
            f"<code>{self.entry.name}{sig}</code>" if sig is not None else
            "<i>Signature unavailable - use *args / **kwargs.</i>")
        self.call_form.set_specs(param_specs(sig))

    # ---- running -------------------------------------------------------- #
    def _prepare(self) -> Tuple[Callable[[], Any], str, CodeBlock, Optional[str]]:
        """Parse the form. Returns ``(thunk, label, code, constructs_name)``."""
        assert self.entry is not None
        entry, specs, raw = self.entry, self.call_form.specs, self.call_form.raw()
        args, kwargs = evaluate_arguments(specs, raw, explorer_namespace(self.ws))
        member = self._current_member() if entry.kind == "class" else None
        class_import = CodeBlock(imports=[f"from {entry.module} import {entry.name}"])
        obj = self.obj

        if member is None:  # plain function, or class construction
            expr = format_call(entry.name, specs, raw)
            if entry.kind == "function":
                return (lambda: obj(*args, **kwargs)), entry.qualname, \
                    class_import.merged(code_block(expr, "result", [])), None
            explicit = self.store_name.text().strip()
            assign = _safe_ident(explicit) if explicit else self.unique_name(
                _safe_ident(entry.name.lower()))
            return (lambda: obj(*args, **kwargs)), entry.qualname, \
                class_import.merged(code_block(expr, assign, [])), assign

        label = f"{entry.qualname}.{member.name}"
        if member.kind in ("classmethod", "static"):
            func: Any = getattr(obj, member.name)
            target, history, value_only = f"{entry.name}.{member.name}", class_import, False
        else:
            inst_name = self.instance_combo.currentData()
            instance = self._selected_instance()
            if instance is None:
                raise ParseError(f"Select an instance of {entry.name} "
                                 "(construct one first) to use this member.")
            var = _safe_ident(inst_name)
            target = f"{var}.{member.name}"
            history = self._history.get(inst_name) or CodeBlock(
                notes=[f"{var}: object from the AstroTools-ADV workspace"])
            value_only = is_value_member(obj, member, instance)
            func = (lambda: getattr(instance, member.name)) if value_only \
                else getattr(instance, member.name)
        if value_only:
            return func, label, history.merged(code_block(target, "result", [])), None
        expr = format_call(target, specs, raw)
        return (lambda: func(*args, **kwargs)), label, \
            history.merged(code_block(expr, "result", [])), None

    def on_run(self) -> None:
        self.guard(self._run)

    def _run(self) -> None:
        if self.entry is None:
            raise ParseError("Select a function or class first.")
        member = self._current_member() if self.entry.kind == "class" else None
        blocked = self.entry.name if member is None else member.name
        if is_blocked(blocked):
            raise ParseError(f"{blocked} is interactive/blocking and not available in the GUI.")
        note = CONFIRM_QUALNAMES.get(self.entry.qualname)
        if note and not self.confirm(f"{self.entry.qualname}\n\n{note}\n\nContinue?"):
            return
        thunk, label, code, constructs = self._prepare()
        self._pending_code = code
        if self.gui_thread.isChecked():
            self.set_status(f"Running {label} ...")
            self._on_outcome(invoke(thunk), label, constructs)
            self.set_status("Ready")
        else:
            self.run(invoke, lambda o: self._on_outcome(o, label, constructs), thunk,
                     busy_text=f"Running {label} ...")

    def confirm(self, text: str) -> bool:
        return QMessageBox.question(self, "Confirm", text) == QMessageBox.Yes

    # ---- results -------------------------------------------------------- #
    def _on_outcome(self, out: Outcome, label: str, constructs: Optional[str]) -> None:
        sections: List[str] = []
        special = False
        if out.error is not None:
            sections.append(f"Error in {label}:\n{format_exception(out.error)}")
            if out.detail:
                sections.append("--- traceback ---\n" + out.detail.rstrip())
            self._has_result = False
            self.store_btn.setEnabled(False)
            self.set_status(f"Error: {format_exception(out.error)}")
        else:
            value = out.value
            self._last_value, self._has_result = value, True
            self.store_btn.setEnabled(True)
            try:
                sections.append(f"{label} -> " + describe_value(value))
            except Exception as exc:  # noqa: BLE001 - a broken __repr__ must not hide the result
                sections.append(f"{label} -> <{type(value).__name__}> (repr failed: {exc})")
            special = self._show_value(value, out.new_figures)
            if constructs is not None:
                name = self._store(constructs, value)
                sections.append(f"Stored in workspace as {name!r}.")
            self.set_status(f"{label}: done")
        if out.stdout.strip():
            sections.append("--- output ---\n" + out.stdout.rstrip())
        if out.warnings:
            sections.append("--- warnings ---\n" + "\n".join(dict.fromkeys(out.warnings)))
        self.result.show_text("\n\n".join(sections))
        if not special:
            self.tabs.setCurrentIndex(self.TAB_RESULT)

    def _show_value(self, value: Any, figures: list) -> bool:
        """Display tables/figures on their tabs; returns whether a tab was chosen."""
        from astropy.table import Table
        from matplotlib.axes import Axes
        from matplotlib.figure import Figure

        special = False
        fig = value if isinstance(value, Figure) else (
            value.figure if isinstance(value, Axes) else (figures[-1] if figures else None))
        if isinstance(value, Table):
            self.table_view.set_table(value)
            self.tabs.setCurrentIndex(self.TAB_TABLE)
            special = True
        if fig is not None:
            plt = sys.modules.get("matplotlib.pyplot")
            if plt is not None:
                for f in figures:
                    plt.close(f)  # hand ownership to our canvas
            self.figure_holder.show_figure(fig)
            self.tabs.setCurrentIndex(self.TAB_FIGURE)
            special = True
        return special

    def _store(self, name: str, value: Any) -> str:
        """Put ``value`` in the workspace, remembering the code that produced it."""
        self.ws.put(name, value)
        code = self._pending_code
        if code.lines:
            code = CodeBlock(code.imports, code.notes, code.lines[:-1] + [
                re.sub(r"^\w+ = ", f"{name} = ", code.lines[-1])])
        self._history[name] = code
        self.ws.log(f"API Explorer: stored {name} ({type(value).__name__})")
        return name

    def unique_name(self, base: str) -> str:
        base = base.strip() or "result"
        if base not in self.ws:
            return base
        i = 1
        while f"{base}_{i}" in self.ws:
            i += 1
        return f"{base}_{i}"

    def on_store_result(self) -> None:
        def go() -> None:
            if not self._has_result:
                raise ParseError("There is no result to store.")
            explicit = self.store_name.text().strip()
            name = _safe_ident(explicit) if explicit else self.unique_name("result")
            self.set_status(f"Stored as {self._store(name, self._last_value)!r}")
        self.guard(go)

    def on_copy_code(self) -> None:
        def go() -> None:
            from PyQt5.QtGui import QGuiApplication
            QGuiApplication.clipboard().setText(self.python_code())
            self.set_status("Python code copied to clipboard")
        self.guard(go)

    def python_code(self) -> str:
        """Source equivalent of the call currently described by the form."""
        if self.entry is None:
            raise ParseError("Select a function or class first.")
        _thunk, _label, code, _c = self._prepare()
        return code.render()


def _make(ws: Workspace) -> QWidget:
    return ApiExplorer(ws)


SPECS = [ModuleSpec(
    "api_explorer", "API Explorer", "System", _make,
    "Browse and call every public astropy function and class with an auto-generated form")]
