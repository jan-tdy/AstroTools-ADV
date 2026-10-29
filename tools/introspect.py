"""Collect the real user interface of every tool by instantiating the panels offscreen.

The documentation reference is generated from this data so that it can never
drift from what the application actually shows.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MPLBACKEND", "Agg")

from PyQt5.QtWidgets import (  # noqa: E402
    QAbstractButton, QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout, QLabel, QLayout,
    QLineEdit, QPlainTextEdit, QPushButton, QSpinBox, QTabWidget, QWidget,
)


@dataclass
class Field:
    label: str
    kind: str
    default: str = ""
    options: List[str] = field(default_factory=list)
    tooltip: str = ""


@dataclass
class ToolInfo:
    key: str
    title: str
    category: str
    description: str
    fields: List[Field] = field(default_factory=list)
    buttons: List[Dict[str, str]] = field(default_factory=list)
    tabs: List[str] = field(default_factory=list)


def _describe(widget: QWidget) -> Optional[Field]:
    tip = widget.toolTip().strip()
    if isinstance(widget, QComboBox):
        opts = [widget.itemText(i) for i in range(widget.count())]
        return Field("", "choice", widget.currentText(), opts, tip)
    if isinstance(widget, QCheckBox):
        return Field("", "checkbox", "on" if widget.isChecked() else "off", [], tip)
    if isinstance(widget, (QSpinBox, QDoubleSpinBox)):
        return Field("", "number", str(widget.value()), [], tip)
    if isinstance(widget, QLineEdit):
        return Field("", "text", widget.text(), [], tip)
    if isinstance(widget, QPlainTextEdit) and not widget.isReadOnly():
        return Field("", "multiline text", widget.toPlainText()[:200], [], tip)
    return None


def _walk(layout: QLayout, out: List[Field]) -> None:
    if isinstance(layout, QFormLayout):
        for row in range(layout.rowCount()):
            label_item = layout.itemAt(row, QFormLayout.LabelRole)
            field_item = layout.itemAt(row, QFormLayout.FieldRole)
            if field_item is None:
                continue
            label = ""
            if label_item is not None and label_item.widget() is not None:
                lw = label_item.widget()
                label = lw.text() if isinstance(lw, QLabel) else ""
            fw = field_item.widget()
            if fw is not None and fw.isHidden():
                continue  # shown only for some option combinations
            if fw is not None:
                info = _describe(fw)
                if info is None:
                    info = Field("", "composite", "", [], fw.toolTip().strip())
                    nested = [w for w in fw.findChildren(QWidget) if _describe(w)]
                    if nested:
                        info = _describe(nested[0]) or info
                info.label = label.strip()
                if info.label:
                    out.append(info)
            elif field_item.layout() is not None:
                _walk(field_item.layout(), out)
        return
    for i in range(layout.count()):
        item = layout.itemAt(i)
        if item.layout() is not None:
            _walk(item.layout(), out)
        elif item.widget() is not None and item.widget().layout() is not None:
            _walk(item.widget().layout(), out)


def inspect_tool(spec: Any, ws: Any) -> ToolInfo:
    widget = spec.factory(ws)
    info = ToolInfo(spec.key, spec.title, spec.category, spec.description)
    controls = getattr(widget, "controls", widget)
    roots: List[QWidget] = [controls] + controls.findChildren(QWidget)
    seen = set()
    for w in roots:
        lay = w.layout()
        if lay is not None and id(lay) not in seen:
            seen.add(id(lay))
            _walk(lay, info.fields)
    # de-duplicate (nested widgets are visited more than once)
    unique, keys = [], set()
    for f in info.fields:
        k = (f.label, f.kind, f.default)
        if k not in keys:
            keys.add(k)
            unique.append(f)
    info.fields = unique
    for b in controls.findChildren(QAbstractButton):
        if isinstance(b, QPushButton) and b.text().strip():
            info.buttons.append({"text": b.text().replace("&", ""), "tooltip": b.toolTip().strip()})
    tabs = getattr(widget, "tabs", None)
    if isinstance(tabs, QTabWidget):
        info.tabs = [tabs.tabText(i) for i in range(tabs.count())]
    widget.deleteLater()
    return info
