---
title: Building the documentation
---

# Building the documentation

The site is built with [MkDocs](https://www.mkdocs.org/) and the [Material](https://squidfunnel.github.io/mkdocs-material/) theme. Part of it is written by hand and part is generated from the running application, so there are two steps.

```bash
python3 -m pip install -r requirements.txt -r docs/requirements.txt
python3 tools/build_reference.py     # tool pages, screenshots, guide navigation
mkdocs serve                         # live preview on http://127.0.0.1:8000
mkdocs build --strict                # what CI runs; broken links fail the build
```

`build_reference.py` runs Qt offscreen, so no display is needed. Run it again after you change a tool's fields, tooltips, a note or a scenario.

## Where things live

| Path | Purpose |
|---|---|
| `docs/*.md`, `docs/concepts/`, `docs/project/` | Hand-written pages. Navigation is in `docs/SUMMARY.md`. |
| `docs/guides/*.md` | Hand-written guides. They appear in the navigation automatically, ordered by the `order:` front-matter key. |
| `docs/notes/<tool key>.md` | Usage text for one tool. It is inserted between the screenshot and the generated field tables of that tool's page. |
| `docs/notes/_<category>.md` | Introduction of a category overview page. |
| `docs/scenarios/*.py` | Executable scenarios that produce screenshots. |
| `docs/reference/`, `docs/assets/tools/`, `docs/assets/guides/` | Generated. Ignored by git. |

## What is generated

For every tool the generator opens the real page offscreen and reads its field labels, types, defaults, option lists, tooltips, buttons and result tabs. Good tooltips are therefore the first layer of documentation. The notes file adds the part a tooltip cannot: the order of steps, what the results mean and what to watch for.

## Scenarios

A scenario drives one tool page in the real application and the build photographs the result.

```python
TOOL_KEY = "coord_convert"      # registry key of the page
NAME = "frame-converter"        # writes docs/assets/guides/frame-converter.png

def run(panel, ws, h):
    h.set(panel, "Lines", "10.684 41.269")      # set a field by its visible label
    h.set(panel, "Frame", "Galactic", nth=1)    # second field with that label
    h.click(panel, "Convert")                   # press a button and wait for the result
    assert "121.17" in h.output_text(panel, "Result")
```

`h.tab(panel, "Plot")` switches the visible result tab. A scenario that raises, or that refers to a field or button that no longer exists, fails the build, so a guide cannot describe steps that stopped working. Set `FULL_WINDOW = True` to photograph the whole main window instead of a single page. Try one without building everything:

```bash
python3 tools/run_scenario.py frame_converter /tmp/shot.png
```

!!! note
    Screenshots show real output of the real code. Do not use mocked data in a screenshot; astroquery pages, which need the network, are documented from their forms only.

## Publishing

`.github/workflows/docs.yml` builds the site on every pull request that touches documentation and deploys it with GitHub Pages on every push to `main`. In the repository settings, set **Pages → Source** to **GitHub Actions** once.
