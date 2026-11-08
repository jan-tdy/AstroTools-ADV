## What it does

Builds an observer location (`EarthLocation`) from the astropy site registry, geodetic values, geocentric values or a workspace object, and shows all its representations.

## How to use

1. Choose **Mode**: `Site name`, `Geodetic`, `Geocentric` or `Workspace`.
2. `Site name`: pick a **Site** from the list (for example `greenwich`). Geodetic: **Longitude** east positive, **Latitude**, **Height** and **Ellipsoid**. 
3. Press **Show**; **Store EarthLocation in workspace** saves it under **Workspace name** (default `site`).

## Reading the results

For `greenwich`: ellipsoid WGS84, longitude -0.00147500 deg (-0:00:05.310), latitude 51.47781100 deg (+51:28:40.120), height 46.000 m, geocentric x 3980608.902 m, y -102.475 m, z 4966861.273 m, distance from Earth centre 6365.1361 km.

## Tips and limits

- Observatory fields in other tools (Alt/Az, Sun & Moon...) offer the same Mode choices, so you need this page only to store a site for reuse.
- The site registry is downloaded by astropy on first use if it is not cached; without network only the built-in list is available.
- Longitude is east positive; Spain is negative.
