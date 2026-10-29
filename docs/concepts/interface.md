---
title: The interface
section: Concepts
order: 0
lede: How the main window and a typical tool page are laid out.
---

## Main window

| Area | Purpose |
|---|---|
| Sidebar | Tool pages grouped by category. Hover a name to see its one-line description. |
| Tool page | The selected tool. Created on first use and kept alive, so switching away and back keeps your inputs. |
| Log | Messages that are not errors, for example which module failed to load. |
| Status bar | `Ready`, `Working...` while a background task runs, or the last error. |

The **Workspace** menu clears the shared workspace or lists what is in it. **Help → About** shows the versions of astropy, astroquery and PyQt5 in use.

## A tool page

Almost every page has the same shape.

- **Left: controls.** A scrollable column of labelled fields, then buttons. Hover a field for its tooltip.
- **Right: results.** A set of tabs, typically a text or table tab plus plots. Table tabs have a **Copy CSV** button; plot tabs have the matplotlib toolbar for zoom, pan and *Save*.

The divider between the two halves can be dragged.

Fields come in a few kinds. Text fields are parsed by the rules in [Entering values](entering-values.md). Drop-downs hold fixed options or the objects currently in the workspace. Multi-line fields take one item per line, and lines beginning with `#` are ignored where lists are expected.

## Errors

Bad input never closes the program. A problem with what you typed (an unknown unit, an unparsable time) opens a warning dialog that says which field and why. An unexpected failure opens an error dialog with the full traceback in the details section, and the status bar keeps the last message.
