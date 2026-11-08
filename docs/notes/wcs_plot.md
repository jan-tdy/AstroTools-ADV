## What it does

Draws an image or an empty frame with WCS sky axes, a coordinate grid, an overlay in a second frame, and marker overlays.

## How to use

1. Choose the **WCS** and optionally an **Image** (**FITS...** or **Test**). With **Use image data** off, a blank frame of **Frame size (nx ny)** is used.
2. **Coordinate grid**; **Overlay frame** (`galactic`, `fk5`, `icrs`, `fk4`) adds a second grid; **Colormap**.
3. **Sky points**, one coordinate per line, and **Sky circles** (`150 2 | 10 arcsec`).
4. Press **Plot**; **Save PNG...** writes it.

## Reading the results

The **WCS plot** tab shows RA/Dec axes with ticks in sexagesimal units, the grid and overlays.

## Tips and limits

- Build a WCS with [WCS builder](wcs_builder.md) first.
- Overlay grids in other frames show how the sky is rotated, for instance Galactic against equatorial.
