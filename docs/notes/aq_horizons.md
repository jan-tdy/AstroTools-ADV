## What it does

Asks the [JPL Horizons](https://ssd.jpl.nasa.gov/horizons/) system for the position of a solar-system body as seen from an observer (ephemerides), its osculating orbital elements, or its state vectors. Results come from the remote service; see [the category overview](index.md) for the shared layout and error messages.

## How to use

Choose the query mode: **Ephemerides**, **Orbital elements** or **State vectors**. All three use the same fields; only **Quantities** is specific to ephemerides.

1. **Target** `*`: a name, number or designation as Horizons understands them (`Ceres`, `499`, `1P`, `2014 AA`).
2. **Target type**: leave empty to let Horizons search planets, satellites and spacecraft first and small bodies second. Choose `smallbody`, `designation`, `name`, `asteroid_name` or `comet_name` to force how the target is read; use it when a name is ambiguous.
3. **Location**: where the observation is made from. Enter an observatory code (`500` is the geocentre, `568` is Mauna Kea, `@sun` is the Sun's centre), or three numbers `lon lat elevation_km` with east-positive longitude and latitude in degrees and the elevation in kilometres, for example `-4.78 37.89 0.12`. Empty means the centre of the Earth for ephemerides and the centre of the Sun for elements and vectors.
4. **Epochs**: choose how to give the times.
    - `now`: the current time.
    - `range`: fill in **Start**, **Stop** and **Step**. Start and stop are `YYYY-MM-DD` or `YYYY-MM-DD HH:MM`; the step is a number with a unit such as `1d`, `6h` or `30m` (see the Horizons manual for the accepted units).
    - `list`: fill in **Epoch list** with Julian dates or ISO times separated by commas; ISO times are converted to Julian dates before they are sent.
5. **Quantities** (ephemerides only): Horizons quantity codes such as `1,9,20`. Empty returns all of them, which is a very wide table.
6. Press **Run query**.

## Reading the results

One row per epoch. **Ephemerides** gives columns such as the target name, epoch, right ascension and declination, magnitudes, distances and elongations; **Orbital elements** gives eccentricity, semi-major axis, inclination and the rest of the elements; **State vectors** gives position and velocity components. Column names and units are those astroquery assigns to the Horizons output.

## Tips and limits

- Time scales are decided by Horizons: ephemeris epochs are UTC, element and vector epochs are TDB. Compare with another tool only after allowing for that.
- The default range is `2026-01-01` to `2026-01-10` in steps of `1d`. A fine step over a long range returns a very large table; Horizons refuses requests above its own limits and the message is shown in the **Info** tab.
- A target name that matches several bodies makes Horizons return a list of matches instead of data; set **Target type** or use the numeric id.
- **Location** with an unknown observatory code produces an error from Horizons. The codes are listed on the Minor Planet Center's site; the [Minor Planet Center](aq_mpc.md) page has an **Observatory codes** query for them.
