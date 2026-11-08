## What it does

Compares models with the Akaike and Bayesian information criteria.

## How to use

1. **Input**: `Log-likelihood` or `Sum of squared residuals`.
2. Enter **Model A: logL / SSR**, **Model A: parameters** and **Samples**.
3. Tick **Compare with model B** and fill the B fields.
4. Press **Compute**.

## Reading the results

Model A with logL -50, 3 parameters, 100 samples: `AIC = 106.25`, `BIC = 113.8155`. Model B (logL -45, 5 parameters): `AIC = 100.6383`, `BIC = 113.0259`. dAIC = -5.61 favours B, dBIC = -0.79 hardly distinguishes them; the relative likelihood of A over B is 0.0605.

## Tips and limits

- Lower is better; differences above about 10 are strong evidence.
- BIC penalises extra parameters more as the sample grows.
