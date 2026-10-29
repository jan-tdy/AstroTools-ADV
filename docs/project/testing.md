---
title: Testing
section: Project
order: 20
lede: How the test-suite is organised and what it deliberately does not cover.
---

```bash
python3 -m pip install -r requirements-dev.txt
QT_QPA_PLATFORM=offscreen python3 -m pytest
```

`.github/workflows/ci.yml` runs the same command on every pull request. The suite runs Qt offscreen, uses matplotlib's `Agg` backend and switches background tasks to run inline, so it needs no display and finishes in about a minute.

## Conventions

- **Numbers are checked against known values**, for example M31 from ICRS to Galactic is `(121.1738, -21.5730)`, the Planck18 luminosity distance at z = 1 is 6791.27 Mpc in astropy 8, and a Lomb-Scargle run recovers an injected 3.7-day period.
- **Panels are driven the way a user does it**: set form values, call the button's handler, read the result tab or the workspace.
- **No network.** astroquery panels run against a fake service that checks each call against the real method signature. Anything that must be unreachable asserts that it raises instead of connecting.
- **Core behaviour** (parsing, tasks, widgets, registry, naming rules) is in `tests/test_core.py`.

## What the suite does not tell you

Live archive behaviour (SIMBAD, VizieR, MAST and others change their schemas), visual layout on other desktops, and optional-dependency paths such as HDF5, Parquet and ASDF when those packages are installed. Those need a manual check.
