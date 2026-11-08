## What it does

Estimates the uncertainty of any statistic by bootstrap and jackknife resampling.

## How to use

1. Choose the **Data** and the **Statistic**: `mean`, `median`, `std`, `biweight_location`, `biweight_scale`, `mad_std` or `custom` (expression in `x`, such as `np.percentile(x, 90)`).
2. **Bootstrap samples** (1000), **Random seed** (empty = non-reproducible), **Confidence level** (0.95).
3. Press **Run bootstrap + jackknife**.

## Reading the results

Median of 40 values with seed 42: statistic 98.88117615; bootstrap mean / std `99.14062055 / 0.76097581`; 95.0% interval `[98.38912243, 101.27403888]`; jackknife std. error 0.25503346, interval `[98.38131976, 99.38103254]` from 40 resamples of 39 values. **Bootstrap distribution** is a histogram of the statistic.

## Tips and limits

- The jackknife is unreliable for the median (it ignores the sample's discrete structure); trust the bootstrap interval, as the different widths above show.
- Set a seed to reproduce a result.
