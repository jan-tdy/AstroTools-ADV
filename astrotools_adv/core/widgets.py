"""Reusable Qt widgets shared by all panels."""
from __future__ import annotations

import csv
import io
from typing import Any, Callable, Dict, List, Optional, Sequence

import numpy as np
from PyQt5.QtCore import QAbstractTableModel, QModelIndex, Qt, pyqtSignal
from PyQt5.QtGui import QFont, QGuiApplication
from PyQt5.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QFormLayout,
    QFrame, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPlainTextEdit, QPushButton,
    QScrollArea, QSpinBox, QSplitter, QTableView, QTabWidget, QVBoxLayout, QWidget,
)

from . import tasks
from .parsing import ParseError, format_exception
from .workspace import Workspace

MAX_TABLE_ROWS = 200_000  # rows rendered by TableModel before truncation


def monospace() -> QFont:
    font = QFont("Monospace")
    font.setStyleHint(QFont.TypeWriter)
    return font


# --------------------------------------------------------------------------- #
# Text output
# --------------------------------------------------------------------------- #
class OutputPane(QPlainTextEdit):
    """Read-only monospace text area."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setReadOnly(True)
        self.setFont(monospace())
        self.setLineWrapMode(QPlainTextEdit.NoWrap)

    def show_text(self, text: Any) -> None:
        self.setPlainText(str(text))

    def append_text(self, text: Any) -> None:
        self.appendPlainText(str(text))

    def show_error(self, exc: BaseException) -> None:
        self.setPlainText(f"Error: {format_exception(exc)}")


# --------------------------------------------------------------------------- #
# Tables
# --------------------------------------------------------------------------- #
def _cell_text(col: Any, i: int) -> str:
    """Text for one cell of an astropy (Mask)Column / Quantity-column; never raises."""
    try:
        value = col[i]
        if value is np.ma.masked:
            return "--"
        if isinstance(value, np.ndarray) and value.ndim > 0:
            return f"array{list(value.shape)}" if value.size > 6 else str(value.tolist())
        if hasattr(value, "value") and hasattr(value, "unit"):  # Quantity scalar
            value = value.value
        if isinstance(value, (bytes, np.bytes_)):
            return value.decode("utf-8", "replace")
        if isinstance(value, (float, np.floating)):
            return f"{value:.10g}"
        return str(value)
    except Exception as exc:  # noqa: BLE001
        return f"<{type(exc).__name__}>"


class TableModel(QAbstractTableModel):
    """Read-only model over an :class:`astropy.table.Table` (or ``None``)."""

    def __init__(self, table: Any = None, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._table = None
        self._names: List[str] = []
        self._rows = 0
        self.truncated = False
        self.set_table(table)

    def set_table(self, table: Any) -> None:
        self.beginResetModel()
        self._table = table
        self._names = list(table.colnames) if table is not None else []
        n = len(table) if table is not None else 0
        self.truncated = n > MAX_TABLE_ROWS
        self._rows = min(n, MAX_TABLE_ROWS)
        self.endResetModel()

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else self._rows

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._names)

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole) -> Any:
        if not index.isValid():
            return None
        if role == Qt.DisplayRole:
            return _cell_text(self._table[self._names[index.column()]], index.row())
        if role == Qt.TextAlignmentRole:
            return int(Qt.AlignRight | Qt.AlignVCenter)
        return None

    def headerData(self, section: int, orientation: Qt.Orientation,
                   role: int = Qt.DisplayRole) -> Any:
        if role != Qt.DisplayRole:
            return None
        if orientation == Qt.Vertical:
            return section
        name = self._names[section]
        unit = getattr(self._table[name], "unit", None)
        return f"{name}\n[{unit}]" if unit not in (None, "") else name

    def to_csv(self) -> str:
        buf = io.StringIO()
        writer = csv.writer(buf, lineterminator="\n")
        writer.writerow(self._names)
        for i in range(self._rows):
            writer.writerow([_cell_text(self._table[n], i) for n in self._names])
        return buf.getvalue()


class TableView(QWidget):
    """Table display with a row/column summary and copy-as-CSV."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.model = TableModel()
        self.view = QTableView()
        self.view.setModel(self.model)
        self.view.setAlternatingRowColors(True)
        self.view.setSelectionBehavior(QAbstractItemView.SelectItems)
        self.view.horizontalHeader().setDefaultAlignment(Qt.AlignCenter)
        self.summary = QLabel("No table.")
        copy = QPushButton("Copy CSV")
        copy.clicked.connect(self.copy_csv)
        top = QHBoxLayout()
        top.addWidget(self.summary, 1)
        top.addWidget(copy)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addLayout(top)
        lay.addWidget(self.view)

    def set_table(self, table: Any) -> None:
        self.model.set_table(table)
        self.view.resizeColumnsToContents()
        if table is None:
            self.summary.setText("No table.")
            return
        text = f"{len(table)} rows x {len(table.colnames)} columns"
        if self.model.truncated:
            text += f" (showing first {MAX_TABLE_ROWS})"
        self.summary.setText(text)

    def copy_csv(self) -> None:
        QGuiApplication.clipboard().setText(self.model.to_csv())


