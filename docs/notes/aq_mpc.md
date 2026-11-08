## What it does

Queries the [Minor Planet Center](https://minorplanetcenter.net/) for orbit database entries, ephemerides and observatory codes. Results come from the remote service; see [the category overview](index.md) for the shared layout, offline mode and error messages.

## How to use

| Query mode | Fill in | Returns |
|---|---|---|
| Query orbit database | **Type** (`asteroid` or `comet`); **Name**, **Number** or **Designation**; **Limit** (default 10) | Orbital elements of the matches |
| Ephemeris | **Target** `*`, **Observatory code** `*` (default `500`, geocentre), **Start (UTC)** (`YYYY-MM-DD HH:MM`, empty = now), **Step** (`1d`), **Steps** (10) | Positions and predicted brightness at each step |
| Observatory codes | nothing | The list of MPC observatory codes |

1. Choose the query mode.
2. Fill its fields. For an asteroid give one of name (`Eros`), number (`433`; `0` means unset) or designation (`2014+AA`, `+` for a space).
3. Press **Run query**; keep the table with **Store table in workspace**.

## Reading the results

The orbit database returns one row per object with its orbital elements and identifiers; the ephemeris has one row per step. **Info** shows the row and column counts.

## Tips and limits

- **Limit** applies to the orbit database only (maximum 100000).
- Observatory code `500` is the geocentre; use your site's code for topocentric positions.
- **Timeout (s)** applies to this page.
