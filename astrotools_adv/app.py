"""Main window and application entry point."""
from __future__ import annotations

import logging
import sys
from typing import Dict, List, Optional, Tuple

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QAction, QApplication, QLabel, QMainWindow, QMessageBox, QSplitter, QStackedWidget,
    QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from . import APP_NAME, __version__
from .core import registry
from .core.widgets import ModulePanel, OutputPane, error_box
from .core.workspace import Workspace

log = logging.getLogger(__name__)
KEY_ROLE = Qt.UserRole


class MainWindow(QMainWindow):
    def __init__(self, specs: List[registry.ModuleSpec],
                 failures: Optional[List[Tuple[str, str]]] = None) -> None:
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} {__version__}")
        self.resize(1280, 800)
        self.ws = Workspace(self)
        self._specs: Dict[str, registry.ModuleSpec] = {s.key: s for s in specs}
        self._pages: Dict[str, int] = {}

        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setMinimumWidth(210)
        self.stack = QStackedWidget()
        welcome = QLabel(
            f"<h2>{APP_NAME}</h2><p>Choose a tool in the sidebar.</p>"
            "<p>Objects you store in the <b>Workspace</b> can be reused by other tools.</p>")
        welcome.setAlignment(Qt.AlignCenter)
        welcome.setWordWrap(True)
        self.stack.addWidget(welcome)

        categories: Dict[str, QTreeWidgetItem] = {}
        for spec in specs:
            parent = categories.get(spec.category)
            if parent is None:
                parent = QTreeWidgetItem(self.tree, [spec.category])
                parent.setFlags(parent.flags() & ~Qt.ItemIsSelectable)
                categories[spec.category] = parent
            item = QTreeWidgetItem(parent, [spec.title])
            item.setData(0, KEY_ROLE, spec.key)
            item.setToolTip(0, spec.description)
        self.tree.expandAll()
        self.tree.currentItemChanged.connect(self._on_select)

        self.log = OutputPane()
        self.log.setMaximumHeight(110)
        self.ws.message.connect(self.log.append_text)

        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.addWidget(self.stack, 1)
        rl.addWidget(self.log)
        split = QSplitter(Qt.Horizontal)
        split.addWidget(self.tree)
        split.addWidget(right)
        split.setStretchFactor(1, 1)
        split.setSizes([240, 1040])
        self.setCentralWidget(split)

        self.status_label = QLabel("Ready")
        self.statusBar().addWidget(self.status_label, 1)
        self._build_menu()
        for name, err in failures or []:
            self.log.append_text(f"[module load failed] {name}: {err}")
        if failures:
            self.statusBar().showMessage(f"{len(failures)} module(s) failed to load - see log.", 8000)

    def _build_menu(self) -> None:
        bar = self.menuBar()
        file_menu = bar.addMenu("&File")
        quit_act = QAction("&Quit", self, shortcut="Ctrl+Q", triggered=self.close)
        file_menu.addAction(quit_act)
        ws_menu = bar.addMenu("&Workspace")
        ws_menu.addAction(QAction("&Clear workspace", self, triggered=self._clear_ws))
        ws_menu.addAction(QAction("&List objects", self, triggered=self._list_ws))
        help_menu = bar.addMenu("&Help")
        help_menu.addAction(QAction("&About", self, triggered=self._about))

    def _clear_ws(self) -> None:
        if QMessageBox.question(self, "Clear workspace", "Remove all stored objects?") \
                == QMessageBox.Yes:
            self.ws.clear()

    def _list_ws(self) -> None:
        names = self.ws.names()
        lines = [f"{n}: {type(self.ws.get(n)).__name__}" for n in names] or ["(empty)"]
        QMessageBox.information(self, "Workspace", "\n".join(lines))

    def _about(self) -> None:
        import astropy
        try:
            import astroquery
            aq = astroquery.__version__
        except Exception:  # noqa: BLE001
            aq = "not installed"
        from PyQt5.QtCore import PYQT_VERSION_STR
        QMessageBox.about(
            self, f"About {APP_NAME}",
            f"<b>{APP_NAME}</b> {__version__}<br>MIT License (c) 2026 Jan Dubovsky<br><br>"
            f"astropy {astropy.__version__}<br>astroquery {aq}<br>PyQt5 {PYQT_VERSION_STR} "
            "(GPLv3, installed separately - not bundled)")

    def _on_select(self, item: Optional[QTreeWidgetItem], _prev=None) -> None:
        if item is None:
            return
        key = item.data(0, KEY_ROLE)
        if key is None:
            return
        self.open_module(key)

    def open_module(self, key: str) -> QWidget:
        """Show (creating lazily on first use) the page for ``key``."""
        if key not in self._pages:
            spec = self._specs[key]
            try:
                page = spec.factory(self.ws)
            except Exception as exc:  # noqa: BLE001
                log.exception("creating %s failed", key)
                error_box(self, exc)
                page = QLabel(f"Could not open {spec.title}:\n{exc}")
            if isinstance(page, ModulePanel):
                page.status_changed.connect(self.status_label.setText)
            self._pages[key] = self.stack.addWidget(page)
        self.stack.setCurrentIndex(self._pages[key])
        return self.stack.currentWidget()


def main(argv: Optional[List[str]] = None) -> int:
    logging.basicConfig(level=logging.WARNING)
    app = QApplication(list(argv if argv is not None else sys.argv))
    app.setApplicationName(APP_NAME)
    specs, failures = registry.discover()
    win = MainWindow(specs, failures)
    win.show()
    return app.exec_()


if __name__ == "__main__":
    sys.exit(main())
