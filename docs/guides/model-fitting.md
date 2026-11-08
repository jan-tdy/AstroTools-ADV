---
title: Fitting models to data
order: 30
lede: Build a model, fit it to a noisy line profile, reject outliers, fit a 2-D star and smooth a curve with a spline.
---

## Build the model

Open [Model Builder](../reference/analysis/model_builder.md). In **Model expression** type

```text
Gaussian1D(1, 0, 1) + Gaussian1D(0.5, 2.5, 0.4) + Const1D(0.1)
```

press **Build / describe**, then **Evaluate and plot**.

![Model Builder with a compound model](../assets/guides/analysis-model-builder.png "A compound model evaluated on a grid.")

The **Parameters** tab lists seven parameters (`amplitude_0`, `mean_0`, `stddev_0`, `amplitude_1`, ... `amplitude_2`); the number is the position of the component. The model is `CompoundModel`, `fittable=True`, `linear=False` and has no inverse. Press **Save model to workspace** to use it by name in a fit.

## Fit a 1-D line

The data are 101 points of a Gaussian line (amplitude 3, centre 0.7, sigma 1.2) on a 0.5 continuum with noise sigma 0.1. Open [Model Fitting (1-D)](../reference/analysis/model_fit1d.md).

1. **x**: `np.linspace(-5, 5, 101)`; **y**: the data expression; **y uncertainty (sigma)**: `np.full(101, 0.1)`.
2. **Initial model**: `Gaussian1D(2, 0, 1) + Const1D(0.4)`; **Fitter** `TRFLSQFitter`.
3. Press **Fit**.

![Fit result](../assets/guides/analysis-model-fit-text.png "Fit result with parameter uncertainties and fit statistics.")

The fit recovers `amplitude_0 = 3.0066 +/- 0.0289`, `mean_0 = 0.6900 +/- 0.0123`, `stddev_0 = 1.2120 +/- 0.0155` and the continuum `0.4837 +/- 0.0165`, on 101 points with 97 degrees of freedom. `reduced chi2 = 0.602` (below 1 because the actual scatter of this sample, `rms 0.076`, is smaller than the stated sigma of 0.1).

![Data, initial model, fitted model and residuals](../assets/guides/analysis-model-fit-plot.png "The Fit tab: data with error bars, the initial and fitted models and the residuals.")

The **Fit** tab shows data with error bars, the starting model and the fitted one, with residuals underneath. Residuals without structure are the sign of a good fit.

## Reject outliers

Add four spikes of +2 (cosmic rays) to the data, tick **Sigma-clip outliers** (3 iterations, clip sigma 3) and press **Fit** again.

![Sigma-clipped fit](../assets/guides/analysis-model-fit-outliers.png "Spikes are marked with red crosses and excluded.")

The header reads `points used: 97 ... outliers rejected: 4`, and the parameters return to `amplitude_0 = 3.0129`, `mean_0 = 0.6889`, `stddev_0 = 1.2114`. Without clipping, the spikes would pull the amplitude and width upwards.

## Fit a star in an image

Open [Image Fitting (2-D)](../reference/analysis/model_fit2d.md), choose the image, press **Estimate Gaussian2D + background** or type `Gaussian2D(40, 30, 25, 3, 3, theta=0.3) + Const2D(8)` and press **Fit**.

![2-D fit](../assets/guides/analysis-model-fit2d.png "Image, model and residual of a 2-D Gaussian fit.")

On the synthetic star the fit finds a centre at (31.293, 24.588), widths 4.031 and 2.480 pixels, `theta = 0.399` rad, amplitude 50.06 on a background of 10.00; the residual image is flat, with `rms 1.004` for unit noise.

## Smooth a curve instead

If you only want a smooth line and not a physical model, open [Splines & Polynomials](../reference/analysis/model_curves.md): **Method** `Spline: smoothing`, **Smoothing s** `0.4`, **Derivative order** `1`.

![Smoothing spline with derivative](../assets/guides/analysis-model-curves.png "A cubic smoothing spline with its first derivative.")

The spline has two interior knots (5.128 and 7.692) and an `rms residual` of 0.100 at the data points, the noise level that was added.
