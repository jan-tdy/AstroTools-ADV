## What it does

Moves stars to a new epoch using proper motion and radial velocity (`SkyCoord.apply_space_motion`).

## How to use

1. Enter the positions (typed, workspace SkyCoord or table) with a **Distance** (or **Parallax**), **PM lon\*cos(lat)**, **PM lat** (mas/yr) and **Radial velocity** (km/s).
2. Give the epoch of the input in **Obstime** (default `J2000`).
3. Give exactly one of **New epoch** (`J2025.0`, `2030-01-01`) or **or dt** (`10 yr`).
4. Press **Apply space motion**. The result is stored as a SkyCoord under **Workspace name** (default `moved`).

## Reading the results

Defaults are Barnard's star: `269.45 4.69`, 1.83 pc, PM -798.58 and 10328.12 mas/yr, RV -110.51 km/s. After 25 years the position is `269.4444265 4.761833927`, a shift of 259.37 arcsec, epoch after `2024-12-31 18:00:00` (J2025.0 is stored in TT).

## Tips and limits

- Errors: `Give exactly one of: new epoch, time step dt.`, `The coordinates need an epoch: set 'Obstime'...`, `Proper motion is required...`.
- The radial velocity only matters with a distance; it changes the position slightly for nearby fast stars.
- Linear motion only; no acceleration or parallax.
- See [Proper motion guide](../../guides/proper-motion.md).
