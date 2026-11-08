---
title: Time scales and sidereal time
order: 10
lede: Convert one instant between UTC, TAI, TT and TDB, then get the local sidereal time and the light-travel-time correction for an observing session.
---

## One instant in every scale

Open [Time converter](../reference/basics/time_converter.md) and enter the observation time.

1. **Time(s)**: `2024-03-10 22:00:00`.
2. **Output scale**: `tdb`. **Output format**: `jd`. **Precision**: `6`.
3. Press **Convert**.

![Time converter with the All scales tab](../assets/guides/basics-time-scales.png "One UTC instant in every time scale.")

The **Result** tab confirms `scale=tdb`. **All scales** lists the same instant in each scale: TAI is `22:00:37.000000` (UTC + 37 s, the current leap-second count) and TT is `22:01:09.184000` (TAI + 32.184 s).

!!! note
    The input scale `auto` reads an ISO string as UTC. If your times come from a data file in another scale, set **Input scale** explicitly.

## Sidereal time and barycentric correction

Open [Sidereal & light time](../reference/basics/sidereal_light_time.md).

1. **Time(s)**: three lines, `2024-03-10 22:00:00`, `2024-03-10 23:00:00`, `2024-03-11 00:00:00`.
2. **Longitude** `-4.78`, **Latitude** `37.89`, **Height** `120 m` (Córdoba; longitude is east positive).
3. **Sidereal time** on, **Kind** `mean`.
4. Tick **Light travel time**, **Source** `12.5 -45.2`, **Correction** `barycentric`.
5. Press **Compute**.

![Sidereal time and light travel time](../assets/guides/basics-sidereal.png "Local mean sidereal time and barycentric correction for three times.")

The local mean sidereal time is `08:57:08.5853` at 22:00 UTC and advances by `01:00:09.856` per clock hour, because a sidereal hour is shorter than a clock hour. The light travel time to the barycentre for this direction is `-350.44 s`, so the corrected TDB time is `21:55:18.741`, about 5 min 51 s earlier. Use the corrected JD (`2460380.413`) for timing work.

See also [Time arithmetic](../reference/basics/time_arithmetic.md) for differences and ranges and [Leap seconds & IERS](../reference/basics/time_leap_iers.md) for the table behind the +37 s.
