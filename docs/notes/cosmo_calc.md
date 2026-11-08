## What it does

Calculates distances, ages, densities and other quantities for a list of redshifts in any FLRW cosmology.

## How to use

1. Choose the **Cosmology** (see the category overview).
2. Enter the redshifts in **Redshift z**: a list (`0.1, 0.5, 1, 2, 5`) or an expression (`linspace(0, 3, 13)`). They must be greater than -1.
3. Tick the **Quantities** you want; **Select all / none** switches them all. The optional **z2 (for z1-z2)** adds columns for the interval between two redshifts.
4. Press **Compute table**; the table is stored as **Table name** (default `cosmo_table`).
5. **Store cosmology in workspace** keeps the cosmology under **Cosmology name** (default `cosmo`); **Show cosmology details** prints its parameters.

## Reading the results

For Planck18 the default rows are:

| z | H | comoving_distance | luminosity_distance | angular_diameter_distance | distmod | lookback_time | age |
|---|---|---|---|---|---|---|---|
| 0.1 | 71.059 | 432.566 | 475.822 | 393.242 | 38.387 | 1.345 | 12.442 |
| 1 | 120.631 | 3395.634 | 6791.268 | 1697.817 | 44.160 | 7.936 | 5.851 |
| 5 | 557.873 | 7946.293 | 47677.760 | 1324.382 | 48.392 | 12.616 | 1.171 |

H is in km/s/Mpc, distances in Mpc, times in Gyr, `distmod` in mag. The **Details** tab prints the cosmology and its parameters.

## Tips and limits

- Angular diameter distance peaks around z = 1.6 and then falls, as the rows show (1697.8 at z = 1, 1769.4 at z = 2).
- Results depend strongly on the cosmology. State which one you used.
