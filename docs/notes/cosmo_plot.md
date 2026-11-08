## What it does

Plots a cosmological quantity versus redshift and overlays other cosmologies.

## How to use

1. Choose the **Cosmology** and the **Quantity** (`luminosity_distance` by default; also `H`, `scale_factor`, `efunc`, `comoving_distance`, and the rest of astropy's list).
2. Set **z min** (0.01), **z max** (5.0) and **Points** (200). **Log-spaced z** needs z min > 0. **Log x axis** and **Log y axis** switch the scales.
3. In **Overlay** tick other cosmologies to draw on the same axes.
4. Press **Plot**; the curves are stored as **Table name** (default `cosmo_curves`).

## Reading the results

**Plot** shows the curves; **Data** lists `z` and one column per cosmology. For Planck18 the luminosity distance at z = 0.01 is 44.647 Mpc.

## Tips and limits

- Differences between cosmologies are largest at high z; use a log y axis to see them over the full range.
- For single values use [Cosmology: Calculator](cosmo_calc.md).
