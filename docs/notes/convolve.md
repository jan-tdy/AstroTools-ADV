## What it does

Convolves an image with a kernel using astropy's direct `convolve` or FFT-based `convolve_fft`, with full control of boundaries and NaN handling.

## How to use

1. Select the **Image** (or press **Test**).
2. **Kernel**: `Gaussian (quick)` or `workspace kernel` (for kernels from [Convolution kernels](conv_kernels.md)).
3. Choose **Method** (`convolve` or `convolve_fft`) and **Boundary** (`fill` with **Fill value**, `wrap`, `extend`, `None`).
4. **NaN treatment** `interpolate` replaces NaN pixels using the kernel, `fill` uses the fill value. **Preserve NaN** puts NaN back where the input had them. **Use NDData mask** honours the image mask. **Normalize kernel** divides by the kernel sum.
5. `convolve_fft` only: **fft_pad**, **psf_pad**, **allow_huge** (arrays over 1 GB), **crop**.
6. Press **Convolve**. The result is stored as **Store as** (default `convolved`).

## Reading the results

For `test_image` and the default Gaussian: `shape (128, 128), NaN count 0`, `kernel shape (17, 17), kernel sum 1`, `flux before 1729072.8 after 1688424.6`. The loss of 2.4% is flux that the `fill` boundary pushes out past the edges. **Before / after** shows both images.

## Tips and limits

- With `wrap` or `extend` the total flux is preserved.
- `convolve_fft` is faster for large kernels; for small kernels the direct method is fine.
- Unnormalised kernels change the flux scale.
