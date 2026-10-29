---
title: AstroTools-ADV
hide:
  - navigation
  - toc
---

# AstroTools-ADV

A desktop interface for **astropy** and **astroquery**. Convert coordinates, fit models, edit FITS headers or query SIMBAD from forms, tables and plots, and fall back to the API Explorer for anything without a dedicated page.

[Get started](getting-started.md){ .md-button .md-button--primary }
[Browse the tools](reference/index.md){ .md-button }
[Source on GitHub](https://github.com/jan-tdy/AstroTools-ADV){ .md-button }

![AstroTools-ADV main window](assets/guides/hero.png){ loading=lazy }

## What is inside

<div class="grid cards" markdown>

-   **Basics**

    Units, physical constants and every kind of time.

    [:octicons-arrow-right-24: Basics](reference/basics/index.md)

-   **Coordinates**

    Frames, geometry, catalog matching, observing and the solar system.

    [:octicons-arrow-right-24: Coordinates](reference/coordinates/index.md)

-   **Data**

    Tables, FITS files and table file formats.

    [:octicons-arrow-right-24: Data](reference/data/index.md)

-   **Images**

    Image containers, WCS, convolution and display.

    [:octicons-arrow-right-24: Images](reference/images/index.md)

-   **Analysis**

    Model fitting, statistics, time series and cosmology.

    [:octicons-arrow-right-24: Analysis](reference/analysis/index.md)

-   **Online**

    astroquery archives and SAMP.

    [:octicons-arrow-right-24: Online](reference/online/index.md)

-   **System**

    API Explorer, IERS data, caches and configuration.

    [:octicons-arrow-right-24: System](reference/system/index.md)

-   **General**

    The shared workspace.

    [:octicons-arrow-right-24: Workspace](reference/general/index.md)

</div>

## How it behaves

**Shared workspace.** A table, coordinate list, image or fitted model stored in one tool can be picked in any other. See [the workspace](concepts/workspace.md).

**Plain input.** Fields accept `3.5 km/s`, `10h30m00s` or `np.linspace(0, 1, 5) * u.m`. See [entering values](concepts/entering-values.md).

**Responsive.** Network queries and long computations run in worker threads, so the window stays usable. See [background work](concepts/background-work.md).

## Limits worth knowing

The automated tests never touch the network, so archive queries are verified against mocked services only. PyQt5 is licensed GPLv3, so a binary bundle that includes it must be GPLv3 too; the source stays MIT. See [licensing](project/licensing.md).
