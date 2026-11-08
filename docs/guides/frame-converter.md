---
title: Converting between coordinate frames
order: 20
lede: Transform coordinates between ICRS, Galactic, FK4 B1950 and a horizontal AltAz frame for a specific place and time.
---

All three examples use [Frame converter](../reference/coordinates/coord_convert.md): the first **Frame** is the input frame, the second the output frame.

## ICRS to Galactic

1. **Lines**: `10.684 41.269` (M31, degrees).
2. First **Frame** `ICRS`, second **Frame** `Galactic`. Press **Convert**.

![Frame converter after converting M31 to Galactic coordinates](../assets/guides/frame-converter.png "M31 from ICRS to Galactic.")

The result is `l = 121.1737667`, `b = -21.57303963`. The **Info** tab adds the constellation (Andromeda).

## The Crab Nebula in FK4 B1950

Catalogs from before 1984 use B1950 coordinates.

1. **Lines**: `83.633 22.0145`.
2. Output **Frame** `FK4`, **Equinox** `B1950`.
3. **Angle format** `hmsdms`, **Precision** `2`. Press **Convert**.

![Crab Nebula in FK4 B1950](../assets/guides/coords-crab-b1950.png "ICRS to FK4 B1950 in sexagesimal form.")

The Crab comes out as `05:31:31.38 +21:58:54.51`. **Info** reads `FK4 Coordinate (equinox=B1950.000, obstime=B1950.000)`, confirming which frame was produced.

## Altitude and azimuth from Córdoba

Horizontal coordinates depend on time and place.

1. **Lines**: `83.633 22.0145`.
2. Output **Frame** `AltAz`, **Obstime** `2026-10-29 21:00` (UTC).
3. **Mode** `Geodetic`, **Longitude [deg]** `-4.78`, **Latitude [deg]** `37.89`, **Height** `120 m`. Press **Convert**.

![Crab Nebula in AltAz](../assets/guides/coords-crab-altaz.png "The Crab Nebula seen from Córdoba on 29 October 2026 at 21:00 UTC.")

The Crab is at `az = 69.126` deg and `alt = 9.136` deg, low in the north-east, rising. The default pressure is 0 hPa, so no refraction is applied; for refraction use the [visibility page](../reference/coordinates/coord_visibility.md) with a pressure.
