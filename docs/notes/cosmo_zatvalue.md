## What it does

Finds the redshift at which a cosmological quantity reaches a target value (`z_at_value`).

## How to use

1. Choose the **Cosmology** and the **Quantity**: `age`, `lookback_time`, `lookback_distance`, `comoving_distance`, `comoving_transverse_distance`, `luminosity_distance` and so on.
2. Enter the **Target value(s)** (`1000, 5000`) and their **Unit** (`Mpc`; blank for dimensionless).
3. The search range is **z min** (1e-08) to **z max** (1000.0). **Method** `Brent`, `Golden` or `Bounded`; **Bracket** (`a, b`) only applies to Brent and Golden. **z tolerance** and **Max evaluations** control the solver.
4. Press **Solve z_at_value**; the table is stored as **Table name** (default `z_solutions`).

## Reading the results

Planck18, luminosity distance 1000 Mpc gives `z = 0.1978197925`, 5000 Mpc gives `z = 0.7794249373`. Columns `func(z)` and `rel_error` show the check: 999.9999973 and 2.7e-09. The Notes tab says `Round-trip check func(z) vs target: OK.`

## Tips and limits

- Quantities that are not monotonic in z (angular diameter distance) have two solutions; the solver finds only one within the range.
- A target outside the reachable range gives a solver error; widen z max or change the target.
