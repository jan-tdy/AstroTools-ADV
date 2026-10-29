#!/usr/bin/env python3
"""Run one documentation scenario and show its result tabs.

    python3 tools/run_scenario.py frame_converter [out.png]

Use while writing a scenario or checking a usage note: it executes the same steps the
documentation build will, prints every result tab and optionally saves a screenshot.
"""
import importlib
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "tools"), str(ROOT / "docs")]
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MPLBACKEND", "Agg")

from PyQt5.QtWidgets import QApplication  # noqa: E402

app = QApplication([])

import astrotools_adv.core.widgets as W  # noqa: E402
from astrotools_adv.core import registry, tasks  # noqa: E402
from astrotools_adv.core.workspace import Workspace  # noqa: E402
from scenario_helpers import Helpers  # noqa: E402


def boom(parent, exc, detail=""):
    raise exc


def main() -> None:
    name = sys.argv[1]
    shot = sys.argv[2] if len(sys.argv) > 2 else None
    W.error_box = boom
    tasks.set_synchronous(True)
    mod = importlib.import_module(f"scenarios.{name}")
    specs, _ = registry.discover()
    spec = {s.key: s for s in specs}[mod.TOOL_KEY]
    ws = Workspace()
    panel = spec.factory(ws)
    panel.resize(*getattr(mod, "SIZE", (1280, 820)))
    panel.show()
    app.processEvents()
    try:
        mod.run(panel, ws, Helpers(app))
        app.processEvents()
        print("scenario ran without errors")
    finally:
        tabs = getattr(panel, "tabs", None)
        for i in range(tabs.count() if tabs else 0):
            w = tabs.widget(i)
            text = ""
            if hasattr(w, "toPlainText"):
                text = w.toPlainText()
            elif hasattr(w, "model") and hasattr(w.model, "to_csv"):
                text = w.model.to_csv()
            print(f"--- tab: {tabs.tabText(i)} ---\n{text[:1500]}")
        print("--- workspace:", {n: type(ws.get(n)).__name__ for n in ws.names()})
        if shot:
            panel.grab().save(shot)


if __name__ == "__main__":
    main()
