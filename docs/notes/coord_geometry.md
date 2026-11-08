## What it does

Geometry on the sphere between two coordinate lists A and B: separation, position angle, offsets, great-circle points, and offsets in a sky-offset frame.

## How to use

1. Enter A in the first **Lines** box and B in the second (or load them through **Source**). Set **Lon unit**, **Lat unit**, **Frame**, and optional distance and proper-motion fields.
2. Choose the **Operation**:

| Operation | Uses | Returns |
|---|---|---|
| Separation + position angle (A to B) | A, B | Separation and PA |
| 3D separation | A, B with distances | Distance between points |
| Position angle (A to B) | A, B | PA only |
| Offset A by position angle + separation | **Position angle**, **Separation** | New positions |
| Spherical offsets A to B / A by (dlon, dlat) | **dlon**, **dlat** | Offsets or positions |
| B in sky-offset frame centred on A | A, B | B relative to A |
| Great circle A to B | **Points** | Points along the arc |

3. Press **Compute**; **Store result coordinates** keeps positions under **Workspace name**.

## Reading the results

A = `0 0`, B = `0 90` gives `sep_deg 90`, `sep_arcmin 5400`, `sep_arcsec 324000` and `pa_deg 0` (north). Reversing A and B gives PA 180. The great circle with the default 11 points returns `lon_deg, lat_deg, fraction, from_A_deg`, here lat 0, 9, 18 ... 90 at fractions 0.0 to 1.0.

## Tips and limits

- Position angle is measured east of north, 0 to 360 deg.
- A single B row is compared with every A row; otherwise rows pair one to one and the counts must match.
- To match whole catalogs use [Catalog matching](coord_match.md).
