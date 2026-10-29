"""Dump tool metadata (JSON) and a screenshot of every tool page."""
from __future__ import annotations

import dataclasses
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import introspect  # noqa: E402
from PyQt5.QtWidgets import QApplication  # noqa: E402

from astrotools_adv.core import registry  # noqa: E402
from astrotools_adv.core.workspace import Workspace  # noqa: E402

SHOT_SIZE = (1180, 700)


def capture(img_dir: Path, json_path: Path, shots: bool = True) -> list:
    """Return ``ToolInfo`` objects; write ``<img_dir>/<key>.png`` and ``json_path``."""
    app = QApplication.instance() or QApplication(sys.argv[:1])
    specs, failures = registry.discover()
    if failures:
        raise SystemExit(f"modules failed to load: {failures}")
    ws = Workspace()
    infos = []
    img_dir.mkdir(parents=True, exist_ok=True)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    for spec in specs:
        infos.append(introspect.inspect_tool(spec, ws))
        if shots:
            widget = spec.factory(ws)
            widget.resize(*SHOT_SIZE)
            widget.show()
            app.processEvents()
            widget.grab().save(str(img_dir / f"{spec.key}.png"))
            widget.close()
            widget.deleteLater()
    json_path.write_text(
        json.dumps([dataclasses.asdict(i) for i in infos], indent=1), encoding="utf-8")
    return infos


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "tools" / "_build"
    result = capture(target / "tools", target / "tools.json")
    print(f"captured {len(result)} tools into {target}")
