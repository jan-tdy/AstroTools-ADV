## What it does

Draws a histogram of image or array values with adaptive bin rules (`astropy.visualization.hist`).

## How to use

1. Select the **Data** image (**FITS...** or **Test**).
2. **Bins**: `knuth`, `freedman`, `scott`, `blocks` (Bayesian blocks), `auto`, or an integer.
3. **Lower %** / **Upper %** clip the range (0 to 100), **Log y**, **Density**.
4. Press **Plot histogram**.

## Reading the results

`test_image` with `knuth`: `16384 values, 255 bins`, `range 87.9305 .. 598.551`. The sharp peak near 100 is the background; the long tail is the stars. Use **Upper %** 99 to zoom the peak.

## Tips and limits

- `blocks` is adaptive and shows structure, but its bins are unequal.
- NaN pixels are ignored.
