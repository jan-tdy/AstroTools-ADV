## What it does

Slices images, and computes overlaps between a small and a large array: `overlap_slices`, `extract_array`, `add_array`, `subpixel_indices`.

## How to use

| Operation | Uses | Returns |
|---|---|---|
| slice (NDSlicingMixin) | **Slice** `10:50, 20:60` | Sub-image with its uncertainty, mask and WCS sliced too |
| overlap_slices | **Small shape**, **Position**, **Mode** | The two slice pairs for overlap |
| extract_array | **Small shape**, **Position**, **Mode**, **Fill value** | Small array cut from the large one |
| add_array | **Small array (add)**, **Position** | Large image with the small one added |
| subpixel_indices | **Position** | Fractional pixel offsets |

**Position** is `y, x` of the small array's centre. **Mode** `partial` allows overlap with the edge, `trim` cuts, `strict` raises an error.

## Reading the results

`test_image` slice `10:50, 20:60` is a `(40, 40)` image with mean 100.011 and std 3.04741. `overlap_slices` with a `20, 20` array at `5, 5` returns `slices_large = (slice(0, 15), slice(0, 15))` and `slices_small = (slice(5, 20), slice(5, 20))`: the overhanging 5 pixels on each side are cut off.

## Tips and limits

- Slices follow NumPy order (rows first, y then x).
- `extract_array` pads with **Fill value** (default `nan`) in `partial` mode.
