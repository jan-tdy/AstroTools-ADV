## What it does

Fits a WCS to matched pixel and sky positions (`fit_wcs_from_points`), optionally with SIP distortion.

## How to use

1. Enter **Points**, one per line, `x y ra dec` (0-based pixels; sky in degrees or sexagesimal), or use **Use workspace table** with **Table** and **Columns** (`x, y, ra, dec`).
2. Choose the **Projection** (`TAN` default, `AZP`, `SZP`, `STG`, `ARC`...) and **SIP degree** (0 = no distortion).
3. **Projection point**: `center` or `ra dec`.
4. Press **Fit WCS**; stored as **Store as** (default `fitted_wcs`).

## Reading the results

**Residuals** lists `x, y, dx_pix, dy_pix, sep_arcsec` per point; **Result** shows `residual rms` and the new WCS. For four test points 10 pixels apart (0.0028 deg) the fit gave `rms 4.861e-06 arcsec`.

## Tips and limits

- Too few points give `Need at least N points, got n.`; the required number grows with the SIP degree.
- Large residuals point to a wrong match, not a bad fit; remove that row and refit.
- `SIN`, `ZPN` and conic projections cannot be fitted.
