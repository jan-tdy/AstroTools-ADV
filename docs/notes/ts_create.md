## What it does

Creates a `TimeSeries` or `BinnedTimeSeries` from a table, from regular sampling, from bins or from a file.

## How to use

Choose the **Mode**, set **Result name** (default `series`).

| Mode | Fill in |
|---|---|
| Table with time column | **Source table**, **Time column**, **Time format**, **Time scale** |
| Regular sampling (start + delta + n) | **Start time**, **Time delta / bin size** (`0.5 day`, `30 s`), **n samples / bins**, **Data columns** |
| Binned (bin start + size/end) | **Start time**, **Time delta / bin size**, **Bin end (binned)** or **n samples / bins**, **Data columns** |
| Read from file | **File** (or **Browse file...**), **File format** (`auto`, `kepler.fits`, `tess.fits`, `ascii.ecsv`, `ascii.csv`, `ascii.basic`), **Time column** |

**Data columns**: one `name = expression` per line; the names `n` (rows) and `t` (days since start) are available (default `flux = 1 + 0*t`). Press **Create series**.

## Reading the results

With 100 samples every `0.5 day` from 2020-01-01: `TimeSeries: 100 rows`, columns `time, flux`, `time: 2020-01-01T00:00:00.000 .. 2020-02-19T12:00:00.000`, `span: 49.5 d`. The first rows are 2020-01-01 00:00, 12:00, 2020-01-02 00:00.

## Tips and limits

- `n` samples span (n - 1) steps, so the span is 49.5 days, not 50.
- Kepler and TESS FITS files need no time column.
