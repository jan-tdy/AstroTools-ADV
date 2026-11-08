## What it does

Convolves two astropy models with each other on a regular grid (`convolve_models`, `convolve_models_fft`).

## How to use

1. Write the **Model** and the **Kernel model** as astropy modeling expressions (`models.Gaussian1D(10, 0, 2)`, `models.Box1D(1, 0, 2)`).
2. Choose the **Mode**: `convolve_fft`, `convolve`, or `convolve_models_fft`.
3. Give the **x grid** as `xmin xmax N` (default `-10 10 201`); the kernel is sampled on the same grid. **Normalize kernel** applies to `convolve` and `convolve_fft`.
4. Press **Convolve models**. The array is stored as `convolved_model`.

## Reading the results

The default `Gaussian1D(10, 0, 1)` (amplitude 10, mean 0, sigma 1) with `Box1D(1, 0, 2)` gives `peak 8.43281 at x = 0` and `integral 25.0663`. The **Plot** tab draws the model, the kernel and the result.

## Tips and limits

- The grid must be wide enough to contain both models, or the result is cut off at the edges.
- Step size is (xmax - xmin) / (N - 1); use a step much smaller than the narrowest feature.
