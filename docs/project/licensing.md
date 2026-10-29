---
title: Licensing
section: Project
order: 40
lede: What licence covers what, and the one situation where it matters.
---

AstroTools-ADV's own source code is released under the **MIT License**. It is distributed as source; no third-party code is copied into the repository, and dependencies are installed separately.

| Package | Licence |
|---|---|
| astropy | BSD-3-Clause |
| astroquery | BSD-3-Clause |
| NumPy, SciPy | BSD-3-Clause |
| Matplotlib | Matplotlib licence (BSD-compatible) |
| PyQt5 | **GPL-3.0-only, or a commercial licence from Riverbank Computing** |

The documentation is built with MkDocs (BSD-3-Clause), Material for MkDocs (MIT) and pymdown-extensions (MIT) at build time only; none of them is part of the program.

## PyQt5

Importing PyQt5 at run time from MIT-licensed source, with PyQt5 installed by the user or the distribution, is the situation this project is built for. It leaves the MIT source as it is.

If you **redistribute a combined work that includes PyQt5**, such as a frozen executable, an AppImage, a container image or a package that ships both, that combined work has to be provided under the GPLv3, unless you hold a commercial PyQt5 licence. Replacing PyQt5 with another Qt binding is not supported by this code base.

## Data and citations

astroquery contacts third-party services. Their terms of use and citation requirements apply to the data you retrieve; this program grants no rights to that data. If astropy contributes to published work, please cite it. **System → About & Citation** shows the BibTeX for the installed version.

The full text of the project licence is in [`LICENSE`](https://github.com/jan-tdy/AstroTools-ADV/blob/main/LICENSE) and the dependency table is also kept in [`THIRD_PARTY_LICENSES.md`](https://github.com/jan-tdy/AstroTools-ADV/blob/main/THIRD_PARTY_LICENSES.md).
