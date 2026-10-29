"""Shared in-memory workspace so panels can hand objects to each other."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from PyQt5.QtCore import QObject, pyqtSignal


class Workspace(QObject):
    """Named store of live objects (Table, SkyCoord, Time, HDUList, WCS, ...)."""

    changed = pyqtSignal()
    message = pyqtSignal(str)

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._items: Dict[str, Any] = {}

    def put(self, name: str, obj: Any) -> str:
        """Store ``obj`` under ``name``; returns the final (stripped) name."""
        name = (name or "").strip()
        if not name:
            raise ValueError("Workspace name must not be empty.")
        self._items[name] = obj
        self.changed.emit()
        return name

    def get(self, name: str) -> Any:
        try:
            return self._items[name]
        except KeyError:
            raise KeyError(f"Nothing named {name!r} in the workspace.") from None

    def remove(self, name: str) -> None:
        if self._items.pop(name, None) is not None:
            self.changed.emit()

    def clear(self) -> None:
        if self._items:
            self._items.clear()
            self.changed.emit()

    def names(self, kind: Optional[type] = None) -> List[str]:
        """Sorted names, optionally only those whose object is an instance of ``kind``."""
        if kind is None:
            return sorted(self._items)
        return sorted(n for n, o in self._items.items() if isinstance(o, kind))

    def __contains__(self, name: str) -> bool:
        return name in self._items

    def log(self, text: str) -> None:
        self.message.emit(text)
