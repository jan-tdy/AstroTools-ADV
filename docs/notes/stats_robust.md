## What it does

Computes outlier-resistant location and scale: biweight estimators, MAD, midvariance, midcovariance and midcorrelation.

## How to use

1. Choose the **Data**.
2. **c (location)** (6.0) and **c (scale)** (9.0) are the tuning constants; **M (center)** sets the initial centre (empty = median); **Modify sample size** counts only points inside the biweight window.
3. **Matrix (optional)** enables midcovariance and midcorrelation.
4. Press **Compute**.

## Reading the results

On the same 203 values: `biweight_location 100.25453838`, `biweight_scale 5.1516115`, `biweight_midvariance 26.53910108`, `mad_std 5.09392052`, `mad 3.43579718`, against `mean 100.60747548`, `median 100.2164795`, `std 9.43403992`. The ordinary mean and std are pulled by the outliers.

## Tips and limits

- `mad_std` = 1.4826 x MAD, the Gaussian-equivalent sigma.
- Smaller tuning constants reject more aggressively.
