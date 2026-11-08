## What it does

Reports a WCS's scales, rotation, distortion and validity, and slices or reorders its axes.

## How to use

1. Choose the **WCS**.
2. **Info** shows scales and frame; **Validate** runs the checks; **Local derivatives** uses **Pixel (x y)** (0-based) to give the local scale and rotation there.
3. **Apply operation** creates a new WCS: **Operation** `slice` (**Argument** `10:50, 20:60`), `sub` (`1,2` or `celestial`), `swapaxes`, `reorient_celestial_first`, `dropaxis`. It is stored as **Store as** (default `wcs_new`). **relax header** accepts non-standard keywords.

## Reading the results

For a TAN WCS with 1 arcsec/pixel: `frame ICRS`, `pixel scale 1 x 1 arcsec/pix`, `pixel area 1 arcsec^2`, `rotation 0 deg (N through E)`, `parity east left`, `physical ['pos.eq.ra', 'pos.eq.dec']`. **Header** gives the FITS keywords; **High-level API** the axis types and units.

## Tips and limits

- A slice follows NumPy order; the WCS shifts CRPIX accordingly.
- `pixel shape None` means the WCS has no stored image size.
