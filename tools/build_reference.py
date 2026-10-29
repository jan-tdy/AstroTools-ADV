#!/usr/bin/env python3
"""Generate the parts of the documentation that come from the running application.

Writes (all git-ignored, rebuilt by CI):

* ``docs/assets/tools/<key>.png``     screenshot of every tool page
* ``docs/assets/guides/<name>.png``   screenshots produced by ``docs/scenarios/*.py``
* ``docs/reference/**``               one page per tool plus category indexes and the nav
* ``docs/guides/SUMMARY.md``          navigation for the hand-written guides

Every tool page lists the controls, defaults, option lists and tooltips exactly as the
program shows them, and appends the hand-written usage text from ``docs/notes/<key>.md``.
Scenarios drive the real application; one that fails fails the build.

Usage::

    python3 tools/build_reference.py        # then: mkdocs serve   (or mkdocs build --strict)
"""
from __future__ import annotations

import dataclasses
import importlib
import os
import re
import shutil
import sys
import traceback
from pathlib import Path
from typing import Dict, List

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
sys.path[:0] = [str(ROOT), str(ROOT / "tools"), str(DOCS)]
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MPLBACKEND", "Agg")

CATEGORIES = [
    ("Basics", "Units, physical constants and every kind of time."),
    ("Coordinates", "Frames, geometry, catalog matching, observing and the solar system."),
    ("Data", "Tables, FITS files and table file formats."),
    ("Images", "Image containers, WCS, convolution and display."),
    ("Analysis", "Model fitting, statistics, time series and cosmology."),
    ("Online", "astroquery archives and SAMP."),
    ("System", "API Explorer, IERS data, caches and configuration."),
    ("General", "The shared workspace."),
]


def cell(text: str) -> str:
    """Escape text for a Markdown table cell."""
    return " ".join(text.replace("|", "\\|").split())


def code(text: str) -> str:
    text = text.split("\n")[0].strip()
    if len(text) > 48:
        text = text[:45] + "..."
    return f"`{text.replace('`', chr(39))}`" if text else ""


def tool_page(info: dict, category: str, notes: str, shot: bool) -> str:
    out: List[str] = [f"# {info['title']}", "", info["description"], ""]
    if shot:
        out += [f'![{info["title"]} tool page](../../assets/tools/{info["key"]}.png){{ loading=lazy }}', ""]
    if notes.strip():
        out += [notes.strip(), ""]
    out += ["## Controls", ""]
    if info["fields"]:
        out += ["| Field | Type | Default | Notes |", "|---|---|---|---|"]
        for f in info["fields"]:
            detail = f["tooltip"]
            opts = [o for o in f["options"] if o]
            if opts and len(opts) <= 14:
                detail = (detail + " " if detail else "") + "Options: " + ", ".join(f"`{o}`" for o in opts) + "."
            elif opts:
                detail = (detail + " " if detail else "") + f"{len(opts)} options."
            out.append(f"| {cell(f['label'])} | {f['kind']} | {code(f['default'])} | {cell(detail)} |")
    else:
        out.append("This page has no plain input fields; see the usage notes above.")
    out.append("")
    if info["buttons"]:
        out += ["## Actions", ""]
        for b in info["buttons"]:
            tip = f" {b['tooltip']}" if b["tooltip"] else ""
            out.append(f"- **{b['text']}**{tip}")
        out.append("")
    if info["tabs"]:
        out += ["## Result tabs", "", ", ".join(f"**{t}**" for t in info["tabs"]), ""]
    return "\n".join(out)


def run_scenarios(specs, assets: Path) -> Dict[str, str]:
    from PyQt5.QtWidgets import QApplication

    import astrotools_adv.core.widgets as W
    from astrotools_adv.core import tasks
    from astrotools_adv.core.workspace import Workspace
    from scenario_helpers import Helpers

    app = QApplication.instance()
    assets.mkdir(parents=True, exist_ok=True)

    def boom(parent, exc, detail=""):
        raise exc

    original = W.error_box
    W.error_box = boom
    tasks.set_synchronous(True)
    by_key = {s.key: s for s in specs}
    produced: Dict[str, str] = {}
    failures: List[str] = []
    try:
        for path in sorted((DOCS / "scenarios").glob("*.py")):
            if path.name.startswith("_"):
                continue
            mod = importlib.import_module(f"scenarios.{path.stem}")
            try:
                if getattr(mod, "FULL_WINDOW", False):
                    from astrotools_adv.app import MainWindow
                    win = MainWindow(specs, [])
                    win.resize(1360, 860)
                    win.show()
                    panel = win.open_module(mod.TOOL_KEY)
                    app.processEvents()
                    mod.run(panel, win.ws, Helpers(app))
                    app.processEvents()
                    win.grab().save(str(assets / f"{mod.NAME}.png"))
                    win.close()
                    win.deleteLater()
                else:
                    ws = Workspace()
                    panel = by_key[mod.TOOL_KEY].factory(ws)
                    panel.resize(*getattr(mod, "SIZE", (1280, 820)))
                    panel.show()
                    app.processEvents()
                    mod.run(panel, ws, Helpers(app))
                    app.processEvents()
                    panel.grab().save(str(assets / f"{mod.NAME}.png"))
                    panel.close()
                    panel.deleteLater()
                produced[mod.NAME] = str(assets / f"{mod.NAME}.png")
                print(f"  scenario ok: {path.stem}", flush=True)
            except Exception:  # noqa: BLE001 - collect all, fail at the end
                failures.append(path.stem)
                print(f"  scenario FAILED: {path.stem}\n{traceback.format_exc()}", file=sys.stderr, flush=True)
    finally:
        W.error_box = original
        tasks.set_synchronous(False)
    if failures:
        raise SystemExit(f"documentation scenarios failed: {failures}")
    return produced