# --------------------------------------------------------------------------- #
# Plotting
# --------------------------------------------------------------------------- #
class MplCanvas(QWidget):
    """Matplotlib figure + navigation toolbar. Use only from the GUI thread."""

    def __init__(self, parent: Optional[QWidget] = None, figsize=(6, 4)) -> None:
        super().__init__(parent)
        from matplotlib.backends.backend_qt5agg import (
            FigureCanvasQTAgg, NavigationToolbar2QT)
        from matplotlib.figure import Figure

        self.figure = Figure(figsize=figsize, tight_layout=True)
        self.canvas = FigureCanvasQTAgg(self.figure)
        self.toolbar = NavigationToolbar2QT(self.canvas, self)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.toolbar)
        lay.addWidget(self.canvas, 1)

    def clear(self) -> None:
        self.figure.clear()
        self.canvas.draw_idle()

    def axes(self, projection: Any = None):
        """Fresh single axes (optionally a WCSAxes ``projection``)."""
        self.figure.clear()
        ax = self.figure.add_subplot(111, projection=projection)
        return ax

    def redraw(self) -> None:
        self.canvas.draw_idle()

    def save(self, path: str) -> None:
        self.figure.savefig(path, dpi=150)


# --------------------------------------------------------------------------- #
# Forms
# --------------------------------------------------------------------------- #
class ParamForm(QWidget):
    """Declarative label/field form. ``values()`` returns raw field contents.

    Text fields return ``str``; combos return the item text (or ``userData`` if
    set); checks return ``bool``; spin boxes return numbers.
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._form = QFormLayout(self)
        self._form.setContentsMargins(0, 0, 0, 0)
        self._form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        self.fields: Dict[str, QWidget] = {}

    def _add(self, key: str, label: str, widget: QWidget, tip: str = "") -> QWidget:
        if key in self.fields:
            raise KeyError(f"duplicate form field {key!r}")
        if tip:
            widget.setToolTip(tip)
        self.fields[key] = widget
        self._form.addRow(label, widget)
        return widget

    def add_text(self, key: str, label: str, default: str = "", tip: str = "",
                 placeholder: str = "") -> QLineEdit:
        w = QLineEdit(default)
        w.setPlaceholderText(placeholder)
        return self._add(key, label, w, tip)  # type: ignore[return-value]

    def add_multiline(self, key: str, label: str, default: str = "", tip: str = "",
                      height: int = 90) -> QPlainTextEdit:
        w = QPlainTextEdit(default)
        w.setFont(monospace())
        w.setFixedHeight(height)
        return self._add(key, label, w, tip)  # type: ignore[return-value]

    def add_combo(self, key: str, label: str, items: Sequence[Any], tip: str = "",
                  current: Optional[str] = None, editable: bool = False) -> QComboBox:
        w = QComboBox()
        w.setEditable(editable)
        for it in items:
            if isinstance(it, tuple):
                w.addItem(str(it[0]), it[1])
            else:
                w.addItem(str(it))
        if current is not None:
            idx = w.findText(current)
            if idx >= 0:
                w.setCurrentIndex(idx)
        return self._add(key, label, w, tip)  # type: ignore[return-value]

    def add_check(self, key: str, label: str, default: bool = False, tip: str = "") -> QCheckBox:
        w = QCheckBox()
        w.setChecked(default)
        return self._add(key, label, w, tip)  # type: ignore[return-value]

    def add_int(self, key: str, label: str, default: int = 0, lo: int = -10**9,
                hi: int = 10**9, tip: str = "") -> QSpinBox:
        w = QSpinBox()
        w.setRange(lo, hi)
        w.setValue(default)
        return self._add(key, label, w, tip)  # type: ignore[return-value]

    def add_float(self, key: str, label: str, default: float = 0.0, lo: float = -1e12,
                  hi: float = 1e12, decimals: int = 6, tip: str = "") -> QDoubleSpinBox:
        w = QDoubleSpinBox()
        w.setDecimals(decimals)
        w.setRange(lo, hi)
        w.setValue(default)
        return self._add(key, label, w, tip)  # type: ignore[return-value]

    def add_widget(self, key: str, label: str, widget: QWidget) -> QWidget:
        return self._add(key, label, widget)

    def value(self, key: str) -> Any:
        w = self.fields[key]
        if isinstance(w, QLineEdit):
            return w.text().strip()
        if isinstance(w, QPlainTextEdit):
            return w.toPlainText().strip()
        if isinstance(w, QComboBox):
            data = w.currentData()
            return data if data is not None else w.currentText().strip()
        if isinstance(w, QCheckBox):
            return w.isChecked()
        if isinstance(w, (QSpinBox, QDoubleSpinBox)):
            return w.value()
        raise TypeError(f"unsupported form field {type(w).__name__}")

    def values(self) -> Dict[str, Any]:
        return {k: self.value(k) for k in self.fields}

    def set_value(self, key: str, value: Any) -> None:
        w = self.fields[key]
        if isinstance(w, QLineEdit):
            w.setText(str(value))
        elif isinstance(w, QPlainTextEdit):
            w.setPlainText(str(value))
        elif isinstance(w, QComboBox):
            idx = w.findText(str(value))
            if idx >= 0:
                w.setCurrentIndex(idx)
            elif w.isEditable():
                w.setEditText(str(value))
        elif isinstance(w, QCheckBox):
            w.setChecked(bool(value))
        else:
            w.setValue(value)  # type: ignore[attr-defined]


def error_box(parent: Optional[QWidget], exc: BaseException, detail: str = "") -> None:
    """Modal error dialog (traceback in the detail section)."""
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Warning if isinstance(exc, ParseError) else QMessageBox.Critical)
    box.setWindowTitle("Error")
    box.setText(format_exception(exc))
    if detail and not isinstance(exc, ParseError):
        box.setDetailedText(detail)
    box.exec_()


# --------------------------------------------------------------------------- #
# Panel base class
# --------------------------------------------------------------------------- #
class ModulePanel(QWidget):
    """Base class for feature pages.

    Layout: controls (left, scrollable) | results tabs (right). Subclasses
    fill ``self.form`` / ``self.controls_layout`` and call ``self.run(...)``
    from button handlers. ``self.tabs`` holds result pages created through
    :meth:`add_output`, :meth:`add_table`, :meth:`add_plot`.
    """

    status_changed = pyqtSignal(str)

    def __init__(self, ws: Workspace, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.ws = ws
        self._busy = 0

        self.form = ParamForm()
        self.controls = QWidget()
        self.controls_layout = QVBoxLayout(self.controls)
        self.controls_layout.addWidget(self.form)
        self.buttons_layout = QVBoxLayout()
        self.controls_layout.addLayout(self.buttons_layout)
        self.controls_layout.addStretch(1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidget(self.controls)
        scroll.setMinimumWidth(300)

        self.tabs = QTabWidget()
        split = QSplitter(Qt.Horizontal)
        split.addWidget(scroll)
        split.addWidget(self.tabs)
        split.setStretchFactor(0, 0)
        split.setStretchFactor(1, 1)
        split.setSizes([360, 740])
        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.addWidget(split)

    # ---- result pages ---------------------------------------------------- #
    def add_output(self, title: str = "Result") -> OutputPane:
        pane = OutputPane()
        self.tabs.addTab(pane, title)
        return pane

    def add_table(self, title: str = "Table") -> TableView:
        view = TableView()
        self.tabs.addTab(view, title)
        return view

    def add_plot(self, title: str = "Plot") -> MplCanvas:
        canvas = MplCanvas()
        self.tabs.addTab(canvas, title)
        return canvas

    def add_button(self, text: str, slot: Callable[[], None], tip: str = "") -> QPushButton:
        btn = QPushButton(text)
        btn.setToolTip(tip)
        btn.clicked.connect(lambda _checked=False: slot())
        self.buttons_layout.addWidget(btn)
        return btn

    # ---- execution -------------------------------------------------------- #
    def set_status(self, text: str) -> None:
        self.status_changed.emit(text)

    def fail(self, exc: BaseException, detail: str = "") -> None:
        """Report an error without raising (status line + dialog)."""
        self.set_status(f"Error: {format_exception(exc)}")
        error_box(self, exc, detail)

    def guard(self, fn: Callable[[], None]) -> None:
        """Run ``fn`` on the GUI thread, routing exceptions to :meth:`fail`."""
        try:
            fn()
        except Exception as exc:  # noqa: BLE001
            import traceback
            self.fail(exc, traceback.format_exc())

    def run(self, work: Callable[..., Any], on_result: Callable[[Any], None], *args: Any,
            busy_text: str = "Working...", **kwargs: Any) -> None:
        """Run ``work`` in a worker thread; ``on_result`` runs on the GUI thread.

        Exceptions in ``work`` *or* in ``on_result`` are shown to the user.
        """
        self._busy += 1
        self.set_status(busy_text)
        self.setCursor(Qt.BusyCursor)

        def _ok(value: Any) -> None:
            self.guard(lambda: on_result(value))
            if self._busy <= 1:  # this task is the last one running
                self.set_status("Ready")

        def _err(exc: BaseException, detail: str) -> None:
            self.fail(exc, detail)

        def _done() -> None:
            self._busy -= 1
            if self._busy <= 0:
                self._busy = 0
                self.unsetCursor()

        tasks.submit(work, *args, on_result=_ok, on_error=_err, on_finished=_done, **kwargs)

    # ---- helpers -------------------------------------------------------- #
    def ask_save_path(self, title: str, filters: str, default: str = "") -> Optional[str]:
        path, _ = QFileDialog.getSaveFileName(self, title, default, filters)
        return path or None

    def ask_open_path(self, title: str, filters: str = "All files (*)") -> Optional[str]:
        path, _ = QFileDialog.getOpenFileName(self, title, "", filters)
        return path or None


class WorkspaceCombo(QComboBox):
    """Combo box listing workspace objects (optionally only instances of ``kind``)."""

    def __init__(self, ws: Workspace, kind: Optional[type] = None,
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.ws, self.kind = ws, kind
        self.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        self.setMinimumContentsLength(14)
        ws.changed.connect(self.refresh)
        self.refresh()

    def refresh(self) -> None:
        current = self.currentText()
        self.blockSignals(True)
        self.clear()
        self.addItems(self.ws.names(self.kind))
        idx = self.findText(current)
        if idx >= 0:
            self.setCurrentIndex(idx)
        self.blockSignals(False)

    def selected(self) -> Any:
        """The chosen object; raises :class:`ParseError` when nothing is selected."""
        name = self.currentText()
        if not name:
            raise ParseError("Nothing selected - load or create an object first.")
        return self.ws.get(name)
