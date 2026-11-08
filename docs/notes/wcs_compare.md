## What it does

Compares two WCS objects and, optionally, how their pixel grids relate.

## How to use

1. Choose **WCS A** and **WCS B**.
2. Optional **Image A size (nx ny)** (empty uses A's `pixel_shape`), **Grid points per side** (default 21), **Tolerance** for `WCS.compare`.
3. Press **Compare**.

## Reading the results

Output lists `core structures equal (WCS.compare)`, both `ctype` lists, pixel scale and rotation. Two TAN WCS with the same scale but a reference position 0.01 deg apart show `False`, `pixel scale 1 / 1 (ratio 1)` and `rotation 0 / 0`. Without an image size the output ends with `(give an image shape to compare pixel grids)`; give one to compare the pixel grids.

## Tips and limits

- `False` only means the structure differs; compare the printed values to see how.
- The pixel-grid comparison samples **Grid points per side** points; it is not an exact check.
