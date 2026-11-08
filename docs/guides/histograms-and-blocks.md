---
title: Histograms, change points and spatial clustering
order: 42
lede: Choose bins objectively, detect a change in an event rate, test directions and check whether points cluster.
---

## Choosing bins

The data are 550 values from two populations: N(0, 1) × 400 and N(4, 0.5) × 150. Open [Histogram Binning](../reference/analysis/stats_histogram.md).

**Knuth** gives 10 equal bins of width 0.852 (counts 3, 21, 74, 158, 98, 38, 8, 34, 85, 31):

![Knuth bins](../assets/guides/analysis-stats-hist-knuth.png "Knuth's rule.")

**blocks** (Bayesian blocks) gives 8 uneven bins and a cleaner picture of the two populations:

![Bayesian blocks bins](../assets/guides/analysis-stats-hist-blocks.png "Bayesian blocks on the same data.")

## Change points in an event list

[Bayesian Blocks](../reference/analysis/stats_blocks.md) on 400 event times (100 in 0-50, 200 in 50-60, 100 in 60-100) with **Fitness** `events` finds 3 blocks with edges `0.29, 50.05, 59.79, 98.94`: the burst between 50 and 60 is recovered to within about 0.25.

![Bayesian blocks](../assets/guides/analysis-stats-blocks.png "The rate is higher between t = 50 and 60.")

## Directions

[Circular Statistics](../reference/analysis/stats_circular.md) for position angles scattered around 40 degrees gives `circular mean 41.003 deg`, `R = 0.857`, `circular std 30.64 deg` and a von Mises fit with `kappa = 3.81`. Rayleigh's p-value (1.3e-32) rejects a uniform distribution of directions.

![Circular statistics](../assets/guides/analysis-stats-circular.png "Polar plot of position angles.")

## Clustering

[Ripley's K](../reference/analysis/stats_ripley.md) for 150 points arranged in ten tight clusters, with the region `0, 1, 0, 1` and `ohser` edge correction, gives `max |L(r) - r| = 0.111`. A value of 0 would mean random placement.

![Ripley's K and L](../assets/guides/analysis-stats-ripley.png "L(r) - r rises above zero for clustered points.")
