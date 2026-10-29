---
title: Building the documentation
section: Project
order: 30
lede: How this site is produced and how to preview it locally.
---

```bash
python3 -m pip install -r requirements.txt markdown pygments
python3 tools/build_docs.py site
python3 -m http.server -d site 8000
```

Open `http://localhost:8000`. The build runs Qt offscreen; no display is required.

## Sources

| Source | Becomes |
|---|---|
| `docs/content/**/*.md` | pages in the matching section (front matter: `title`, `section`, `order`, `lede`) |
| `docs/notes/<tool key>.md` | prose shown above that tool's controls in the reference |
| `docs/notes/_<category>.md` | introduction of a category page |
| `docs/scenarios/*.py` | screenshots and a check that each documented workflow works |
| the live application | every tool's controls, defaults, tooltips, buttons and tabs |

Links inside content use site-absolute paths such as `/guides/x.html`; the build rewrites them to relative links so the site works under any URL prefix.

## Scenarios

A scenario drives one tool page in the real application and the build photographs the result:

```python
TOOL_KEY = "coord_convert"      # registry key of the page
NAME = "frame-converter"        # writes img/guides/frame-converter.png

def run(panel, ws, h):
    h.set(panel, "Lines", "10.684 41.269")      # set a field by its visible label
    h.set(panel, "Frame", "Galactic", nth=1)    # second field with that label
    h.click(panel, "Convert")                   # press a button, wait for the result
    assert "121.17" in h.output_text(panel, "Result")
```

A scenario that raises, or a field or button that does not exist, fails the build, so a guide cannot describe steps that no longer work. A scenario with `FULL_WINDOW = True` photographs the whole main window instead of a single page.

## Publishing

The workflow in `.github/workflows/docs.yml` builds the site and deploys it with GitHub Pages on every push to `main`. In the repository settings, set **Pages → Source** to **GitHub Actions** once.
