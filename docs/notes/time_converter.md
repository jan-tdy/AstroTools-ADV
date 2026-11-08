## What it does

Reads one or more times in any astropy format and scale and writes them out in another format and scale. It also shows every format and every scale at once, and can produce a custom `strftime` string.

## How to use

1. Type the times in **Time(s)**, one per line. Accepted: ISO strings (`2000-01-01 12:00:00`), the words `now` and `J2000`, or plain numbers when the input format is numeric (`jd`).
2. Leave **Input format** and **Input scale** at `auto` to let astropy decide (ISO strings are read as UTC), or set them explicitly. A bare number needs an explicit format such as `jd`.
3. Choose **Output scale** (default `same as input`) and **Output format** (default `iso`). **Precision** is the number of sub-second digits in string formats.
4. Optional: **strftime**, for example `%Y/%m/%d %H:%M:%S`, adds a formatted line to the result.
5. Press **Convert**. **Store result in workspace** keeps the last result as a `Time` object under **Store as** (default `time`).

The optional **Longitude** (east positive, `-5.9` or `5d54m w`), **Latitude** and **Height** (plain numbers are metres) define an observer location; give both longitude and latitude or neither. The input scale list also contains `tcg`, `ut1` and `local`.

## Reading the results

- **Result** repeats the interpretation (`Input: 1 time(s), format=iso, scale=utc`), then the output in your chosen format.
- **All formats** lists the same instant in every astropy format. For `2000-01-01 12:00:00` UTC: `jd` 2451545.0, `mjd` 51544.5, `unix` 946728000.0, `gps` 630763213.0, `yday` `2000:001:12:00:00.000`, `jyear` 2000.0.
- **All scales** lists the instant in `utc`, `tai`, `tt`, `tdb`, `tcb`, `tcg` and `ut1`. For the example: TAI is 12:00:32, TT 12:01:04.184, TDB 12:01:04.184, UT1 12:00:00.355.

## Tips and limits

- TAI-UTC is 32 s in 2000 and 37 s since 2017; [Leap seconds & IERS](time_leap_iers.md) shows the table.
- UT1 comes from the bundled IERS table, so far-future dates are extrapolated and less certain.
- To compute differences or time ranges use [Time arithmetic](time_arithmetic.md).
