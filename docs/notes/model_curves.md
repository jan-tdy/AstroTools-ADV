## What it does

Fits splines, interpolates with tabular models, and fits Chebyshev, Legendre, Hermite or ordinary polynomials to x/y data.

## How to use

1. Give **x**, **y** and optional **Weights (optional)**.
2. Choose the **Method**: `Spline: interpolate`, `Spline: smoothing`, `Spline: exact knots`, `Spline: splrep`, `Tabular1D: linear`, `Tabular1D: nearest`, `Polynomial: Polynomial1D`, `Polynomial: Chebyshev1D`, and others in the list.
3. **Degree** (spline 1 to 5, or the polynomial degree), **Smoothing s** (empty = automatic), **Interior knots** (exact-knots only, e.g. `3, 6`).
4. **Derivative order** plots that derivative of a spline in a second panel; **Curve points** sets the plot resolution.
5. Press **Fit / interpolate**; **Save model** stores it under **Save model as** (default `curve_model`).

## Reading the results

`Spline: smoothing` with `s = 0.4`, degree 3 on the scenario data: two interior knots (5.12820513, 7.69230769) and `rms residual at data points: 0.100015`. **Curve** shows the data, the fit and the derivative.

## Tips and limits

- Interpolation passes through all points; use smoothing for noisy data.
- Higher polynomial degrees oscillate near the ends; Chebyshev is better conditioned than the power basis.
- See the [model fitting guide](../../guides/model-fitting.md).
