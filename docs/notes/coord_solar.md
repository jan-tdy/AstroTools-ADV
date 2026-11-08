## What it does

Positions of the Sun, Moon and planets at given times, geocentric or topocentric, plus their barycentric positions and velocities.

## How to use

1. Enter **Times (UTC)**, one per line (`now` allowed).
2. Choose the **Ephemeris**: `builtin` works offline; `jpl` and `de*` need the `jplephem` package and a downloaded kernel.
3. For topocentric positions plus altitude/azimuth tick **Use observer location** and set the site.
4. Press **Compute**; **Store tables in workspace** saves them (**Workspace name**, default `bodies`).

## Reading the results

- **Apparent positions**: `body, ra_deg, dec_deg, ra_hms, dec_dms, distance_AU, ecl_lon_deg, ecl_lat_deg, elongation_deg`. On 2024-03-10 22:00 UTC the Sun is at RA 351.256592 deg (23:25:01.58), Dec -3.770422 deg, 0.9933975 AU; Jupiter at RA 40.589 deg, Dec +14.827 deg, 5.5449 AU, 52.28 deg from the Sun.
- **Barycentric pos / vel**: `x_AU, y_AU, z_AU, vx_kms, vy_kms, vz_kms` for sun, planets, earth, moon and the Earth-Moon barycentre.

## Tips and limits

- The Moon distance is given in AU (0.002388 AU is about 357,000 km).
- Positions are astrometric, without aberration or refraction. Use [Sun, Moon & twilight](coord_sunmoon.md) for rise/set.
