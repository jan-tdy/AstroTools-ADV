## What it does

Computes differences, offsets and regularly spaced ranges of times using astropy `Time` and `TimeDelta`.

## How to use

| Operation | Uses | Returns |
|---|---|---|
| `t1 - t2` | **t1** (first line), **t2** | The difference as days, seconds and a readable duration |
| `t1 + delta` | **t1**, **delta** | Each time in t1 shifted forward |
| `t1 - delta` | **t1**, **delta** | Each time shifted back |
| `range t1 .. t2` | first line of **t1**, **t2**, **Points N** | N equally spaced times from t1 to t2 |
| `range t1 + k*delta` | **t1**, **delta**, **Points N** | t1, t1+delta, t1+2*delta, ... (N points) |

1. Enter **t1** (one time per line, ISO or `now`) and, where needed, **t2** in the same format and scale.
2. Set **Input format** and **Input scale** (`auto` reads ISO as UTC).
3. **delta** is a duration such as `36 h` or `3600 s`; a plain number means days. Default `1.5 d`.
4. Pick the **Operation**, set **Points N** for ranges, press **Compute**.
5. **Store result in workspace** keeps the result under **Store as** (default `time_result`).

## Reading the results

With the defaults (`2024-03-10 06:00:00` minus `2024-03-12 18:30:00`): `jd: -2.5208333`, `sec: -217800.0`, `quantity_str: -2d 12hr 30min`. The sign is t1 minus t2, so it is negative when t1 is earlier. The difference is computed in TAI.

`range t1 .. t2` with N = 5 gives 2024-03-10 06:00, 21:07:30, 03-11 12:15, 03-12 03:22:30 and 18:30; the **Range** tab holds them as a table with `iso`, `jd` and `mjd`.

## Tips and limits

- Offsets of a few days are exact in TAI; across a leap second a UTC offset in days is not the same as the same number of seconds.
- Ranges include both end points, so N points give N-1 intervals.
- For format and scale conversion use [Time converter](time_converter.md).
