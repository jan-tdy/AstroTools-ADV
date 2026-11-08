## What it does

Transforms sky coordinates between astropy frames (ICRS, FK5, FK4, Galactic, Supergalactic, ecliptic, and others) and writes the result in the angle format and representation you choose. Optional distance, proper motion and radial velocity are carried through the transformation.

## How to use

1. Choose **Source**: `Typed text` (the **Lines** box), `Workspace SkyCoord` or `Workspace table`.
2. Typed text: one coordinate per line as `lon lat`. Plain numbers are degrees; values with `h m s` or `:` are read as hours for longitude. Override with **Lon unit** / **Lat unit** (`auto`, `deg`, `hourangle`, `rad`).
3. Optional **Distance** (`100 pc`, default unit pc), **Parallax** (mas, used when distance is blank), **PM lon\*cos(lat)**, **PM lat** (mas/yr) and **Radial velocity** (km/s, needs a distance).
4. Set the input **Frame** (first one) and the output **Frame** (second one). Frames that depend on time or place (AltAz, GCRS...) show extra fields (obstime, observatory).
5. Pick **Representation**, **Angle format** (`decimal`, `hmsdms`, `dms`, `radians`), **Precision** and **Always show sign**. Press **Convert**.
6. **Store SkyCoord in workspace** keeps the result under **Workspace name** (default `converted`).

## Reading the results

M31 `10.684 41.269` ICRS to Galactic gives `l = 121.1737667`, `b = -21.57303963`. The **Info** tab shows the object, the number of rows, the `hmsdms` string and, for ICRS-like output, the constellation (here Andromeda).

## Tips and limits

- FK4 is B1950 with E-terms; use `FK4NoETerms` only to compare with older software. FK5 is J2000 by default.
- Cartesian output needs distances; without one you get a unit-vector result.
- Time-dependent frames need an observation time and, for AltAz, a site; see [Observatory](coord_observatory.md) and [Alt/Az & visibility](coord_visibility.md).
