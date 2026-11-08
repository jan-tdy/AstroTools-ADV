## What it does

Altitude, azimuth and airmass of targets over a time window from an observer location, with rise/transit/set, a sky chart and Moon information.

## How to use

1. Set the observer (**Mode**, **Longitude**, **Latitude**, **Height**) as in [Observatory](coord_observatory.md).
2. Enter the targets in **Lines**, one per line (`10.684 41.269`), with **Frame**.
3. Set **Start (UTC)** (`now` or ISO), **Duration [h]** (24), **Step [min]** (10) and **Display UTC offset [h]** (shifts shown times only; 2 for CEST).
4. **Horizon altitude [deg]** defines rise and set. **Pressure [hPa]** 0 disables refraction; with refraction on, set temperature, humidity and wavelength.
5. Press **Compute**; **Store tables in workspace** saves the tables.

## Reading the results

- **Alt/Az track**: `target, time, alt_deg, az_deg, airmass`. M31 from lat 51.48, 2024-03-10 18:00 UTC: alt 43.88 deg, az 285.37 deg, airmass 1.443.
- **Rise / transit / set**: times, transit altitude, `status` and Moon separation. A target that stays above the horizon in the window shows `always above horizon`, one that stays below it `always below horizon`; the missing times show `--`.
- **Altitude**, **Airmass**, **Sky chart**: plots. **Moon**: phase, illumination and elongation at the start.

## Tips and limits

- Airmass is only meaningful above the horizon; below it values are blank or NaN.
- Altitudes include refraction only when the pressure is non-zero.
- Window times are UTC; the offset changes only labels.
- See [Observing night guide](../../guides/observing-night.md).
