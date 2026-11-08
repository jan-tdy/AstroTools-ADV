## Choosing an image

Most pages in this category start with an **Image** drop-down listing the images in the [workspace](../../concepts/workspace.md) (arrays, quantities and `NDData` / `CCDData` objects). Next to it:

- **FITS...** opens a file dialog and loads a FITS image into the workspace under the file name; the new image is selected.
- **Test** creates `test_image`, a synthetic 128 x 128 frame: background 100, Gaussian noise (sigma 3) and ten Gaussian stars, always the same. Use it to try any page without data; the numbers in these notes come from it unless stated otherwise.

Results are stored back in the workspace under the **Store as** name. An existing name is replaced, except that some pages append `_2`, `_3`... to avoid overwriting.
