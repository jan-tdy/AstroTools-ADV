---
title: Outliers, robust statistics and S/N
order: 40
lede: Measure the typical value and the spread of a sample that contains outliers, and estimate the signal-to-noise of an exposure.
---

The sample is 200 values from N(100, 5) plus three gross outliers (160, 175 and 40). The correct answer is therefore a mean near 100 and a scatter near 5.

## Sigma clipping

Open [Sigma Clipping](../reference/analysis/stats_sigmaclip.md), enter the data and press **Compute**.

![Sigma clipping statistics](../assets/guides/analysis-stats-sigmaclip-text.png "Clipped versus unclipped statistics.")

The clip bounds are `85.04 .. 115.22`; four values fall outside them. The clipped statistics are `mean 100.159`, `median 100.131`, `std 5.031`; the unclipped ones `mean 100.607` and `std 9.434`. A handful of outliers nearly doubles the apparent scatter.

![Clipped data plot](../assets/guides/analysis-stats-sigmaclip.png "Clipped values shown on the data.")

## Robust estimators

[Robust Statistics](../reference/analysis/stats_robust.md) does not reject anything but weights down distant points.

![Robust statistics](../assets/guides/analysis-stats-robust.png "The biweight location sits with the bulk of the data.")

`biweight_location 100.2545` and `biweight_scale 5.1516` agree with the clipped values, as do `mad_std 5.0939` and `median 100.2165`. Use these when you cannot decide by eye what an outlier is.

## Bootstrap errors for a statistic

[Bootstrap & Jackknife](../reference/analysis/stats_resampling.md) estimates how well a statistic is known. For the median of 40 values (seed 42) the statistic is `98.881`, the bootstrap standard deviation `0.761` and the 95% interval `[98.389, 101.274]`; the jackknife error is `0.255`.

![Bootstrap distribution](../assets/guides/analysis-stats-resampling.png "Bootstrap distribution of the median.")

For a median, trust the bootstrap: the jackknife gives a much narrower interval.

## Signal-to-noise of an exposure

[CCD Signal-to-Noise](../reference/analysis/stats_snr.md) with a 10 e-/s source, 1 e-/s/pix sky, 0.1 e-/s/pix dark, 5 e- read noise and a 20-pixel aperture:

![S/N versus exposure time](../assets/guides/analysis-stats-snr.png "Signal-to-noise against exposure time for a faint source.")

S/N is `0.43` at 1 s (the read noise dominates), `9.72` at 41.6 s and `19.28` at 133 s. S/N reaches 10 at about 43 s; doubling the S/N from the 41.6 s value to 19.3 took about 3.2 times the exposure.
