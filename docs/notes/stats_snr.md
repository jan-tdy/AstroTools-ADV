## What it does

Signal-to-noise of a CCD observation as a function of exposure time.

## How to use

1. **Exposure times (s)**: numbers/expression, e.g. `linspace(1, 300, 30)`.
2. **Source (e-/s)**, **Sky (e-/s/pix)**, **Dark (e-/s/pix)**, **Read noise (e-)**, **Pixels in aperture** and **Gain (e-/ADU)**.
3. Press **Compute**.

## Reading the results

**S/N** lists `t, snr`; with the defaults (10 e-/s source, 1 e-/s/pix sky, 0.1 dark, 5 e- read noise, 20 pixels) the S/N is 0.434 at 1 s, 9.72 at 41.6 s and 19.28 at 133 s. **S/N vs time** plots it.

## Tips and limits

- S/N grows as sqrt(t) when sky or source dominate and linearly when the read noise dominates.
- Raise the pixel count for a larger aperture; sky and read noise grow with it.
