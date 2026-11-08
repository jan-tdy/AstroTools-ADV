## What it does

Computes local sidereal time for a site and the light travel time correction (barycentric or heliocentric) toward a source, for one or many times.

## How to use

1. Enter **Time(s)**, one per line, and set **Input format** / **Input scale** (`auto` reads ISO as UTC).
2. For local sidereal time fill **Longitude** (east positive) and **Latitude**; **Height** defaults to `0 m`. Tick **Sidereal time**, choose **Kind** (`mean` or `apparent`) and the precession-nutation **Model** (`default` is astropy's).
3. For light travel time tick **Light travel time**, give the **Source** as `RA Dec` (degrees or hms/dms) or a name (name lookup needs network), and choose **Correction**: `barycentric` or `heliocentric`. **Ephemeris** offers only `builtin`.
4. Press **Compute**. **Store result in workspace** saves the corrected times under **Store as** (default `time_corrected`).

## Reading the results

Example: `2024-03-10 22:00:00` UTC at longitude -5.9, latitude 37.9, mean sidereal time = `08:52:39.7853` (8.87771814514204 h). With light travel time on, source `12.5 -45.2`, barycentric: LTT = -350.44 s, corrected TDB time `2024-03-10 21:55:18.741`, corrected JD 2460380.4134. A negative LTT means light from that direction reaches the barycentre earlier than the observer.

The **Table** tab has the same rows as CSV.

## Tips and limits

- With neither longitude nor latitude the sidereal time is for Greenwich (the result header says so). Giving only one of them is an error: `Give both longitude and latitude (or leave both empty).`
- The correction depends on the observer location when one is given; leave it empty for a geocentric correction.
- Use barycentric (TDB) times for timing work such as pulsars or eclipse timing; heliocentric is the older convention.
