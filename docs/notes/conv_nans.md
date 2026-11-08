## What it does

Replaces NaN pixels by values interpolated with a convolution kernel (`interpolate_replace_nans`).

## How to use

1. Select the **Image** that contains NaN (or press **Test** and set **Inject NaN fraction**, a testing aid that blanks that fraction of pixels first).
2. Choose the **Kernel** (`Gaussian (quick)` or a workspace kernel) and **Convolution** (`convolve` or `convolve_fft`).
3. Press **Interpolate NaNs**; the result is stored as **Store as** (default `nan_filled`).

## Reading the results

With 5% injected: `NaN before: 832`, `NaN after : 0`. The note `(NaNs wider than the kernel cannot be filled in one pass)` means holes larger than the kernel remain; repeat with a wider kernel. **Before / after** compares the images.

## Tips and limits

- Interpolation smooths: filled pixels are weighted averages of their neighbours, so they are not valid for photometry.
- Make the kernel at least as wide as the largest hole.
