---
title: Architecture
section: Project
order: 0
lede: How the code is organised, and the rules that keep 100+ tool pages consistent.
---

## Layout

```text
astrotools.py              launcher
astrotools_adv/
  app.py                   main window, exception hook, entry point
  core/
    registry.py            discovers modules, isolates import failures
    workspace.py           shared object store (Qt signals on change)
    tasks.py               thread-pool runner with GUI-thread callbacks
    parsing.py             text -> Quantity / Angle / Time / SkyCoord / expressions
    widgets.py             ModulePanel, ParamForm, TableView, MplCanvas, WorkspaceCombo
  modules/                 one file per feature area, each exports SPECS
tests/                     pytest + pytest-qt, offscreen, no network
tools/ docs/               documentation generator and content
```

## Registry and lazy pages

Every non-underscore file in `astrotools_adv/modules/` exports `SPECS`, a list of `ModuleSpec(key, title, category, factory, description)`. `registry.discover()` imports each file and collects them. A module that fails to import is reported in the log and the rest of the application starts normally. `factory(workspace)` is only called when a page is first opened, so heavy imports belong in the panel, not at import time.

## ModulePanel

`ModulePanel` provides the standard two-column page: a `ParamForm` and buttons on the left, result tabs on the right. Its helpers cover most of what a tool needs:

| Helper | Use |
|---|---|
| `add_output()`, `add_table()`, `add_plot()` | create a result tab and return the widget |
| `add_button(text, slot)` | button whose slot runs inside `guard()`, so exceptions become dialogs |
| `run(work, on_result, ...)` | run `work` in a worker thread and call `on_result` on the GUI thread |
| `fail(exc)` / `guard(fn)` | route an exception to the status bar and an error dialog |

## Threading rule

`work` runs off the GUI thread and must return plain data (arrays, tables, strings). Anything that creates Qt widgets or touches matplotlib happens in `on_result`. Tests switch the task runner to synchronous mode so panels can be driven deterministically.

## Pitfalls that have bitten before

- **Do not name a panel method after a `QWidget` method.** A method called `show`, `create`, `render` or `mask` silently replaces the Qt one. `tests/test_core.py` scans every panel for this.
- **`ParamForm.values()` skips custom widgets** added with `add_widget`; read those from the widget directly.
- **`parse_quantity` and `safe_eval` are shared.** Fix input-syntax bugs there, not inside a panel.
- **Offline.** Never rely on a network call in code paths a test exercises; use the mocks in `tests/test_astroquery_*.py` as the pattern.
