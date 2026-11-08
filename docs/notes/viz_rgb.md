## What it does

Combines three images into an RGB composite with `make_lupton_rgb` or `make_rgb`.

## How to use

1. Choose the **Red**, **Green** and **Blue** images from the workspace (same shape).
2. **Method**: `Lupton (make_lupton_rgb)` or `make_rgb`.
3. Lupton: **Lupton stretch** (`LuptonAsinhStretch` or `LuptonAsinhZscaleStretch`), **Stretch width**, **Q** (softening) and **Minimum** (black level).
4. `make_rgb`: **Interval**, **Stretch**, **Then stretch** and the stretch parameters as in [Image viewer](viz_viewer.md).
5. Press **Compose**; stored as **Store as** (default `rgb`). **Save PNG...** writes the picture.

## Reading the results

The **RGB** tab shows the composite, **Info** the settings. Scale each band to balance colour before composing.

## Tips and limits

- All three images must have the same shape; align them first.
- For Lupton, larger **Q** compresses bright regions more; start at 8 and **Stretch width** 5.
