## What it does

Barycentric and heliocentric radial velocity corrections and light-travel-time corrections (BJD, HJD) for a target at given observation times.

## How to use

1. Set the observer location and target(s) as in [Alt/Az & visibility](coord_visibility.md).
2. Enter **Observation times (UTC)**, one per line (`2024-01-01T00:00:00`; `now` allowed).
3. Optional **Observed RV** (`-300 km/s`) adds corrected velocities.
4. Press **Compute**; **Store table in workspace** saves it under **Workspace name** (default `velocity_corr`).

## Reading the results

Columns: `rv_corr_bary_kms`, `rv_corr_helio_kms`, `ltt_bary_s`, `ltt_helio_s`, `bjd_tdb`, `hjd_utc` and their text forms. For `10.684 41.269` from Greenwich: 2024-01-01 correction -24.25198601 km/s, light time 124.1489655 s, BJD(TDB) 2460310.502237649; 2024-07-01 correction +23.42014394 km/s, -137.9057614 s.

## Tips and limits

- Add the correction to the observed velocity to get the barycentric one; the sign convention is that of astropy's `radial_velocity_correction`.
- The correction varies by about ±30 km/s over a year, and by metres per second with the observatory position.
- Use BJD(TDB) for timing; HJD is provided for older literature.
