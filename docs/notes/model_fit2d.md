## What it does

Fits 2-D models (for example a Gaussian star profile with a background) to a workspace image or a region of it.

## How to use

1. Choose the **Image**, optionally a **Region x0:x1, y0:y1** (pixel slice such as `10:60, 20:80`; empty = whole image).
2. Press **Estimate Gaussian2D + background** to fill the **Initial model** automatically, or write it, e.g. `Gaussian2D(40, 30, 25, 3, 3, theta=0.3) + Const2D(8)`.
3. Choose the **Fitter**, **Max iterations**, **Tolerance (acc)**, **Constraints**, **Sigma-clip outliers** (as in [1-D fitting](model_fit1d.md)).
4. Press **Fit**; **Save fitted model** stores it under **Save fitted model as** (default `fitted_model_2d`).

## Reading the results

For a synthetic star (4800 pixels): `amplitude_0 50.056 +/- 0.254`, `x_mean_0 31.2929`, `y_mean_0 24.5885`, `x_stddev_0 4.0309`, `y_stddev_0 2.4796`, `theta_0 0.3990`, background `amplitude_1 10.004`; `rms 1.0039`, `free parameters 7`, `dof 4793`. The **Image / model / residual** tab shows the three panels.

## Tips and limits

- Cut a region around the star first; fitting a whole frame with one Gaussian fails.
- `theta` is in radians. Remember that stddevs can swap if the start values are rotated.
