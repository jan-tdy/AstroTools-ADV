---
title: Background work and offline use
section: Concepts
order: 30
lede: What runs off the main thread, what needs the network, and what happens without one.
---

## Threads

Computations that can take noticeable time, and every network query, run in worker threads. While one runs the status bar shows `Working...` and the cursor changes. Results are drawn back on the main thread, so the window stays responsive and plots are never touched from a worker.

On the astroquery pages, an answer that arrives after you started a newer query, or after the page was closed, is discarded instead of being drawn over the newer result.

## Network use

Only a few things reach the network, and only when you press their button:

- **Online** pages (astroquery): SIMBAD, VizieR, Gaia, MAST and the rest.
- **Name resolution**: typing an object name such as `M31` in a coordinate field.
- **Data downloads** by astropy: IERS Earth-orientation updates, remote files, the download cache.

The astroquery pages have an **Offline mode** switch. With it on, queries stop with a message instead of attempting a connection.

## Earth-orientation data (IERS)

Time scales that involve UT1, and coordinates that depend on the Earth's rotation, need Earth-orientation data. astropy ships a bundled table, and AstroTools-ADV turns off automatic downloads while computing so that a missing network cannot stall a calculation. Dates beyond the bundled table are computed at reduced accuracy instead of raising an error. The [IERS & Leap Seconds page](../reference/basics/time_leap_iers.md) shows the table's range, and the [System tools](../reference/system/index.md) let you change the settings or refresh the data deliberately.

## When something is slow

A first call into a large astropy subpackage can take a second or two while it imports. Image convolution with `convolve_fft` on large arrays, Lomb-Scargle with the bootstrap false-alarm method, and 2-D model fitting are the genuinely heavy operations; all of them run in the background.
