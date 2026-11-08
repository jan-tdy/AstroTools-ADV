## What it does

Converts lists of points between pixel and world coordinates.

## How to use

1. Choose the **WCS** and **Direction** (`pixel -> world` or `world -> pixel`).
2. **Method**: `all_*2* (with distortion)`, `wcs_*2* (core only)` or `high-level (SkyCoord / SpectralCoord)`.
3. **Origin**: `0` for NumPy pixels, `1` for the FITS convention.
4. Enter **Points**, one per line (one number per WCS axis), or tick **Use workspace table** and give the **Table** and **Columns** (`x, y`).
5. For `world -> pixel` with distortion set **Tolerance** (pixels) and **Max iterations**.
6. Press **Transform**; stored as **Store as** (default `wcs_points`).

## Reading the results

With a TAN WCS at (150, 2), reference pixel 50.5 and 1 arcsec/pixel: pixel `50 50` gives `ra 149.999861`, `dec 2.000138889`; `10 20` gives `150.0109789`, `1.991805519`. **Info** reports the number of points and NaN results.

## Tips and limits

- With origin 0, pixel 50 is the 51st pixel; the half-pixel offset from 50.5 explains the small shift from the reference.
- Points outside the projection's valid area return NaN.
