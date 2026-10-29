---
title: Adding a tool
section: Project
order: 10
lede: A complete minimal tool page, and what the documentation build derives from it.
---

Create `astrotools_adv/modules/my_tool.py`:

```python
from __future__ import annotations

import numpy as np
from astropy.table import Table
from PyQt5.QtWidgets import QWidget

from ..core.parsing import parse_array
from ..core.registry import ModuleSpec
from ..core.widgets import ModulePanel
from ..core.workspace import Workspace


class SquarePanel(ModulePanel):
    def __init__(self, ws: Workspace) -> None:
        super().__init__(ws)
        self.form.add_text("x", "Values", "1 2 3", tip="Numbers or an expression")
        self.form.add_text("name", "Store as", "squares")
        self.table = self.add_table("Result")
        self.add_button("Compute", self.compute)

    def compute(self) -> None:
        x = parse_array(self.form.value("x"))          # ParseError -> warning dialog

        def work() -> Table:                            # worker thread: data only
            return Table({"x": x, "x2": x ** 2})

        def show(t: Table) -> None:                     # GUI thread: widgets allowed
            self.table.set_table(t)
            self.ws.put(self.form.value("name"), t)

        self.run(work, show)


def _make(ws: Workspace) -> QWidget:
    return SquarePanel(ws)


SPECS = [ModuleSpec("my_square", "Squares", "Basics", _make, "Square a list of numbers")]
```

The page appears in the sidebar the next time the program starts. Choose an existing category name unless you are adding a new area.

## Test it

```python
def test_square(qtbot, ws):
    panel = SquarePanel(ws)
    qtbot.addWidget(panel)
    panel.form.set_value("x", "2 3")
    panel.compute()
    assert list(ws.get("squares")["x2"]) == [4.0, 9.0]
```

`ws` and synchronous task execution come from `tests/conftest.py`. `tests/test_core.py` additionally checks that every registered page opens and that keys are unique.

## Documentation for free

The reference build opens every page offscreen and reads its labels, defaults, option lists, tooltips, buttons and result tabs. Writing good tooltips is therefore the documentation of the tool. For prose, add `docs/notes/<key>.md` (shown above the controls of that tool) and, for a worked example, a scenario; see [Building the documentation](building-the-docs.md).
