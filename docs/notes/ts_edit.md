## What it does

Inspects a time series and adds or removes columns, slices by time, sorts, plots and saves it.

## How to use

1. Choose the **Series**, **Signal column** and **Error column**. **Show** prints the structure.
2. **Add column**: **New column** name and **Expression** (column names, `n`, `t` in days; e.g. `flux / np.nanmedian(flux)`).
3. **Remove columns**: comma-separated names.
4. **Slice by time**: **Keep from** / **Keep until** (ISO; blank = open).
5. **Sort by time**, **Plot**, **Save as file...**.
6. **Result name**: blank replaces the selected series.

## Reading the results

**Info** gives the number of rows, columns with units, time range, scale and span. For the default synthetic series: `1000 rows`, `columns ['time', 'flux', 'flux_err']`. **Table** shows the data and **Plot** the signal with error bars.

## Tips and limits

- Slice before folding to remove bad stretches.
- Use a new **Result name** if you want to keep the original.
