## What it does

Fits astropy models to x/y data with any astropy fitter, optional uncertainties, constraints and sigma-clipping of outliers.

## How to use

1. Give **x**, **y** and optionally **y uncertainty (sigma)** and **Extra weights**, each as numbers/expression or from a workspace table.
2. Write the **Initial model**, e.g. `Gaussian1D(2, 0, 1) + Const1D(0.4)`, or use a workspace model by name.
3. Choose the **Fitter** (`LinearLSQFitter`, `LevMarLSQFitter`, `TRFLSQFitter`, `DogBoxLSQFitter`, `SLSQPLSQFitter`, `SimplexLSQFitter`), **Max iterations** and **Tolerance (acc)**.
4. **Constraints**, one line each: `mean: fixed`, `stddev: 0.1..5`, `amplitude: free`.
5. **Sigma-clip outliers** with **Outlier iterations** and **Clip sigma** (default 3) uses `FittingWithOutlierRemoval`.
6. **Units-aware** passes Quantity data. **Plot initial model** draws the starting guess.
7. Press **Fit**. **Save fitted model** (name **Save fitted model as**) and **Save residual table** keep the results.

## Reading the results

A Gaussian plus constant fitted to 101 points: `amplitude_0 3.006601 +/- 0.0289`, `mean_0 0.690044 +/- 0.0123`, `stddev_0 1.212047 +/- 0.01546`, `amplitude_1 0.48371 +/- 0.01649`; `free parameters 4`, `dof 97`, `rms 0.076065`, `chi2 58.4379`, `reduced chi2 0.602453`, `AIC (lsq) -511.968`. The covariance matrix follows.

With **Sigma-clip outliers** on, the header gains `outliers rejected: 4` and the same fit moves to `amplitude_0 3.012859`, `mean_0 0.688865`, `stddev_0 1.211435` on 97 points. The **Fit** tab plots data, model and residuals.

## Tips and limits

- Start parameters matter for nonlinear fitters; a poor guess can end in the wrong minimum.
- Parameter uncertainties are not available for `SLSQP` and `Simplex`.
- The reduced chi2 is only meaningful when you supply real sigma values; without them the fit is unweighted.
