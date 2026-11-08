## What it does

Adds, subtracts, multiplies and divides `NDData` images with propagation of uncertainty, masks and WCS.

## How to use

1. Select **Operand A** and the **Operation**.
2. **Operand B is** a `workspace object` (choose **B (workspace)**) or a `constant` (**B (constant)**, a number or a quantity like `2.5 adu`).
3. **Propagate uncertainty** with **Correlation** (0 to 1). **handle_mask** (`logical_or`, `logical_and`, `bitwise_or`, `first_found`, `none`), **handle_meta** and **compare_wcs** (`first_found`, `strict`, `none`) control the rest.
4. Press **Compute**; stored as **Store as** (default `nd_result`).

## Reading the results

`test_image + 2` gives an `NDDataRef` with `min / max 89.9305 / 600.551` and `mean 107.534`, exactly 2 above the input. **Plot** shows the result.

## Tips and limits

- Without an uncertainty on the inputs nothing is propagated.
- `strict` WCS comparison fails if the operands are not aligned.
- For calibration chains see [Calibration & statistics](ccd_calib.md).
