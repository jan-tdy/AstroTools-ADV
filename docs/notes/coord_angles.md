## What it does

Angle arithmetic: convert and format angles, add or subtract two lists, scale, wrap into a range and validate as a latitude.

## How to use

1. Write **Angle A** one value per line: `12.5`, `10h30m`, `-5d12m3s`, `0.2 rad`. Plain numbers use **Plain numbers are** (default `deg`; also `hourangle`, `rad`, `arcmin`, `arcsec`).
2. Choose **Operation**: `Convert / format`, `A + B`, `A - B`, `A * k`, `A / k`, `Wrap at 180 (-180..180)`, `Wrap at 360 (0..360)`, `Validate as Latitude`.
3. `A + B` and `A - B` use **Angle B**, either one value or one per line of A. `A * k` and `A / k` use **Factor k**.
4. Press **Calculate**.

## Reading the results

One row per input with columns `deg`, `hourangle`, `rad`, `arcmin`, `arcsec`, `hms`, `dms`, `hms_tuple`, `signed_dms`. `10h30m` is 157.5 deg, 2.748893572 rad, `+157:30:00.000`. `-5d12m3s` is -5.200833333 deg. Wrapping `190, 350, -200` at 180 gives `-170, -10, 160`.

## Tips and limits

- `10h30m` is hours; `10d30m` is degrees. A bare `10.5` follows the **Plain numbers are** setting.
- The `*_tuple` columns can show rounding noise such as 59.99999999999744 s or `(-, 169, 59, 60.0000)`; use the `hms`/`dms` strings for display.
- `Validate as Latitude` reports an error for a value outside -90..90 deg (95 is refused).
