# AstroTools-ADV

A PyQt5 desktop application that exposes the **astropy** ecosystem (and **astroquery**)
through a GUI. Everything runs locally; online archives are only contacted when you
press a query button.

If you found this useful, please give this repo a star.

## Documentation

Full documentation, with a page for every tool and worked guides: <https://jan-tdy.github.io/AstroTools-ADV/>. It is built from `docs/` with MkDocs; see `docs/project/building-the-docs.md` to build it locally.

## Tools

| Category | Pages |
|----------|-------|
| Basics | Units & constants, Time |
| Coordinates | Converter, separations/offsets, catalog matching, observing (AltAz, rise/set, twilight), solar system |
| Data | Table tools, FITS, ASCII/VOTable/other table I/O |
| Images | NDData/CCDData/Cutout2D, WCS, convolution, visualization (stretches, RGB, WCSAxes) |
| Analysis | Modeling & fitting, statistics, time series (Lomb-Scargle, BLS), cosmology |
| Online | astroquery (dedicated forms + generic browser for every service), SAMP |
| System | API Explorer (every public astropy callable), IERS/cache/config utilities |

Tools exchange objects (tables, coordinates, times, images, WCS, models) through a shared
**Workspace**.

## Install and run (Linux)

```bash
sudo apt install python3-pyqt5 python3-astropy python3-astroquery python3-matplotlib python3-scipy
python3 astrotools.py
```

or with pip: `python3 -m pip install --user -r requirements.txt`.
Tested with Python 3.13, astropy 8.0, astroquery 0.4.11, PyQt5 5.15.

It is also published for [Code Master](https://github.com/jan-tdy/codemaster) via
`codemaster-metadata.json`.

## Tests

```bash
python3 -m pip install --user -r requirements-dev.txt
QT_QPA_PLATFORM=offscreen python3 -m pytest
```

No test touches the network.

## License

MIT (c) 2026 Jan Dubovsky. See `LICENSE`. Dependency licenses, including the **PyQt5 GPLv3**
note for redistributed binaries, are in `THIRD_PARTY_LICENSES.md`.
