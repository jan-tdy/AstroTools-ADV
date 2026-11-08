## What it does

Applies bias, dark and flat calibration to a raw frame and computes image statistics.

## How to use

1. Select the raw **Image**.
2. Tick **Subtract bias** and choose the **Bias frame**; tick **Subtract dark**, choose the **Dark frame** and set **Dark scale** (exposure of raw / exposure of dark); tick **Divide by flat** and choose the **Flat frame**.
3. Press **Calibrate**; stored as **Store as** (default `calibrated`). The order is bias, then dark, then flat.
4. **Statistics** analyses the selected image. **Sigma-clipped stats** adds the 3-sigma clipped mean, median and standard deviation.

## Reading the results

`test_image` statistics: 16384 finite pixels, `min / max 87.9305 / 598.551`, `mean / std 105.534 / 32.811`, `median 100.348`, `MAD std 3.28275`, percentiles `1%=93.0911 25%=98.196 75%=102.633 99%=281.917`. The 3-sigma clipped values (`mean 100.146`, `median 100.11`, `std 3.01053`) describe the background, because the stars are clipped away.

## Tips and limits

- Use a master bias, dark and flat; the flat should be normalised to mean 1 or the signal scale changes.
- The plain mean and std are pulled up by the bright stars; trust the clipped or MAD values for noise.