def write_guides_nav() -> int:
    """``docs/guides/SUMMARY.md`` from the front matter of the guide pages."""
    guides = []
    for md in sorted((DOCS / "guides").glob("*.md")):
        if md.name in ("index.md", "SUMMARY.md"):
            continue
        meta = {}
        text = md.read_text(encoding="utf-8")
        if text.startswith("---\n"):
            for line in text[4:text.index("\n---", 4)].splitlines():
                if ":" in line:
                    k, v = line.split(":", 1)
                    meta[k.strip()] = v.strip()
        title = meta.get("title") or re.search(r"^#\s+(.+)$", text, re.M).group(1)
        guides.append((int(meta.get("order", 100)), title, md.name))
    guides.sort()
    lines = ["* [Overview](index.md)"] + [f"* [{t}]({n})" for _, t, n in guides]
    (DOCS / "guides" / "SUMMARY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return len(guides)


def main() -> None:
    from PyQt5.QtWidgets import QApplication

    from astrotools_adv.core import registry
    from capture import capture

    app = QApplication.instance() or QApplication(sys.argv[:1])  # noqa: F841 - must stay alive
    from astrotools_adv.core import tasks
    tasks.set_synchronous(True)  # no worker threads racing with widget teardown
    specs, failures = registry.discover()
    if failures:
        raise SystemExit(f"modules failed to load: {failures}")

    ref = DOCS / "reference"
    for path in (ref, DOCS / "assets" / "tools", DOCS / "assets" / "guides"):
        if path.exists():
            shutil.rmtree(path)
    print("capturing tool pages ...", flush=True)
    infos = [dataclasses.asdict(i) for i in capture(DOCS / "assets" / "tools", ROOT / "tools" / "_build" / "tools.json")]
    print("running scenarios ...", flush=True)
    shots = run_scenarios(specs, DOCS / "assets" / "guides")

    by_cat: Dict[str, List[dict]] = {name: [] for name, _ in CATEGORIES}
    for info in infos:
        by_cat.setdefault(info["category"], []).append(info)

    nav = ["* [Overview](index.md)"]
    overview = ["# Tool reference", "",
                "Every tool page, generated from the running application. Field names, defaults, option lists and "
                "tooltips are exactly what the program shows. The usage text above each field table is hand-written.", ""]
    documented = 0
    for name, blurb in CATEGORIES:
        items = by_cat.get(name, [])
        if not items:
            continue
        folder = ref / name.lower()
        folder.mkdir(parents=True, exist_ok=True)
        nav += [f"* {name}", f"    * [Overview]({name.lower()}/index.md)"]
        idx = [f"# {name}", "", blurb, "", "| Tool | What it does |", "|---|---|"]
        overview += [f"## {name}", "", blurb, "", "| Tool | What it does |", "|---|---|"]
        for info in items:
            note = DOCS / "notes" / f"{info['key']}.md"
            notes = note.read_text(encoding="utf-8") if note.exists() else ""
            documented += bool(notes)
            shot = (DOCS / "assets" / "tools" / f"{info['key']}.png").exists()
            (folder / f"{info['key']}.md").write_text(tool_page(info, name, notes, shot), encoding="utf-8")
            nav.append(f"    * [{info['title']}]({name.lower()}/{info['key']}.md)")
            idx.append(f"| [{info['title']}]({info['key']}.md) | {cell(info['description'])} |")
            overview.append(f"| [{info['title']}]({name.lower()}/{info['key']}.md) | {cell(info['description'])} |")
        cat_notes = DOCS / "notes" / f"_{name.lower()}.md"
        if cat_notes.exists():
            idx = idx[:4] + [cat_notes.read_text(encoding="utf-8").strip(), ""] + idx[4:]
        (folder / "index.md").write_text("\n".join(idx) + "\n", encoding="utf-8")
        overview.append("")
    (ref / "index.md").write_text("\n".join(overview) + "\n", encoding="utf-8")
    (ref / "SUMMARY.md").write_text("\n".join(nav) + "\n", encoding="utf-8")
    n_guides = write_guides_nav()
    print(f"reference: {len(infos)} tools ({documented} with usage notes), "
          f"{len(shots)} guide screenshots, {n_guides} guides", flush=True)


if __name__ == "__main__":
    main()
