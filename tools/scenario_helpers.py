"""Small helpers for driving panels from documentation scenarios."""
from __future__ import annotations

from typing import Any, List

from PyQt5.QtWidgets import (
    QAbstractButton, QApplication, QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout,
    QLabel, QLineEdit, QPlainTextEdit, QSpinBox, QTabWidget, QWidget,
)

from astrotools_adv.core import tasks


class Helpers:
    """Find widgets by their visible label and operate them."""

    def __init__(self, app: QApplication) -> None:
        self.app = app

    def pump(self) -> None:
        tasks.wait_all()
        self.app.processEvents()

    def _rows(self, root: QWidget) -> List[tuple]:
        rows = []
        for form in self._forms(root):
            for r in range(form.rowCount()):
                li = form.itemAt(r, QFormLayout.LabelRole)
                fi = form.itemAt(r, QFormLayout.FieldRole)
                if li is None or fi is None or li.widget() is None:
                    continue
                label = li.widget().text().replace("&", "").strip() if isinstance(li.widget(), QLabel) else ""
                rows.append((label, fi.widget()))
        return rows

    def _forms(self, root: QWidget) -> List[QFormLayout]:
        found: List[QFormLayout] = []

        def walk(layout: Any) -> None:
            if layout is None:
                return
            if isinstance(layout, QFormLayout):
                found.append(layout)
            for i in range(layout.count()):
                item = layout.itemAt(i)
                walk(item.layout())
                if item.widget() is not None:
                    walk(item.widget().layout())

        for w in [root] + root.findChildren(QWidget):
            walk(w.layout())
        return found

    def field(self, root: QWidget, label: str, nth: int = 0) -> QWidget:
        """The ``nth`` field whose row label equals ``label`` (case-insensitive)."""
        matches = [w for text, w in self._rows(root) if text.lower() == label.lower() and w]
        if len(matches) <= nth:
            have = sorted({text for text, _ in self._rows(root)})
            raise KeyError(f"no field {label!r} (#{nth}); available: {have}")
        return matches[nth]

    def set(self, root: QWidget, label: str, value: Any, nth: int = 0) -> None:
        w = self.field(root, label, nth)
        if isinstance(w, QLineEdit):
            w.setText(str(value))
        elif isinstance(w, QPlainTextEdit):
            w.setPlainText(str(value))
        elif isinstance(w, QComboBox):
            idx = w.findText(str(value))
            if idx < 0 and w.isEditable():
                w.setEditText(str(value))
            elif idx < 0:
                raise ValueError(f"{label!r}: no option {value!r} in "
                                 f"{[w.itemText(i) for i in range(w.count())]}")
            else:
                w.setCurrentIndex(idx)
        elif isinstance(w, QCheckBox):
            w.setChecked(bool(value))
        elif isinstance(w, (QSpinBox, QDoubleSpinBox)):
            w.setValue(value)
        else:
            raise TypeError(f"{label!r}: unsupported widget {type(w).__name__}")
        self.app.processEvents()

    def click(self, root: QWidget, text: str) -> None:
        """Press the button whose text equals ``text`` and wait for background work."""
        for b in root.findChildren(QAbstractButton):
            if b.text().replace("&", "").strip() == text and b.isEnabled():
                b.click()
                self.pump()
                return
        have = [b.text() for b in root.findChildren(QAbstractButton)]
        raise KeyError(f"no enabled button {text!r}; available: {have}")

    def tab(self, panel: QWidget, title: str) -> None:
        tabs = getattr(panel, "tabs", None) or panel.findChild(QTabWidget)
        for i in range(tabs.count()):
            if tabs.tabText(i) == title:
                tabs.setCurrentIndex(i)
                self.app.processEvents()
                return
        raise KeyError(f"no tab {title!r}; have {[tabs.tabText(i) for i in range(tabs.count())]}")

    def output_text(self, panel: QWidget, tab_title: str) -> str:
        """Text of a result tab: output panes as plain text, tables as CSV."""
        tabs = getattr(panel, "tabs")
        for i in range(tabs.count()):
            if tabs.tabText(i) == tab_title:
                w = tabs.widget(i)
                if hasattr(w, "toPlainText"):
                    return w.toPlainText()
                if hasattr(w, "model") and hasattr(w.model, "to_csv"):
                    return w.model.to_csv()
                return ""
        raise KeyError(tab_title)
