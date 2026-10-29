---
title: Getting started
section: Start
order: 0
lede: Install the dependencies, start the program and run a first conversion.
---

## Requirements

| | Needed | Tested with |
|---|---|---|
| Python | 3.9 or newer | 3.13 |
| astropy | 6.0 or newer (older versions start, with a warning) | 8.0 |
| astroquery | 0.4.7 or newer | 0.4.11 |
| PyQt5 | 5.15 | 5.15.11 |
| matplotlib, numpy, scipy | any current release | 3.11, 2.5, 1.18 |

Python 3.9 is the lowest version the source's syntax allows (checked with `vermin`); the test-suite runs on 3.13. The program is developed and tested on Linux. It is plain Python with Qt, so macOS and Windows will probably work, but nothing is verified there.

## Install

### Debian and Ubuntu (recommended)

Distribution packages avoid the "externally managed environment" error that recent Debian-based systems give for `pip install`.

```bash
sudo apt install python3-pyqt5 python3-astropy python3-astroquery \
                 python3-matplotlib python3-scipy
git clone https://github.com/jan-tdy/AstroTools-ADV
cd AstroTools-ADV
python3 astrotools.py
```

The distribution's astropy may be older than the version listed above. If a tool misbehaves, check **Help → About** for the installed versions and compare with the table.

### pip

```bash
git clone https://github.com/jan-tdy/AstroTools-ADV
cd AstroTools-ADV
python3 -m venv --system-site-packages .venv
. .venv/bin/activate
python3 -m pip install -r requirements.txt
python3 astrotools.py
```

### Code Master

The repository contains a `codemaster-metadata.json`, so [Code Master](https://github.com/jan-tdy/codemaster) lists it in its Store once the file is on the default branch. Installing from there clones the repository, installs the requirements (apt first, pip as a fallback) and can add a menu launcher.

### Menu launcher

```bash
sed "s#__INSTALL_DIR__#$PWD#g" assets/astrotools-adv.desktop \
    > ~/.local/share/applications/astrotools-adv.desktop
```

## First run

The window has a sidebar of tool pages on the left, the selected tool in the middle, and a log line and status bar below. Pages are created the first time you open them, so start-up stays fast.

1. Open **Coordinates → Frame converter**.
2. Leave *Source* on `Typed text` and the lines as `10.684 41.269` (the position of M31).
3. Set the second *Frame* (under *Target frame*) to `Galactic`.
4. Press **Convert**.

The **Result** tab shows `l = 121.1738`, `b = -21.5730`. The **Info** tab adds the sexagesimal form and the constellation.

![Frame converter after converting M31 to Galactic coordinates](assets/guides/frame-converter.png "Frame converter: M31 from ICRS to Galactic.")

Press **Store SkyCoord in workspace** to keep the result. Any other tool that asks for a coordinate list can now pick it from a drop-down. See [the workspace](concepts/workspace.md).

## Where to go next

- [Entering values](concepts/entering-values.md): the syntax every text field accepts.
- [Guides](guides/index.md): complete workflows with screenshots.
- [Tool reference](reference/index.md): every tool, field and default.
- The **System → API Explorer** page reaches every public astropy function and class, including ones without a dedicated form.
