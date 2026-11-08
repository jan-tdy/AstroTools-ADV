## What it does

Converts between redshift and other quantities using `astropy.cosmology.units` equivalencies.

## How to use

1. Choose the **Cosmology** and the **Equivalency**: `redshift_distance`, `redshift_hubble`, `redshift_temperature`, `with_redshift`, `with_H0`, `dimensionless_redshift`.
2. For distances set **Distance kind** (`comoving`, `lookback`, `luminosity`). For `with_redshift`, **Include Hubble** and **Include Tcmb** add those equivalencies.
3. Enter the **Value** (number or array) and its **Unit** (`redshift`, `Mpc`, `K`, `Mpc/littleh`), and **Convert to**.
4. Press **Convert**.

## Reading the results

`1` redshift to Mpc with `redshift_distance` (comoving) gives `3395.63447115 Mpc`, matching the calculator. The result also names the equivalency and cosmology used.

## Tips and limits

- Converting a distance back to redshift is done numerically by astropy; very large distances may be outside its range.
- `littleh` units carry the Hubble parameter; `with_H0` converts them.
