## What it does

Displays an image with astropy intervals, stretches and colormaps, with WCS axes, a coordinate grid and sky overlays.

## How to use

1. Select the **Image**.
2. **Normalization**: `ImageNormalize (interval + stretch)` or `simple_norm`.
3. Choose the **Interval**: `ZScale`, `MinMax`, `Percentile` (**Percentile**), `AsymmetricPercentile` (**Lower %**, **Upper %**), or `Manual` (**vmin**, **vmax**).
4. Choose the **Stretch** (`Linear`, `Sqrt`, `Squared`, `Log`, `Asinh`), optional **Then stretch**, and the parameters **a**, **Power**, **Contrast**, **Bias**, **Clip**.
5. **Colormap**, **Invert colormap**, **Colorbar**.
6. With a 2-D WCS, **WCS axes** and **Coordinate grid** switch on sky axes; **Sky points** (`150.0 2.0`) and **Sky circles** (`150 2 | 10 arcsec`) are overlaid.
7. Press **Show image**; **Save PNG...** writes the figure.

## Reading the results

The **Info** tab states the limits actually used. `test_image` with ZScale: `vmin = 87.930524`, `vmax = 120.35128`, `stretch = LinearStretch`, `WCS axes = False`. **Stretch** shows the stretch curve.

## Tips and limits

- ZScale suits star fields; the stars saturate while the background shows. Use `Percentile` 99.5 and `Asinh` for bright objects.
- Overlays need a WCS; without one they are ignored.
