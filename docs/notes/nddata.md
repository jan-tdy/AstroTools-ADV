## What it does

Wraps an image into an `NDData`, `NDDataRef`, `NDDataArray` or `CCDData` container with a unit, an uncertainty and a mask, and saves it as FITS.

## How to use

1. Select the **Image** (**FITS...** or **Test**).
2. Choose the **Container**. `CCDData` needs a unit and defaults to `adu`.
3. **Unit**: `adu`, `electron`, `Jy/beam`...; empty keeps the source unit.
4. **Uncertainty** class: `none`, `StdDev`, `Variance`, `InverseVariance`, `Unknown`. **Unc. value** is a number, an expression in `data` (`0.1*data`) or `poisson`.
5. **Mask**: empty, `nonfinite`, or an expression like `data > 60000`.
6. Press **Build  store** (two spaces in the button text); the object is saved under **Store as** (default `nddata`). **Describe selected image** prints the summary of any image, **Save as FITS...** writes the selected container.

## Reading the results

The **Summary** shows type, shape/dtype, unit, uncertainty class, mask, WCS, number of meta keys and pixel statistics. For `test_image` with `StdDev`: `type NDData`, `shape/dtype (128, 128) / float64`, `uncertainty StdDevUncertainty`, `min / max 87.9305 / 598.551`, `mean / std 105.534 / 32.811`.

## Tips and limits

- Uncertainties and masks propagate in [NDData arithmetic](ndarith.md).
- `poisson` takes the square root of the data; use it only for data in counts.
