## What it does

Shows the Earth-orientation (IERS) tables astropy uses for UT1 and polar motion, looks up values for a date, lists leap seconds and controls the update configuration.

## How to use

- **Show table ranges** lists the bundled tables and the current configuration.
- **Look up UT1-UTC / polar motion**: choose the **Lookup table** (`IERS-B (bundled)`, `IERS-A (bundled)`, `Active table`), type the **UTC time** (ISO, `now`) and press the button. `Active table` may download data when **auto_download** is on.
- **Show leap seconds** lists them (same list as [Leap seconds & IERS](../basics/time_leap_iers.md)).
- **Apply configuration** sets **auto_download**, **auto_max_age [days]** (`none` disables the age check), **iers_degraded_accuracy** (`error`, `warn`, `ignore`) and **remote_timeout [s]** for this session; **Reset configuration** restores defaults.
- **Use selected Earth orientation table** makes the chosen **Earth orientation table** (`IERS-B (bundled)` or `IERS-A (bundled)`) the session-wide table; **Restore default Earth orientation table** undoes it.
- **Update IERS-A from network ...** downloads the current table.

## Reading the results

The bundled IERS-B table has 23648 rows, MJD 37665.0 to 61312.0 (1962-01-01 to 2026-09-29); the bundled IERS-A has 20024 rows to MJD 61707.0 (2027-10-29). A lookup for 2020-06-01 00:00 UTC gives `UT1-UTC = -0.254647 s`, `polar motion x = 0.114178 arcsec, y = 0.441625 arcsec`, `status code: 0 (IERS-B final)`. Codes: 1 = IERS-A observed, 2 = IERS-A prediction, -1 / -2 = before / after the table.

## Tips and limits

- Dates after the table end are not covered; with `iers_degraded_accuracy = 'error'` a time past the end of the table raises an error instead of silently using a worse value.
- The update and the `Active table` lookup need network access.
