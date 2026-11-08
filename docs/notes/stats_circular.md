## What it does

Statistics for angles: circular mean and variance, Rayleigh and V tests, von Mises fit, moments and circular correlation.

## How to use

1. **Angles** with **Angle unit** (`degrees`, `radians`, `hours (hourangle)`), optional **Weights (optional)**.
2. **Second angles (for circcorrcoef)** gives the circular correlation coefficient.
3. **V-test direction mu** is the hypothesised direction; **Moment order p**.
4. Press **Compute**. **Polar plot** draws the angles.

## Reading the results

Scenario angles: `circular mean 41.002993 deg`, `mean resultant length R 0.85700876`, `circular variance 0.14299124`, `circular std 30.640 deg`, `Rayleigh test p-value 1.26658e-32`, `V-test p-value 1.13164e-19`, `von Mises MLE mu = 41.002993 deg, kappa = 3.80789`.

## Tips and limits

- Do not average angles arithmetically; 359 and 1 deg average to 0, not 180.
- Rayleigh tests for any preferred direction; the V test for a given one.
