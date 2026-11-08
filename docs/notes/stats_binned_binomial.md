## What it does

Estimates a success fraction in bins of x from 0/1 outcomes (`binned_binom_proportion`).

## How to use

1. **x values** and **Success (0/1)**: numbers/expression or table columns of equal length.
2. **Bins**: a count (`10`) or a list of edges. **Range** `lo, hi` applies with a bin count.
3. **Confidence level** (0.68269) and **Interval** (`wilson`, `jeffreys`, `flat`, `wald`).
4. Press **Compute**.

## Reading the results

Five bins on the scenario data: `bin_center` 1.02, 3.01, 5.00, 7.00, 8.99, `fraction` 0.138, 0.316, 0.434, 0.736, 0.948 with asymmetric errors (`err_lower`, `err_upper`). **Plot** draws fraction against x with bars.

## Tips and limits

- Each bin needs enough points for a useful interval; use fewer bins for small samples.
- Use this for detection efficiency versus magnitude.
