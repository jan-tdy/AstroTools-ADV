"""Module registry: every file in ``astrotools_adv.modules`` exports ``SPECS``."""
from __future__ import annotations

import importlib
import logging
import pkgutil
from dataclasses import dataclass
from typing import Callable, List, Tuple

from PyQt5.QtWidgets import QWidget

from .workspace import Workspace

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class ModuleSpec:
    """One page in the sidebar.

    ``factory`` receives the shared :class:`Workspace` and returns the page widget.
    It is only called when the user first opens the page, so heavy imports belong
    inside the panel, not at module import time.
    """

    key: str
    title: str
    category: str
    factory: Callable[[Workspace], QWidget]
    description: str = ""


def discover() -> Tuple[List[ModuleSpec], List[Tuple[str, str]]]:
    """Import every module and collect specs. Returns ``(specs, failures)``.

    A module that fails to import never takes the application down; it is
    reported in ``failures`` as ``(module_name, error_text)``.
    """
    from .. import modules

    specs: List[ModuleSpec] = []
    failures: List[Tuple[str, str]] = []
    seen = set()
    for info in sorted(pkgutil.iter_modules(modules.__path__), key=lambda i: i.name):
        if info.name.startswith("_"):
            continue
        full = f"{modules.__name__}.{info.name}"
        try:
            mod = importlib.import_module(full)
            for spec in getattr(mod, "SPECS"):
                if spec.key in seen:
                    raise ValueError(f"duplicate module key {spec.key!r}")
                seen.add(spec.key)
                specs.append(spec)
        except Exception as exc:  # noqa: BLE001 - isolate faulty modules
            log.exception("module %s failed to load", full)
            failures.append((full, f"{type(exc).__name__}: {exc}"))
    return specs, failures
