"""Workspace browser: inspect and delete stored objects. Also the reference panel."""
from __future__ import annotations

from PyQt5.QtWidgets import QWidget

from ..core.registry import ModuleSpec
from ..core.widgets import ModulePanel, WorkspaceCombo
from ..core.workspace import Workspace


class WorkspaceBrowser(ModulePanel):
    def __init__(self, ws: Workspace) -> None:
        super().__init__(ws)
        self.combo = WorkspaceCombo(ws)
        self.form.add_widget("name", "Object", self.combo)
        self.out = self.add_output("Object")
        self.add_button("Show", self.show_selected)
        self.add_button("Delete", self.delete_selected)
        ws.changed.connect(self.show_selected)
        self.show_selected()

    def show_selected(self) -> None:
        name = self.combo.currentText()
        if not name:
            self.out.show_text("(workspace is empty)")
            return
        obj = self.ws.get(name)
        self.out.show_text(f"{name}  <{type(obj).__module__}.{type(obj).__name__}>\n\n{obj!r}")

    def delete_selected(self) -> None:
        name = self.combo.currentText()
        if name:
            self.ws.remove(name)


def _make(ws: Workspace) -> QWidget:
    return WorkspaceBrowser(ws)


SPECS = [ModuleSpec("workspace", "Workspace", "General", _make,
                    "Objects shared between tools")]
