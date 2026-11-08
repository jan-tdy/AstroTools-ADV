## What it does

Plots expressions of astropy Quantities and Times with proper unit and time axes (`quantity_support`, `time_support`).

## How to use

1. **x** is an expression returning a Quantity or Time (`Time('2024-01-01') + linspace(0, 30, 31) * u.day`). `u`, `np`, `Time` and `linspace` are available.
2. **y** is an expression using the name `x`.
3. For Time on the x axis choose the **Time format** (`default`, `iso`, `isot`, `jd`, `mjd`).
4. **Style**: `line`, `markers`, `line+markers`. Press **Plot**.

## Reading the results

The defaults (31 days; `y` is a square-root growth in metres) give `x: Time`, `y: Quantity [m]`, `n = 31` in **Info**. The axes show units automatically.

## Tips and limits

- Quantities with different but convertible units are drawn on the unit of the first.
- Incompatible units on one axis raise an error from matplotlib.
