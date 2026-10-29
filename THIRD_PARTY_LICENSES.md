# Third-party software and licensing

AstroTools-ADV's own source code is released under the **MIT License** (see `LICENSE`).
It is distributed as **source only**: no third-party code is copied into or bundled with
this repository. Dependencies are installed separately by the user (or by Code Master).

| Package | License | Role |
|---------|---------|------|
| [astropy](https://www.astropy.org) | BSD-3-Clause | core science library |
| [astroquery](https://astroquery.readthedocs.io) | BSD-3-Clause | online archive access |
| [NumPy](https://numpy.org) | BSD-3-Clause | arrays |
| [SciPy](https://scipy.org) | BSD-3-Clause | numerical routines used by astropy |
| [Matplotlib](https://matplotlib.org) | Matplotlib License (PSF-style, BSD-compatible) | plotting |
| [PyQt5](https://riverbankcomputing.com/software/pyqt/) | **GPL-3.0-only or commercial** | GUI toolkit |

## PyQt5 note

PyQt5 is licensed by Riverbank Computing under the GPLv3 (or a commercial license).
This repository only *imports* PyQt5 at run time and never distributes it, so the MIT
source tree is unaffected. However, if you **redistribute a combined work** that includes
PyQt5 (a frozen executable, an AppImage, a container image, a distro package that depends
on it and ships both, ...), that combined work must comply with the GPLv3 (or you must hold a
commercial PyQt5 license). Replacing PyQt5 with a different Qt binding is out of scope here.

## Data and services

astroquery contacts third-party services (SIMBAD, VizieR, MAST, JPL Horizons, ...). Their
terms of use and citation requirements apply to the data you retrieve; AstroTools-ADV
grants no rights to that data. If you use astropy in published work, please cite it
(Help → About shows the BibTeX).
