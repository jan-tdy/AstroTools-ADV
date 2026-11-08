## What it does

Shows the table of leap seconds and the Earth-orientation values (UT1-UTC, polar motion) astropy uses, for a date.

## How to use

- **Leap seconds** lists every TAI-UTC step. The **Result** tab states the entry count and when the table expires (`28 entries; table expires 2027-06-28.` with the bundled data). The **Leap seconds** tab has columns `year`, `month`, `TAI-UTC [s]`, from 1972-01 (10 s) to 2017-01 (37 s).
- **Earth orientation at date** uses the **UTC date** field (default `2020-01-01 00:00:00`) and reports JD, TAI-UTC, UT1-UTC with its source and polar motion x, y in arcsec. For 2020-01-01: TAI-UTC 37.0 s, UT1-UTC -0.1771665 s [IERS-B (final)], polar x, y 0.076614, 0.282309 arcsec.
- **IERS table range** shows the date span the loaded IERS table covers.

## Tips and limits

- The source tag in brackets tells you whether a value is final data (IERS-B), a prediction (IERS-A) or an extrapolation; dates beyond the table are less reliable.
- UT1-UTC stays within ±0.9 s by definition; leap seconds are added to keep it so.
- To refresh the bundled data see [IERS & Time Data](../system/iers.md).
