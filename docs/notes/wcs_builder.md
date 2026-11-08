## What it does

Creates a WCS from scratch, from a celestial frame, from header text, from a FITS file or from a workspace image.

## How to use

Choose the **Source**:

| Source | Fill in |
|---|---|
| scratch | **Projection** (`TAN`, `SIN`, `STG`, `AZP`...), **Frame**, **CRVAL (lon lat)**, **CRPIX (x y)** (FITS 1-based), **Pixel scale (arcsec)**, **Rotation (deg)**, **East left**, **Image size (nx ny)**, **PV parameters** |
| celestial frame | **Frame name** (`icrs`, `fk5`, `galactic`...) |
| header text | **Header text**, one card per line, **relax** |
| FITS file | **FITS path**, **HDU**, **relax**, **Alt key** |
| workspace image | **Workspace image** with a WCS |

Press **Build WCS**; stored under **Store as** (default `wcs`).

## Reading the results

Defaults: `CTYPE ['RA---TAN', 'DEC--TAN']`, `CRVAL [150.0, 2.0]`, `CRPIX [50.5, 50.5]`, `pixel scale 1 x 1 arcsec/pix`, `rotation 0 deg (N through E)`, `parity east left`, `distortion SIP=False`. **Header** has the FITS header form.

## Tips and limits

- `CRPIX` uses FITS 1-based pixels; a 100 x 100 image centred on pixel 50.5 has its reference at the exact centre.
- The default pixel scale is 1 arcsec.
- Follow with [WCS transform](wcs_transform.md) or [WCS plot](wcs_plot.md).
